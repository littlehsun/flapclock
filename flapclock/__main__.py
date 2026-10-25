"""Run Flapclock, or check the clock without opening a window."""

from __future__ import annotations

import sys
from datetime import datetime

import cairo

from flapclock.clock import ClockFace, format_digits
from flapclock.render import draw_face


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv if argv is None else argv)
    if "--self-test" in args:
        return _self_test()
    if "--screenshot" in args:
        index = args.index("--screenshot")
        if index + 1 >= len(args):
            print("用法：flapclock --screenshot 檔案.png", file=sys.stderr)
            return 2
        return _write_screenshot(args[index + 1])
    from flapclock.app import FlapclockApp

    app = FlapclockApp()
    return app.run(args)


def _self_test() -> int:
    assert format_digits(datetime(2026, 1, 1, 0, 0), True) == ("0000", "")
    assert format_digits(datetime(2026, 1, 1, 0, 0), False) == ("1200", "AM")
    assert format_digits(datetime(2026, 1, 1, 12, 0), False) == ("1200", "PM")
    assert format_digits(datetime(2026, 1, 1, 13, 5), True) == ("1305", "")
    assert format_digits(datetime(2026, 1, 1, 13, 5), False) == ("0105", "PM")

    face = ClockFace()
    face.update("0000", "")
    assert face.phase == [0.0, 0.0, 0.0, 0.0]
    face.update("0001", "")
    assert face.previous[3] == "0"
    assert face.digits[3] == "1"
    assert face.phase[3] > 0
    face.advance(1)
    face.advance(1.2)
    assert face.phase[3] > face.phase[0]
    face.advance(3)
    assert face.phase == [0.0, 0.0, 0.0, 0.0]

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 800, 280)
    cr = cairo.Context(surface)
    draw_face(cr, 800, 280, face, transparent_backdrop=False)
    face.phase[2] = 0.3
    face.previous[2] = "4"
    face.digits[2] = "5"
    draw_face(cr, 800, 280, face, transparent_backdrop=True)
    face.phase[2] = 0.75
    draw_face(cr, 800, 280, face, transparent_backdrop=False)
    print("ok")
    return 0


def _write_screenshot(path: str) -> int:
    face = ClockFace()
    face.update("1038", "")
    _write(path, face, 1280, 420, False)

    flip = ClockFace()
    flip.update("1038", "")
    flip.previous[3] = "7"
    flip.digits[3] = "8"
    flip.phase[3] = 0.32
    flip_path = path.rsplit(".", 1)
    second = f"{flip_path[0]}-flip.png" if len(flip_path) == 2 else path + "-flip"
    _write(second, flip, 1280, 420, False)

    widget = ClockFace()
    widget.update("1038", "PM")
    widget_path = f"{flip_path[0]}-widget.png" if len(flip_path) == 2 else path + "-widget"
    _write(widget_path, widget, 640, 250, True)
    print(path)
    print(second)
    print(widget_path)
    return 0


def _write(path: str, face: ClockFace, width: int, height: int, transparent: bool) -> None:
    clock = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    draw_face(cairo.Context(clock), width, height, face, transparent_backdrop=transparent)
    if not transparent:
        clock.write_to_png(path)
        return
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)
    cr.set_source_rgb(0.75, 0.78, 0.74)
    cr.paint()
    cr.set_source_surface(clock, 0, 0)
    cr.paint()
    surface.write_to_png(path)


if __name__ == "__main__":
    raise SystemExit(main())
