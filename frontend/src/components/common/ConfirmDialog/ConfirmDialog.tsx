import { useTranslation } from 'react-i18next';

import { Button } from '@/components/common/Button';
import { Modal } from '@/components/common/Modal';

import styles from './ConfirmDialog.module.css';

interface ConfirmDialogProps {
  isOpen: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  isBusy?: boolean;
  danger?: boolean;
  onConfirm: () => void;
  onClose: () => void;
  onCancel?: () => void;
}

export function ConfirmDialog({
  isOpen,
  title,
  message,
  confirmLabel,
  cancelLabel,
  isBusy = false,
  danger = false,
  onConfirm,
  onClose,
  onCancel,
}: ConfirmDialogProps) {
  const { t } = useTranslation();

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title} size="sm">
      <div className={styles.body}>
        <p>{message}</p>
        <div className={styles.actions}>
          <Button variant="secondary" onClick={onCancel ?? onClose} disabled={isBusy} type="button">
            {cancelLabel ?? t('cancel')}
          </Button>
          <Button
            variant={danger ? 'danger' : 'primary'}
            onClick={onConfirm}
            disabled={isBusy}
            type="button"
          >
            {confirmLabel ?? t('confirm')}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
