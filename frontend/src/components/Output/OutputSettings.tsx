/**
 * OutputSettings - Main output configuration UI
 */

import React from 'react';
import { OutputConfig, ContainerFormat, CONTAINER_INFO } from '../../types/output';
import ContainerSelector from './ContainerSelector';
import OutputPathSelector from './OutputPathSelector';

interface OutputSettingsProps {
  config: OutputConfig;
  onChange: (config: OutputConfig) => void;
  sourcePath?: string; // Source file path to suggest output name
  onAddToJobs?: () => void; // Callback to add job to queue
}

export default function OutputSettings({
  config,
  onChange,
  sourcePath,
  onAddToJobs,
}: OutputSettingsProps): JSX.Element {
  const handleContainerChange = (container: ContainerFormat) => {
    const containerInfo = CONTAINER_INFO[container];
    onChange({
      ...config,
      container,
      muxer: containerInfo.muxer, // Auto-select muxer
    });
  };

  const handlePathChange = (outputPath: string) => {
    onChange({
      ...config,
      outputPath,
    });
  };

  const handleFastStartChange = (fastStart: boolean) => {
    onChange({
      ...config,
      fastStart,
    });
  };

  const handleOverwriteChange = (overwrite: boolean) => {
    onChange({
      ...config,
      overwrite,
    });
  };

  const canAddToJobs = () => {
    return config.outputPath.trim() !== '' && sourcePath;
  };

  return (
    <div className="output-settings">
      <div className="output-header">
        <h2>Output Configuration</h2>
        <p className="header-description">Configure your output file format and destination</p>
      </div>

      <div className="output-form">
        {/* Container Format Selection */}
        <ContainerSelector selected={config.container} onChange={handleContainerChange} />

        {/* Output Path */}
        <OutputPathSelector
          outputPath={config.outputPath}
          onChange={handlePathChange}
          container={config.container}
          sourcePath={sourcePath}
        />

        {/* Container-Specific Options */}
        <div className="output-options">
          <h3>Output Options</h3>

          {/* MP4 Fast Start */}
          {config.container === 'mp4' && (
            <div className="option-item">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={config.fastStart ?? false}
                  onChange={e => handleFastStartChange(e.target.checked)}
                />
                <span className="checkbox-text">
                  <strong>Fast Start</strong>
                  <span className="option-description">
                    Move moov atom to beginning of file for faster web streaming
                  </span>
                </span>
              </label>
            </div>
          )}

          {/* Overwrite Existing */}
          <div className="option-item">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={config.overwrite ?? false}
                onChange={e => handleOverwriteChange(e.target.checked)}
              />
              <span className="checkbox-text">
                <strong>Overwrite Existing File</strong>
                <span className="option-description">
                  Automatically overwrite the output file if it already exists
                </span>
              </span>
            </label>
          </div>
        </div>

        {/* Encoding Summary */}
        <div className="encoding-summary">
          <h3>Encoding Summary</h3>
          <div className="summary-grid">
            <div className="summary-item">
              <span className="summary-label">Source:</span>
              <span className="summary-value">{sourcePath || 'No file selected'}</span>
            </div>
            <div className="summary-item">
              <span className="summary-label">Output:</span>
              <span className="summary-value">{config.outputPath || 'Not set'}</span>
            </div>
            <div className="summary-item">
              <span className="summary-label">Container:</span>
              <span className="summary-value">{CONTAINER_INFO[config.container].displayName}</span>
            </div>
            <div className="summary-item">
              <span className="summary-label">Muxer:</span>
              <span className="summary-value">
                {config.muxer || CONTAINER_INFO[config.container].muxer}
              </span>
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="output-actions">
          <button
            className="add-to-jobs-button"
            onClick={onAddToJobs}
            disabled={!canAddToJobs()}
            title={
              !canAddToJobs()
                ? 'Select a source file and set output path to add job'
                : 'Add encoding job to queue'
            }
          >
            ➕ Add to Jobs
          </button>

          {!canAddToJobs() && (
            <div className="action-hint">
              {!sourcePath && '⚠️ Select a source file first'}
              {sourcePath && !config.outputPath.trim() && '⚠️ Set an output path'}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
