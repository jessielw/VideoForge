// Types for processing probe results (vsInfo.vapoursynth).
// Keep fields optional — backend may return a subset depending on probe success.
export interface VsProbe {
  frames?: number;
  width?: number;
  height?: number;
  fps?: number;
  error?: string | null;
  // Additional probe-specific metadata (pixel format, color info, etc.)
  [key: string]: any;
}
// The backend wrapper response for the VapourSynth probe endpoint.
// Keep this 1:1 with `backend/app/payloads/vs.py:VsResponse`.
export interface VsResponse {
  ok: boolean;
  path?: string | null;
  vapoursynth?: VsProbe | null;
}
