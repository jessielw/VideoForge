"""A track's measure step for normalizing (core/execute/audio.py measure_argv): ffmpeg's volumedetect or
loudnorm's first pass, its findings written to a JSON file the encode step reads.

    python -m videoforge.core.execute.loudness <out.json> <duration_ms> <ffmpeg> <args...>

ffmpeg prints what it measured on its log, so this runs it and keeps that log: its other lines pass through,
its time= stats become "Progress: N%" lines (by the track's duration; none when that is 0). The JSON has
volumedetect's max_volume (dB) or loudnorm's input_i, input_tp, input_lra, input_thresh and target_offset;
a value ffmpeg gives as -inf (a silent track) is left out.
"""

from __future__ import annotations

import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import cast

_TIME = re.compile(r"\btime=(\d+):(\d\d):(\d\d(?:\.\d+)?)")
_MAX_VOLUME = re.compile(r"max_volume:\s*(-?[\d.]+|-?inf) dB")
_JSON = re.compile(r"\{[^{}]*\"input_i\"[^{}]*\}")
_LOUDNORM_KEYS = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")


def _number(text: str) -> float | None:
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def parse(log: str) -> dict[str, float] | None:
    """What volumedetect or loudnorm (print_format=json) printed; None when neither did."""
    if m := _MAX_VOLUME.search(log):
        value = _number(m.group(1))
        return {} if value is None else {"max_volume": value}
    if blocks := _JSON.findall(log):
        doc = json.loads(blocks[-1])
        values = {key: _number(str(doc.get(key, ""))) for key in _LOUDNORM_KEYS}
        return {key: v for key, v in values.items() if v is not None}
    return None


def read(path: Path) -> dict[str, float] | None:
    """A measure step's file; None when it isn't there (the step hasn't run)."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: python -m videoforge.core.execute.loudness <out.json> <duration_ms> <ffmpeg> <args...>")
        return 2
    out, duration_s, command = Path(argv[0]), int(argv[1]) / 1000, argv[2:]
    proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    reader = cast(io.BufferedReader, proc.stderr)  # Popen's pipes are buffered readers
    lines: list[str] = []
    shown = -1
    pending = b""
    while chunk := reader.read1(65536):
        *done, pending = re.split(rb"\r\n|\r|\n", pending + chunk)
        for raw in done:
            line = raw.decode("utf-8", errors="replace")
            if m := _TIME.search(line):  # the stats line, rewritten many times a second
                if duration_s > 0:
                    pct = min(int((int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])) / duration_s * 100), 100)
                    if pct > shown:
                        shown = pct
                        print(f"Progress: {pct}%", flush=True)
                continue
            lines.append(line)
            if line.strip():
                print(line, flush=True)
    if pending.strip():
        lines.append(pending.decode("utf-8", errors="replace"))
        print(lines[-1], flush=True)
    if code := proc.wait():
        return code
    found = parse("\n".join(lines))
    if found is None:
        print("ffmpeg printed no measurement")
        return 1
    part = out.with_name(out.name + ".partial")
    part.write_text(json.dumps(found), encoding="utf-8")
    os.replace(part, out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
