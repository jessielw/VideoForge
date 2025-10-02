import React from 'react';

export default function FileBrowserModal({
  fileCurrent,
  goUp,
  fileLoading,
  fileError,
  fileEntries,
  drill,
  selectFile,
  onClose,
}: {
  fileCurrent: string | null;
  goUp: () => void;
  fileLoading: boolean;
  fileError: string | null;
  fileEntries: any[] | null;
  drill: (path: string) => void;
  selectFile: (path: string) => void;
  onClose: () => void;
}) {
  return (
    <div
      style={{
        position: 'fixed',
        left: 0,
        top: 0,
        right: 0,
        bottom: 0,
        background: 'rgba(0,0,0,0.15)',
        zIndex: 1000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <div
        style={{
          background: 'white',
          width: '80%',
          padding: 18,
          borderRadius: 8,
          boxShadow: '0 2px 12px #0002',
          height: '80%',
          overflowY: 'auto',
        }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <strong>File Browser</strong>
          <button onClick={onClose}>Close</button>
        </div>
        <div style={{ margin: '10px 0', fontSize: 13, color: '#666' }}>
          {fileCurrent ? <span>Current: {fileCurrent}</span> : <span>Roots</span>}
          {fileCurrent && (
            <button style={{ marginLeft: 12 }} onClick={goUp}>
              Up
            </button>
          )}
        </div>
        {fileLoading ? (
          <div>Loading...</div>
        ) : fileError ? (
          <div style={{ color: 'red' }}>{fileError}</div>
        ) : (
          <ul style={{ listStyle: 'none', padding: 0 }}>
            {fileEntries &&
              fileEntries.map((e: any) => (
                <li key={e.normalized || e.name} style={{ margin: '4px 0' }}>
                  {e.is_dir ? '📁' : '📄'}{' '}
                  <a
                    href="#"
                    style={{
                      color: e.is_dir ? '#0077cc' : '#222',
                      textDecoration: 'none',
                    }}
                    onClick={ev => {
                      ev.preventDefault();
                      if (e.is_dir) drill(e.normalized);
                      else selectFile(e.normalized);
                    }}
                  >
                    {e.name}
                  </a>
                </li>
              ))}
          </ul>
        )}
      </div>
    </div>
  );
}
