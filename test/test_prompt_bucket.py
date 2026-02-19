import sys
import os
import json
import unittest

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.npc_pipeline import NPCPromptLoader
from app.agents.npc_dialogue_engine import get_relationship_bucket

class TestPromptBucket(unittest.TestCase):
    def setUp(self):
        # Calculate absolute path to app/data/NPC_prompt.json
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.prompt_path = os.path.join(base_dir, "app", "data", "NPC_prompt.json")
        
        if not os.path.exists(self.prompt_path):
            self.skipTest(f"NPC_prompt.json not found at {self.prompt_path}")
        self.loader = NPCPromptLoader(self.prompt_path)
        self.npc_id = "cheonggalchi"

    def test_bucket_ranges(self):
        """Verify get_relationship_bucket returns correct bucket for score ranges"""
        test_cases = [
            (0, "bad"),
            (19, "bad"),
            (20, "normal"),
            (45, "normal"),
            (46, "good"),
            (75, "good"),
            (76, "perfect"),
            (100, "perfect"),
        ]
        
        print("\n[Testing Bucket Ranges]")
        for score, expected in test_cases:
            result = get_relationship_bucket(score)
            print(f"  Score {score} -> {result} (Expected: {expected})")
            self.assertEqual(result, expected)

    def test_prompt_content_loading(self):
        """Verify NPCPromptLoader returns unique content for each bucket"""
        print(f"\n[Testing Prompt Content for {self.npc_id}]")
        
        buckets = {
            "bad": 10,
            "normal": 30,
            "good": 60,
            "perfect": 90
        }
        
        loaded_prompts = {}
        
        for bucket_name, score in buckets.items():
            prompt_text = self.loader.build_persona_prompt(self.npc_id, score)
            loaded_prompts[bucket_name] = prompt_text
            
            # Simple check: The prompt should contain the bucket name implicitly or explicitly 
            # (In our case, we check if the prompts are different)
            print(f"  Score {score} ({bucket_name}): Length {len(prompt_text)}")
            print(f"  --- PROMPT CONTENT START ({bucket_name}) ---")
            print(prompt_text)
            print(f"  --- PROMPT CONTENT END ({bucket_name}) ---\n")
            
            # Check for unique keywords if possible, or just ensure they are different
            # Based on translation, "Identity" description changes.
        
        # Verify that all loaded prompts are distinct
        unique_prompts = set(loaded_prompts.values())
        self.assertEqual(len(unique_prompts), 4, "All 4 buckets should have distinct prompts")
        print("  ✅ All 4 buckets returned distinct prompts.")

if __name__ == "__main__":
    unittest.main()
