import { useEffect, useMemo, useState } from 'react';

import { CircleHelp } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';

import { useAppStore } from '@/store';

import {
  ApiError,
  createVideoReconstruction,
  createVideoReconstructionFromFile,
  fetchVideoReconstructionStatus,
} from '@/api';
import { Button } from '@/components/common/Button';
import { ChevronDownIcon, SparklesIcon } from '@/components/common/Icons';
import { Modal } from '@/components/common/Modal';

import type {
  VideoReconstructionCacheImages,
  VideoReconstructionCustomOptions,
  VideoReconstructionEngine,
  VideoReconstructionMatchingMethod,
  VideoReconstructionMode,
  VideoReconstructionQuality,
} from '@/types';

import styles from './VideoReconstructionDialog.module.css';

const MAX_OUTPUT_NAME_LENGTH = 120;

const MODE_OPTIONS: VideoReconstructionMode[] = ['auto', 'object', 'environment'];
const QUALITY_OPTIONS: VideoReconstructionQuality[] = ['preview', 'high', 'extreme', 'custom'];
const ENGINE_OPTIONS: VideoReconstructionEngine[] = ['auto', 'stable'];
const DOWNSCALE_OPTIONS = [1, 2, 4] as const;
const MATCHING_OPTIONS: VideoReconstructionMatchingMethod[] = ['sequential', 'exhaustive'];
const CACHE_OPTIONS: VideoReconstructionCacheImages[] = ['gpu', 'cpu'];
const DEFAULT_CUSTOM_OPTIONS: VideoReconstructionCustomOptions = {
  frame_count: 600,
  max_num_iterations: 35000,
  downscale_factor: 2,
  matching_method: 'sequential',
  cache_images: 'cpu',
};

function deriveOutputName(filename: string): string {
  const withoutExtension = filename.replace(/\.[^.]+$/, '');
  return Array.from(withoutExtension)
    .map((char) => (char.charCodeAt(0) < 32 || '<>:"/\\|?*'.includes(char) ? '_' : char))
    .join('')
    .trim()
    .slice(0, MAX_OUTPUT_NAME_LENGTH);
}

export function VideoReconstructionDialog() {
  const { t } = useTranslation();
  const {
    isOpen,
    target,
    fileTarget,
    dependencies,
    config,
    submitting,
    closeDialog,
    openGuide,
    setStatus,
    setSubmitting,
    upsertTasks,
  } = useAppStore(
    useShallow((state) => ({
      isOpen: state.videoReconstructionDialogOpen,
      target: state.videoReconstructionTarget,
      fileTarget: state.videoReconstructionFileTarget,
      dependencies: state.videoReconstructionDependencies,
      config: state.videoReconstructionConfig,
      submitting: state.videoReconstructionSubmitting,
      closeDialog: state.closeVideoReconstructionDialog,
      openGuide: state.openVideoReconstructionGuide,
      setStatus: state.setVideoReconstructionStatus,
      setSubmitting: state.setVideoReconstructionSubmitting,
      upsertTasks: state.upsertTasks,
    })),
  );
  const [mode, setMode] = useState<VideoReconstructionMode>('auto');
  const [quality, setQuality] = useState<VideoReconstructionQuality>('high');
  const [engine, setEngine] = useState<VideoReconstructionEngine>('auto');
  const [customOptions, setCustomOptions] = useState<VideoReconstructionCustomOptions>(DEFAULT_CUSTOM_OPTIONS);
  const [outputName, setOutputName] = useState('');
  const [keepIntermediateFiles, setKeepIntermediateFiles] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [message, setMessage] = useState<{ tone: 'error' | 'success' | 'warning'; text: string } | null>(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);

  useEffect(() => {
    const targetName = target?.name ?? fileTarget?.name;
    if (!isOpen || !targetName) {
      return;
    }

    setMode('auto');
    setQuality(config.default_quality);
    setEngine(config.default_engine);
    setCustomOptions(DEFAULT_CUSTOM_OPTIONS);
    setOutputName(deriveOutputName(targetName));
    setKeepIntermediateFiles(config.keep_intermediate_files);
    setAdvancedOpen(false);
    setMessage(null);
    setUploadProgress(null);
  }, [config.default_engine, config.default_quality, config.keep_intermediate_files, fileTarget, isOpen, target]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    if (dependencies && !dependencies.summary.checking) {
      setStatusLoading(false);
      return;
    }

    let cancelled = false;
    let retryTimer: number | undefined;
    const loadStatus = () => {
      setStatusLoading(true);
      void fetchVideoReconstructionStatus()
        .then((status) => {
          if (!cancelled) {
            setStatus(status.dependencies, status.config);
          }
        })
        .catch((error: unknown) => {
          if (!cancelled) {
            const text = error instanceof Error ? error.message : t('videoReconStatusLoadFailed');
            setMessage({ tone: 'error', text });
          }
        })
        .finally(() => {
          if (!cancelled) {
            setStatusLoading(false);
          }
        });
    };

    if (dependencies?.summary.checking) {
      retryTimer = window.setTimeout(loadStatus, 1400);
    } else {
      loadStatus();
    }

    return () => {
      cancelled = true;
      if (retryTimer !== undefined) {
        window.clearTimeout(retryTimer);
      }
    };
  }, [dependencies, isOpen, setStatus, t]);

  const customValidationMessage = useMemo(() => {
    if (quality !== 'custom') {
      return null;
    }
    if (customOptions.frame_count < 24 || customOptions.frame_count > 1200) {
      return t('videoReconCustomValidation.frameCount');
    }
    if (customOptions.max_num_iterations < 1000 || customOptions.max_num_iterations > 80000) {
      return t('videoReconCustomValidation.iterations');
    }
    if (customOptions.matching_method === 'exhaustive' && customOptions.frame_count > 450) {
      return t('videoReconCustomValidation.exhaustiveFrames');
    }
    return null;
  }, [customOptions, quality, t]);

  const stableAvailable = Boolean(dependencies?.summary.stable_available);
  const dependenciesChecking = Boolean(dependencies?.summary.checking) || statusLoading;
  const canSubmit = (target?.media_type === 'video' || Boolean(fileTarget))
    && !submitting
    && !dependenciesChecking
    && stableAvailable
    && !customValidationMessage
    && outputName.trim().length > 0
    && outputName.trim().length <= MAX_OUTPUT_NAME_LENGTH;

  const dependencyMessage = useMemo(() => {
    if (dependencies?.summary.checking) {
      return t('videoReconCheckingDependencies');
    }
    if (!dependencies) {
      return statusLoading ? t('videoReconCheckingDependencies') : null;
    }
    if (!dependencies.required.available) {
      return t('videoReconRequiredMissing');
    }
    if (!dependencies.stable.available) {
      return t('videoReconStableMissing');
    }
    return t('videoReconDependenciesReady');
  }, [dependencies, statusLoading, t]);

  const handleSubmit = async () => {
    if (!canSubmit || (!target && !fileTarget)) {
      return;
    }

    setSubmitting(true);
    setMessage(null);
    setUploadProgress(fileTarget ? 0 : null);
    try {
      const requestOptions = {
        mode,
        quality,
        custom_options: quality === 'custom' ? customOptions : undefined,
        engine,
        output_name: outputName.trim(),
        keep_intermediate_files: keepIntermediateFiles,
      };
      const response = fileTarget
        ? await createVideoReconstructionFromFile(fileTarget, requestOptions, {
            onUploadProgress: ({ percent }) => setUploadProgress(percent),
          })
        : await createVideoReconstruction({
            video_id: target!.id,
            ...requestOptions,
          });
      if (response.task) {
        upsertTasks([response.task]);
      }
      setMessage({ tone: 'success', text: t('videoReconQueued') });
      window.setTimeout(() => closeDialog(), 260);
    } catch (error) {
      setUploadProgress(null);
      const text = error instanceof ApiError && error.data?.code
        ? t(`videoReconError.${error.data.code}`, { defaultValue: error.message })
        : error instanceof Error
          ? error.message
          : t('videoReconCreateFailed');
      setMessage({ tone: 'error', text });
    } finally {
      setSubmitting(false);
    }
  };

  const updateCustomOption = <Key extends keyof VideoReconstructionCustomOptions>(
    key: Key,
    value: VideoReconstructionCustomOptions[Key],
  ) => {
    setCustomOptions((current) => ({ ...current, [key]: value }));
  };

  const updateCustomNumber = (
    key: 'frame_count' | 'max_num_iterations',
    value: string,
  ) => {
    const parsed = Number.parseInt(value, 10);
    updateCustomOption(key, Number.isFinite(parsed) ? parsed : 0);
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={submitting ? () => undefined : closeDialog}
      title={t('videoReconDialogTitle')}
      size="lg"
    >
      <div className={styles.root}>
        <div className={styles.summary}>
          <SparklesIcon width={18} height={18} />
          <div>
            <strong>{target?.name ?? fileTarget?.name ?? t('photoVideo')}</strong>
            <span>{dependencyMessage}</span>
          </div>
        </div>

        <fieldset className={styles.fieldset} disabled={submitting}>
          <label className={styles.label}>{t('videoReconModeLabel')}</label>
          <div className={styles.segmented}>
            {MODE_OPTIONS.map((option) => (
              <button
                key={option}
                className={[styles.segmentBtn, mode === option ? styles.segmentActive : ''].filter(Boolean).join(' ')}
                onClick={() => setMode(option)}
                type="button"
              >
                <span>{t(`videoReconMode.${option}`)}</span>
                <small>{t(`videoReconModeMeta.${option}`)}</small>
              </button>
            ))}
          </div>
        </fieldset>

        <fieldset className={styles.fieldset} disabled={submitting}>
          <label className={styles.label}>{t('videoReconQualityLabel')}</label>
          <div className={styles.segmented}>
            {QUALITY_OPTIONS.map((option) => (
              <button
                key={option}
                className={[styles.segmentBtn, quality === option ? styles.segmentActive : ''].filter(Boolean).join(' ')}
                onClick={() => setQuality(option)}
                type="button"
              >
                <span>{t(`videoReconQuality.${option}`)}</span>
                <small>
                  {config.default_quality === option
                    ? `${t('videoReconRecommended')} / ${t(`videoReconQualityMeta.${option}`)}`
                    : t(`videoReconQualityMeta.${option}`)}
                </small>
              </button>
            ))}
          </div>
        </fieldset>

        {quality === 'custom' ? (
          <div className={styles.customPanel}>
            <div className={styles.customHeader}>
              <strong>{t('videoReconCustomTitle')}</strong>
              <span>{t('videoReconCustomHint')}</span>
            </div>

            <div className={styles.customGrid}>
              <label className={styles.numberField}>
                <span>{t('videoReconCustomFrameCount')}</span>
                <input
                  className={styles.numberInput}
                  type="number"
                  min={24}
                  max={1200}
                  step={12}
                  value={customOptions.frame_count}
                  disabled={submitting}
                  onChange={(event) => updateCustomNumber('frame_count', event.target.value)}
                />
                <small>{t('videoReconCustomFrameCountHint')}</small>
              </label>

              <label className={styles.numberField}>
                <span>{t('videoReconCustomIterations')}</span>
                <input
                  className={styles.numberInput}
                  type="number"
                  min={1000}
                  max={80000}
                  step={1000}
                  value={customOptions.max_num_iterations}
                  disabled={submitting}
                  onChange={(event) => updateCustomNumber('max_num_iterations', event.target.value)}
                />
                <small>{t('videoReconCustomIterationsHint')}</small>
              </label>
            </div>

            <fieldset className={styles.fieldset} disabled={submitting}>
              <label className={styles.label}>{t('videoReconCustomDownscale')}</label>
              <div className={styles.segmented}>
                {DOWNSCALE_OPTIONS.map((option) => (
                  <button
                    key={option}
                    className={[
                      styles.segmentBtn,
                      customOptions.downscale_factor === option ? styles.segmentActive : '',
                    ].filter(Boolean).join(' ')}
                    onClick={() => updateCustomOption('downscale_factor', option)}
                    type="button"
                  >
                    <span>{t(`videoReconDownscale.${option}`)}</span>
                    <small>{t(`videoReconDownscaleMeta.${option}`)}</small>
                  </button>
                ))}
              </div>
              <p className={styles.parameterHint}>{t('videoReconCustomDownscaleHint')}</p>
            </fieldset>

            <fieldset className={styles.fieldset} disabled={submitting}>
              <label className={styles.label}>{t('videoReconCustomMatching')}</label>
              <div className={styles.segmented}>
                {MATCHING_OPTIONS.map((option) => (
                  <button
                    key={option}
                    className={[
                      styles.segmentBtn,
                      customOptions.matching_method === option ? styles.segmentActive : '',
                    ].filter(Boolean).join(' ')}
                    onClick={() => updateCustomOption('matching_method', option)}
                    type="button"
                  >
                    <span>{t(`videoReconMatching.${option}`)}</span>
                    <small>{t(`videoReconMatchingMeta.${option}`)}</small>
                  </button>
                ))}
              </div>
              <p className={styles.parameterHint}>{t('videoReconCustomMatchingHint')}</p>
            </fieldset>

            <fieldset className={styles.fieldset} disabled={submitting}>
              <label className={styles.label}>{t('videoReconCustomCacheImages')}</label>
              <div className={styles.segmented}>
                {CACHE_OPTIONS.map((option) => (
                  <button
                    key={option}
                    className={[
                      styles.segmentBtn,
                      customOptions.cache_images === option ? styles.segmentActive : '',
                    ].filter(Boolean).join(' ')}
                    onClick={() => updateCustomOption('cache_images', option)}
                    type="button"
                  >
                    <span>{t(`videoReconCacheImages.${option}`)}</span>
                    <small>{t(`videoReconCacheImagesMeta.${option}`)}</small>
                  </button>
                ))}
              </div>
              <p className={styles.parameterHint}>{t('videoReconCustomCacheImagesHint')}</p>
            </fieldset>

            {customValidationMessage ? (
              <div className={[styles.message, styles.warning].join(' ')}>
                {customValidationMessage}
              </div>
            ) : null}
          </div>
        ) : null}

        <div className={styles.fieldset}>
          <label className={styles.label} htmlFor="video-recon-output-name">
            {t('videoReconOutputName')}
          </label>
          <input
            id="video-recon-output-name"
            className={styles.input}
            value={outputName}
            maxLength={MAX_OUTPUT_NAME_LENGTH}
            disabled={submitting}
            onChange={(event) => setOutputName(event.target.value)}
            placeholder={t('videoReconOutputPlaceholder')}
          />
        </div>

        <button
          className={styles.advancedToggle}
          type="button"
          onClick={() => setAdvancedOpen((current) => !current)}
          aria-expanded={advancedOpen}
        >
          <span>{t('videoReconAdvanced')}</span>
          <ChevronDownIcon
            width={15}
            height={15}
            className={advancedOpen ? styles.advancedChevronOpen : ''}
          />
        </button>

        {advancedOpen ? (
          <div className={styles.advancedPanel}>
            <fieldset className={styles.fieldset} disabled={submitting}>
              <label className={styles.label}>{t('videoReconEngineLabel')}</label>
              <div className={styles.segmented}>
                {ENGINE_OPTIONS.map((option) => (
                  <button
                    key={option}
                    className={[
                      styles.segmentBtn,
                      engine === option ? styles.segmentActive : '',
                    ].filter(Boolean).join(' ')}
                    onClick={() => setEngine(option)}
                    type="button"
                  >
                    <span>{t(`videoReconEngine.${option}`)}</span>
                    <small>{t(`videoReconEngineMeta.${option}`)}</small>
                  </button>
                ))}
              </div>
            </fieldset>

            <label className={styles.toggleRow}>
              <span>
                <strong>{t('videoReconKeepIntermediate')}</strong>
                <small>{t('videoReconKeepIntermediateHint')}</small>
              </span>
              <input
                type="checkbox"
                checked={keepIntermediateFiles}
                disabled={submitting}
                onChange={(event) => setKeepIntermediateFiles(event.target.checked)}
              />
            </label>

            <div className={styles.budgetHint}>
              <span>{t('videoReconVramBudget')}</span>
              <strong>{t(`videoReconVram.${config.vram_budget}`)}</strong>
            </div>
          </div>
        ) : null}

        {submitting && fileTarget && uploadProgress !== null ? (
          <div className={[styles.message, styles.uploading].join(' ')} role="status" aria-live="polite">
            <div className={styles.uploadProgressHeader}>
              <span>{t('videoReconUploadingFile')}</span>
              <strong>{Math.round(uploadProgress)}%</strong>
            </div>
            <div className={styles.uploadProgressBar}>
              <div
                className={styles.uploadProgressFill}
                style={{ width: `${Math.min(100, Math.max(0, uploadProgress))}%` }}
              />
            </div>
          </div>
        ) : message ? (
          <div className={[styles.message, styles[message.tone]].join(' ')} role="status" aria-live="polite">
            {message.text}
          </div>
        ) : dependencyMessage ? (
          <div className={[styles.message, dependenciesChecking ? styles.warning : stableAvailable ? styles.success : styles.error].join(' ')}>
            {dependencyMessage}
          </div>
        ) : null}

        <div className={styles.actions}>
          <Button
            variant="ghost"
            type="button"
            onClick={openGuide}
            icon={<CircleHelp width={16} height={16} />}
          >
            {t('videoReconOpenGuide')}
          </Button>
          <div className={styles.actionGroup}>
            <Button variant="secondary" type="button" onClick={closeDialog} disabled={submitting}>
              {t('cancel')}
            </Button>
            <Button
              variant="primary"
              type="button"
              onClick={handleSubmit}
              disabled={!canSubmit}
              icon={<SparklesIcon width={16} height={16} />}
            >
              {submitting ? t('videoReconSubmitting') : t('videoReconStart')}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
