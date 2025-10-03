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
  const sliderRef = useRef<HTMLInputElement | null>(null);
  const draggingRef = useRef<boolean>(false);

  // Handle slider changes: update visual state and debounce finalization
  const handleSliderChange = (newFrame: number) => {
    setSliderFrame(newFrame);

    // Ensure dragging state is set (pointerdown should normally set this,
    // but keep here as a fallback when events differ across devices).
    setIsDragging(true);

    if (debounceTimeoutRef.current) {
      clearTimeout(debounceTimeoutRef.current);
    }

    // If we're actively dragging (pointerdown has occurred), avoid the
    // short debounce which causes mid-slide finalization if the user
    // pauses briefly. Instead set a longer fallback timer (2s) that will
    // finalize only if pointerup is missed. If not dragging, use a short
    // 300ms debounce to finalize (keyboard or programmatic changes).
    const fallbackDelay = draggingRef.current ? 2000 : 300;
    debounceTimeoutRef.current = window.setTimeout(() => {
      const clamped = Math.max(0, Math.min(maxFrames - 1, newFrame));
      setInputValue(clamped.toString());
      onFrameChange(clamped);
      setIsDragging(false);
      debounceTimeoutRef.current = null;
    }, fallbackDelay);
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
    draggingRef.current = false;
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

  // Attach a global pointerup listener while dragging to ensure we finalize
  // the slide when the user releases the pointer, even if it happens
  // outside the slider element.
  useEffect(() => {
    if (!isDragging) return;

    const onPointerUp = () => {
      // finalize now
      finalizeSliderChange();
    };

    const onPointerCancel = () => {
      // treat cancel like an end
      finalizeSliderChange();
    };

    const onBlurOrHidden = () => {
      // If the window loses focus or the page is hidden, finalize.
      finalizeSliderChange();
    };

    window.addEventListener('pointerup', onPointerUp);
    window.addEventListener('mouseup', onPointerUp);
    window.addEventListener('pointercancel', onPointerCancel);
    window.addEventListener('blur', onBlurOrHidden);
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') onBlurOrHidden();
    });

    return () => {
      window.removeEventListener('pointerup', onPointerUp);
      window.removeEventListener('mouseup', onPointerUp);
      window.removeEventListener('pointercancel', onPointerCancel);
      window.removeEventListener('blur', onBlurOrHidden);
      // no direct remove for visibilitychange anonymous handler
    };
  }, [isDragging, finalizeSliderChange]);

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
          onKeyDown={handleTextInputKeyPress}
          className="frame-input"
          disabled={loading}
          placeholder="Frame"
        />
        <span className="frame-total">of {maxFrames}</span>
        {/* Static tooltip placed at the top-left of the input box while dragging */}
        {isDragging && <div className="frame-static-tooltip">{sliderFrame}</div>}
      </div>

      <div className="frame-slider-wrapper">
        <input
          ref={el => (sliderRef.current = el)}
          type="range"
          min="0"
          max={maxFrames - 1}
          value={isDragging ? sliderFrame : currentFrame}
          onChange={e => handleSliderChange(parseInt(e.target.value))}
          onPointerDown={e => {
            setIsDragging(true);
            draggingRef.current = true;
            // try to capture pointer to get pointerup reliably
            try {
              (e.target as HTMLElement).setPointerCapture?.((e as any).pointerId);
            } catch {}
          }}
          className="frame-slider"
          disabled={loading}
        />
      </div>

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
