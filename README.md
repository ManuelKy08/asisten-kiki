# Kiki

Asisten suara desktop dengan wajah animasi, khusus **Arch Linux + Openbox**.
Dengar perintah suara, buka aplikasi/situs, atur sistem, dan bisa **curhat**.

```
        .-"""-.
       / .===. \        jalan terus, kok
       \/ 6 6 \/ \       dan wajah animasi
       ( \__/  )  \     selalu di layar
```

## Fitur

- **Wajah animasi** (pygame, X11 transparan, selalu di atas, tanpa dekorasi)
  - idle: napas + kedip mata + arah mata bergerak + aura glow
  - **listening**: hijau, avatar bounce, bar mic level realtime
  - **thinking**: ungu, geleng pelan
  - **speaking**: mulut ikut gerak (lip-sync dari amplitudo TTS)
  - **curhat**: `#sad` `#love` `#happy` `#excited` `#tired` -> ekspresi berubah
  - subtitle bubble + partikel kecil saat senang
  - drag pakai klik kiri untuk pindah posisi
- **STT offline** (Vosk, model `id-small`, tanpa internet, tanpa API key)
- **Wake word**: `kiki`, `ki`, `halo`, `hai kiki`, `asisten` (bisa dimatikan: `require_wake: false`)
- **TTS**: Piper (suara natural) → fallback espeak-ng
- **Aksi**: YouTube, browser, aplikasi, Google/ DuckDuckGo, volume, media player,
  wifi, bluetooth, kecerahan, screenshot, clipboard, jendela, timer, catatan, jam/tanggal
- **Curhat**: deteksi mood, balas empatik singkat; bisa di-upgrade ke Ollama (LLM)
- **Konfirmasi** untuk shutdown/reboot/suspend
- CLI remote: `vivy say`, `vivy wake`, `vivy mute`, `vivy hide`, `vivy status`

## Pemasangan (Arch + Openbox)

```bash
git clone <repo> ~/kiki && cd ~/kiki
chmod +x install.sh
./install.sh

source ~/.bashrc
vivy start
```

Test perintah tanpa mikrofon:

```bash
vivy test
vivy test "cari di youtube lagu djakarta"
```

### Autostart

`install.sh` membuat `~/.config/autostart/kiki.desktop`. Openbox sering
mengabaikan autostart `.desktop`, jadi lebih aman taruh di `~/.config/openbox/rc.xml`
sebelum `</openbox>`:

```xml
<program>
  <command>~/.local/bin/vivy start</command>
</program>
```

Alternatif systemd user:

```bash
systemctl --user enable --now kiki.service
```

### Keybind Openbox (ditambahkan otomatis oleh installer)

| Pintasan | Fungsi |
|---|---|
| `Super+K` | panggil Kiki (langsung dengarin tanpa wake word) |
| `Super+Shift+K` | bisukan |
| `Super+Alt+K` | Kiki menyapa |

Reload: `openbox --reconfigure`

## Mood wajah + curhat

Wajah berubah sesuai situasi, dan balasannya empatik (bukan sekadar "ok"):

| Kalau bilang | Mood | Wajah |
|---|---|---|
| "aku sedih banget kerjaan numpuk" | `sad` | biru murung, mata soft, senyum terbalik |
| "aku cinta kamu" | `love` | pink, blush penuh |
| "senang banget finalistku dium" | `happy` | kuning cerah + partikel |
| "takut presentasi besok" | `scared` | ungu alias `thinking` |
| "aku capek banget" | `tired` | biru pucat, mata setengah nutup |
| "aku bingung soal skripsi" | `confused` | ungu alias `thinking` |
| "aku marah banget" | `angry` | merah alias `error` |
| "nggak ada gunanya hidup" | `sad` | empatik, nggak buru-buru ngasih saran |

Aktifkan LLM supaya bisa jawab bebas (bukan cuma perintah tetap):

```bash
ollama pull llama3.1:8b
```

```yaml
brain:
  ai_enabled: true
```

## Contoh perintah

```
kiki buka youtube
kiki youtube                          # buka YouTube
kiki cari di youtube lagu djakarta   # cari di YouTube
kiki play youtube ed sheer           # pemutar + cari = search YouTube
kiki buka browser / firefox / terminal
kiki instagram / gmail / whatsapp    # sebut nama langsung juga bisa
kiki cari wedangereum
kiki volume naik / turun / 40        # naik, turun, atau set absolute
kiki diamkan suara / buka suara
kiki lagu berikutnya / sebelumnya / pause / lanjut
kiki wifi nyala / wifi mati
kiki kecerahan naik
kiki screenshot
kiki tutup jendela
kiki jam berapa / tanggal berapa
kiki timer 10 menit
kiki catat besok beli bensin

kiki aku sedih banget hari ini  # curhat -> muka sedih
kiki aku cinta kamu             # curhat -> muka cinta
kiki aku capek kerjaan banget   # curhat -> muka lelah/sleep
kiki aku bingung soal skripsi   # curhat -> muka bingung
kiki shutdown                   # minta konfirmasi dulu, baru jalan
kiki shutdown / ya / batal      # lanjut atau batalkan
kiki tidur                      # Kiki tidur (bukan suspend)
kiki tidur laptop               # suspend, minta konfirmasi
```

## AI pintar (opsional)

Kalau ingin jawaban bebas (bukan cuma perintah tetap):

```bash
# Ollama
ollama pull llama3.1:8b
```

`config.yaml`:

```yaml
brain:
  ai_enabled: true
  ai_endpoint: http://localhost:11434
  ai_model: llama3.1:8b
```

Atau pakai endpoint OpenAI-compatible (OpenRouter, Groq, llama.cpp server):

```yaml
brain:
  ai_enabled: true
  ai_endpoint: https://openrouter.ai/api/v1
  ai_model: google/gemini-flash
  ai_api_key: "sk-..."
```

## Paket Archcraft/Openbox

Installer sudah pasang yang wajib. Yang sering hilang di Archcraft tapi berguna untuk Kiki:

```bash
sudo pacman -S --needed brightnessctl scrot playerctl wmctrl xdotool xclip
yay -S piper-tts                     # TTS natural (opsional tapi jauh lebih enak)
```

Kalau suaramu dari headset atau webcam terpisah, cek dulu:

```bash
arecord -l            # daftar mikrofon
pactl list short sources
```

Lalu taruh nama device-nya di `config.yaml`:

```yaml
stt:
  device: "USB Audio Device"    # atau pakai angka index
```

## Tuning

| Setting | Arti |
|---|---|
| `face.pos` | `bottom-right`, `bottom-left`, `top-right`, `top-left`, `center`, `custom` |
| `face.width/height` | ukuran jendela wajah |
| `face.subtitle` | tampilkan teks bubble |
| `face.body`, `face.accent` | warna |
| `stt.wake_words` | daftar kata pemicu |
| `stt.require_wake` | `false` = selalu dengarin |
| `stt.silence_ms` | jeda diam sebelum anggap selesai bicara |
| `stt.mic_rms_gate` | abaikan suara terlalu pelan (0.006 default) |
| `tts.rate` | kecepatan bicara (1.0 normal, 1.2 lebih cepat) |
| `security.allow_power` | izinkan perintah shutdown/reboot |

## Troubleshooting

**Tidak mendengar suara**
```bash
vivy status
# cek log
tail -f ~/.local/share/kiki/kiki.log
# uji mic manual
arecord -d 3 -r 16000 -f S16_LE -t wav /tmp/t.wav && ffplay /tmp/t.wav
```

**Wajah masuk taskbar** → `wmctrl tidak ada`; installer sudah pasang `wmctrl`.
Kalau masih, set `face.hide_taskbar: true` (default) dan `face.always_on_top: true`.

**Salah pilih mikrofon** → `stt.device: "USB Audio Device"` (lihat `arecord -l`).

**TTS robotik** → Piper gagal terpasang: `yay -S piper-tts`, lalu jalankan ulang `install.sh`.

**Model STT jelek** → ganti `stt.model` ke model penuh:
https://alphacephei.com/vosk/models (`vosk-model-small-id-0.3` sudah cukup untuk Indon).

**Layar gelap tanpa taskbar** → klik kiri-drag wajah untuk pindah, atau `vivy hide` / `vivy show`.

## Struktur

```
config.yaml          # semua pengaturan
vivy/
  daemon.py          # orkestrasi
  stt.py             # Vosk + wake word + VAD
  tts.py             # Piper/espeak + lip-sync
  face.py            # animasi wajah pygame
  intents.py         # perintah -> aksi
  actions.py         # aksi sistem/X11
  brain.py           # curhat + mood + LLM opsional
  cli.py             # CLI
install.sh           # pemasang Arch
systemd/kiki.service # unit systemd user
```