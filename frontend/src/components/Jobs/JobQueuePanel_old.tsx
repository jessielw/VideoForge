/**
 * JobQueuePanel - Main job queue management UI
 */

import React, { useState, useEffect } from 'react';
import { Job, JobStatus } from '../../types/job';
import JobCard from './JobCard';

interface JobQueuePanelProps {
  autoRefresh?: boolean; // Auto-refresh jobs every few seconds
  refreshInterval?: number; // Milliseconds between refreshes
}

export default function JobQueuePanel({
  autoRefresh = true,
  refreshInterval = 2000,
}: JobQueuePanelProps): JSX.Element {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState<JobStatus | 'all'>('all');
  const [sortBy, setSortBy] = useState<'priority' | 'created' | 'status'>('priority');

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
  const handleStartJob = async (jobId: number) => {
    try {
      const response = await fetch(`http://localhost:8000/api/jobs/${jobId}/start`, {
        method: 'POST',
      });
      const result = await response.json();

      if (result.ok) {
        fetchJobs(); // Refresh list
      } else {
        alert(`Failed to start job: ${result.message || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Failed to start job:', error);
      alert('Failed to start job');
    }
  };

  const handlePauseJob = async (jobId: number) => {
    try {
      const response = await fetch(`http://localhost:8000/api/jobs/${jobId}/pause`, {
        method: 'POST',
      });
      const result = await response.json();

      if (result.ok) {
        fetchJobs(); // Refresh list
      } else {
        alert(`Failed to pause job: ${result.message || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Failed to pause job:', error);
      alert('Failed to pause job');
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
        fetchJobs(); // Refresh list
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
        fetchJobs(); // Refresh list
      } else {
        alert(`Failed to delete job: ${result.message || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Failed to delete job:', error);
      alert('Failed to delete job');
    }
  };

  // Filter and sort jobs
  const getFilteredAndSortedJobs = (): Job[] => {
    let filtered = jobs;

    // Apply filter
    if (filterStatus !== 'all') {
      filtered = filtered.filter(job => job.status === filterStatus);
    }

    // Apply sort
    const sorted = [...filtered];
    switch (sortBy) {
      case 'priority':
        sorted.sort((a, b) => {
          const priorityOrder = { high: 0, normal: 1, low: 2 };
          return priorityOrder[a.priority] - priorityOrder[b.priority];
        });
        break;
      case 'created':
        sorted.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
        break;
      case 'status':
        sorted.sort((a, b) => a.status.localeCompare(b.status));
        break;
    }

    return sorted;
  };

  const filteredJobs = getFilteredAndSortedJobs();

  // Job stats
  const stats = {
    total: jobs.length,
    queued: jobs.filter(j => j.status === 'queued').length,
    running: jobs.filter(j => j.status === 'running').length,
    paused: jobs.filter(j => j.status === 'paused').length,
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
        <button onClick={fetchJobs} className="refresh-btn" title="Refresh jobs">
          🔄 Refresh
        </button>
      </div>

      {/* Stats Bar */}
      <div className="jobs-stats">
        <div className="stat-item">
          <span className="stat-value">{stats.total}</span>
          <span className="stat-label">Total</span>
        </div>
        <div className="stat-item queued">
          <span className="stat-value">{stats.queued}</span>
          <span className="stat-label">Queued</span>
        </div>
        <div className="stat-item running">
          <span className="stat-value">{stats.running}</span>
          <span className="stat-label">Running</span>
        </div>
        <div className="stat-item paused">
          <span className="stat-value">{stats.paused}</span>
          <span className="stat-label">Paused</span>
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
            <option value="paused">Paused</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </div>

        <div className="control-group">
          <label>Sort by:</label>
          <select
            value={sortBy}
            onChange={e => setSortBy(e.target.value as 'priority' | 'created' | 'status')}
            className="sort-select"
          >
            <option value="priority">Priority</option>
            <option value="created">Created Date</option>
            <option value="status">Status</option>
          </select>
        </div>
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
            <JobCard
              key={job.id}
              job={job}
              onStart={handleStartJob}
              onPause={handlePauseJob}
              onCancel={handleCancelJob}
              onDelete={handleDeleteJob}
            />
          ))
        )}
      </div>
    </div>
  );
}
