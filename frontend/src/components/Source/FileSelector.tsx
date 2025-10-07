interface FileSelectProps {
  inputPath: string;
  onFileSelect: (path: string) => void;
  onBrowseClick: () => void;
  isLoading: boolean;
}

export default function FileSelector({
  inputPath,
  onFileSelect,
  onBrowseClick,
  isLoading,
}: FileSelectProps): JSX.Element {
  const busy = isLoading;
  return (
    <div className="file-selector">
      <h3>Source File</h3>
      <div className="input-group">
        <input
          type="text"
          value={inputPath}
          onChange={e => onFileSelect(e.target.value)}
          placeholder="Select or enter file path..."
          className="file-input"
          disabled={busy}
        />
        <button onClick={onBrowseClick} className="browse-button" disabled={busy}>
          📁 Browse
        </button>
      </div>
      {busy && (
        <div className="loading-status">
          <div className="spinner"></div>
          <span>Loading...</span>
        </div>
      )}
    </div>
  );
}
