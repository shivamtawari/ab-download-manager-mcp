import zipfile
import re
import glob
import os
import httpx
import asyncio

def inspect_jar():
    app_dir = os.path.expandvars(r"%LOCALAPPDATA%\ABDownloadManager\app")
    jar_files = glob.glob(os.path.join(app_dir, "server-*.jar"))
    if not jar_files:
        print("No server JAR found")
        return
    
    jar_path = jar_files[0]
    print(f"Inspecting JAR: {jar_path}")
    
    with zipfile.ZipFile(jar_path) as z:
        for name in z.namelist():
            if name.endswith(".class") and "setupRouting" in name:
                data = z.read(name)
                strings = re.findall(rb'[\x20-\x7E]{2,}', data)
                str_list = [s.decode('latin1') for s in strings]
                print(f"\nClass: {name}")
                print("  Strings:", [s for s in str_list if not s.startswith('Lcom') and not s.startswith('Lio')][:25])

async def test_ports():
    ports = [15151, 9554]
    endpoints = ["/queues", "/add", "/start-headless-download", "/ping"]
    
    print("\n=== Probing Ports and Endpoints ===")
    async with httpx.AsyncClient(timeout=2.0) as client:
        for port in ports:
            for ep in endpoints:
                for h in [{}, {"X-API-Key": "test"}, {"apiKey": "test"}]:
                    url = f"http://127.0.0.1:{port}{ep}"
                    try:
                        resp = await client.get(url, headers=h)
                        if resp.status_code != 404:
                            print(f"[{port}] GET {ep} {h} -> Status {resp.status_code}: {resp.text[:100]}")
                    except Exception:
                        pass

if __name__ == "__main__":
    inspect_jar()
    asyncio.run(test_ports())
