# syntax=docker/dockerfile:1
# VideoForge in a container: the server and its free tools. The native ones (FFmpeg, MP4Box, x264, the
# VapourSynth plugins) come from the plugins image (vsplugins/), built rarely; x265 is built here (with HDR10+);
# MKVToolNix and opus-tools from Debian; DeeZy, truehdd, dovi_tool and hdr10plus_tool from their releases; Wine
# for Windows tools. DEE, qaac and other tools of your own go in /tools (docker/entrypoint.sh).
# See README "Docker".
#   docker build -t videoforge .                      (with the published plugins image)
#   docker build -t videoforge-plugins vsplugins && docker build --build-arg PLUGINS_IMAGE=videoforge-plugins -t videoforge .

ARG PYTHON_IMAGE=python:3.12-slim-trixie
ARG PLUGINS_IMAGE=ghcr.io/jessielw/videoforge-plugins:latest
ARG DEEZY_VERSION=1.3.15
# x265 from source: Debian's is built without HDR10+ (--dhdr10-info)
ARG X265_VERSION=4.1
ARG X265_SHA256=a31699c6a89806b74b0151e5e6a7df65de4b49050482fe5ebf8a4379d7af8f29
ARG TRUEHDD_VERSION=0.6.2
# quietvoid's Dolby Vision / HDR10+ tools (MIT): the versions scripts/fetch_tools.py takes for Windows
ARG DOVI_TOOL_VERSION=2.3.4
ARG DOVI_TOOL_SHA256=1844258e13c26607b32224bf1fa82b595d3b35949f5467405fda560daad32b3f
ARG HDR10PLUS_TOOL_VERSION=1.7.2
ARG HDR10PLUS_TOOL_SHA256=06385f37a639d61ba21d4be3150c863846933bc3b58110e094d8fc8f1c2249f2

FROM ${PLUGINS_IMAGE} AS plugins

# --- the frontend -------------------------------------------------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- x265 ----------------------------------------------------------------------------------------------
# 8, 10 and 12-bit in one static binary (the usual multilib build), with HDR10+ (ENABLE_HDR10_PLUS). git is there
# so its CMake reads the version from the tarball's x265Version.txt (without it: "version unknown")
FROM ${PYTHON_IMAGE} AS x265
ARG X265_VERSION
ARG X265_SHA256
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl cmake nasm g++ make git \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN curl -fsSL -o x265.tar.gz "https://download.videolan.org/pub/videolan/x265/x265_${X265_VERSION}.tar.gz" \
    && echo "${X265_SHA256}  x265.tar.gz" | sha256sum -c - \
    && tar -xzf x265.tar.gz && mv "x265_${X265_VERSION}" x265
RUN set -e; common="-DCMAKE_BUILD_TYPE=Release -DENABLE_HDR10_PLUS=ON -DCMAKE_POLICY_VERSION_MINIMUM=3.5"; \
    mkdir -p b12 b10 b8; \
    cmake -S x265/source -B b12 $common -DHIGH_BIT_DEPTH=ON -DMAIN12=ON -DEXPORT_C_API=OFF -DENABLE_SHARED=OFF \
        -DENABLE_CLI=OFF; \
    cmake --build b12 -j"$(nproc)"; \
    cmake -S x265/source -B b10 $common -DHIGH_BIT_DEPTH=ON -DEXPORT_C_API=OFF -DENABLE_SHARED=OFF -DENABLE_CLI=OFF; \
    cmake --build b10 -j"$(nproc)"; \
    cp b12/libx265.a b8/libx265_main12.a; cp b10/libx265.a b8/libx265_main10.a; \
    cmake -S x265/source -B b8 $common -DENABLE_SHARED=OFF -DLINKED_10BIT=ON -DLINKED_12BIT=ON \
        -DEXTRA_LIB="x265_main10.a;x265_main12.a" -DEXTRA_LINK_FLAGS=-L.; \
    cmake --build b8 -j"$(nproc)"; \
    install -m 0755 b8/x265 /x265

# --- release binaries ---------------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS downloads
ARG DEEZY_VERSION
ARG TRUEHDD_VERSION
ARG DOVI_TOOL_VERSION
ARG DOVI_TOOL_SHA256
ARG HDR10PLUS_TOOL_VERSION
ARG HDR10PLUS_TOOL_SHA256
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl unzip \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /out
RUN curl -fsSL -o deezy.zip "https://github.com/jessielw/DeeZy/releases/download/${DEEZY_VERSION}/deezy-linux-x64.zip" \
    && unzip -q deezy.zip -d deezy && rm deezy.zip \
    && find deezy -type f -name deezy -exec install -m 0755 {} /out/deezy-bin \;
RUN base="truehdd-${TRUEHDD_VERSION}-x86_64-unknown-linux-gnu.tar.gz" \
    && curl -fsSL -o "$base" "https://github.com/truehdd/truehdd/releases/download/${TRUEHDD_VERSION}/$base" \
    && sum="$(curl -fsSL "https://github.com/truehdd/truehdd/releases/download/${TRUEHDD_VERSION}/$base.sha256")" \
    && echo "${sum%% *}  $base" | sha256sum -c - \
    && mkdir truehdd && tar -xzf "$base" -C truehdd \
    && find truehdd -type f -name truehdd -exec install -m 0755 {} /out/truehdd-bin \;
RUN for t in "dovi_tool ${DOVI_TOOL_VERSION} ${DOVI_TOOL_SHA256}" "hdr10plus_tool ${HDR10PLUS_TOOL_VERSION} ${HDR10PLUS_TOOL_SHA256}"; do \
        set -- $t; base="$1-$2-x86_64-unknown-linux-musl.tar.gz"; \
        curl -fsSL -o "$base" "https://github.com/quietvoid/$1/releases/download/$2/$base" \
        && echo "$3  $base" | sha256sum -c - \
        && mkdir "$1" && tar -xzf "$base" -C "$1" \
        && find "$1" -type f -name "$1" -exec install -m 0755 {} "/out/$1-bin" \; || exit 1; \
    done

# --- the app ------------------------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS app
# The Debian libraries the plugins image's binaries link to are listed in it.
COPY --from=plugins /opt/vf/runtime-packages.txt /tmp/runtime-packages.txt
RUN apt-get update \
    && apt-get install -y --no-install-recommends mkvtoolnix opus-tools tini $(cat /tmp/runtime-packages.txt) \
    && rm -rf /var/lib/apt/lists/* /tmp/runtime-packages.txt
COPY --from=plugins /opt/vf /opt/vf
RUN echo /opt/vf/lib > /etc/ld.so.conf.d/vf.conf && ldconfig
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv
COPY --from=downloads /out/deezy-bin /usr/local/bin/deezy
COPY --from=downloads /out/truehdd-bin /usr/local/bin/truehdd
COPY --from=x265 /x265 /usr/local/bin/x265
COPY --from=downloads /out/dovi_tool-bin /usr/local/bin/dovi_tool
COPY --from=downloads /out/hdr10plus_tool-bin /usr/local/bin/hdr10plus_tool
# Wine for the Windows tools in /tools/wine (qaac, DEE's Windows build). Its DLLs lose their debug info
# (711 MB -> 237 MB), and a template prefix is made for docker/wine-run to copy (docker/wine-prefix.sh).
COPY docker/wine-prefix.sh /tmp/wine-prefix.sh
RUN apt-get update \
    && apt-get install -y --no-install-recommends wine64 binutils \
    && find /usr/lib/x86_64-linux-gnu/wine -type f -exec strip --strip-debug {} + \
    && apt-get purge -y --auto-remove binutils \
    && rm -rf /var/lib/apt/lists/* \
    && bash /tmp/wine-prefix.sh && rm /tmp/wine-prefix.sh
COPY --chmod=0755 docker/wine-run /opt/wine/bin/wine-run
COPY --chmod=0755 docker/entrypoint.sh /usr/local/bin/videoforge-entrypoint

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --extra filters --no-install-project
COPY vsplugins/manifest.toml vsplugins/manifest.toml
COPY scripts/fetch_plugins.py scripts/fetch_plugins.py
# The plugins are the vapoursynth package's own plugins folder (always loaded); the filter scripts
# (havsfunc, mvsfunc) go in site-packages. Then every plugin in the manifest has to load.
RUN site="$(.venv/bin/python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')" \
    && rm -rf "$site/vapoursynth/plugins" && ln -s /opt/vf/vs-plugins "$site/vapoursynth/plugins" \
    && .venv/bin/python scripts/fetch_plugins.py --no-plugins --scripts "$site" \
    && rm -rf build \
    && .venv/bin/python -c "import tomllib, vapoursynth as vs; m = tomllib.load(open('/opt/vf/manifest.toml', 'rb')); \
missing = [p['namespace'] for p in m['plugin'] if not hasattr(vs.core, p['namespace'])]; \
assert not missing, missing; import havsfunc, mvsfunc, awsmfunc, dfttest2; print(len(m['plugin']), 'plugins')"
COPY src/ src/
RUN uv sync --frozen --no-dev --extra filters
COPY --from=frontend /src/frontend/dist frontend/dist
COPY docker/videoforge.toml videoforge.toml

# Any user id works (docker run --user): HOME only holds VapourSynth's small config.
RUN mkdir -p /data /tools /home/videoforge && chmod 0777 /data /tools /home/videoforge
ENV VIDEOFORGE_ROOT=/app HOME=/home/videoforge PATH=/app/.venv/bin:/opt/vf/bin:$PATH PYTHONUNBUFFERED=1
VOLUME ["/data"]
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=4)"
ENTRYPOINT ["tini", "--", "videoforge-entrypoint"]
# 0.0.0.0 inside the container; publish the port on the host's 127.0.0.1 (there's no login).
CMD ["videoforge", "serve", "--no-browser", "--host", "0.0.0.0", "--data-dir", "/data"]
