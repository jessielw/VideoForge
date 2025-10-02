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
  maxFrames: number;
  script?: string;
  onScriptChange?: (script: string) => void;
}

const API = "http://127.0.0.1:8000";

export function useAutoCropDetection({ 
  inputPath, 
  maxFrames, 
  script, 
  onScriptChange 
}: UseAutoCropDetectionProps) {
  const [autoCropDetecting, setAutoCropDetecting] = useState(false);
  const [autoCropResult, setAutoCropResult] = useState<AutoCropResult | null>(null);

  // Analyze a single frame for crop detection
  const analyzeFrameForCrop = useCallback((imageUrl: string): Promise<CropData | null> => {
    return new Promise((resolve) => {
      const img = new Image();
      img.crossOrigin = 'anonymous';
      
      img.onload = () => {
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        if (!ctx) {
          resolve(null);
          return;
        }
        
        canvas.width = img.width;
        canvas.height = img.height;
        ctx.drawImage(img, 0, 0);
        
        const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
        const data = imageData.data;
        
        // Detect black bars by analyzing edge rows/columns
        const threshold = 35; // Slightly higher brightness threshold for "black" pixels
        const tolerance = 0.92; // 92% of pixels must be below threshold (slightly more lenient)
        const minCropSize = 8; // Minimum crop size to avoid detecting noise as crop
        
        // Detect top crop
        let topCrop = 0;
        for (let y = 0; y < canvas.height; y++) {
          let darkPixels = 0;
          for (let x = 0; x < canvas.width; x++) {
            const idx = (y * canvas.width + x) * 4;
            const brightness = (data[idx] + data[idx + 1] + data[idx + 2]) / 3;
            if (brightness < threshold) darkPixels++;
          }
          const darkRatio = darkPixels / canvas.width;
          if (darkRatio < tolerance) break;
          topCrop = y + 1;
        }
        // Only consider significant crops
        if (topCrop < minCropSize) topCrop = 0;
        
        // Detect bottom crop
        let bottomCrop = 0;
        for (let y = canvas.height - 1; y >= 0; y--) {
          let darkPixels = 0;
          for (let x = 0; x < canvas.width; x++) {
            const idx = (y * canvas.width + x) * 4;
            const brightness = (data[idx] + data[idx + 1] + data[idx + 2]) / 3;
            if (brightness < threshold) darkPixels++;
          }
          const darkRatio = darkPixels / canvas.width;
          if (darkRatio < tolerance) break;
          bottomCrop = canvas.height - y;
        }
        // Only consider significant crops
        if (bottomCrop < minCropSize) bottomCrop = 0;
        
        // Detect left crop
        let leftCrop = 0;
        for (let x = 0; x < canvas.width; x++) {
          let darkPixels = 0;
          for (let y = 0; y < canvas.height; y++) {
            const idx = (y * canvas.width + x) * 4;
            const brightness = (data[idx] + data[idx + 1] + data[idx + 2]) / 3;
            if (brightness < threshold) darkPixels++;
          }
          const darkRatio = darkPixels / canvas.height;
          if (darkRatio < tolerance) break;
          leftCrop = x + 1;
        }
        // Only consider significant crops
        if (leftCrop < minCropSize) leftCrop = 0;
        
        // Detect right crop
        let rightCrop = 0;
        for (let x = canvas.width - 1; x >= 0; x--) {
          let darkPixels = 0;
          for (let y = 0; y < canvas.height; y++) {
            const idx = (y * canvas.width + x) * 4;
            const brightness = (data[idx] + data[idx + 1] + data[idx + 2]) / 3;
            if (brightness < threshold) darkPixels++;
          }
          const darkRatio = darkPixels / canvas.height;
          if (darkRatio < tolerance) break;
          rightCrop = canvas.width - x;
        }
        // Only consider significant crops
        if (rightCrop < minCropSize) rightCrop = 0;
        
        resolve({
          left: leftCrop,
          top: topCrop,
          right: rightCrop,
          bottom: bottomCrop
        });
      };
      
      img.onerror = () => resolve(null);
      img.src = imageUrl;
    });
  }, []);

  // Calculate recommended crop from multiple detections
  const calculateRecommendedCrop = useCallback((detections: Array<{frame: number, crop: CropData}>) => {
    if (detections.length === 0) {
      return { left: 0, top: 0, right: 0, bottom: 0 };
    }
    
    console.log('🔍 Individual frame detections:', detections);
    
    // Round down to nearest even number (important for video encoding)
    const roundDownToEven = (num: number) => {
      const rounded = Math.floor(num);
      return rounded % 2 === 0 ? rounded : rounded - 1;
    };
    
    // Find consistent values across frames (must appear in at least 70% of frames)
    const findConsistentValue = (values: number[], tolerance = 10) => {
      const roundedValues = values.map(v => roundDownToEven(v));
      const consistencyThreshold = Math.ceil(values.length * 0.7); // 70% of frames
      
      // Group similar values (within tolerance)
      const groups: {[key: number]: number[]} = {};
      
      for (const value of roundedValues) {
        let foundGroup = false;
        
        // Check if this value fits in an existing group
        for (const [groupKey, groupValues] of Object.entries(groups)) {
          const groupKeyNum = parseInt(groupKey);
          if (Math.abs(value - groupKeyNum) <= tolerance) {
            groupValues.push(value);
            foundGroup = true;
            break;
          }
        }
        
        // Create new group if no existing group found
        if (!foundGroup) {
          groups[value] = [value];
        }
      }
      
      // Find the group with most consistent values
      let bestGroup: number[] = [];
      let bestGroupKey = 0;
      
      for (const [groupKey, groupValues] of Object.entries(groups)) {
        if (groupValues.length >= consistencyThreshold && groupValues.length > bestGroup.length) {
          bestGroup = groupValues;
          bestGroupKey = parseInt(groupKey);
        }
      }
      
      console.log(`📊 Value groups:`, groups);
      console.log(`✅ Best group (${bestGroup.length}/${values.length} frames):`, bestGroup);
      
      // If no group meets consistency threshold, return 0 (no crop)
      if (bestGroup.length < consistencyThreshold) {
        console.log(`⚠️ No consistent value found (need ${consistencyThreshold}/${values.length} frames)`);
        return 0;
      }
      
      // Return the most common value in the best group
      return bestGroupKey;
    };
    
    const leftValues = detections.map(d => d.crop.left);
    const topValues = detections.map(d => d.crop.top);
    const rightValues = detections.map(d => d.crop.right);
    const bottomValues = detections.map(d => d.crop.bottom);
    
    const result = {
      left: findConsistentValue(leftValues),
      top: findConsistentValue(topValues),
      right: findConsistentValue(rightValues),
      bottom: findConsistentValue(bottomValues)
    };
    
    console.log('🎯 Final consistent crop values:', result);
    return result;
  }, []);

  // Auto crop detection function
  const detectAutoCrop = useCallback(async () => {
    if (!inputPath || autoCropDetecting) return;
    
    setAutoCropDetecting(true);
    console.log('🔍 Starting auto crop detection...');
    
    try {
      // Sample 10 frames spread throughout the video
      const sampleFrames = [];
      const frameStep = Math.max(1, Math.floor(maxFrames / 10));
      
      for (let i = 0; i < 10; i++) {
        const frameNum = Math.min(i * frameStep, maxFrames - 1);
        sampleFrames.push(frameNum);
      }
      
      console.log(`📊 Sampling frames: ${sampleFrames.join(', ')}`);
      
      const cropDetections = [];
      
      // Analyze each sample frame
      for (const frameNum of sampleFrames) {
        try {
          const url = `${API}/api/frame?path=${encodeURIComponent(inputPath)}&frame=${frameNum}`;
          const resp = await fetch(url);
          
          if (resp.ok) {
            const blob = await resp.blob();
            const imageUrl = URL.createObjectURL(blob);
            
            // Analyze the frame for crop detection
            const cropData = await analyzeFrameForCrop(imageUrl);
            if (cropData) {
              cropDetections.push({
                frame: frameNum,
                crop: cropData
              });
            }
            
            // Clean up blob URL
            URL.revokeObjectURL(imageUrl);
          }
        } catch (error) {
          console.warn(`⚠️ Failed to analyze frame ${frameNum}:`, error);
        }
      }
      
      // Calculate recommended crop from all detections
      const recommendedCrop = calculateRecommendedCrop(cropDetections);
      console.log('✅ Auto crop detection complete!');
      console.log('📏 Recommended crop:', recommendedCrop);
      console.log('📊 All detections:', cropDetections);
      
      // Append crop command to script if detected
      if (recommendedCrop.left > 0 || recommendedCrop.top > 0 || recommendedCrop.right > 0 || recommendedCrop.bottom > 0) {
        const cropCommand = `# Auto-detected crop (remove comment to apply):\n# clip = core.std.Crop(clip, left=${recommendedCrop.left}, top=${recommendedCrop.top}, right=${recommendedCrop.right}, bottom=${recommendedCrop.bottom})`;
        
        if (onScriptChange && script) {
          const updatedScript = script + '\n\n' + cropCommand;
          onScriptChange(updatedScript);
          console.log('📝 Crop command appended to script');
          
          // Show success feedback
          setAutoCropResult({
            success: true,
            command: cropCommand,
            crop: recommendedCrop
          });
        } else {
          console.log('📋 Crop command generated:', cropCommand);
          setAutoCropResult({
            success: false,
            command: cropCommand,
            crop: recommendedCrop
          });
        }
      } else {
        console.log('ℹ️ No significant crop detected');
        setAutoCropResult({
          success: true,
          command: null,
          crop: recommendedCrop
        });
      }
      
      // Clear result after a few seconds
      setTimeout(() => {
        setAutoCropResult(null);
      }, 4000);
      
    } catch (error) {
      console.error('❌ Auto crop detection failed:', error);
      setAutoCropResult({
        success: false,
        command: null,
        crop: null
      });
      
      // Clear error after a few seconds
      setTimeout(() => {
        setAutoCropResult(null);
      }, 4000);
    } finally {
      setAutoCropDetecting(false);
    }
  }, [inputPath, maxFrames, script, onScriptChange, analyzeFrameForCrop, calculateRecommendedCrop, autoCropDetecting]);

  return {
    autoCropDetecting,
    autoCropResult,
    detectAutoCrop
  };
}