import type { ReactNode, MouseEvent } from 'react';
import { useEffect, useId } from 'react';
import { createPortal } from 'react-dom';

import { useTranslation } from 'react-i18next';

import { CloseIcon } from '@/components/common/Icons';
import styles from './Modal.module.css';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
  showCloseButton?: boolean;
  size?: 'sm' | 'md' | 'lg';
  portal?: boolean;
}

export function Modal({
  isOpen,
  onClose,
  title,
  children,
  showCloseButton = true,
  size = 'md',
  portal = false,
}: ModalProps) {
  const { t } = useTranslation();
  const titleId = useId();
  // Handle escape key
  useEffect(() => {
    if (!isOpen) return;
    
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !e.defaultPrevented) {
        e.preventDefault();
        onClose();
      }
    };
    
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen, onClose]);

  // Prevent body scroll when modal is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  if (!isOpen) return null;

  const handleBackdropClick = (e: MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  const dialog = (
    <div className={portal ? `${styles.backdrop} ${styles.portalBackdrop}` : styles.backdrop} onClick={handleBackdropClick}>
      <div
        className={`${styles.modal} ${styles[size]}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
      >
        {(title || showCloseButton) && (
          <div className={styles.header}>
            {title && <h3 id={titleId} className={styles.title}>{title}</h3>}
            {showCloseButton && (
              <button className={styles.closeButton} onClick={onClose} aria-label={t('close')}>
                <CloseIcon width={16} height={16} />
              </button>
            )}
          </div>
        )}
        <div className={styles.content}>{children}</div>
      </div>
    </div>
  );
  return portal ? createPortal(dialog, document.body) : dialog;
}
