import requests
import json

def check_health():
    url = "http://127.0.0.1:8001/health"
    try:
        print(f"Connecting to {url}...")
        res = requests.get(url, timeout=5)
        print(f"Status Code: {res.status_code}")
        print("Response:")
        print(json.dumps(res.json(), indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Connection failed: {e}")

def check_inference():
    url = "http://127.0.0.1:8001/infer/story/diary"
    payload = {
        "messages": "User: Hello\nNPC: Hi there.",
        "fish_level": 0,
        "max_new_tokens": 50
    }
    try:
        print(f"\nTesting Inference at {url}...")
        res = requests.post(url, json=payload, timeout=30)
        print(f"Status Code: {res.status_code}")
        if res.status_code == 200:
            print("Response:")
            print(json.dumps(res.json(), indent=2, ensure_ascii=False))
        else:
            print(f"Error: {res.text}")
    except Exception as e:
        print(f"Inference failed: {e}")

if __name__ == "__main__":
    check_health()
    check_inference()
