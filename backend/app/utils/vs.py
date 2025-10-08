import vapoursynth as vs

PLUGIN_PATH = r"C:\VapourSynth\vs-plugins"

# TODO: convert this potentially to a class that allows updating the core with plugins etc

def init_vapoursynth():
    """Initialize VapourSynth core and load plugins once."""
    core = vs.core

    # try to load plugins from configured path (if provided)
    if PLUGIN_PATH:
        try:
            core.std.LoadAllPlugins(str(PLUGIN_PATH))
        except Exception:
            pass

    return core


vs_core = init_vapoursynth()
