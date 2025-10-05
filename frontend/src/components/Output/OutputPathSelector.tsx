/**
 * OutputPathSelector - Choose output file path with file browser
 */

import React, { useState } from 'react';
import { ContainerFormat, CONTAINER_INFO } from '../../types/output';
import FileBrowser from '../UI/FileBrowser';

interface OutputPathSelectorProps {
  outputPath: string;
  onChange: (path: string) => void;
  container: ContainerFormat;
  sourcePath?: string; // Optional: use to suggest default output name
}

export default function OutputPathSelector({
  outputPath,
  onChange,
  container,
  sourcePath,
}: OutputPathSelectorProps): JSX.Element {
  const [showSuggestion, setShowSuggestion] = useState(true);
  const [showBrowser, setShowBrowser] = useState(false);

  const containerInfo = CONTAINER_INFO[container];

  // Generate suggested filename from source
  const getSuggestedFilename = (): string => {
    if (!sourcePath) return `output${containerInfo.extension}`;

    const sourceFilename = sourcePath.split(/[/\\]/).pop() || 'output';
    const baseName = sourceFilename.replace(/\.[^.]+$/, ''); // Remove existing extension
    return `${baseName}_encoded${containerInfo.extension}`;
  };

  // Auto-suggest on mount if no output path set
  React.useEffect(() => {
    if (!outputPath && sourcePath && showSuggestion) {
      const suggested = getSuggestedFilename();
      onChange(suggested);
      setShowSuggestion(false);
    }
  }, [sourcePath, outputPath, container, showSuggestion]);

  // Update extension when container changes
  React.useEffect(() => {
    if (outputPath && !outputPath.endsWith(containerInfo.extension)) {
      const basePath = outputPath.replace(/\.[^.]+$/, ''); // Remove existing extension
      onChange(`${basePath}${containerInfo.extension}`);
    }
  }, [container]);

  const handleBrowseClick = () => {
    setShowBrowser(true);
  };

  const handleInputChange = (value: string) => {
    onChange(value);
    setShowSuggestion(false);
  };

  const handleBrowserSelect = (path: string) => {
    onChange(path);
    setShowSuggestion(false);
  };

  // Get directory from current output path for browser starting location
  const getStartingDirectory = (): string | null => {
    if (!outputPath) {
      // If source path exists, start in source directory
      if (sourcePath) {
        const parts = sourcePath.split(/[/\\]/);
        parts.pop(); // Remove filename
        return parts.join('/') || null;
      }
      return null;
    }

    // Extract directory from output path
    const parts = outputPath.split(/[/\\]/);
    if (parts.length > 1) {
      parts.pop(); // Remove filename
      return parts.join('/') || null;
    }

    return null;
  };

  return (
    <div className="output-path-selector">
      <label htmlFor="output-path">Output File Path</label>
      <div className="path-input-group">
        <input
          type="text"
          id="output-path"
          value={outputPath}
          onChange={e => handleInputChange(e.target.value)}
          placeholder={`Enter output path (e.g., ${getSuggestedFilename()})`}
          className="path-input"
        />
        <button
          onClick={handleBrowseClick}
          className="browse-button"
          title="Browse for save location"
        >
          📁 Browse
        </button>
      </div>

      {/* File Browser Modal */}
      {showBrowser && (
        <FileBrowser
          mode="save"
          title="Save Output File"
          currentPath={getStartingDirectory()}
          onSelect={handleBrowserSelect}
          onClose={() => setShowBrowser(false)}
          defaultFilename={
            outputPath
              ? outputPath.split(/[/\\]/).pop() || getSuggestedFilename()
              : getSuggestedFilename()
          }
        />
      )}

      {/* Show suggestion if path is empty */}
      {!outputPath && sourcePath && (
        <div className="path-suggestion">
          <span className="suggestion-label">💡 Suggested:</span>
          <button
            className="suggestion-button"
            onClick={() => {
              const suggested = getSuggestedFilename();
              onChange(suggested);
              setShowSuggestion(false);
            }}
          >
            {getSuggestedFilename()}
          </button>
        </div>
      )}

      {/* Show info about current path */}
      {outputPath && (
        <div className="path-info">
          <div className="path-info-line">
            <span className="info-label">Extension:</span>
            <span className="info-value">{containerInfo.extension}</span>
          </div>
          <div className="path-info-line">
            <span className="info-label">Muxer:</span>
            <span className="info-value">{containerInfo.muxer}</span>
          </div>
        </div>
      )}
    </div>
  );
}
