import httpx
import asyncio
import subprocess
import json

async def test_rest_and_cli():
    url = "http://127.0.0.1:15151/start-headless-download"
    cli_path = r"C:\Users\shiva\AppData\Local\ABDownloadManager\ABDownloadManagerCli.exe"
    
    payload = {
        "downloadSource": {
            "link": "https://raw.githubusercontent.com/amir1376/ab-download-manager/main/README.md"
        },
        "name": "test_rest_interop.txt",
        "folder": r"C:\Users\shiva\Downloads\ABDM",
        "queueId": 0
    }
    
    print("1. Sending POST /start-headless-download via REST...")
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload)
        print(f"   REST Response Status: {resp.status_code}")
        print(f"   REST Response Body: {resp.text}")
    
    print("\n2. Querying CLI: abdm download show...")
    proc = subprocess.run([cli_path, "download", "show"], capture_output=True, text=True)
    print("   CLI stdout:")
    print(proc.stdout)
    
    # Try to extract the ID from the output table
    import re
    ids = re.findall(r'\?\s+(\d+)\s+\?', proc.stdout)
    print(f"   Found IDs in CLI: {ids}")
    
    if ids:
        test_id = ids[-1]
        print(f"\n3. Testing CLI pause on ID {test_id}...")
        proc_pause = subprocess.run([cli_path, "download", "pause", test_id], capture_output=True, text=True)
        print(f"   CLI pause exit code: {proc_pause.returncode}")
        
        print(f"\n4. Testing CLI remove on ID {test_id}...")
        proc_rm = subprocess.run([cli_path, "download", "remove", test_id], capture_output=True, text=True)
        print(f"   CLI remove exit code: {proc_rm.returncode}")
    else:
        print("   No ID found to pause/remove")

if __name__ == "__main__":
    asyncio.run(test_rest_and_cli())
