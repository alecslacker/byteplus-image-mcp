#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP Server: byteplus_image_mcp
Generate image via BytePlus ModelArk (keluarga Seedream) untuk kebutuhan
logo, mockup UI/UX, dan ilustrasi dokumen/proposal.

Model yang didukung (aktifkan dulu di console BytePlus):
- seedream-4-5-251128  (Seedream 4.5 — terbaik untuk logo & mockup, 4K)
- seedream-4-0-250828  (Seedream 4.0 — hemat untuk ilustrasi dokumen)
- doubao-seedream-4-5-251128 (alias resmi Seedream 4.5)

Environment variable yang dibutuhkan:
- BYTEPLUS_API_KEY        : API key dari console BytePlus ModelArk
- BYTEPLUS_IMAGE_OUTPUT_DIR (opsional) : folder simpan gambar
                             default: ~/Pictures/byteplus-mcp
"""

import base64
import json
import os
import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, field_validator

from byteplus_image_mcp import __version__

# ---------------------------------------------------------------------------
# Konstanta
# ---------------------------------------------------------------------------
API_BASE = "https://ark.ap-southeast.bytepluses.com/api/v3"
GENERATE_ENDPOINT = f"{API_BASE}/images/generations"
API_KEY = os.environ.get("BYTEPLUS_API_KEY", "")
DEFAULT_TIMEOUT = 180.0
DEFAULT_OUTPUT_DIR = os.environ.get(
    "BYTEPLUS_IMAGE_OUTPUT_DIR",
    str(Path.home() / "Pictures" / "byteplus-mcp"),
)

# Catatan kuota gratis per model (informasional, dibaca dari console):
# Seedream 4.5 = 200 gambar | Seedream 4.0 = 200 gambar | Dola-Seedream-5.0-lite = 50 gambar

mcp = MCPServer("byteplus_image_mcp", version=__version__)


# ---------------------------------------------------------------------------
# Enum & Model Pydantic
# ---------------------------------------------------------------------------
class ImageModel(str, Enum):
    """Model Seedream yang tersedia di akun BytePlus."""

    SEEDREAM_45 = "seedream-4-5-251128"
    SEEDREAM_40 = "seedream-4-0-250828"
    DOUBAO_SEEDREAM_45 = "doubao-seedream-4-5-251128"


class ImageSize(str, Enum):
    """Resolusi output gambar."""

    SIZE_1K = "1K"
    SIZE_2K = "2K"
    SIZE_4K = "4K"


class Purpose(str, Enum):
    """Tujuan penggunaan — menentukan model otomatis yang paling efisien."""

    LOGO = "logo"
    MOCKUP = "mockup"
    DOCUMENT = "document"


class GenerateImageInput(BaseModel):
    """Input untuk generate image."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    prompt: str = Field(
        ...,
        description=(
            "Deskripsi gambar dalam bahasa Inggris (disarankan). "
            "Gunakan struktur: [SUJEK] + [LINGKUNGAN] + [PENCAHAYAAN] + [GAYA] + [DETAIL KUALITAS]. "
            "Contoh: 'minimalist geometric logo, golden letter D monogram, deep navy background, flat vector style'"
        ),
        min_length=3,
        max_length=2000,
    )
    model: Optional[ImageModel] = Field(
        default=None,
        description=(
            "Model Seedream. Jika kosong + purpose diisi, model dipilih otomatis. "
            "Default: seedream-4-5-251128 (kualitas terbaik untuk logo & mockup)."
        ),
    )
    purpose: Optional[Purpose] = Field(
        default=None,
        description=(
            "Tujuan gambar untuk auto-pilih model: "
            "'logo'/'mockup' -> Seedream 4.5 (text rendering bagus), "
            "'document' -> Seedream 4.0 (hemat, cukup untuk ilustrasi dokumen)."
        ),
    )
    size: ImageSize = Field(
        default=ImageSize.SIZE_2K,
        description="Resolusi output. 2K cukup untuk mayoritas kebutuhan; 4K untuk presentasi/print.",
    )
    count: int = Field(
        default=1,
        description="Jumlah gambar yang di-generate (1-6). Masing-masing dihitung 1 kuota.",
        ge=1,
        le=6,
    )
    sequence_format: str = Field(
        default="url",
        description="Format respon API BytePlus: 'url' (default) atau 'b64_json'.",
        pattern="^(url|b64_json)$",
    )
    save_to_disk: bool = Field(
        default=True,
        description="Jika true, gambar otomatis di-download ke folder output lokal.",
    )
    watermark: bool = Field(
        default=False,
        description="Tampilkan watermark ByteDance di gambar (default false).",
    )
    seed: Optional[int] = Field(
        default=None,
        description="Seed untuk hasil reproducible. Isi angka yang sama = gambar yang sama.",
        ge=0,
        le=2147483647,
    )

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, v: str) -> str:
        """Pastikan prompt tidak kosong setelah strip."""
        if not v.strip():
            raise ValueError("Prompt tidak boleh kosong")
        return v.strip()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def _resolve_model(params: GenerateImageInput) -> ImageModel:
    """Tentukan model final: eksplisit > auto berdasarkan purpose > default."""
    if params.model is not None:
        return params.model
    if params.purpose == Purpose.DOCUMENT:
        return ImageModel.SEEDREAM_40  # hemat: $0.03/gambar
    return ImageModel.SEEDREAM_45  # default & untuk logo/mockup


def _handle_api_error(e: Exception) -> str:
    """Format error API jadi pesan yang actionable dalam Bahasa Indonesia."""
    if isinstance(e, httpx.HTTPStatusError):
        status = e.response.status_code
        try:
            body = e.response.json()
            detail = body.get("error", {}).get("message", "")
        except Exception:
            detail = e.response.text[:200] if e.response.text else ""

        if status == 404 and "ModelNotOpen" in detail:
            return (
                "Error: Model belum diaktifkan di console BytePlus. "
                "Buka ModelArk > Model activation > tab Media > klik Activate pada model yang dimaksud. "
                f"Detail: {detail}"
            )
        if status == 401:
            return (
                "Error: API key tidak valid/kadaluarsa. "
                "Set environment variable BYTEPLUS_API_KEY dengan key dari "
                "console.byteplus.com > ModelArk > API keys."
            )
        if status == 429:
            return (
                "Error: Rate limit tercapai (IPM 500). Tunggu beberapa detik lalu coba lagi."
            )
        if status == 402:
            return (
                "Error: Kuota gratis habis dan saldo tidak cukup. "
                "Top-up di console BytePlus > Billing center > Payment."
            )
        return f"Error: API gagal (HTTP {status}). Detail: {detail}"

    if isinstance(e, httpx.TimeoutException):
        return (
            "Error: Request timeout (batas 180 detik). "
            "Generate 4K atau count>1 butuh waktu lebih lama — coba lagi dengan size lebih kecil."
        )
    if isinstance(e, httpx.ConnectError):
        return "Error: Tidak bisa terhubung ke ark.ap-southeast.bytepluses.com. Periksa koneksi internet."

    return f"Error: Kesalahan tak terduga ({type(e).__name__}): {e}"


def _sanitize_filename(text: str, max_len: int = 40) -> str:
    """Buat nama file aman dari prompt."""
    slug = re.sub(r"[^a-zA-Z0-9\s-]", "", text)[:max_len].strip()
    slug = re.sub(r"\s+", "-", slug.lower())
    return slug if slug else "image"


async def _download_image(client: httpx.AsyncClient, url: str, dest: Path) -> bool:
    """Download gambar dari URL TOS ke file lokal."""
    try:
        resp = await client.get(url, timeout=120.0)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
@mcp.tool(
    name="byteplus_generate_image",
    annotations=ToolAnnotations(
        title="Generate Image via BytePlus Seedream",
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=True,
    ),
)
async def byteplus_generate_image(params: GenerateImageInput) -> str:
    """Generate gambar via BytePlus ModelArk (Seedream) untuk logo, mockup UI/UX, dan ilustrasi dokumen.

    Tool ini memanggil API BytePlus images/generations dengan model keluarga Seedream.
    Pemakaian otomatis mengurangi kuota gratis akun (Seedream 4.5: 200 gambar,
    Seedream 4.0: 200 gambar) sebelum menyentuh saldo berbayar.

    Args:
        params (GenerateImageInput): Parameter tervalidasi:
            - prompt (str): Deskripsi gambar (bahasa Inggris disarankan), 3-2000 karakter
            - model (Optional[ImageModel]): Override model secara eksplisit
            - purpose (Optional[Purpose]): 'logo'|'mockup' -> Seedream 4.5, 'document' -> Seedream 4.0
            - size (ImageSize): '1K'|'2K'|'4K' (default 2K)
            - count (int): 1-6 gambar per request
            - save_to_disk (bool): Download hasil ke folder output lokal (default true)
            - watermark (bool): Watermark ByteDance (default false)
            - seed (Optional[int]): Untuk hasil reproducible

    Returns:
        str: JSON berisi status, model terpakai, URL gambar (valid 24 jam),
        dan path lokal jika berhasil di-download.

    Contoh sukses:
        {
          "status": "success",
          "model": "seedream-4-5-251128",
          "count": 1,
          "images": [
            {"url": "https://ark-content-generation...", "local_path": "C:/Users/.../logo-duta.jpg", "size_kb": 335}
          ],
          "usage_tokens": 16384
        }

    Kapan dipakai:
        - "Buatkan logo ..." -> purpose='logo'
        - "Mockup halaman utama web ..." -> purpose='mockup'
        - "Ilustrasi untuk proposal ..." -> purpose='document'
    """
    if not API_KEY:
        return (
            "Error: BYTEPLUS_API_KEY belum diset. "
            "Set environment variable sebelum menjalankan MCP server ini."
        )

    model_id = _resolve_model(params)

    payload: Dict[str, Any] = {
        "model": model_id.value,
        "prompt": params.prompt,
        "size": params.size.value,
        "response_format": params.sequence_format,
        "watermark": params.watermark,
    }
    if params.count > 1:
        payload["sequence"] = params.count
    if params.seed is not None:
        payload["seed"] = params.seed

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                GENERATE_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=DEFAULT_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            images: List[Dict[str, Any]] = []
            out_dir = Path(DEFAULT_OUTPUT_DIR)
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            slug = _sanitize_filename(params.prompt)

            for idx, item in enumerate(data.get("data", []), start=1):
                entry: Dict[str, Any] = {}
                url = item.get("url")
                b64 = item.get("b64_json")

                if url:
                    entry["url"] = url
                if b64:
                    # Simpan b64 langsung ke file tanpa mengekspos string panjang
                    if params.save_to_disk:
                        out_dir.mkdir(parents=True, exist_ok=True)
                        fpath = out_dir / f"{ts}-{slug}-{idx}.jpg"
                        fpath.write_bytes(base64.b64decode(b64))
                        entry["local_path"] = str(fpath)
                    entry["encoding"] = "b64_json"

                if url and params.save_to_disk:
                    out_dir.mkdir(parents=True, exist_ok=True)
                    fpath = out_dir / f"{ts}-{slug}-{idx}.jpg"
                    ok = await _download_image(client, url, fpath)
                    if ok:
                        entry["local_path"] = str(fpath)
                        entry["size_kb"] = round(fpath.stat().st_size / 1024, 1)

                images.append(entry)

            result = {
                "status": "success",
                "model": model_id.value,
                "count": len(images),
                "images": images,
                "usage_tokens": data.get("usage", {}).get("total_tokens"),
                "note": "URL gambar valid 24 jam. File lokal tersimpan permanen.",
            }
            return json.dumps(result, indent=2, ensure_ascii=False)

    except Exception as e:  # noqa: BLE001 - handler terpusat
        return _handle_api_error(e)


@mcp.tool(
    name="byteplus_list_models",
    annotations=ToolAnnotations(
        title="List Model Seedream Tersedia",
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
async def byteplus_list_models() -> str:
    """Tampilkan daftar model Seedream yang tersedia beserta panduan pemilihan dan info kuota.

    Returns:
        str: JSON daftar model dengan model_id, use_case, harga per gambar,
        dan sisa kuota gratis (informasional).

    Gunakan tool ini sebelum byteplus_generate_image jika ragu memilih model.
    """
    models = [
        {
            "model_id": ImageModel.SEEDREAM_45.value,
            "nama": "Seedream 4.5",
            "use_case": "Logo, mockup UI/UX, teks di dalam gambar (text rendering terbaik keluarga Seedream)",
            "harga_per_gambar_usd": 0.04,
            "kuota_gratis": "200 gambar (sekali akun)",
            "max_resolusi": "4K",
        },
        {
            "model_id": ImageModel.SEEDREAM_40.value,
            "nama": "Seedream 4.0",
            "use_case": "Ilustrasi dokumen/proposal, hero image, kebutuhan hemat",
            "harga_per_gambar_usd": 0.03,
            "kuota_gratis": "200 gambar (sekali akun)",
            "max_resolusi": "4K",
        },
        {
            "model_id": ImageModel.DOUBAO_SEEDREAM_45.value,
            "nama": "Doubao Seedream 4.5 (alias)",
            "use_case": "Alias resmi Seedream 4.5 dengan prefix doubao-",
            "harga_per_gambar_usd": 0.04,
            "kuota_gratis": "berbagi dengan Seedream 4.5",
            "max_resolusi": "4K",
        },
    ]
    return json.dumps(
        {
            "status": "success",
            "models": models,
            "tip": (
                "Gunakan purpose='logo'/'mockup' untuk otomatis pakai Seedream 4.5, "
                "purpose='document' untuk Seedream 4.0 yang lebih hemat."
            ),
        },
        indent=2,
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    """Entry point console script `byteplus-image-mcp` (transport stdio)."""
    mcp.run()


if __name__ == "__main__":
    main()
