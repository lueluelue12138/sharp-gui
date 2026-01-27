import type { ButtonHTMLAttributes, ReactNode } from 'react';
import styles from './Button.module.css';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  icon?: ReactNode;
  iconOnly?: boolean;
  children?: ReactNode;
}

export function Button({
  variant = 'primary',
  size = 'md',
  icon,
  iconOnly = false,
  children,
  className = '',
  disabled,
  ...props
}: ButtonProps) {
  const classes = [
    styles.button,
    styles[variant],
    styles[size],
    iconOnly && styles.iconOnly,
    disabled && styles.disabled,
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <button className={classes} disabled={disabled} {...props}>
      {icon && <span className={styles.icon}>{icon}</span>}
      {!iconOnly && children && <span className={styles.label}>{children}</span>}
    </button>
  );
}
