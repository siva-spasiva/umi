"""
NPC 배치 대화 테스트
- filtered_text_only.csv의 텍스트를 각 NPC에게 보내서 응답을 확인
- 대화 기억 없이 매번 새로운 대화 (history=None)
- 결과를 CSV로 저장

사용법:
    python test_npc_batch.py
    python test_npc_batch.py --limit 10       # 처음 10개만
    python test_npc_batch.py --npc NPC_CHEONG_02  # 특정 NPC만
"""

import csv
import json
import time
import httpx
import argparse
from datetime import datetime
from pathlib import Path


# ============================================================
# 설정
# ============================================================

GPU_SERVER_URL = "http://localhost:8001"
NPC_IDS = ["NPC_KWAK_01", "NPC_CHEONG_02", "NPC_PARK_03", "NPC_JEON_04"]
NPC_NAMES = {
    "NPC_KWAK_01": "곽빙어",
    "NPC_CHEONG_02": "청갈치", 
    "NPC_PARK_03": "박복어",
    "NPC_JEON_04": "전광어"
}
INPUT_CSV = "app/data/filtered_text_only.csv"
OUTPUT_DIR = "npc_batch_results"


def load_texts(csv_path: str, limit: int = None) -> list:
    """CSV에서 텍스트 전체 로드 (중복 포함)"""
    texts = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            text = row["text"].strip()
            if text:
                texts.append(text)
    
    if limit:
        texts = texts[:limit]
    
    print(f"[데이터] {len(texts)}개 텍스트 로드됨 (from {csv_path})")
    return texts


def send_message(npc_id: str, message: str, timeout: int = 120) -> dict:
    """GPU 서버에 NPC 대화 요청 (기억 없이 새 대화)"""
    payload = {
        "npc_id": npc_id,
        "message": message,
        "history": None,          # 대화 기억 없음
        "memory_context": None    # 장기 기억 없음
    }
    
    try:
        start = time.time()
        resp = httpx.post(
            f"{GPU_SERVER_URL}/infer/npc",
            json=payload,
            timeout=timeout
        )
        elapsed = time.time() - start
        resp.raise_for_status()
        data = resp.json()
        
        return {
            "success": True,
            "response": data.get("response", ""),
            "analysis": data.get("analysis", {}),
            "state": data.get("state", {}),
            "elapsed": round(elapsed, 2)
        }
    except Exception as e:
        return {
            "success": False,
            "response": f"ERROR: {e}",
            "analysis": {},
            "state": {},
            "elapsed": 0
        }


def run_batch(npc_ids: list, texts: list, output_dir: str):
    """전 NPC × 전 텍스트 배치 실행"""
    Path(output_dir).mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    all_results = []
    
    for npc_id in npc_ids:
        npc_name = NPC_NAMES.get(npc_id, npc_id)
        print(f"\n{'='*60}")
        print(f"🐟 NPC: {npc_name} ({npc_id})")
        print(f"{'='*60}")
        
        npc_results = []
        
        for i, text in enumerate(texts):
            print(f"\n[{i+1}/{len(texts)}] 플레이어: {text}")
            
            result = send_message(npc_id, text)
            
            if result["success"]:
                analysis = result["analysis"]
                print(f"  {npc_name}: {result['response']}")
                print(f"  [분석] 태그={analysis.get('reason_tags', [])}, "
                      f"호감={analysis.get('friendly_delta', 0):+d}, "
                      f"신뢰={analysis.get('faith_delta', 0):+d} "
                      f"({result['elapsed']}s)")
            else:
                print(f"  ❌ {result['response']}")
            
            row = {
                "npc_id": npc_id,
                "npc_name": npc_name,
                "input": text,
                "response": result["response"],
                "success": result["success"],
                "tags": ", ".join(result["analysis"].get("reason_tags", [])),
                "friendly_delta": result["analysis"].get("friendly_delta", 0),
                "faith_delta": result["analysis"].get("faith_delta", 0),
                "friendly": result["state"].get("friendly", "?"),
                "faith": result["state"].get("faith", "?"),
                "elapsed_sec": result["elapsed"]
            }
            npc_results.append(row)
            all_results.append(row)
        
        # NPC별 CSV 저장
        npc_csv = f"{output_dir}/{npc_id}_{timestamp}.csv"
        _save_csv(npc_results, npc_csv)
        print(f"\n💾 {npc_name} 결과 저장: {npc_csv}")
    
    # 전체 결과 CSV
    all_csv = f"{output_dir}/all_npcs_{timestamp}.csv"
    _save_csv(all_results, all_csv)
    
    # 요약
    print(f"\n{'='*60}")
    print(f"📊 배치 테스트 완료")
    print(f"{'='*60}")
    print(f"  총 요청: {len(all_results)}건")
    print(f"  성공률: {sum(1 for r in all_results if r['success'])}/{len(all_results)}")
    
    successes = [r for r in all_results if r["success"]]
    if successes:
        avg_time = sum(r["elapsed_sec"] for r in successes) / len(successes)
        print(f"  평균 응답 시간: {avg_time:.2f}s")
    
    for npc_id in npc_ids:
        npc_rows = [r for r in all_results if r["npc_id"] == npc_id and r["success"]]
        if npc_rows:
            avg_f = sum(r["friendly_delta"] for r in npc_rows) / len(npc_rows)
            avg_t = sum(r["faith_delta"] for r in npc_rows) / len(npc_rows)
            name = NPC_NAMES.get(npc_id, npc_id)
            print(f"  {name}: 평균 호감Δ={avg_f:+.2f}, 평균 신뢰Δ={avg_t:+.2f}")
    
    print(f"\n💾 전체 결과 저장: {all_csv}")


def _save_csv(rows: list, path: str):
    if not rows:
        return
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NPC 배치 대화 테스트")
    parser.add_argument("--limit", type=int, default=None, help="테스트할 텍스트 수 제한")
    parser.add_argument("--npc", type=str, default=None, help="특정 NPC만 테스트 (예: NPC_CHEONG_02)")
    parser.add_argument("--timeout", type=int, default=120, help="요청 타임아웃 (초)")
    args = parser.parse_args()
    
    texts = load_texts(INPUT_CSV, limit=args.limit)
    
    npc_ids = [args.npc] if args.npc else NPC_IDS
    
    # GPU 서버 상태 확인
    try:
        health = httpx.get(f"{GPU_SERVER_URL}/health", timeout=5)
        print(f"[서버] GPU 서버 상태: {health.json()}")
    except Exception as e:
        print(f"⚠️ GPU 서버 연결 실패: {e}")
        print("connect_aws.sh를 먼저 실행해주세요.")
        exit(1)
    
    run_batch(npc_ids, texts, OUTPUT_DIR)
