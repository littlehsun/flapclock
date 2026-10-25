"""Time formatting and per-digit flap state."""

from __future__ import annotations

from datetime import datetime

FLIP_SECONDS = 0.58


def format_digits(when: datetime, hour24: bool) -> tuple[str, str]:
    """Return four hour/minute digits and an AM/PM suffix.

    The suffix is empty in 24-hour mode. Twelve-hour mode keeps a leading
    zero so the flap layout never changes width.
    """
    if hour24:
        return f"{when.hour:02d}{when.minute:02d}", ""
    suffix = "AM" if when.hour < 12 else "PM"
    hour = when.hour % 12
    if hour == 0:
        hour = 12
    return f"{hour:02d}{when.minute:02d}", suffix


class ClockFace:
    """Four flaps. A phase of 0 means the digit is resting on `digits`."""

    def __init__(self) -> None:
        self.digits = ["0", "0", "0", "0"]
        self.previous = ["0", "0", "0", "0"]
        self.phase = [0.0, 0.0, 0.0, 0.0]
        self.suffix = ""
        self.ready = False
        self._last = 0.0

    def update(self, digits: str, suffix: str) -> None:
        if len(digits) != 4 or any(not ch.isdigit() for ch in digits):
            raise ValueError(f"expected four digits, got {digits!r}")
        self.suffix = suffix
        if not self.ready:
            self.digits = list(digits)
            self.previous = list(digits)
            self.phase = [0.0, 0.0, 0.0, 0.0]
            self.ready = True
            return
        for index, char in enumerate(digits):
            if self.phase[index] > 0:
                continue
            if char != self.digits[index]:
                self.previous[index] = self.digits[index]
                self.digits[index] = char
                self.phase[index] = 0.0001

    def advance(self, now: float) -> None:
        if self._last <= 0:
            self._last = now
            return
        dt = now - self._last
        self._last = now
        if dt <= 0:
            return
        if dt > 0.5:
            self.phase = [0.0, 0.0, 0.0, 0.0]
            return
        step = dt / FLIP_SECONDS
        for index, phase in enumerate(self.phase):
            if phase <= 0:
                continue
            phase += step
            self.phase[index] = 0.0 if phase >= 1 else phase

    @property
    def animating(self) -> bool:
        return any(phase > 0 for phase in self.phase)
