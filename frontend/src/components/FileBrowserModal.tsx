/**
 * FileBrowserModal - Wrapper for backward compatibility
 *
 * This component maintains the old API but uses the new FileBrowser internally.
 * Eventually, components should migrate to use FileBrowser directly.
 */

import React, { useState, useEffect } from 'react';
import FileBrowser, { FileEntry } from './UI/FileBrowser';

interface FileBrowserModalProps {
  fileCurrent: string | null;
  goUp: () => void;
  fileLoading: boolean;
  fileError: string | null;
  fileEntries: FileEntry[] | null;
  drill: (path: string) => void;
  selectFile: (path: string) => void;
  onClose: () => void;
}

export default function FileBrowserModal({
  fileCurrent,
  selectFile,
  onClose,
}: FileBrowserModalProps) {
  // Use new FileBrowser component with 'open' mode
  return (
    <FileBrowser
      mode="open"
      title="Open File"
      currentPath={fileCurrent}
      onSelect={selectFile}
      onClose={onClose}
      fileFilter={entry => {
        // Only show .mkv and .mp4 files
        if (entry.is_dir) return true;
        return entry.name.endsWith('.mkv') || entry.name.endsWith('.mp4');
      }}
    />
  );
}
