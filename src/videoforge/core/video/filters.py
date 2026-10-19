"""The built-in filter presets: one click puts a filter in the chain (VideoSettings.filters) at its category's place.

Each uses only the plugins and filter scripts VideoForge ships (vsplugins/manifest.toml and the `filters`
extra), so every one runs as it is. A filter's variants (strengths, widths) are separate presets of one family
("BM3D" Light, Medium, Strong): picking another of a family already in the chain swaps it in place. The script
is plain VapourSynth on `clip`, so a step can be edited after it's added.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from videoforge.core.video.settings import FilterCategory, FilterStep

C = FilterCategory


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
        "clip = core.vivtc.VFM(clip, order=1)  # order=0: bottom field first\nclip = core.vivtc.VDecimate(clip)",
        "Telecined film back to 23.976 fps (8-bit sources)",
    ),
    *_variants(
        C.FIELD,
        "QTGMC",
        "import havsfunc\n"
        "clip = core.std.SetFieldBased(clip, 2)  # 1: bottom field first, 2: top field first\n"
        "clip = havsfunc.QTGMC(clip, TFF=True, Preset={}, FPSDivisor=2)  # FPSDivisor=1: double rate",
        {"Fast": "'Fast'", "Medium": "'Medium'", "Slower": "'Slower'"},
        "Deinterlace, same frame rate",
    ),
    FilterPreset(
        C.FIELD,
        "Bwdif",
        "",
        "clip = core.bwdif.Bwdif(clip, field=1)  # 0: bottom field first, 1: top field first",
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
        "Draw an SRT or ASS file on the video (SubText); PGS: burn a track in from the Subtitles tab",
        fill_in=True,
    ),
    # Restoration
    *_variants(
        C.RESTORATION,
        "EdgeFixer",
        "clip = core.edgefixer.Continuity(clip, left={}, top={}, right={}, bottom={})",
        {"1 px": "1", "2 px": "2", "Empty": "0"},
        "Fix dirty lines at the frame's edges (after the crop)",
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
        "clip = core.fb.FillBorders(clip, left={}, top={}, right={}, bottom={}, mode='fixborders')",
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
