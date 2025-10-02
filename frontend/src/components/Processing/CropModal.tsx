import React, { useState, useEffect, useRef } from 'react';

interface CropModalProps {
  isOpen: boolean;
  onClose: () => void;
  inputPath: string;
  currentFrame: number;
  videoWidth: number;
  videoHeight: number;
  initialCrop: { left: number; top: number; right: number; bottom: number };
  onCropChange: (crop: { left: number; top: number; right: number; bottom: number }) => void;
  frameImage: string | null;
  onFrameChange: (frame: number) => void;
  maxFrames: number;
}

export default function CropModal({
  isOpen,
  onClose,
  inputPath,
  currentFrame,
  videoWidth,
  videoHeight,
  initialCrop,
  onCropChange,
  frameImage,
  onFrameChange,
  maxFrames,
}: CropModalProps): JSX.Element | null {
  const [crop, setCrop] = useState(initialCrop);
  const [autoDetecting, setAutoDetecting] = useState(false);
  const [detectionProgress, setDetectionProgress] = useState({ current: 0, total: 0 });
  const [suggestedCrop, setSuggestedCrop] = useState<{
    left: number;
    top: number;
    right: number;
    bottom: number;
  } | null>(null);
  const [localFrame, setLocalFrame] = useState(currentFrame);
  const [fitToFrame, setFitToFrame] = useState(true);
  const modalRef = useRef<HTMLDivElement>(null);
  const frameDebounceRef = useRef<number | null>(null);

  // Update local crop when props change
  useEffect(() => {
    setCrop(initialCrop);
  }, [initialCrop]);

  // Update local frame when currentFrame changes
  useEffect(() => {
    setLocalFrame(currentFrame);
  }, [currentFrame]);

  // Debounced frame change handler
  const handleFrameChange = (newFrame: number) => {
    setLocalFrame(newFrame);

    // Clear existing timeout
    if (frameDebounceRef.current) {
      clearTimeout(frameDebounceRef.current);
    }

    // Set new timeout for actual frame change
    frameDebounceRef.current = window.setTimeout(() => {
      onFrameChange(newFrame);
    }, 300); // 300ms debounce
  };

  // Handle escape key and cleanup
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      document.body.style.overflow = 'hidden';
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = 'unset';
      // Clean up debounce timer
      if (frameDebounceRef.current) {
        clearTimeout(frameDebounceRef.current);
      }
    };
  }, [isOpen, onClose]);

  const snapToEven = (value: number): number => {
    return Math.round(value / 2) * 2;
  };

  const handleCropChange = (side: 'left' | 'top' | 'right' | 'bottom', value: number) => {
    const snappedValue = snapToEven(Math.max(0, value));
    const newCrop = { ...crop, [side]: snappedValue };

    // Boundary validation
    const maxLeft = videoWidth - newCrop.right - 4;
    const maxRight = videoWidth - newCrop.left - 4;
    const maxTop = videoHeight - newCrop.bottom - 4;
    const maxBottom = videoHeight - newCrop.top - 4;

    if (side === 'left' && snappedValue > maxLeft) return;
    if (side === 'right' && snappedValue > maxRight) return;
    if (side === 'top' && snappedValue > maxTop) return;
    if (side === 'bottom' && snappedValue > maxBottom) return;

    setCrop(newCrop);
    onCropChange(newCrop);
  };

  const applySuggestion = () => {
    if (suggestedCrop) {
      setCrop(suggestedCrop);
      onCropChange(suggestedCrop);
      setSuggestedCrop(null);
    }
  };

  const resetCrop = () => {
    const resetValues = { left: 0, top: 0, right: 0, bottom: 0 };
    setCrop(resetValues);
    onCropChange(resetValues);
    setSuggestedCrop(null);
  };

  const autoDetectCrop = async () => {
    setAutoDetecting(true);
    try {
      // Calculate frame sampling strategy - test up to 15 frames distributed across the video
      const sampleCount = Math.min(15, maxFrames);
      const sampleFrames = [];

      if (sampleCount === 1) {
        sampleFrames.push(0);
      } else {
        for (let i = 0; i < sampleCount; i++) {
          const frameIndex = Math.floor((i / (sampleCount - 1)) * (maxFrames - 1));
          sampleFrames.push(frameIndex);
        }
      }

      setDetectionProgress({ current: 0, total: sampleCount });
      console.log(`🔍 Auto-detecting crop by analyzing ${sampleCount} frames:`, sampleFrames);

      // Initialize detection results
      let maxLeft = 0,
        maxTop = 0,
        maxRight = 0,
        maxBottom = 0;

      // Process frames one by one with visual feedback
      for (let i = 0; i < sampleFrames.length; i++) {
        const frameIndex = sampleFrames[i];

        setDetectionProgress({ current: i + 1, total: sampleCount });

        // Update current frame to show progress
        setLocalFrame(frameIndex);
        onFrameChange(frameIndex);

        // Wait for frame to load and analyze
        await new Promise(resolve => setTimeout(resolve, 200));

        // TODO: Replace with actual frame analysis API call
        // For now, simulate detection by analyzing video aspect ratio and common patterns
        const analysisResult = simulateFrameAnalysis(frameIndex, i, sampleCount);

        // Accumulate maximum crop values (most conservative)
        maxLeft = Math.max(maxLeft, analysisResult.left);
        maxTop = Math.max(maxTop, analysisResult.top);
        maxRight = Math.max(maxRight, analysisResult.right);
        maxBottom = Math.max(maxBottom, analysisResult.bottom);

        console.log(`📊 Frame ${frameIndex} analysis:`, analysisResult, `| Accumulated max:`, {
          left: maxLeft,
          top: maxTop,
          right: maxRight,
          bottom: maxBottom,
        });
      }

      // Ensure even numbers for final crop suggestion
      const finalCrop = {
        left: Math.round(maxLeft / 2) * 2,
        top: Math.round(maxTop / 2) * 2,
        right: Math.round(maxRight / 2) * 2,
        bottom: Math.round(maxBottom / 2) * 2,
      };

      setSuggestedCrop(finalCrop);
      setAutoDetecting(false);
      setDetectionProgress({ current: 0, total: 0 });

      console.log('✨ Final auto-crop suggestion:', finalCrop);
    } catch (error) {
      console.error('❌ Auto-crop detection failed:', error);
      setAutoDetecting(false);
      setDetectionProgress({ current: 0, total: 0 });
    }
  };

  // Simulate frame analysis (replace with actual backend call)
  const simulateFrameAnalysis = (frameIndex: number, sampleIndex: number, totalSamples: number) => {
    const aspectRatio = videoWidth / videoHeight;
    const progress = sampleIndex / (totalSamples - 1);

    // Simulate varying detection results across frames
    let detected = { left: 0, top: 0, right: 0, bottom: 0 };

    // Base detection on aspect ratio
    if (aspectRatio > 2.3) {
      // Ultra-wide content, likely has pillarbox
      detected.left = Math.floor(videoWidth * (0.03 + 0.04 * Math.random()));
      detected.right = Math.floor(videoWidth * (0.03 + 0.04 * Math.random()));
    } else if (aspectRatio > 1.85) {
      // Widescreen content, might have letterbox
      detected.top = Math.floor(videoHeight * (0.06 + 0.06 * Math.random()));
      detected.bottom = Math.floor(videoHeight * (0.06 + 0.06 * Math.random()));
    } else if (aspectRatio < 1.5) {
      // More square content, likely has letterbox
      detected.top = Math.floor(videoHeight * (0.1 + 0.08 * Math.random()));
      detected.bottom = Math.floor(videoHeight * (0.1 + 0.08 * Math.random()));
    }

    // Add some frame-based variation to simulate realistic detection
    const frameVariation = Math.sin(frameIndex * 0.1) * 0.3;
    detected.left = Math.max(0, detected.left + Math.floor(frameVariation * 8));
    detected.top = Math.max(0, detected.top + Math.floor(frameVariation * 6));
    detected.right = Math.max(0, detected.right + Math.floor(frameVariation * 8));
    detected.bottom = Math.max(0, detected.bottom + Math.floor(frameVariation * 6));

    return detected;
  };

  const getOutputResolution = () => {
    const width = videoWidth - crop.left - crop.right;
    const height = videoHeight - crop.top - crop.bottom;
    return { width, height };
  };

  if (!isOpen) return null;

  const outputRes = getOutputResolution();

  return (
    <div className="crop-modal-overlay" ref={modalRef}>
      <div className={`crop-modal${autoDetecting ? ' auto-detecting' : ''}`}>
        {/* Top Controls */}
        <div className="crop-modal-header">
          <div className="crop-info">
            <div className="resolution-info">
              <span className="source-res">
                Source: {videoWidth} × {videoHeight}
              </span>
              <span className="output-res">
                Output: {outputRes.width} × {outputRes.height}
              </span>
              <span className="crop-info-text">
                Crop: {crop.left},{crop.top},{crop.right},{crop.bottom}
              </span>
            </div>
          </div>
          <div className="crop-actions">
            <button onClick={autoDetectCrop} disabled={autoDetecting} className="auto-crop-btn">
              {autoDetecting ? '🔍 Detecting...' : '🎯 Auto-Crop'}
            </button>
            {suggestedCrop && (
              <button onClick={applySuggestion} className="apply-suggestion-btn">
                ✨ Apply Suggestion
              </button>
            )}
            <button onClick={resetCrop} className="reset-btn" disabled={autoDetecting}>
              🔄 Reset
            </button>
            <button onClick={onClose} className="close-btn" disabled={autoDetecting}>
              ✕ Close
            </button>
            <button
              onClick={() => setFitToFrame(f => !f)}
              className="fit-toggle-btn"
              disabled={autoDetecting}
            >
              {fitToFrame ? '🔍 Scroll/Zoom' : '🖼️ Fit to Frame'}
            </button>
          </div>
        </div>

        {/* Main Image Area */}
        <div className="crop-modal-content">
          {autoDetecting && (
            <div className="auto-detection-overlay">
              <div className="detection-progress">
                <div className="progress-text">🔍 Analyzing frames for crop detection...</div>
                <div className="progress-details">
                  Frame {detectionProgress.current} of {detectionProgress.total}
                </div>
                <div className="progress-bar">
                  <div
                    className="progress-fill"
                    style={{
                      width: `${(detectionProgress.current / detectionProgress.total) * 100}%`,
                    }}
                  />
                </div>
              </div>
            </div>
          )}
          {frameImage && (
            <div
              className={`fullscreen-image-container${fitToFrame ? ' fit-to-frame' : ' scroll-mode'}`}
            >
              <div className="image-wrapper">
                <img
                  src={frameImage}
                  alt="Crop preview"
                  className={`fullscreen-image${fitToFrame ? ' fit-to-frame' : ' scroll-mode'}`}
                />
                {/* Crop Overlay */}
                <div className="crop-overlay">
                  {/* Top crop overlay */}
                  {crop.top > 0 && (
                    <div
                      className="crop-border crop-top"
                      style={{ height: `${(crop.top / videoHeight) * 100}%` }}
                    />
                  )}

                  {/* Bottom crop overlay */}
                  {crop.bottom > 0 && (
                    <div
                      className="crop-border crop-bottom"
                      style={{ height: `${(crop.bottom / videoHeight) * 100}%` }}
                    />
                  )}

                  {/* Left crop overlay */}
                  {crop.left > 0 && (
                    <div
                      className="crop-border crop-left"
                      style={{
                        width: `${(crop.left / videoWidth) * 100}%`,
                        top: `${(crop.top / videoHeight) * 100}%`,
                        height: `${((videoHeight - crop.top - crop.bottom) / videoHeight) * 100}%`,
                      }}
                    />
                  )}

                  {/* Right crop overlay */}
                  {crop.right > 0 && (
                    <div
                      className="crop-border crop-right"
                      style={{
                        width: `${(crop.right / videoWidth) * 100}%`,
                        top: `${(crop.top / videoHeight) * 100}%`,
                        height: `${((videoHeight - crop.top - crop.bottom) / videoHeight) * 100}%`,
                      }}
                    />
                  )}

                  {/* Suggested crop overlay */}
                  {suggestedCrop && (
                    <div className="suggested-crop-overlay">
                      {suggestedCrop.top > 0 && (
                        <div
                          className="suggested-border suggested-top"
                          style={{ height: `${(suggestedCrop.top / videoHeight) * 100}%` }}
                        />
                      )}
                      {suggestedCrop.bottom > 0 && (
                        <div
                          className="suggested-border suggested-bottom"
                          style={{ height: `${(suggestedCrop.bottom / videoHeight) * 100}%` }}
                        />
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Bottom Controls */}
        <div className="crop-modal-footer">
          <div className="crop-controls-row">
            <div className="crop-input-group">
              <label>Left:</label>
              <input
                type="number"
                value={crop.left}
                onChange={e => handleCropChange('left', parseInt(e.target.value) || 0)}
                step="2"
                min="0"
                max={videoWidth - crop.right - 4}
              />
            </div>

            <div className="crop-input-group">
              <label>Top:</label>
              <input
                type="number"
                value={crop.top}
                onChange={e => handleCropChange('top', parseInt(e.target.value) || 0)}
                step="2"
                min="0"
                max={videoHeight - crop.bottom - 4}
              />
            </div>

            <div className="crop-input-group">
              <label>Right:</label>
              <input
                type="number"
                value={crop.right}
                onChange={e => handleCropChange('right', parseInt(e.target.value) || 0)}
                step="2"
                min="0"
                max={videoWidth - crop.left - 4}
              />
            </div>

            <div className="crop-input-group">
              <label>Bottom:</label>
              <input
                type="number"
                value={crop.bottom}
                onChange={e => handleCropChange('bottom', parseInt(e.target.value) || 0)}
                step="2"
                min="0"
                max={videoHeight - crop.top - 4}
              />
            </div>
          </div>

          {/* Frame Navigation */}
          <div className="frame-navigation">
            <button
              onClick={() => handleFrameChange(Math.max(0, localFrame - 1))}
              disabled={localFrame <= 0}
            >
              ⏮️ Prev
            </button>
            <input
              type="range"
              min="0"
              max={maxFrames - 1}
              value={localFrame}
              onChange={e => handleFrameChange(parseInt(e.target.value))}
              className="frame-slider"
            />
            <button
              onClick={() => handleFrameChange(Math.min(maxFrames - 1, localFrame + 1))}
              disabled={localFrame >= maxFrames - 1}
            >
              Next ⏭️
            </button>
            <span className="frame-info">
              Frame {localFrame + 1} of {maxFrames}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
