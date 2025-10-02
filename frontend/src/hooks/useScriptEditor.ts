import { useState, useRef, useCallback } from 'react';

interface UseScriptEditorProps {
  script: string;
  onScriptChange: (script: string) => void;
  onValidate?: () => void;
  onApply?: () => void;
}

const API = "http://127.0.0.1:8000";

export function useScriptEditor({ script, onScriptChange, onValidate, onApply }: UseScriptEditorProps) {
  const [localScript, setLocalScript] = useState(script);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [validationStatus, setValidationStatus] = useState<'idle' | 'validating' | 'valid' | 'error'>('idle');
  const [validationMessage, setValidationMessage] = useState<string>('');
  const editorRef = useRef<any>(null);

  const handleEditorChange = useCallback((value: string | undefined) => {
    const newValue = value || '';
    setLocalScript(newValue);
    setHasUnsavedChanges(newValue !== script);
    setValidationStatus('idle'); // Reset validation when editing
  }, [script]);

  const applyChanges = useCallback(() => {
    onScriptChange(localScript);
    setHasUnsavedChanges(false);
    if (onApply) {
      onApply();
    }
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
        } else {
          setValidationStatus('error');
          setValidationMessage(result.error || 'Script validation failed');
        }
      } else {
        throw new Error('Validation request failed');
      }
    } catch (error) {
      setValidationStatus('error');
      setValidationMessage('Failed to validate script');
      console.error('Script validation error:', error);
    }

    if (onValidate) {
      onValidate();
    }
  }, [localScript, onValidate]);

  const handleEditorMount = useCallback((editor: any, monaco: any) => {
    editorRef.current = editor;
    
    // Add keyboard shortcuts
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
      validateScript();
    });
    
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => {
      applyChanges();
    });
  }, [validateScript, applyChanges]);

  const resetScript = useCallback(() => {
    setLocalScript(script);
    setHasUnsavedChanges(false);
    setValidationStatus('idle');
    setValidationMessage('');
  }, [script]);

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
    resetScript
  };
}