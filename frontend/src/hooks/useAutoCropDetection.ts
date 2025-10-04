import { useState, useCallback } from 'react';

interface CropData {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

interface AutoCropResult {
  success: boolean;
  command: string | null;
  crop: CropData | null;
}

interface UseAutoCropDetectionProps {
  inputPath: string;
  script?: string;
  onScriptChange?: (script: string) => void;
}

const API = 'http://127.0.0.1:8000';

export function useAutoCropDetection({
  inputPath,
  script,
  onScriptChange,
}: UseAutoCropDetectionProps) {
  const [autoCropDetecting, setAutoCropDetecting] = useState(false);
  const [autoCropResult, setAutoCropResult] = useState<AutoCropResult | null>(null);

  // Now requires an explicit numeric sampleCount parameter (10..100)
  const detectAutoCrop = useCallback(
    async (sampleCount: number) => {
      if (!inputPath || autoCropDetecting) return;
      const sampleCountNum = Math.max(10, Math.min(100, Math.floor(sampleCount)));

      setAutoCropDetecting(true);
      try {
        const resp = await fetch(`${API}/api/auto-crop`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: inputPath, sample_count: sampleCountNum }),
        });

        if (!resp.ok) {
          throw new Error(`Auto-crop request failed: ${resp.status}`);
        }

        const j = await resp.json();
        if (!j.ok) {
          throw new Error(j.error || 'Auto-crop failed');
        }

        const recommendedCrop: CropData = j.recommendedCrop || {
          left: 0,
          top: 0,
          right: 0,
          bottom: 0,
        };

        if (
          recommendedCrop.left > 0 ||
          recommendedCrop.top > 0 ||
          recommendedCrop.right > 0 ||
          recommendedCrop.bottom > 0
        ) {
          const cropCommand = `# Auto-detected crop (remove comment to apply):\n# clip = core.std.Crop(clip, left=${recommendedCrop.left}, top=${recommendedCrop.top}, right=${recommendedCrop.right}, bottom=${recommendedCrop.bottom})`;
          if (onScriptChange && script) {
            const updatedScript = script + '\n\n' + cropCommand;
            onScriptChange(updatedScript);
          }
          setAutoCropResult({ success: true, command: cropCommand, crop: recommendedCrop });
        } else {
          setAutoCropResult({ success: true, command: null, crop: recommendedCrop });
        }

        // Clear result after a few seconds
        setTimeout(() => setAutoCropResult(null), 3000);
      } catch (error) {
        console.error('Auto crop failed:', error);
        setAutoCropResult({ success: false, command: null, crop: null });
        setTimeout(() => setAutoCropResult(null), 4000);
      } finally {
        setAutoCropDetecting(false);
      }
    },
    [inputPath, script, onScriptChange, autoCropDetecting]
  );

  return {
    autoCropDetecting,
    autoCropResult,
    detectAutoCrop,
  };
}
