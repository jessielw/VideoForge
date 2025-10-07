import '../../styles/UI/CriticalErrorOverlay.css';

interface Props {
  message: string;
}

export default function CriticalErrorOverlay({ message }: Props): JSX.Element {
  return (
    <div className="critical-error-container">
      <h3 className="critical-error-title">A critical error occurred</h3>
      <p className="critical-error-message">{message}</p>
      <div className="critical-error-actions">
        <button
          className="critical-error-reload themed-btn"
          onClick={() => {
            window.location.reload();
          }}
        >
          Reload
        </button>
      </div>
    </div>
  );
}
