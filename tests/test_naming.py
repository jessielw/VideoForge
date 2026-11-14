"""Output names from a name template (core/naming.py), the suffix, and the MKV title."""

from __future__ import annotations

from pathlib import Path

from conftest import audio, plan_for, source
import pytest

from videoforge.core import naming
from videoforge.core.execute.mux import MuxSettings, mux_command
from videoforge.core.job import JobSpec
from videoforge.core.models import AudioAction, AudioCodec as C, JobInputs, Layout, Severity, VideoInfo
from videoforge.core.pipeline.build import output_path
from videoforge.core.plan_io import from_json, to_json
from videoforge.core.video.settings import Crop, Encoder
from videoforge.rule_sets.manual import ManualRuleSet

ABYSS = "MADE IN ABYSS - Journey's Dawn 2019 1080p BluRay Hybrid-REMUX AVC DTS HD MA 5.1 Dual Audio -ZR-.mkv"


def job(name: str = ABYSS, **mux) -> tuple[JobSpec, object]:
    src = source([audio(C.DTS_HD_MA, "5.1", "ja"), audio(C.AC3, "2.0", "en", index=1)], name=name)
    plan = plan_for(src)
    spec = JobSpec(inputs=JobInputs(Path(name)), rule_set="manual", mux=MuxSettings(**mux))
    return spec, plan


def out(spec, plan) -> str:
    return output_path(spec, plan, ManualRuleSet(), Path()).name


@pytest.mark.parametrize(
    ("template", "want"),
    [
        ("{title} {release_year} {edition} {resolution}", "Movie 2019 1080p"),  # an empty token takes its space
        ("{title}{:opt=-:edition} {resolution}", "Movie 1080p"),
        ("{title}{:opt=-:resolution}", "Movie-1080p"),
        ("{title}{:opt= (:release_year:opt=):}", "Movie (2019)"),
        ("{title}{:opt= (:edition:opt=):}", "Movie"),
        ("{title|upper} {resolution}", "MOVIE 1080p"),
        ("{title|dots}.{release_year}.{edition|dots}.{resolution}", "Movie.2019.1080p"),
        ("{title} {nope}", "Movie {nope}"),  # unknown: as typed
        ("{edition} - {title} -", "Movie"),  # the ends trimmed
    ],
)
def test_render(template, want):
    values = {"title": "Movie", "release_year": "2019", "edition": "", "resolution": "1080p"}
    assert naming.render(template, values) == want


def test_dots_keeps_hyphenated_words():
    assert naming.render("{title|dots}", {"title": "Spider-Man - Far Home"}) == "Spider-Man.Far.Home"


@pytest.mark.parametrize(
    ("name", "want"),
    [
        (
            ABYSS.removesuffix(".mkv"),
            {"title": "MADE IN ABYSS - Journey's Dawn", "release_year": "2019", "hybrid": "Hybrid", "source": "BluRay"},
        ),
        (
            "Not.Another.Teen.Movie.2001.DC.1080p.BluRay.Remux.AVC.DTS-HD.MA.5.1-GRP",
            {"title": "Not Another Teen Movie", "edition": "Director's Cut", "hybrid": ""},
        ),
        (
            "The.Expanse.S02E05.Home.2160p.UHD.BluRay.REMUX.HDR.HEVC.Atmos-EPSiLON",
            {"title": "The Expanse", "season_episode": "S02E05", "episode_title": "Home", "source": "UHD BluRay"},
        ),
        ("Show.Name.S01E02.1080p.WEB-DL.DDP5.1.H.264-GRP", {"source": "WEB-DL", "release_year": ""}),
        ("Movie.Title.2010.Extended.Cut.1080p.WEBRip.x264", {"source": "WEBRip", "edition": "Extended"}),
    ],
)
def test_name_tokens(name, want):
    got = naming.name_tokens(name)
    assert {k: got[k] for k in want} == want
    assert got["original_filename"] == name


def test_clean_title():
    assert naming.name_tokens("Amélie & Co's Day 2001 1080p BluRay")["title_clean"] == "Amelie and Cos Day"


@pytest.mark.parametrize(
    ("size", "want"),
    [((1920, 1080), "1080p"), ((1920, 800), "1080p"), ((3840, 1600), "2160p"), ((1280, 536), "720p")]
    + [((720, 576), "576p"), ((720, 480), "480p"), ((2560, 1440), "1440p")],
)
def test_resolution_class(size, want):
    assert naming.resolution_class(*size) == want


def test_tokens_from_what_the_job_makes():
    """The output's codecs, not the source's: the plan's first audio output and the job's encoder."""
    spec, plan = job()
    first = plan.audio[0]
    first.action, first.out_codec, first.out_layout = AudioAction.DDP, C.EAC3, Layout(5, 1)
    spec.encoder.encoder, spec.encoder.depth = Encoder.X265, 10
    got = naming.tokens(spec, plan)
    assert (got["audio_codec"], got["audio_channel_s"], got["atmos"]) == ("DDP", "5.1", "")
    assert (got["video_codec"], got["video_format"], got["video_bit_depth_dash"]) == ("x265", "HEVC", "10-Bit")
    assert (got["video_dynamic_range"], got["video_dynamic_range_type"]) == ("SDR", "")


def test_resolution_follows_the_crop_and_resize():
    spec, plan = job()
    plan.source.video = VideoInfo(3840, 2160)
    spec.video.crop = Crop(top=280, bottom=280)
    assert naming.tokens(spec, plan)["resolution"] == "2160p"
    from videoforge.core.video.settings import Resize

    spec.video.resize = Resize(1920, 800)
    assert naming.tokens(spec, plan)["resolution"] == "1080p"


def test_hdr_the_encode_carries():
    spec, plan = job()
    video = plan.source.video
    video.color.transfer = "smpte2084"
    video.hdr.dv_profile, video.hdr.hdr10plus = 8, True
    spec.encoder.encoder = Encoder.X265
    assert naming.tokens(spec, plan)["video_dynamic_range_type"] == "DV HDR10+"
    spec.encoder.dolby_vision = spec.encoder.hdr10plus = False
    assert naming.tokens(spec, plan)["video_dynamic_range_type"] == "HDR"
    assert naming.tokens(spec, plan)["video_dynamic_range"] == "HDR"


def test_atmos_from_the_output_track():
    spec, plan = job()
    plan.audio[0].out_codec, plan.audio[0].out_atmos = C.TRUEHD, True
    assert naming.tokens(spec, plan)["atmos"] == "Atmos"


def test_a_reused_encode_is_named_by_its_extension():
    spec, plan = job()
    spec.inputs.encode = Path("Movie_out.hevc")
    got = naming.tokens(spec, plan)
    assert (got["video_codec"], got["video_bit_depth_dash"]) == ("x265", "")


def test_output_name_default_is_unchanged():
    spec, plan = job()
    assert out(spec, plan) == ABYSS


def test_suffix_and_label():
    spec, plan = job(name_suffix=".vf")
    assert out(spec, plan) == ABYSS.removesuffix(".mkv") + ".vf.mkv"
    spec.label = "dubbed"
    assert out(spec, plan) == ABYSS.removesuffix(".mkv") + ".dubbed.vf.mkv"


def test_template_names_the_file():
    spec, plan = job(template_file_name=True, name_suffix="vf")
    assert out(spec, plan) == "MADE IN ABYSS - Journey's Dawn 2019 Hybrid 1080p BluRay DTS-HD MA 5.1 x264.vf.mkv"
    spec.mux.name_template = "{title}: {release_year}-GRP"  # made a file name
    assert out(spec, plan) == "MADE IN ABYSS - Journey's Dawn 2019-GRP.vf.mkv"
    spec.output_name = "Typed"  # a name typed for the job wins
    assert out(spec, plan) == "Typed.vf.mkv"


def test_an_empty_render_falls_back_to_the_source_name():
    spec, plan = job(template_file_name=True, name_template="{edition}")
    assert out(spec, plan) == ABYSS


def test_title_only_when_asked():
    spec, plan = job(name_template="{title} {release_year}")
    assert naming.title(spec, plan) == ""
    spec.mux.template_title = True
    assert naming.title(spec, plan) == "MADE IN ABYSS - Journey's Dawn 2019"
    assert out(spec, plan) == ABYSS  # the file keeps its name


def test_mkvmerge_writes_the_title():
    _, plan = job()
    plan.encode_path = Path("video.h264")
    plan.source.video.default_duration_ns = 41708333
    argv = mux_command(plan, {}, Path("out.mkv"), "mkvmerge", (".h264",), title="Movie 2019")
    assert argv[argv.index("--title") + 1] == "Movie 2019"
    argv = mux_command(plan, {}, Path("out.mkv"), "mkvmerge", (".h264",))
    assert argv[argv.index("--title") + 1] == ""


def test_unknown_tokens_and_filters_warn_when_the_template_is_used():
    spec, _ = job(name_template="{title|shout} {bogus}")
    assert naming.issues(spec) == []
    spec.mux.template_file_name = True
    assert [(i.severity, i.code) for i in naming.issues(spec)] == [
        (Severity.WARN, "name.filter"),
        (Severity.WARN, "name.token"),
    ]


def test_saved_mux_settings_without_naming_load():
    """Jobs and templates saved before naming: the new fields take their defaults."""
    got = from_json(MuxSettings, {"container": "mkv", "extra": "", "pgs_zlib": True})
    assert got == MuxSettings(container="mkv", pgs_zlib=True)
    assert from_json(MuxSettings, to_json(MuxSettings(name_template="{title}", template_title=True))).template_title


def test_name_tokens_endpoint(tmp_path):
    from test_server import make_client

    got = make_client(tmp_path).get("/api/name-tokens").json()
    assert got["default_template"] == naming.DEFAULT_TEMPLATE
    assert {t["name"] for t in got["tokens"]} == {t.name for t in naming.TOKENS}
    assert set(got["filters"]) == {"upper", "lower", "dots"}


@pytest.mark.parametrize(
    ("policy", "templates", "want"),
    [
        (naming.NamePolicy(), (True, False), (True, False)),  # as the template says
        (naming.NamePolicy(naming.NameUse.OFF, naming.NameUse.ON), (True, False), (False, True)),
        (naming.NamePolicy(naming.NameUse.ON), (False, True), (True, True)),
    ],
)
def test_name_policy(policy, templates, want):
    mux = MuxSettings(extra="-x", template_file_name=templates[0], template_title=templates[1])
    got = policy.apply(mux)
    assert (got.template_file_name, got.template_title) == want and got.extra == "-x"


def test_settings_name_policies(tmp_path):
    """Settings' word wins over a template's where a job takes the template (added, a template applied); the
    job's own edit still wins over Settings."""
    from test_server import add, make_client, make_files, wait_for

    make_files(tmp_path)
    named = to_json(MuxSettings(template_file_name=True, template_title=True))
    with make_client(tmp_path) as client:
        put = lambda naming: client.put("/api/config", json={"naming": naming})
        assert put({"manual": {"file_name": "maybe"}}).status_code == 422
        assert put({"manual": {"name": "on"}}).status_code == 422
        r = put({"manual": {"file_name": "off"}, "other": {"file_name": "template", "title": "template"}})
        assert r.json()["naming"] == {"manual": {"file_name": "off", "title": "template"}}  # "as templates": dropped
        assert client.get("/api/config").json()["naming"] == {"manual": {"file_name": "off", "title": "template"}}

        (job,) = add(client, tmp_path, template={"mux": named})
        mux = wait_for(client, job, "ready", "warn", "blocked")["spec"]["mux"]
        assert (mux["template_file_name"], mux["template_title"]) == (False, True)

        # the job's own switch: kept
        client.patch(f"/api/jobs/{job}", json={"mux": mux | {"template_file_name": True}})
        assert client.get(f"/api/jobs/{job}").json()["spec"]["mux"]["template_file_name"] is True
        # a template applied again: Settings' word again
        client.patch(f"/api/jobs/{job}", json={"template": {"mux": named}})
        assert client.get(f"/api/jobs/{job}").json()["spec"]["mux"]["template_file_name"] is False

        put({})  # back to what each template says
        client.patch(f"/api/jobs/{job}", json={"template": {"mux": named}})
        assert client.get(f"/api/jobs/{job}").json()["spec"]["mux"]["template_file_name"] is True
