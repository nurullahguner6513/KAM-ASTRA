"""
Holografik astronot kıyafeti — sağlık analizi görseli (yalnızca Pillow).

Dönen, taranan bir astronot silueti çizer; vücut bölgeleri risk motorunun
bulgularına göre renklenir:
  ZİHİN / UYKU (kask)  · KALP · AKCİĞER / SpO2 · DERİ ISISI · AKTİVİTE (bacak) · RADYASYON (kıyafet çevresi)
Renkler: yeşil = normal, sarı = bilgilendirme, turuncu = dikkat, kırmızı = yüksek risk / acil, gri = veri yok.
Renkler yalnızca kural tabanlı risk motorunun sonucunu gösterir; teşhis değildir.
"""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 560, 690
CX = W // 2
TOP = 70  # figürün üst sınırı

BG = (2, 12, 12)
PRI = (0, 212, 192)
TEXT = (125, 255, 246)
LEVEL_RGB = {None: (90, 115, 112), 0: (0, 255, 136), 1: (255, 204, 0), 2: (255, 153, 0),
             3: (255, 51, 68), 4: (255, 51, 68)}
LEVEL_WORD = {None: "VERİ YOK", 0: "NORMAL", 1: "BİLGİ", 2: "DİKKAT", 3: "YÜKSEK RİSK", 4: "ACİL"}

# bölge: (etiket, göstergeler, etiket sütunu, işaret konumu (gövde koordinatı))
ZONES = {
    "head": ("ZİHİN / UYKU", ("stress_level", "sleep_total_min"), "left", (0, 62)),
    "heart": ("KALP", ("resting_hr", "heart_rate_mean", "hrv_rmssd"), "right", (24, 168)),
    "lungs": ("AKCİĞER / SpO2", ("spo2_mean", "spo2"), "left", (-28, 186)),
    "skin": ("DERİ ISISI", ("skin_temp_mean",), "right", (84, 212)),
    "legs": ("AKTİVİTE", ("steps", "longest_sedentary_min"), "left", (-29, 395)),
    "suit": ("RADYASYON", (), "right", (0, 0)),
}


def zone_states(assessment) -> dict[str, int | None]:
    """Risk değerlendirmesinden bölge seviyeleri. None: o bölge için veri yok."""
    states = {}
    for zone, (_, keys, _, _) in ZONES.items():
        if zone == "suit":
            has_data = assessment.radiation.has_data
            levels = [f.level for f in assessment.findings if f.category == "radiation"]
        else:
            has_data = any(k in assessment.summary.values for k in keys)
            levels = [f.level for f in assessment.findings if f.indicator in keys]
        states[zone] = max(levels, default=0) if has_data or levels else None
    return states


def _font(size: int, bold: bool = False):
    base = Path(__file__).resolve().parents[3]
    candidates = [
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
        base / "Fonts" / ("Grift-Bold.ttf" if bold else "Grift-Regular.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
             else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        try:
            if path.exists():
                font = ImageFont.truetype(str(path), size)
                if font.getlength("İĞŞ") > 0:
                    return font
        except Exception:
            continue
    return ImageFont.load_default()


def _rgba(rgb, alpha):
    return (*rgb, int(max(0, min(255, alpha))))


class _Body:
    """Gövde koordinatlarını (x: merkezden, y: yukarıdan) dönüşe göre ekrana çevirir."""

    def __init__(self, scale_x: float):
        self.s = scale_x

    def p(self, x, y):
        return (CX + x * self.s, TOP + y)

    def box(self, x0, y0, x1, y1):
        a, b = self.p(x0, y0), self.p(x1, y1)
        return (min(a[0], b[0]), a[1], max(a[0], b[0]), b[1])

    def poly(self, pts):
        return [self.p(x, y) for x, y in pts]


def _draw_suit(d: ImageDraw.ImageDraw, b: _Body, front: bool, alpha: float):
    line = _rgba(PRI, 230 * alpha)
    fill = _rgba(PRI, 34 * alpha)
    dim = _rgba(PRI, 120 * alpha)
    w = 2
    # sırt çantası (arkadan bakınca öne çıkar)
    d.rounded_rectangle(b.box(-66, 112, 66, 262), 12, fill=_rgba(PRI, (18 if front else 46) * alpha),
                        outline=dim if front else line, width=w)
    # bacaklar ve botlar
    for sign in (-1, 1):
        x0, x1 = (-50, -9) if sign < 0 else (9, 50)
        d.rounded_rectangle(b.box(x0, 300, x1, 458), 14, fill=fill, outline=line, width=w)
        d.line([b.p(x0 + 4, 380), b.p(x1 - 4, 380)], fill=dim, width=1)  # diz
        bx0, bx1 = (-58, -6) if sign < 0 else (6, 58)
        d.rounded_rectangle(b.box(bx0, 452, bx1, 492), 10, fill=_rgba(PRI, 60 * alpha), outline=line, width=w)
    # kollar ve eldivenler
    for sign in (-1, 1):
        arm = [(58 * sign, 122), (92 * sign, 132), (98 * sign, 268), (70 * sign, 270), (60 * sign, 160)]
        d.polygon(b.poly(arm), fill=fill, outline=line)
        d.line([b.p(78 * sign, 196), b.p(96 * sign, 196)], fill=dim, width=1)  # dirsek
        gx, gy = b.p(84 * sign, 288)
        r = 17
        d.ellipse((gx - r * abs(b.s), gy - r, gx + r * abs(b.s), gy + r), fill=_rgba(PRI, 60 * alpha),
                  outline=line, width=w)
    # gövde
    d.rounded_rectangle(b.box(-60, 112, 60, 308), 20, fill=fill, outline=line, width=w)
    d.rectangle(b.box(-60, 284, 60, 300), fill=_rgba(PRI, 55 * alpha), outline=dim)  # kemer
    if front:
        d.rounded_rectangle(b.box(-32, 140, 32, 204), 6, fill=_rgba(PRI, 50 * alpha), outline=line, width=w)
        for i, x in enumerate((-20, -6, 8, 22)):  # kontrol paneli ışıkları
            cx, cy = b.p(x, 152)
            r = 3
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=_rgba((0, 255, 136) if i % 2 else PRI, 220 * alpha))
        for y in (172, 182, 192):
            d.line([b.p(-24, y), b.p(24, y)], fill=dim, width=1)
    # boyun halkası ve kask
    d.ellipse(b.box(-40, 100, 40, 124), fill=_rgba(PRI, 50 * alpha), outline=line, width=w)
    hx, hy = b.p(0, 58)
    rx, ry = 52 * abs(b.s), 54
    d.ellipse((hx - rx, hy - ry, hx + rx, hy + ry), fill=fill, outline=line, width=w + 1)
    if front:
        vx0, vy0, vx1, vy1 = b.box(-38, 34, 38, 86)
        d.ellipse((vx0, vy0, vx1, vy1), fill=_rgba((0, 40, 48), 200 * alpha), outline=line, width=w)
        d.arc((vx0 + 6, vy0 + 5, vx1 - 6, vy1 - 8), 200, 250, fill=_rgba((200, 255, 250), 200 * alpha), width=3)


ASSET = Path(__file__).resolve().parent / "assets" / "astronot_hologram.png"
# Bölge işaretlerinin kaynak görseldeki (480×480) konumları
ASSET_POINTS = {"head": (240, 52), "heart": (263, 148), "lungs": (214, 150), "skin": (346, 232),
                "legs": (213, 362)}
ASSET_HEIGHT = 520  # figürün ekrandaki yüksekliği (piksel)


@lru_cache(maxsize=1)
def _asset_figure():
    """Kullanıcının verdiği tel kafes astronot görselini turkuaz hologram katmanına çevirir.

    Döndürür: (renkli figür RGBA, işaret konumları, ayak hizası) — görsel yoksa None.
    """
    if not ASSET.exists():
        return None
    from PIL import ImageOps

    gray = Image.open(ASSET).convert("L")
    x0, y0, x1, y1 = gray.point(lambda v: 255 if v > 40 else 0).getbbox()
    x0, y0, x1, y1 = max(0, x0 - 8), max(0, y0 - 8), min(gray.width, x1 + 8), min(gray.height, y1 + 8)
    crop = gray.crop((x0, y0, x1, y1))
    scale = ASSET_HEIGHT / crop.height
    crop = crop.resize((round(crop.width * scale), ASSET_HEIGHT), Image.LANCZOS)
    ox, oy = (W - crop.width) // 2, TOP - 15

    color = ImageOps.colorize(crop, black=(0, 0, 0), mid=PRI, white=(215, 255, 250)).convert("RGBA")
    color.putalpha(crop.point(lambda v: min(255, int(v * 1.25))))
    figure = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    figure.alpha_composite(color, (ox, oy))
    points = {zone: (ox + (x - x0) * scale, oy + (y - y0) * scale) for zone, (x, y) in ASSET_POINTS.items()}
    return figure, points, oy + crop.height - 6


def _with_alpha(image: Image.Image, factor: float) -> Image.Image:
    out = image.copy()
    out.putalpha(out.getchannel("A").point(lambda v: int(v * factor)))
    return out


def _glitch(layer: Image.Image, i: int) -> Image.Image:
    """Bazı karelerde yatay şeritleri kaydırarak hologram titremesi verir."""
    if i % 12 not in (5, 6):
        return layer
    out = layer.copy()
    for k, shift in ((0, 5), (1, -4)):
        y = 120 + ((i * 97 + k * 211) % 380)
        strip = layer.crop((0, y, W, y + 6 + 4 * k))
        out.paste((0, 0, 0, 0), (0, y, W, y + 6 + 4 * k))
        out.alpha_composite(strip, (shift, y))
    return out


def _marker(d, xy, level, phase, alpha):
    color = LEVEL_RGB[level]
    pulse = 0.5 + 0.5 * math.sin(phase * (2.5 if (level or 0) >= 3 else 1.0))
    r = 7 + 3 * pulse
    x, y = xy
    d.ellipse((x - r, y - r, x + r, y + r), fill=_rgba(color, 230 * alpha), outline=_rgba((255, 255, 255), 160 * alpha))
    if level is not None and level >= 2:
        rr = 14 + 12 * pulse
        d.ellipse((x - rr, y - rr, x + rr, y + rr), outline=_rgba(color, (200 - 150 * pulse) * alpha), width=2)


def render_frames(states: dict[str, int | None], overall: int, simulated: bool, title: str = "",
                  count: int = 36) -> list[Image.Image]:
    """Dönen hologram animasyonunun karelerini üretir (RGB, W×H)."""
    return list(_render_cached(tuple(sorted(states.items(), key=lambda kv: kv[0])), overall, simulated,
                               title, count))


@lru_cache(maxsize=8)
def _render_cached(states_items, overall, simulated, title, count):
    states = dict(states_items)
    f_title, f_label, f_small = _font(17, True), _font(14, True), _font(12)
    frames = []
    for i in range(count):
        theta = 2 * math.pi * i / count
        c = math.cos(theta)
        front = c >= 0
        scale = math.copysign(max(abs(c), 0.22), c)
        flicker = 0.88 + 0.12 * math.sin(i * 2.3)

        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)

        # zemin halkaları ve dönen nokta
        for rx, ry, a in ((150, 26, 120), (200, 36, 70)):
            d.ellipse((CX - rx, TOP + 500 - ry, CX + rx, TOP + 500 + ry), outline=_rgba(PRI, a), width=2)
        dot = (CX + 150 * math.cos(theta * 2), TOP + 500 + 26 * math.sin(theta * 2))
        d.ellipse((dot[0] - 4, dot[1] - 4, dot[0] + 4, dot[1] + 4), fill=_rgba(PRI, 230))

        # radyasyon: kıyafet çevresinde ışıma
        suit_level = states.get("suit")
        aura = LEVEL_RGB[suit_level]
        pulse = 0.5 + 0.5 * math.sin(theta * 4)
        d.ellipse((CX - 140, TOP - 20, CX + 140, TOP + 510), outline=_rgba(aura, 60 + 80 * pulse), width=2)

        asset = _asset_figure()
        positions = {}
        if asset is not None:
            # Gerçekçi tel kafes kıyafet: sabit önden görünüm, titreşim ve tarama efekti
            figure, points, _ = asset
            front = True
            layer.alpha_composite(_glitch(_with_alpha(figure, flicker), i))
            for zone, xy in points.items():
                positions[zone] = xy
                _marker(d, xy, states.get(zone), theta * 3, flicker)
        else:
            _draw_suit(d, _Body(scale), front, flicker)
            body = _Body(scale)
            marker_alpha = 1.0 if front else 0.35  # arkadan bakınca soluk
            for zone, (_, _, _, pos) in ZONES.items():
                if zone == "suit":
                    continue
                positions[zone] = body.p(*pos)
                _marker(d, positions[zone], states.get(zone), theta * 3, marker_alpha * flicker)

        glow = layer.filter(ImageFilter.GaussianBlur(6))
        frame = Image.new("RGBA", (W, H), (*BG, 255))
        frame.alpha_composite(glow)
        if asset is None:  # çizilen figür ince olduğu için iki kat parıltı
            frame.alpha_composite(glow)
        frame.alpha_composite(layer)

        # tarama çizgileri ve hareketli tarama bandı
        over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        o = ImageDraw.Draw(over)
        for y in range(0, H, 3):
            o.line([(0, y), (W, y)], fill=(0, 0, 0, 55))
        band_y = TOP - 10 + (i / count) * 520  # aşağı inen ince tarama çizgisi ve sönen izi
        o.line([(CX - 150, band_y), (CX + 150, band_y)], fill=_rgba((180, 255, 248), 140), width=2)
        for k in range(1, 22):
            o.line([(CX - 150, band_y - k), (CX + 150, band_y - k)], fill=_rgba(PRI, 26 - k))
        frame.alpha_composite(over)

        # sabit etiketler ve bağlantı çizgileri
        t = ImageDraw.Draw(frame)
        rows = {"left": 0, "right": 0}
        for zone, (label, _, side, _) in ZONES.items():
            level = states.get(zone)
            color = LEVEL_RGB[level]
            y = TOP + 40 + rows[side] * 150
            rows[side] += 1
            x = 18 if side == "left" else W - 18
            anchor = "la" if side == "left" else "ra"
            t.text((x, y), label, font=f_label, fill=TEXT, anchor=anchor)
            t.text((x, y + 20), LEVEL_WORD[level], font=f_small, fill=color, anchor=anchor)
            if zone in positions:
                gap = f_label.getlength(label) + 8
                lx = x + gap if side == "left" else x - gap
                t.line([(lx, y + 9), positions[zone]], fill=_rgba(color, 150 if front else 60), width=1)
        t.text((CX, 20), title or "ASTRA · HOLOGRAFİK SAĞLIK TARAMASI", font=f_title, fill=TEXT, anchor="ma")
        footer = f"GENEL SEVİYE {overall} · {LEVEL_WORD[overall]}"
        t.text((CX, H - 46), footer, font=f_label, fill=LEVEL_RGB[overall], anchor="ma")
        if simulated:
            t.text((CX, H - 24), "SİMÜLASYON VERİSİ — gerçek ölçüm değildir", font=f_small, fill=(255, 204, 0),
                   anchor="ma")
        frames.append(frame.convert("RGB"))
    return frames


# ── Ana ekran için dönen küçük hologram ──────────────────────────────────────
@lru_cache(maxsize=1)
def _asset_crop():
    if not ASSET.exists():
        return None
    gray = Image.open(ASSET).convert("L")
    x0, y0, x1, y1 = gray.point(lambda v: 255 if v > 40 else 0).getbbox()
    return gray.crop((max(0, x0 - 6), max(0, y0 - 6), min(gray.width, x1 + 6), min(gray.height, y1 + 6)))


def render_turntable(level: int, width: int, height: int, count: int = 48) -> list[Image.Image]:
    """KAM ana ekranına konacak dönen astronot hologramı (saydam arka planlı RGBA kareler).

    Kaynak görsel tek bir önden görünüm olduğu için dönüş, figürü yatayda daraltıp
    arka yüzde aynalayarak verilir. Renk genel risk seviyesini gösterir.
    """
    return list(_turntable_cached(level, width, height, count))


@lru_cache(maxsize=6)
def _turntable_cached(level, width, height, count):
    from PIL import ImageOps

    crop = _asset_crop()
    tint = PRI if level in (None, 0) else LEVEL_RGB[level]
    floor_h = max(10, height // 14)
    fig_h = height - floor_h - 6
    frames = []
    if crop is None:  # görsel yoksa: çizilen figürü küçült
        for i in range(count):
            big = _render_cached(tuple(), level or 0, False, " ", count)[i % count]
            frames.append(big.resize((width, height)).convert("RGBA"))
        return frames
    base = crop.resize((max(2, round(crop.width * fig_h / crop.height)), fig_h), Image.LANCZOS)
    for i in range(count):
        theta = 2 * math.pi * i / count
        c = math.cos(theta)
        w = max(2, round(base.width * max(abs(c), 0.06)))
        g = base.resize((w, fig_h), Image.LANCZOS)
        if c < 0:
            g = ImageOps.mirror(g).point(lambda v: int(v * 0.7))  # arka yüz: aynalı ve soluk
        flicker = 0.85 + 0.15 * math.sin(i * 1.7)
        color = ImageOps.colorize(g, black=(0, 0, 0), mid=tint, white=(215, 255, 250)).convert("RGBA")
        color.putalpha(g.point(lambda v: min(255, int(v * 1.3 * flicker))))

        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        layer.alpha_composite(color, ((width - w) // 2, 2))
        d = ImageDraw.Draw(layer)
        cy = height - floor_h // 2 - 2
        rx = width * 0.42
        d.ellipse((width / 2 - rx, cy - floor_h / 2, width / 2 + rx, cy + floor_h / 2), outline=_rgba(tint, 150), width=2)
        dot = (width / 2 + rx * math.cos(theta * 2), cy + floor_h / 2 * math.sin(theta * 2))
        d.ellipse((dot[0] - 3, dot[1] - 3, dot[0] + 3, dot[1] + 3), fill=_rgba(tint, 230))
        scan_y = 2 + (i / count) * fig_h
        d.line([(width * 0.15, scan_y), (width * 0.85, scan_y)], fill=_rgba((180, 255, 248), 110), width=1)

        glow = layer.filter(ImageFilter.GaussianBlur(4))
        frame = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        frame.alpha_composite(glow)
        frame.alpha_composite(layer)
        frames.append(frame)
    return frames
