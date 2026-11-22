import { useId, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';

import { Minus, Plus } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/common/Button';
import { SelectMenu } from '@/components/common/SelectMenu';
import styles from '@/components/portrait/WorkbenchControls/WorkbenchControls.module.css';

export function Segments<T extends string>({ value, options, onChange, label }: {
  value: T; options: ReadonlyArray<{ value: T; label: string; icon?: ReactNode; disabled?: boolean }>;
  onChange: (value: T) => void; label: string;
}) {
  return <div className={styles.segments} role="group" aria-label={label}>
    {options.map((option) => <Button variant="ghost" size="sm" key={option.value}
      type="button" icon={option.icon} disabled={option.disabled} aria-pressed={option.value === value}
      onClick={() => onChange(option.value)}>{option.label}</Button>)}
  </div>;
}

export function Choice({ label, value, options, disabled, onChange }: {
  label: string; value: string | number; options: Array<{ value: string; label: string }>;
  disabled?: boolean; onChange: (value: string) => void;
}) {
  return <div className={styles.field}><span>{label}</span><SelectMenu portal value={String(value)} options={options}
    ariaLabel={label} disabled={disabled} onChange={onChange} menuClassName={styles.raisedMenu} /></div>;
}

export function PixelChoice({ label, value, values, disabled, allowCustom, onChange }: {
  label: string; value: number; values: number[]; disabled?: boolean; allowCustom?: boolean; onChange: (value: number) => void;
}) {
  const { t } = useTranslation();
  const [custom, setCustom] = useState(false);
  const editingSize = allowCustom && (custom || !values.includes(value));
  const options = values.map((edge) => ({ value: String(edge), label: `${edge} px` }));
  if (allowCustom) options.push({ value: 'custom', label: t('portrait.customSize') });
  return <div className={styles.pixelChoice}>
    <Choice label={label} value={editingSize ? 'custom' : value} disabled={disabled} onChange={(next) => {
      setCustom(next === 'custom');
      if (next !== 'custom') onChange(Number(next));
    }} options={options} />
    {editingSize && <NumberField label={t('portrait.pixels')} value={value} min={Math.min(...values)} max={Math.max(...values)}
      step={32} disabled={disabled} onChange={(next) => onChange(Math.round(next / 32) * 32)} />}
  </div>;
}

export function RangeField({ label, value, onChange, min, max, step, display, disabled }: {
  label: string; value: number; onChange: (value: number) => void;
  min: number; max: number; step: number; display: string; disabled?: boolean;
}) {
  const id = useId();
  return <label className={styles.rangeField} htmlFor={id}>
    <span>{label}</span><output htmlFor={id}>{display}</output>
    <input type="range" id={id} className={styles.range} min={min} max={max} step={step}
      value={value} aria-valuetext={display} disabled={disabled}
      style={{ '--range-value': `${Math.min(100, Math.max(0, 100 * (value - min) / (max - min)))}%` } as CSSProperties}
      onChange={(event) => onChange(event.currentTarget.valueAsNumber)} />
  </label>;
}

export function NumberField({ label, value, min, max, step = 1, disabled, onChange, steppers = true }: {
  label: string; value: number; min: number; max: number; step?: number; disabled?: boolean;
  onChange: (value: number) => void; steppers?: boolean;
}) {
  const [draft, setDraft] = useState<string>();
  const update = (next: number) => { if (Number.isFinite(next)) onChange(Math.min(max, Math.max(min, next))); };
  function commit() {
    if (draft?.trim()) update(Number(draft.replace(',', '.')));
    setDraft(undefined);
  }
  return <div className={styles.field}>
    <span>{label}</span><div className={styles.number}>
      {steppers && <Button variant="ghost" size="sm" type="button" iconOnly icon={<Minus size={15} />}
        aria-label={`${label} −`} disabled={disabled || value <= min} onClick={() => update(value - step)} />}
      <input aria-label={label} type="text" inputMode={step % 1 ? 'decimal' : 'numeric'} disabled={disabled}
        value={draft ?? value} onChange={(event) => setDraft(event.currentTarget.value)} onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === 'Enter') event.currentTarget.blur();
          if (event.key === 'Escape') setDraft(undefined);
        }} />
      {steppers && <Button variant="ghost" size="sm" type="button" iconOnly icon={<Plus size={15} />}
        aria-label={`${label} +`} disabled={disabled || value >= max} onClick={() => update(value + step)} />}
    </div>
  </div>;
}

export function ToggleField({ label, checked, disabled, onChange }: {
  label: string; checked: boolean; disabled?: boolean; onChange: (checked: boolean) => void;
}) {
  return <button type="button" className={styles.toggleField} role="switch" aria-checked={checked}
    disabled={disabled} onClick={() => onChange(!checked)}><span>{label}</span><i aria-hidden="true" /></button>;
}
