import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import * as Icons from '@/components/common/Icons';
import type { ViewerDebugInfo } from '@/hooks/useViewer';
import { useAppStore } from '@/store';
import styles from './QuickControls.module.css';

interface QuickControlsProps {
  isInXr: boolean;
  debugInfo: ViewerDebugInfo | null;
}

function toDegrees(radians: number): number {
  return (radians * 180) / Math.PI;
}

function toRadians(degrees: number): number {
  return (degrees * Math.PI) / 180;
}

function formatValue(value: number, fractionDigits = 2): string {
  return value.toFixed(fractionDigits);
}

function formatDebugNumber(value: number, fractionDigits = 2): string {
  if (!Number.isFinite(value)) return '-';
  return value.toFixed(fractionDigits);
}

function formatDebugVector(value: [number, number, number] | null, fractionDigits = 2): string {
  if (!value) return '-';
  return value.map((item) => formatDebugNumber(item, fractionDigits)).join(', ');
}

function getOrientationModeLabelKey(mode: ViewerDebugInfo['orientation']['mode']): string {
  return mode === 'y-front'
    ? 'quickControlsDebugOrientationModeYFront'
    : 'quickControlsDebugOrientationModeDefault';
}

function getOrientationReasonLabelKey(
  reason: ViewerDebugInfo['orientation']['reason'],
): string {
  if (reason === 'explicit-default') return 'quickControlsDebugOrientationReasonExplicitDefault';
  if (reason === 'explicit-y-front') return 'quickControlsDebugOrientationReasonExplicitYFront';
  if (reason === 'source-image') return 'quickControlsDebugOrientationReasonSourceImage';
  if (reason === 'source-video') return 'quickControlsDebugOrientationReasonSourceVideo';
  if (reason === 'legacy-video') return 'quickControlsDebugOrientationReasonLegacyVideo';
  return 'quickControlsDebugOrientationReasonUnknownFallback';
}

function getFramingModeLabelKey(mode: ViewerDebugInfo['framingMode']): string {
  if (mode === 'bounds-centered') return 'quickControlsDebugFramingModeBoundsCentered';
  if (mode === 'bounds-default') return 'quickControlsDebugFramingModeBoundsDefault';
  if (mode === 'bounds-unavailable') return 'quickControlsDebugFramingModeBoundsUnavailable';
  return 'quickControlsDebugFramingModeDefault';
}

function createDebugText(debugInfo: ViewerDebugInfo): string {
  return [
    `[orientation] mode=${debugInfo.orientation.mode} reason=${debugInfo.orientation.reason}`,
    `[framing] mode=${debugInfo.framingMode}`,
    `[camera] pos=${formatDebugVector(debugInfo.camera.position)} rotDeg=${formatDebugVector(debugInfo.camera.rotationDeg)} up=${formatDebugVector(debugInfo.camera.up)} forward=${formatDebugVector(debugInfo.camera.forward)}`,
    `[orbit] target=${formatDebugVector(debugInfo.controls.target)} distance=${formatDebugNumber(debugInfo.controls.distance)} azimuth=${formatDebugNumber(debugInfo.controls.orbitAzimuthDeg)} polar=${formatDebugNumber(debugInfo.controls.orbitPolarDeg)}`,
    `[model] pos=${formatDebugVector(debugInfo.model.position)} rotDeg=${formatDebugVector(debugInfo.model.rotationDeg)} scale=${formatDebugVector(debugInfo.model.scale)} right=${formatDebugVector(debugInfo.model.right)} up=${formatDebugVector(debugInfo.model.up)} forward=${formatDebugVector(debugInfo.model.forward)}`,
    `[bounds] center=${formatDebugVector(debugInfo.bounds?.center ?? null)} size=${formatDebugVector(debugInfo.bounds?.size ?? null)} targetDelta=${formatDebugVector(debugInfo.bounds?.targetDelta ?? null)} targetDistance=${formatDebugNumber(debugInfo.bounds?.targetDistance ?? Number.NaN)}`,
  ].join('\n');
}

function DebugRow({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.debugRow}>
      <span className={styles.debugLabel}>{label}</span>
      <span className={styles.debugValue}>{value}</span>
    </div>
  );
}

export function QuickControls({ isInXr, debugInfo }: QuickControlsProps) {
  const { t } = useTranslation();
  const [debugCopied, setDebugCopied] = useState(false);
  const {
    currentModelUrl,
    quickControlsOpen,
    setQuickControlsOpen,
    toggleQuickControls,
    viewerTransformDraft,
    viewerInteractionDraft,
    setViewerTransformDraft,
    applyViewerTransformDraft,
    setViewerInteractionDraft,
    applyViewerInteractionDraft,
    applyOrientationPreset,
    resetViewerQuickControlsForCurrentModel,
  } = useAppStore();

  const hasActiveModel = Boolean(currentModelUrl);
  const controlsDisabled = !hasActiveModel || isInXr;
  const disabledHint = !hasActiveModel
    ? t('quickControlsNoModelHint')
    : isInXr
      ? t('quickControlsXrHint')
      : '';

  useEffect(() => {
    if (!hasActiveModel && quickControlsOpen) {
      setQuickControlsOpen(false);
    }
  }, [hasActiveModel, quickControlsOpen, setQuickControlsOpen]);

  useEffect(() => {
    if (!quickControlsOpen) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setQuickControlsOpen(false);
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [quickControlsOpen, setQuickControlsOpen]);

  const updateTransform = (patch: Partial<typeof viewerTransformDraft>) => {
    setViewerTransformDraft(patch);
    applyViewerTransformDraft();
  };

  const updateInteraction = (patch: Partial<typeof viewerInteractionDraft>) => {
    setViewerInteractionDraft(patch);
    applyViewerInteractionDraft();
  };

  const handlePreset = (preset: 'default' | 'openCv' | 'openGl' | 'zUp' | 'flipUpsideDown') => {
    applyOrientationPreset(preset);
  };

  const handleCopyDebug = async () => {
    if (!debugInfo) return;

    try {
      await navigator.clipboard.writeText(createDebugText(debugInfo));
      setDebugCopied(true);
      window.setTimeout(() => setDebugCopied(false), 1400);
    } catch (error) {
      console.warn('[Viewer] Failed to copy debug info:', error);
    }
  };

  const orbitValue = debugInfo
    ? [
      `${t('quickControlsDebugDistanceShort')} ${formatDebugNumber(debugInfo.controls.distance)}`,
      `${t('quickControlsDebugAzimuthShort')} ${formatDebugNumber(debugInfo.controls.orbitAzimuthDeg)}°`,
      `${t('quickControlsDebugPolarShort')} ${formatDebugNumber(debugInfo.controls.orbitPolarDeg)}°`,
    ].join(' / ')
    : '-';

  return (
    <div className={styles.root}>
      <button
        className={styles.trigger}
        type="button"
        onClick={toggleQuickControls}
        data-tooltip={quickControlsOpen ? t('quickControlsClose') : t('quickControlsOpen')}
        aria-label={quickControlsOpen ? t('quickControlsCloseAria') : t('quickControlsOpenAria')}
        aria-expanded={quickControlsOpen}
      >
        <Icons.SettingsIcon />
      </button>

      <section
        className={`${styles.panel} ${quickControlsOpen ? styles.panelOpen : ''}`}
        aria-hidden={!quickControlsOpen}
      >
        <header className={styles.panelHeader}>
          <h4>{t('quickControlsTitle')}</h4>
          <button
            className={styles.resetBtn}
            type="button"
            onClick={resetViewerQuickControlsForCurrentModel}
            disabled={controlsDisabled}
          >
            <Icons.ResetIcon />
            <span>{t('quickControlsResetAll')}</span>
          </button>
        </header>

        {controlsDisabled && (
          <p className={styles.disabledHint}>{disabledHint}</p>
        )}

        <div className={styles.section}>
          <div className={styles.sectionTitle}>{t('quickControlsTransform')}</div>

          <div className={styles.presetGrid}>
            <button type="button" className={styles.presetBtn} onClick={() => handlePreset('default')} disabled={controlsDisabled}>
              {t('quickControlsPresetDefault')}
            </button>
            <button type="button" className={styles.presetBtn} onClick={() => handlePreset('flipUpsideDown')} disabled={controlsDisabled}>
              {t('quickControlsPresetUpsideDown')}
            </button>
            <button type="button" className={styles.presetBtn} onClick={() => handlePreset('openGl')} disabled={controlsDisabled}>
              {t('quickControlsPresetOpenGl')}
            </button>
            <button type="button" className={styles.presetBtn} onClick={() => handlePreset('zUp')} disabled={controlsDisabled}>
              {t('quickControlsPresetZUp')}
            </button>
          </div>

          <label className={styles.field}>
            <span className={styles.fieldLabel}>{t('quickControlsScale')}</span>
            <input
              type="range"
              min="0.2"
              max="8"
              step="0.01"
              value={viewerTransformDraft.scale}
              onChange={(event) => updateTransform({ scale: Number(event.target.value) })}
              disabled={controlsDisabled}
            />
            <span className={styles.fieldValue}>{formatValue(viewerTransformDraft.scale)}</span>
          </label>

          <label className={styles.field}>
            <span className={styles.fieldLabel}>{t('quickControlsPosX')}</span>
            <input
              type="range"
              min="-5"
              max="5"
              step="0.01"
              value={viewerTransformDraft.positionX}
              onChange={(event) => updateTransform({ positionX: Number(event.target.value) })}
              disabled={controlsDisabled}
            />
            <span className={styles.fieldValue}>{formatValue(viewerTransformDraft.positionX)}</span>
          </label>

          <label className={styles.field}>
            <span className={styles.fieldLabel}>{t('quickControlsPosY')}</span>
            <input
              type="range"
              min="-5"
              max="5"
              step="0.01"
              value={viewerTransformDraft.positionY}
              onChange={(event) => updateTransform({ positionY: Number(event.target.value) })}
              disabled={controlsDisabled}
            />
            <span className={styles.fieldValue}>{formatValue(viewerTransformDraft.positionY)}</span>
          </label>

          <label className={styles.field}>
            <span className={styles.fieldLabel}>{t('quickControlsPosZ')}</span>
            <input
              type="range"
              min="-5"
              max="5"
              step="0.01"
              value={viewerTransformDraft.positionZ}
              onChange={(event) => updateTransform({ positionZ: Number(event.target.value) })}
              disabled={controlsDisabled}
            />
            <span className={styles.fieldValue}>{formatValue(viewerTransformDraft.positionZ)}</span>
          </label>

          <label className={styles.field}>
            <span className={styles.fieldLabel}>{t('quickControlsRotX')}</span>
            <input
              type="range"
              min="-180"
              max="180"
              step="1"
              value={toDegrees(viewerTransformDraft.rotationX)}
              onChange={(event) => updateTransform({ rotationX: toRadians(Number(event.target.value)) })}
              disabled={controlsDisabled}
            />
            <span className={styles.fieldValue}>{formatValue(toDegrees(viewerTransformDraft.rotationX), 0)}°</span>
          </label>

          <label className={styles.field}>
            <span className={styles.fieldLabel}>{t('quickControlsRotY')}</span>
            <input
              type="range"
              min="-180"
              max="180"
              step="1"
              value={toDegrees(viewerTransformDraft.rotationY)}
              onChange={(event) => updateTransform({ rotationY: toRadians(Number(event.target.value)) })}
              disabled={controlsDisabled}
            />
            <span className={styles.fieldValue}>{formatValue(toDegrees(viewerTransformDraft.rotationY), 0)}°</span>
          </label>

          <label className={styles.field}>
            <span className={styles.fieldLabel}>{t('quickControlsRotZ')}</span>
            <input
              type="range"
              min="-180"
              max="180"
              step="1"
              value={toDegrees(viewerTransformDraft.rotationZ)}
              onChange={(event) => updateTransform({ rotationZ: toRadians(Number(event.target.value)) })}
              disabled={controlsDisabled}
            />
            <span className={styles.fieldValue}>{formatValue(toDegrees(viewerTransformDraft.rotationZ), 0)}°</span>
          </label>
        </div>

        <div className={styles.section}>
          <div className={styles.sectionTitle}>{t('quickControlsInteraction')}</div>

          <label className={styles.toggleField}>
            <input
              type="checkbox"
              checked={viewerInteractionDraft.reversePointerDirection}
              onChange={(event) => updateInteraction({ reversePointerDirection: event.target.checked })}
              disabled={controlsDisabled}
            />
            <span>{t('quickControlsReversePointer')}</span>
          </label>

          <label className={styles.toggleField}>
            <input
              type="checkbox"
              checked={viewerInteractionDraft.reversePointerSlide}
              onChange={(event) => updateInteraction({ reversePointerSlide: event.target.checked })}
              disabled={controlsDisabled}
            />
            <span>{t('quickControlsReverseSlide')}</span>
          </label>
        </div>

        <div className={styles.section}>
          <div className={styles.debugHeader}>
            <div className={styles.sectionTitle}>{t('quickControlsDebug')}</div>
            <button
              className={styles.debugCopyBtn}
              type="button"
              onClick={handleCopyDebug}
              disabled={!debugInfo}
            >
              {debugCopied ? t('quickControlsDebugCopied') : t('quickControlsDebugCopy')}
            </button>
          </div>

          {debugInfo ? (
            <div className={styles.debugGrid}>
              <DebugRow
                label={t('quickControlsDebugOrientationMode')}
                value={t(getOrientationModeLabelKey(debugInfo.orientation.mode))}
              />
              <DebugRow
                label={t('quickControlsDebugOrientationReason')}
                value={t(getOrientationReasonLabelKey(debugInfo.orientation.reason))}
              />
              <DebugRow
                label={t('quickControlsDebugFramingMode')}
                value={t(getFramingModeLabelKey(debugInfo.framingMode))}
              />
              <DebugRow
                label={t('quickControlsDebugCameraPosition')}
                value={formatDebugVector(debugInfo.camera.position)}
              />
              <DebugRow
                label={t('quickControlsDebugCameraRotation')}
                value={`${formatDebugVector(debugInfo.camera.rotationDeg, 1)}°`}
              />
              <DebugRow
                label={t('quickControlsDebugCameraUp')}
                value={formatDebugVector(debugInfo.camera.up)}
              />
              <DebugRow
                label={t('quickControlsDebugCameraForward')}
                value={formatDebugVector(debugInfo.camera.forward)}
              />
              <DebugRow
                label={t('quickControlsDebugControlsTarget')}
                value={formatDebugVector(debugInfo.controls.target)}
              />
              <DebugRow
                label={t('quickControlsDebugOrbit')}
                value={orbitValue}
              />
              <DebugRow
                label={t('quickControlsDebugModelPosition')}
                value={formatDebugVector(debugInfo.model.position)}
              />
              <DebugRow
                label={t('quickControlsDebugModelRotation')}
                value={`${formatDebugVector(debugInfo.model.rotationDeg, 1)}°`}
              />
              <DebugRow
                label={t('quickControlsDebugModelScale')}
                value={formatDebugVector(debugInfo.model.scale)}
              />
              <DebugRow
                label={t('quickControlsDebugModelRight')}
                value={formatDebugVector(debugInfo.model.right)}
              />
              <DebugRow
                label={t('quickControlsDebugModelUp')}
                value={formatDebugVector(debugInfo.model.up)}
              />
              <DebugRow
                label={t('quickControlsDebugModelForward')}
                value={formatDebugVector(debugInfo.model.forward)}
              />
              <DebugRow
                label={t('quickControlsDebugBoundsCenter')}
                value={formatDebugVector(debugInfo.bounds?.center ?? null)}
              />
              <DebugRow
                label={t('quickControlsDebugBoundsSize')}
                value={formatDebugVector(debugInfo.bounds?.size ?? null)}
              />
              <DebugRow
                label={t('quickControlsDebugTargetDelta')}
                value={[
                  formatDebugVector(debugInfo.bounds?.targetDelta ?? null),
                  `d=${formatDebugNumber(debugInfo.bounds?.targetDistance ?? Number.NaN)}`,
                ].join(' / ')}
              />
            </div>
          ) : (
            <p className={styles.disabledHint}>{t('quickControlsDebugWaiting')}</p>
          )}
        </div>
      </section>
    </div>
  );
}
