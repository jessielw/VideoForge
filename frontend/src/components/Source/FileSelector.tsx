import React from 'react';

interface FileSelectProps {
  inputPath: string;
  onFileSelect: (path: string) => void;
  onBrowseClick: () => void;
  indexing: boolean;
}

export default function FileSelector({ inputPath, onFileSelect, onBrowseClick, indexing }: FileSelectProps): JSX.Element {
  return (
    <div className="file-selector">
      <h3>Source File</h3>
      <div className="input-group">
        <input
          type="text"
          value={inputPath}
          onChange={(e) => onFileSelect(e.target.value)}
          placeholder="Select or enter file path..."
          className="file-input"
          disabled={indexing}
        />
        <button 
          onClick={onBrowseClick}
          className="browse-button"
          disabled={indexing}
        >
          📁 Browse
        </button>
      </div>
      {indexing && (
        <div className="indexing-status">
          <div className="spinner"></div>
          <span>Indexing file...</span>
        </div>
      )}
    </div>
  );
}