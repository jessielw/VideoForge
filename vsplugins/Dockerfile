# syntax=docker/dockerfile:1
# The native half of the VideoForge image, built rarely (it's slow): FFmpeg, then everything linked against it
# (MP4Box, x264, the VapourSynth plugins in manifest.toml), all in /opt/vf. The app image (../Dockerfile)
# copies /opt/vf from it and installs the Debian packages listed in /opt/vf/runtime-packages.txt.
#   docker build -t videoforge-plugins vsplugins
# `--target toolchain` stops before the plugins: a container of it is where to try a new plugin's build
# (mount this folder at /src/vf, then `python3 /src/vf/build.py NAME`).

ARG PYTHON_IMAGE=python:3.12-slim-trixie
ARG FFMPEG_VERSION=n9.0.2
# GPAC master: v26.07.0 still reads AVCodec.pix_fmts, which FFmpeg 9 removed.
ARG GPAC_COMMIT=39c23ed6f027741c154cd1fe4adbc087a503cc4b
ARG X264_COMMIT=0480cb05fa188d37ae87e8f4fd8f1aea3711f7ee
ARG VAPOURSYNTH_VERSION=81
ARG MESON_VERSION=1.12.1
# The Zig versions manifest.toml's zig plugins ask for, with their tarballs' sha256.
ARG ZIG_RELEASES="0.15.2:02aa270f183da276e5b5920b1dac44a63f1a49e55050ebde3aecc9eb82f93239 0.16.0:70e49664a74374b48b51e6f3fdfbf437f6395d42509050588bd49abe52ba3d00"

FROM ${PYTHON_IMAGE} AS base
RUN apt-get update \
    && apt-get install -y --no-install-recommends autoconf automake build-essential ca-certificates cmake curl git \
        libtool nasm ninja-build pkg-config xz-utils \
        libbz2-dev libdav1d-dev liblzma-dev libopus-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*
ENV PKG_CONFIG_PATH=/opt/vf/lib/pkgconfig:/usr/local/lib/pkgconfig PATH=/opt/vf/bin:$PATH
RUN echo /opt/vf/lib > /etc/ld.so.conf.d/vf.conf

# --- FFmpeg (the CLI the app runs for audio, and the libraries the source filters and MP4Box use) -------
ARG FFMPEG_VERSION
RUN git clone -q --depth 1 --branch "${FFMPEG_VERSION}" https://github.com/FFmpeg/FFmpeg /src/ffmpeg \
    && cd /src/ffmpeg \
    && ./configure --prefix=/opt/vf --enable-shared --disable-static --disable-doc --disable-debug \
        --disable-autodetect --enable-bzlib --enable-iconv --enable-libdav1d --enable-libopus --enable-lzma \
        --enable-zlib --disable-ffplay \
    && make -j"$(nproc)" && make install && ldconfig \
    && cd / && rm -rf /src/ffmpeg /opt/vf/share \
    && ffmpeg -hide_banner -version | head -1

# --- MP4Box (Debian trixie has no gpac; GPAC reads MKV sources through FFmpeg) --------------------------
ARG GPAC_COMMIT
RUN git init -q /src/gpac && cd /src/gpac \
    && git fetch -q --depth 1 https://github.com/gpac/gpac "${GPAC_COMMIT}" && git checkout -q FETCH_HEAD \
    && ./configure --prefix=/opt/vf --extra-cflags=-I/opt/vf/include --extra-ldflags=-L/opt/vf/lib \
    && make -j"$(nproc)" && make install && ldconfig \
    && cd / && rm -rf /src/gpac /opt/vf/share/man \
    && MP4Box -version \
    && gpac -h filters 2>&1 | grep -q ffdmx

# --- x264 (reads y4m from vspipe, so no input libraries) -----------------------------------------------
ARG X264_COMMIT
RUN git init -q /src/x264 && cd /src/x264 \
    && git fetch -q --depth 1 https://code.videolan.org/videolan/x264.git "${X264_COMMIT}" && git checkout -q FETCH_HEAD \
    && ./configure --prefix=/opt/vf --bit-depth=all --disable-lavf --disable-ffms --disable-gpac --disable-lsmash \
        --disable-swscale --enable-strip \
    && make -j"$(nproc)" && make install \
    && cd / && rm -rf /src/x264 \
    && x264 --version | head -1

# --- what the plugins build with -----------------------------------------------------------------------
FROM base AS toolchain
RUN apt-get update \
    && apt-get install -y --no-install-recommends libass-dev libfftw3-dev libgsl-dev libxxhash-dev \
    && rm -rf /var/lib/apt/lists/*
# Meson from pip (Debian's runs /usr/bin/python3, which doesn't have the vapoursynth package the builds ask).
# VapourSynth is the one the app runs; its wheel has the headers. Its own .pc lacks libdir, which some builds
# read, so the plugins get a complete one.
ARG MESON_VERSION
ARG VAPOURSYNTH_VERSION
RUN pip install --no-cache-dir "meson==${MESON_VERSION}" "vapoursynth==${VAPOURSYNTH_VERSION}" \
    && vs=/usr/local/lib/python3.12/site-packages/vapoursynth \
    && mkdir -p /usr/local/lib/pkgconfig \
    && printf 'prefix=%s\nincludedir=${prefix}/include\nlibdir=${prefix}\n\nName: vapoursynth\nDescription: VapourSynth\nVersion: %s\nCflags: -I${includedir}\n' \
        "$vs" "${VAPOURSYNTH_VERSION}" > /usr/local/lib/pkgconfig/vapoursynth.pc \
    && pkg-config --modversion vapoursynth
ARG ZIG_RELEASES
RUN for release in ${ZIG_RELEASES}; do \
        version="${release%%:*}"; sum="${release##*:}"; tarball="zig-x86_64-linux-${version}.tar.xz"; \
        curl -fsSL -o "/tmp/$tarball" "https://ziglang.org/download/${version}/$tarball" \
        && echo "$sum  /tmp/$tarball" | sha256sum -c - \
        && tar -xJf "/tmp/$tarball" -C /opt && rm "/tmp/$tarball" || exit 1; \
    done

# --- the plugins ----------------------------------------------------------------------------------------
FROM toolchain AS plugins
COPY manifest.toml build.py /src/vf/
RUN python3 /src/vf/build.py
RUN python3 /src/vf/build.py --check \
    && rm -rf /opt/vf/include /opt/vf/lib/pkgconfig \
    && strip --strip-unneeded /opt/vf/lib/*.so.* \
    && cp /src/vf/manifest.toml /opt/vf/manifest.toml

FROM scratch
COPY --from=plugins /opt/vf /opt/vf
