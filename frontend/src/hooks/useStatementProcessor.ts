import { useState, useCallback } from 'react';
import type { ProcessorState } from '@/types';
import { apiService } from '@/services/api';

const INITIAL_STATE: ProcessorState = {
  step: 'idle',
  sessionId: null,
  isEncrypted: false,
  downloadToken: null,
  transactionCount: 0,
  error: null,
  warnings: [],
  attemptsLeft: 3,
  isLocked: false,
  lockoutSeconds: 0,
  accountName: '',
  statementPeriod: '',
};

export const useStatementProcessor = () => {
  const [state, setState] = useState<ProcessorState>(INITIAL_STATE);

  const processStatement = useCallback(
    async (sessionId: string, pin?: string) => {
      setState((prev) => ({ ...prev, step: 'processing', error: null }));

      try {
        const data = await apiService.processStatement(sessionId, pin);

        setState((prev) => ({
          ...prev,
          step: 'complete',
          downloadToken: data.download_token ?? null,
          transactionCount: data.transaction_count,
          warnings: data.parsing_warnings || [],
          accountName: data.account_name || '',
          statementPeriod: data.statement_period || '',
          error: null,
        }));
      } catch (error: unknown) {
        const message =
          error instanceof Error ? error.message : 'Processing failed';

        // Check if PIN error (keep on pin_required step)
        setState((prev) => ({
          ...prev,
          step: prev.isEncrypted ? 'pin_required' : 'error',
          error: message,
          attemptsLeft: Math.max(0, prev.attemptsLeft - 1),
        }));
      }
    },
    []
  );

  const handleUploadSuccess = useCallback(
    (sessionId: string, isEncrypted: boolean) => {
      setState((prev) => ({
        ...prev,
        sessionId,
        isEncrypted,
        step: isEncrypted ? 'pin_required' : 'processing',
        error: null,
      }));

      if (!isEncrypted) {
        processStatement(sessionId);
      }
    },
    [processStatement]
  );

  const handlePinSubmit = useCallback(
    (pin: string) => {
      if (state.sessionId) {
        processStatement(state.sessionId, pin);
      }
    },
    [state.sessionId, processStatement]
  );

  const handleDownload = useCallback(async () => {
    if (!state.downloadToken) return;

    try {
      const blob = await apiService.downloadFile(state.downloadToken);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `MPesa_Statement_${new Date().toISOString().split('T')[0]}.xlsx`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch {
      setState((prev) => ({ ...prev, error: 'Download failed' }));
    }
  }, [state.downloadToken]);

  const reset = useCallback(() => {
    setState(INITIAL_STATE);
  }, []);

  return { state, handleUploadSuccess, handlePinSubmit, handleDownload, reset };
};