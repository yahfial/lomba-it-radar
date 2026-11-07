# 📡 Lomba IT Radar Indonesia (24/7 Real-time Telegram Bot)

Bot otonom pencari informasi **Lomba IT, Hackathon, Capture The Flag (CTF), Data Science/AI, Competitive Programming, dan UI/UX Design** skala nasional Indonesia secara **real-time 24 jam**.

---

## ✨ Fitur Utama

1. **Multi-Source Web & Community Radar:**
   - **Google News Indonesia Real-Time Index (`hl=id&gl=ID`):** Menyadap setiap artikel, pengumuman kampus, dan portal berita yang baru diindeks di internet dengan kueri Boolean khusus lomba IT.
   - **Bing Web News Index (`cc=id`):** Lapisan kedua pencari kata kunci lomba IT nasional.
   - **Dicoding Challenges & Events Scraper:** Memantau langsung halaman tantangan dan event teknologi resmi di Dicoding Indonesia.
   - **Public Telegram Broadcast Scraper (`t.me/s/...`):** Memantau channel publik info lomba (seperti `@kabarlomba`) tanpa memerlukan login akun Telegram pribadi.
2. **Smart NLP Keyword Classifier & Noise Filter:**
   - Otomatis mengelompokkan lomba ke dalam kategori:
     - `Hackathon & Software Dev`
     - `Cyber Security & CTF`
     - `Data Science & AI/ML`
     - `UI/UX & Product Design`
     - `Competitive Programming`
     - `Lomba IT & Inovasi Nasional` (Gemastik, Compfest, Arkavidia, Schematics, Find IT, Hology, dll.)
   - Membuang *false positive* seperti lomba mewarnai, lomba menyanyi, lowongan kerja biasa, dll.
3. **Anti-Duplikat (SQLite WAL + SHA-256 Fingerprinting):**
   - Setiap lomba yang ditemukan di-hash berdasarkan URL kanonis (tanpa parameter `utm_*`) dan *slug* judul sehingga **Anda tidak akan pernah dikirimi notifikasi yang sama dua kali**.
4. **Dual Deployment Mode:**
   - **Mode Lokal (`--once` atau `--daemon`):** Berjalan di laptop/VPS Anda.
   - **Mode Cloud Gratis 24 Jam (GitHub Actions):** Sudah dilengkapi file `.github/workflows/radar_cron.yml` yang berjalan otomatis setiap 30 menit di server GitHub tanpa perlu menyalakan laptop.

---

## 🚀 Cara Penggunaan Cepat (Di Laptop Ini)

### 1. Persiapan Konfigurasi Telegram Bot (Hanya 2 Menit)
1. Buka Telegram, cari **`@BotFather`**, ketik `/newbot`, lalu ikuti instruksi hingga mendapat **Bot Token** (contoh: `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`).
2. Buka bot yang baru Anda buat, lalu klik **Start** (`/start`).
3. Cari **`@userinfobot`** di Telegram, klik Start untuk melihat **Chat ID** angka akun Anda (contoh: `987654321`).
4. Salin file `.env.example` menjadi `.env`:
   ```powershell
   Copy-Item .env.example .env
   ```
5. Isi `TELEGRAM_BOT_TOKEN` dan `TELEGRAM_CHAT_ID` di dalam file `.env`.

### 2. Perintah Menjalankan Bot

```powershell
# Masuk ke direktori proyek
cd D:\alfa\Documents\Antigravity\lomba-it-radar

# 1. Tes koneksi bot ke Telegram Anda
.\.venv\Scripts\python.exe main.py --test-telegram

# 2. Jalankan 1x pemindaian penuh sekarang juga
.\.venv\Scripts\python.exe main.py --once

# 3. Jalankan mode 24/7 nonstop di background (memindai setiap 15 menit)
.\.venv\Scripts\python.exe main.py --daemon

# 4. Lihat daftar lomba IT terbaru yang sudah tersimpan di database lokal
.\.venv\Scripts\python.exe main.py --list-history 20
```

---

## ☁️ Cara Menjalankan 24 Jam Gratis Tanpa Nyalakan Laptop (GitHub Actions)

1. Upload folder `lomba-it-radar` ini ke repositori GitHub Anda (bisa *Public* atau *Private*).
2. Masuk ke repositori GitHub -> **Settings** -> **Secrets and variables** -> **Actions**.
3. Tambahkan 2 *Repository Secrets*:
   - `TELEGRAM_BOT_TOKEN` = Token dari `@BotFather`
   - `TELEGRAM_CHAT_ID` = Chat ID Anda
4. Buka tab **Actions** di GitHub, aktifkan workflow **Lomba IT Indonesia 24/7 Radar**. Bot akan otomatis menyapu internet setiap 30 menit selama 24 jam penuh dan mengirimkan notifikasi langsung ke Telegram Anda!
