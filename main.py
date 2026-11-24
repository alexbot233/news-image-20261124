#!/usr/bin/env python3
"""Deterministic, standard-library-only front page for 24 November 2026.

The image is drawn directly into an RGB byte buffer.  All lettering uses the
embedded 5x7 bitmap font below; every string is measured against its container
before it is drawn, and the whole text inventory is swept before the PNG is
written.
"""

from __future__ import annotations

import math
import os
import re
import struct
import zlib
from dataclasses import dataclass

W = H = 960

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
PAPER = (242, 237, 225)
CARD_PAPER = (252, 249, 241)
INK = (24, 22, 21)
MUTED = (92, 86, 78)
GOLD = (196, 148, 52)
RED = (172, 43, 38)
NAVY = (27, 51, 74)
CREAM = (251, 246, 234)
RULE = (207, 199, 184)
TICKER_DIM = (72, 92, 113)
FLAME = (222, 137, 46)

# ---------------------------------------------------------------------------
# 5x7 bitmap font.  The zero is slashed so 0 can never be read as O.
# ---------------------------------------------------------------------------
FONT: dict[str, tuple[str, ...]] = {
    "A": (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "B": ("####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    "C": (".####", "#....", "#....", "#....", "#....", "#....", ".####"),
    "D": ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "F": ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    "G": (".####", "#....", "#....", "#.###", "#...#", "#...#", ".###."),
    "H": ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "I": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"),
    "J": ("..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."),
    "K": ("#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"),
    "L": ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    "M": ("#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"),
    "N": ("#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"),
    "O": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "P": ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    "Q": (".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "S": (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "V": ("#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    "W": ("#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"),
    "X": ("#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"),
    "Y": ("#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
    "Z": ("#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"),
    # Digits: the zero carries a diagonal slash through its bowl.
    "0": (".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."),
    "1": ("..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "2": (".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"),
    "3": ("####.", "....#", "....#", ".###.", "....#", "....#", "####."),
    "4": ("...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."),
    "5": ("#####", "#....", "####.", "....#", "....#", "#...#", ".###."),
    "6": (".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."),
    "7": ("#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."),
    "8": (".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    "9": (".###.", "#...#", "#...#", ".####", "....#", "....#", ".###."),
    " ": (".....", ".....", ".....", ".....", ".....", ".....", "....."),
    "-": (".....", ".....", ".....", "#####", ".....", ".....", "....."),
    ",": (".....", ".....", ".....", ".....", ".....", "..#..", ".#..."),
    ".": (".....", ".....", ".....", ".....", ".....", ".....", "..#.."),
    ":": (".....", "..#..", "..#..", ".....", "..#..", "..#..", "....."),
    "/": ("....#", "....#", "...#.", "..#..", ".#...", "#....", "#...."),
    "&": (".##..", "#..#.", "#.#..", ".#...", "#.#.#", "#..#.", ".##.#"),
    "'": ("..#..", "..#..", ".....", ".....", ".....", ".....", "....."),
    "!": ("..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."),
}

DIGITS = frozenset("0123456789")
DATE_TEXT = "24 NOVEMBER 2026"
MONTH_WORDS = re.compile(
    r"\b(?:JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|"
    r"SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER|JAN|FEB|MAR|APR|JUN|JUL|"
    r"AUG|SEP|SEPT|OCT|NOV|DEC)\b"
)
YEAR_WORDS = re.compile(r"\b(?:18|19|20|21)\d{2}\b")
NUMERIC_DATE = re.compile(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{1,4})?\b")
KNOWN_SCORES = frozenset({"1-0"})


@dataclass(frozen=True)
class TextRecord:
    """One placed string, retained for the automated text sweep."""

    text: str
    x: int
    y: int
    scale: int
    width: int
    height: int
    box: tuple[int, int, int, int]
    role: str

    @property
    def x1(self) -> int:
        return self.x + self.width

    @property
    def y1(self) -> int:
        return self.y + self.height


DRAWN: list[TextRecord] = []


# ---------------------------------------------------------------------------
# Pixel canvas primitives
# ---------------------------------------------------------------------------
class Canvas:
    def __init__(self, width: int, height: int, color: tuple[int, int, int]) -> None:
        self.w = width
        self.h = height
        self.buf = bytearray(bytes(color) * (width * height))

    def px(self, x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            o = (y * self.w + x) * 3
            self.buf[o] = color[0]
            self.buf[o + 1] = color[1]
            self.buf[o + 2] = color[2]

    def rect(self, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
        xa, xb = max(0, x0), min(self.w, x1)
        ya, yb = max(0, y0), min(self.h, y1)
        if xa >= xb or ya >= yb:
            return
        row = bytes(color) * (xb - xa)
        for y in range(ya, yb):
            o = (y * self.w + xa) * 3
            self.buf[o:o + len(row)] = row

    def border(self, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
        self.rect(x0, y0, x1, y0 + 1, color)
        self.rect(x0, y1 - 1, x1, y1, color)
        self.rect(x0, y0, x0 + 1, y1, color)
        self.rect(x1 - 1, y0, x1, y1, color)

    def poly(self, points: list[tuple[int, int]], color: tuple[int, int, int]) -> None:
        if len(points) < 3:
            return
        ys = [p[1] for p in points]
        y_min = max(0, math.floor(min(ys)))
        y_max = min(self.h, math.ceil(max(ys)) + 1)
        n = len(points)
        for y in range(y_min, y_max):
            scan = y + 0.5
            crossings: list[float] = []
            for i in range(n):
                ax, ay = points[i]
                bx, by = points[(i + 1) % n]
                if (ay <= scan < by) or (by <= scan < ay):
                    crossings.append(ax + (scan - ay) * (bx - ax) / (by - ay))
            crossings.sort()
            for a, b in zip(crossings[0::2], crossings[1::2]):
                xa = max(0, math.ceil(a - 0.5))
                xb = min(self.w, math.ceil(b - 0.5))
                if xb > xa:
                    self.rect(xa, y, xb, y + 1, color)

    def ellipse(self, cx: int, cy: int, rx: int, ry: int, color: tuple[int, int, int]) -> None:
        steps = 40
        pts = [
            (
                round(cx + rx * math.cos(2.0 * math.pi * i / steps)),
                round(cy + ry * math.sin(2.0 * math.pi * i / steps)),
            )
            for i in range(steps)
        ]
        self.poly(pts, color)

    def line(self, x0: int, y0: int, x1: int, y1: int, width: int,
             color: tuple[int, int, int]) -> None:
        """Bresenham line drawn with a square brush of the requested width."""
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        half = width // 2
        while True:
            self.rect(x0 - half, y0 - half, x0 - half + width,
                      y0 - half + width, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy


# ---------------------------------------------------------------------------
# Text measuring and placement
# ---------------------------------------------------------------------------
def text_width(text: str, scale: int) -> int:
    if not text:
        return 0
    return (len(text) - 1) * 6 * scale + 5 * scale


def draw_text(canvas: Canvas, text: str, x: int, y: int, scale: int,
              color: tuple[int, int, int]) -> None:
    for col, char in enumerate(text):
        glyph = FONT[char]
        gx = x + col * 6 * scale
        for row, bits in enumerate(glyph):
            gy = y + row * scale
            start = -1
            for c in range(6):
                on = c < 5 and bits[c] == "#"
                if on and start < 0:
                    start = c
                if not on and start >= 0:
                    canvas.rect(gx + start * scale, gy,
                                gx + c * scale, gy + scale, color)
                    start = -1
            if start >= 0:
                canvas.rect(gx + start * scale, gy,
                            gx + 5 * scale, gy + scale, color)


def place(canvas: Canvas, text: str, scale: int, color: tuple[int, int, int],
          box: tuple[int, int, int, int], align: str = "left",
          role: str = "") -> None:
    """Measure against *box*, assert it fits, then draw and remember it."""
    x0, y0, x1, y1 = box
    w = text_width(text, scale)
    h = 7 * scale
    if align == "center":
        x = x0 + (x1 - x0 - w) // 2
    elif align == "right":
        x = x1 - w
    else:
        x = x0
    y = y0
    if not (x0 <= x and x + w <= x1 and y0 <= y and y + h <= y1):
        raise ValueError(
            f"text does not fit {role or 'box'}: {text!r} "
            f"{w}x{h} at ({x},{y}) in {box}"
        )
    draw_text(canvas, text, x, y, scale, color)
    DRAWN.append(TextRecord(text, x, y, scale, w, h, box, role or "text"))


def verify_text(records: list[TextRecord], width: int, height: int) -> list[str]:
    """Programmatic sweep of every string actually placed on the canvas."""
    checks: list[str] = []
    dates = [r for r in records if r.text == DATE_TEXT]
    assert len(dates) == 1, f"expected exactly one masthead date, found {len(dates)}"
    checks.append("exactly one 24 NOVEMBER 2026, all other strings date-free")
    assert dates[0].role == "masthead-date"
    assert dates[0].scale >= 4

    for r in records:
        t = r.text
        if t != DATE_TEXT:
            assert not MONTH_WORDS.search(t), f"month name outside masthead date: {t!r}"
            assert not YEAR_WORDS.search(t), f"four-digit year outside masthead date: {t!r}"
            for match in NUMERIC_DATE.finditer(t):
                assert match.group() in KNOWN_SCORES, f"date-like token: {t!r}"
        assert r.x >= r.box[0] and r.x1 <= r.box[2], f"horizontal clip: {t!r}"
        assert r.y >= r.box[1] and r.y1 <= r.box[3], f"vertical clip: {t!r}"
        assert 0 <= r.x and r.x1 <= width and 0 <= r.y and r.y1 <= height
        for ch in t:
            if ch in DIGITS:
                assert ch in FONT and FONT[ch] != FONT["O"], f"bad digit glyph: {ch!r}"
    checks.append("every placed line fits its measured container and canvas")
    checks.append("all digits use distinct 5x7 digit glyphs; slashed zero != O")

    assert FONT["0"] != FONT["O"]
    assert sum(FONT["0"][i] != FONT["O"][i] for i in range(7)) >= 3
    assert all(ch in FONT for r in records for ch in r.text)
    checks.append("font inventory complete; score 1-0 rendered from digit glyphs")
    return checks


# ---------------------------------------------------------------------------
# Pictograms: flat rectangles and polygons, no tiny floating artifacts
# ---------------------------------------------------------------------------
def pic_warship(c: Canvas, x: int, y: int, accent: tuple[int, int, int],
                tint: tuple[int, int, int]) -> None:
    c.rect(x + 8, y + 92, x + 108, y + 99, accent)
    c.rect(x + 14, y + 86, x + 38, y + 92, accent)
    c.rect(x + 46, y + 86, x + 70, y + 92, accent)
    c.rect(x + 78, y + 86, x + 102, y + 92, accent)
    c.poly([(x + 12, y + 68), (x + 102, y + 68), (x + 88, y + 87),
            (x + 26, y + 87)], accent)
    c.rect(x + 34, y + 60, x + 80, y + 68, accent)
    c.rect(x + 56, y + 32, x + 61, y + 60, accent)
    c.poly([(x + 61, y + 32), (x + 90, y + 40), (x + 61, y + 48)], INK)
    c.line(x + 16, y + 14, x + 46, y + 40, 5, INK)
    c.poly([(x + 42, y + 34), (x + 54, y + 44), (x + 40, y + 48)], INK)
    c.rect(x + 22, y + 74, x + 84, y + 77, tint)


def pic_rejected(c: Canvas, x: int, y: int, accent: tuple[int, int, int],
                 tint: tuple[int, int, int]) -> None:
    c.poly([(x + 20, y + 18), (x + 98, y + 24), (x + 94, y + 88),
            (x + 26, y + 82)], accent)
    for i in range(3):
        yy = y + 34 + i * 15
        c.rect(x + 34, yy, x + 82, yy + 5, tint)
    c.line(x + 30, y + 22, x + 90, y + 84, 6, INK)
    c.line(x + 90, y + 24, x + 30, y + 82, 6, INK)
    c.poly([(x + 26, y + 82), (x + 48, y + 84), (x + 40, y + 100),
            (x + 30, y + 92)], INK)


def pic_blast(c: Canvas, x: int, y: int, accent: tuple[int, int, int],
              tint: tuple[int, int, int]) -> None:
    cx, cy = x + 58, y + 60
    spikes: list[tuple[int, int]] = []
    for i in range(16):
        ang = 2.0 * math.pi * i / 16.0
        radius = 46 if i % 2 == 0 else 22
        spikes.append((round(cx + radius * math.cos(ang)),
                       round(cy + radius * math.sin(ang))))
    c.poly(spikes, accent)
    c.ellipse(cx, cy, 18, 18, tint)
    c.ellipse(cx, cy, 9, 9, INK)
    c.ellipse(x + 28, y + 22, 13, 18, INK)
    c.poly([(x + 18, y + 20), (x + 12, y + 8), (x + 26, y + 14)], INK)
    c.poly([(x + 38, y + 20), (x + 44, y + 8), (x + 30, y + 14)], INK)


def pic_scales(c: Canvas, x: int, y: int, accent: tuple[int, int, int],
               tint: tuple[int, int, int]) -> None:
    c.rect(x + 46, y + 94, x + 72, y + 101, accent)
    c.rect(x + 54, y + 34, x + 64, y + 94, accent)
    c.rect(x + 14, y + 32, x + 104, y + 39, accent)
    c.ellipse(x + 59, y + 27, 8, 8, accent)
    c.poly([(x + 16, y + 41), (x + 46, y + 41), (x + 40, y + 62),
            (x + 22, y + 62)], accent)
    c.poly([(x + 72, y + 41), (x + 102, y + 41), (x + 96, y + 62),
            (x + 78, y + 62)], accent)
    c.rect(x + 22, y + 66, x + 40, y + 70, tint)
    c.rect(x + 78, y + 66, x + 96, y + 70, tint)


def pic_growth(c: Canvas, x: int, y: int, accent: tuple[int, int, int],
               tint: tuple[int, int, int]) -> None:
    c.rect(x + 8, y + 96, x + 108, y + 101, INK)
    c.rect(x + 14, y + 74, x + 36, y + 96, accent)
    c.rect(x + 40, y + 60, x + 62, y + 96, accent)
    c.rect(x + 66, y + 44, x + 88, y + 96, accent)
    c.rect(x + 92, y + 30, x + 108, y + 96, accent)
    c.rect(x + 14, y + 70, x + 36, y + 74, INK)
    c.rect(x + 40, y + 56, x + 62, y + 60, INK)
    c.rect(x + 66, y + 40, x + 88, y + 44, INK)
    c.rect(x + 92, y + 26, x + 108, y + 30, INK)
    c.line(x + 18, y + 62, x + 94, y + 18, 4, tint)
    c.poly([(x + 88, y + 12), (x + 104, y + 16), (x + 92, y + 28)], tint)


def pic_rocket(c: Canvas, x: int, y: int, accent: tuple[int, int, int],
               tint: tuple[int, int, int]) -> None:
    c.poly([(x + 54, y + 8), (x + 68, y + 8), (x + 76, y + 68),
            (x + 46, y + 68)], accent)
    c.poly([(x + 46, y + 48), (x + 30, y + 72), (x + 46, y + 68)], INK)
    c.poly([(x + 76, y + 48), (x + 92, y + 72), (x + 76, y + 68)], INK)
    c.ellipse(x + 61, y + 32, 8, 8, INK)
    c.ellipse(x + 61, y + 32, 5, 5, tint)
    c.poly([(x + 50, y + 68), (x + 72, y + 68), (x + 61, y + 100)], FLAME)
    c.poly([(x + 55, y + 68), (x + 67, y + 68), (x + 61, y + 86)], tint)
    c.rect(x + 57, y + 92, x + 65, y + 100, accent)


def pic_trophy(c: Canvas, x: int, y: int, accent: tuple[int, int, int],
               tint: tuple[int, int, int]) -> None:
    c.poly([(x + 30, y + 20), (x + 86, y + 20), (x + 80, y + 58),
            (x + 68, y + 72), (x + 48, y + 72), (x + 36, y + 58)], accent)
    c.rect(x + 18, y + 28, x + 32, y + 52, accent)
    c.rect(x + 18, y + 28, x + 30, y + 33, tint)
    c.rect(x + 84, y + 28, x + 98, y + 52, accent)
    c.rect(x + 86, y + 28, x + 98, y + 33, tint)
    c.rect(x + 55, y + 72, x + 63, y + 90, accent)
    c.rect(x + 38, y + 90, x + 80, y + 98, accent)
    c.ellipse(x + 90, y + 80, 10, 10, INK)
    c.poly([(x + 90, y + 72), (x + 93, y + 78), (x + 99, y + 79),
            (x + 94, y + 83), (x + 96, y + 89), (x + 90, y + 85),
            (x + 84, y + 89), (x + 86, y + 83), (x + 81, y + 79),
            (x + 87, y + 78)], tint)


def pic_volcano(c: Canvas, x: int, y: int, accent: tuple[int, int, int],
                tint: tuple[int, int, int]) -> None:
    c.poly([(x + 4, y + 94), (x + 42, y + 30), (x + 76, y + 30),
            (x + 112, y + 94)], accent)
    c.poly([(x + 42, y + 30), (x + 76, y + 30), (x + 67, y + 44),
            (x + 51, y + 44)], tint)
    c.poly([(x + 54, y + 42), (x + 68, y + 42), (x + 78, y + 72),
            (x + 66, y + 94), (x + 58, y + 70)], FLAME)
    c.ellipse(x + 54, y + 18, 15, 13, INK)
    c.ellipse(x + 74, y + 9, 12, 10, MUTED)
    c.rect(x + 6, y + 94, x + 110, y + 102, INK)
    c.rect(x + 12, y + 102, x + 104, y + 106, tint)


PICTOGRAMS = (pic_warship, pic_rejected, pic_blast, pic_scales,
              pic_growth, pic_rocket, pic_trophy, pic_volcano)

# ---------------------------------------------------------------------------
# Story copy: only facts present in NEWS.md, all uppercase, all pre-measured
# ---------------------------------------------------------------------------
CARDS = [
    {
        "header": "EUROPE / WAR", "accent": RED, "tint": (238, 224, 219),
        "label": ("UKRAINE WAR", "WIDENS"),
        "sub": ("WARSHIP SUNK IN LIBYA", "MISSILES LAND IN POLAND"),
    },
    {
        "header": "WORLD / CLIMATE", "accent": (28, 103, 100), "tint": (217, 234, 231),
        "label": ("COP31 TALKS", "COLLAPSE"),
        "sub": ("EU, UP TO 100 STATES", "REJECT DRAFT TEXT"),
    },
    {
        "header": "MIDDLE EAST", "accent": (121, 45, 43), "tint": (234, 220, 219),
        "label": ("GAZA CHIEF", "KILLED"),
        "sub": ("STRIKES KILL ABU NAHEL", "AND SIX OTHERS"),
    },
    {
        "header": "EUROPE / COURTS", "accent": (35, 66, 104), "tint": (220, 227, 237),
        "label": ("SARKOZY &", "BRUNI TRIAL"),
        "sub": ("CHARGED OVER ALLEGED", "WITNESS TAMPERING"),
    },
    {
        "header": "US / BUSINESS", "accent": (34, 95, 66), "tint": (218, 232, 222),
        "label": ("HUANG BACK", "AS CEO"),
        "sub": ("SHARES UP MORE THAN", "30 PERCENT"),
    },
    {
        "header": "ASIA / SPACE", "accent": (54, 63, 129), "tint": (223, 225, 239),
        "label": ("CHINA: FIRST", "FOREIGN CREW"),
        "sub": ("PAKISTAN'S ZEESHAN ALI", "ABOARD TIANGONG"),
    },
    {
        "header": "AFRICA / SPORT", "accent": (139, 94, 24), "tint": (239, 229, 207),
        "label": ("SENEGAL CUP", "TITLE BACK"),
        "sub": ("CAS UPHOLDS APPEAL", "1-0 OVER MOROCCO"),
    },
    {
        "header": "PACIFIC / NATURE", "accent": (155, 73, 39), "tint": (240, 225, 215),
        "label": ("VOLCANO", "GROWS ISLAND"),
        "sub": ("ERUPTION EXTENDS", "IWO JIMA'S BEACH"),
    },
]

TICKER = (
    "HOUTHI FORCES 60 KM FROM ADEN",
    "FRENCH OFFICER MURDER TRIAL",
    "HOSTAGES AT CARTAGENA STORE",
    "27 RESIDENTS SUE COPPER MINE",
    "DR CONGO, KENYA RESTORE TIES",
    "WEBB: HOT DUST IN SUPERNOVA",
)


# ---------------------------------------------------------------------------
# Page composition
# ---------------------------------------------------------------------------
def draw_masthead(c: Canvas) -> None:
    c.rect(0, 0, W, 8, INK)
    c.rect(0, 8, W, 10, GOLD)
    place(c, "WORLD NEWS", 9, INK, (0, 18, W, 84), "center", "masthead-title")
    for xa, xb in ((24, 190), (770, 936)):
        c.rect(xa, 48, xb, 51, INK)
        c.poly([((xa + xb) // 2 - 6, 49), ((xa + xb) // 2, 42),
                ((xa + xb) // 2 + 6, 49), ((xa + xb) // 2, 56)], GOLD)
    c.rect(0, 92, W, 148, RED)
    c.rect(0, 92, W, 95, GOLD)
    c.rect(0, 145, W, 148, GOLD)
    place(c, DATE_TEXT, 5, CREAM, (0, 101, W, 139), "center", "masthead-date")
    c.poly([(204, 113), (211, 120), (204, 127), (197, 120)], CREAM)
    c.poly([(756, 113), (763, 120), (756, 127), (749, 120)], CREAM)
    c.rect(0, 154, W, 156, INK)


def draw_card(c: Canvas, number: int, index: int, card: dict, cx: int, cy: int) -> None:
    accent = card["accent"]
    tint = card["tint"]
    c.rect(cx, cy, cx + 448, cy + 164, INK)
    c.rect(cx + 1, cy + 1, cx + 447, cy + 163, CARD_PAPER)
    c.rect(cx + 1, cy + 1, cx + 447, cy + 28, accent)
    c.rect(cx + 1, cy + 28, cx + 447, cy + 30, INK)

    place(c, card["header"], 2, CREAM,
          (cx + 14, cy + 7, cx + 434, cy + 21), "left", f"card-{number}-region")

    px, py = cx + 12, cy + 40
    c.rect(px, py, px + 116, py + 112, tint)
    c.border(px, py, px + 116, py + 112, accent)
    PICTOGRAMS[index](c, px + 3, py + 2, accent, tint)

    tx = cx + 142
    place(c, card["label"][0], 4, INK, (tx, cy + 39, cx + 434, cy + 67),
          "left", f"card-{number}-headline-1")
    place(c, card["label"][1], 4, accent, (tx, cy + 69, cx + 434, cy + 97),
          "left", f"card-{number}-headline-2")
    c.rect(tx, cy + 104, cx + 434, cy + 106, RULE)
    place(c, card["sub"][0], 2, MUTED, (tx, cy + 110, cx + 434, cy + 124),
          "left", f"card-{number}-detail-1")
    place(c, card["sub"][1], 2, MUTED, (tx, cy + 130, cx + 434, cy + 144),
          "left", f"card-{number}-detail-2")


def draw_ticker(c: Canvas) -> None:
    c.rect(0, 844, W, H, NAVY)
    c.rect(0, 844, W, 850, RED)
    c.rect(0, 956, W, 960, GOLD)
    c.rect(478, 850, 482, 956, TICKER_DIM)
    for yy in (886, 922):
        c.rect(20, yy, 940, yy + 2, TICKER_DIM)
    cells = ((36, 474), (492, 930))
    for i, headline in enumerate(TICKER):
        cell_x0, cell_x1 = cells[i % 2]
        row = i // 2
        ty = 858 + row * 36
        c.rect(cell_x0 + 4, ty + 4, cell_x0 + 10, ty + 10, GOLD)
        place(c, headline, 2, CREAM,
              (cell_x0 + 16, ty, cell_x1 - 4, ty + 14),
              "left", f"ticker-{i + 1}")


def render() -> Canvas:
    DRAWN.clear()
    c = Canvas(W, H, PAPER)
    draw_masthead(c)
    for i, card in enumerate(CARDS):
        cx = 24 + (i % 2) * 464
        cy = 160 + (i // 2) * 170
        draw_card(c, i + 1, i, card, cx, cy)
    draw_ticker(c)
    verify_text(DRAWN, W, H)
    return c


# ---------------------------------------------------------------------------
# PNG output (hand-rolled IHDR / IDAT / IEND)
# ---------------------------------------------------------------------------
def chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def write_png(path: str, canvas: Canvas) -> None:
    raw = bytearray()
    stride = canvas.w * 3
    for y in range(canvas.h):
        raw.append(0)  # filter type: none
        raw.extend(canvas.buf[y * stride:(y + 1) * stride])
    ihdr = struct.pack(">IIBBBBB", canvas.w, canvas.h, 8, 2, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", ihdr)
           + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
           + chunk(b"IEND", b""))
    with open(path, "wb") as fh:
        fh.write(png)


def main() -> None:
    out_dir = os.environ.get("OUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    canvas = render()
    write_png(os.path.join(out_dir, "entry.png"), canvas)


if __name__ == "__main__":
    main()
