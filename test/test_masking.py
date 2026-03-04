import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Test only the utility to avoid DB dependencies
from app.core.masking_utils import word_masker

def test_masking_logic():
    print("=== Word Masking Logic Test (Utility) ===")
    
    # Check loaded words
    count = len(word_masker.forbidden_words)
    print(f"Loaded forbidden words count: {count}")
    assert count > 0, "Dictionary not loaded"
    
    # Test Cases
    test_cases = [
        ("어머니 바다의 축복을 받으세요.", "뻐끔의 뻐끔을 받으세요."), # "어머니 바다", "축복" masked
        ("솔피는 우리의 구원입니다.", "뻐끔는 우리의 구원입니다."), # "솔피" masked
        ("이곳은 교주님의 기록실입니다.", "이곳은 뻐끔님의 뻐끔입니다."), # "교주", "기록실" masked
        ("안녕하세요, 평범한 대화입니다.", "안녕하세요, 평범한 대화입니다.") # No mask
    ]
    
    for input_text, expected_part in test_cases:
        masked = word_masker.mask_text(input_text)
        print(f"Input:    {input_text}")
        print(f"Masked:   {masked}")
        
        # Check if forbidden words are gone
        for word in word_masker.forbidden_words:
            if word in input_text:
                if word in masked:
                    print(f"❌ Failed to mask '{word}'")
                    raise AssertionError(f"Failed to mask '{word}'")
        
        # Simple assertion for '뻐끔' presence if masking expected
        if input_text != masked:
            assert "뻐끔" in masked
            
    print("\n✅ All masking tests passed!")

if __name__ == "__main__":
    try:
        test_masking_logic()
    except Exception as e:
        print(f"❌ Test failed: {e}")
        exit(1)
