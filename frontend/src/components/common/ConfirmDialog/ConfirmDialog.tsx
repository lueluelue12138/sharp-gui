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
}: ConfirmDialogProps) {
  const { t } = useTranslation();
  const handleClose = () => {
    if (!isBusy) {
      onClose();
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title={title} size="sm">
      <div className={styles.body}>
        <p>{message}</p>
        <div className={styles.actions}>
          <Button variant="secondary" onClick={handleClose} disabled={isBusy} type="button">
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
