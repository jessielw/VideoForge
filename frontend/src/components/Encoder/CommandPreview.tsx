/**
 * CommandPreview - Shows generated CLI command
 */

import React, { useState } from 'react';

interface CommandPreviewProps {
  command: string[] | undefined;
}

export default function CommandPreview({ command }: CommandPreviewProps): JSX.Element {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!command || command.length === 0) {
    return <></>;
  }

  const commandString = command.join(' ');

  return (
    <div className="command-preview-section">
      <button
        type="button"
        className="command-preview-toggle"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <span className="toggle-icon">{isExpanded ? '▼' : '▶'}</span>
        <span>Command Preview</span>
      </button>

      {isExpanded && (
        <div className="command-preview">
          <code>{commandString}</code>
        </div>
      )}
    </div>
  );
}
