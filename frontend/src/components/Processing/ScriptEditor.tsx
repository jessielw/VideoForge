import React, { useState, useRef, useEffect } from 'react';
import Editor from '@monaco-editor/react';

interface ScriptEditorProps {
  script: string;
  onScriptChange: (script: string) => void;
  onValidate?: () => void;
  onApply?: () => void;
}

export default function ScriptEditor({ script, onScriptChange, onValidate, onApply }: ScriptEditorProps): JSX.Element {
  const [localScript, setLocalScript] = useState(script);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [validationStatus, setValidationStatus] = useState<'idle' | 'validating' | 'valid' | 'error'>('idle');
  const [validationMessage, setValidationMessage] = useState<string>('');
  const editorRef = useRef<any>(null);

  // Sync external script changes to local state
  useEffect(() => {
    if (script !== localScript && !hasUnsavedChanges) {
      setLocalScript(script);
    }
  }, [script, localScript, hasUnsavedChanges]);

  const handleEditorChange = (value: string | undefined) => {
    const newValue = value || '';
    setLocalScript(newValue);
    setHasUnsavedChanges(newValue !== script);
    setValidationStatus('idle'); // Reset validation when editing
  };

  const applyChanges = () => {
    onScriptChange(localScript);
    setHasUnsavedChanges(false);
    if (onApply) {
      onApply();
    }
  };

  const handleEditorMount = (editor: any, monaco: any) => {
    editorRef.current = editor;
    
    // Add keyboard shortcuts
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
      validateScript();
    });
    
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => {
      applyChanges();
    });
  };

  const validateScript = async () => {
    if (!localScript.trim()) {
      setValidationStatus('idle');
      return;
    }

    setValidationStatus('validating');
    try {
      const response = await fetch('http://127.0.0.1:8000/api/script/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ script: localScript })
      });
      
      const result = await response.json();
      
      if (result.valid) {
        setValidationStatus('valid');
        setValidationMessage('Script is valid');
      } else {
        setValidationStatus('error');
        setValidationMessage(result.error || 'Script validation failed');
      }
    } catch (error) {
      setValidationStatus('error');
      setValidationMessage('Failed to validate script');
    }
  };

  const resetScript = () => {
    setLocalScript(script);
    setHasUnsavedChanges(false);
    setValidationStatus('idle');
  };

  const insertTemplate = () => {
    const template = `import vapoursynth as vs
core = vs.core

# Load video
clip = core.lsmas.LWLibavSource(r'INPUT_PATH')

# Add your filters here
# clip = core.std.Crop(clip, left=0, right=0, top=0, bottom=0)
`;
    setLocalScript(template);
    setHasUnsavedChanges(template !== script);
  };

  return (
    <div className="script-editor">
      <div className="editor-header">
        <h3>VapourSynth Script</h3>
        <div className="editor-actions">
          <button onClick={insertTemplate} className="template-button">
            📄 Template
          </button>
          <button 
            onClick={validateScript} 
            className="validate-button" 
            disabled={validationStatus === 'validating'}
          >
            ✓ Validate (Ctrl+S)
          </button>
          <button 
            onClick={applyChanges} 
            className={`apply-button ${hasUnsavedChanges ? 'apply-button-highlight' : ''}`}
            disabled={!hasUnsavedChanges}
          >
            ▶️ Apply (Ctrl+Enter)
          </button>
          <button onClick={resetScript} className="reset-button">
            🗑️ Reset
          </button>
          {hasUnsavedChanges && <span className="unsaved-indicator">● Unsaved changes</span>}
        </div>
      </div>
      
      {validationStatus !== 'idle' && (
        <div className={`validation-status ${validationStatus}`}>
          {validationStatus === 'validating' && (
            <span>🔄 Validating script...</span>
          )}
          {validationStatus === 'valid' && (
            <span>✅ {validationMessage}</span>
          )}
          {validationStatus === 'error' && (
            <span>❌ {validationMessage}</span>
          )}
        </div>
      )}
      
      <div className="editor-container">
        <Editor
          height="400px"
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
            contextmenu: true,
            selectOnLineNumbers: true,
            glyphMargin: false,
            folding: true,
            foldingHighlight: true,
            foldingStrategy: 'indentation',
            showFoldingControls: 'always',
            matchBrackets: 'always',
            autoIndent: 'full',
            formatOnPaste: true,
            formatOnType: true,
          }}
        />
      </div>
      
      <div className="editor-hints">
        <span>💡 Ctrl+Enter to apply • Ctrl+S to validate • {hasUnsavedChanges ? 'Unsaved changes' : 'All changes saved'}</span>
      </div>
    </div>
  );
}