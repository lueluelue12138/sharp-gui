import type { ReactNode, MouseEvent } from 'react';
import { useEffect } from 'react';
import { CloseIcon } from '../Icons';
import styles from './Modal.module.css';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
  showCloseButton?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

export function Modal({
  isOpen,
  onClose,
  title,
  children,
  showCloseButton = true,
  size = 'md',
}: ModalProps) {
  // Handle escape key
  useEffect(() => {
    if (!isOpen) return;
    
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
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

  return (
    <div className={styles.backdrop} onClick={handleBackdropClick}>
      <div className={`${styles.modal} ${styles[size]}`}>
        {(title || showCloseButton) && (
          <div className={styles.header}>
            {title && <h3 className={styles.title}>{title}</h3>}
            {showCloseButton && (
              <button className={styles.closeButton} onClick={onClose} aria-label="Close">
                <CloseIcon width={16} height={16} />
              </button>
            )}
          </div>
        )}
        <div className={styles.content}>{children}</div>
      </div>
    </div>
  );
}
