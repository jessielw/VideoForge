import React, { useEffect, useRef, ReactNode } from 'react';
import FocusTrap from 'focus-trap-react';
import '../../styles/blockingoverlay.css';

interface BlockingOverlayProps {
  visible: boolean;
  message?: string;
  type?: 'loading' | 'indexing' | 'autocrop' | 'probe-failure' | 'custom';
  children?: ReactNode;
  dismissible?: boolean;
  onDismiss?: () => void;
}

export default function BlockingOverlay({
  visible,
  message,
  type = 'loading',
  children,
  dismissible = false,
  onDismiss,
}: BlockingOverlayProps): JSX.Element | null {
  const overlayRef = useRef<HTMLDivElement>(null);

  // Lock body scroll when overlay is visible
  useEffect(() => {
    if (visible) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }

    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [visible]);

  // Handle escape key for dismissible overlays
  useEffect(() => {
    if (!visible || !dismissible || !onDismiss) return;

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onDismiss();
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [visible, dismissible, onDismiss]);

  if (!visible) return null;

  // Render custom content (like AutoCropModal) if provided
  if (children) {
    return (
      <FocusTrap
        focusTrapOptions={{
          allowOutsideClick: true,
          escapeDeactivates: dismissible,
          fallbackFocus: () => overlayRef.current || document.body,
        }}
      >
        <div className="blocking-overlay" ref={overlayRef} tabIndex={-1}>
          <div className="blocking-overlay-backdrop" />
          <div className="blocking-overlay-content">{children}</div>
        </div>
      </FocusTrap>
    );
  }

  // Render simple spinner + message for standard types
  const getIcon = () => {
    switch (type) {
      case 'indexing':
        return '⏳';
      case 'loading':
        return '⏳';
      case 'autocrop':
        return '🔍';
      case 'probe-failure':
        return '⚠️';
      default:
        return '⏳';
    }
  };

  const getTitle = () => {
    switch (type) {
      case 'indexing':
        return 'Indexing source';
      case 'loading':
        return 'Loading';
      case 'autocrop':
        return 'Detecting Auto Crop';
      case 'probe-failure':
        return 'Probe Failed';
      default:
        return 'Please wait';
    }
  };

  return (
    <FocusTrap
      focusTrapOptions={{
        allowOutsideClick: true,
        escapeDeactivates: dismissible,
        fallbackFocus: () => overlayRef.current || document.body,
      }}
    >
      <div className="blocking-overlay" ref={overlayRef} tabIndex={-1}>
        <div className="blocking-overlay-backdrop" />
        <div className="blocking-overlay-panel" tabIndex={0}>
          <div className="blocking-overlay-spinner">{getIcon()}</div>
          <h3>{getTitle()}</h3>
          {message && <p>{message}</p>}
          {dismissible && onDismiss && (
            <button onClick={onDismiss} className="blocking-overlay-dismiss">
              Dismiss
            </button>
          )}
        </div>
      </div>
    </FocusTrap>
  );
}
