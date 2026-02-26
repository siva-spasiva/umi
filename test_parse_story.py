import re
import json

def _extract_json_objects(text: str):
    if not text:
        raise ValueError("empty response")
    
    raw = text.strip()
    raw = re.sub(r"^```json\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"```\s*$", "", raw)
    
    if not raw.startswith("{"):
        if '"ending_type"' in raw: # Guess it's an epilogue that skipped prefix
            raw = '{\n  "title": "기록 정리",\n  "text": "' + raw
        else:
            raw = "{\n" + raw
            
    # Gemma JSON hallucination fixes
    if raw.count("{") > raw.count("}"):
        raw += "\n}"
        
    raw = re.sub(r",\s*}", "}", raw)

    candidates = []
    candidates.append(raw)

    first = raw.find("{")
    last = raw.rfind("}")
    if first != -1 and last != -1 and first < last:
        candidates.append(raw[first:last + 1])
        
    return candidates

broken_json = """남겨두었으나, 아직도 불명확한 부분이 많습니다. 특히, 응답의 형식이 불안정함으로써 단서를 해석하는 데 어려움을 겪었습니다. 이로 인해 이전의 증거들이 더욱 의심스러워졌습니다.",
  "ending_type": "failure",
  "reason": "불안정한 응답 형식으로 인해 핵심 단서를 정확히 파악하지 못하였음."
}"""

cands = _extract_json_objects(broken_json)
success = False
for c in cands:
    try:
        j = json.loads(c)
        print("SUCCESS:", j)
        success = True
    except Exception as e:
        print("FAIL:", e)

if not success:
    exit(1)
