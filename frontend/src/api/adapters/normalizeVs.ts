import type { VsProbe, VsResponse } from '../../types/vs';

function toNumber(v: any): number | undefined {
  if (v === undefined || v === null) return undefined;
  const n = Number(v);
  return Number.isFinite(n) ? n : undefined;
}

export function normalizeVsResponse(resp: VsResponse | null | undefined): VsProbe {
  const vap = resp && (resp as any).vapoursynth ? (resp as any).vapoursynth : resp || {};

  return {
    frames: toNumber(vap.frames),
    width: toNumber(vap.width),
    height: toNumber(vap.height),
    fps: toNumber(vap.fps),
    error: vap.error ?? null,
    // pass-through any extra probe metadata
    ...vap,
  };
}
