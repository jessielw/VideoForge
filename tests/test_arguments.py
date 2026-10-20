import json
from pathlib import Path
import subprocess
import sys

import pytest

from videoforge.core.arguments import split_args
from videoforge.core.video.encoders import encoder_command, level_vbv
from videoforge.core.video.settings import Encoder, EncoderSettings


@pytest.mark.parametrize(
    "values",
    [
        ["--title", "Director Cut", "--chapters", r"C:\My Clips\chapters.txt"],
        ["", "has spaces\\", 'embedded "quote"', r"\\server\share\file", "O'Brien"],
        ["--name=two words", r"C:\plain\path", "|", "&", "$HOME", "#literal"],
    ],
)
def test_extra_arguments_roundtrip_through_a_real_child(values):
    parsed = split_args(subprocess.list2cmdline(values))
    assert parsed == values
    result = subprocess.run(
        [sys.executable, "-c", "import json,sys; print(json.dumps(sys.argv[1:]))", *parsed],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == values


def test_embedded_quotes_and_empty_values():
    assert split_args('--name="two words" --empty="" --text "say ""yes"""') == [
        "--name=two words",
        "--empty=",
        "--text",
        'say "yes"',
    ]
    with pytest.raises(ValueError, match="Unclosed"):
        split_args('--path "unfinished')


@pytest.mark.parametrize("encoder", list(Encoder))
def test_every_video_encoder_uses_the_shared_parser(encoder):
    settings = EncoderSettings(encoder=encoder, extra='--example "C:\\My Clips\\file.txt"')
    argv = encoder_command("encoder", settings, output=Path("output"))
    assert argv[argv.index("--example") + 1] == r"C:\My Clips\file.txt"


def test_quoted_values_are_used_for_derived_flags():
    settings = EncoderSettings(encoder=Encoder.X265, extra='--level-idc "5.1" --vbv-maxrate "12000"')
    assert level_vbv(settings) == ["--vbv-bufsize", "160000"]


def test_audio_extra_arguments_use_the_shared_parser():
    from test_execute_audio import A, C, command, planned

    audio = planned(C.FLAC, "2.0", A.AAC)
    audio.options = {"extra": '--tag "title:Director Cut"'}
    argv = command(audio).argvs[-1]
    assert argv[argv.index("--tag") + 1] == "title:Director Cut"
