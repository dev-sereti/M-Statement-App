import React, { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { apiService } from '@/services/api';
import './FileUpload.css';

interface Props {
  onUploadSuccess: (sessionId: string, isEncrypted: boolean) => void;
  onError: (message: string) => void;
  isLoading: boolean;
}

const FileUpload: React.FC<Props> = ({ onUploadSuccess, onError, isLoading }) => {
  const [uploading, setUploading] = useState(false);

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      const file = acceptedFiles[0];
      if (!file) return;

      setUploading(true);
      try {
        const data = await apiService.uploadFile(file);
        onUploadSuccess(data.session_id, data.is_encrypted);
      } catch (error: unknown) {
        onError(error instanceof Error ? error.message : 'Upload failed');
      } finally {
        setUploading(false);
      }
    },
    [onUploadSuccess, onError]
  );

  const { getRootProps, getInputProps, isDragActive, fileRejections } =
    useDropzone({
      onDrop,
      accept: { 'application/pdf': ['.pdf'] },
      maxFiles: 1,
      maxSize: 10 * 1024 * 1024,
      disabled: isLoading || uploading,
    });

  return (
    <div className="upload-container">
      <div
        {...getRootProps()}
        className={`dropzone ${isDragActive ? 'active' : ''} ${uploading ? 'uploading' : ''}`}
      >
        <input {...getInputProps()} />
        <div className="dropzone-content">
          <div className="upload-icon">
            {uploading ? '⏳' : '📤'}
          </div>
          {uploading ? (
            <>
              <p><strong>Uploading...</strong></p>
              <div className="upload-spinner"></div>
            </>
          ) : isDragActive ? (
            <p><strong>Drop your MPesa statement here...</strong></p>
          ) : (
            <>
              <p><strong>Drop your MPesa PDF statement here</strong></p>
              <p className="subtitle">or click to browse files</p>
              <p className="constraints">PDF files only • Maximum 10MB</p>
            </>
          )}
        </div>
      </div>

      {fileRejections.length > 0 && (
        <div className="upload-error">
          {fileRejections[0].errors[0].message}
        </div>
      )}
    </div>
  );
};

export default FileUpload;