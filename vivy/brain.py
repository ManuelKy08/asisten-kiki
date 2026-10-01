"""Otak percakapan Kiki: deteksi mood + balas curhat.

Dua mode:
1) Curhat lokal (default, tanpa internet) - empatik, singkat, hangat.
2) AI (Ollama / OpenAI-compatible) untuk tanya-jawab bebas.
"""
import json
import random
import re
import threading
import time
import urllib.request

from .intents import norm, strip_filler

MOOD_RULES = {
    "tired": r"\b(lelah|kelelahan|capek|ngantuk|mata berat|kurang tidur|mau tidur|"
             r"tidur dulu|burnout|habis tenaga|kurang tenaga|capek-capek)\b",
    "scared": r"\b(takut|cemas|khawatir|gelisah|deg-degan|degdeg|panik|gugup)\b",
    "love": r"\b(cinta|sayang|kangen|miss|rindu|manis|cantik|ganteng|cute|imut|love|"
            r"sayang banget|terharu|haru)\b",
    "happy": r"\b(senang|senang banget|happy|gembira|lega|syukur|alhamdulillah|"
             r"lulus|kerjaan berhasil|berhasil|menang|juara|bangga|proud|puas)\b",
    "excited": r"\b(wow|keren|bagus|asyik|seru|hype|akhirnya|gila|amazing|mantap|"
               r"seru banget|kaget|terkejut|syukurlah|alhamdulillah)\b",
    "confused": r"\b(bingung|gak paham|nggak paham|nggak tau|gatau|kebingungan|pusing)\b",
    "sad": r"\b(sedih|galau|kecewa|nangis|menangis|hancur|hopeless|"
           r"(nggak|ga|gak|ngga) ada (gunanya|artinya|makna)|tak ada artinya|"
           r"depresi|kesepian|ditinggalkan|sendiri|stres|stress|kesal|hapus muka)\b",
    "angry": r"\b(marah|sebal|jengkel|sehek|omong kosong|goblok|nolok|geram)\b",
}

MOOD_ACK = {
    "sad": [
        "Wah, kayaknya kamu lagi berat ya. Cerita aja, Kiki dengerin.",
        "Kiki ngerti kok. Nggak apa-apa ngeluarin itu.",
        "Hmm, kedengarannya capek banget. Mau ceritain bagian yang paling berat?",
        "Oke, Kiki di sini. Nggak buru-buru, cerita pelan-pelan aja.",
    ],
    "love": [
        "Aww, manis banget nih.",
        "Wah seneng ya. Kiki ikut senang!",
        "Gueeee, lanjut ceritain.",
    ],
    "happy": [
        "Seneng dengarnya!",
        "Mantap! Semoga terus ya.",
        "Wah, hari bagus juga ya! Ada lagi?",
    ],
    "excited": [
        "Yeay! Cikita!",
        "Gas terus! Kiki ikut senang juga.",
    ],
    "scared": [
        "Wajar sih kalau takut. Kiki di sini, nggak sendirian.",
        "Rasa takut itu manusiawi. Apa yang paling bikin khawatir?",
        "Tarik napas pelan-pelan ya. Ceritain bagian yang paling bikin takut.",
    ],
"tired": [
 "Capek juga ya. Istirahat dulu, nggak apa-apa.",
 "Kalau capek, turun santai. Besok masih fresh lagi kok.",
],
    "confused": [
 "Hmm, ini yang bikin bingung? Ceritain dikit dong.",
 "Kiki juga sering bingung, lho. Bagian mana yang nggak jelas?",
],
    "angry": [
 "Wajar sih kalau kesal. Tarik napas dulu ya.",
 "Kiki dengerin. Mau ceritain apa yang bikin frustrasi?",
],
}


def detect_mood(text):
    t = norm(text)
    for mood, pat in MOOD_RULES.items():
        if re.search(pat, t):
            return mood
    return None


CHAT_HINTS = (r"\b(aku|gua|gue|saya|perasaanku|pikiranku|ceritain|cerita|dongeng|"
              r"bantuin aku|bikin aku|nggak tau|gatau|kepikiran|aku rasa|aku takut|"
              r"bahasain|gamblang)\b")


def looks_like_chat(text):
    t = norm(text)
    if len(t.split()) < 2:
        return False
    return bool(re.search(CHAT_HINTS, t))


MOOD_FACE = {
 "sad": "sad", "love": "love", "happy": "happy",
 "excited": "excited", "tired": "sleep", "scared": "thinking",
 "confused": "thinking", "angry": "error",
}


def mood_for(mood, text=None):
    return MOOD_FACE.get(mood, "listening")


# ---------- AI opsional ----------
_ai_state = {"history": [], "lock": threading.Lock()}


def ai_available(cfg):
    return bool((cfg.get("brain") or {}).get("ai_enabled"))


def _ask_ai(text, cfg):
    b = cfg["brain"]
    endpoint = (b.get("ai_endpoint") or "").rstrip("/")
    key = b.get("ai_api_key") or ""
    with _ai_state["lock"]:
        msgs = [{"role": "system", "content": b.get("system", "Kamu Kiki.")}]
        msgs += _ai_state["history"][-(int(b.get("history", 8)) * 2):]
        msgs.append({"role": "user", "content": text})
    try:
        if "11434" in endpoint:  # Ollama
            data = json.dumps({
                "model": b.get("ai_model", "llama3.1:8b"),
                "messages": msgs, "stream": False,
                "options": {"temperature": 0.8, "num_predict": 120},
            }).encode()
            req = urllib.request.Request(f"{endpoint}/api/chat", data=data,
                                         headers={"Content-Type": "application/json"})
        else:  # OpenAI-compatible
            data = json.dumps({
                "model": b.get("ai_model", "gpt-4o-mini"),
                "messages": msgs, "max_tokens": 150, "temperature": 0.8,
            }).encode()
            headers = {"Content-Type": "application/json"}
            if key:
                headers["Authorization"] = f"Bearer {key}"
            req = urllib.request.Request(f"{endpoint}/chat/completions", data=data,
                                         headers=headers)
        with urllib.request.urlopen(req, timeout=45) as r:
            out = json.loads(r.read().decode())
        reply = (out.get("message", {}).get("content") if "message" in out
                 else out["choices"][0]["message"]["content"]) or ""
        with _ai_state["lock"]:
            _ai_state["history"] += [{"role": "user", "content": text},
                                     {"role": "assistant", "content": reply.strip()}]
            _ai_state["history"] = _ai_state["history"][-40:]
        return reply.strip()
    except Exception:
        return None


# ---------- reply utama ----------
def reply(text, cfg, mood=None):
    mood = mood or detect_mood(text)
    if ai_available(cfg):
        ai = _ask_ai(text, cfg)
        if ai:
            return ai
    return _local_reply(text, cfg, mood)


def _local_reply(text, cfg, mood):
    t = strip_filler(text)
    name = cfg["assistant"]["name"]
    ask = re.search(r"\b(apa|kenapa|mengapa|siapa|kapan|dimana|di mana|gimana|bagai mana|"
                    r"bagaimana|boleh ga|bisa ga|padahal)\b", t)

    if mood == "sad":
        return f"{_pick(MOOD_ACK['sad'])} {_sad_follow(t)}"
    if mood == "love":
        return f"{_pick(MOOD_ACK['love'])} {name} juga suka lho."
    if mood == "happy":
        return f"{_pick(MOOD_ACK['happy'])} {_happy_follow(t)}"
    if mood == "excited":
        return f"{_pick(MOOD_ACK['excited'])} Ceritakan detailnya dong!"
    if mood == "tired":
        return _pick(MOOD_ACK["tired"])
    if mood == "scared":
        return f"{_pick(MOOD_ACK['scared'])} {_scared_follow(t)}"
    if mood == "confused":
        return f"{_pick(MOOD_ACK['confused'])} {_confused_follow(t)}"
    if mood == "angry":
        return f"{_pick(MOOD_ACK['angry'])} {_angry_follow(t)}"

    if t.strip() in (name.lower(), "ki", "kiki"):
        return "Ya, aku di sini. Bilang aja."
    if re.search(r"\b(nama kamu|nama mu|siapa kamu|kamu siapa)\b", t):
        return f"Aku {name}, asisten suaramu. Senang kenal kamu!"
    if re.search(r"\b(terima kasih|makasih|thanks|thank you)\b", t):
        return "Sama-sama! Senang bisa bantu"
    if re.search(r"\b(permisi|maaf|mohon maaf|sorry)\b", t) and not ask:
        return "Nggak apa-apa, santai saja :)"
    if re.search(r"\b(lompat|hello|hi|hai|halo|hei|assalamualaikum|pagi|siang|sore|malam)\b", t) \
            and len(t.split()) <= 3:
        return _greet()

    if ask:
        return _answer_stub(t, cfg)
    if re.search(r"\b(nggak ada gunanya|nggak ada artinya|tak ada artinya|ga ada artinya)\b", t):
        return ("Aku dengerin. Rasanya berat ya. Tapi Kiki masih di sini, dan kamu "
                "bukan sendirian. Ceritain pelan-pelan, nggak usah buru-buru.")
    if looks_like_chat(t):
        return "Aku dengerin. Lanjutin dong, ceritain detailnya - Kiki nggak buru-buru. " \
               + _echo_hint(t)
    return "Hmm, aku belum sepenuhnya paham. Maksudnya gitu? Coba lagi ya :)"


def _greet():
    h = time.localtime().tm_hour
    if h < 11:
        return "Selamat pagi! Ada yang bisa kubantu?"
    if h < 15:
        return "Selamat siang! Gimana harimu?"
    if h < 18:
        return "Selamat sore! Sempat ngerjain yang belum selesai?"
    return "Selamat malam! Mau curhat atau mau kubantu sesuatu?"


def _pick(arr):
    return random.choice(arr)


def _sad_follow(t):
    if re.search(r"\b(kerjaan|kerja|kantor|bos|proyek|tugas)\b", t):
        return ("Kerjaan memang berat kalau dibebani bareng. Kalau perlu, pecah jadi langkah kecil ya."
                if len(t.split()) < 8 else "Pokoknya kamu udah kerja keras banget. Istirahat gapapa.")
    if re.search(r"\b(uts|uas|ujian|nilai|sekolah|kampus|skripsi|tugas)\b", t):
        return "Nilai itu cuma salah satu bagian. Kamu lebih dari itu."
    if re.search(r"\b(pacar|pasangan|gebetan|cinta)\b", t):
        return "Perasaan itu nggak salah. Ceritain aja ke Kiki."
    if re.search(r"\b(orang|teman|keluarga|bapak|ibu|adik|kakak|orang tua)\b", t):
        return "Kadang orang terdekat justru yang paling bikin berat. Kiki di sini buat dengerin."
    return "Kalau mau cerita lebih lanjut, Kiki dengerin sampai habis. Jangan dipendek sendiri ya."


def _scared_follow(t):
    if re.search(r"\b(ujian|uts|uas|nilai|skripsi|presentasi|wawancara)\b", t):
        return "Kalau tes atau Presentasi, siapkan poin-poin kecil dulu biar lebih tenang."
    if re.search(r"\b(orang|boss|bos|ketua|pacar|pasangan|keluarga)\b", t):
        return "Kamu nggak sendirian. Aku dengerin, kok."
    return "Nggak apa-apa kalau belum siap. Pelan-pelan aja."


def _happy_follow(t):
    if re.search(r"\b(kerja|lulus|ujian|nilai|skripsi)\b", t):
        return "Kamu kelamaan kerja kerasmu."
    if re.search(r"\b(rencana|niat|mau)\b", t):
        return " Semoga rantainya lancar ya. Semangat!"
    return "Semoga hari ini penuh hal baik."


def _confused_follow(t):
    if re.search(r"\b(skripsi|tugas|kuliah|kampus|sekolah|uts|uas)\b", t):
        return "Coba pecah masalahnya jadi langkah kecil, satu per satu."
    if re.search(r"\b(keputusan|pilih|pilihan)\b", t):
        return "Kalau bingung antara dua pilihan, sebutkan kelebihan dan kekurangannya biar kelihatan jelas."
    return "Kiki bantu pecah pelan-pelan kalau mau."


def _angry_follow(t):
    if re.search(r"\b(kerja|bos|kantor|sekolah|kampus|banyak)\b", t):
        return "Kalau lagi banyak, dibalas terlambat biasanya bukan berarti nggak peduli."
    if re.search(r"\b(pacar|pasangan|orang|keluarga|teman)\b", t):
        return "Bicara baik-baik dulu kalau sudah tenang, ya."
    return "Tarik napas dulu. Kalau mau, ceritain ke Kiki apa yang bikin kesal."


def _echo_hint(t):
    if re.search(r"\b(tidak tau|nggak tau|gatau|bingung)\b", t):
        return "Kalau belum yakin, nggak apa-apa. Ceritain bagian mana yang bingung."
    if re.search(r"\b(takut|cemas|khawatir|gelisah|deg degalan|anxiety)\b", t):
        return "Rasa takut itu wajar. Apa yang paling kamu khawatirkan?"
    if re.search(r"\b(banyak|berat|berantakan|stress)\b", t):
        return "Kalau berat, pecah jadi satu langkah kecil dulu ya."
    return ""


def _answer_stub(t, cfg):
    if re.search(r"\bjam berapa|pukul berapa\b", t):
        return "Sekarang " + time.strftime("%H.%M") + "."
    if re.search(r"\bcuaca|weather|hujan|panas|dingin\b", t):
        return "Aku belum punya data cuaca. Nyalakan `brain.ai_enabled` plus Ollama biar aku bisa jawab itu."
    if re.search(r"\bsiapa (president|ketua|direktur|ceo)\b", t):
        return "Itu perlu data internet. Aku belum terhubung ke sumber live."
    return ("Itu pertanyaan di luar jangkauan Kiki. Kalau mau aku jawab cerdas, "
            "pasang Ollama lalu set `brain.ai_enabled: true` di config.yaml.")