export type ProcessingStep =
  | 'idle'
  | 'uploading'
  | 'pin_required'
  | 'processing'
  | 'complete'
  | 'error';

export interface UploadResponse {
  session_id: string;
  filename: string;
  is_encrypted: boolean;
  file_size_kb: number;
  message: string;
}

export interface ProcessResponse {
  success: boolean;
  download_token?: string;
  transaction_count: number;
  parsing_warnings: string[];
  statement_period?: string;
  account_name?: string;
  message: string;
}

export interface ProcessorState {
  step: ProcessingStep;
  sessionId: string | null;
  isEncrypted: boolean;
  downloadToken: string | null;
  transactionCount: number;
  error: string | null;
  warnings: string[];
  attemptsLeft: number;
  isLocked: boolean;
  lockoutSeconds: number;
  accountName: string;
  statementPeriod: string;
}