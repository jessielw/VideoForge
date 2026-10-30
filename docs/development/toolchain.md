# Windows toolchain maintenance

Developer setup (`scripts/setup_windows.py`) and portable packaging (`scripts/build_portable.py`) use the same tool inventory (`scripts/tools.toml`), plugin inventory (`vsplugins/manifest.toml`), fetchers and smoke checks. Native provisioning supports Windows x64. Linux amd64 uses the Docker image. ARM64 images, macOS packaging and macOS Docker validation are deferred. Linux ARM64 and macOS users can attempt a [self-managed source setup](../getting-started/source.md#macos-and-arm64), supplying compatible tools and compiling plugins as needed; full feature parity and end-to-end validation are not claimed.

## Provision and inspect

```powershell
uv run python scripts/setup_windows.py
uv run python scripts/fetch_tools.py --list
uv run python scripts/fetch_tools.py --only x265
uv run python scripts/verify_toolchain.py --smoke
```

The complete setup installs locked desktop/filter dependencies and builds the frontend. The component fetchers are also usable independently. `fetch_tools.py --tools <folder>` changes the tool destination; `fetch_plugins.py --plugins <folder>` changes the plugin destination. Pass `--runtime-dir <python-folder>` to the tool fetcher to place the pinned Microsoft runtime beside Python hosts too.

The provisioner replaces only manifest-selected files, preserves unrelated files, caches downloads under `build/plugin-cache/`, and checks each download's SHA-256 even on a cache hit. Installed-file hashes under `tools/.videoforge/` allow repeat runs to skip complete packages and repair damaged or incomplete ones. `tools/THIRD_PARTY.md` records the inventory and source/build links; keep the upstream notices too.

GPAC and Microsoft redistributable installers are extracted as archives. They are never installed or run, and provisioning needs no administrator rights. The Microsoft runtime entry describes the exact attached CAB in its pinned Burn installer; update and inspect its offsets/member mapping when changing versions.

## Update a pinned tool

1. Select a versioned artifact from the upstream project or named build publisher. Verify its checksum and inspect the archive, including DLLs, notices and CPU requirements.
2. Update its version, source/build provenance, checksum and archive selection in `scripts/tools.toml`. Preserve runtime paths or update `videoforge.toml` and documentation together.
3. Provision into a fresh folder, provision its plugins, and run `verify_toolchain.py --tools <folder> --smoke`. Use the same Python environment's `filters` extra and pinned single-file filter scripts.
4. Build the portable release. Its bundled Python must pass the smoke checks before packaging. Review the applicable source-distribution and license requirements before publishing binaries.

x265 pins Patman's generic x86-64 multilib build (the one StaxRip takes). Its `--help` and `--fullhelp` leave out `--dhdr10-info`, but the option works: check a new build by encoding with `--dhdr10-info` and `--dolby-vision-rpu`, then reading the metadata back with `hdr10plus_tool extract` and `dovi_tool extract-rpu`. Its CPU-tuned builds (znver3 and others) measured no faster on Zen 3, since x265 picks its AVX2 assembly at runtime either way. Opus uses the named RareWares x64 build and pinned Xiph notices.

## Verification scope

The Windows CI job provisions real tools and plugins. Smoke checks remove developer tools from PATH, use explicit executable paths and temporary media, and require plugin/script imports, MediaInfo probing, source indexing, a decoded preview frame, vspipe, H.264/HEVC/AV1 encoding and decoding, common audio encoders, standalone opusenc, MKV/MP4 muxing, metadata edits and track extraction.

DEE and Apple's CoreAudioToolbox are user supplied. Verification checks the DeeZy and qaac frontends start, but does not claim their licensed encoding paths work without those components. HDR metadata tools are checked for startup; the x265 capability check requires HDR10+ and Dolby Vision CLI options. The generated fixtures do not establish correctness for every HDR/Atmos source or custom filter script.

The desktop shell uses Windows Edge WebView2, which is separate from the media toolchain. Windows 10+ is required by the selected tool builds; WebView2 must be available to use the desktop window.
