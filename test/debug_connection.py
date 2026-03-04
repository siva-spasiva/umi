import httpx
import asyncio
import os

async def main():
    print("🔍 Testing connection to GPU Server (Port 8001)...")
    
    # 1. Test localhost
    url = "http://localhost:8001/" # Root path on server usually returns 404 but confirms connection
    print(f"\n1. Trying {url}...")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            print(f"   ✅ Connected! Status: {resp.status_code}")
    except Exception as e:
        print(f"   ❌ Failed: {e}")

    # 2. Test 127.0.0.1
    url = "http://127.0.0.1:8001/"
    print(f"\n2. Trying {url}...")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            print(f"   ✅ Connected! Status: {resp.status_code}")
    except Exception as e:
        print(f"   ❌ Failed: {e}")

    # 3. Check Proxy Evironment Variables
    print("\n3. Environment Variables:")
    print(f"   HTTP_PROXY: {os.environ.get('HTTP_PROXY', 'Not Set')}")
    print(f"   HTTPS_PROXY: {os.environ.get('HTTPS_PROXY', 'Not Set')}")
    print(f"   ALL_PROXY: {os.environ.get('ALL_PROXY', 'Not Set')}")

if __name__ == "__main__":
    asyncio.run(main())
