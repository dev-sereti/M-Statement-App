import React, { useState } from 'react';
import './ResultDownload.css';

interface Props {
  downloadToken: string;
  transactionCount: number;
  accountName?: string;
  statementPeriod?: string;
  warnings?: string[];
  onDownload: () => Promise<void>;
  onReset: () => void;
}

const ResultDownload: React.FC<Props> = ({
  transactionCount,
  accountName,
  statementPeriod,
  warnings = [],
  onDownload,
  onReset,
}) => {
  const [downloading, setDownloading] = useState(false);
  const [downloaded, setDownloaded] = useState(false);
  const [showWarnings, setShowWarnings] = useState(false);

  const handleDownload = async () => {
    setDownloading(true);
    try {
      await onDownload();
      setDownloaded(true);
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="result-download">
      <div className="success-header">
        <div className="success-icon">✅</div>
        <h2>Statement Processed!</h2>
      </div>

      <div className="summary-card">
        <div className="summary-item">
          <span className="label">Transactions</span>
          <span className="value highlight">{transactionCount}</span>
        </div>
        {accountName && (
          <div className="summary-item">
            <span className="label">Account</span>
            <span className="value">{accountName}</span>
          </div>
        )}
        {statementPeriod && (
          <div className="summary-item">
            <span className="label">Period</span>
            <span className="value">{statementPeriod}</span>
          </div>
        )}
      </div>

      {warnings.length > 0 && (
        <div className="warnings">
          <button
            className="warnings-toggle"
            onClick={() => setShowWarnings(!showWarnings)}
          >
            ⚠️ {warnings.length} note{warnings.length !== 1 ? 's' : ''}{' '}
            {showWarnings ? '▲' : '▼'}
          </button>
          {showWarnings && (
            <ul className="warnings-list">
              {warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="excel-features">
        <p>Your Excel file includes:</p>
        <div className="features-grid">
          <span>📊 Summary Dashboard</span>
          <span>📝 All Transactions</span>
          <span>📅 Monthly Breakdown</span>
          <span>📈 Type Analysis</span>
        </div>
      </div>

      <div className="actions">
        <button
          onClick={handleDownload}
          disabled={downloading}
          className={`download-btn ${downloaded ? 'downloaded' : ''}`}
        >
          {downloading
            ? '⏳ Preparing...'
            : downloaded
              ? '✓ Download Again'
              : '📥 Download Excel File'}
        </button>

        <button onClick={onReset} className="reset-btn">
          Process Another Statement
        </button>
      </div>

      <div className="data-notice">
        🔐 Your files are automatically deleted within 30 minutes.
      </div>
    </div>
  );
};

export default ResultDownload;