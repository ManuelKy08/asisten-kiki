"""Peta perintah -> aksi (Indonesia, longgar)."""
import re
import unicodedata

from . import actions as A
from . import config as C

NUM = {"nol": 0, "kosong": 0, "satu": 1, "dua": 2, "tiga": 3, "empat": 4, "lima": 5, "enam": 6,
       "tujuh": 7, "delapan": 8, "sembilan": 9, "sepuluh": 10, "seperempat": 25, "setengah": 50,
       "seratus": 100, "puluh": 10, "duapuluh": 20, "tigapuluh": 30, "empatpuluh": 40,
       "l-limapuluh": 50, "enampuluh": 60, "tujuhpuluh": 70, "delapanpuluh": 80,
       "sembilanpuluh": 90}

SITES = {}


def norm(t):
    t = unicodedata.normalize("NFKD", str(t)).lower()
    t = re.sub(r"[^a-z0-9\s:/?&=.\-]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def parse_num(s):
    s = norm(s).replace(" ", "")
    if s in NUM:
        return NUM[s]
    m = re.match(r"^(\d+)", s)
    if m:
        return int(m.group(1))
    for k, v in NUM.items():
        if k in s:
            return v
    return None


def duration(text):
    t = norm(text)
    m = re.search(r"(\d+)\s*(detik|second|sec|s)", t)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*(menit|minute|min|m)\b", t)
    if m:
        return int(m.group(1)) * 60
    m = re.search(r"(\d+)\s*(jam|hour|hr|h)\b", t)
    if m:
        return int(m.group(1)) * 3600
    return None


def _drop_wake(t, cfg):
    """Buang kata pemicu di awal kalimat ('kiki buka youtube' -> 'buka youtube')."""
    words = [str(w).strip().lower() for w in
             ((cfg.get("stt") or {}).get("wake_words") or []) if str(w).strip()]
    words += [str((cfg.get("assistant") or {}).get("name", "")).lower()]
    words = sorted(set(words), key=len, reverse=True)
    for _ in range(3):
        for w in words:
            if not w:
                continue
            new = re.sub(rf"^\s*{re.escape(w)}\b[\s,]*", "", t, flags=re.I)
            if new != t:
                t = new
                break
        else:
            break
    return t.strip()


def strip_filler(t):
    t = norm(t)
    for f in ("tolong", "tolong dong", "dong", "dongg", "please", "please dong", "cak",
              "mas", "bro", "bang", "yuk", "ya", "sih", "deh", "kok", "eh"):
        t = re.sub(rf"\b{f}\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def keyword_site(text):
    best, bestlen = None, 0
    for k, url in SITES.items():
        kk = k.strip()
        if not kk:
            continue
        if re.search(rf"\b{re.escape(kk)}\b", text) and len(kk) > bestlen:
            best, bestlen = url, len(kk)
    return best


def handle(text, cfg, ctx=None):
    """Kembalikan (balasan_teks, mood_wajah, intent_name)."""
    raw_t = strip_filler(text)
    t = _drop_wake(raw_t, cfg)
    if not t:
        # hanya kata pemicu -> biarkan brain yang menyapa sesuai waktu
        return None, None, "chat"
    SITES.update({norm(k): v for k, v in (cfg.get("sites") or {}).items()})

    # --- kontrol hidup ---
    if re.search(r"^\s*(dengar|dengerin|dengarin|dengarkan|listening)\b", t) and len(t.split()) <= 2:
        if ctx is not None and getattr(ctx, "stt", None) is not None:
            ctx.stt.force_arm()
        return "Aku dengerin. Bilang saja.", "listening", "listen_now"
    if re.search(r"^\s*(diam|berhenti|stop)\b", t) and len(t.split()) <= 2:
        return "Oke, aku diam dulu. Panggil 'kiki' kalau butuh.", "sleep", "stop_listening"
    if re.search(r"\b(matikan|berhenti|stop|selesai|udah deh|cukup)\b", t) and \
       re.search(r"\b(dengar|dengerin|dengarin|asisten|kiki|suara|listen)\b", t):
        return "Oke, aku diam dulu. Panggil 'kiki' kalau butuh.", "sleep", "stop_listening"
    if re.match(r"^\s*(tidur|istirahat)\s*$", t):
        return "Baik, aku tidur dulu. Bilang 'kiki' kalau butuh.", "sleep", "sleep"
    if re.search(r"^\s*(bangun|bangunkan|mulai lagi|lanjut)\b", t):
        return "Aku aktif lagi!", "happy", "wake"
    if re.search(r"\b(bangun|bangunkan|lanjut dengar)\b", t):
        return "Aku aktif lagi!", "happy", "wake"
    if re.match(r"^\s*(kiki|ki|halo|hai|hei)\b", t) and len(t.split()) <= 2:
        return "Ya, aku di sini. Bilang aja.", "listening", "here"

    # --- buka situs/app ---
    m = re.search(r"\b(?:cari|search|googling|find|coba|dengerin|main|mainkan|putar|play)\b"
                  r"\s*(?:di|dalam|ke)?\s*(?:youtube|yt)\s+(.+)$", t)
    if m:
        q = strip_filler(m.group(1))
        if q:
            return (A.open_url(f"https://www.youtube.com/results?search_query={_q(q)}"),
                    "excited", "yt_search")
    if (re.search(r"\b(?:buka|open|jalan|masuk|alihkan|go to)\b.*\b(youtube|yt)\b", t)
            or re.match(r"^\s*(youtube|yt)\s*$", t)) and \
       not re.search(r"\b(cari|search|googling)\b", t):
        return A.open_url("https://www.youtube.com"), "happy", "youtube"

    m = re.search(r"\b(?:youtube|yt)\s+(?:cari|search|googling|find)\s*(.+)$", t)
    if m:
        q = strip_filler(m.group(1))
        if q:
            return (A.open_url(f"https://www.youtube.com/results?search_query={_q(q)}"),
                    "excited", "yt_search")

    m = re.search(r"\b(?:cari|search|googling|find)\b\s*(?:di|dalam|ke)?\s*"
                  r"(?:google|internet|web|goggles)?\s+(.+)$", t)
    if m:
        q = strip_filler(m.group(1))
        if q and len(q.split()) <= 8:
            return A.open_url(f"https://duckduckgo.com/?q={_q(q)}"), "idle", "search"
    if re.search(r"\b(cari apa|carikan|cari)\b", t) and len(t.split()) <= 3:
        return "Mau cari apa? Sebut kata kuncinya.", "listening", "need_query"

    m = re.search(r"\b(?:buka|open|jalan|masuk|alihkan|go to|to)\b\s+(.+)$", t)
    if m:
        arg = strip_filler(m.group(1))
        arg = re.sub(r"^(aplikasi|app|aplikasinya)\s+", "", arg)
        arg = re.sub(r"\b(di|ke)\b.*$", "", arg) if arg in ("youtube", "yt") else arg
        site = keyword_site(arg) or keyword_site(t)
        if site:
            return A.open_url(site), "happy", "site"
        if re.match(r"^(apa|apakah|which|what)\b", arg) or len(arg) < 2:
            return "Buka apa? Sebut nama aplikasinya.", "listening", "need_app"
        if arg:
            return A.open_app(arg), "happy", "app"
    if re.search(r"\b(buka|open)\b", t):
        return "Buka apa? Sebut nama aplikasinya.", "listening", "need_app"

    # sebut nama langsung tanpa kata "buka": "kiki instagram" -> buka instagram
    m = re.match(r"^\s*(?:buka|open|jalankan)\s+(\w[\w ._-]{0,24})$", t)
    if m:
        arg = strip_filler(m.group(1))
        site = keyword_site(arg)
        if site:
            return A.open_url(site), "happy", "site"
    if keyword_site(t):
        return A.open_url(keyword_site(t)), "happy", "site"

    # --- media & suara ---
    media_word = r"\b(lagu|musik|media|player|video|spotify|youtube)\b"
    if re.search(r"\b(jeda|pause|berhenti main)\b", t) or \
       (re.search(r"\bstop\b", t) and re.search(media_word, t)):
        return A.media("pause"), "idle", "pause"
    if re.search(r"\b(lanjut|play|mainkan|resume)\b", t) or \
       (re.search(r"\b(buka|nyalakan|start)\b", t) and re.search(media_word, t)):
        return A.media("play"), "happy", "play"
    if re.search(r"\b(next|skip|lewati)\b", t) or \
       re.search(media_word + r"\s+(berikutnya|selejutnya)", t) or \
       re.search(r"\b(berikutnya|selejutnya)\s+(lagu|musik|video)\b", t):
        return A.media("next"), "excited", "next"
    if re.search(r"\b(prev|previous|sebelumnya|kembali|kembali ke|mundur|back)\b", t) or \
       re.search(media_word + r"\s+sebelumnya", t) or \
       re.search(r"\bsebelumnya\s+(lagu|musik|video)\b", t):
        return A.media("previous"), "idle", "prev"
    if re.search(r"\bvolume\s*(naik|tinggi|add|tambah|besar|keras|up)\b", t):
        return A.volume(+1), "idle", "vol_up"
    if re.search(r"\bvolume\s*(turun|rendah|kecil|kurang|lembut|soft|down)\b", t):
        return A.volume(-1), "idle", "vol_down"
    if re.search(r"\b(diamkan|senyapkan|mute|bisukan)\b", t):
        return A.volume(mute=True), "idle", "mute"
    if re.search(r"\b(suara|bunyi|audio)\s+(nyala|nORMAL|normal)\b", t) or re.search(r"\bunmute\b", t):
        return A.volume(mute=False), "idle", "unmute"
    m = re.search(r"\bvolume\s+(?:jadi|set|ke|tingkat)?\s*(\d{1,3})\s*(?:%|persen)?\b", t) or \
        re.search(r"^\s*(\d{1,3})\s*(?:%|persen)\s*$", t)
    if m:
        return A.volume(pct=int(m.group(1))), "idle", "vol_set"
    if re.search(r"^volume|^berapa volume|volume berapa", t):
        return A.volume(), "idle", "vol_get"

    # --- layar & jendela ---
    if re.search(r"\b(screenshot|screen shot|tangkapan layar|ss)\b", t):
        return A.screenshot(), "happy", "screenshot"
    if re.search(r"\b(tutup|close)\s+(jendela|window|aplikasi|tab)\b", t):
        return A.window("close"), "idle", "close_win"
    if re.search(r"\b(maksimal|maximize|perbesar)\b", t):
        return A.window("maximize"), "idle", "maximize"
    if re.search(r"\b(minimalkan|minimize|sembunyikan)\b", t):
        return A.window("minimize"), "idle", "minimize"
    if re.search(r"\b(tampilkan\s+desktop|desktop)\b", t):
        return A.openbox("desktop"), "idle", "show_desktop"
    if re.search(r"\b(kunci|lock)\s+(layar|screen|komputer)\b", t):
        return A.openbox("lock"), "idle", "lock"
    if re.search(r"\b(kecerahan|brightness|terang|gelap)\b", t):
        if re.search(r"\b(naik|tinggi|tambah|terang|panas)\b", t):
            return A.brightness(+10), "idle", "br_up"
        if re.search(r"\b(turun|rendah|kecil|gelap|redup)\b", t):
            return A.brightness(-10), "idle", "br_down"
        return A.brightness(), "idle", "br_get"

    # --- konektivitas ---
    if re.search(r"\bwifi\b|\bwlan\b|\bhotspot\b", t):
        if re.search(r"\b(nyalakan|hidup|on|nyala|connect)\b", t):
            return A.wifi(True), "happy", "wifi_on"
        if re.search(r"\b(matikan|mati|off|putus)\b", t):
            return A.wifi(False), "idle", "wifi_off"
        return A.wifi(), "idle", "wifi_get"
    if re.search(r"\bbluetooth\b", t):
        if re.search(r"\b(nyalakan|hidup|nyala|on|connect)\b", t):
            return A.bluetooth(True), "happy", "bt_on"
        if re.search(r"\b(matikan|mati|off|putus)\b", t):
            return A.bluetooth(False), "idle", "bt_off"
        return A.bluetooth(), "idle", "bt_get"

    # --- clipboard ---
    if re.search(r"\b(salin|copy)\b", t):
        q = re.sub(r"^.*?\b(salin|copy)\b", "", t).strip()
        if q:
            return A.copy(q), "happy", "copy"
        return A.copy(A.paste()), "happy", "copy_active"
    if re.search(r"\b(tempel|paste|ketik)\b", t):
        val = A.paste()
        if val:
            C.run_quiet(["xdotool", "type", "--clearmodifiers", "--delay", "20", val])
            return "sudah diketik", "happy", "paste"

    # --- info ---
    if re.search(r"\b(jam berapa|pukul berapa|jamnya berapa|what time)\b", t):
        s, _ = A.time_info()
        return s, "idle", "time"
    if re.search(r"\b(tanggal|hari apa|datang sekarang)\b", t):
        import time as _t
        hari = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"][_t.localtime().tm_wday]
        return f"hari {hari}, {_t.strftime('%d %B %Y')}", "idle", "date"
    if re.search(r"\b(baca|tampilkan|lihat|dengerin) (catatan|note)\b", t) or \
       re.search(r"^catatan$", t):
        return A.notes("read"), "idle", "note_read"
    if re.search(r"\b(catat|note|catatan)\b", t):
        q = re.sub(r"^.*?\b(catat|note)\b", "", t).strip(" .,:-")
        q = re.sub(r"\b(baca|tampilkan|lihat)\b", "", q).strip(" .,:-")
        if q:
            return A.notes("add", q), "happy", "note_add"
        return A.notes("read"), "idle", "note_read"
    if re.search(r"\b(timer|alarm|ingatkan)\b", t):
        d = duration(t)
        if d:
            return A.timer(d), "happy", "timer"
        return "Timer berapa lama? Misalnya: timer 10 menit", "listening", "timer_need"

    # --- CURHAT / AJAK NGOBROL ---
    from . import brain
    mood = brain.detect_mood(t)
    if mood or brain.looks_like_chat(t):
        reply = brain.reply(t, cfg, mood)
        return reply, brain.mood_for(mood, t), "chat"

    # --- bantuan ---
    if re.search(r"\b(bantuan|help|bisa apa|apa saja|perintah|what can)\b", t):
        return _help(), "happy", "help"

    # --- energi (perlu konfirmasi) ---
    if re.search(r"\b(shutdown|matikan komputer|power off)\b", t):
        return ("Yakin mau matikan? Bilang 'ya'.",
                "thinking", "confirm:power_off")
    if re.search(r"\b(reboot|restart)\b", t):
        return ("Yakin mau restart? Bilang 'ya'.", "thinking", "confirm:reboot")
    if re.search(r"\b(suspend|sleep)\b|\btidur\s+(laptop|komputer|pc|mesin)\b", t):
        return ("Yakin mau tidur? Bilang 'ya'.", "thinking", "confirm:suspend")

    return None, None, "unknown"


def _q(s):
    from urllib.parse import quote
    return quote(s)


def _help():
    return ("Bisa: buka YouTube/browser/aplikasi, cari di internet, atur volume, "
            "ganti lagu, wifi, kecerahan, screenshot, timer, catatan, jam. "
            "Kalau mau curhat, tinggal cerita aja.")


POWER_ACTIONS = {
    "power_off": ("shutdown", r"\b(shutdown|matikan|power off)\b"),
    "reboot": ("reboot", r"\b(reboot|restart)\b"),
    "suspend": ("suspend", r"\b(tidur|sleep|suspend)\b"),
}


def confirm(text, cfg, pending=None):
    """Konfirmasi untuk perintah berisiko.

    `pending` adalah nama aksi dari `handle()` (mis. "confirm:reboot").
    Kalau tidak ada, aksi ditebak dari teks jawaban.
    """
    t = norm(text)
    action = None
    if pending:
        action = pending.split(":", 1)[-1].strip()
        if action not in POWER_ACTIONS:
            action = None
    if action is None:
        for name, (_label, pat) in POWER_ACTIONS.items():
            if re.search(pat, t):
                action = name
                break

    if re.search(r"\b(batal|bukan|tidak|no|nope|ganti|cancel)\b", t):
        return "Batal, aman.", "happy", "cancel"
    yes = re.search(r"\b(iya|ya|yes|yep|betul|boleh|lanjut|ok|oke|setuju|confirm)\b", t)
    if not yes:
        if action:
            return ("Yakin? Bilang 'ya' atau 'batal'.", "thinking", "need_yes_no")
        return "Hmm, jawab ya atau batal ya.", "listening", "need_yes_no"

    if action:
        return A.power(action), "idle", action
    return "", "idle", "noop"