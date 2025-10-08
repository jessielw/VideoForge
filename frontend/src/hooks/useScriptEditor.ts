import { useState, useRef, useCallback } from 'react';
import { API } from '../api/base';

interface UseScriptEditorProps {
  script: string;
  onScriptChange: (script: string) => void;
  onValidate?: () => void;
  onApply?: () => void;
}

export function useScriptEditor({
  script,
  onScriptChange,
  onValidate,
  onApply,
}: UseScriptEditorProps) {
  const [localScript, setLocalScript] = useState(script);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [validationStatus, setValidationStatus] = useState<
    'idle' | 'validating' | 'valid' | 'error'
  >('idle');
  const [validationMessage, setValidationMessage] = useState<string>('');
  const editorRef = useRef<any>(null);

  const handleEditorChange = useCallback(
    (value: string | undefined) => {
      const newValue = value || '';
      setLocalScript(newValue);
      setHasUnsavedChanges(newValue !== script);
      setValidationStatus('idle'); // Reset validation when editing
    },
    [script]
  );

  const applyChanges = useCallback(() => {
    // Validate before applying. We expect validateScript to set validationStatus.
    (async () => {
      try {
        const valid = await validateScript();
        if (!valid) return; // don't apply if validation failed

        onScriptChange(localScript);
        setHasUnsavedChanges(false);
        if (onApply) {
          onApply();
        }
      } catch (err) {
        console.error('Error during apply:', err);
      }
    })();
  }, [localScript, onScriptChange, onApply]);

  const validateScript = useCallback(async () => {
    if (!localScript.trim()) {
      setValidationStatus('error');
      setValidationMessage('Script cannot be empty');
      return;
    }

    setValidationStatus('validating');
    setValidationMessage('');

    try {
      const response = await fetch(`${API}/api/script/validate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          script: localScript,
        }),
      });

      if (response.ok) {
        const result = await response.json();
        if (result.valid) {
          setValidationStatus('valid');
          setValidationMessage('Script is valid');
          if (onValidate) onValidate();
          return true;
        } else {
          setValidationStatus('error');
          setValidationMessage(result.error || 'Script validation failed');
          if (onValidate) onValidate();
          return false;
        }
      } else {
        throw new Error('Validation request failed');
      }
    } catch (error) {
      setValidationStatus('error');
      setValidationMessage('Failed to validate script');
      console.error('Script validation error:', error);
      if (onValidate) onValidate();
      return false;
    }
  }, [localScript, onValidate]);

  const handleEditorMount = useCallback(
    (editor: any, monaco: any) => {
      editorRef.current = editor;

      // Add keyboard shortcuts
      // Ctrl+S now performs Apply (validate + apply)
      editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
        applyChanges();
      });

      // Ctrl+Enter also performs Apply
      editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => {
        applyChanges();
      });
    },
    [applyChanges]
  );

  const resetScript = useCallback(() => {
    setLocalScript(script);
    setHasUnsavedChanges(false);
    setValidationStatus('idle');
    setValidationMessage('');
  }, [script]);

  // Force-set the local script from outside callers (used for hard reset)
  const forceSetLocalScript = useCallback((newScript: string) => {
    setLocalScript(newScript);
    setHasUnsavedChanges(false);
    setValidationStatus('idle');
    setValidationMessage('');
  }, []);

  return {
    localScript,
    hasUnsavedChanges,
    validationStatus,
    validationMessage,
    editorRef,
    handleEditorChange,
    applyChanges,
    validateScript,
    handleEditorMount,
    resetScript,
    forceSetLocalScript,
  };
}
