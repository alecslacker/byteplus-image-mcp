#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP Server: byteplus_image_mcp
Generate image via BytePlus ModelArk (Dola-Seedream 5.0) untuk kebutuhan
logo, mockup UI/UX, dan ilustrasi dokumen/proposal.

Mendukung dua mode:
- Text-to-image       : cukup prompt.
- Image-to-image      : tambahkan image referensi (path lokal via `image_paths`
                        atau URL via `image_urls`, 1-14 gambar) untuk edit,
                        restyle, atau fusion beberapa gambar.

Model yang didukung (aktif di console BytePlus akun Duta Corpora,
diverifikasi 2026-09-01):
- dola-seedream-5-0-pro-260628  (Dola-Seedream-5.0-pro — kualitas maksimal:
  precise editing, layer control, teks multibahasa termasuk Indonesia.
  Resolusi 1K/1.5K/2K, hanya 1 gambar per request)
- seedream-5-0-260128           (Dola-Seedream-5.0-lite — hemat, resolusi
  2K/3K/4K, batch set gambar hingga 15 per request)

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
# Dola-Seedream-5.0-lite = 50 gambar | Dola-Seedream-5.0-pro = cek konsol

mcp = MCPServer("byteplus_image_mcp", version=__version__)


# ---------------------------------------------------------------------------
# Enum & Model Pydantic
# ---------------------------------------------------------------------------
class ImageModel(str, Enum):
    """Model Dola-Seedream 5.0 yang tersedia di akun BytePlus."""

    DOLA_SEEDREAM_50_PRO = "dola-seedream-5-0-pro-260628"
    DOLA_SEEDREAM_50_LITE = "seedream-5-0-260128"


class ImageSize(str, Enum):
    """Resolusi output gambar (kombinasi Pro + Lite)."""

    SIZE_1K = "1K"
    SIZE_15K = "1.5K"
    SIZE_2K = "2K"
    SIZE_3K = "3K"
    SIZE_4K = "4K"


class Purpose(str, Enum):
    """Tujuan penggunaan — menentukan model otomatis yang paling efisien."""

    LOGO = "logo"
    MOCKUP = "mockup"
    DOCUMENT = "document"


# Sumber kebenaran tunggal kapabilitas tiap model (dipakai validasi + list_models)
MODEL_INFO: Dict[ImageModel, Dict[str, Any]] = {
    ImageModel.DOLA_SEEDREAM_50_PRO: {
        "nama": "Dola-Seedream-5.0-pro",
        "sizes": ["1K", "1.5K", "2K"],
        "max_count": 1,
        "max_ref_images": 14,
        "max_total_in_out": None,  # output selalu 1, tidak ada aturan gabungan
        "harga_per_gambar_usd": 0.045,
        "kuota_gratis": "cek konsol BytePlus",
        "use_case": (
            "Logo, mockup UI/UX, poster/infografis dengan teks di dalam gambar "
            "(Bahasa Indonesia didukung native), precise editing & layer control"
        ),
    },
    ImageModel.DOLA_SEEDREAM_50_LITE: {
        "nama": "Dola-Seedream-5.0-lite",
        "sizes": ["2K", "3K", "4K"],
        "max_count": 15,
        "max_ref_images": 14,
        "max_total_in_out": 15,  # total gambar referensi + gambar hasil <= 15
        "harga_per_gambar_usd": 0.035,
        "kuota_gratis": "50 gambar (sekali akun)",
        "use_case": (
            "Ilustrasi dokumen/proposal, batch set gambar konsisten (hingga 15), "
            "resolusi hingga 4K, pilihan hemat"
        ),
    },
}

# Batasan input gambar referensi (spesifikasi API BytePlus ModelArk)
MAX_REF_IMAGES = 14
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB per gambar
MIME_BY_EXT: Dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".gif": "image/gif",
}


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
            "Deskripsi gambar (Bahasa Inggris atau Indonesia — Pro memahami "
            "Bahasa Indonesia native). Gunakan struktur: "
            "[SUBJEK] + [LINGKUNGAN] + [PENCAHAYAAN] + [GAYA] + [DETAIL KUALITAS]. "
            "Contoh: 'minimalist geometric logo, golden letter D monogram, "
            "deep navy background, flat vector style'"
        ),
        min_length=3,
        max_length=2000,
    )
    model: Optional[ImageModel] = Field(
        default=None,
        description=(
            "Model Dola-Seedream 5.0. Jika kosong + purpose diisi, model dipilih otomatis. "
            "Default: dola-seedream-5-0-pro-260628 (kualitas terbaik untuk logo & mockup)."
        ),
    )
    purpose: Optional[Purpose] = Field(
        default=None,
        description=(
            "Tujuan gambar untuk auto-pilih model: "
            "'logo'/'mockup' -> Pro (teks multibahasa, presisi), "
            "'document' -> Lite (hemat, hingga 4K)."
        ),
    )
    size: ImageSize = Field(
        default=ImageSize.SIZE_2K,
        description=(
            "Resolusi output. Pro: 1K/1.5K/2K. Lite: 2K/3K/4K. "
            "Default 2K — satu-satunya resolusi yang didukung keduanya."
        ),
    )
    count: int = Field(
        default=1,
        description=(
            "Jumlah gambar yang di-generate (1-15). count>1 HANYA didukung Lite "
            "(mode set gambar; jumlah aktual bisa <= count karena model menilai "
            "kebutuhan dari prompt). Pro selalu 1 gambar per request."
        ),
        ge=1,
        le=15,
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
        description="Tampilkan watermark di gambar (default false).",
    )
    seed: Optional[int] = Field(
        default=None,
        description="Seed untuk hasil reproducible. Isi angka yang sama = gambar serupa.",
        ge=0,
        le=2147483647,
    )
    image_paths: Optional[List[str]] = Field(
        default=None,
        description=(
            "Path file gambar referensi di komputer (1-14 gambar) untuk mode "
            "image-to-image: edit, restyle, atau fusion. Format didukung: "
            "jpg/png/webp/bmp/tiff/gif, maksimal 10 MB per gambar."
        ),
    )
    image_urls: Optional[List[str]] = Field(
        default=None,
        description=(
            "URL gambar referensi (1-14) — alternatif image_paths, misalnya URL "
            "hasil generate sebelumnya (valid 24 jam)."
        ),
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
        return ImageModel.DOLA_SEEDREAM_50_LITE  # hemat: $0.035/gambar
    return ImageModel.DOLA_SEEDREAM_50_PRO  # default & untuk logo/mockup


def _validate_model_params(
    params: GenerateImageInput, model_id: ImageModel, num_ref_images: int = 0
) -> Optional[str]:
    """Validasi kombinasi size, count, dan jumlah gambar referensi.

    Mengembalikan pesan error solutif (Bahasa Indonesia) jika tidak valid,
    atau None jika lolos.
    """
    info = MODEL_INFO[model_id]

    if params.size.value not in info["sizes"]:
        return (
            f"Error: resolusi '{params.size.value}' tidak didukung {info['nama']}. "
            f"Pilihan yang tersedia: {', '.join(info['sizes'])}. "
            "Tip: gunakan 2K (didukung semua model) atau ganti model."
        )

    if params.count > info["max_count"]:
        return (
            f"Error: {info['nama']} hanya mendukung maksimal {info['max_count']} gambar "
            f"per request (diminta: {params.count}). "
            "Untuk batch banyak gambar, gunakan Dola-Seedream-5.0-lite "
            "(mendukung hingga 15 gambar per request)."
        )

    if num_ref_images > info["max_ref_images"]:
        return (
            f"Error: jumlah gambar referensi ({num_ref_images}) melebihi batas "
            f"{info['max_ref_images']} milik {info['nama']}. "
            "Kurangi gambar referensi atau gabungkan beberapa gambar menjadi satu "
            "referensi terlebih dahulu."
        )

    max_total = info["max_total_in_out"]
    if max_total is not None and num_ref_images + params.count > max_total:
        return (
            f"Error: total gambar referensi ({num_ref_images}) + gambar hasil "
            f"({params.count}) melebihi batas {max_total} milik {info['nama']}. "
            f"Kurangi jumlah gambar referensi atau turunkan count menjadi "
            f"maksimal {max(1, max_total - num_ref_images)}."
        )

    return None


def _encode_image_to_data_uri(path_str: str) -> str:
    """Baca file gambar lokal dan kembalikan sebagai data URI base64.

    Raises:
        ValueError: jika file tidak ada, format tidak didukung, atau > 10 MB.
    """
    p = Path(path_str)
    mime = MIME_BY_EXT.get(p.suffix.lower())
    if mime is None:
        suffix = p.suffix if p.suffix else "(tanpa ekstensi)"
        raise ValueError(
            f"Format gambar '{suffix}' tidak didukung "
            f"({path_str}). Gunakan: jpg, png, webp, bmp, tiff, atau gif."
        )
    if not p.is_file():
        raise ValueError(f"File gambar referensi tidak ditemukan: {path_str}")
    data = p.read_bytes()
    if len(data) > MAX_IMAGE_BYTES:
        size_mb = round(len(data) / (1024 * 1024), 1)
        raise ValueError(
            f"Ukuran gambar referensi {size_mb} MB melebihi batas 10 MB ({path_str}). "
            "Kompres atau perkecil resolusi gambar terlebih dahulu."
        )
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _ext_from_bytes(data: bytes) -> str:
    """Deteksi ekstensi file dari magic bytes (PNG vs JPEG)."""
    return ".png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"


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
                "Buka ModelArk > Model Square > cari Dola-Seedream-5.0 > klik Activate. "
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
            "Generate 4K atau count>1 butuh waktu lebih lama — coba lagi dengan "
            "size lebih kecil atau kurangi jumlah gambar."
        )
    if isinstance(e, httpx.ConnectError):
        return "Error: Tidak bisa terhubung ke ark.ap-southeast.bytepluses.com. Periksa koneksi internet."

    return f"Error: Kesalahan tak terduga ({type(e).__name__}): {e}"


def _sanitize_filename(text: str, max_len: int = 40) -> str:
    """Buat nama file aman dari prompt."""
    slug = re.sub(r"[^a-zA-Z0-9\s-]", "", text)[:max_len].strip()
    slug = re.sub(r"\s+", "-", slug.lower())
    return slug if slug else "image"


async def _download_image(
    client: httpx.AsyncClient, url: str, dest_base: Path
) -> Optional[Path]:
    """Download gambar dari URL TOS; ekstensi file mengikuti content-type."""
    try:
        resp = await client.get(url, timeout=120.0)
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "").lower()
        ext = ".png" if "png" in ctype else ".jpg"
        dest = dest_base.with_suffix(ext)
        dest.write_bytes(resp.content)
        return dest
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
@mcp.tool(
    name="byteplus_generate_image",
    annotations=ToolAnnotations(
        title="Generate Image via Dola-Seedream-5.0",
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=True,
    ),
)
async def byteplus_generate_image(params: GenerateImageInput) -> str:
    """Generate gambar via BytePlus ModelArk (Dola-Seedream 5.0) untuk logo, mockup UI/UX, dan ilustrasi dokumen.

    Tool ini memanggil API BytePlus images/generations dengan keluarga
    Dola-Seedream-5.0. Mendukung text-to-image (cukup prompt) dan
    image-to-image (dengan gambar referensi via image_paths/image_urls
    untuk edit, restyle, atau fusion beberapa gambar).

    Args:
        params (GenerateImageInput): Parameter tervalidasi:
            - prompt (str): Deskripsi gambar / instruksi edit, 3-2000 karakter
            - model (Optional[ImageModel]): Override model secara eksplisit
            - purpose (Optional[Purpose]): 'logo'/'mockup' -> Pro, 'document' -> Lite
            - size (ImageSize): Pro 1K/1.5K/2K, Lite 2K/3K/4K (default 2K)
            - count (int): 1-15; >1 hanya untuk Lite (mode set gambar)
            - image_paths (Optional[List[str]]): Path gambar referensi lokal (1-14)
            - image_urls (Optional[List[str]]): URL gambar referensi (1-14)
            - save_to_disk (bool): Download hasil ke folder output lokal (default true)
            - watermark (bool): Watermark pada gambar (default false)
            - seed (Optional[int]): Untuk hasil reproducible

    Returns:
        str: JSON berisi status, model terpakai, URL gambar (valid 24 jam),
        dan path lokal jika berhasil di-download.

    Contoh sukses:
        {
          "status": "success",
          "model": "dola-seedream-5-0-pro-260628",
          "count": 1,
          "images": [
            {"url": "https://ark-content-generation...", "local_path": "C:/Users/.../logo-duta.png", "size_kb": 335}
          ],
          "generated_images": 1,
          "usage_tokens": 16384
        }

    Kapan dipakai:
        - "Buatkan logo ..." -> purpose='logo' (Pro)
        - "Mockup halaman utama web ..." -> purpose='mockup' (Pro)
        - "Ilustrasi untuk proposal ..." -> purpose='document' (Lite, hemat)
        - "Edit logo yang saya upload: ganti warna jadi emas"
          -> image_paths=[path upload], prompt instruksi edit (Pro)
        - "Gabungkan: model dari gambar 1 pegang produk dari gambar 2"
          -> image_paths=[gambar1, gambar2] (fusion)
    """
    if not API_KEY:
        return (
            "Error: BYTEPLUS_API_KEY belum diset. "
            "Set environment variable sebelum menjalankan MCP server ini."
        )

    model_id = _resolve_model(params)

    # Susun daftar gambar referensi: path lokal (di-encode) + URL (langsung)
    ref_images: List[str] = []
    for path_str in params.image_paths or []:
        try:
            ref_images.append(_encode_image_to_data_uri(path_str))
        except ValueError as e:
            return f"Error: {e}"
    ref_images.extend(params.image_urls or [])

    # Validasi kombinasi size/count/referensi terhadap kapabilitas model final
    err = _validate_model_params(params, model_id, num_ref_images=len(ref_images))
    if err:
        return err

    payload: Dict[str, Any] = {
        "model": model_id.value,
        "prompt": params.prompt,
        "size": params.size.value,
        "response_format": params.sequence_format,
        "watermark": params.watermark,
    }
    # Gambar referensi (image-to-image): string jika 1, array jika lebih
    if len(ref_images) == 1:
        payload["image"] = ref_images[0]
    elif ref_images:
        payload["image"] = ref_images
    # Multi-gambar (hanya Lite): mode set gambar via sequential_image_generation
    if params.count > 1:
        payload["sequential_image_generation"] = "auto"
        payload["sequential_image_generation_options"] = {"max_images": params.count}
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
                        raw = base64.b64decode(b64)
                        fpath = out_dir / f"{ts}-{slug}-{idx}{_ext_from_bytes(raw)}"
                        fpath.write_bytes(raw)
                        entry["local_path"] = str(fpath)
                    entry["encoding"] = "b64_json"

                if url and params.save_to_disk:
                    out_dir.mkdir(parents=True, exist_ok=True)
                    base_path = out_dir / f"{ts}-{slug}-{idx}"
                    fpath = await _download_image(client, url, base_path)
                    if fpath:
                        entry["local_path"] = str(fpath)
                        entry["size_kb"] = round(fpath.stat().st_size / 1024, 1)

                images.append(entry)

            usage = data.get("usage", {})
            result = {
                "status": "success",
                "model": model_id.value,
                "count": len(images),
                "images": images,
                "generated_images": usage.get("generated_images"),
                "usage_tokens": usage.get("total_tokens"),
                "note": "URL gambar valid 24 jam. File lokal tersimpan permanen.",
            }
            return json.dumps(result, indent=2, ensure_ascii=False)

    except Exception as e:  # noqa: BLE001 - handler terpusat
        return _handle_api_error(e)


@mcp.tool(
    name="byteplus_list_models",
    annotations=ToolAnnotations(
        title="List Model Dola-Seedream-5.0 Tersedia",
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
async def byteplus_list_models() -> str:
    """Tampilkan daftar model Dola-Seedream-5.0 beserta panduan pemilihan dan info kuota.

    Returns:
        str: JSON daftar model dengan model_id, use_case, harga per gambar,
        resolusi yang didukung, batas jumlah gambar, dan info kuota gratis.

    Gunakan tool ini sebelum byteplus_generate_image jika ragu memilih model.
    """
    models = []
    for model, info in MODEL_INFO.items():
        models.append(
            {
                "model_id": model.value,
                "nama": info["nama"],
                "use_case": info["use_case"],
                "harga_per_gambar_usd": info["harga_per_gambar_usd"],
                "kuota_gratis": info["kuota_gratis"],
                "resolusi": ", ".join(info["sizes"]),
                "max_gambar_per_request": info["max_count"],
            }
        )
    return json.dumps(
        {
            "status": "success",
            "models": models,
            "tip": (
                "Gunakan purpose='logo'/'mockup' untuk otomatis pakai "
                "Dola-Seedream-5.0-pro, purpose='document' untuk "
                "Dola-Seedream-5.0-lite yang lebih hemat. "
                "Batch >1 gambar hanya bisa via Lite. "
                "Mode image-to-image (edit/fusion gambar referensi) "
                "didukung kedua model via image_paths/image_urls."
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
