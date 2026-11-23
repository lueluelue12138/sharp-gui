import type { PortraitProgress } from '@/types/portrait';

export function progressPercent({ value, max }: PortraitProgress) {
  return typeof value === 'number' && max ? Math.min(100, Math.max(0, Math.round(100 * value / max))) : undefined;
}
