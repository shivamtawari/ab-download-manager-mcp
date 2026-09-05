"""
Head-to-head benchmark comparing standard single-threaded download vs
AB Download Manager multi-threaded segmented download.
"""

import argparse
import asyncio
import subprocess
import time
from pathlib import Path

import httpx

from abdm_mcp.config import load_settings
from abdm_mcp.service import ABDMService

TEST_FILES = {
    "50mb": {
        "url": "https://speed.cloudflare.com/__down?bytes=52428800",
        "bytes": 52428800,
        "name": "benchmark_50mb.bin",
        "desc": "Cloudflare Edge CDN (50 MB)",
    },
    "100mb": {
        "url": "https://speed.cloudflare.com/__down?bytes=104857600",
        "bytes": 104857600,
        "name": "benchmark_100mb.bin",
        "desc": "Cloudflare Edge CDN (100 MB)",
    },
    "135mb": {
        "url": "https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.8.tar.xz",
        "bytes": 142502100,
        "name": "linux-6.8.tar.xz",
        "desc": "Linux Kernel Archive (135.9 MB)",
    },
    "340mb": {
        "url": "https://download.blender.org/release/Blender4.1/blender-4.1.0-windows-x64.msi",
        "bytes": 343068672,
        "name": "blender-4.1.0-windows-x64.msi",
        "desc": "Blender 4.1 Installer (327 MB)",
    },
    "2.6gb": {
        "url": "https://releases.ubuntu.com/24.04.1/ubuntu-24.04.1-live-server-amd64.iso",
        "bytes": 2773874688,
        "name": "ubuntu-24.04.1-live-server-amd64.iso",
        "desc": "Ubuntu 24.04.1 Server ISO (2.58 GB)",
    },
    "10gb": {
        "url": "https://huggingface.co/mistralai/Mistral-7B-v0.1/resolve/main/model-00001-of-00002.safetensors",
        "bytes": 9942981696,
        "name": "model-00001-of-00002.safetensors",
        "desc": "Mistral-7B LLM Weights (9.94 GB)",
    },
}


def benchmark_single_thread(url: str, target_path: Path, expected_bytes: int) -> tuple[float, float, int]:
    """Download file using standard single-threaded streaming HTTP request."""
    print("\n--> [1/2] Starting Single-Thread Download (1 connection)...")
    start = time.perf_counter()
    downloaded = 0
    last_print = start

    with httpx.stream("GET", url, follow_redirects=True, timeout=600.0) as response:
        response.raise_for_status()
        with open(target_path, "wb") as f:
            for chunk in response.iter_bytes(chunk_size=1024 * 512):
                f.write(chunk)
                downloaded += len(chunk)
                now = time.perf_counter()
                if now - last_print >= 1.0:
                    pct = (downloaded / expected_bytes) * 100 if expected_bytes else 0
                    cur_speed = (downloaded / (1024 * 1024)) / (now - start)
                    print(
                        f"\r    [Single-Thread] {downloaded / (1024 * 1024):.1f}/{expected_bytes / (1024 * 1024):.1f} MB ({pct:.1f}%) - Avg: {cur_speed:.2f} MB/s",
                        end="",
                        flush=True,
                    )
                    last_print = now

    elapsed = time.perf_counter() - start
    speed_mb_s = (downloaded / (1024 * 1024)) / elapsed
    print()  # newline
    return elapsed, speed_mb_s, downloaded


async def benchmark_abdm_multithread(url: str, filename: str, expected_bytes: int) -> tuple[float, float, int]:
    """Download file using AB Download Manager multi-threaded segmented acceleration."""
    print("\n--> [2/2] Starting Multi-Threaded Download (AB Download Manager)...")
    settings = load_settings()
    service = ABDMService(settings)
    target_path = settings.allowed_roots[0] / filename

    if target_path.exists():
        target_path.unlink()

    start = time.perf_counter()
    res = await service.download(
        url=url,
        mode="headless",
        filename=filename,
    )
    print(f"    ABDM Task Submitted: ID={res.download_id} via {res.backend}")

    # Poll until file is completely written
    max_wait = 600.0
    poll_interval = 0.5
    waited = 0.0
    last_print = start

    from abdm_mcp.errors import DownloadNotFoundError

    # Wait for task to register in ABDM
    await asyncio.sleep(1.0)

    while waited < max_wait:
        await asyncio.sleep(poll_interval)
        waited += poll_interval

        try:
            items = await service.cli.show_downloads(download_id=res.download_id)
            if items:
                status = items[0].status.strip()
                now = time.perf_counter()
                if now - last_print >= 1.0:
                    print(
                        f"\r    [ABDM Multi-Thread] Task #{res.download_id} Status: {status} ({waited:.1f}s elapsed)...",
                        end="",
                        flush=True,
                    )
                    last_print = now

                if "finish" in status.lower() or "complete" in status.lower():
                    break
                elif "error" in status.lower():
                    raise RuntimeError(f"ABDM download #{res.download_id} failed with status '{status}'.")
            else:
                # Disappeared from active download list = completed
                if target_path.exists():
                    break
        except DownloadNotFoundError:
            # Completed and cleared from active downloads
            if target_path.exists():
                break

    elapsed = time.perf_counter() - start
    print()  # newline
    if not target_path.exists() or target_path.stat().st_size < expected_bytes:
        actual = target_path.stat().st_size if target_path.exists() else 0
        raise RuntimeError(f"ABDM download incomplete ({actual}/{expected_bytes} bytes) after {elapsed:.1f}s.")

    actual_size = target_path.stat().st_size
    speed_mb_s = (actual_size / (1024 * 1024)) / elapsed
    return elapsed, speed_mb_s, actual_size, res.download_id


def main():
    parser = argparse.ArgumentParser(description="Benchmark Single-Thread vs ABDM Multi-Thread download speed.")
    parser.add_argument(
        "--size",
        choices=list(TEST_FILES.keys()),
        default="100mb",
        help="Preset file size to benchmark (default: 100mb). Options: 50mb, 100mb, 135mb, 340mb, 2.6gb, 10gb",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="Custom download URL to benchmark",
    )
    parser.add_argument(
        "--name",
        type=str,
        default="custom_download.bin",
        help="Filename when using a custom URL",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep downloaded files instead of deleting after test",
    )
    args = parser.parse_args()

    if args.url:
        url = args.url
        filename = args.name
        desc = f"Custom URL: {url}"
        # Probe content length
        resp = httpx.head(url, follow_redirects=True, timeout=15.0)
        expected_bytes = int(resp.headers.get("Content-Length", 0))
        if expected_bytes == 0:
            raise ValueError("Could not determine Content-Length from custom URL.")
    else:
        info = TEST_FILES[args.size]
        url = info["url"]
        expected_bytes = info["bytes"]
        filename = info["name"]
        desc = info["desc"]

    size_mb = expected_bytes / (1024 * 1024)

    settings = load_settings()
    single_target = settings.allowed_roots[0] / f"single_{filename}"
    abdm_target = settings.allowed_roots[0] / filename
    download_id = None

    print("=" * 68)
    print("        BENCHMARK: SINGLE-THREAD vs MULTI-THREAD (ABDM)")
    print(f"  Target : {desc}")
    print(f"  Size   : {size_mb:.1f} MB ({expected_bytes:,} bytes)")
    print("=" * 68)

    try:
        # 1. Single Thread
        t1, speed1, bytes1 = benchmark_single_thread(url, single_target, expected_bytes)
        print(f"    Completed in: {t1:.2f} s ({speed1:.2f} MB/s)")

        # Free disk space immediately before starting Phase 2
        if not args.keep and single_target.exists():
            single_target.unlink()
            print("    [Freed single-thread file from disk before Phase 2]")

        # 2. Multi Thread ABDM
        t2, speed2, bytes2, d_id = asyncio.run(benchmark_abdm_multithread(url, filename, expected_bytes))
        download_id = d_id
        print(f"    Completed in: {t2:.2f} s ({speed2:.2f} MB/s)")

        # 3. Comparison
        ratio = speed2 / speed1 if speed1 > 0 else 0
        diff_pct = ((speed2 - speed1) / speed1) * 100 if speed1 > 0 else 0

        print("\n" + "=" * 68)
        print("                         RESULTS SUMMARY")
        print("=" * 68)
        print(f"{'Method':<30} | {'Time (s)':<10} | {'Speed (MB/s)':<14}")
        print("-" * 68)
        print(f"{'1. Single-Thread (HTTP stream)':<30} | {t1:>8.2f} s | {speed1:>10.2f} MB/s")
        print(f"{'2. ABDM Multi-Thread':<30} | {t2:>8.2f} s | {speed2:>10.2f} MB/s")
        print("-" * 68)
        if ratio >= 1.0:
            print(f"-> ABDM was {ratio:.2f}x faster (+{diff_pct:.1f}% throughput acceleration)!")
        else:
            print(f"-> Single-thread was faster for this small payload (ABDM overhead: {t2 - t1:.2f}s).")
        print("=" * 68)

    finally:
        if not args.keep:
            if single_target.exists():
                try:
                    single_target.unlink()
                except Exception:
                    pass

            # Tell ABDM to remove the task and delete its file
            if download_id and settings.cli_path and settings.cli_path.exists():
                subprocess.run(
                    [str(settings.cli_path), "download", "remove", "--remove-file", str(download_id)],
                    capture_output=True,
                )

            if abdm_target.exists():
                for _ in range(5):
                    try:
                        abdm_target.unlink()
                        break
                    except PermissionError:
                        time.sleep(1.0)
                    except Exception:
                        break


if __name__ == "__main__":
    main()
