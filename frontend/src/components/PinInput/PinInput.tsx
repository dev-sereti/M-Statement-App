import React, { useState, useEffect } from 'react';
import './PinInput.css';

interface Props {
  onSubmit: (pin: string) => void;
  attemptsLeft: number;
  isLoading: boolean;
  isLocked: boolean;
  lockoutSeconds: number;
}

const PinInput: React.FC<Props> = ({
  onSubmit,
  attemptsLeft,
  isLoading,
  isLocked,
  lockoutSeconds,
}) => {
  const [pin, setPin] = useState('');
  const [showPin, setShowPin] = useState(false);
  const [countdown, setCountdown] = useState(lockoutSeconds);

  useEffect(() => {
    if (isLocked && lockoutSeconds > 0) {
      setCountdown(lockoutSeconds);
      const timer = setInterval(() => {
        setCountdown((prev) => (prev <= 1 ? 0 : prev - 1));
      }, 1000);
      return () => clearInterval(timer);
    }
  }, [isLocked, lockoutSeconds]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!pin.trim() || isLoading || isLocked) return;
    onSubmit(pin);
    setPin('');
  };

  return (
    <div className="pin-container">
      <div className="pin-header">
        <div className="lock-icon">🔐</div>
        <h3>Enter Your Statement PIN</h3>
        <p className="pin-desc">
          The PIN you received via SMS when requesting your MPesa statement.
        </p>
      </div>

      {isLocked ? (
        <div className="lockout-message">
          <p>⚠️ Too many incorrect attempts.</p>
          <p>
            Try again in{' '}
            <strong>
              {Math.floor(countdown / 60)}m {countdown % 60}s
            </strong>
          </p>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="pin-form">
          <div className="pin-input-group">
            <input
              type={showPin ? 'text' : 'password'}
              value={pin}
              onChange={(e) =>
                setPin(e.target.value.replace(/[^0-9+\-]/g, '').slice(0, 20))
              }
              placeholder="Enter PIN"
              disabled={isLoading}
              autoFocus
              className="pin-input"
            />
            <button
              type="button"
              onClick={() => setShowPin(!showPin)}
              className="toggle-visibility"
            >
              {showPin ? '🙈' : '👁️'}
            </button>
          </div>

          {attemptsLeft < 3 && attemptsLeft > 0 && (
            <div className="attempts-warning">
              ⚠️ {attemptsLeft} attempt{attemptsLeft !== 1 ? 's' : ''} remaining
            </div>
          )}

          <button
            type="submit"
            disabled={!pin.trim() || isLoading}
            className="submit-btn"
          >
            {isLoading ? (
              <span className="btn-loading">⏳ Processing...</span>
            ) : (
              '🔓 Unlock & Process'
            )}
          </button>
        </form>
      )}
    </div>
  );
};

export default PinInput;