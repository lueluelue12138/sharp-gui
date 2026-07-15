import { useEffect, useRef } from 'react';

import { uploadModelAssetCover } from '@/api';
import { generateModelCoverFile } from '@/utils';
import type { ModelAsset } from '@/types';

const MAX_CONCURRENT_COVERS = 2;

function shouldGenerateCover(asset: ModelAsset): boolean {
  return Boolean(
    asset.is_imported
    && asset.available
    && !asset.thumb_url
    && asset.thumbnail_state !== 'error',
  );
}

/**
 * 为缺少封面的导入资产在后台生成系统封面：优先离屏渲染真实模型，
 * 失败时回退占位。并发受限、失败缓存，且不会因资产列表刷新而丢失
 * 已完成的封面更新或重复入队。
 */
export function useModelAssetCoverQueue(
  assets: ModelAsset[],
  onCoverUpdated: (asset: ModelAsset) => void,
  enabled = true,
): void {
  const onCoverUpdatedRef = useRef(onCoverUpdated);
  const failedIdsRef = useRef(new Set<string>());
  const pendingIdsRef = useRef(new Set<string>());
  const queuedIdsRef = useRef(new Set<string>());
  const queueRef = useRef<ModelAsset[]>([]);
  const activeCountRef = useRef(0);
  const mountedRef = useRef(true);

  useEffect(() => {
    onCoverUpdatedRef.current = onCoverUpdated;
  }, [onCoverUpdated]);

  useEffect(() => {
    const queue = queueRef.current;
    const queuedIds = queuedIdsRef.current;
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      queue.length = 0;
      queuedIds.clear();
    };
  }, []);

  useEffect(() => {
    const pump = () => {
      if (!mountedRef.current || !enabled) {
        return;
      }
      while (activeCountRef.current < MAX_CONCURRENT_COVERS) {
        const next = queueRef.current.shift();
        if (!next) {
          return;
        }
        queuedIdsRef.current.delete(next.id);
        pendingIdsRef.current.add(next.id);
        activeCountRef.current += 1;

        const openFormat = next.default_open_format ?? next.primary_format ?? next.formats[0] ?? null;
        generateModelCoverFile(next.id, next.default_open_url ?? null, openFormat)
          .then((file) => uploadModelAssetCover(next.id, file, 'system'))
          .then((updated) => {
            // The callback updates the global asset store. Keep the completed
            // result even if the library was just closed so reopening it does
            // not enqueue and upload the same cover again.
            onCoverUpdatedRef.current(updated);
          })
          .catch(() => {
            failedIdsRef.current.add(next.id);
          })
          .finally(() => {
            pendingIdsRef.current.delete(next.id);
            activeCountRef.current -= 1;
            if (mountedRef.current) {
              pump();
            }
          });
      }
    };

    if (!enabled) {
      queueRef.current.length = 0;
      queuedIdsRef.current.clear();
      return;
    }

    for (const asset of assets) {
      if (
        shouldGenerateCover(asset)
        && !failedIdsRef.current.has(asset.id)
        && !pendingIdsRef.current.has(asset.id)
        && !queuedIdsRef.current.has(asset.id)
      ) {
        queuedIdsRef.current.add(asset.id);
        queueRef.current.push(asset);
      }
    }

    pump();
  }, [assets, enabled]);
}
