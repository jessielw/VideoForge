/**
 * JobQueuePanel - Main job queue management UI with drag-and-drop
 * Jobs are processed top-to-bottom, similar to StaxRip
 */

import React, { useState, useEffect, DragEvent } from 'react';
import { Job, JobStatus } from '../../types/job';
import JobCard from './JobCard';

interface JobQueuePanelProps {
  autoRefresh?: boolean;
  refreshInterval?: number;
}

export default function JobQueuePanel({
  autoRefresh = true,
  refreshInterval = 2000,
}: JobQueuePanelProps): JSX.Element {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState<JobStatus | 'all'>('all');
  const [draggedJobId, setDraggedJobId] = useState<number | null>(null);
  const [isStarting, setIsStarting] = useState(false);

  // Fetch jobs from backend
  const fetchJobs = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/jobs/list');
      const result = await response.json();

      if (result.ok) {
        setJobs(result.jobs);
        setError(null);
      } else {
        setError('Failed to load jobs');
      }
    } catch (err) {
      console.error('Failed to fetch jobs:', err);
      setError('Network error - could not load jobs');
    } finally {
      setLoading(false);
    }
  };

  // Initial load
  useEffect(() => {
    fetchJobs();
  }, []);

  // Auto-refresh
  useEffect(() => {
    if (!autoRefresh) return;

    const interval = setInterval(() => {
      fetchJobs();
    }, refreshInterval);

    return () => clearInterval(interval);
  }, [autoRefresh, refreshInterval]);

  // Job actions
  const handleStartNextJob = async () => {
    if (isStarting) {
      console.log('Already starting a job, ignoring click');
      return;
    }

    setIsStarting(true);

    try {
      const response = await fetch('http://localhost:8000/api/jobs/start-next', {
        method: 'POST',
      });
      const result = await response.json();

      if (result.ok) {
        console.log(`Job ${result.jobId} started successfully`);
        await fetchJobs(); // Wait for refresh
      } else {
        console.warn('Start next failed:', result.message);
        alert(result.message || 'No enabled jobs in queue');
      }
    } catch (error) {
      console.error('Failed to start next job:', error);
      alert('Failed to start next job');
    } finally {
      setIsStarting(false);
    }
  };

  const handleStartJob = async (jobId: number) => {
    if (isStarting) {
      console.log('Already starting a job, ignoring click');
      return;
    }

    setIsStarting(true);

    try {
      const response = await fetch(`http://localhost:8000/api/jobs/${jobId}/start`, {
        method: 'POST',
      });

      if (!response.ok) {
        const result = await response.json();
        throw new Error(result.detail || 'Failed to start job');
      }

      const result = await response.json();
      console.log(`Job ${jobId} started successfully`);
      await fetchJobs();
    } catch (error) {
      console.error('Failed to start job:', error);
      alert(error instanceof Error ? error.message : 'Failed to start job');
    } finally {
      setIsStarting(false);
    }
  };

  const handleCancelJob = async (jobId: number) => {
    if (!confirm('Are you sure you want to cancel this job?')) return;

    try {
      const response = await fetch(`http://localhost:8000/api/jobs/${jobId}/cancel`, {
        method: 'POST',
      });
      const result = await response.json();

      if (result.ok) {
        fetchJobs();
      } else {
        alert(`Failed to cancel job: ${result.message || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Failed to cancel job:', error);
      alert('Failed to cancel job');
    }
  };

  const handleDeleteJob = async (jobId: number) => {
    if (!confirm('Are you sure you want to delete this job?')) return;

    try {
      const response = await fetch(`http://localhost:8000/api/jobs/${jobId}`, {
        method: 'DELETE',
      });
      const result = await response.json();

      if (result.ok) {
        fetchJobs();
      } else {
        alert(`Failed to delete job: ${result.message || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Failed to delete job:', error);
      alert('Failed to delete job');
    }
  };

  const handleToggleEnabled = async (jobId: number) => {
    try {
      const response = await fetch(`http://localhost:8000/api/jobs/${jobId}/toggle`, {
        method: 'POST',
      });
      const result = await response.json();

      if (result.ok) {
        fetchJobs();
      } else {
        alert(`Failed to toggle job: ${result.message || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Failed to toggle job:', error);
      alert('Failed to toggle job');
    }
  };

  // Drag and drop handlers
  const handleDragStart = (e: DragEvent<HTMLDivElement>, jobId: number) => {
    setDraggedJobId(jobId);
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  };

  const handleDrop = async (e: DragEvent<HTMLDivElement>, targetJobId: number) => {
    e.preventDefault();

    if (draggedJobId === null || draggedJobId === targetJobId) {
      setDraggedJobId(null);
      return;
    }

    // Reorder jobs locally first for immediate feedback
    const reorderedJobs = [...jobs];
    const draggedIndex = reorderedJobs.findIndex(j => j.id === draggedJobId);
    const targetIndex = reorderedJobs.findIndex(j => j.id === targetJobId);

    if (draggedIndex === -1 || targetIndex === -1) return;

    const [draggedJob] = reorderedJobs.splice(draggedIndex, 1);
    reorderedJobs.splice(targetIndex, 0, draggedJob);

    setJobs(reorderedJobs);
    setDraggedJobId(null);

    // Send update to backend
    try {
      const jobIds = reorderedJobs.map(j => j.id);
      const response = await fetch('http://localhost:8000/api/jobs/reorder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jobIds }),
      });

      if (!response.ok) {
        // Revert on error
        fetchJobs();
        alert('Failed to reorder jobs');
      }
    } catch (error) {
      console.error('Failed to reorder jobs:', error);
      fetchJobs(); // Revert
      alert('Failed to reorder jobs');
    }
  };

  // Filter jobs
  const filteredJobs =
    filterStatus === 'all' ? jobs : jobs.filter(job => job.status === filterStatus);

  // Job stats
  const stats = {
    total: jobs.length,
    queued: jobs.filter(j => j.status === 'queued').length,
    queuedEnabled: jobs.filter(j => j.status === 'queued' && j.enabled).length,
    running: jobs.filter(j => j.status === 'running').length,
    completed: jobs.filter(j => j.status === 'completed').length,
    failed: jobs.filter(j => j.status === 'failed').length,
    cancelled: jobs.filter(j => j.status === 'cancelled').length,
  };

  if (loading) {
    return (
      <div className="job-queue-panel">
        <div className="loading-message">Loading jobs...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="job-queue-panel">
        <div className="error-message">
          <p>{error}</p>
          <button onClick={fetchJobs} className="retry-btn">
            🔄 Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="job-queue-panel">
      {/* Header */}
      <div className="jobs-header">
        <h2>Job Queue</h2>
        <div className="header-actions">
          <button
            onClick={handleStartNextJob}
            className="start-next-btn"
            disabled={stats.queuedEnabled === 0 || stats.running > 0 || isStarting}
            title={
              isStarting
                ? 'Starting job...'
                : stats.running > 0
                  ? 'A job is already running'
                  : stats.queuedEnabled === 0
                    ? 'No enabled jobs in queue'
                    : 'Start next enabled job'
            }
          >
            {isStarting ? '⏳ Starting...' : '▶️ Start Next'}
          </button>
          <button onClick={fetchJobs} className="refresh-btn" title="Refresh jobs">
            🔄 Refresh
          </button>
        </div>
      </div>

      {/* Stats Bar */}
      <div className="jobs-stats">
        <div className="stat-item">
          <span className="stat-value">{stats.total}</span>
          <span className="stat-label">Total</span>
        </div>
        <div className="stat-item queued">
          <span className="stat-value">
            {stats.queuedEnabled}/{stats.queued}
          </span>
          <span className="stat-label">Enabled/Queued</span>
        </div>
        <div className="stat-item running">
          <span className="stat-value">{stats.running}</span>
          <span className="stat-label">Running</span>
        </div>
        <div className="stat-item completed">
          <span className="stat-value">{stats.completed}</span>
          <span className="stat-label">Completed</span>
        </div>
        <div className="stat-item failed">
          <span className="stat-value">{stats.failed}</span>
          <span className="stat-label">Failed</span>
        </div>
        <div className="stat-item cancelled">
          <span className="stat-value">{stats.cancelled}</span>
          <span className="stat-label">Cancelled</span>
        </div>
      </div>

      {/* Controls */}
      <div className="jobs-controls">
        <div className="control-group">
          <label>Filter:</label>
          <select
            value={filterStatus}
            onChange={e => setFilterStatus(e.target.value as JobStatus | 'all')}
            className="filter-select"
          >
            <option value="all">All Jobs</option>
            <option value="queued">Queued</option>
            <option value="running">Running</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </div>
        <div className="drag-hint">💡 Drag jobs to reorder • Top jobs process first</div>
      </div>

      {/* Job List */}
      <div className="jobs-list">
        {filteredJobs.length === 0 ? (
          <div className="empty-state">
            <p>No jobs {filterStatus !== 'all' ? `with status "${filterStatus}"` : 'in queue'}</p>
            <p className="empty-hint">Add jobs from the Output tab to start encoding</p>
          </div>
        ) : (
          filteredJobs.map(job => (
            <div
              key={job.id}
              draggable={job.status === 'queued'}
              onDragStart={e => handleDragStart(e, job.id)}
              onDragOver={handleDragOver}
              onDrop={e => handleDrop(e, job.id)}
              className={`job-wrapper ${draggedJobId === job.id ? 'dragging' : ''}`}
            >
              <JobCard
                job={job}
                onStart={handleStartJob}
                onCancel={handleCancelJob}
                onDelete={handleDeleteJob}
                onToggleEnabled={handleToggleEnabled}
              />
            </div>
          ))
        )}
      </div>
    </div>
  );
}
