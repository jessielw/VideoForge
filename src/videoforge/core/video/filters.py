"""The built-in filter presets: one click puts a filter in the chain (VideoSettings.filters) at its category's place.

Each uses only the plugins and filter scripts VideoForge ships (vsplugins/manifest.toml and the `filters`
extra), so every one runs as it is. A filter's variants (strengths, widths) are separate presets of one family
("BM3D" Light, Medium, Strong): picking another of a family already in the chain swaps it in place. The script
is plain VapourSynth on `clip`, so a step can be edited after it's added.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import re

from videoforge.core.models import Issue, Severity, VideoInfo
from videoforge.core.video.fieldscan import FieldScan, Verdict, step_name
from videoforge.core.video.settings import FilterCategory, FilterStep, SourceFilter, VideoSettings

C = FilterCategory
_ORDER = {"TFF": "top field first", "BFF": "bottom field first"}
# VFM, Bwdif and QTGMC take the field order from the frames' _FieldBased tag (the source filter's, from the stream)
# over their own argument, which only counts for frames tagged progressive or not at all. So the field presets
# follow the source, and carry this line, commented out, to override a source flagged with the wrong order.
_OVERRIDE_ORDER = (
    "# clip = core.std.SetFieldBased(clip, 2)  # overrides the source's field order: 2 top first, 1 bottom first\n"
)


def field_issues(video: VideoInfo | None, settings: VideoSettings, scan: FieldScan | None = None) -> list[Issue]:
    """An interlaced source with no field step in the chain: the encode would keep its combing. StaxRip shows
    the scan type and leaves it to the user; this says so before the run. A custom body isn't read (it may
    deinterlace in its own lines). With the source's field scan (core/video/fieldscan.py), what it found instead
    of MediaInfo's scan type: no warning for progressive video stored as fields, the chain that fits, a Field step
    of the wrong kind, and a field order the step would get wrong (_scan_issues).

    Pulldown (soft telecine): applying it needs a source filter that can (FFMS2 can't: blocked). Applied, the film
    comes out telecined, which combs like an interlaced source without a field step. Not applied while an IVTC
    decimates, the soft-telecined parts reach VDecimate as film frames already, so it can drop real ones."""
    out: list[Issue] = []
    if settings.pulldown and not settings.source_filter.applies_pulldown:
        out.append(
            Issue(
                Severity.BLOCK,
                "video.pulldown_filter",
                "FFMS2 can't apply pulldown flags. Pick BestSource or L-SMASH Works as the Source filter (Video tab, "
                "Advanced), or turn off Apply pulldown",
            )
        )
    if video is None or settings.custom is not None:
        return out
    field_steps = [s for s in settings.filters if s.category is C.FIELD and s.enabled]
    if scan is not None and scan.verdict is not Verdict.UNKNOWN:
        out += _scan_issues(scan, video, settings, field_steps)
    elif video.interlaced and not field_steps:
        how = ", ".join(
            x
            for x in (video.scan_type if video.scan_type != "Interlaced" else "", _ORDER.get(video.scan_order, ""))
            if x
        )
        out.append(
            Issue(
                Severity.WARN,
                "video.interlaced",
                f"The source is interlaced{f' ({how})' if how else ''}, and the filter chain doesn't deinterlace it. "
                "Add IVTC (for telecined film) or a deinterlacer (QTGMC, Bwdif) from the Field filters, or check the "
                "preview for combing first. Some progressive video is stored as interlaced",
            )
        )
    elif video.pulldown and settings.pulldown and not field_steps:
        out.append(
            Issue(
                Severity.WARN,
                "video.interlaced",
                f"Apply pulldown repeats the source's fields as a player shows them ({video.scan_order}), so its film "
                "frames come out telecined and comb. Add IVTC from the Field filters to match them back into film "
                "frames, or turn off Apply pulldown",
            )
        )
    if video.pulldown and not settings.pulldown and any("VDecimate" in s.script for s in field_steps):
        out.append(
            Issue(
                Severity.WARN,
                "video.pulldown",
                f"The source has pulldown flags ({video.scan_order}) and the IVTC decimates, but Apply pulldown is "
                "off. The source's soft-telecined parts then reach VDecimate as film frames already, and it can drop "
                "real ones. Turn on Apply pulldown (Video tab, Advanced; BestSource or L-SMASH Works), or remove the "
                "IVTC if no part of the source is telecined for real",
            )
        )
    return out


_DEINTERLACERS = ("Bwdif", "QTGMC", "nnedi3", "eedi3", "Yadif", "TDeint")
# An override line, as the presets and the scan's chain have it: unindented (QTGMC's preset sets an order only on
# frames that carry none, in an if)
_SET_ORDER = re.compile(r"^clip\s*=\s*core\.std\.SetFieldBased\(\s*clip\s*,\s*([012])\s*\)", re.MULTILINE)
_TAGS = {"tff": 2, "bff": 1}
_TAG_NAMES = {0: "progressive", 1: "bottom field first", 2: "top field first"}
# Bottom field first given to the filter itself (it counts when the frames carry no order): VFM's, Bwdif's, QTGMC's
_BOTTOM_ARGS = re.compile(r"order\s*=\s*0|field\s*=\s*[02]\b|TFF\s*=\s*False")


def _found(scan: FieldScan) -> str:
    return f"{scan.verdict.label.lower()}, {_TAG_NAMES[_TAGS[scan.order]]}"


def _fix_text(scan: FieldScan, video: VideoInfo, settings: VideoSettings) -> str:
    what = {
        Verdict.TELECINE: "IVTC (VFM + VDecimate) matches the fields back into film frames",
        Verdict.SHIFTED: "VFM matches the fields back into whole frames and drops none",
        Verdict.HYBRID: f"IVTC, with QTGMC on the {scan.fallback} frames field matching leaves combed",
        Verdict.INTERLACED: "Bwdif deinterlaces it",
    }[scan.verdict]
    pulldown = ", which also turns on Apply pulldown" if video.pulldown and not settings.pulldown else ""
    return f"Apply the scan's chain (Video tab, Scan){pulldown}: {what}"


def _scan_issues(scan: FieldScan, video: VideoInfo, settings: VideoSettings, steps: list[FilterStep]) -> list[Issue]:
    """What the field scan says of the chain's Field steps: none needed (progressive), none there, the wrong kind
    (deinterlacing film, field matching video, decimating a source that repeats no frames, no fallback for the
    frames matching leaves combed), or the right kind at the wrong field order."""
    text = "\n".join(s.script for s in steps)
    v = scan.verdict
    if v is Verdict.PROGRESSIVE:
        if not steps:
            return []
        if "VDecimate" in text:
            harm = "its VDecimate drops real frames"
        elif any(d in text for d in _DEINTERLACERS):
            harm = "it softens the picture"
        else:
            harm = "it may change the picture"
        stored = " (it's stored as fields, but each frame is whole)" if video.interlaced else ""
        return [
            Issue(
                Severity.WARN,
                "video.field_unneeded",
                f"The field scan found no combing{stored}, so the Field filter isn't needed, and {harm}. Remove it",
            )
        ]
    found, fix = f"The field scan found {_found(scan)}", _fix_text(scan, video, settings)
    if not steps:
        return [
            Issue(
                Severity.WARN,
                "video.field",
                f"{found}, and the filter chain has no Field filter, so the encode would keep its combing. {fix}",
            )
        ]
    matches, decimates = "VFM" in text, "VDecimate" in text
    kind = ""
    if v in (Verdict.TELECINE, Verdict.HYBRID) and not matches:
        kind = "the Field filter deinterlaces it, which halves the film's detail where IVTC restores whole frames"
    elif v is Verdict.INTERLACED and matches:
        kind = "the Field filter field-matches it: video's fields are each their own moment, so it stays combed"
        kind += " and VDecimate drops real frames" if decimates else ""
    elif v is Verdict.SHIFTED and decimates:
        kind = "the Field filter decimates it: the source repeats no frames, so VDecimate drops real ones"
    elif v is Verdict.TELECINE and not decimates:
        kind = "the Field filter has no VDecimate, so a repeated frame stays in every 5"
    elif v is Verdict.HYBRID and not any(d in text for d in _DEINTERLACERS):
        kind = f"field matching leaves {scan.fallback} frames combed, and the Field filter has no deinterlacer for them"
    if kind:
        return [Issue(Severity.WARN, "video.field_kind", f"{found}, but {kind}. {fix}")]
    want = _TAGS[scan.order]
    if sets := _SET_ORDER.findall(text):
        given = int(sets[-1])
        if given == want:
            return []
        said = f"the Field filter sets {_TAG_NAMES[given]}"
    elif scan.stream_order in _TAGS:
        if scan.stream_order == scan.order:
            return []
        said = f"the stream is flagged {_TAG_NAMES[_TAGS[scan.stream_order]]}, and the Field filter follows the flag"
    elif (scan.order == "bff") != bool(_BOTTOM_ARGS.search(text)):
        # No order on the frames: the filter's own argument counts (the presets': top field first)
        said = "the source gives no field order, and the Field filter's own is the other one"
    else:
        return []
    return [
        Issue(
            Severity.WARN,
            "video.field_order",
            f"{found}, but {said}. Set the step's override line to clip = core.std.SetFieldBased(clip, {want}), or "
            "apply the scan's chain (Video tab, Scan)",
        )
    ]


@dataclass(frozen=True, slots=True)
class FieldFix:
    """What the field scan's Apply sets: its chain as the only Field step (none for progressive video), and for a
    source with pulldown flags Apply pulldown on (the scan's frames), on a source filter that can (BestSource,
    whose index the scan made, in place of FFMS2)."""

    step: FilterStep | None
    pulldown: bool
    source_filter: SourceFilter

    def applied(self, settings: VideoSettings) -> bool:
        have = [s.script for s in settings.filters if s.category is C.FIELD]
        return (
            have == ([self.step.script] if self.step else [])
            and settings.pulldown == self.pulldown
            and settings.source_filter is self.source_filter
        )

    def apply(self, settings: VideoSettings) -> VideoSettings:
        """The settings with the fix: the Field steps out, its step first (Field comes first in the chain)."""
        rest = [s for s in settings.filters if s.category is not C.FIELD]
        return replace(
            settings,
            filters=([self.step] if self.step else []) + rest,
            pulldown=self.pulldown,
            source_filter=self.source_filter,
        )


def field_fix(scan: FieldScan | None, video: VideoInfo | None, settings: VideoSettings) -> FieldFix | None:
    """The scan's Apply for a job's settings; None without a verdict."""
    if scan is None or scan.verdict is Verdict.UNKNOWN:
        return None
    step = FilterStep(C.FIELD, step_name(scan.verdict), scan.chain) if scan.chain else None
    pulldown = settings.pulldown or bool(step is not None and video is not None and video.pulldown)
    source_filter = settings.source_filter
    if pulldown and not source_filter.applies_pulldown:
        source_filter = SourceFilter.BESTSOURCE
    return FieldFix(step, pulldown, source_filter)


@dataclass(frozen=True, slots=True)
class FilterPreset:
    category: FilterCategory
    family: str  # the filter, as the menu labels it
    variant: str  # "Light", "1 px", ...; "" for a filter with just the one
    script: str
    description: str = ""
    fill_in: bool = False  # added with its lines open, for values to be typed in (an Empty variant, Custom)
    name: str = field(init=False)  # the step's name in the chain: family and variant

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", f"{self.family} {self.variant}".strip())

    def step(self) -> FilterStep:
        return FilterStep(self.category, self.name, self.script)


def _variants(
    category: FilterCategory, family: str, script: str, values: dict[str, str], description: str
) -> list[FilterPreset]:
    """One preset per variant: script with each {} replaced by that variant's arguments. An "Empty" variant
    (every value 0) opens its lines to fill in, e.g. to fix one side only."""
    return [
        FilterPreset(category, family, v, script.replace("{}", args), description, fill_in=v == "Empty")
        for v, args in values.items()
    ]


PRESETS: list[FilterPreset] = [
    # Field: before the crop, which could otherwise shift the fields.
    FilterPreset(
        C.FIELD,
        "IVTC (VIVTC)",
        "",
        _OVERRIDE_ORDER
        + "clip = core.vivtc.VFM(clip, order=1)  # order if the source has none: 1 top first, 0 bottom\n"
        "clip = core.vivtc.VDecimate(clip)",
        "Telecined film back to 23.976 fps (8-bit sources)",
    ),
    *_variants(
        C.FIELD,
        "QTGMC",
        "import havsfunc\n"
        + _OVERRIDE_ORDER
        + "if '_FieldBased' not in clip.get_frame(0).props:  # QTGMC can't run without a field order\n"
        "    clip = core.std.SetFieldBased(clip, 2)\n"
        "clip = havsfunc.QTGMC(clip, TFF=True, Preset={}, FPSDivisor=2)"
        "  # TFF only counts where the source gives no order; FPSDivisor=1: double rate",
        {"Fast": "'Fast'", "Medium": "'Medium'", "Slower": "'Slower'"},
        "Deinterlace, same frame rate",
    ),
    FilterPreset(
        C.FIELD,
        "Bwdif",
        "",
        _OVERRIDE_ORDER
        + "clip = core.bwdif.Bwdif(clip, field=1)  # field if the source has none: 1 top first, 0 bottom",
        "Quick deinterlace, same frame rate",
    ),
    FilterPreset(
        C.FIELD,
        "QTGMC Repair",
        "",
        "import havsfunc\nclip = havsfunc.QTGMC(clip, Preset='Slower', InputType=1)",
        "Clean up shimmer and combing left in progressive video",
    ),
    # Subtitle: a text subtitle file drawn on the cropped picture (a track burned in from the track editor
    # is placed by core.video.burn; an image subtitle goes there, before the crop).
    FilterPreset(
        C.SUBTITLE,
        "Burn in subtitles",
        "",
        "clip = core.sub.TextFile(clip, file=r'')  # an SRT or ASS file; style='...' restyles an SRT",
        "Draws an SRT or ASS file on the video (SubText). For PGS, burn a track in from the Subtitles tab",
        fill_in=True,
    ),
    # Restoration
    *_variants(
        C.RESTORATION,
        "EdgeFixer",
        "clip = core.edgefixer.Continuity(clip, left={}, top={}, right={}, bottom={}, radius=0)",
        {"1 px": "1", "2 px": "2", "Empty": "0"},
        "Fix dirty lines at the frame's edges, using the next good row or column as the reference (continuity mode)",
    ),
    *_variants(
        C.RESTORATION,
        "EdgeFixer Reference",
        "clip = core.edgefixer.Reference(clip, core.std.BoxBlur(clip, hradius=1, vpasses=0), left={}, right={}, radius=0)\n"
        "clip = core.edgefixer.Reference(clip, core.std.BoxBlur(clip, vradius=1, hpasses=0), top={}, bottom={}, radius=0)"
        "  # left/right use a horizontal blur, top/bottom a vertical one (as StaxRip's edge_fixer_reference)",
        {"1 px": "1", "2 px": "2", "Empty": "0"},
        "Fix dirty lines at the frame's edges against a blurred copy of the picture (reference mode)",
    ),
    *_variants(
        C.RESTORATION,
        "bbmod",
        "import awsmfunc\nclip = awsmfunc.bbmod(clip, left={}, top={}, right={}, bottom={})",
        {"1 px": "1", "2 px": "2", "Empty": "0"},
        "Fix dirty lines at the frame's edges (after the crop)",
    ),
    *_variants(
        C.RESTORATION,
        "FillBorders",
        "clip = core.fb.FillBorders(clip, left={}, top={}, right={}, bottom={}, mode='fillmargins')"
        "  # or fixborders, repeat, mirror, reflect, wrap, fade",
        {"1 px": "1", "2 px": "2", "Empty": "0"},
        "Replace broken edge rows and columns",
    ),
    *_variants(
        C.RESTORATION,
        "Deblock",
        "clip = core.deblock.Deblock(clip, quant={})",
        {"Light": "20", "Medium": "25", "Strong": "30"},
        "Smooth out compression blocks",
    ),
    FilterPreset(
        C.RESTORATION,
        "DeHalo_alpha",
        "",
        "import havsfunc\nclip = havsfunc.DeHalo_alpha(clip)",
        "Remove halos around edges",
    ),
    FilterPreset(
        C.RESTORATION,
        "FineDehalo",
        "",
        "import havsfunc\nclip = havsfunc.FineDehalo(clip)",
        "Remove halos, protecting fine lines",
    ),
    # Noise
    *_variants(
        C.NOISE,
        "BM3D",
        "import mvsfunc\nclip = mvsfunc.BM3D(clip, sigma={})",
        {"Light": "1.5", "Medium": "3", "Strong": "5"},
        "Denoise, keeps detail well (slow)",
    ),
    *_variants(
        C.NOISE,
        "DFTTest",
        "import dfttest2\nclip = dfttest2.DFTTest(clip, {}, backend=dfttest2.Backend.CPU())",
        {"Light": "sigma=4, tbsize=3", "Medium": "sigma=8, tbsize=3", "Strong": "sigma=16, tbsize=5"},
        "Frequency-domain denoise",
    ),
    *_variants(
        C.NOISE,
        "SMDegrain",
        "import havsfunc\nclip = havsfunc.SMDegrain(clip, {}, RefineMotion=True)",
        {"Light": "tr=1, thSAD=300", "Medium": "tr=2, thSAD=300", "Strong": "tr=3, thSAD=500"},
        "Motion-compensated temporal denoise, for grain",
    ),
    FilterPreset(C.NOISE, "TTempSmooth", "", "clip = core.ttmpsm.TTempSmooth(clip)", "Light temporal smoothing"),
    FilterPreset(
        C.NOISE, "FFT3DFilter", "", "clip = core.fft3dfilter.FFT3DFilter(clip, sigma=2)", "Quick 3D FFT denoise"
    ),
    # Line
    FilterPreset(
        C.LINE,
        "Anti-alias (daa)",
        "",
        "import havsfunc\nclip = core.std.SetFieldBased(clip, 0)\nclip = havsfunc.daa(clip)",
        "Smooth jagged lines",
    ),
    FilterPreset(
        C.LINE, "Anti-alias (santiag)", "", "import havsfunc\nclip = havsfunc.santiag(clip)", "Smooth jagged lines"
    ),
    *_variants(
        C.LINE,
        "CAS",
        "clip = core.cas.CAS(clip, sharpness={})",
        {"Light": "0.3", "Medium": "0.5", "Strong": "0.8"},
        "Contrast adaptive sharpening",
    ),
    FilterPreset(C.LINE, "LSFmod", "", "import havsfunc\nclip = havsfunc.LSFmod(clip, defaults='slow')", "Sharpen"),
    # Deband
    *_variants(
        C.DEBAND,
        "Deband",
        "clip = core.vszip.Deband(clip, thr={}, grain=0)",
        {"Light": "32", "Medium": "48", "Strong": "64"},
        "Smooth banding in gradients (f3kdb)",
    ),
    # Grain
    *_variants(
        C.GRAIN,
        "AddGrain",
        "clip = core.grain.Add(clip, var={}, uvar=0)",
        {"Light": "0.5", "Medium": "1.0", "Strong": "2.0"},
        "Add grain, which also hides banding",
    ),
    *_variants(
        C.GRAIN,
        "AddGrain static",
        "clip = core.grain.Add(clip, var={}, uvar=0, constant=True)",
        {"Light": "0.5", "Medium": "1.0", "Strong": "2.0"},
        "Grain that stays put from frame to frame (cheaper to encode)",
    ),
    FilterPreset(C.CUSTOM, "Custom", "", "", "Your own VapourSynth lines on clip", fill_in=True),
]
