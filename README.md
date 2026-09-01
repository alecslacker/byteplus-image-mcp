# BytePlus Image MCP

MCP server untuk generate image via **BytePlus ModelArk** (keluarga model **Dola-Seedream 5.0** dari ByteDance) — dirancang untuk kebutuhan **logo, mockup UI/UX, dan ilustrasi dokumen/proposal**. Mendukung **text-to-image** dan **image-to-image** (edit/restyle/fusion dengan gambar referensi).

## ✨ Fitur

- **Auto-routing model cerdas** — sebut `purpose` saja, model dipilih otomatis:
  - `logo` / `mockup` → Dola-Seedream-5.0-pro (teks multibahasa termasuk Bahasa Indonesia, presisi tinggi)
  - `document` → Dola-Seedream-5.0-lite (hemat, resolusi hingga 4K)
- **Image-to-image** — berikan gambar referensi (`image_paths` path lokal / `image_urls`) untuk edit, restyle, atau fusion beberapa gambar (1–14 referensi)
- Multi-gambar per request via Lite (mode set gambar konsisten, 1–15)
- Resolusi per model: Pro 1K/1.5K/2K • Lite 2K/3K/4K — kombinasi tidak valid ditolak dengan pesan solutif
- Seed reproducible untuk hasil konsisten
- Auto-download hasil ke folder lokal (ekstensi png/jpg terdeteksi otomatis)
- Error handling lengkap dengan solusi konkret (Bahasa Indonesia)

## 📊 Model

| Model | Model ID | Kegunaan | Resolusi | Harga | Kuota Gratis* |
|---|---|---|---|---|---|
| Dola-Seedream-5.0-pro | `dola-seedream-5-0-pro-260628` | Logo, mockup, poster/teks di gambar, precise editing & layer control | 1K, 1.5K, 2K | $0.045/gambar | cek konsol |
| Dola-Seedream-5.0-lite | `seedream-5-0-260128` | Ilustrasi dokumen (hemat), batch set gambar konsisten (hingga 15) | 2K, 3K, 4K | $0.035/gambar | 50 gambar |

*Catatan: Pro hanya mendukung 1 gambar per request. Batch multi-gambar hanya via Lite.

Kuota gratis akun baru BytePlus. Daftar di [console.byteplus.com](https://console.byteplus.com). Aktifkan model di ModelArk → Model activation → tab Media.

## 🚀 Install

### Prasyarat
1. Akun [BytePlus](https://console.byteplus.com) dengan API key (ModelArk → API keys)
2. Aktifkan model Dola-Seedream-5.0 di ModelArk → Model activation → tab Media
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
| `prompt` | string | — | Deskripsi gambar (Inggris atau Indonesia — Pro memahami Indonesia native) |
| `purpose` | `logo`\|`mockup`\|`document` | — | Auto-pilih model (logo/mockup→Pro, document→Lite) |
| `model` | string | — | Override manual model ID |
| `size` | `1K`\|`1.5K`\|`2K`\|`3K`\|`4K` | `2K` | Resolusi — Pro: 1K/1.5K/2K, Lite: 2K/3K/4K |
| `count` | 1–15 | `1` | Jumlah gambar; >1 hanya untuk Lite (mode set gambar) |
| `image_paths` | list string | — | Path gambar referensi lokal (1–14): jpg/png/webp/bmp/tiff/gif, maks 10MB |
| `image_urls` | list string | — | URL gambar referensi (1–14), mis. URL hasil generate sebelumnya |
| `seed` | int | — | Reproducible |
| `save_to_disk` | bool | `true` | Download otomatis |
| `watermark` | bool | `false` | Watermark pada gambar |

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

"4 varian ilustrasi konsisten untuk slide deck"
→ byteplus_generate_image({
     prompt: "isometric illustration set of Indonesian village scenes ...",
     model: "seedream-5-0-260128",
     size: "2K",
     count: 4
   })

"Edit logo yang sudah ada: ganti warna jadi emas"
→ byteplus_generate_image({
     prompt: "change the logo color to luxurious gold, keep the shape and layout unchanged",
     image_paths: ["C:/uploads/logo-klien.png"],   // gambar referensi
     purpose: "logo"
   })

"Fusion: model dari gambar 1 memegang produk dari gambar 2"
→ byteplus_generate_image({
     prompt: "the person in image 1 holding the product from image 2, keep background unchanged",
     image_paths: ["C:/uploads/model.jpg", "C:/uploads/produk.jpg"]
   })
```

### 🖼️ Mode Image-to-Image

Berikan gambar referensi, prompt berubah fungsi menjadi **instruksi edit**:

1. Upload gambar ke chat MCP client (mis. TRAE) — agent akan mengambil path file-nya
2. Agent memanggil tool dengan `image_paths` (lokal) atau `image_urls` (URL, mis. hasil generate sebelumnya yang masih valid 24 jam)
3. Aturan: maks **14 gambar referensi** (jpg/png/webp/bmp/tiff/gif, ≤10MB per gambar); Lite: total referensi + hasil ≤ 15; Pro: hasil selalu 1 gambar

Use case: edit logo klien existing, restyle foto produk, mockup dari sketsa, konsistensi karakter antar-aset.

### `byteplus_list_models`
Lihat daftar model + harga + resolusi + panduan pemilihan.

## 📁 Output

Gambar tersimpan di `BYTEPLUS_IMAGE_OUTPUT_DIR` dengan nama `{timestamp}-{slug-prompt}-{index}.png|.jpg` (ekstensi mengikuti format asli dari API). URL dari API valid 24 jam; file lokal permanen.

## 🔒 Keamanan

- API key **hanya** via environment variable — tidak pernah di-hardcode
- Jangan commit `.env` atau key ke repository
- Monitor pemakaian: console.byteplus.com → ModelArk → Usage

## 📄 Lisensi

MIT — lihat [LICENSE](LICENSE).
