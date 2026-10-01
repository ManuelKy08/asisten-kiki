#!/usr/bin/env bash
# Kiki - pemasang untuk Arch Linux + Openbox
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
say()  { printf '\033[1;36m[Kiki]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[Kiki]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[Kiki]\033[0m %s\n' "$*" >&2; exit 1; }

PKGS=(python python-pip alsa-utils pulseaudio-utils playerctl wmctrl xdotool xclip xorg-x11-utils)
OPTIONAL=(brightnessctl scrot thunar alacritty)

say "Memasang paket sistem..."
sudo pacman -S --needed --noconfirm "${PKGS[@]}" || die "gagal memasang paket sistem"
sudo pacman -S --needed --noconfirm "${OPTIONAL[@]}" || warn "paket opsional ada yang gagal (lompat)"

say "Memasang dependensi Python ke venv..."
VENV="$HOME/.local/share/kiki/venv"
mkdir -p "$HOME/.local/share/kiki"
[ -d "$VENV" ] || python -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip wheel
"$VENV/bin/pip" install -r "$DIR/requirements.txt"

say "Mencari mesin TTS..."
if ! command -v piper >/dev/null && ! command -v espeak-ng >/dev/null; then
  if command -v paru >/dev/null; then
    paru -S --noconfirm piper-tts || warn "paru gagal"
  elif command -v yay >/dev/null; then
    yay -S --noconfirm piper-tts || warn "yay gagal"
  else
    warn "tidak ada piper maupun espeak-ng -> TTS nonaktif (install manual: yay -S piper-tts)"
  fi
fi

PIPER_MODEL=""
if command -v piper >/dev/null; then
  say "Mengunduh suara Indonesia Piper id_ID-medium (~60MB)..."
  VDIR="$HOME/.local/share/kiki/voices"
  mkdir -p "$VDIR"
  BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/id/id_ID"
  for F in id_ID-medium.onnx id_ID-medium.onnx.json; do
    [ -s "$VDIR/$F" ] || curl -fL --progress-bar "$BASE/$F" -o "$VDIR/$F" || true
  done
  if [ -s "$VDIR/id_ID-medium.onnx" ]; then
    PIPER_MODEL="$VDIR/id_ID-medium.onnx"
    say "Suara Piper siap."
  else
    warn "Model Piper gagal diunduh -> TTS pakai espeak-ng"
  fi
else
  warn "Piper tidak ada -> TTS pakai espeak-ng (lebih robot)"
fi

CFG="$DIR/config.yaml"
if [ -n "$PIPER_MODEL" ]; then
  KIKI_CFG="$CFG" KIKI_PIPER="$(command -v piper)" KIKI_MODEL="$PIPER_MODEL" python3 - <<'PY'
import os, re
cfg = os.environ["KIKI_CFG"]
s = open(cfg, encoding="utf-8").read()
s = re.sub(r"^  piper_bin: .*$", "  piper_bin: " + os.environ["KIKI_PIPER"], s, flags=re.M)
s = re.sub(r"^  piper_model: .*$", "  piper_model: " + os.environ["KIKI_MODEL"], s, flags=re.M)
open(cfg, "w", encoding="utf-8").write(s)
print("config Piper diperbarui")
PY
fi

say "Membuat CLI '$HOME/.local/bin/vivy'..."
mkdir -p "$HOME/.local/bin"
BIN="$HOME/.local/bin/vivy"
cat > "$BIN" <<EOF
#!/usr/bin/env bash
export VIVY_CONFIG="$CFG"
export VIVY_RUNTIME="\$HOME/.local/share/kiki"
export PYTHONPATH="$DIR\${PYTHONPATH:+:\$PYTHONPATH}"
exec "$VENV/bin/python" -m vivy "\$@"
EOF
chmod +x "$BIN"

say "Membuat autostart XDG..."
AUTOSTART="$HOME/.config/autostart/kiki.desktop"
mkdir -p "$HOME/.config/autostart"
cat > "$AUTOSTART" <<EOF
[Desktop Entry]
Type=Application
Name=Kiki
Comment=Asisten suara dengan wajah animasi
Exec=$BIN start
Terminal=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
EOF
warn "Openbox tidak selalu membaca autostart .desktop. Lihat catatan di bawah."

say "Menambahkan keybind Openbox..."
RC="$HOME/.config/openbox/rc.xml"
if [ -f "$RC" ] && ! grep -q 'vivy wake' "$RC"; then
  cp "$RC" "$RC.kiki.bak"
  KIKI_RC="$RC" KIKI_BIN="$BIN" python3 - <<'PY'
import os
rc, binp = os.environ["KIKI_RC"], os.environ["KIKI_BIN"]
s = open(rc, encoding="utf-8").read()
keys = f"""  <!-- Kiki voice assistant -->
  <keybind key="A-k">
    <action name="Execute"><command>{binp} wake</command></action>
  </keybind>
  <keybind key="A-C-k">
    <action name="Execute"><command>{binp} mute</command></action>
  </keybind>
  <keybind key="A-S-k">
    <action name="Execute"><command>{binp} say Hai, aku di sini</command></action>
  </keybind>
</keybind>"""
if "</keybind>" in s:
    s = s.replace("</keybind>", keys, 1)
else:
    s = s.replace("<keyboard>", "<keyboard>\n" + keys, 1)
open(rc, "w", encoding="utf-8").write(s)
print("keybind ditambahkan:", rc)
PY
  say "Super+K panggil, Super+Shift+K bisukan, Super+Alt+K sapa."
else
  warn "rc.xml tidak ada atau sudah punya keybind Kiki (lompat)"
fi

UNIT="$HOME/.config/systemd/user/kiki.service"
mkdir -p "$HOME/.config/systemd/user"
cat > "$UNIT" <<EOF
[Unit]
Description=Kiki voice assistant
After=graphical-session.target

[Service]
Type=simple
ExecStart=$BIN start
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF
warn "Alternatif autostart: systemctl --user enable --now kiki.service"

say "Memeriksa konfigurasi..."
"$VENV/bin/python" -c "import yaml; yaml.safe_load(open('$CFG')); print('config.yaml ok')"

cat <<EOF

====================================================
 Kiki siap dipasang.
====================================================
 1. source ~/.bashrc            # agar vivy ada di PATH
 2. vivy start                  # jalanankan sekarang
 3. vivy test                   # uji perintah tanpa mikrofon
 4. openbox --reconfigure       # muat ulang keybind

 Kalau Openbox tidak menjalankan autostart .desktop,
 tambahkan di ~/.config/openbox/rc.xml sebelum </openbox>:
     <program>
       <command>{BIN} start</command>
     </program>

 Ingin wajah kecil saja (dengan AI pintar)?  pasang Ollama:
     ollama pull llama3.1:8b
 lalu config.yaml -> brain.ai_enabled: true

 Berkas:
   config   : $CFG
   log      : ~/.local/share/kiki/kiki.log
   perintah : vivy start|stop|status|say "..."|wake|mute|hide|show|quit|test
====================================================
EOF