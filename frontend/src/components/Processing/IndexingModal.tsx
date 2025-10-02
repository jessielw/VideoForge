import React from 'react';

interface IndexingModalProps {
  indexing: boolean;
}

export default function IndexingModal({ indexing }: IndexingModalProps): JSX.Element | null {
  if (!indexing) return null;

  return (
    <div className="indexing-modal-overlay">
      <div className="indexing-modal">
        <div className="indexing-spinner">⏳</div>
        <h3>Indexing source</h3>
        <p>Please wait while the video is being analyzed. This operation locks the UI.</p>
      </div>
    </div>
  );
}
