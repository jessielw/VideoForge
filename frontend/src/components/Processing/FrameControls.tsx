import React, { useState, useRef, useEffect, useCallback } from 'react';

interface FrameControlsProps {
  currentFrame: number;
  maxFrames: number;
  loading: boolean;
  onFrameChange: (frame: number) => void;
}

export default function FrameControls({
  currentFrame,
  maxFrames,
  loading,
  onFrameChange,
}: FrameControlsProps): JSX.Element {
  const [sliderFrame, setSliderFrame] = useState(currentFrame);
  const [inputValue, setInputValue] = useState(currentFrame.toString());
  const [isDragging, setIsDragging] = useState(false);
  const debounceTimeoutRef = useRef<number | null>(null);

  // Handle slider changes: update visual state and debounce finalization
  const handleSliderChange = (newFrame: number) => {
    setSliderFrame(newFrame);
    setIsDragging(true);

    if (debounceTimeoutRef.current) {
      clearTimeout(debounceTimeoutRef.current);
    }

    debounceTimeoutRef.current = window.setTimeout(() => {
      const clamped = Math.max(0, Math.min(maxFrames - 1, newFrame));
      setInputValue(clamped.toString());
      onFrameChange(clamped);
      setIsDragging(false);
      debounceTimeoutRef.current = null;
    }, 300);
  };

  // Immediate finalize (used when needed)
  const finalizeSliderChange = useCallback(() => {
    if (debounceTimeoutRef.current) {
      clearTimeout(debounceTimeoutRef.current);
      debounceTimeoutRef.current = null;
    }
    const clamped = Math.max(0, Math.min(maxFrames - 1, sliderFrame));
    setInputValue(clamped.toString());
    onFrameChange(clamped);
    setIsDragging(false);
  }, [onFrameChange, sliderFrame, maxFrames]);

  // Handle prev/next button clicks (immediate)
  const handlePrevNext = (newFrame: number) => {
    const clampedFrame = Math.max(0, Math.min(maxFrames - 1, newFrame));
    setSliderFrame(clampedFrame);
    setInputValue(clampedFrame.toString());
    onFrameChange(clampedFrame);
    setIsDragging(false);
    if (debounceTimeoutRef.current) clearTimeout(debounceTimeoutRef.current);
  };

  // Text input
  const handleTextInputChange = (value: string) => setInputValue(value);

  const handleTextInputBlur = () => {
    const newFrame = parseInt(inputValue) || 0;
    const clampedFrame = Math.max(0, Math.min(maxFrames - 1, newFrame));
    setInputValue(clampedFrame.toString());
    setSliderFrame(clampedFrame);
    onFrameChange(clampedFrame);
    setIsDragging(false);
    if (debounceTimeoutRef.current) clearTimeout(debounceTimeoutRef.current);
  };

  const handleTextInputKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleTextInputBlur();
  };

  useEffect(() => {
    if (!isDragging) {
      setSliderFrame(currentFrame);
      setInputValue(currentFrame.toString());
    }
  }, [currentFrame, isDragging]);

  useEffect(() => {
    return () => {
      if (debounceTimeoutRef.current) clearTimeout(debounceTimeoutRef.current);
    };
  }, []);

  return (
    <div className="frame-controls-header">
      <button
        onClick={() => handlePrevNext(currentFrame - 1)}
        disabled={currentFrame <= 0 || loading}
        className="nav-button"
      >
        ⏮️ Prev
      </button>

      <div className="frame-input-group">
        <input
          type="text"
          value={inputValue}
          onChange={e => handleTextInputChange(e.target.value)}
          onBlur={handleTextInputBlur}
          onKeyPress={handleTextInputKeyPress}
          className="frame-input"
          disabled={loading}
          placeholder="Frame"
        />
        <span className="frame-total">of {maxFrames}</span>
      </div>

      <input
        type="range"
        min="0"
        max={maxFrames - 1}
        value={isDragging ? sliderFrame : currentFrame}
        onChange={e => handleSliderChange(parseInt(e.target.value))}
        className="frame-slider"
        disabled={loading}
      />

      <button
        onClick={() => handlePrevNext(currentFrame + 1)}
        disabled={currentFrame >= maxFrames - 1 || loading}
        className="nav-button"
      >
        Next ⏭️
      </button>
    </div>
  );
}
