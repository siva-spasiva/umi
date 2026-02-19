
import unittest
import os
import sys
import json
from unittest.mock import MagicMock, patch

# 프로젝트 루트를 sys.path에 추가 (test/ 디렉토리에서 직접 실행 가능하도록)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.agents.npc_pipeline import NPCDialoguePipeline, NPCPromptLoader, RAGRetriever
from app.agents.npc_dialogue_engine import NPCState, IntentAnalyzer

from langchain_core.runnables import RunnableLambda

class MockAnalyzer:
    def analyze(self, text):
        return {
            "reason_tags": ["TEST_TAG"],
            "friendly_delta": 5,
            "faith_delta": -2,
            "tag_probs": {}
        }

class TestV3PipelineLogic(unittest.TestCase):
    def setUp(self):
        # Setup paths
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dir = os.path.join(self.base_dir, "app", "data")
        self.prompt_json = os.path.join(self.data_dir, "NPC_prompt.json")
        self.char_json = os.path.join(self.data_dir, "characters.json")
        
        # Verify files exist
        if not os.path.exists(self.prompt_json) or not os.path.exists(self.char_json):
            self.skipTest("Data files not found")

        self.loader = NPCPromptLoader(self.prompt_json, self.char_json)

    def test_prompt_loader(self):
        """Test if NPCPromptLoader loads data correctly"""
        npc_id = "gwakbing"
        
        # Test Korean name mapping
        korean_name = self.loader.get_korean_name(npc_id)
        self.assertEqual(korean_name, "곽빙어")
        
        # Test Initial State
        state = self.loader.get_initial_state(npc_id)
        self.assertIsInstance(state, NPCState)
        
        # Test Persona Prompt Retrieval
        prompt = self.loader.build_persona_prompt(npc_id, friendly=50)
        self.assertTrue(len(prompt) > 0)
        self.assertIn("곽빙어", prompt)

    def test_pipeline_state_update(self):
        """Test if pipeline updates state correctly after chat"""
        npc_id = "gwakbing"
        initial_state = NPCState(friendly=50, faith=50)
        
        # Mock LLM using RunnableLambda
        mock_llm = RunnableLambda(lambda x: "테스트 응답입니다.")
        
        pipeline = NPCDialoguePipeline(
            analyzer=MockAnalyzer(),
            llm=mock_llm,
            prompt_loader=self.loader,
            npc_id=npc_id,
            initial_state=initial_state,
            retriever=None # Disable RAG for this test
        )
        
        # Chat
        pipeline.chat("Hello")
        
        # Check State Update (MockAnalyzer returns +5 friendly, -2 faith)
        self.assertEqual(pipeline.state.friendly, 55)
        self.assertEqual(pipeline.state.faith, 48)

    def test_system_prompt_construction(self):
        """Test if system prompt contains all necessary components"""
        npc_id = "gwakbing"
        
        # Mock LLM using RunnableLambda
        mock_llm = RunnableLambda(lambda x: "테스트 응답입니다.")
        
        pipeline = NPCDialoguePipeline(
            analyzer=MockAnalyzer(),
            llm=mock_llm,
            prompt_loader=self.loader,
            npc_id=npc_id,
            retriever=None
        )
        
        analysis = {
            "reason_tags": ["TEST_TAG"],
            "friendly_delta": 0,
            "faith_delta": 0
        }
        
        # Build prompt
        prompt = pipeline._build_system_prompt("Test Input", analysis, context="RAG Context")
        
        # Verify Components
        self.assertIn("곽빙어", prompt) # Persona
        self.assertIn("RAG Context", prompt) # RAG
        self.assertIn("REASON_TAGS=TEST_TAG", prompt) # Control Signal
        self.assertIn("오직 '한국어'로만 출력하십시오", prompt) # Korean Constraint
    def test_dynamic_persona_rag(self):
        """Test if Dynamic Persona RAG retrieves affinity-appropriate rules"""
        npc_id = "gwakbing"
        
        # PersonaRAG should be initialized
        self.assertIsNotNone(self.loader.persona_rag)
        self.assertTrue(self.loader.persona_rag.enabled)
        
        # "bad" bucket (friendly ≤ 19) → 경계/거절 관련 규칙
        rules_bad = self.loader.retrieve_dynamic_rules(npc_id, friendly=10, user_message="도움을 줘")
        self.assertIn("bad", rules_bad)  # bucket label
        
        # "good" bucket (friendly 46-75) → 협력/정보 제공 관련 규칙
        rules_good = self.loader.retrieve_dynamic_rules(npc_id, friendly=50, user_message="금고 접근법 알려줘")
        self.assertIn("good", rules_good)  # bucket label
        
        # 서로 다른 규칙이 반환되어야 함
        self.assertNotEqual(rules_bad, rules_good)

    def test_core_vs_dynamic_split(self):
        """Test if Core (static) and Dynamic (RAG) are properly separated"""
        npc_id = "gwakbing"
        
        # Core prompt should contain PERSONALITY and SPEECH_STYLE, not BEHAVIOR_RULES
        core = self.loader.get_core_prompt(npc_id, friendly=50)
        self.assertIn("[PERSONALITY]", core)
        self.assertIn("[SPEECH_STYLE]", core)
        # BEHAVIOR_RULES should NOT be in the core (it's offloaded to RAG)
        self.assertNotIn("[BEHAVIOR_RULES]", core)

    def test_system_prompt_with_dynamic_rules(self):
        """Test if system prompt includes dynamic rules from RAG"""
        npc_id = "gwakbing"
        mock_llm = RunnableLambda(lambda x: "테스트 응답입니다.")
        
        pipeline = NPCDialoguePipeline(
            analyzer=MockAnalyzer(),
            llm=mock_llm,
            prompt_loader=self.loader,
            npc_id=npc_id,
            retriever=None
        )
        
        analysis = {
            "reason_tags": ["TEST_TAG"],
            "friendly_delta": 0,
            "faith_delta": 0
        }
        
        prompt = pipeline._build_system_prompt("금고를 열고 싶어", analysis)
        
        # Core components
        self.assertIn("[PERSONALITY]", prompt)
        self.assertIn("[SPEECH_STYLE]", prompt)
        # Dynamic component
        self.assertIn("[DYNAMIC_GUIDELINES", prompt)
        # Korean constraint
        self.assertIn("오직 '한국어'로만 출력하십시오", prompt)

if __name__ == "__main__":
    unittest.main()
