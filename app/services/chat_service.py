from app.services.base_service import BaseService
from app.schemas.chat import DayLog
from app.schemas.story import (
    StorySummary, Diary, KeyConversation, ItemUsage, Clue,
    TrollAnalysis, ConsistencyCheck, GameEnding, NextDayFlag, SafetyCheck
)
from app.agents.ga1_agent import ga1_agent
from app.agents.ga2_context import ga2_context
from app.agents.llm_engine import llm_engine
from app.agents.guardrail import ga_agent

from langsmith import traceable

import json
import os
from typing import Optional
from app.core.masking_utils import word_masker

from app.services.inventory_service import inventory_service

class ChatService(BaseService):
    def __init__(self):
        super().__init__()
        self.collection = self.db["chat_logs"]

    def _normalize_item_id(self, item_id: Optional[str]) -> Optional[str]:
        """
        Swagger 기본 placeholder("string") 및 빈 입력을 무시한다.
        """
        if item_id is None:
            return None
        value = str(item_id).strip()
        if not value:
            return None
        if value.lower() in {"null", "none", "string"}:
            return None
        return value
    
    @traceable(run_type="chain", name="Chat_Flow_Pipeline")
    async def process_chat_flow(self, user_id: str, npc_id: str, message: str, item_id: str = None):
        """
        GA1 -> GA2 -> LLM -> Output Guardrail 파이프라인
        """
        item_id = self._normalize_item_id(item_id)

        # [Item Usage Logic]
        system_injection = ""
        if item_id:
            # 1. 소유 확인
            has_item = await inventory_service.check_item_ownership(user_id, item_id)
            if has_item:
                # 2. 아이템 정보 조회
                item_info = await inventory_service.get_item_info(item_id)
                if item_info:
                    item_name = item_info.get("name", "Unknown Item")
                    # 3. 프롬프트 주입
                    system_injection = f"\n[System] User uses item: {item_name}"
                    
                    # 4. 소모품 처리 (consumable=True인 경우)
                    if item_info.get("consumable") is True:
                        await inventory_service.use_item(user_id, item_id)
                        system_injection += " (The item has been consumed)"
            else:
                print(f"⚠️ [Chat] User {user_id} tried to use item {item_id} but does not own it.")

        # 0. Basic Guardrail: 기본 규칙 검증 (길이, 금지어 등)
        is_basic_safe, basic_msg = await ga_agent.validate_input(message)
        if not is_basic_safe:
            triggered_skip, troll_count = await self.handle_troll_event(user_id, "BASIC_GUARDRAIL", basic_msg)
            if triggered_skip:
                return {
                    "response": basic_msg + "\n\n(시스템: 경고 3회 누적으로 인해 하루가 강제 종료되었습니다. 다음 날로 넘어갑니다.)",
                    "status": "blocked_by_troll_limit",
                    "troll_count": troll_count,
                    "force_skip": True
                }
            return {"response": basic_msg, "status": "blocked_by_guardrail", "troll_count": troll_count}

        # 1. GA1: 입력 안전성 검증
        is_safe, safety_msg = await ga1_agent.check_safety(message)
        if not is_safe:
            # 트롤 레벨 증가 및 체크
            triggered_skip, troll_count = await self.handle_troll_event(user_id, "GA1_BLOCK", safety_msg)
            if triggered_skip:
                return {
                    "response": safety_msg + "\n\n(시스템: 경고 3회 누적으로 인해 하루가 강제 종료되었습니다. 다음 날로 넘어갑니다.)",
                    "status": "blocked_by_troll_limit",
                    "troll_count": troll_count,
                    "force_skip": True
                }
            return {"response": safety_msg, "status": "blocked_by_ga1", "troll_count": troll_count}

        # 2. GA2: 문맥 및 세계관 검증
        # TODO : 아직 GA2모델이 개발되지 않아서 사용 (History는 LLM에 전달)
        history = await self._get_recent_history(user_id, npc_id, limit=5)
        # is_context_ok, context_msg = await ga2_context.check_context(message, history)
        # if not is_context_ok:
        #     return {"response": context_msg, "status": "blocked_by_ga2"}

        # 3. LLM Generation (Dict 반환: response + analysis + state)
        # 아이템 사용 문구가 있으면 메시지 뒤에 추가하여 LLM에 전달
        full_message = message + system_injection
        llm_result = await llm_engine.ask(npc_id, full_message, history)
        raw_response = llm_result.get("response", "")

        # [Word Masking] 
        # 1. NPC Fish Level 확인
        npc_state = llm_result.get("state", {})
        npc_fish_level = npc_state.get("fish_level", 0)
        
        # 2. User Fish Level 확인 (DB 조회)
        user_state = await self.db["user_states"].find_one({"user_id": user_id})
        user_fish_level = user_state.get("fish_level", 0) if user_state else 0
        
        # 3. 마스킹 로직 적용
        # 조건: NPC 레벨이 유저보다 2 이상 높을 때 -> Heavy Masking (금기어 + 랜덤 80%)
        if npc_fish_level - user_fish_level >= 2:
            # 1단계: 금기어 마스킹 (100% 차단)
            raw_response = word_masker.mask_text(raw_response)
            # 2단계: 남은 단어 80% 랜덤 마스킹
            raw_response = word_masker.mask_randomly(raw_response, ratio=0.8)
            
        # 조건: 그 외 NPC 생선화 3단계 이상 -> 일반 마스킹 (금기어만)
        elif npc_fish_level >= 3:
            raw_response = word_masker.mask_text(raw_response)

        # 4. Output Guardrail (페르소나 체크 등)
        is_output_safe, final_response = await ga_agent.validate_output(raw_response)
        
        # LLM 결과 검증 및 분석 데이터 추출
        analysis = llm_result.get("analysis", {})
        
        
        # 실제 DB 업데이트는 호출하는 쪽(router)이나 여기서 수행 가능
        # 현재 구조상 반환값에 포함시켜 router에서 처리하거나,
        # stats_service를 여기서 호출하여 즉시 반영할 수도 있음.
        # 기존 로직 유지를 위해 반환값에 반영
        
        return {
            "response": final_response,
            "npcId": npc_id,
            "status": "success" if is_output_safe else "sanitized",
            "analysis": analysis,
            "state": llm_result.get("state") # state는 현재 스냅샷이므로 유지하되, 다음 턴에 반영됨
        }

    async def _get_recent_history(self, user_id: str, npc_id: str = None, limit: int = 5):
        """DB에서 해당 유저와 NPC의 최근 대화 내역을 가져옵니다. npc_id가 없으면 전체 대화."""
        if npc_id:
            query = {"conversation.participants.name": {"$in": [user_id, npc_id]}}
        else:
            query = {"conversation.participants.name": user_id}
        
        cursor = self.collection.find(query).sort("_id", -1).limit(limit)
        
        logs = await cursor.to_list(length=limit)
        history = []
        for log in reversed(logs):
            for msg in log.get("conversation", {}).get("messages", []):
                history.append({"speaker": msg["speaker"], "content": msg["content"]})
        return history

    async def save_chat_log(self, log_data: DayLog):
        """복잡한 게임 로그 데이터를 저장"""
        # Pydantic 모델을 dict로 변환 (datetime 처리 포함)
        doc = log_data.model_dump()

        # 정제 작업: 예를 들어 메시지 내용의 공백 제거
        for msg in doc["conversation"]["messages"]:
            msg["content"] = msg["content"].strip()

        # MongoDB 저장
        result = await self.collection.insert_one(doc)
        return str(result.inserted_id)

    # 기존 ChatService 내부에 추가
    async def create_diary_entry(self, user_id: str, day_index: int = None):
        """
        하루 동안의 모든 대화 로그를 기반으로 StorySummary(일기 등)를 생성하여 저장
        """
        from app.agents.story_agent import story_agent
        
        # 1. Day Index 자동 감지 (입력되지 않은 경우)
        if day_index is None:
            day_index = await self._get_current_day_index(user_id)
            # 현재 진행 중인 날짜는 아직 끝나지 않았을 수 있으므로 주의. 
            # 보통 end_day 시점이나 summary 요청 시점이므로 현재 날짜가 맞음.
        
        # 2. 해당 날짜에 대한 모든 Chat Logs 조회
        # chat_logs 구조: { ..., "day_index": 1, ... } (스키마 확인 필요)
        # 현재 DayLog 스키마에는 day_index 필드가 없음. (timestamp만 있음)
        # TODO: DayLog에 day_index를 추가하거나, timestamp로 필터링해야 함.
        # 일단은 모든 로그를 가져와서 day_index를 추정하거나, user_states를 참고?
        # 임시로 '가장 최근 50개 대화'를 가져온다고 가정하거나, 
        # DayLog 저장 시 day_index를 넣도록 수정해야 완벽함.
        # 여기서는 "해당 유저의 모든 로그" 중 가장 최근 것들을 가져와 LLM에게 판단 맡기거나,
        # API에서 day_index를 받아도 DB에 없으면 필터링 불가.
        # -> 일단 최근 대화 30턴을 가져와서 요약한다고 가정. (프로토타입)
        
        history = await self._get_recent_history(user_id, npc_id=None, limit=50) 
        # _get_recent_history는 npc_id=None이면 전체를 가져오도록 수정 필요.
        # 현재 구현은 npc_id 필수 아님? -> _get_recent_history 서명: (user_id, npc_id, limit)
        
        # 로그 텍스트 변환
        messages_text = ""
        for h in history:
            messages_text += f"[{h['speaker']}]: {h['content']}\n"
            
        # 3. LLM 호출 (StoryAgent)
        summary_data_dict = await story_agent.generate_diary_summary(messages_text, day_index)
        
        if "error" in summary_data_dict:
            raise Exception(f"Failed to generate diary: {summary_data_dict['error']}")
            
        # 4. 저장 (StorySummary 객체 변환 후)
        # 딕셔너리를 바로 저장해도 되지만 검증을 위해 변환
        try:
            summary_data_dict["user_id"] = user_id
            summary_obj = StorySummary(**summary_data_dict)
            await self.save_story_summary(summary_obj)
            
            # [NEW] 5일차인 경우 엔딩 자동 생성 트리거
            if day_index == 5:
                print(f"🏁 [Chat] Day 5 reached for {user_id}. Triggering Epilogue...")
                try:
                    await self.create_ending(user_id)
                except Exception as ending_err:
                    print(f"⚠️ [Chat] 엔딩 자동 생성 실패: {ending_err}")

            return summary_obj
        except Exception as e:
            print(f"[ChatService] Validation Failed: {e}")
            # 검증 실패해도 일단 raw dict로 저장하거나 에러 반환
            # 여기서는 에러 반환
            raise e

    async def save_story_summary(self, summary_data: StorySummary):
        """LLM이 생성한 스토리 요약 및 분석 결과를 저장"""
        # model_dump(by_alias=True)를 사용해야 'with' 필드가 제대로 저장됩니다.
        doc = summary_data.model_dump(by_alias=True)

        # 중복 저장 방지 (user_id & day_index 기준 upsert)
        result = await self.db["story_diary"].update_one(
            {"user_id": doc["user_id"], "day_index": doc["day_index"]},
            {"$set": doc},
            upsert=True
        )
        return "updated" if result.matched_count else "inserted"

    async def handle_troll_event(self, user_id: str, action_type: str, reason: str) -> tuple[bool, int]:
        """
        트롤 이벤트를 기록하고, 레벨이 평계치(3)에 도달하면 True 반환 (Skip Trigger)
        """
        day_index = await self._get_current_day_index(user_id)
        
        user_state = await self.db["user_states"].find_one({"user_id": user_id})
        if not user_state:
            user_state = {"user_id": user_id, "troll_count": 0, "day_index": day_index}
        
        current_count = user_state.get("troll_count", 0) + 1
        
        await self.db["user_states"].update_one(
            {"user_id": user_id},
            {"$set": {"troll_count": current_count, "day_index": day_index}},
            upsert=True
        )
        
        print(f"🚨 [Troll] User {user_id} Warning ({current_count}/3) - {reason}")
        
        # 3. 임계치 체크
        if current_count >= 3:
            await self._skip_to_next_day(user_id, day_index)
            return True, current_count
            
        return False, current_count

    async def _get_current_day_index(self, user_id: str) -> int:
        """유저의 현재 진행 일차(Day Index)를 조회"""
        # 1. UserState 확인
        user_state = await self.db["user_states"].find_one({"user_id": user_id})
        if user_state and "day_index" in user_state:
            return user_state["day_index"]
            
        # 2. 없다면 StorySummary(회고록)에서 가장 최근 날짜 조회
        # [REFACTOR] story_summaries -> story_diary
        latest_summary = await self.db["story_diary"].find_one(
            sort=[("day_index", -1)] # TODO: user_id 필드가 story_summaries에 있다면 필터 추가 필요
        )
        if latest_summary:
            return latest_summary["day_index"] + 1
            
        # 3. 기본값 1
        return 1

    async def _skip_to_next_day(self, user_id: str, day_index: int):
        """
        강제로 하루를 종료하고, '망쳐버린 하루' 요약을 생성하여 저장.
        """
        print(f"💀 [Troll] User {user_id} - Day {day_index} FORCED SKIP")
        
        # 1. 망친 하루 요약 저장
        failed_summary = StorySummary(
            user_id=user_id,
            day_index=day_index,
            diary=Diary(
                title="망쳐버린 하루",
                text="오늘 하루종일 이상한 소리만 하다가 시간을 낭비했다. 마을 사람들의 시선이 따갑다.",
                tone="regretful"
            ),
            summary_bullets=[
                "플레이어의 불손한 태도로 인해 대화가 단절됨",
                "마을에서 평판이 급격히 하락함",
                "아무런 소득 없이 하루를 마감함"
            ],
            key_conversations=[],
            items=[],
            clues=[],
            troll_level_analysis=TrollAnalysis(
                delta_total=3,
                top_causes=["abusive_language", "safety_violation"]
            ),
            consistency_check=ConsistencyCheck(
                contradictions_found=[],
                missing_info=[]
            ),
            ending=GameEnding(
                status="continue",
                ending_type="failure",
                reason="Troll limit exceeded",
                required_next_step="be_polite"
            ),
            flags_for_next_day=[
                NextDayFlag(flag="villager_hostility", why="Player Trolling")
            ],
            safety=SafetyCheck(
                hallucination_risk="low",
                spoiler_blocked=True
            )
        )
        
        await self.save_story_summary(failed_summary)
        
        # 2. 유저 상태 업데이트 (다음 날로, 트롤 카운트 리셋)
        await self.db["user_states"].update_one(
            {"user_id": user_id},
            {"$set": {
                "day_index": day_index + 1,
                "troll_count": 0
            }}
        )

    async def create_ending(self, user_id: str):
        """
        1~5일차의 모든 일기를 수집하여 최종 엔딩(에필로그)을 생성합니다.
        """
        from app.agents.story_agent import story_agent
        from app.schemas.story import EpilogueResponse

        # 1. 1~5일차의 모든 일기(Diary) 조회
        diaries = []
        cursor = self.db["story_diary"].find(
            {"user_id": user_id, "day_index": {"$lte": 5}}
        ).sort("day_index", 1)
        
        summaries = await cursor.to_list(length=5)
        for s in summaries:
            diary_data = s.get("diary", {})
            diaries.append({
                "day": s.get("day_index"),
                "title": diary_data.get("title"),
                "text": diary_data.get("text")
            })

        if not diaries:
            raise Exception("엔딩을 생성할 일기 데이터가 없습니다.")

        # 2. StoryAgent 호출 (EPILOGUE 모드)
        ending_dict = await story_agent.generate_story_content(mode="EPILOGUE", data=diaries)
        
        if "error" in ending_dict:
            raise Exception(f"Failed to generate ending: {ending_dict['error']}")
            
        # 3. 저장 및 반환
        try:
            ending_dict["user_id"] = user_id
            ending_obj = EpilogueResponse(**ending_dict)
            
            await self.db["game_endings"].update_one(
                {"user_id": user_id},
                {"$set": ending_obj.model_dump()},
                upsert=True
            )
            return ending_obj
        except Exception as e:
            print(f"[ChatService] Ending Validation Failed: {e}")
            raise e

chat_service = ChatService()
