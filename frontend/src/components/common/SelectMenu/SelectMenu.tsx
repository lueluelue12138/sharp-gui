import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';

import { CheckIcon, ChevronDownIcon } from '@/components/common/Icons';

import styles from './SelectMenu.module.css';

export interface SelectMenuOption {
  value: string;
  label: string;
  icon?: ReactNode;
}

interface SelectMenuProps {
  value: string;
  options: SelectMenuOption[];
  onChange: (value: string) => void;
  ariaLabel: string;
  icon?: ReactNode;
  compact?: boolean;
  showSelectedLabel?: boolean;
  disabled?: boolean;
  className?: string;
  portal?: boolean;
}

export function SelectMenu({
  value,
  options,
  onChange,
  ariaLabel,
  icon,
  compact = false,
  showSelectedLabel = true,
  disabled = false,
  className = '',
  portal = false,
}: SelectMenuProps) {
  const listboxId = useId();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [isOpen, setIsOpen] = useState(false);

  const selectedOption = useMemo(
    () => options.find((option) => option.value === value) ?? options[0],
    [options, value],
  );

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const handlePointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node) && !menuRef.current?.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsOpen(false);
        if (portal && menuRef.current?.contains(document.activeElement)) rootRef.current?.querySelector('button')?.focus();
      }
    };

    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, portal]);

  useLayoutEffect(() => {
    if (!portal || !isOpen || disabled) return;
    const positionMenu = () => {
      const trigger = rootRef.current?.querySelector('button'); const menu = menuRef.current;
      if (!trigger || !menu) return;
      const rect = trigger.getBoundingClientRect();
      const width = Math.min(Math.max(rect.width, 176), window.innerWidth - 16);
      const above = Math.max(0, rect.top - 16);
      const below = Math.max(0, window.innerHeight - rect.bottom - 16);
      const height = Math.min(menu.scrollHeight, 300);
      const opensAbove = below < height && above > below;
      const visibleHeight = Math.min(height, opensAbove ? above : below);
      menu.style.width = `${width}px`;
      menu.style.maxHeight = `${visibleHeight}px`;
      menu.style.left = `${Math.max(8, Math.min(rect.right - width, window.innerWidth - width - 8))}px`;
      menu.style.top = `${opensAbove ? rect.top - visibleHeight - 8 : rect.bottom + 8}px`;
    };
    positionMenu();
    menuRef.current?.querySelector<HTMLButtonElement>('[aria-selected="true"]')?.focus({ preventScroll: true });
    window.addEventListener('resize', positionMenu);
    window.addEventListener('scroll', positionMenu, true);
    return () => {
      window.removeEventListener('resize', positionMenu);
      window.removeEventListener('scroll', positionMenu, true);
    };
  }, [portal, isOpen, disabled, options.length]);

  const handleSelect = useCallback((nextValue: string) => {
    onChange(nextValue);
    setIsOpen(false);
    rootRef.current?.querySelector('button')?.focus({ preventScroll: true });
  }, [onChange]);

  const menu = isOpen && !disabled ? (
    <div ref={menuRef} id={listboxId} className={[styles.menu, portal && styles.portalMenu].filter(Boolean).join(' ')} role="listbox" aria-label={ariaLabel} onKeyDown={event => {
      if (!portal) return;
      const buttons = [...event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="option"]')];
      const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
      if (event.key === 'Tab') {
        setIsOpen(false); rootRef.current?.querySelector('button')?.focus();
      } else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
        event.preventDefault();
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : (index + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length;
        buttons[next]?.focus();
      }
    }}>
      {options.map((option) => {
        const isSelected = option.value === value;
        return (
          <button key={option.value} className={[styles.option, isSelected ? styles.optionSelected : ''].filter(Boolean).join(' ')} type="button" role="option" aria-selected={isSelected} onClick={() => handleSelect(option.value)}>
            <span className={styles.optionLabel}>
              {option.icon ? <span className={styles.optionDirection}>{option.icon}</span> : null}
              <span className={styles.optionText}>{option.label}</span>
            </span>
            {isSelected ? <CheckIcon width={15} height={15} /> : null}
          </button>
        );
      })}
    </div>
  ) : null;

  return (
    <div
      ref={rootRef}
      className={[
        styles.root,
        compact ? styles.compact : '',
        !showSelectedLabel ? styles.iconOnly : '',
        className,
      ].filter(Boolean).join(' ')}
    >
      <button
        className={styles.trigger}
        type="button"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-controls={listboxId}
        disabled={disabled}
        onClick={() => setIsOpen((current) => !current)}
      >
        {icon ? <span className={styles.triggerIcon}>{icon}</span> : null}
        {showSelectedLabel ? <span className={styles.triggerLabel}>{selectedOption?.label}</span> : null}
        {showSelectedLabel && selectedOption?.icon ? (
          <span className={styles.triggerDirection}>{selectedOption.icon}</span>
        ) : null}
        <ChevronDownIcon width={15} height={15} />
      </button>

      {portal && menu ? createPortal(menu, document.body) : menu}
    </div>
  );
}
