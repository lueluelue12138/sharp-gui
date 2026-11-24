import { useId, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';

import { MemoryStick, Minus, Plus } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/common/Button';
import { SelectMenu } from '@/components/common/SelectMenu';
import workbenchStyles from '@/components/portrait/PortraitWorkbench/PortraitWorkbench.module.css';
import styles from '@/components/portrait/WorkbenchControls/WorkbenchControls.module.css';
import type { PortraitCacheRelease, PortraitProgress, PortraitTask } from '@/types/portrait';
import { progressPercent } from '@/utils/portraitProgress';

const largeEdges = [2560, 2880, 3072, 3200, 3584, 3840];

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

export function PixelChoice({ label, value, values, disabled, alignment = 1, originalLabel, onChange }: {
  label: string; value: number; values: number[]; disabled?: boolean; alignment?: number; onChange: (value: number) => void;
  originalLabel?: string;
}) {
  const { t } = useTranslation();
  const [custom, setCustom] = useState(false);
  const edges = [...new Set([...values, ...largeEdges])].sort((a, b) => a - b);
  const original = originalLabel !== undefined && value === 0;
  const editingSize = custom || (!original && !edges.includes(value));
  const options = edges.map((edge) => ({ value: String(edge), label: `${edge} px` }));
  if (originalLabel !== undefined) options.unshift({ value: '0', label: originalLabel });
  options.push({ value: 'custom', label: t('portrait.customSize') });
  return <div className={styles.pixelChoice}>
    <Choice label={label} value={editingSize ? 'custom' : value} disabled={disabled} onChange={(next) => {
      setCustom(next === 'custom');
      if (next !== 'custom') onChange(Number(next));
      else if (original) onChange(edges.find((edge) => edge >= 1024) ?? edges[0]);
    }} options={options} />
    {editingSize && <NumberField label={t('portrait.pixels')} value={value} min={edges[0]} max={edges[edges.length - 1]}
      step={alignment} disabled={disabled} onChange={(next) => onChange(Math.round(next / alignment) * alignment)} />}
  </div>;
}

export function WorkflowProgress({ progress, nodeName }: { progress: PortraitProgress; nodeName?: string }) {
  const { t } = useTranslation();
  const percent = progressPercent(progress);
  return <>
    <div className={workbenchStyles.progressTrack} data-indeterminate={percent === undefined} role="progressbar"
      aria-label={t('portrait.nodeProgress')} aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}>
      <span style={percent === undefined ? undefined : { width: `${percent}%` }} />
    </div>
    <div className={workbenchStyles.statusDetails}>
      <span>{nodeName ? t(`portrait.nodes.${nodeName}`) : t(`portrait.${progress.state}`)}</span>
      {percent !== undefined && <span>{t('portrait.progressSteps', {
        value: Number(progress.value?.toFixed(1)), max: progress.max, percent,
      })}</span>}
    </div>
  </>;
}

export function BatchProgress({ task, nodeNames }: { task: PortraitTask; nodeNames: Record<string, string> }) {
  const { t } = useTranslation();
  const progress = task.progress ?? { state: task.status === 'running' ? 'running' : 'queued' };
  return <>
    <div className={workbenchStyles.statusTitle}>
      <strong>{t(`portrait.progress.${task.stage}`)}</strong>
      {task.batch && <span>{task.batch.index} / {task.batch.count}</span>}
    </div>
    <WorkflowProgress progress={progress} nodeName={progress.node ? nodeNames[progress.node] ?? 'processing' : undefined} />
  </>;
}

export function ReleaseCacheButton({ disabled, canClearCache, onClick }: {
  disabled?: boolean; canClearCache: boolean; onClick: () => void;
}) {
  const { t } = useTranslation();
  return <Button variant="secondary" size="sm" type="button" icon={<MemoryStick size={16} />}
    disabled={disabled || !canClearCache}
    data-tooltip={t(canClearCache ? 'portrait.releasePreviewHint' : 'portrait.errors.portraitEngineBusy')} onClick={onClick}>
    {t('portrait.releaseEngine')}
  </Button>;
}

export function CacheReleaseStatus({ result, onClose }: { result: PortraitCacheRelease; onClose: () => void }) {
  const { t } = useTranslation();
  return <div className={workbenchStyles.statusTitle}>
    <div><strong>{t('portrait.memoryRequested', { count: result.removed })}</strong>
      {result.failed > 0 && <small>{t('portrait.cacheFilesBusy', { count: result.failed })}</small>}</div>
    <Button variant="ghost" size="sm" type="button" onClick={onClose}>{t('close')}</Button>
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
      <input aria-label={label} type="text" inputMode={min < 0 ? 'text' : step % 1 ? 'decimal' : 'numeric'} disabled={disabled}
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

export function BatchCount({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  const { t } = useTranslation();
  return <div className={styles.batchCount}>
    <NumberField label={t('portrait.batchCount')} value={value} min={1} max={32} onChange={(next) => onChange(Math.floor(next))} />
  </div>;
}

export function BatchNotice({ preparing, queued }: { preparing: number; queued: number }) {
  const { t } = useTranslation();
  return <p className={styles.batchNotice} role="status">
    {preparing ? t('portrait.batchPreparing', { count: preparing }) : queued ? t('portrait.batchQueued', { count: queued }) : ''}
  </p>;
}
