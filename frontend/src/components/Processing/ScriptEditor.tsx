import React, { useEffect } from 'react';
import Editor from '@monaco-editor/react';
import { useScriptEditor } from '../../hooks/useScriptEditor';

interface ScriptEditorProps {
  script: string;
  onScriptChange: (script: string) => void;
  onValidate?: () => void;
  onApply?: () => void;
}

export default function ScriptEditor({
  script,
  onScriptChange,
  onValidate,
  onApply,
}: ScriptEditorProps): JSX.Element {
  const {
    localScript,
    hasUnsavedChanges,
    validationStatus,
    validationMessage,
    handleEditorChange,
    applyChanges,
    validateScript,
    handleEditorMount,
    resetScript,
  } = useScriptEditor({
    script,
    onScriptChange,
    onValidate,
    onApply,
  });

  // Sync external script changes to local state
  useEffect(() => {
    if (script !== localScript && !hasUnsavedChanges) {
      resetScript();
    }
  }, [script, localScript, hasUnsavedChanges, resetScript]);

  const getStatusIcon = () => {
    switch (validationStatus) {
      case 'validating':
        return '⏳';
      case 'valid':
        return '✅';
      case 'error':
        return '❌';
      default:
        return '📝';
    }
  };

  const getStatusText = () => {
    switch (validationStatus) {
      case 'validating':
        return 'Validating script...';
      case 'valid':
        return validationMessage || 'Script is valid';
      case 'error':
        return validationMessage || 'Script has errors';
      default:
        return hasUnsavedChanges ? 'Ready to validate' : 'Ready';
    }
  };

  return (
    <div className="script-editor">
      <div className="editor-header">
        <h3>
          VapourSynth Script
          {hasUnsavedChanges && <span className="unsaved-changes"> (unsaved changes)</span>}
        </h3>
        <div className="editor-actions">
          <button
            onClick={validateScript}
            disabled={validationStatus === 'validating' || !localScript.trim()}
            className="validate-button"
          >
            ✓ Validate (Ctrl+S)
          </button>
          <button onClick={applyChanges} disabled={!hasUnsavedChanges} className="apply-button">
            ▶ Apply (Ctrl+Enter)
          </button>
          <button onClick={resetScript} disabled={!hasUnsavedChanges} className="reset-button">
            ↻ Reset
          </button>
        </div>
      </div>

      <div className="editor-content">
        <Editor
          height="100%"
          defaultLanguage="python"
          value={localScript}
          onChange={handleEditorChange}
          onMount={handleEditorMount}
          theme="vs-dark"
          options={{
            minimap: { enabled: false },
            fontSize: 14,
            lineNumbers: 'on',
            roundedSelection: false,
            scrollBeyondLastLine: false,
            automaticLayout: true,
            tabSize: 4,
            insertSpaces: true,
            wordWrap: 'on',
            folding: true,
            lineDecorationsWidth: 0,
            lineNumbersMinChars: 3,
            glyphMargin: false,
            formatOnPaste: true,
            formatOnType: true,
          }}
        />
      </div>

      <div className={`editor-status ${validationStatus}`}>
        <span className="status-icon">{getStatusIcon()}</span>
        <span>{getStatusText()}</span>
      </div>
    </div>
  );
}
