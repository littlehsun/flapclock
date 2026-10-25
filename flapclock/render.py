"""Cairo drawing for the split-flap face.

The look is an original white-on-black flap clock: equal cards, a gap
between hours and minutes, and a hinge through the middle of each glyph.
"""

from __future__ import annotations

import math

import cairo
import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo

from flapclock.clock import ClockFace

FONT_FAMILY = "Nimbus Sans"
# Flat matte faces. Real split-flap apps use two solid tones and a hairline
# hinge, not a glossy gradient.
TOP_FACE = (0.145, 0.145, 0.145)
BOTTOM_FACE = (0.078, 0.078, 0.078)
INK = (0.93, 0.93, 0.91)
GLYPH_CACHE: dict[tuple[str, int, int], cairo.ImageSurface] = {}
_CACHE_LIMIT = 64


def widget_size(scale: float) -> tuple[int, int]:
    scale = min(2.6, max(0.45, scale))
    return int(round(640 * scale)), int(round(250 * scale))


def draw_face(
    cr: cairo.Context,
    width: int,
    height: int,
    face: ClockFace,
    *,
    transparent_backdrop: bool,
) -> None:
    if transparent_backdrop:
        cr.save()
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.restore()
    else:
        cr.set_source_rgb(0, 0, 0)
        cr.paint()

    rects = _layout(width, height, bool(face.suffix))
    if not rects:
        return
    for index, rect in enumerate(rects):
        old = _glyph(face.previous[index], rect[2], rect[3])
        new = _glyph(face.digits[index], rect[2], rect[3])
        _draw_flap(cr, rect, old, new, face.phase[index])
    if face.suffix:
        _draw_suffix(cr, rects, face.suffix)


def _layout(width: int, height: int, has_suffix: bool) -> list[tuple[int, int, int, int]]:
    if width < 40 or height < 40:
        return []
    pad_x = max(16, int(width * 0.055))
    pad_y = max(14, int(height * 0.12))
    suffix_w = int(width * 0.11) if has_suffix else 0
    usable_w = width - pad_x * 2 - suffix_w
    usable_h = height - pad_y * 2
    gap_ratio = 0.14
    group_ratio = 0.40
    # card + card + gap + group + card + card, with gap expressed in card widths.
    card_w = usable_w / (4 + gap_ratio * 2 + group_ratio)
    card_h = card_w * 1.38
    if card_h > usable_h:
        card_h = usable_h
        card_w = card_h / 1.38
    card_w = max(1, int(card_w))
    card_h = max(1, int(card_h))
    gap = max(4, int(card_w * gap_ratio))
    group = max(gap + 8, int(card_w * group_ratio))
    row_w = card_w * 4 + gap * 2 + group + suffix_w
    x = max(0, (width - row_w) // 2)
    y = max(0, (height - card_h) // 2)
    rects = []
    for index in range(4):
        rects.append((x, y, card_w, card_h))
        x += card_w
        if index == 1:
            x += group
        elif index < 3:
            x += gap
    return rects


def _rounded_rect(cr: cairo.Context, x: float, y: float, w: float, h: float, radius: float) -> None:
    radius = min(radius, w / 2, h / 2)
    cr.new_sub_path()
    cr.arc(x + w - radius, y + radius, radius, -math.pi / 2, 0)
    cr.arc(x + w - radius, y + h - radius, radius, 0, math.pi / 2)
    cr.arc(x + radius, y + h - radius, radius, math.pi / 2, math.pi)
    cr.arc(x + radius, y + radius, radius, math.pi, 3 * math.pi / 2)
    cr.close_path()


def _glyph(char: str, width: int, height: int) -> cairo.ImageSurface:
    key = (char, width, height)
    cached = GLYPH_CACHE.get(key)
    if cached is not None:
        return cached
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)
    cr.set_operator(cairo.OPERATOR_SOURCE)
    cr.set_source_rgba(0, 0, 0, 0)
    cr.paint()
    cr.set_operator(cairo.OPERATOR_OVER)
    layout = PangoCairo.create_layout(cr)
    layout.set_text(char, -1)
    options = cairo.FontOptions()
    options.set_antialias(cairo.ANTIALIAS_GRAY)
    options.set_hint_style(cairo.HINT_STYLE_SLIGHT)
    PangoCairo.context_set_font_options(layout.get_context(), options)

    # Leave room for the stroke that thickens the grotesque without rounding it.
    target_w = width * 0.72
    target_h = height * 0.76
    low = 8.0
    high = float(height)
    best = low
    for _ in range(18):
        mid = (low + high) / 2
        layout.set_font_description(_font(mid))
        ink, _logical = layout.get_pixel_extents()
        if ink.width <= target_w and ink.height <= target_h:
            best = mid
            low = mid
        else:
            high = mid
    layout.set_font_description(_font(best))
    ink, _logical = layout.get_pixel_extents()
    expand = max(1.15, best * 0.055)
    cr.set_source_rgb(*INK)
    cr.save()
    cr.translate((width - ink.width) / 2 - ink.x, (height - ink.height) / 2 - ink.y)
    PangoCairo.layout_path(cr, layout)
    cr.set_line_width(expand * 2)
    cr.set_line_join(cairo.LINE_JOIN_MITER)
    cr.set_miter_limit(2.2)
    cr.fill_preserve()
    cr.stroke()
    cr.restore()

    if len(GLYPH_CACHE) >= _CACHE_LIMIT:
        GLYPH_CACHE.clear()
    GLYPH_CACHE[key] = surface
    return surface


def _font(size_px: float) -> Pango.FontDescription:
    desc = Pango.FontDescription(FONT_FAMILY)
    desc.set_weight(Pango.Weight.BOLD)
    desc.set_absolute_size(size_px * Pango.SCALE)
    return desc


def _draw_flap(
    cr: cairo.Context,
    rect: tuple[int, int, int, int],
    old: cairo.ImageSurface,
    new: cairo.ImageSurface,
    phase: float,
) -> None:
    x, y, w, h = rect
    gap = max(2, int(round(h * 0.018)))
    top_h = h // 2 - gap // 2
    bottom_y = y + h // 2 + gap - gap // 2
    bottom_h = y + h - bottom_y
    half = h / 2
    cr.save()
    _clip_card(cr, x, y, w, h)
    if phase <= 0:
        _paint_half(cr, new, 0, half, x, y, w, top_h, upper=True)
        _paint_half(cr, new, half, half, x, bottom_y, w, bottom_h, upper=False)
    elif phase <= 0.5:
        t = _ease_in(phase / 0.5)
        _paint_half(cr, new, 0, half, x, y, w, top_h, upper=True)
        _paint_half(cr, old, half, half, x, bottom_y, w, bottom_h, upper=False)
        flap_h = top_h * (1 - t)
        if flap_h >= 1:
            dest_y = y + top_h - flap_h
            src_h = half * (flap_h / top_h)
            _paint_half(cr, old, half - src_h, src_h, x, dest_y, w, flap_h, upper=True)
    else:
        t = _ease_out((phase - 0.5) / 0.5)
        _paint_half(cr, new, 0, half, x, y, w, top_h, upper=True)
        cr.rectangle(x, bottom_y, w, bottom_h)
        cr.set_source_rgb(*BOTTOM_FACE)
        cr.fill()
        flap_h = max(1.0, bottom_h * t)
        src_h = half * (flap_h / bottom_h)
        _paint_half(cr, new, half, src_h, x, bottom_y, w, flap_h, upper=False)
    _hinge_edge(cr, x, y + h / 2 - gap / 2, w, gap)
    cr.restore()


def _clip_card(cr: cairo.Context, x: float, y: float, w: float, h: float) -> None:
    radius = max(4.0, min(w, h) * 0.08)
    _rounded_rect(cr, x, y, w, h, radius)
    cr.clip()


def _paint_half(
    cr: cairo.Context,
    glyph: cairo.ImageSurface,
    src_y: float,
    src_h: float,
    dest_x: float,
    dest_y: float,
    dest_w: float,
    dest_h: float,
    *,
    upper: bool,
) -> None:
    """Paint one opaque flap face, then the digit slice that belongs on it."""
    if dest_h < 0.5 or dest_w < 0.5 or src_h < 0.5:
        return
    cr.save()
    cr.rectangle(dest_x, dest_y, dest_w, dest_h)
    cr.set_source_rgb(*(TOP_FACE if upper else BOTTOM_FACE))
    cr.fill()
    cr.restore()
    _blit(cr, glyph, src_y, src_h, dest_x, dest_y, dest_w, dest_h)


def _blit(
    cr: cairo.Context,
    surface: cairo.ImageSurface,
    src_y: float,
    src_h: float,
    dest_x: float,
    dest_y: float,
    dest_w: float,
    dest_h: float,
) -> None:
    if dest_h < 0.5 or src_h < 0.5 or dest_w < 0.5:
        return
    cr.save()
    cr.rectangle(dest_x, dest_y, dest_w, dest_h)
    cr.clip()
    scale_x = dest_w / surface.get_width()
    scale_y = dest_h / src_h
    cr.translate(dest_x, dest_y - src_y * scale_y)
    cr.scale(scale_x, scale_y)
    cr.set_source_surface(surface, 0, 0)
    cr.get_source().set_filter(cairo.FILTER_BILINEAR)
    cr.paint()
    cr.restore()


def _hinge_edge(cr: cairo.Context, x: float, y: float, w: float, thickness: float) -> None:
    cr.set_source_rgb(0, 0, 0)
    cr.rectangle(x, y, w, max(2.0, thickness))
    cr.fill()


def _ease_in(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return t * t


def _ease_out(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return 1 - (1 - t) * (1 - t)


def _draw_suffix(cr: cairo.Context, rects: list[tuple[int, int, int, int]], suffix: str) -> None:
    _x, y, w, h = rects[-1]
    right = rects[-1][0] + w
    layout_cr = cr
    layout = PangoCairo.create_layout(layout_cr)
    layout.set_text(suffix, -1)
    size = max(12, int(h * 0.14))
    desc = Pango.FontDescription(FONT_FAMILY)
    desc.set_weight(Pango.Weight.BOLD)
    desc.set_absolute_size(size * Pango.SCALE)
    layout.set_font_description(desc)
    ink, _logical = layout.get_pixel_extents()
    layout_cr.save()
    layout_cr.set_source_rgb(0.96, 0.96, 0.94)
    layout_cr.move_to(right + max(8, int(w * 0.08)), y + h * 0.62 - ink.y)
    PangoCairo.show_layout(layout_cr, layout)
    layout_cr.restore()
