# Verifikasi package MCP server: import dari src + panggil tools
# Jalankan dengan: python test_mcp.py
# API key diambil dari environment variable BYTEPLUS_API_KEY (jangan hardcode!)

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from byteplus_image_mcp.server import (  # noqa: E402
    GenerateImageInput,
    Purpose,
    byteplus_generate_image,
    byteplus_list_models,
)


async def main():
    print("=== TEST 1: list models ===")
    result = await byteplus_list_models()
    parsed = json.loads(result)
    print("status:", parsed["status"], "| jumlah model:", len(parsed["models"]))

    if not os.environ.get("BYTEPLUS_API_KEY"):
        print()
        print("BYTEPLUS_API_KEY tidak diset — skip test generate.")
        print("Set dulu:  set BYTEPLUS_API_KEY=ark-xxxx-anda")
        print("=== TEST 1 LULUS (generate diskip) ===")
        return

    print()
    print("=== TEST 2: generate image (purpose=document -> Dola-Seedream-5.0-lite) ===")
    params = GenerateImageInput(
        prompt="clean geometric illustration of connected nodes network, soft blue gradient background, minimalist professional style",
        purpose=Purpose.DOCUMENT,
        size="2K",
    )
    result = await byteplus_generate_image(params)
    parsed = json.loads(result)
    print("status:", parsed.get("status"))
    print("model:", parsed.get("model"))
    for img in parsed.get("images", []):
        print("  local:", img.get("local_path"), "| size_kb:", img.get("size_kb"))

    if parsed.get("status") != "success":
        print("FULL OUTPUT:", result[:500])
        sys.exit(1)

    print()
    print("=== SEMUA TEST LULUS ===")


if __name__ == "__main__":
    asyncio.run(main())
