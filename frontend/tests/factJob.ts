import type { JobSummary } from '../src/lib/types.ts'

// A job with just what jobFacts reads, for the tests of a job's facts line.
export const factJob = (over: Partial<JobSummary> = {}) =>
  ({
    encoder: 'x265',
    crop: null,
    custom_script: false,
    audio: [{}, {}],
    subs: 3,
    source_facts: { resolution: '1920x1080', duration_ms: 1_500_000, hdr: ['HDR10', 'HLG'], interlaced: false },
    ...over,
  }) as unknown as JobSummary
