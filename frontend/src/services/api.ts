import type { UploadResponse, ProcessResponse } from '@/types';

const API_BASE = '/api/v1';

class ApiService {
  async uploadFile(file: File): Promise<UploadResponse> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE}/upload`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
      throw new Error(error.detail || error.error || 'Upload failed');
    }

    return response.json();
  }

  async processStatement(sessionId: string, pin?: string): Promise<ProcessResponse> {
    const response = await fetch(`${API_BASE}/process`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, pin }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Processing failed' }));
      throw new Error(error.detail || error.error || 'Processing failed');
    }

    return response.json();
  }

  async downloadFile(downloadToken: string): Promise<Blob> {
    const response = await fetch(`${API_BASE}/download/${downloadToken}`);
    if (!response.ok) throw new Error('Download failed');
    return response.blob();
  }

  async healthCheck(): Promise<{ status: string }> {
    const response = await fetch(`${API_BASE}/health`);
    return response.json();
  }
}

export const apiService = new ApiService();