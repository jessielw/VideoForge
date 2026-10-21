"""Video encoder option names from each encoder's help, and the warning for one it doesn't list."""

from __future__ import annotations

import pytest

from videoforge.core.config import Tools
from videoforge.core.video import options
from videoforge.core.video.options import option_issues, parse_dashdash, parse_ffmpeg, used_options
from videoforge.core.video.settings import Encoder, EncoderSettings

X265_HELP = """\
x265 [INFO]: HEVC encoder version 4.3+22
Output Options:
-o/--output <filename>           Bitstream output file name
-D/--output-depth 8|10|12        Output bit depth (also internal bit depth). Default 8
   --level-idc <integer|float>   Force a minimum required decoder level (as '5.0' or '50')
   --[no-]high-tier              If a decoder level is specified, this modifier selects the High tier of that level
   --input-csp <string>          Chroma subsampling, auto-detected if Y4M
                                 0 - i400 (4:0:0 monochrome)
"""

X264_HELP = """\
      --preset <string>       Use a preset to select encoding settings [medium]
                                  - ultrafast:
                                    --no-8x8dct --aq-mode 0 --b-adapt 0
  -b, --bframes <integer>     Number of B-frames between I and P [3]
      --no-8x8dct             Disable adaptive spatial transform size
"""

SVT_HELP = """\
  -i, --input                      Input raw video (y4m and yuv) file path
      --film-grain                 Enable film grain, default is 0 [0: off, 1-50: level of denoising for film grain]
"""

FFMPEG_ENCODER_HELP = """\
Encoder libvpx-vp9 [libvpx VP9]:
libvpx-vp9 encoder AVOptions:
  -lag-in-frames     <int>        E..V....... Number of frames to look ahead (from -1 to INT_MAX) (default -1)
  -arnr-type         <int>        E..V....... altref noise reduction filter type (from -1 to INT_MAX) (default -1)
     backward        1            E..V.......
  -row-mt            <boolean>    E..V....... Row based multi-threading (default auto)
"""

FFMPEG_FULL_HELP = """\
Main options:
-f fmt              force container format (auto-detected otherwise)
-pix_fmt[:<stream_spec>] format  set pixel format
AVCodecContext AVOptions:
  -b                 <int64>      E..VA...... set bitrate (in bits/s) (from 0 to INT64_MAX) (default 200000)
  -g                 <int>        E..V....... set the group of picture (GOP) size (from INT_MIN to INT_MAX) (default 12)
  -ac                <int>        ED..A...... set number of audio channels (from 0 to INT_MAX) (default 0)
  -lowres            <int>        .D.VA...... decode at 1= 1/2, 2=1/4, 3=1/8 resolutions (from 0 to INT_MAX) (default 0)
amv encoder AVOptions:
  -mpv_flags         <flags>      E..V....... Flags common for all mpegvideo-based encoders. (default 0)
"""


def test_parse_dashdash():
    x265 = parse_dashdash(X265_HELP)
    assert set(x265) == {"output", "output-depth", "level-idc", "high-tier", "no-high-tier", "input-csp"}
    assert x265["level-idc"].startswith("<integer|float> Force a minimum")
    x264 = parse_dashdash(X264_HELP)
    assert set(x264) == {"preset", "bframes", "no-8x8dct"}  # not the preset list's options (a description)
    assert x264["no-8x8dct"] == "Disable adaptive spatial transform size"
    assert set(parse_dashdash(SVT_HELP)) == {"input", "film-grain"}


def test_parse_ffmpeg():
    own = parse_ffmpeg(FFMPEG_ENCODER_HELP, encoder_options=True)
    assert set(own) == {"lag-in-frames", "arnr-type", "row-mt"}  # not the "backward" value line
    assert own["row-mt"] == "Row based multi-threading (default auto)"
    full = parse_ffmpeg(FFMPEG_FULL_HELP, encoder_options=False)
    assert set(full) == {"f", "pix_fmt", "b", "g"}  # video encoding codec options; not another encoder's


def test_used_options():
    s = EncoderSettings(
        Encoder.X265, options={"--psy-rd": "2", "aq-mode": "3"}, extra='--no-sao --zones "0,100,q=20" -p 5'
    )
    assert used_options(s) == ["psy-rd", "aq-mode", "no-sao", "zones"]  # a short flag (-p) isn't checked
    vp9 = EncoderSettings(Encoder.VP9, options={"row-mt": "1"}, extra="-g 240 -b:v 0 -tile-columns 2 -1")
    assert used_options(vp9) == ["row-mt", "g", "b", "tile-columns"]


def test_option_issues(monkeypatch):
    known = {"psy-rd": "", "aq-mode": "", "no-sao": "", "level-idc": ""}
    monkeypatch.setattr(options, "known_options", lambda _encoder, _tools: known)
    tools = Tools("", "", "", "", "", "")
    s = EncoderSettings(Encoder.X265, options={"psy-rd": "2", "levle-idc": "5.1"}, extra="--no-sao --frobnicate")
    issues = option_issues(s, tools)
    assert [i.code for i in issues] == ["video.option_unknown"] * 2
    assert "--levle-idc: did you mean --level-idc?" in issues[0].message
    assert "--frobnicate: check its spelling." in issues[1].message
    assert option_issues(s, None) == []  # no tools: nothing to check against


def test_no_list_no_issues(tmp_path):
    """An encoder that isn't there (or lists nothing) checks nothing."""
    tools = Tools("", "", "", "", "", "", x265=str(tmp_path / "missing.exe"))
    assert option_issues(EncoderSettings(Encoder.X265, options={"anything": "1"}), tools) == []


@pytest.mark.parametrize("encoder", [Encoder.X264, Encoder.X265, Encoder.SVTAV1, Encoder.VP9])
def test_real_encoder_lists(encoder):
    """The configured encoders' own help, where they're installed."""
    from videoforge.core.config import load_app_config

    known = options.known_options(encoder, load_app_config().tools)
    if not known:
        pytest.skip(f"{encoder.label} isn't installed")
    common = {Encoder.X264: "bframes", Encoder.X265: "level-idc", Encoder.SVTAV1: "film-grain", Encoder.VP9: "row-mt"}
    assert common[encoder] in known and len(known) > 50
