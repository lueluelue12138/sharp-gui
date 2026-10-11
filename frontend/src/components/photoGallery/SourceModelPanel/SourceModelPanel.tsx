import { useCallback, useEffect, useRef, useState } from 'react';

import { Box, Star } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useAppStore } from '@/store';
import { convertPhotosToModels, fetchSourceModels, setSourceDefault } from '@/api';
import { Button } from '@/components/common/Button';
import { ChevronRightIcon, CloseIcon, SparklesIcon } from '@/components/common/Icons';
import { openLinkedModel } from '@/hooks/useModelSources';
import type { ModelAsset, SourceModelsResponse } from '@/types';

import styles from './SourceModelPanel.module.css';

export function SourceModelPanel() {
  const { t, i18n } = useTranslation();
  const target = useAppStore((state) => state.sourceModelTarget);
  const revision = useAppStore((state) => state.modelSourceRevision);
  const serverRevision = useAppStore((state) => state.modelSourceServerRevision);
  const owner = useAppStore((state) => state.isOwnerAccess);
  const canGenerate = useAppStore((state) => state.isOwnerAccess || Boolean(state.authStatus?.allow_remote_generation));
  const [data, setData] = useState<(SourceModelsResponse & { mediaId: string }) | null>(null);
  const [errorMediaId, setErrorMediaId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);
  const requestRef = useRef(0);
  const close = useCallback(() => useAppStore.getState().setSourceModelTarget(null), []);

  useEffect(() => {
    const request = ++requestRef.current;
    if (!target) return;
    void fetchSourceModels(target.id).then((response) => {
      if (request !== requestRef.current) return;
      setData({ ...response, mediaId: target.id });
      setErrorMediaId(null);
    }).catch(() => {
      if (request === requestRef.current) setErrorMediaId(target.id);
    });
    return () => { requestRef.current += 1; };
  }, [target, revision, serverRevision]);

  useEffect(() => {
    if (!target) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    dialogRef.current?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopImmediatePropagation();
        close();
      }
      if (event.key === 'Tab') {
        const buttons = dialogRef.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)');
        if (!buttons?.length) return;
        const first = buttons[0], last = buttons[buttons.length - 1];
        if (event.shiftKey && (document.activeElement === first || document.activeElement === dialogRef.current)) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener('keydown', keydown, true);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', keydown, true);
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, [target, close]);

  if (!target) return null;
  const matchesTarget = data?.mediaId === target.id;
  const models = matchesTarget ? data?.models ?? [] : [];
  const error = errorMediaId === target.id;
  const open = async (asset: ModelAsset) => {
    setBusy(true);
    setErrorMediaId(null);
    try { await openLinkedModel(asset); }
    catch { setErrorMediaId(target.id); }
    finally { setBusy(false); }
  };
  const prefer = async (asset: ModelAsset) => {
    if (!data?.source_id || !matchesTarget) return;
    setBusy(true);
    setErrorMediaId(null);
    const preferred = data.default_model_id === asset.id ? null : asset.id;
    try {
      await setSourceDefault(data.source_id, preferred);
      setData((current) => current?.mediaId === target.id ? { ...current, default_model_id: preferred } : current);
      useAppStore.getState().invalidateModelSources();
    } catch { setErrorMediaId(target.id); }
    finally { setBusy(false); }
  };
  const regenerate = async () => {
    const state = useAppStore.getState();
    if (target.media_type === 'video') {
      state.setPreviewPhoto(null);
      close();
      state.openVideoReconstructionDialog(target);
      return;
    }
    setBusy(true);
    setErrorMediaId(null);
    try {
      const response = await convertPhotosToModels([target.id]);
      if (!response.success) { setErrorMediaId(target.id); return; }
      state.upsertTasks(response.tasks ?? []);
      close();
    } catch { setErrorMediaId(target.id); }
    finally { setBusy(false); }
  };

  return (
    <div
      className={styles.backdrop}
      onClick={(event) => { if (event.target === event.currentTarget && !busy) close(); }}
    >
      <div
        ref={dialogRef}
        className={styles.panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby="source-model-title"
        tabIndex={-1}
      >
        <header className={styles.header}>
          <span className={styles.sourceCover}>
            {target.thumb_url ? <img src={target.thumb_url} alt="" /> : <Box size={22} />}
          </span>
          <div className={styles.heading}>
            <h2 id="source-model-title">{t('sourceModelsTitle')}</h2>
            <p data-tooltip={target.name}>{target.name}</p>
          </div>
          <button
            type="button"
            className={styles.close}
            onClick={close}
            disabled={busy}
            aria-label={t('close')}
            data-tooltip={t('close')}
          >
            <CloseIcon width={16} height={16} />
          </button>
        </header>
        <p className={styles.hint}>{t('sourceModelsHint')}</p>
        {error ? <p role="alert" className={styles.error}>{t('sourceModelsLoadFailed')}</p> : null}
        <div className={styles.list} aria-busy={busy || !matchesTarget}>
          {!matchesTarget && !error ? <p className={styles.empty}>{t('sourceModelsLoading')}</p> : null}
          {matchesTarget && models.length === 0 && !error ? <p className={styles.empty}>{t('sourceModelsEmpty')}</p> : null}
          {models.map((asset) => {
            const preferred = data?.default_model_id === asset.id;
            const quality = asset.quality && ['preview', 'high', 'extreme', 'custom'].includes(asset.quality)
              ? t('videoReconQuality.' + asset.quality) : null;
            return (
              <article
                className={[styles.model, preferred ? styles.preferredRow : ''].join(' ')}
                key={asset.id}
              >
                <button
                  type="button"
                  className={styles.open}
                  onClick={() => void open(asset)}
                  disabled={busy || !asset.available}
                  aria-label={t('sourceOpenNamedModel', { name: asset.name })}
                >
                  <span className={styles.cover}>
                    {asset.thumb_url ? <img src={asset.thumb_url} alt="" /> : <Box size={24} />}
                  </span>
                  <span className={styles.info}>
                    <span className={styles.name}>
                      <strong data-tooltip={asset.name}>{asset.name}</strong>
                      {preferred ? <span className={styles.defaultLabel}>{t('sourceDefaultModel')}</span> : null}
                    </span>
                    <span>
                      {t(asset.source_generation_kind === 'edited' ? 'sourceEditedCopy' : 'sourceReconstructed')}
                      {quality ? ' · ' + quality : ''}
                    </span>
                    <small>
                      {asset.created_at
                        ? new Date(asset.created_at).toLocaleString(i18n.language, { dateStyle: 'medium', timeStyle: 'short' })
                        : ''}
                      {' · ' + asset.formats.join(' / ').toUpperCase()}
                      {!asset.available ? ' · ' + t('modelAssetOpenUnavailable') : ''}
                    </small>
                  </span>
                  <ChevronRightIcon className={styles.arrow} width={15} height={15} aria-hidden="true" />
                </button>
                {owner && asset.available ? (
                  <button
                    type="button"
                    className={[styles.star, preferred ? styles.preferred : ''].join(' ')}
                    onClick={() => void prefer(asset)}
                    disabled={busy}
                    aria-pressed={preferred}
                    data-tooltip={t(preferred ? 'sourceUnsetDefault' : 'sourceSetDefault')}
                    aria-label={t(preferred ? 'sourceUnsetDefault' : 'sourceSetDefault')}
                  >
                    <Star size={18} fill={preferred ? 'currentColor' : 'none'} />
                  </button>
                ) : null}
              </article>
            );
          })}
        </div>
        <footer className={styles.footer}>
          <span>{t('sourceModelCount', { count: matchesTarget ? data?.model_count ?? 0 : 0 })}</span>
          {canGenerate ? (
            <Button
              type="button"
              variant="secondary"
              className={styles.regenerate}
              onClick={() => void regenerate()}
              disabled={busy || (matchesTarget ? data?.source_available === false : target.source_available === false)}
              icon={<SparklesIcon width={16} height={16} />}
            >
              {t('sourceRegenerate')}
            </Button>
          ) : null}
        </footer>
      </div>
    </div>
  );
}
