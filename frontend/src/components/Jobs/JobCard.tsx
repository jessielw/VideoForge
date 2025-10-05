/**
 * JobCard - Individual job display with actions and progress
 */

import React from 'react';
import { Job, JobStatus } from '../../types/job';

interface JobCardProps {
  job: Job;
  onStart: (jobId: number) => void;
  onCancel: (jobId: number) => void;
  onDelete: (jobId: number) => void;
  onToggleEnabled: (jobId: number) => void;
}

export default function JobCard({
  job,
  onStart,
  onCancel,
  onDelete,
  onToggleEnabled,
}: JobCardProps): JSX.Element {
  const getStatusIcon = (status: JobStatus): string => {
    switch (status) {
      case 'queued':
        return '⏳';
      case 'running':
        return '▶️';
      case 'paused':
        return '⏸️';
      case 'completed':
        return '✅';
      case 'failed':
        return '❌';
      case 'cancelled':
        return '🚫';
      default:
        return '❓';
    }
  };

  const getStatusClass = (status: JobStatus): string => {
    return `job-status status-${status}`;
  };



  const formatFileSize = (bytes: number | null | undefined): string => {
    if (!bytes) return 'N/A';
    const mb = bytes / 1024 / 1024;
    if (mb < 1024) return `${mb.toFixed(2)} MB`;
    return `${(mb / 1024).toFixed(2)} GB`;
  };

  const formatDuration = (seconds: number | null | undefined): string => {
    if (!seconds) return 'N/A';
    const hours = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    if (hours > 0) return `${hours}h ${mins}m ${secs}s`;
    if (mins > 0) return `${mins}m ${secs}s`;
    return `${secs}s`;
  };

  const formatTimestamp = (isoString: string | null | undefined): string => {
    if (!isoString) return 'N/A';
    try {
      const date = new Date(isoString);
      return date.toLocaleString();
    } catch {
      return 'Invalid date';
    }
  };

  const canStart = job.status === 'queued' && job.enabled;
  const canCancel = job.status === 'queued' || job.status === 'running';
  const canDelete = job.status !== 'running';
  const canToggle = job.status === 'queued';

  return (
    <div className={`job-card ${getStatusClass(job.status)} ${!job.enabled ? 'job-disabled' : ''}`}>
      {/* Header */}
      <div className="job-header">
        <div className="job-title-section">
          {/* Enabled Checkbox */}
          {canToggle && (
            <input
              type="checkbox"
              className="job-enabled-checkbox"
              checked={job.enabled}
              onChange={() => onToggleEnabled(job.id)}
              title={job.enabled ? "Disable job" : "Enable job"}
            />
          )}
          
          <div className="job-status-badge">
            <span className="status-icon">{getStatusIcon(job.status)}</span>
            <span className="status-text">{job.status}</span>
          </div>
          <h3 className="job-name">{job.name}</h3>
          <div className="job-position">
            <span className="position-text">#{job.position + 1}</span>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="job-actions">
          {canStart && (
            <button
              className="job-action-btn start-btn"
              onClick={() => onStart(job.id)}
              title="Start encoding"
            >
              ▶️ Start
            </button>
          )}
          {canCancel && (
            <button
              className="job-action-btn cancel-btn"
              onClick={() => onCancel(job.id)}
              title="Cancel job"
            >
              🚫 Cancel
            </button>
          )}
          {canDelete && (
            <button
              className="job-action-btn delete-btn"
              onClick={() => onDelete(job.id)}
              title="Delete job"
            >
              🗑️ Delete
            </button>
          )}
        </div>
      </div>

      {/* Progress Bar (for running/completed jobs) */}
      {(job.status === 'running' || job.status === 'completed') && (
        <div className="job-progress-section">
          <div className="progress-bar-container">
            <div className="progress-bar" style={{ width: `${job.progress}%` }}>
              <span className="progress-text">{job.progress.toFixed(1)}%</span>
            </div>
          </div>
          <div className="progress-stats">
            {job.currentFrame !== null && job.totalFrames !== null && (
              <span className="stat">
                Frame: {job.currentFrame} / {job.totalFrames}
              </span>
            )}
            {job.fps !== null && job.fps !== undefined && (
              <span className="stat">Speed: {job.fps.toFixed(2)} fps</span>
            )}
            {job.eta !== null && job.status === 'running' && (
              <span className="stat">ETA: {formatDuration(job.eta)}</span>
            )}
          </div>
        </div>
      )}

      {/* Error Message (for failed jobs) */}
      {job.status === 'failed' && job.errorMessage && (
        <div className="job-error">
          <strong>Error:</strong> {job.errorMessage}
        </div>
      )}

      {/* Job Details */}
      <div className="job-details">
        <div className="detail-row">
          <span className="detail-label">Source:</span>
          <span className="detail-value" title={job.sourcePath}>
            {job.sourcePath.split(/[\\/]/).pop()}
          </span>
        </div>
        <div className="detail-row">
          <span className="detail-label">Output:</span>
          <span className="detail-value" title={job.outputPath}>
            {job.outputPath.split(/[\\/]/).pop()}
          </span>
        </div>
        <div className="detail-row">
          <span className="detail-label">Video:</span>
          <span className="detail-value">
            {job.videoConfig?.encoder || 'N/A'} ({job.videoConfig?.mode || 'N/A'})
          </span>
        </div>
        <div className="detail-row">
          <span className="detail-label">Audio:</span>
          <span className="detail-value">
            {job.audioConfig?.encoder || 'N/A'} (Track {job.audioConfig?.sourceTrack ?? 'N/A'})
          </span>
        </div>
        <div className="detail-row">
          <span className="detail-label">Container:</span>
          <span className="detail-value">
            {job.outputConfig?.container?.toUpperCase() || 'N/A'}
          </span>
        </div>
      </div>

      {/* Timestamps */}
      <div className="job-timestamps">
        <div className="timestamp-item">
          <span className="timestamp-label">Created:</span>
          <span className="timestamp-value">{formatTimestamp(job.createdAt)}</span>
        </div>
        {job.startedAt && (
          <div className="timestamp-item">
            <span className="timestamp-label">Started:</span>
            <span className="timestamp-value">{formatTimestamp(job.startedAt)}</span>
          </div>
        )}
        {job.completedAt && (
          <div className="timestamp-item">
            <span className="timestamp-label">Completed:</span>
            <span className="timestamp-value">{formatTimestamp(job.completedAt)}</span>
          </div>
        )}
      </div>

      {/* File Sizes (for completed jobs) */}
      {job.status === 'completed' && (job.sourceSize || job.outputSize) && (
        <div className="job-file-sizes">
          {job.sourceSize && (
            <span className="file-size">Source: {formatFileSize(job.sourceSize)}</span>
          )}
          {job.outputSize && (
            <span className="file-size">Output: {formatFileSize(job.outputSize)}</span>
          )}
          {job.sourceSize && job.outputSize && (
            <span className="file-size compression-ratio">
              Ratio: {((job.outputSize / job.sourceSize) * 100).toFixed(1)}%
            </span>
          )}
        </div>
      )}
    </div>
  );
}
