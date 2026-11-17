# syntax=docker/dockerfile:1
# VideoForge in a container: the server and its free tools. The native ones (FFmpeg, MP4Box, x264, the
# VapourSynth plugins) come from the plugins image (vsplugins/), built rarely; x265 (with HDR10+), SVT-AV1 and
# SVT-AV1-HDR (with Dolby Vision and HDR10+) are built here; MKVToolNix and opus-tools from Debian; DeeZy, truehdd, dovi_tool and hdr10plus_tool from their
# releases; Wine for Windows tools. DEE, qaac and other tools of your own go in /tools (docker/entrypoint.sh).
# See README "Docker".
#   docker build -t videoforge .                      (with the published plugins image)
#   docker build -t videoforge-plugins vsplugins && docker build --build-arg PLUGINS_IMAGE=videoforge-plugins -t videoforge .

ARG PYTHON_IMAGE=python:3.12-slim-trixie
ARG PLUGINS_IMAGE=ghcr.io/jessielw/videoforge-plugins:latest
ARG DEEZY_VERSION=1.5.0
# x265 from source: Patman's mod (the Windows build's, scripts/tools.toml), at its release tag; Debian's is built
# without HDR10+ (--dhdr10-info)
ARG X265_VERSION=4.3+22+73
ARG X265_COMMIT=1e85ca6eb
ARG X265_SHA256=bc603457c7e4de3b0349a92a4af50e597d3cd9f2c6dd687c1fc2e753627175db
# SVT-AV1's SvtAv1EncApp from its tag (Debian's is older)
ARG SVTAV1_VERSION=v4.2.0
# juliobbv-p's SVT-AV1-HDR at the commit the Windows build is (scripts/tools.toml; its releases are rolling
# "pgo-build-<date>-<commit>" tags), with Rust for its Dolby Vision and HDR10+ libraries and cargo-c to build them
ARG SVTAV1HDR_COMMIT=a46bc2d59774785f4db7341003fa23dbeb473b5a
ARG SVTAV1HDR_SHA256=dcd9e7247c1044f1730ada6786a3cf4da4e15e01eb7808fd4176481fbd42e150
ARG RUST_IMAGE=rust:1.98-slim-trixie
ARG CARGO_C_VERSION=0.10.26
ARG CARGO_C_SHA256=685fab5a2e1539c5075cea21c42469ee5a489d877dbdbf7adccf4bb631d77545
ARG TRUEHDD_VERSION=0.6.3
# quietvoid's Dolby Vision / HDR10+ tools (MIT): the versions scripts/fetch_tools.py takes for Windows
ARG DOVI_TOOL_VERSION=2.3.4
ARG DOVI_TOOL_SHA256=1844258e13c26607b32224bf1fa82b595d3b35949f5467405fda560daad32b3f
ARG HDR10PLUS_TOOL_VERSION=1.7.2
ARG HDR10PLUS_TOOL_SHA256=06385f37a639d61ba21d4be3150c863846933bc3b58110e094d8fc8f1c2249f2
# Their sources at the same tags: SVT-AV1-HDR links their libraries (libdovi, hdr10plus)
ARG DOVI_TOOL_SRC_SHA256=15b5cb68b3598e51ca968316443c9fb9597b6230e9d692cb4e641d54505a97ec
ARG HDR10PLUS_TOOL_SRC_SHA256=cc917e769bad85323c7f596179798cc96ac878a01ddfd53b210fecae4c891849

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
# so its CMake reads the version from x265Version.txt (without it: "version unknown"). The tarball's is upstream's
# (4.3+1), so it's rewritten from the tag: "4.3+22+73" is 22 commits past 4.3, 73 of them Patman's, as his
# Windows builds print it.
FROM ${PYTHON_IMAGE} AS x265
ARG X265_VERSION
ARG X265_COMMIT
ARG X265_SHA256
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl cmake nasm g++ make git \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN tag="$(echo "${X265_VERSION}" | sed 's/+/%2B/g')" \
    && curl -fsSL -o x265.tar.gz "https://github.com/Patman86/x265-Mod-by-Patman/archive/refs/tags/${tag}.tar.gz" \
    && echo "${X265_SHA256}  x265.tar.gz" | sha256sum -c - \
    && mkdir x265 && tar -xzf x265.tar.gz -C x265 --strip-components=1 \
    && set -- $(echo "${X265_VERSION}" | tr + ' ') \
    && printf 'releasetag: %s\nreleasetagdistance: %s\nrepositorychangeset: %s\n' "$1" "$2" "${X265_COMMIT}" \
        > x265/x265Version.txt \
    && echo "$3" > /src/x265-patman-commits
RUN set -e; common="-DCMAKE_BUILD_TYPE=Release -DENABLE_HDR10_PLUS=ON -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
        -DX265_TAG_DISTANCE_COM=$(cat /src/x265-patman-commits)"; \
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

# --- SVT-AV1 -------------------------------------------------------------------------------------------
# SvtAv1EncApp, statically linked; git so its CMake reads the version from the tag
FROM ${PYTHON_IMAGE} AS svtav1
ARG SVTAV1_VERSION
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates cmake nasm g++ make git \
    && rm -rf /var/lib/apt/lists/*
RUN git clone -q --depth 1 --branch "${SVTAV1_VERSION}" https://gitlab.com/AOMediaCodec/SVT-AV1.git /src/svtav1 \
    && cmake -S /src/svtav1 -B /src/b -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DBUILD_TESTING=OFF \
    && cmake --build /src/b -j"$(nproc)" \
    && install -m 0755 /src/svtav1/Bin/Release/SvtAv1EncApp /SvtAv1EncApp

# --- SVT-AV1-HDR ---------------------------------------------------------------------------------------
# Its SvtAv1EncApp with Dolby Vision and HDR10+: quietvoid's libdovi (dovi_tool's dolby_vision crate) and hdr10plus
# (hdr10plus_tool's) as static C libraries (cargo-c), linked as its own release builds link them, by the defines and
# pkg-config's flags (its CMake options for them are made for Windows). From source rather than its Linux release,
# which needs AVX2 (x86-64-v3). Without git its version is CMake's (v4.2.0). The flags show in --help only when
# built with the libraries: the stage stops if they don't (hdr.py's hdr.svt_build reads the same).
FROM ${RUST_IMAGE} AS svtav1hdr
ARG SVTAV1HDR_COMMIT
ARG SVTAV1HDR_SHA256
ARG CARGO_C_VERSION
ARG CARGO_C_SHA256
ARG DOVI_TOOL_VERSION
ARG DOVI_TOOL_SRC_SHA256
ARG HDR10PLUS_TOOL_VERSION
ARG HDR10PLUS_TOOL_SRC_SHA256
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl cmake nasm g++ make pkg-config \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN curl -fsSL -o cargo-c.tar.gz \
        "https://github.com/lu-zero/cargo-c/releases/download/v${CARGO_C_VERSION}/cargo-c-x86_64-unknown-linux-musl.tar.gz" \
    && echo "${CARGO_C_SHA256}  cargo-c.tar.gz" | sha256sum -c - \
    && tar -xzf cargo-c.tar.gz -C /usr/local/cargo/bin
RUN for t in "dovi_tool ${DOVI_TOOL_VERSION} ${DOVI_TOOL_SRC_SHA256} dolby_vision" \
             "hdr10plus_tool ${HDR10PLUS_TOOL_VERSION} ${HDR10PLUS_TOOL_SRC_SHA256} hdr10plus"; do \
        set -- $t; \
        curl -fsSL -o "$1.tar.gz" "https://github.com/quietvoid/$1/archive/refs/tags/$2.tar.gz" \
        && echo "$3  $1.tar.gz" | sha256sum -c - \
        && mkdir "$1" && tar -xzf "$1.tar.gz" -C "$1" --strip-components=1 \
        && (cd "$1/$4" && cargo cinstall --release --library-type staticlib --prefix /opt/deps --libdir /opt/deps/lib) \
        || exit 1; \
    done
RUN curl -fsSL -o svt.tar.gz "https://github.com/juliobbv-p/svt-av1-hdr/archive/${SVTAV1HDR_COMMIT}.tar.gz" \
    && echo "${SVTAV1HDR_SHA256}  svt.tar.gz" | sha256sum -c - \
    && mkdir svt && tar -xzf svt.tar.gz -C svt --strip-components=1
RUN export PKG_CONFIG_PATH=/opt/deps/lib/pkgconfig \
    && cflags="-DLIBDOVI_FOUND=1 -DLIBHDR10PLUS_RS_FOUND=1 $(pkg-config --cflags --static dovi hdr10plus-rs)" \
    && cmake -S svt -B b -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DBUILD_TESTING=OFF \
        -DCMAKE_C_FLAGS="$cflags" -DCMAKE_C_STANDARD_LIBRARIES="$(pkg-config --libs --static dovi hdr10plus-rs)" \
    && cmake --build b -j"$(nproc)" \
    && install -m 0755 svt/Bin/Release/SvtAv1EncApp /SvtAv1EncApp-HDR
RUN { /SvtAv1EncApp-HDR --help > help.txt 2>&1 || true; } \
    && head -n 1 help.txt \
    && if ! grep -q -- --dolby-vision-rpu help.txt || ! grep -q -- --hdr10plus-json help.txt; then \
        echo "SVT-AV1-HDR was built without Dolby Vision or HDR10+"; exit 1; fi

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
    && apt-get install -y --no-install-recommends mkvtoolnix opus-tools tini gosu tzdata $(cat /tmp/runtime-packages.txt) \
    && rm -rf /var/lib/apt/lists/* /tmp/runtime-packages.txt
COPY --from=plugins /opt/vf /opt/vf
RUN echo /opt/vf/lib > /etc/ld.so.conf.d/vf.conf && ldconfig
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv
COPY --from=downloads /out/deezy-bin /usr/local/bin/deezy
COPY --from=downloads /out/truehdd-bin /usr/local/bin/truehdd
COPY --from=x265 /x265 /usr/local/bin/x265
COPY --from=svtav1 /SvtAv1EncApp /usr/local/bin/SvtAv1EncApp
COPY --from=svtav1hdr /SvtAv1EncApp-HDR /usr/local/bin/SvtAv1EncApp-HDR
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
COPY scripts/artifacts.py scripts/artifacts.py
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

# Any user id works (docker run --user, or PUID / PGID: docker/entrypoint.sh): HOME only holds VapourSynth's
# small config and the Wine prefixes.
RUN mkdir -p /data /tools /home/videoforge && chmod 0777 /data /tools /home/videoforge
ENV VIDEOFORGE_ROOT=/app HOME=/home/videoforge PATH=/app/.venv/bin:/opt/vf/bin:$PATH PYTHONUNBUFFERED=1
# serve's settings as variables, for a template to change: 0.0.0.0 inside the container; publish the port on
# the host's 127.0.0.1 (there's no login). VIDEOFORGE_ALLOW_HOST adds the address you open it at.
ENV VIDEOFORGE_HOST=0.0.0.0 VIDEOFORGE_DATA_DIR=/data
VOLUME ["/data"]
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('VIDEOFORGE_PORT', '8765') + '/api/health', timeout=4)"
ENTRYPOINT ["tini", "--", "videoforge-entrypoint"]
CMD ["videoforge", "serve", "--no-browser"]
