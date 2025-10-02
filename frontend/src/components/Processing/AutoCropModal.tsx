import React from 'react';

interface AutoCropResult {
  success: boolean;
  command: string | null;
  crop: {
    left: number;
    top: number;
    right: number;
    bottom: number;
  } | null;
}

interface AutoCropModalProps {
  autoCropDetecting: boolean;
  autoCropResult: AutoCropResult | null;
}

export default function AutoCropModal({ autoCropDetecting, autoCropResult }: AutoCropModalProps): JSX.Element | null {
  if (!autoCropDetecting && !autoCropResult) {
    return null;
  }

  return (
    <div className="auto-crop-modal-overlay">
      <div className="auto-crop-modal">
        {autoCropDetecting ? (
          <>
            <div className="auto-crop-spinner">⏳</div>
            <h3>Detecting Auto Crop</h3>
            <p>Analyzing frames to detect letterboxing and black bars...</p>
            <div className="progress-text">This may take a few seconds</div>
          </>
        ) : autoCropResult ? (
          <>
            {autoCropResult.success ? (
              <>
                {autoCropResult.command ? (
                  <>
                    <div className="auto-crop-success">✅</div>
                    <h3>Crop Detected & Added!</h3>
                    <p>Auto crop command has been appended to your script:</p>
                    <div className="crop-command-display">
                      <code>{autoCropResult.command}</code>
                    </div>
                    <div className="crop-values">
                      Left: {autoCropResult.crop?.left}, Top: {autoCropResult.crop?.top}, 
                      Right: {autoCropResult.crop?.right}, Bottom: {autoCropResult.crop?.bottom}
                    </div>
                    <div className="progress-text">Remove the # comment to apply the crop!</div>
                  </>
                ) : (
                  <>
                    <div className="auto-crop-info">ℹ️</div>
                    <h3>No Crop Needed</h3>
                    <p>No significant letterboxing or black bars detected.</p>
                    <div className="progress-text">Your video appears to be full frame!</div>
                  </>
                )}
              </>
            ) : (
              <>
                <div className="auto-crop-error">❌</div>
                <h3>Detection Failed</h3>
                <p>Unable to detect crop or update script.</p>
                <div className="progress-text">Please try again or crop manually</div>
              </>
            )}
          </>
        ) : null}
      </div>
    </div>
  );
}