import { useMemo } from 'react';

import { useTranslation } from 'react-i18next';

import { CheckIcon, CloseIcon, CloudUploadIcon } from '@/components/common/Icons';
import { Modal } from '@/components/common/Modal';

import styles from './ModelAssetImportDialog.module.css';

const ignoreClose = () => undefined;

export type ModelAssetImportPhase = 'uploading' | 'complete' | 'error';
export type ModelAssetImportFileStatus = 'pending' | 'success' | 'error';

export interface ModelAssetImportFileEntry {
  id: string;
  name: string;
  status: ModelAssetImportFileStatus;
  error?: string | null;
}

interface ModelAssetImportDialogProps {
  isOpen: boolean;
  phase: ModelAssetImportPhase;
  progress: number;
  files: ModelAssetImportFileEntry[];
  importedCount: number;
  failedCount: number;
  errorMessage?: string | null;
  showViewLibrary: boolean;
  onClose: () => void;
  onOpenLibrary: () => void;
}

export function ModelAssetImportDialog({
  isOpen,
  phase,
  progress,
  files,
  importedCount,
  failedCount,
  errorMessage,
  showViewLibrary,
  onClose,
  onOpenLibrary,
}: ModelAssetImportDialogProps) {
  const { t } = useTranslation();
  const isUploading = phase === 'uploading';
  const safeProgress = Math.max(0, Math.min(100, Math.round(progress)));
  const statusText = useMemo(() => {
    if (isUploading) {
      return t('modelAssetImportDialogUploading', { count: files.length });
    }
    if (phase === 'error') {
      return t('modelAssetImportDialogFailed');
    }
    return t('modelAssetImportDialogComplete', {
      count: importedCount,
      failed: failedCount,
    });
  }, [failedCount, files.length, importedCount, isUploading, phase, t]);

  return (
    <Modal
      isOpen={isOpen}
      onClose={isUploading ? ignoreClose : onClose}
      title={t('modelAssetImportDialogTitle')}
      showCloseButton={!isUploading}
      size="lg"
    >
      <div className={styles.content}>
        <div className={styles.summary} aria-live="polite">
          <div className={[
            styles.iconShell,
            phase === 'complete' && failedCount === 0 ? styles.iconShellComplete : '',
            !isUploading && (phase === 'error' || failedCount > 0) ? styles.iconShellError : '',
          ].filter(Boolean).join(' ')}>
            {isUploading ? (
              <CloudUploadIcon width={24} height={24} aria-hidden="true" />
            ) : failedCount === 0 && phase === 'complete' ? (
              <CheckIcon width={24} height={24} aria-hidden="true" />
            ) : (
              <CloseIcon width={22} height={22} aria-hidden="true" />
            )}
          </div>
          <div className={styles.summaryText}>
            <strong>{statusText}</strong>
            <span>
              {isUploading
                ? t('modelAssetImportDialogKeepOpen')
                : failedCount > 0
                  ? t('modelAssetImportDialogRetryHint')
                  : t('modelAssetImportDialogPersisted')}
            </span>
          </div>
          <span className={styles.progressValue}>{safeProgress}%</span>
        </div>

        <div
          className={styles.progressTrack}
          role="progressbar"
          aria-label={t('modelAssetImportDialogProgressLabel')}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={safeProgress}
        >
          <span className={styles.progressFill} style={{ width: `${safeProgress}%` }} />
        </div>

        {errorMessage ? (
          <div className={styles.globalError} role="alert">{errorMessage}</div>
        ) : null}

        <div className={styles.fileList} aria-label={t('modelAssetImportDialogFileList')}>
          {files.map((file) => (
            <div className={styles.fileRow} key={file.id}>
              <span className={[styles.fileStatus, styles[file.status]].join(' ')} aria-hidden="true">
                {file.status === 'success' ? (
                  <CheckIcon width={13} height={13} />
                ) : file.status === 'error' ? (
                  <CloseIcon width={13} height={13} />
                ) : (
                  <span className={styles.pendingDot} />
                )}
              </span>
              <span className={styles.fileInfo}>
                <strong title={file.name}>{file.name}</strong>
                <small className={file.status === 'error' ? styles.fileError : ''}>
                  {file.status === 'pending'
                    ? t('modelAssetImportDialogWaiting')
                    : file.status === 'success'
                      ? t('modelAssetImportDialogImported')
                      : file.error ?? t('modelAssetImportFailed')}
                </small>
              </span>
            </div>
          ))}
        </div>

        {!isUploading ? (
          <div className={styles.actions}>
            {showViewLibrary ? (
              <>
                <button className={styles.secondaryButton} type="button" onClick={onClose}>
                  {t('close')}
                </button>
                <button className={styles.primaryButton} type="button" onClick={onOpenLibrary}>
                  {t('modelAssetImportDialogViewLibrary')}
                </button>
              </>
            ) : (
              <button className={styles.primaryButton} type="button" onClick={onClose}>
                {t('modelAssetImportDialogDone')}
              </button>
            )}
          </div>
        ) : null}
      </div>
    </Modal>
  );
}
