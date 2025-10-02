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
  onFrameChange 
}: FrameControlsProps): JSX.Element {
  const [sliderFrame, setSliderFrame] = useState(currentFrame);
  const [inputValue, setInputValue] = useState(currentFrame.toString());
  const [isDragging, setIsDragging] = useState(false);
  const debounceTimeoutRef = useRef<number | null>(null);

  // Debounced frame change function
  const debouncedFrameChange = useCallback((frame: number) => {
    if (debounceTimeoutRef.current) {
      clearTimeout(debounceTimeoutRef.current);
    }
    
    debounceTimeoutRef.current = window.setTimeout(() => {
      onFrameChange(frame);
      setIsDragging(false);
    }, 300);
  }, [onFrameChange]);

  // Handle slider changes (immediate visual feedback, debounced API call)
  const handleSliderChange = (newFrame: number) => {
    setSliderFrame(newFrame);
    setIsDragging(true);
    debouncedFrameChange(newFrame);
  };

  // Handle prev/next button clicks (immediate, no debounce needed)
  const handlePrevNext = (newFrame: number) => {
    const clampedFrame = Math.max(0, Math.min(maxFrames - 1, newFrame));
    setSliderFrame(clampedFrame);
    onFrameChange(clampedFrame);
    setIsDragging(false);
    // Cancel any pending debounced changes
    if (debounceTimeoutRef.current) {
      clearTimeout(debounceTimeoutRef.current);
    }
  };

  // Handle text input changes (only visual update, no API call)
  const handleTextInputChange = (value: string) => {
    setInputValue(value);
  };

  // Handle text input blur or Enter key (immediate update)
  const handleTextInputBlur = () => {
    const newFrame = parseInt(inputValue) || 0;
    const clampedFrame = Math.max(0, Math.min(maxFrames - 1, newFrame));
    setInputValue(clampedFrame.toString());
    setSliderFrame(clampedFrame);
    onFrameChange(clampedFrame);
    setIsDragging(false);
    // Cancel any pending debounced changes
    if (debounceTimeoutRef.current) {
      clearTimeout(debounceTimeoutRef.current);
    }
  };

  // Handle Enter key press in text input
  const handleTextInputKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleTextInputBlur();
    }
  };

  // Sync input value and slider with current frame when not dragging
  useEffect(() => {
    if (!isDragging) {
      setSliderFrame(currentFrame);
      setInputValue(currentFrame.toString());
    }
  }, [currentFrame, isDragging]);

  // Cleanup debounce timeout on unmount
  useEffect(() => {
    return () => {
      if (debounceTimeoutRef.current) {
        clearTimeout(debounceTimeoutRef.current);
      }
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
          onChange={(e) => handleTextInputChange(e.target.value)}
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
        onChange={(e) => handleSliderChange(parseInt(e.target.value))}
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