"""core.disks.low_space: the free-space check a queued run makes before its first step."""

from __future__ import annotations

from collections import namedtuple

from videoforge.core import disks
from videoforge.core.disks import GB, low_space

Usage = namedtuple("Usage", "total used free")


def test_low_space_reads_the_nearest_existing_folder_once_per_volume(tmp_path, monkeypatch):
    looked: list[str] = []

    def usage(path):
        looked.append(str(path))
        return Usage(0, 0, 5 * GB)

    monkeypatch.setattr(disks.shutil, "disk_usage", usage)
    work, out = tmp_path / "Show.mkv_tmp" / "main", tmp_path / "out"  # neither exists yet
    assert low_space([work, out], 0) == ""  # off
    assert looked == []
    assert low_space([work, out], 4) == ""
    assert looked == [str(tmp_path)]  # one volume: looked at once
    short = low_space([work, out], 20)
    assert short.startswith(f"Only 5.0 GB free on the disk of {work}, under the 20 GB minimum")


def test_low_space_passes_a_volume_it_cant_read(tmp_path, monkeypatch):
    def usage(path):
        raise OSError("gone")

    monkeypatch.setattr(disks.shutil, "disk_usage", usage)
    assert low_space([tmp_path], 20) == ""
