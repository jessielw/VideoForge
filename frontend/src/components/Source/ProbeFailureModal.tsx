import React from 'react';

interface Props {
  error?: string | null;
  onClose?: () => void;
}

export default function ProbeFailureModal({ error, onClose }: Props) {
  if (!error) return null;

  return (
    <div className="modal-overlay">
      <div className="modal">
        <h3>VapourSynth Probe Failed</h3>
        <p>
          The application failed to probe the selected file using VapourSynth. Previews and
          processing are disabled until this is resolved.
        </p>
        <pre className="error-text">{String(error)}</pre>
        <div style={{ marginTop: 16, display: 'flex', justifyContent: 'flex-end' }}>
          <button onClick={onClose}>Dismiss</button>
        </div>
      </div>
    </div>
  );
}
