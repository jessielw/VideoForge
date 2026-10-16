# syntax=docker/dockerfile:1
# VideoForge in a container: the server and its free tools (MKVToolNix, x264, x265, ffmpeg, MP4Box,
# opus-tools, FFMS2, DeeZy, truehdd). DEE and other tools of your own go in /tools. See README "Docker".

ARG PYTHON_IMAGE=python:3.12-slim-trixie
ARG GPAC_VERSION=v26.07.0
ARG DEEZY_VERSION=1.3.15
ARG TRUEHDD_VERSION=0.6.2

# --- the frontend -------------------------------------------------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- MP4Box (Debian trixie has no gpac) -------------------------------------------------------------
# Against Debian's FFmpeg (the one the app stage installs): GPAC reads MKV sources through it.
FROM ${PYTHON_IMAGE} AS gpac
ARG GPAC_VERSION
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential ca-certificates git pkg-config zlib1g-dev \
        libavcodec-dev libavdevice-dev libavfilter-dev libavformat-dev libavutil-dev libswresample-dev libswscale-dev \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch "${GPAC_VERSION}" https://github.com/gpac/gpac /src/gpac
WORKDIR /src/gpac
RUN ./configure --prefix=/opt/gpac \
    && make -j"$(nproc)" \
    && make install \
    && rm -rf /opt/gpac/include /opt/gpac/share/man \
    && strip /opt/gpac/bin/* /opt/gpac/lib/libgpac.so.* \
    && LD_LIBRARY_PATH=/opt/gpac/lib /opt/gpac/bin/MP4Box -version \
    && LD_LIBRARY_PATH=/opt/gpac/lib /opt/gpac/bin/gpac -h filters 2>&1 | grep -q ffdmx

# --- release binaries ---------------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS downloads
ARG DEEZY_VERSION
ARG TRUEHDD_VERSION
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

# --- the app ------------------------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS app
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libffms2-5 mkvtoolnix opus-tools tini x264 x265 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv
COPY --from=gpac /opt/gpac /opt/gpac
RUN echo /opt/gpac/lib > /etc/ld.so.conf.d/gpac.conf && ldconfig && ln -s /opt/gpac/bin/MP4Box /usr/local/bin/MP4Box
COPY --from=downloads /out/deezy-bin /usr/local/bin/deezy
COPY --from=downloads /out/truehdd-bin /usr/local/bin/truehdd

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src/ src/
# FFMS2 as an autoloaded VapourSynth plugin (the library is the plugin).
RUN uv sync --frozen --no-dev \
    && plugins="$(.venv/bin/python -c 'import vapoursynth, pathlib; print(pathlib.Path(vapoursynth.__file__).parent / "plugins")')" \
    && mkdir -p "$plugins" \
    && ln -s /usr/lib/x86_64-linux-gnu/libffms2.so.5 "$plugins/libffms2.so" \
    && .venv/bin/python -c 'import vapoursynth as vs; print("ffms2", vs.core.ffms2.Version())'
COPY --from=frontend /src/frontend/dist frontend/dist
COPY docker/videoforge.toml videoforge.toml

# Any user id works (docker run --user): HOME only holds VapourSynth's small config.
RUN mkdir -p /data /tools /home/videoforge && chmod 0777 /data /tools /home/videoforge
ENV VIDEOFORGE_ROOT=/app HOME=/home/videoforge PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1
VOLUME ["/data"]
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=4)"
ENTRYPOINT ["tini", "--"]
# 0.0.0.0 inside the container; publish the port on the host's 127.0.0.1 (there's no login).
CMD ["videoforge", "serve", "--no-browser", "--host", "0.0.0.0", "--data-dir", "/data"]
