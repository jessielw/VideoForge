# Video-Forge — Roadmap

This document captures the architecture decisions, tradeoffs, and the MVP roadmap we discussed for a lightweight StaxRip-like video processing app (one frontend, one logical backend) supporting Vapoursynth (and Avisynth on Windows).

## Goals
- Single frontend codebase (React + TypeScript) usable in browser, Electron desktop, and served statically for Docker/headless.
- Logical backend (Python + FastAPI) to run frameservers (Vapoursynth primarily) and manage encoding via ffmpeg.
- Stream frames (pipes) to ffmpeg; avoid full-file intermediate copies.
- Desktop packaging via Electron; headless via Docker.

## High-Level Architecture

- Frontend: React + TypeScript (Vite) — single codebase. Communicates with backend via REST and WebSocket for realtime logs/progress.
- Backend: Python 3.11+, FastAPI (async). Job runner spawns isolated processes for script execution and encoding; SQLite for local job store.
- Frameserving:
  - Vapoursynth (Python) — primary, cross-platform.
  - Avisynth — Windows-only adapter using avs2pipemod/avs2yuv piping to ffmpeg.
- Encoding: ffmpeg (use piping / rawvideo) with detection and fallback for hardware encoders (NVENC/QSV/VAAPI/AMF).
- Packaging: Electron to bundle the UI and spawn the Python backend locally. Docker for headless Linux images.

## API Contract (minimal)
- POST /jobs -> { job_id }
- GET /jobs/{id} -> job metadata/status
- WebSocket /ws/{job_id} -> streaming logs, progress, optional thumbnails

Job config shape (example):

```
{
  "input_path": "path/to/input.mkv",
  "script_type": "vapoursynth", // or "avisynth" or "none"
  "script": "...script text...",
  "encoder": "libx264",
  "output": "path/to/out.mkv"
}
```

## MVP Roadmap (prioritized)
1. Backend (FastAPI): Job submission, in-memory job store, async worker that runs Vapoursynth script and pipes frames to ffmpeg. WebSocket for progress/logs.
2. Frontend (React + Vite): Job submit form, job list, log viewer, WebSocket-based live updates.
3. Desktop (Electron): Simple launcher that spawns the Python backend and loads the UI. Bind to localhost only.
4. Docker image for headless operation (Vapoursynth + ffmpeg preinstalled).
5. Windows-specific Avisynth adapter, hardware encoder detection, job persistence (SQLite), concurrency limits, plugin/preset UI.

## Tradeoffs & Notes
- Use Python for backend to leverage Vapoursynth natively. If you later need extreme performance or strict isolation, consider a Rust/Go controller that delegates to Python worker processes.
- Electron simplifies launching and local communication with a Python backend, but increases package size. Tauri is smaller but integrates less straightforwardly with Python/Vapoursynth.
- Always prefer piping frames to ffmpeg to conserve disk and memory.

## Security
- Bind backend to localhost by default.
- Use token-based auth for remote access and TLS when exposing to networks.

## Next steps
- Start scaffolding: FastAPI backend + React frontend + Electron launcher (scaffolded in this repo).
- Add real Vapoursynth integration and ffmpeg piping for the first integration test.

---
Generated scaffold and minimal roadmap on request. Expand pieces in small iterations: test the frame -> ffmpeg pipeline first, then build the UI around job control.

## How frameserving / encoding should work (practical patterns)

Overview
- The core idea is to decode frames to rawvideo (yuv420p or the encoder's preferred pixel format) and stream them into a native encoder CLI (x264/x265) or ffmpeg.
- Keep the pipeline process-local and stream over stdout/stderr; avoid full intermediate files.
- On Windows we typically run: ffprobe -> ffmpeg (decode to raw) -> encoder CLI (stdin). Encoder stderr becomes the live log stream.

Windows example (x264)
- Probe metadata (ffprobe) to choose width/height/fps and pixel format:
  - ffprobe -v error -show_entries stream=width,height,r_frame_rate -of json "input.mkv"
- Decode to rawvideo and pipe to x264 (example):
  - ffmpeg -i "input.mkv" -f rawvideo -pix_fmt yuv420p - | x264.exe --demuxer raw --input-res WIDTHxHEIGHT --input-csp i420 --fps FPS - -o "output.h264"
- Notes:
  - Replace WIDTHxHEIGHT and FPS with values from ffprobe.
  - x264's Windows CLI (x264.exe) accepts `--demuxer raw` and `--input-res`/`--input-csp` to read rawstdin. On some builds the demuxer flags differ; test your x264 binary with a short raw file first.

Windows example (x265)
- x265's CLI also accepts raw stdin; a sample pipeline:
  - ffmpeg -i "input.mkv" -f rawvideo -pix_fmt yuv420p - | x265.exe --input - --input-res WIDTHxHEIGHT --fps FPS -o "output.hevc"
- Notes:
  - x265 CLI flags historically vary between builds; consult `x265.exe --help` and test with small inputs.

Integration with the backend
- The repo contains `backend/frameserver.py` with two helpers:
  - probe_video(path) — uses ffprobe to get width/height/fps.
  - run_encoder_pipeline(input_path, output_path, encoder, env_paths, send_cb) — spawns ffmpeg to decode and pipes rawvideo to the `encoder` binary, streaming encoder stderr via the `send_cb` callback used to forward logs over the WebSocket.
- The `run_job` worker in `backend/app/main.py` will call the pipeline when the job payload includes an `encoder_binary` override. This allows testing with a full path to `C:\tools\x264.exe` or `C:\tools\x265.exe` on Windows.

Testing checklist (first end-to-end run)
1. Ensure ffmpeg/ffprobe are on PATH and an x264/x265 binary is available on disk.
2. Submit a job that includes `encoder_binary` pointing to the encoder exe and `path_mode: 'local'` for a local input file inside the allowed roots.
3. Watch the WebSocket logs: ffprobe output, ffmpeg decoding logs, then encoder stderr progress. Expect the encoder to emit bitrate/frame stats to stderr.
4. If the encoder exits with an error, capture stderr for diagnostics; common issues are wrong pixel format, incorrect resolution, or mismatched FPS.

Practical tips
- Start with a short test clip (10s) to validate the pipe flags and pixel format before using long jobs.
- On Windows, if you don't have a native x264/x265 CLI, you can also run ffmpeg to encode using libx264/libx265 as a fallback:
  - ffmpeg -i "input.mkv" -c:v libx264 -preset medium -crf 18 "out.mkv"
- Use the `encoder_binary` job field to make encoder choice configurable per-job; fall back to ffmpeg encoding when the native binary isn't available.

Next steps
- Test the pipeline on your Windows machine with a known x264/x265 executable. If the CLI flags differ for your build, update `backend/frameserver.py` with a small per-binary adapter mapping.
- After a successful test, add a test job in the repo (e.g. `scripts/test_native_encode.py`) and wire a minimal integration test that runs quickly (short clip, asserts encoder exit code == 0).

## File browser / headless UX

- For headless / Docker deployments the frontend should not rely on client-side file pickers. Instead, implement a server-side file browser API that lists allowed roots (configured via `VIDEO_FORGE_ROOTS`) and exposes directory listings and small previews via the backend. The browser UI will call these APIs to let users select files from mounted volumes.
- For desktop / Electron deployments, prefer the native file picker (electron.showOpenDialog) and pass absolute paths to the renderer/main process; still support the server-side file browser as a fallback.
- API suggestions:
  - GET /api/list?path={relative_or_absolute} -> { entries: [{name,is_dir,normalized,size,mtime}] }
  - POST /api/inspect -> returns small preview/metadata (already implemented)
  - POST /api/validate-path -> existing validation endpoint
- Security: backend MUST enforce allowed roots and resolve symlinks. For Docker, instruct users to mount host folders and set `VIDEO_FORGE_ROOTS` to container paths (e.g., `/data`).

This approach gives a single backend serving both headless and desktop frontends, and avoids exposing arbitrary filesystem paths to untrusted browsers.

