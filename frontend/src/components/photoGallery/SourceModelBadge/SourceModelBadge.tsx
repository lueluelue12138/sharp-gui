import { Box, Clock3, Layers3, TriangleAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useAppStore } from '@/store';
import { useSourceModelsEntry } from '@/hooks/useModelSources';
import { sourceTask } from '@/utils';
import type { PhotoItem } from '@/types';

import styles from './SourceModelBadge.module.css';

interface SourceModelBadgeProps {
  item: PhotoItem;
  preview?: boolean;
}

export function SourceModelBadge({ item, preview = false }: SourceModelBadgeProps) {
  const { t } = useTranslation();
  const link = useAppStore((state) => state.modelSourceLinks[item.id]) ?? item.model_link;
  const tasks = useAppStore((state) => state.tasks);
  const open = useSourceModelsEntry();
  const task = sourceTask(item, link, tasks);
  const count = link?.model_count ?? 0;
  const hasModels = count > 0 || (link?.total_count ?? 0) > 0;
  if (!hasModels && !task) return null;

  const statusKey = task?.status === 'failed'
    ? 'sourceTaskFailed' : task?.status === 'pending' ? 'sourceTaskQueued' : 'sourceTaskRunning';
  const allLabel = t(count > 1 ? 'sourceAllModels' : 'sourceModelOptions', { count });

  return (
    <div
      className={[styles.root, preview ? styles.preview : ''].join(' ')}
      onMouseDown={(event) => event.stopPropagation()}
      onClick={(event) => event.stopPropagation()}
    >
      {hasModels ? (
        <>
          <button
            type="button"
            className={styles.badge}
            onClick={() => void open(item)}
            aria-label={t('sourceViewModels')}
            data-tooltip={t('sourceViewModels') + ' · ' + t('sourceModelCount', { count })}
          >
            <Box size={preview ? 20 : 14} aria-hidden="true" />
            <span>{preview ? t('sourceView3d') : '3D'}{count > 1 ? ' · ' + count : ''}</span>
          </button>
          {preview && count > 0 ? (
            <button
              type="button"
              className={styles.allModels}
              onClick={() => void open(item, true)}
              aria-label={allLabel}
              data-tooltip={allLabel}
            >
              <Layers3 size={20} aria-hidden="true" />
            </button>
          ) : null}
        </>
      ) : null}
      {task ? (
        <span
          className={[styles.status, task.status === 'failed' ? styles.failed : ''].join(' ')}
          data-tooltip={task.error ? t(statusKey) + ' · ' + task.error : t(statusKey)}
          aria-label={t(statusKey)}
          role="status"
        >
          {task.status === 'failed' ? <TriangleAlert size={14} /> : <Clock3 size={14} />}
          {preview ? <span>{t(statusKey)}</span> : null}
        </span>
      ) : null}
    </div>
  );
}
