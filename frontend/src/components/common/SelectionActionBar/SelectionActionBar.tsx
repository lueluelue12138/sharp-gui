import type { ReactNode } from 'react';

import { CloseIcon } from '@/components/common/Icons';

import styles from './SelectionActionBar.module.css';

export interface SelectionActionBarAction {
  id: string;
  icon: ReactNode;
  label?: ReactNode;
  ariaLabel: string;
  tooltip?: string;
  disabled?: boolean;
  busy?: boolean;
  variant?: 'primary' | 'default' | 'danger';
  onClick: () => void;
}

interface SelectionActionBarProps {
  className?: string;
  selectedCount: number;
  selectedLabel: string;
  countAriaLabel: string;
  actions: SelectionActionBarAction[];
  clearLabel: string;
  onClear: () => void;
}

export function SelectionActionBar({
  className,
  selectedCount,
  selectedLabel,
  countAriaLabel,
  actions,
  clearLabel,
  onClear,
}: SelectionActionBarProps) {
  if (selectedCount === 0) {
    return null;
  }

  const primaryActionCount = actions.filter((action) => action.variant === 'primary').length;
  const utilityActionCount = actions.length - primaryActionCount;

  return (
    <div
      className={[
        styles.bar,
        primaryActionCount > 1 ? styles.withTwoPrimary : '',
        utilityActionCount === 0 ? styles.withoutUtility : '',
        className,
      ].filter(Boolean).join(' ')}
      role="toolbar"
      aria-label={countAriaLabel}
    >
      <span className={styles.count} role="status" aria-live="polite" aria-label={countAriaLabel}>
        <strong>{selectedCount}</strong>
        <span>{selectedLabel}</span>
      </span>

      {actions.map((action) => {
        const variant = action.variant ?? 'default';
        return (
          <button
            key={action.id}
            className={[
              variant === 'primary' ? styles.primaryBtn : styles.iconBtn,
              variant === 'danger' ? styles.dangerBtn : '',
            ].filter(Boolean).join(' ')}
            onClick={action.onClick}
            disabled={action.disabled}
            type="button"
            data-tooltip={action.tooltip ?? action.ariaLabel}
            aria-label={action.ariaLabel}
            aria-busy={action.busy || undefined}
          >
            {action.icon}
            {action.label ? <span>{action.label}</span> : null}
          </button>
        );
      })}

      <button
        className={styles.clearBtn}
        onClick={onClear}
        type="button"
        data-tooltip={clearLabel}
        aria-label={clearLabel}
      >
        <CloseIcon width={16} height={16} />
      </button>
    </div>
  );
}
