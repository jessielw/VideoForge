"""Audio encode commands for a planned track (DeeZy for DDP/Atmos, ffmpeg | qaac for AAC).

Delay: the source's "delay relative to video" is applied exactly once. DeeZy
never reads it from the container (only from --delay or a "DELAY Xms" file name
token), so we pass it explicitly; DeeZy bakes it into the stream (padding or
trimming, plus DEE's own priming) and the output starts at 0. ffmpeg | qaac
starts at the first audio sample, so AAC gets the delay at mux (mkvmerge --sync).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from videoforge.core.config import Tools
from videoforge.core.models import AudioAction, PlannedAudio

_SUFFIX = {AudioAction.DDP: ".ec3", AudioAction.ATMOS: ".ec3", AudioAction.AAC: ".m4a"}


def delay_in_encode(action: AudioAction) -> bool:
    """True when the encoder applies the source delay itself, so the mux must not."""
    return action in (AudioAction.DDP, AudioAction.ATMOS)


@dataclass(frozen=True, slots=True)
class AudioSettings:
    """Encoder knobs a profile sets once (per-track choices live on PlannedAudio)."""

    atmos_mode: str = "streaming"
    qaac_tvbr: int = 127
    deezy_extra_args: tuple[str, ...] = ()
    qaac_extra_args: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AudioCommand:
    """One encode. With two argvs, the first one's stdout is piped into the second."""

    planned: PlannedAudio
    output: Path
    argvs: tuple[tuple[str, ...], ...]


def output_path(planned: PlannedAudio, position: int, temp_dir: Path) -> Path:
    return temp_dir / f"audio{position}_{planned.language}{_SUFFIX[planned.action]}"


def _deezy(planned: PlannedAudio, source: Path, output: Path, temp_dir: Path, settings: AudioSettings, tools: Tools) -> tuple[str, ...]:
    track = planned.source
    common = (
        f"--track-index={track.index}",
        f"--delay={track.delay_ms}ms",
        f"--bitrate={planned.bitrate_kbps}",
        "--output", str(output),
        "--temp-dir", str(temp_dir / "deezy"),
        "--overwrite",
        "--ffmpeg", tools.ffmpeg,
        "--dee", tools.dee,
        "--truehdd", tools.truehdd,
    )
    if planned.action is AudioAction.ATMOS:
        mode = ("encode", "atmos", f"--atmos-mode={settings.atmos_mode}")
    else:
        mode = ("encode", "ddp", f"--channels={planned.out_layout.channels}")
        if planned.upmix_50:
            mode += ("--upmix-50-to-51",)
    return (tools.deezy, *mode, *common, *settings.deezy_extra_args, str(source))


def _aac(planned: PlannedAudio, source: Path, output: Path, settings: AudioSettings, tools: Tools) -> tuple[tuple[str, ...], ...]:
    # Float WAV so a lossless 24-bit source isn't truncated and a downmix can't clip.
    ffmpeg = (
        tools.ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error",
        "-i", str(source),
        "-map", f"0:a:{planned.source.index}",
        "-ac", str(planned.out_layout.channels),
        "-c:a", "pcm_f32le", "-f", "wav", "-",
    )
    # --ignorelength: a piped WAV header has no real data size.
    # --no-delay: compensate encoder priming in the stream itself; MKV has no gapless metadata.
    # A bitrate means constrained VBR at about that rate; none means true VBR at the profile's quality.
    mode = ("--cvbr", str(planned.bitrate_kbps)) if planned.bitrate_kbps else ("--tvbr", str(settings.qaac_tvbr))
    qaac = (
        tools.qaac, *mode, "--ignorelength", "--no-delay", "--threading",
        *settings.qaac_extra_args, "-o", str(output), "-",
    )
    return ffmpeg, qaac


def audio_command(
    planned: PlannedAudio, position: int, source: Path, temp_dir: Path, settings: AudioSettings, tools: Tools
) -> AudioCommand | None:
    """The encode for one planned track, or None when it is copied from the source."""
    if planned.action is AudioAction.COPY:
        return None
    output = output_path(planned, position, temp_dir)
    if planned.action is AudioAction.AAC:
        argvs = _aac(planned, source, output, settings, tools)
    else:
        argvs = (_deezy(planned, source, output, temp_dir, settings, tools),)
    return AudioCommand(planned, output, argvs)
