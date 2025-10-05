/**
 * Job system types for encoding queue
 */

import { EncoderConfig } from './encoder';
import { SimpleAudioConfig } from './audio';
import { OutputConfig } from './output';

// Job status enum
export type JobStatus =
  | 'queued' // Waiting to start
  | 'running' // Currently encoding
  | 'paused' // Paused by user
  | 'completed' // Successfully finished
  | 'failed' // Error occurred
  | 'cancelled'; // Cancelled by user

// Job configuration (what gets submitted to backend)
export interface JobConfig {
  // Source
  sourcePath: string;

  // Processing
  vsScript: string;

  // Video encoding
  videoConfig: EncoderConfig;

  // Audio encoding
  audioConfig: SimpleAudioConfig;

  // Output
  outputConfig: OutputConfig;

  // Job metadata
  name?: string; // Optional custom name for the job
}

// Job (stored in database, returned from API)
export interface Job {
  id: number;
  name: string;
  status: JobStatus;
  position: number; // Order in queue (lower = higher priority)
  enabled: boolean; // Whether job should be processed

  // Paths
  sourcePath: string;
  outputPath: string;

  // Configs (JSON stored in DB)
  videoConfig: EncoderConfig;
  audioConfig: SimpleAudioConfig;
  outputConfig: OutputConfig;
  vsScript: string;

  // Progress tracking
  progress: number; // 0-100
  currentFrame?: number;
  totalFrames?: number;
  fps?: number; // Encoding speed
  eta?: number; // Estimated time remaining (seconds)

  // Timestamps
  createdAt: string;
  startedAt?: string;
  completedAt?: string;

  // Error handling
  errorMessage?: string;

  // File info
  sourceSize?: number; // bytes
  outputSize?: number; // bytes
}

// Job submission request
export interface SubmitJobRequest {
  config: JobConfig;
}

// Job submission response
export interface SubmitJobResponse {
  ok: boolean;
  jobId?: number;
  message?: string;
  error?: string;
}

// Job list response
export interface JobListResponse {
  ok: boolean;
  jobs: Job[];
  error?: string;
}

// Job action response (pause, resume, cancel, delete)
export interface JobActionResponse {
  ok: boolean;
  message?: string;
  error?: string;
}
