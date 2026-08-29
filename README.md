# BytePlus Image MCP

MCP server untuk generate image via **BytePlus ModelArk** (keluarga model **Seedream** dari ByteDance) — dirancang untuk kebutuhan **logo, mockup UI/UX, dan ilustrasi dokumen/proposal**.

## ✨ Fitur

- **Auto-routing model cerdas** — sebut `purpose` saja, model dipilih otomatis:
  - `logo` / `mockup` → Seedream 4.5 (text rendering terbaik, 4K)
  - `document` → Seedream 4.0 (hemat, cukup untuk ilustrasi)
- Multi-gambar per request (1–6), resolusi 1K/2K/4K
- Seed reproducible untuk hasil konsisten
- Auto-download hasil ke folder lokal
- Error handling lengkap dengan solusi konkret (Bahasa Indonesia)

## 📊 Model

| Model | Kegunaan | Harga | Kuota Gratis* |
|---|---|---|---|
| Seedream 4.5 | Logo, mockup, teks di gambar | $0.04/gambar | 200 gambar |
| Seedream 4.0 | Ilustrasi dokumen (hemat) | $0.03/gambar | 200 gambar |

*Kuota gratis akun baru BytePlus. Daftar di [console.byteplus.com](https://console.byteplus.com).

## 🚀 Install

### Prasyarat
1. Akun [BytePlus](https://console.byteplus.com) dengan API key (ModelArk → API keys)
2. Aktifkan model Seedream di ModelArk → Model activation → tab Media
3. Python ≥ 3.10 dan [uv](https://docs.astral.sh/uv/) (opsional tapi disarankan)

### Cara 1: uvx langsung dari GitHub (tanpa install manual)

```json
{
  "mcpServers": {
    "byteplus-image": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/alecslacker/byteplus-image-mcp", "byteplus-image-mcp"],
      "env": {
        "BYTEPLUS_API_KEY": "isi-api-key-anda"
      }
    }
  }
}
```

### Cara 2: pip install dari GitHub

```bash
pip install git+https://github.com/alecslacker/byteplus-image-mcp
```

Lalu di config MCP client:
```json
{
  "mcpServers": {
    "byteplus-image": {
      "command": "byteplus-image-mcp",
      "env": { "BYTEPLUS_API_KEY": "isi-api-key-anda" }
    }
  }
}
```

### Cara 3: jalankan file langsung (lokal)

```bash
git clone https://github.com/alecslacker/byteplus-image-mcp
cd byteplus-image-mcp
pip install mcp httpx pydantic
BYTEPLUS_API_KEY=isi-api-key-anda python src/byteplus_image_mcp/server.py
```

## ⚙️ Environment Variables

| Variable | Wajib | Default | Keterangan |
|---|---|---|---|
| `BYTEPLUS_API_KEY` | ✅ | — | API key dari console BytePlus |
| `BYTEPLUS_IMAGE_OUTPUT_DIR` | ❌ | `~/Pictures/byteplus-mcp` | Folder simpan gambar |

## 🛠️ Tools

### `byteplus_generate_image`

| Parameter | Tipe | Default | Keterangan |
|---|---|---|---|
| `prompt` | string | — | Deskripsi gambar (English disarankan) |
| `purpose` | `logo`\|`mockup`\|`document` | — | Auto-pilih model |
| `model` | string | — | Override manual model ID |
| `size` | `1K`\|`2K`\|`4K` | `2K` | Resolusi |
| `count` | 1–6 | `1` | Jumlah gambar |
| `seed` | int | — | Reproducible |
| `save_to_disk` | bool | `true` | Download otomatis |

**Contoh pemakaian:**

```
"Buatkan logo Duta Corpora"
→ byteplus_generate_image({
     prompt: "minimalist geometric logo, letter D monogram, gold on navy, flat vector",
     purpose: "logo"
   })

"Ilustrasi cover proposal"
→ byteplus_generate_image({
     prompt: "abstract tech illustration, flowing data lines, blue gradient",
     purpose: "document"
   })
```

### `byteplus_list_models`
Lihat daftar model + harga + panduan pemilihan.

## 📁 Output

Gambar tersimpan di `BYTEPLUS_IMAGE_OUTPUT_DIR` dengan nama `{timestamp}-{slug-prompt}-{index}.jpg`. URL dari API valid 24 jam; file lokal permanen.

## 🔒 Keamanan

- API key **hanya** via environment variable — tidak pernah di-hardcode
- Jangan commit `.env` atau key ke repository
- Monitor pemakaian: console.byteplus.com → ModelArk → Usage

## 📄 Lisensi

MIT — lihat [LICENSE](LICENSE).
