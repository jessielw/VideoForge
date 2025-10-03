import React, { useEffect } from 'react';
import Editor from '@monaco-editor/react';
import { useScriptEditor } from '../../hooks/useScriptEditor';

interface ScriptEditorProps {
  script: string;
  onScriptChange: (script: string) => void;
  onValidate?: () => void;
  onApply?: () => void;
  selectedPath: string;
}

export default function ScriptEditor({
  script,
  onScriptChange,
  onValidate,
  onApply,
  selectedPath,
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

  // Indexer definitions: key -> label + template generator
  const INDEXERS: Record<string, { label: string; template: (p: string) => string }> = {
    lsmash: {
      label: 'L-Smash (LWLibavSource)',
      template: (p: string) => `clip = core.lsmas.LWLibavSource(r'${p}')`,
    },
    ffms2: {
      label: 'FFMS2',
      template: (p: string) => `clip = core.ffms2.Source(r'${p}')`,
    },
  };

  // Indexer selection state (store the key)
  const [indexer, setIndexer] = React.useState<string>('lsmash');

  // `selectedPath` is required and provided by the parent App. Use it directly.

  // Helper to build a default script template for a given path + indexer key
  const makeTemplateForPath = (key: string, path?: string) => {
    if (!path) return '';
    // Use a Python raw string literal (r'...') to avoid needing to escape
    // backslashes. We still escape single quotes so the JS->Python string is valid.
    const safePath = String(path).replace(/'/g, "\\'");
    const entry = INDEXERS[key];
    const loader = entry
      ? entry.template(safePath)
      : `clip = core.lsmas.LWLibavSource(r'${safePath}')`;
    // Include blank lines and a placeholder comment so the editor shows
    // a tidy starter script the user can edit.
    return `import vapoursynth as vs\ncore = vs.core\n\n# Load source\n${loader}\n\n# Add your filters here\n`;
  };

  // When a new file is selected, if there are no unsaved changes, populate a default script.
  // IMPORTANT: do not include `hasUnsavedChanges` in the dependency list — we only want
  // to run this effect when the selected file or the chosen indexer change. If we
  // included `hasUnsavedChanges`, toggling it (for example after Apply) would cause
  // the template to be re-injected and overwrite the user's script.
  React.useEffect(() => {
    if (selectedPath && !hasUnsavedChanges) {
      const tmpl = makeTemplateForPath(indexer, selectedPath);
      if (tmpl) {
        onScriptChange(tmpl);
      }
    }
    // only run when selectedPath or indexer changes
  }, [selectedPath, indexer, onScriptChange]);

  return (
    <div className="script-editor">
      <div className="editor-header">
        <div className="editor-title">
          <h3>VapourSynth Script</h3>
          {hasUnsavedChanges && <span className="unsaved-changes"> (unsaved changes)</span>}
        </div>
        <div className="editor-actions">
          <div className="indexer-selection">
            <label htmlFor="indexer-select">Indexer:</label>
            <select
              id="indexer-select"
              className="indexer-select"
              value={indexer}
              onChange={e => {
                const newKey = (e as React.ChangeEvent<HTMLSelectElement>).target.value;

                const scriptText = localScript || '';
                const pathForNew = selectedPath;

                const newLoaderCall = INDEXERS[newKey]
                  .template(String(pathForNew).replace(/'/g, "\\'"))
                  .replace(/^clip\s*=\s*/, '')
                  .trim();

                // Safer, line-based replacement: find the line containing a known loader
                // and replace only the RHS after the '=' on that single line.
                const lines = scriptText.split(/\r?\n/);
                const loaderLineIdx = lines.findIndex(l =>
                  /core\.lsmas\.LWLibavSource|core\.ffms2\.Source/.test(l)
                );
                if (loaderLineIdx !== -1) {
                  // Replace everything after the '=' on that line
                  lines[loaderLineIdx] = lines[loaderLineIdx].replace(
                    /(clip\s*=\s*).*/,
                    `$1${newLoaderCall}`
                  );
                  handleEditorChange(lines.join('\n'));
                } else {
                  const tmpl = makeTemplateForPath(newKey, pathForNew);
                  handleEditorChange(tmpl + '\n' + scriptText);
                }

                setIndexer(newKey);
              }}
            >
              {Object.entries(INDEXERS).map(([key, info]) => (
                <option key={key} value={key}>
                  {info.label}
                </option>
              ))}
            </select>
          </div>

          <div className="editor-actions-btn-group">
            <button onClick={applyChanges} disabled={!hasUnsavedChanges} className="apply-button">
              ▶ Apply (Ctrl+S / Ctrl+Enter)
            </button>
            <button onClick={resetScript} disabled={!hasUnsavedChanges} className="reset-button">
              ↻ Reset
            </button>
          </div>
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
