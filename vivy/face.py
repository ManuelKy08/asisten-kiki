"""UI wajah:窗口 pygame di X11, transparan, selalu di atas, tanpa dekorasi.

State: idle, listening, thinking, speaking, happy, sad, sleep, error
Animasi: kedip mata, napas (idle), bounce ringan, mouth lip-sync dari level TTS,
bubble gelembung untuk subtitle, efekkcute (mata besar, blush, antenna).
"""
import math
import random

import pygame

from . import config as C

MOODS = {
    #            accent   eye_open  mouth_w  bounce tilt
    "idle":      dict(accent="#6ee7ff", eye=1.0, mouth=0.35, bounce=0.0, blush=0.25),
    "listening": dict(accent="#8affc1", eye=1.15, mouth=0.25, bounce=1.0, blush=0.35),
    "thinking":  dict(accent="#c9a7ff", eye=0.75, mouth=0.20, bounce=0.2, blush=0.15),
    "speaking":  dict(accent="#ffd166", eye=1.0, mouth=1.0, bounce=0.6, blush=0.4),
    "happy":     dict(accent="#ffe66d", eye=0.35, mouth=1.0, bounce=1.0, blush=0.7),
    "excited":   dict(accent="#ff9ff3", eye=1.2, mouth=0.9, bounce=1.4, blush=0.8),
    "sad":       dict(accent="#8fb3ff", eye=0.85, mouth=0.1, bounce=0.0, blush=0.1),
    "sleep":     dict(accent="#a0b4d8", eye=0.0, mouth=0.15, bounce=0.0, blush=0.3),
    "error":     dict(accent="#ff7b7b", eye=1.1, mouth=0.15, bounce=0.4, blush=0.2),
    "love":      dict(accent="#ff6b9d", eye=0.6, mouth=0.7, bounce=0.8, blush=1.0),
}


def _font(size, bold=False):
    """Font sistem bila ada; fallback ke font bawaan pygame."""
    for names in ("dejavusans", "notosans,noto sans", "liberationsans,liberation sans",
                  "ubuntu", "freesans", "arial"):
        try:
            f = pygame.font.SysFont(names, size, bold=bold)
            if f:
                return f
        except Exception:
            continue
    return pygame.font.Font(None, int(size * 1.25))


def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def lerp(a, b, t):
    return a + (b - a) * t


class Face:
    def __init__(self, cfg):
        self.cfg = cfg["face"]
        self.name = cfg["assistant"]["name"]
        self.W = int(self.cfg["width"])
        self.H = int(self.cfg["height"])
        self.S = max(1, int(self.cfg.get("scale", 2)))
        self.fps = int(self.cfg.get("fps", 30))
        self.running = False
        self.mood = "idle"
        self.mood_until = 0.0
        self.t = 0.0
        self.mouth_level = 0.0
        self.mic_level = 0.0
        self.subtitle = ""
        self.subtitle_alpha = 0.0
        self.body = hex2rgb(self.cfg.get("body", "#6ee7ff"))
        self.body_dark = hex2rgb(self.cfg.get("body_dark", "#3aa7d8"))
        self.drag = None
        self._blink = 0.0
        self._next_blink = 2.0
        self._eye_look = 0.0
        self._eye_look_t = 0.0
        self._particles = []

    # ---------- lifecycle ----------
    def start(self):
        flags = pygame.NOFRAME
        if self.cfg.get("transparent", True):
            flags |= pygame.SRCALPHA
        pygame.init()
        pygame.display.set_caption(self.name)
        self.screen = pygame.display.set_mode((self.W, self.H), flags)
        self.screen.fill((0, 0, 0, 0))
        self.clock = pygame.time.Clock()
        self._place()
        if self.cfg.get("always_on_top", True):
            C.run_quiet(["wmctrl", "-r", self.name, "-b", "add,above"])
        if self.cfg.get("hide_taskbar", True):
            C.run_quiet(["wmctrl", "-r", self.name, "-b", "remove,from_taskbar,from_pager"])
        self.running = True
        self.font = _font(17)
        self.font_small = _font(14)
        self.big_font = _font(20, bold=True)
        if not C.which("wmctrl"):
            print("[face] wmctrl tidak ada: jendela mungkin ikut masuk taskbar/pager")
        threading.Thread(target=self._loop, daemon=True).start()

    

    def _place(self):
        pos = self.cfg.get("pos", "bottom-right")
        m = int(self.cfg.get("margin", 36))
        import os
        sw, sh = 1920, 1080
        try:
            info = pygame.display.Info()
            sw, sh = info.current_w, info.current_h
        except Exception:
            out = C.capture(["xdpyinfo"]) or ""
            for line in out.splitlines():
                if "dimensions:" in line:
                    try:
                        sw, sh = [int(x) for x in line.split()[1].split("x")]
                    except Exception:
                        pass
        if pos == "custom":
            x, y = self.cfg.get("custom_pos", [60, 60])
        elif pos == "bottom-right":
            x, y = sw - self.W - m, sh - self.H - m
        elif pos == "bottom-left":
            x, y = m, sh - self.H - m
        elif pos == "top-right":
            x, y = sw - self.W - m, m
        elif pos == "top-left":
            x, y = m, m
        else:
            x, y = (sw - self.W) // 2, (sh - self.H) // 2
        try:
            os.environ["SDL_VIDEO_WINDOW_POS"] = f"{max(0, x)},{max(0, y)}"
        except Exception:
            pass
        try:
            self._winpos = (x, y)
            pygame.display.set_mode((self.W, self.H), pygame.NOFRAME | pygame.SRCALPHA)
        except Exception:
            pass

    # ---------- API dari thread lain ----------
    def set_mood(self, mood, seconds=0.0):
        if mood in MOODS:
            self.mood = mood
            self.mood_until = self.t + seconds if seconds else 0.0

    def mood_for(self, seconds):
        return self.mood if self.mood_until == 0.0 or self.t < self.mood_until else "idle"

    def say(self, text):
        self.subtitle = text
        self.subtitle_alpha = 1.0
        self.set_mood("speaking")

    def set_mouth(self, level):
        self.mouth_level = max(0.0, min(1.0, level))

    def set_mic(self, level):
        self.mic_level = max(0.0, min(1.0, level * 8.0))

    def toggle(self):
        self.visible = not getattr(self, "visible", True)
        pygame.display.set_icon(pygame.Surface((1, 1)))
        return self.visible

    def stop(self):
        self.running = False

    # ---------- loop ----------
    def _loop(self):
        while self.running:
            dt = self.clock.tick(self.fps) / 1000.0
            self.t += dt
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    self.running = False
                elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    self.drag = [ev.pos, self._winpos]
                elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                    self.drag = None
                elif ev.type == pygame.MOUSEMOTION and self.drag:
                    self._move(ev.pos)
                elif ev.type == pygame.KEYDOWN:
                    if ev.key in (pygame.K_q, pygame.K_ESCAPE):
                        self.running = False
                    elif ev.key == pygame.K_h:
                        C.write_file(C.F_CMD, "toggle")
                    elif ev.key == pygame.K_s:
                        C.write_file(C.F_CMD, "silence")
            self._update(dt)
            self._draw()
            pygame.display.flip()
        pygame.quit()

    def _move(self, pos):
        try:
            import subprocess
            x = self.drag[1][0] + (pos[0] - self.drag[0][0])
            y = self.drag[1][1] + (pos[1] - self.drag[0][1])
            subprocess.run(["wmctrl", "-r", self.name, "-e", "0", str(x), str(y),
                            str(self.W), str(self.H)], capture_output=True)
            self._winpos = (x, y)
        except Exception:
            pass

    def _update(self, dt):
        # kedip
        self._next_blink -= dt
        if self._next_blink <= 0:
            self._blink = 1.0
            self._next_blink = random.uniform(2.2, 5.5)
        self._blink = max(0.0, self._blink - dt * 7.0)

        # arah mata
        self._eye_look_t -= dt
        if self._eye_look_t <= 0:
            self._eye_look = random.uniform(-1, 1)
            self._eye_look_t = random.uniform(1.5, 4.0)

        # subtitle fade
        if self.subtitle_alpha > 0:
            self.subtitle_alpha -= dt * 0.18
            if self.subtitle_alpha < 0:
                self.subtitle_alpha = 0.0

        # partikel kecil untuk mood happy/excited
        if self.mood in ("happy", "excited", "love") and random.random() < dt * 6:
            self._particles.append([
                random.uniform(self.W * 0.25, self.W * 0.75), random.uniform(20, self.H * 0.4),
                random.uniform(-14, 14), random.uniform(-22, -8), random.uniform(2, 4), 1.0,
            ])
        self._particles = [p for p in self._particles if p[5] > 0 and p[1] < self.H * 0.75]
        for p in self._particles:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[5] = max(0.0, p[5] - dt * 0.5)

    # ---------- gambar ----------
    def _draw(self):
        W, H, S = self.W, self.H, self.S
        surf = pygame.Surface((W, H), pygame.SRCALPHA)
        mood = MOODS.get(self.mood_for(0), MOODS["idle"])
        accent = hex2rgb(mood["accent"])

        cx, cy = W // 2, int(H * 0.42)
        bounce = mood["bounce"] * math.sin(self.t * 4.2) * 3.0
        bob = math.sin(self.t * 1.7) * 2.5
        cy += bounce + bob

        # bayangan
        sh = pygame.Surface((W * S, 90 * S), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 60), pygame.Rect(0, 0, W * S, 90 * S))
        sh = pygame.transform.smoothscale(sh, (W, 90))
        surf.blit(sh, (0, int(H * 0.72)))

        # lingkaran aura
        aura_r = int(min(W, H) * 0.36) + int(mood["bounce"] * 6)
        aura = pygame.Surface((W, H), pygame.SRCALPHA)
        for i in range(6, 0, -1):
            a = 8 + (6 - i) * 3
            pygame.draw.circle(aura, (*accent, a), (cx, cy), aura_r + i * 9)
        surf.blit(aura, (0, 0))

        # badan (kepala) — gradient
        head_r = int(min(W, H) * 0.27)
        head = pygame.Surface((head_r * 2 + 8, head_r * 2 + 8), pygame.SRCALPHA)
        for y in range(0, head.get_height(), 2):
            f = y / head.get_height()
            col = (int(lerp(self.body[0], self.body_dark[0], f)),
                   int(lerp(self.body[1], self.body_dark[1], f)),
                   int(lerp(self.body[2], self.body_dark[2], f)),
                   255)
            pygame.draw.line(head, col, (0, y), (head.get_width(), y + 2))
        head_rect = pygame.Rect(0, 0, head_r * 2 + 8, head_r * 2 + 8)
        mask = pygame.Surface(head_rect.size, pygame.SRCALPHA)
        pygame.draw.circle(mask, (255, 255, 255, 255), (head_r + 4, head_r + 4), head_r)
        head.blit(mask, (0, 0), None, pygame.BLEND_RGBA_MULT)
        # outline
        outline = pygame.Surface(head_rect.size, pygame.SRCALPHA)
        pygame.draw.circle(outline, (*accent, 200), (head_r + 4, head_r + 4), head_r, 4)
        outline.blit(head, (0, 0))
        surf.blit(outline, (cx - head_r - 4, cy - head_r - 4))

        # antena
        ay = cy - head_r - 6
        pygame.draw.line(surf, accent, (cx, ay - 2), (cx, ay - 22 - bounce), 4)
        ar = 7 + int(abs(math.sin(self.t * 5)) * (1.5 + mood["bounce"]))
        pygame.draw.circle(surf, accent, (cx, ay - 26 - bounce), ar)

        # telinga/ headphone
        for sx in (-1, 1):
            ex = cx + sx * (head_r + 2)
            pygame.draw.ellipse(surf, self.body_dark,
                                pygame.Rect(ex - 8, cy - 26, 16, 52))
            pygame.draw.ellipse(surf, (*accent, 220),
                                pygame.Rect(ex - 5, cy - 20, 10, 40))

        # blush
        if mood["blush"] > 0.05:
            blush = pygame.Surface((W, H), pygame.SRCALPHA)
            for sx in (-1, 1):
                pygame.draw.ellipse(blush, (255, 130, 170, int(90 * mood["blush"])),
                                    pygame.Rect(cx + sx * head_r * 0.62 - 22, cy + 22, 44, 26))
            surf.blit(blush, (0, 0))

        # mata
        self._draw_eyes(surf, cx, cy, head_r, mood, accent)

        # mulut (lip-sync)
        self._draw_mouth(surf, cx, cy, head_r, mood, accent)

        # subtitle bubble
        if self.cfg.get("subtitle") and self.subtitle:
            self._draw_subtitle(surf, mood)

        # mic level bar (kalau listening)
        if self.mood == "listening":
            self._draw_mic(surf, W, H, accent)

        # nama
        name = self.font_small.render(self.name, True, (255, 255, 255, 200))
        surf.blit(name, (W // 2 - name.get_width() // 2, int(H * 0.86)))

        # hint kecil
        hint = self.font_small.render("drag: pindah | H: bisu | Q: keluar", True, (255, 255, 255, 120))
        surf.blit(hint, (W // 2 - hint.get_width() // 2, int(H * 0.92)))

        # partikel
        for p in self._particles:
            a = max(0, min(255, int(200 * p[5])))
            r = max(1, int(p[4] * p[5] + 1))
            pygame.draw.circle(surf, (*accent, a), (int(p[0]), int(p[1])), r)

        big = pygame.transform.smoothscale(surf, (W, H))
        self.screen.blit(big, (0, 0))

    def _draw_eyes(self, surf, cx, cy, head_r, mood, accent):
        eye_open = mood["eye"] * (1.0 - self._blink * 0.95)
        if eye_open < 0.05:
            # tutup: garis melengkung (tidur)
            w = int(self._blink * head_r * 0.2)
            for sx in (-1, 1):
                ex = cx + sx * head_r * 0.42
                if self._blink > 0.4:
                    pygame.draw.arc(surf, (30, 40, 60), pygame.Rect(ex - 26, cy - 26 + w, 52, 52),
                                    0.2, math.pi - 0.2, 5)
                else:
                    pygame.draw.line(surf, (30, 40, 60), (ex - 22, cy), (ex + 22, cy), 5)
            return
        ew, eh = int(30 * eye_open), int(34 * min(1.3, eye_open))
        look = int(self._eye_look * 6)
        for sx in (-1, 1):
            ex = cx + sx * head_r * 0.42
            rect = pygame.Rect(ex - ew // 2, cy - eh - 6, ew, eh)
            pygame.draw.ellipse(surf, (255, 255, 255, 255), rect)
            pygame.draw.ellipse(surf, (25, 35, 55, 255),
                                pygame.Rect(rect.x + ew // 2 - ew // 4 + look - 2,
                                            rect.y + eh // 2 - eh // 3 + 2,
                                            ew // 2, int(eh * 0.62)))
            # highlight
            pygame.draw.circle(surf, (255, 255, 255, 220),
                               (rect.x + ew // 3, rect.y + eh // 3), max(3, ew // 8))

    def _draw_mouth(self, surf, cx, cy, head_r, mood, accent):
        mx, my = cx, cy + int(head_r * 0.52)
        lvl = self.mouth_level if mood["mouth"] > 0.5 else 0.0
        if self.mood == "sleep":
            pygame.draw.circle(surf, (25, 35, 55, 255), (mx, my), 6)
            return
        open_h = int(6 + lvl * 30)
        width = int(head_r * 0.5)
        if lvl < 0.06:
            # senyum garis (arah bergantung mood)
            if self.mood in ("sad", "error"):
                pygame.draw.arc(surf, (25, 35, 55, 255),
                                pygame.Rect(mx - width // 2, my - 12, width, 30),
                                math.pi + 0.3, 2 * math.pi - 0.3, 4)
            else:
                pygame.draw.arc(surf, (25, 35, 55, 255),
                                pygame.Rect(mx - width // 2, my - 10, width, 26),
                                0.2, math.pi - 0.2, 4)
        else:
            rect = pygame.Rect(mx - width // 2, my - open_h // 2, width, open_h)
            pygame.draw.ellipse(surf, (60, 25, 45, 255), rect)
            pygame.draw.ellipse(surf, (255, 130, 160, 220),
                                pygame.Rect(rect.x + width // 4, rect.bottom - open_h // 3,
                                            width // 2, max(3, open_h // 3)))
            pygame.draw.ellipse(surf, (255, 255, 255, 255), rect, 3)

    def _draw_subtitle(self, surf, mood):
        W = self.W
        maxw = int(W * 0.88)
        words = self.subtitle.split()
        lines, cur = [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if self.font.size(t)[0] <= maxw:
                cur = t
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        lines = lines[:4]
        lh = 22
        h = lh * len(lines) + 24
        y = int(self.H * 0.70) - h
        x = (W - maxw) // 2
        bubble = pygame.Surface((maxw, h), pygame.SRCALPHA)
        alpha = int(220 * min(1.0, self.subtitle_alpha))
        pygame.draw.rect(bubble, (20, 26, 40, alpha), pygame.Rect(0, 0, maxw, h), border_radius=14)
        pygame.draw.rect(bubble, (*hex2rgb(mood["accent"]), min(255, alpha)),
                         pygame.Rect(0, 0, maxw, h), 2, border_radius=14)
        # ekor bubble
        pygame.draw.polygon(bubble, (20, 26, 40, alpha),
                            [(maxw // 2 - 8, h - 1), (maxw // 2 + 8, h - 1), (maxw // 2, h + 10)])
        for i, line in enumerate(lines):
            txt = self.font.render(line, True, (240, 245, 255, min(255, alpha)))
            bubble.blit(txt, (12, 10 + i * lh))
        surf.blit(bubble, (x, y))

    def _draw_mic(self, surf, W, H, accent):
        n = 9
        bw = 4
        gap = 6
        total = n * (bw + gap)
        x0 = W // 2 - total // 2
        y = int(H * 0.64)
        lvl = min(1.0, self.mic_level)
        for i in range(n):
            phase = math.sin(self.t * 6 - i * 0.5) * 0.5 + 0.5
            h = int(4 + (6 + lvl * 26) * phase)
            a = int(120 + 135 * phase)
            pygame.draw.rect(surf, (*accent, a), pygame.Rect(x0 + i * (bw + gap), y - h, bw, h),
                             border_radius=2)


import threading  # noqa: E402