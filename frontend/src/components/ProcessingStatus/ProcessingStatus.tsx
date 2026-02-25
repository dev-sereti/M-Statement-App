import React from 'react';
import './ProcessingStatus.css';

interface Props {
  status: 'uploading' | 'processing' | 'complete' | 'error';
  message?: string;
}

const ProcessingStatus: React.FC<Props> = ({ status, message }) => {
  const configs = {
    uploading: { icon: '📤', title: 'Uploading' },
    processing: { icon: '⚙️', title: 'Processing' },
    complete: { icon: '✅', title: 'Complete' },
    error: { icon: '❌', title: 'Error' },
  };

  const config = configs[status];
  const isLoading = status === 'uploading' || status === 'processing';

  return (
    <div className={`processing-status status-${status}`}>
      {isLoading ? (
        <div className="spinner-wrapper">
          <div className="spinner"></div>
          <span className="spinner-icon">{config.icon}</span>
        </div>
      ) : (
        <div className="status-icon">{config.icon}</div>
      )}
      <h3>{config.title}</h3>
      {message && <p className="status-message">{message}</p>}
      {isLoading && (
        <div className="security-note">
          🔒 Your data is processed securely
        </div>
      )}
    </div>
  );
};

export default ProcessingStatus;