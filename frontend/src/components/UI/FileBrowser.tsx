/**
 * FileBrowser - Universal file/folder browser component
 *
 * Supports two modes:
 * - 'open': Browse and select existing files (read-only)
 * - 'save': Browse folders and specify output filename (allows new files)
 */

import React, { useState, useEffect } from 'react';
import '../../styles/file-browser.css';

export interface FileEntry {
  name: string;
  is_dir: boolean;
  normalized: string;
  size?: number;
  mtime?: number;
}

interface FileBrowserProps {
  mode: 'open' | 'save';
  title?: string;
  currentPath: string | null;
  onSelect: (path: string) => void;
  onClose: () => void;
  fileFilter?: (entry: FileEntry) => boolean; // Filter visible files
  defaultFilename?: string; // For save mode
}

export default function FileBrowser({
  mode,
  title,
  currentPath: initialPath,
  onSelect,
  onClose,
  fileFilter,
  defaultFilename = 'output.mkv',
}: FileBrowserProps): JSX.Element {
  const [currentPath, setCurrentPath] = useState<string | null>(initialPath);
  const [entries, setEntries] = useState<FileEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filename, setFilename] = useState(defaultFilename);
  const [showNewFolderDialog, setShowNewFolderDialog] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');

  // Fetch directory contents
  const fetchDirectory = async (path: string | null) => {
    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams();
      if (path) params.set('path', path);

      const response = await fetch(`http://localhost:8000/api/list?${params}`);
      const data = await response.json();

      if (!data.ok) {
        setError(data.reason || 'Failed to list directory');
        setEntries([]);
        return;
      }

      let filteredEntries = data.entries || [];

      // Apply file filter if provided
      if (fileFilter) {
        filteredEntries = filteredEntries.filter((e: FileEntry) => e.is_dir || fileFilter(e));
      }

      setEntries(filteredEntries);
      setCurrentPath(data.path || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Network error');
      setEntries([]);
    } finally {
      setLoading(false);
    }
  };

  // Load initial directory
  useEffect(() => {
    fetchDirectory(initialPath);
  }, []);

  // Navigate up one level
  const navigateUp = () => {
    if (!currentPath) return;

    const pathParts = currentPath.split(/[/\\]/);
    pathParts.pop();
    const parentPath = pathParts.join('/') || null;
    fetchDirectory(parentPath);
  };

  // Navigate into directory
  const navigateInto = (path: string) => {
    fetchDirectory(path);
  };

  // Handle file selection (open mode)
  const handleFileSelect = (path: string) => {
    if (mode === 'open') {
      onSelect(path);
      onClose();
    }
  };

  // Handle save confirmation (save mode)
  const handleSaveConfirm = () => {
    if (!filename.trim()) {
      alert('Please enter a filename');
      return;
    }

    // Construct full path
    const fullPath = currentPath ? `${currentPath}/${filename.trim()}` : filename.trim();

    onSelect(fullPath);
    onClose();
  };

  // Create new folder
  const handleCreateFolder = async () => {
    if (!newFolderName.trim()) {
      alert('Please enter a folder name');
      return;
    }

    // Construct full path - backend expects absolute paths
    // Use the platform's native separator (backend will handle both / and \)
    let folderPath: string;
    if (currentPath) {
      // Detect separator used in currentPath
      const separator = currentPath.includes('\\') ? '\\' : '/';
      const needsSeparator = !currentPath.endsWith('/') && !currentPath.endsWith('\\');
      folderPath = `${currentPath}${needsSeparator ? separator : ''}${newFolderName.trim()}`;
    } else {
      // No current path - should not happen in save mode, but handle it
      folderPath = newFolderName.trim();
    }

    console.log('📁 Frontend: Creating folder:', folderPath);
    console.log('📁 Frontend: Current path:', currentPath);
    console.log('📁 Frontend: New folder name:', newFolderName.trim());

    try {
      const response = await fetch('http://localhost:8000/api/mkdir', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: folderPath }),
      });

      const data = await response.json();

      if (data.ok) {
        setShowNewFolderDialog(false);
        setNewFolderName('');
        fetchDirectory(currentPath); // Refresh
      } else {
        alert(`Failed to create folder: ${data.error || 'Unknown error'}`);
      }
    } catch (err) {
      alert(`Network error: ${err instanceof Error ? err.message : 'Unknown'}`);
    }
  };

  // Format file size
  const formatSize = (bytes?: number): string => {
    if (!bytes) return '';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  };

  // Format modified time
  const formatTime = (mtime?: number): string => {
    if (!mtime) return '';
    const date = new Date(mtime * 1000);
    return date.toLocaleString();
  };

  return (
    <div className="file-browser-overlay" onClick={onClose}>
      <div className="file-browser-modal" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="file-browser-header">
          <h2>{title || (mode === 'open' ? 'Open File' : 'Save File')}</h2>
          <button className="close-button" onClick={onClose} title="Close">
            ✕
          </button>
        </div>

        {/* Location bar */}
        <div className="file-browser-location">
          <button
            className="nav-button"
            onClick={navigateUp}
            disabled={!currentPath}
            title="Go up one level"
          >
            ⬆️ Up
          </button>
          <div className="current-path">{currentPath || '(Root)'}</div>
          {mode === 'save' && (
            <button
              className="new-folder-button"
              onClick={() => setShowNewFolderDialog(true)}
              title="Create new folder"
            >
              📁+ New Folder
            </button>
          )}
        </div>

        {/* File list */}
        <div className="file-browser-content">
          {loading ? (
            <div className="loading-state">
              <div className="spinner" />
              <span>Loading...</span>
            </div>
          ) : error ? (
            <div className="error-state">
              <span className="error-icon">⚠️</span>
              <span>{error}</span>
            </div>
          ) : entries.length === 0 ? (
            <div className="empty-state">
              <span>📂</span>
              <span>No items to display</span>
            </div>
          ) : (
            <table className="file-list">
              <thead>
                <tr>
                  <th className="col-icon"></th>
                  <th className="col-name">Name</th>
                  <th className="col-size">Size</th>
                  <th className="col-modified">Modified</th>
                </tr>
              </thead>
              <tbody>
                {entries.map(entry => (
                  <tr
                    key={entry.normalized}
                    className={`file-entry ${entry.is_dir ? 'is-directory' : 'is-file'}`}
                    onClick={() => {
                      if (entry.is_dir) {
                        navigateInto(entry.normalized);
                      } else if (mode === 'open') {
                        handleFileSelect(entry.normalized);
                      } else {
                        // In save mode, clicking a file sets it as the filename
                        setFilename(entry.name);
                      }
                    }}
                    onDoubleClick={() => {
                      if (!entry.is_dir && mode === 'save') {
                        setFilename(entry.name);
                        handleSaveConfirm();
                      }
                    }}
                  >
                    <td className="col-icon">{entry.is_dir ? '📁' : '📄'}</td>
                    <td className="col-name">{entry.name}</td>
                    <td className="col-size">{entry.is_dir ? '' : formatSize(entry.size)}</td>
                    <td className="col-modified">{formatTime(entry.mtime)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Save mode footer */}
        {mode === 'save' && (
          <div className="file-browser-footer">
            <div className="filename-input-group">
              <label>Filename:</label>
              <input
                type="text"
                value={filename}
                onChange={e => setFilename(e.target.value)}
                placeholder="Enter filename..."
                className="filename-input"
                onKeyDown={e => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    handleSaveConfirm();
                  }
                }}
              />
            </div>
            <div className="footer-actions">
              <button className="cancel-button" onClick={onClose}>
                Cancel
              </button>
              <button
                className="save-button"
                onClick={handleSaveConfirm}
                disabled={!filename.trim()}
              >
                Save
              </button>
            </div>
          </div>
        )}

        {/* New folder dialog */}
        {showNewFolderDialog && (
          <div className="new-folder-overlay" onClick={() => setShowNewFolderDialog(false)}>
            <div className="new-folder-dialog" onClick={e => e.stopPropagation()}>
              <h3>Create New Folder</h3>
              <input
                type="text"
                value={newFolderName}
                onChange={e => setNewFolderName(e.target.value)}
                placeholder="Folder name..."
                className="folder-name-input"
                autoFocus
                onKeyDown={e => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    handleCreateFolder();
                  } else if (e.key === 'Escape') {
                    setShowNewFolderDialog(false);
                  }
                }}
              />
              <div className="dialog-actions">
                <button onClick={() => setShowNewFolderDialog(false)}>Cancel</button>
                <button onClick={handleCreateFolder} disabled={!newFolderName.trim()}>
                  Create
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
