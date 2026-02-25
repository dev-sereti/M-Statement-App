import React from 'react';
import FileUpload from './components/FileUpload/FileUpload';
import PinInput from './components/PinInput/PinInput';
import ProcessingStatus from './components/ProcessingStatus/ProcessingStatus';
import ResultDownload from './components/ResultDownload/ResultDownload';
import { useStatementProcessor } from './hooks/useStatementProcessor';
import './App.css';

const App: React.FC = () => {
  const { state, handleUploadSuccess, handlePinSubmit, handleDownload, reset } =
    useStatementProcessor();

  const renderContent = () => {
    switch (state.step) {
      case 'idle':
        return (
          <FileUpload
            onUploadSuccess={handleUploadSuccess}
            onError={(msg) => console.error('Upload error:', msg)}
            isLoading={false}
          />
        );

      case 'uploading':
        return (
          <ProcessingStatus status="uploading" message="Uploading your statement..." />
        );

      case 'pin_required':
        return (
          <div className="pin-step">
            <ProcessingStatus status="complete" message="File uploaded successfully" />
            <PinInput
              onSubmit={handlePinSubmit}
              attemptsLeft={state.attemptsLeft}
              isLoading={false}
              isLocked={state.isLocked}
              lockoutSeconds={state.lockoutSeconds}
            />
            {state.error && (
              <div className="error-banner">
                <span>⚠️</span> {state.error}
              </div>
            )}
          </div>
        );

      case 'processing':
        return (
          <ProcessingStatus
            status="processing"
            message="Extracting transactions from your statement..."
          />
        );

      case 'complete':
        return (
          <ResultDownload
            downloadToken={state.downloadToken!}
            transactionCount={state.transactionCount}
            accountName={state.accountName}
            statementPeriod={state.statementPeriod}
            warnings={state.warnings}
            onDownload={handleDownload}
            onReset={reset}
          />
        );

      case 'error':
        return (
          <div className="error-state">
            <div className="error-icon">❌</div>
            <h2>Something went wrong</h2>
            <p>{state.error}</p>
            <button className="retry-btn" onClick={reset}>
              Try Again
            </button>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-content">
          <h1>📊 MPesa Statement Processor</h1>
          <p>Convert your MPesa PDF statements to Excel instantly</p>
        </div>
      </header>

      <main className="app-main">{renderContent()}</main>

      <footer className="app-footer">
        <div className="footer-badges">
          <span>🔒 Secure</span>
          <span>🗑️ Auto-Delete</span>
          <span>📱 Mobile Friendly</span>
        </div>
        <p>© {new Date().getFullYear()} MPesa Statement Processor</p>
      </footer>
    </div>
  );
};

export default App;