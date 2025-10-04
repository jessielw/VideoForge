import React, { useState, useRef, useEffect, useCallback } from 'react';
import FrameControls from './FrameControls';
import ZoomControls from './ZoomControls';
import DisplayEffects from './DisplayEffects';
import AutoCropModal from './AutoCropModal';
import { useAutoCropDetection } from '../../hooks/useAutoCropDetection';
import { useOverlay } from '../../context/OverlayContext';

interface FramePreviewProps {
  inputPath: string;
  script?: string;
  indexInfo: any;
  onScriptChange?: (script: string) => void;
  // A numeric counter; increment to trigger a preview fetch (applies the script)
  previewVersion?: number;
  onPreviewError?: (err: string | null) => void;
  // Parent-driven reset signal to force widget reset
  resetSignal?: number;
}

export default function FramePreview({
  inputPath,
  script,
  indexInfo,
  onScriptChange,
  previewVersion = 0,
  onPreviewError,
  resetSignal,
}: FramePreviewProps & { resetSignal?: number }): JSX.Element {
  const [currentFrame, setCurrentFrame] = useState(0);
  const [frameImage, setFrameImage] = useState<string | null>(null);
  const [scriptError, setScriptError] = useState<string | null>(null);
  const [originalFrameImage, setOriginalFrameImage] = useState<string | null>(null); // Store original image
  const [loading, setLoading] = useState(false);
  const [frameMeta, setFrameMeta] = useState<any | null>(null);
  const [currentCrop, setCurrentCrop] = useState({ left: 0, top: 0, right: 0, bottom: 0 });
  const [zoomLevel, setZoomLevel] = useState(100); // Zoom percentage
  const [sampleCount, setSampleCount] = useState<number>(20);
  const [isPanning, setIsPanning] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [scrollStart, setScrollStart] = useState({ x: 0, y: 0 });
  const pointerIdRef = useRef<number | null>(null);
  const [viewportPos, setViewportPos] = useState({ left: 0, top: 0 }); // For minimap
  const [isScrolling, setIsScrolling] = useState(false); // For wheel scroll minimap
  const [displayEffect, setDisplayEffect] = useState<'none' | 'edge_detect'>('none'); // Display effects

  const imageRef = useRef<HTMLImageElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const scrollTimeoutRef = useRef<number | null>(null);

  // Use VapourSynth probe results for preview. If the probe isn't present,
  // fall back to safe defaults.
  const vsInfo = indexInfo?.vapoursynth || {};

  const maxFrames = (typeof vsInfo.frames === 'number' && vsInfo.frames) || 1000;
  const videoWidth = (typeof vsInfo.width === 'number' && vsInfo.width) || 1920;
  const videoHeight = (typeof vsInfo.height === 'number' && vsInfo.height) || 1080;

  const API = 'http://127.0.0.1:8000';
  const overlay = useOverlay();

  // Use the auto crop detection hook
  const { autoCropDetecting, autoCropResult, detectAutoCrop } = useAutoCropDetection({
    inputPath,
    script,
    onScriptChange,
  });

  // Reset processing state when a new source is opened. This ensures the
  // Processing page returns to sane defaults (frame 0, no image, default zoom/crop)
  // so the UI is in a predictable state when switching sources.
  useEffect(() => {
    // Revoke any created object URLs to avoid leaking memory
    try {
      if (frameImage) {
        URL.revokeObjectURL(frameImage);
      }
    } catch (e) {
      // ignore
    }
    try {
      if (originalFrameImage) {
        URL.revokeObjectURL(originalFrameImage);
      }
    } catch (e) {
      // ignore
    }

    setCurrentFrame(0);
    setFrameImage(null);
    setOriginalFrameImage(null);
    setScriptError(null);
    setFrameMeta(null);
    setCurrentCrop({ left: 0, top: 0, right: 0, bottom: 0 });
    setZoomLevel(100);
    setIsPanning(false);
    setViewportPos({ left: 0, top: 0 });
    setIsScrolling(false);
    setDisplayEffect('none');
  }, [inputPath]);

  // Also respond to an explicit reset signal from the parent
  React.useEffect(() => {
    if (typeof resetSignal === 'number') {
      // mirror inputPath reset behavior
      try {
        if (frameImage) URL.revokeObjectURL(frameImage);
      } catch (e) {}
      try {
        if (originalFrameImage) URL.revokeObjectURL(originalFrameImage);
      } catch (e) {}

      setCurrentFrame(0);
      setFrameImage(null);
      setOriginalFrameImage(null);
      setScriptError(null);
      setFrameMeta(null);
      setCurrentCrop({ left: 0, top: 0, right: 0, bottom: 0 });
      setZoomLevel(100);
      setIsPanning(false);
      setViewportPos({ left: 0, top: 0 });
      setIsScrolling(false);
      setDisplayEffect('none');
    }
  }, [resetSignal]);

  // Zoom control functions
  const setZoom = (zoom: number) => {
    setZoomLevel(zoom);
  };

  const handleMouseWheel = (e: React.WheelEvent) => {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      const delta = e.deltaY > 0 ? -50 : 50;
      const newZoom = Math.max(100, Math.min(800, zoomLevel + delta));
      setZoomLevel(newZoom);
    } else if (zoomLevel > 100) {
      // Show minimap during regular scrolling when zoomed
      setIsScrolling(true);
      updateViewportPosition();

      // Clear existing timeout
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current);
      }

      // Hide minimap after scrolling stops
      scrollTimeoutRef.current = window.setTimeout(() => {
        setIsScrolling(false);
      }, 1000); // Hide after 1 second of no scrolling
    }
  };

  const handleDoubleClick = () => {
    const zoomLevels = [100, 150, 200, 300, 400, 500, 600, 700, 800];
    const currentIndex = zoomLevels.indexOf(zoomLevel);

    if (currentIndex === -1 || currentIndex === zoomLevels.length - 1) {
      setZoomLevel(100); // Return to fit if at max or custom zoom
    } else {
      setZoomLevel(zoomLevels[currentIndex + 1]); // Go to next zoom level
    }
  };

  // Update viewport position for minimap
  const updateViewportPosition = () => {
    const viewport = containerRef.current;
    if (!viewport) return;

    // Calculate the maximum scroll distances
    const maxScrollLeft = Math.max(0, viewport.scrollWidth - viewport.clientWidth);
    const maxScrollTop = Math.max(0, viewport.scrollHeight - viewport.clientHeight);

    if (maxScrollLeft > 0 || maxScrollTop > 0) {
      // Calculate percentage position (0-100%)
      const leftPercent = maxScrollLeft > 0 ? (viewport.scrollLeft / maxScrollLeft) * 100 : 0;
      const topPercent = maxScrollTop > 0 ? (viewport.scrollTop / maxScrollTop) * 100 : 0;

      setViewportPos({ left: leftPercent, top: topPercent });
    } else {
      setViewportPos({ left: 0, top: 0 });
    }
  };

  // Drag/Pan functionality
  // Use pointer events for more reliable panning (including touch)
  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (zoomLevel > 100) {
      const elem = e.currentTarget;
      pointerIdRef.current = e.pointerId;
      try {
        elem.setPointerCapture(pointerIdRef.current);
      } catch (err) {
        // ignore if capture fails
      }
      setIsPanning(true);
      setDragStart({ x: e.clientX, y: e.clientY });
      setScrollStart({ x: elem.scrollLeft, y: elem.scrollTop });
      e.preventDefault();
    }
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (isPanning && containerRef.current && pointerIdRef.current === e.pointerId) {
      const deltaX = dragStart.x - e.clientX;
      const deltaY = dragStart.y - e.clientY;

      containerRef.current.scrollLeft = scrollStart.x + deltaX;
      containerRef.current.scrollTop = scrollStart.y + deltaY;

      // Update viewport position for minimap
      updateViewportPosition();
    }
  };

  const handlePointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    const elem = e.currentTarget;
    if (pointerIdRef.current === e.pointerId) {
      try {
        elem.releasePointerCapture(e.pointerId);
      } catch (err) {
        // ignore
      }
      pointerIdRef.current = null;
      setIsPanning(false);
    }
  };

  const handlePointerCancel = (e: React.PointerEvent<HTMLDivElement>) => {
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch (err) {
      // ignore
    }
    pointerIdRef.current = null;
    setIsPanning(false);
  };

  // Fetch frame image (processed with script when available)
  const fetchFrame = async (frame: number) => {
    if (!inputPath) return;

    setLoading(true);
    overlay.show({
      type: 'loading',
      message: 'Loading frame preview...',
    });

    try {
      let url = `${API}/api/frame?path=${encodeURIComponent(inputPath)}&frame=${frame}`;

      if (script && script.trim()) {
        // Add script as query parameter for processed frame
        url += `&script=${encodeURIComponent(script)}`;
        console.log('🎬 Fetching processed frame with script');
      } else {
        console.log('🎬 Fetching original frame (no script)');
      }

      const resp = await fetch(url);
      if (resp.ok) {
        const blob = await resp.blob();
        const imageUrl = URL.createObjectURL(blob);
        setOriginalFrameImage(imageUrl); // Store original
        // Clear any previous script error on successful fetch
        setScriptError(null);
        if (onPreviewError) onPreviewError(null);

        // Read metadata header (if provided)
        try {
          const metaHeader = resp.headers.get('X-Frame-Meta');
          if (metaHeader) {
            try {
              const parsed = JSON.parse(metaHeader);
              setFrameMeta(parsed);
            } catch (err) {
              console.warn('Failed to parse X-Frame-Meta header:', err);
              setFrameMeta(null);
            }
          } else {
            setFrameMeta(null);
          }
        } catch (err) {
          console.warn('Failed to read X-Frame-Meta header:', err);
          setFrameMeta(null);
        }

        // Apply current display effect to new frame, or show original if none
        if (displayEffect === 'none') {
          setFrameImage(imageUrl);
        } else {
          // Re-apply the current display effect to the new frame
          setTimeout(() => {
            applyDisplayEffect(displayEffect);
          }, 50); // Small delay to ensure image is loaded
        }

        console.log('✅ Frame fetched successfully');
      } else {
        const errorText = await resp.text();
        console.error('❌ Failed to fetch frame:', resp.status, errorText);
        // Surface the error to the user in the preview area
        const errMsg = errorText || `Frame request failed: ${resp.status}`;
        setScriptError(errMsg);
        if (onPreviewError) onPreviewError(errMsg);
        setFrameImage(null);
        setOriginalFrameImage(null);
        setFrameMeta(null);
      }
    } catch (error) {
      console.error('💥 Error fetching frame:', error);
      const errMsg = String(error);
      setScriptError(errMsg);
      if (onPreviewError) onPreviewError(errMsg);
      setFrameImage(null);
      setOriginalFrameImage(null);
      setFrameMeta(null);
    } finally {
      setLoading(false);
      overlay.hide();
    }
  };

  // Only fetch frames when previewVersion changes (user pressed Apply/Preview).
  // This prevents auto previewing on page open or on every script edit.
  useEffect(() => {
    if (previewVersion <= 0) return;
    if (inputPath) {
      fetchFrame(currentFrame);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewVersion, currentFrame]);

  // Show AutoCropModal in the global overlay when detecting or when results are available
  useEffect(() => {
    if (autoCropDetecting || autoCropResult) {
      overlay.show({
        type: 'autocrop',
        customContent: (
          <AutoCropModal autoCropDetecting={autoCropDetecting} autoCropResult={autoCropResult} />
        ),
      });
    } else {
      // Only hide if the overlay is currently showing autocrop content
      if (overlay.state.type === 'autocrop') {
        overlay.hide();
      }
    }
  }, [autoCropDetecting, autoCropResult]);

  // Track scroll position for minimap
  useEffect(() => {
    const viewport = containerRef.current;
    if (!viewport) return;

    // Update on scroll
    viewport.addEventListener('scroll', updateViewportPosition);

    // Initial update
    updateViewportPosition();

    return () => {
      viewport.removeEventListener('scroll', updateViewportPosition);
    };
  }, [zoomLevel, frameImage]);

  // Apply display effects to the image
  const applyDisplayEffect = (effect: 'none' | 'edge_detect') => {
    if (!originalFrameImage || !canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const img = new Image();
    img.crossOrigin = 'anonymous';

    img.onload = () => {
      canvas.width = img.width;
      canvas.height = img.height;
      ctx.drawImage(img, 0, 0);

      if (effect === 'none') {
        // Just show original
        setFrameImage(originalFrameImage);
        setDisplayEffect('none');
        return;
      }

      const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const data = imageData.data;

      if (effect === 'edge_detect') {
        // Simple edge detection
        const width = canvas.width;
        const height = canvas.height;
        const newData = new Uint8ClampedArray(data);

        // Convert to grayscale and apply edge detection
        for (let y = 1; y < height - 1; y++) {
          for (let x = 1; x < width - 1; x++) {
            const idx = (y * width + x) * 4;

            // Get surrounding pixels (grayscale)
            const gray = (pixel: number) => {
              const i = pixel * 4;
              return data[i] * 0.299 + data[i + 1] * 0.587 + data[i + 2] * 0.114;
            };

            // Sobel operator
            const gx =
              -gray((y - 1) * width + (x - 1)) +
              gray((y - 1) * width + (x + 1)) +
              -2 * gray(y * width + (x - 1)) +
              2 * gray(y * width + (x + 1)) +
              -gray((y + 1) * width + (x - 1)) +
              gray((y + 1) * width + (x + 1));

            const gy =
              -gray((y - 1) * width + (x - 1)) -
              2 * gray((y - 1) * width + x) -
              gray((y - 1) * width + (x + 1)) +
              gray((y + 1) * width + (x - 1)) +
              2 * gray((y + 1) * width + x) +
              gray((y + 1) * width + (x + 1));

            const magnitude = Math.sqrt(gx * gx + gy * gy);
            const edge = Math.min(255, magnitude * 2);

            // Invert for better visibility (bright edges on dark background)
            const inverted = 255 - edge;

            newData[idx] = inverted; // R
            newData[idx + 1] = inverted; // G
            newData[idx + 2] = inverted; // B
            // Alpha stays the same
          }
        }

        // Copy new data
        for (let i = 0; i < data.length; i++) {
          data[i] = newData[i];
        }
      }

      ctx.putImageData(imageData, 0, 0);

      // Convert canvas to blob and create new URL
      canvas.toBlob(blob => {
        if (blob) {
          const processedUrl = URL.createObjectURL(blob);
          setFrameImage(processedUrl);
          setDisplayEffect(effect);
        }
      }, 'image/png');
    };

    img.src = originalFrameImage;
  };

  return (
    <div className="frame-preview">
      <div className="preview-header">
        <div className="preview-title-row">
          <h3>Frame Preview</h3>

          <DisplayEffects
            displayEffect={displayEffect}
            onEffectChange={applyDisplayEffect}
            // Bind current sampleCount so the click event isn't forwarded as the argument
            onAutoCropDetect={() => detectAutoCrop(sampleCount)}
            autoCropDetecting={autoCropDetecting}
            disabled={!inputPath}
            onSampleCountChange={setSampleCount}
          />
        </div>

        <ZoomControls zoomLevel={zoomLevel} onZoomChange={setZoom} />

        <FrameControls
          currentFrame={currentFrame}
          maxFrames={maxFrames}
          loading={loading}
          onFrameChange={setCurrentFrame}
        />
      </div>

      <div className="preview-container" style={{ padding: '20px' }}>
        {/* Show script/runtime errors from preview processing */}
        {scriptError && (
          <div className="preview-error-panel">
            <div className="preview-error-header">
              <strong>Preview error</strong>
            </div>
            <pre className="preview-error-body">{scriptError}</pre>
          </div>
        )}
        <div
          className={`image-viewport ${zoomLevel > 100 ? 'draggable' : ''}`}
          ref={containerRef}
          onWheel={handleMouseWheel}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerCancel}
          onDoubleClick={handleDoubleClick}
          style={{
            maxHeight: zoomLevel > 100 ? '50vh' : 'none', // Only constrain height when zoomed
          }}
        >
          {frameImage && (
            <div className={`image-container ${zoomLevel !== 100 ? 'zoomed' : ''}`}>
              <div
                className="image-wrapper"
                style={{
                  display: 'inline-block',
                  width: 'auto',
                  height: 'auto',
                }}
              >
                <img
                  ref={imageRef}
                  src={frameImage}
                  alt="Frame preview"
                  className="frame-image"
                  style={{
                    opacity: loading ? 0.7 : 1,
                    width: zoomLevel === 100 ? '100%' : `calc(100% * ${zoomLevel / 100})`,
                    height: 'auto',
                    display: 'block',
                    cursor: zoomLevel > 100 ? (isPanning ? 'grabbing' : 'grab') : 'default',
                  }}
                  onClick={e => e.preventDefault()}
                  onContextMenu={e => e.preventDefault()}
                  draggable={false}
                />

                {/* Hidden canvas for image processing */}
                <canvas ref={canvasRef} style={{ display: 'none' }} />

                {/* Show simple crop overlay if crop is active */}
                {(currentCrop.left > 0 ||
                  currentCrop.top > 0 ||
                  currentCrop.right > 0 ||
                  currentCrop.bottom > 0) && (
                  <div className="crop-overlay">
                    {currentCrop.top > 0 && (
                      <div
                        className="crop-border crop-top"
                        style={{ height: `${(currentCrop.top / videoHeight) * 100}%` }}
                      />
                    )}
                    {currentCrop.bottom > 0 && (
                      <div
                        className="crop-border crop-bottom"
                        style={{ height: `${(currentCrop.bottom / videoHeight) * 100}%` }}
                      />
                    )}
                    {currentCrop.left > 0 && (
                      <div
                        className="crop-border crop-left"
                        style={{
                          width: `${(currentCrop.left / videoWidth) * 100}%`,
                          top: `${(currentCrop.top / videoHeight) * 100}%`,
                          height: `${
                            ((videoHeight - currentCrop.top - currentCrop.bottom) / videoHeight) *
                            100
                          }%`,
                        }}
                      />
                    )}
                    {currentCrop.right > 0 && (
                      <div
                        className="crop-border crop-right"
                        style={{
                          width: `${(currentCrop.right / videoWidth) * 100}%`,
                          top: `${(currentCrop.top / videoHeight) * 100}%`,
                          height: `${
                            ((videoHeight - currentCrop.top - currentCrop.bottom) / videoHeight) *
                            100
                          }%`,
                        }}
                      />
                    )}
                    <div className="crop-info-overlay">
                      <div className="crop-dimensions">
                        Output: {videoWidth - currentCrop.left - currentCrop.right} ×{' '}
                        {videoHeight - currentCrop.top - currentCrop.bottom}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Simple minimap overlay during panning or scrolling - positioned outside viewport */}
        {(isPanning || isScrolling) && zoomLevel > 100 && frameImage && (
          <div className="minimap-overlay">
            <div className="minimap">
              <div className="minimap-image">
                <img src={frameImage} alt="Overview" />
                <div
                  className="minimap-viewport"
                  style={{
                    width: `${100 / (zoomLevel / 100)}%`,
                    height: `${100 / (zoomLevel / 100)}%`,
                    left: `${viewportPos.left * (1 - 1 / (zoomLevel / 100))}%`,
                    top: `${viewportPos.top * (1 - 1 / (zoomLevel / 100))}%`,
                  }}
                />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Frame metadata display */}
      <div className="frame-meta">
        {frameMeta &&
        (frameMeta.format ||
          frameMeta.width ||
          frameMeta.height ||
          frameMeta.fps ||
          frameMeta.frame_type) ? (
          <div className="frame-meta-row">
            <span>Format: {frameMeta.format ?? '—'}</span>
            <span>
              Size: {frameMeta.width ?? '—'} × {frameMeta.height ?? '—'}
            </span>
            <span>
              FPS:{' '}
              {frameMeta.fps != null
                ? Number(frameMeta.fps)
                    .toFixed(3)
                    .replace(/\.000$/, '')
                : '—'}
            </span>
            <span>Frame type: {frameMeta.frame_type ?? '—'}</span>
          </div>
        ) : (
          <div className="frame-meta-row">No frame metadata available</div>
        )}
      </div>
    </div>
  );
}
