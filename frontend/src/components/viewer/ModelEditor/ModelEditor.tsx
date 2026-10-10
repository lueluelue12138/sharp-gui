import { useEffect, useState } from 'react';
import type { RefObject } from 'react';
import {
  ArrowLeft,
  Box,
  Camera,
  Check,
  Circle,
  Eraser,
  Grid3X3,
  Move,
  Redo2,
  RotateCw,
  Save,
  SlidersHorizontal,
  SquareDashed,
  Trash2,
  Undo2,
  X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { uploadModelAssetCover } from '@/api/modelAssets';
import { useModelEditor } from '@/hooks/useModelEditor';
import type { ViewerContext } from '@/hooks/useViewer';
import { useAppStore } from '@/store/useAppStore';
import type { EditorTool } from '@/types/modelEditor';
import type { ViewerTransformState } from '@/types/viewerQuickControls';
import { resolveModelAssetSource } from '@/utils/modelAssets';

import styles from './ModelEditor.module.css';

interface ModelEditorProps {
  viewerRef: RefObject<ViewerContext | null>;
  assetId: string;
  onClose: () => void;
}

function NumberField({
  label,
  value,
  onCommit,
  disabled = false,
  min,
  max,
}: {
  label: string;
  value: number;
  onCommit: (value: number) => void;
  disabled?: boolean;
  min?: number;
  max?: number;
}) {
  const commit = (input: HTMLInputElement) => {
    const number = input.valueAsNumber;
    if (
      Number.isFinite(number) &&
      (min === undefined || number >= min) &&
      (max === undefined || number <= max)
    )
      onCommit(number);
    else input.value = String(Number(value.toFixed(4)));
  };
  return (
    <label className={styles.numberField}>
      <span>{label}</span>
      <input
        key={value}
        aria-label={label}
        type="number"
        step="any"
        min={min}
        max={max}
        disabled={disabled}
        defaultValue={Number(value.toFixed(4))}
        onBlur={(event) => commit(event.currentTarget)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') event.currentTarget.blur();
        }}
      />
    </label>
  );
}

const TOOLS = [
  { id: 'move', label: 'modelEditorMove', icon: Move },
  { id: 'rotate', label: 'modelEditorRotate', icon: RotateCw },
  { id: 'rectangle', label: 'modelEditorRectangle', icon: SquareDashed },
  { id: 'sphere', label: 'modelEditorSphere', icon: Circle },
  { id: 'box', label: 'modelEditorBox', icon: Box },
] as const;

export function ModelEditor({ viewerRef, assetId, onClose }: ModelEditorProps) {
  const { t } = useTranslation();
  const editor = useModelEditor(viewerRef, assetId);
  const { state } = editor;
  const [showExit, setShowExit] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [name, setName] = useState<string | null>(null);
  const defaultName = state.name ? t('modelEditorDefaultName', { name: state.name }) : '';
  const controlsReady = state.ready && !state.busy;
  const regionTool = state.tool === 'sphere' || state.tool === 'box';
  const canDelete = controlsReady && state.selectedCount > 0;

  useEffect(() => {
    const onUnload = (event: BeforeUnloadEvent) => {
      if (state.dirty || state.busy) event.preventDefault();
    };
    window.addEventListener('beforeunload', onUnload);
    return () => window.removeEventListener('beforeunload', onUnload);
  }, [state.dirty, state.busy]);

  useEffect(() => {
    const store = useAppStore.getState();
    const wasCollapsed = store.sidebarCollapsed;
    if (!wasCollapsed) store.toggleSidebarCollapsed();
    return () => {
      if (!wasCollapsed && useAppStore.getState().sidebarCollapsed)
        useAppStore.getState().toggleSidebarCollapsed();
    };
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (showExit) return;
      if ((event.target as HTMLElement)?.closest('input, textarea, [contenteditable="true"]'))
        return;
      if ((event.ctrlKey || event.metaKey) && ['z', 'y'].includes(event.key.toLowerCase())) {
        event.preventDefault();
        event.stopImmediatePropagation();
        editor.travelHistory(event.key.toLowerCase() === 'y' || event.shiftKey ? 1 : -1);
      } else if (['Delete', 'Backspace'].includes(event.key)) {
        event.preventDefault();
        event.stopImmediatePropagation();
        editor.deleteSelection();
      } else if (event.key === 'Escape') {
        event.preventDefault();
        event.stopImmediatePropagation();
        editor.clearSelection();
      }
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => window.removeEventListener('keydown', onKeyDown, true);
  }, [editor, showExit]);

  const close = () => {
    editor.close();
    onClose();
  };
  const save = async () => {
    let asset = await editor.save(name ?? defaultName);
    if (!asset) return;
    const cover = await editor.captureCover();
    if (cover) {
      try {
        asset = await uploadModelAssetCover(
          asset.id,
          new File([cover], 'editor-cover.jpg', { type: 'image/jpeg' }),
          'system',
        );
      } catch {
        /* A cover failure must not hide the successfully saved model. */
      }
    }
    const store = useAppStore.getState();
    const source = resolveModelAssetSource(asset, store.effectiveModelFormat());
    editor.close();
    store.upsertModelAssets([asset]);
    if (source.url)
      store.setCurrentModel({
        id: asset.id,
        url: source.url,
        format: source.format,
        size: source.size,
        source: 'model-asset-generated',
        sourceMediaType: source.sourceMediaType,
        viewerOrientation: source.viewerOrientation,
        viewerCamera: source.viewerCamera,
        viewerTransform: source.viewerTransform,
      });
    onClose();
  };
  const changeTransform = (key: keyof ViewerTransformState, value: number) => {
    if (state.transform) editor.changeTransform({ ...state.transform, [key]: value });
  };
  const selectTool = (tool: EditorTool) => {
    editor.changeTool(tool);
  };

  return (
    <div className={styles.root} data-model-editor="true" aria-label={t('modelEditorTitle')}>
      <header className={styles.header}>
        <button
          className={styles.iconButton}
          aria-label={t('modelEditorExit')}
          title={t('modelEditorExit')}
          disabled={state.busy}
          onClick={() => (state.dirty ? setShowExit(true) : close())}
        >
          <ArrowLeft size={19} />
        </button>
        <div className={styles.title}>
          <span className={styles.eyebrow}>SHARP GUI</span>
          <h2>{t('modelEditorTitle')}</h2>
        </div>
        <div className={styles.history}>
          <button
            className={styles.iconButton}
            aria-label={t('modelEditorUndo')}
            title={t('modelEditorUndo')}
            disabled={!controlsReady || !state.canUndo}
            onClick={() => editor.travelHistory(-1)}
          >
            <Undo2 size={18} />
          </button>
          <button
            className={styles.iconButton}
            aria-label={t('modelEditorRedo')}
            title={t('modelEditorRedo')}
            disabled={!controlsReady || !state.canRedo}
            onClick={() => editor.travelHistory(1)}
          >
            <Redo2 size={18} />
          </button>
        </div>
        <button
          className={styles.saveButton}
          aria-label={t(state.busy ? 'modelEditorWorking' : 'modelEditorSave')}
          title={t('modelEditorSave')}
          disabled={!controlsReady || state.deletedCount === state.pointCount}
          onClick={() => void save()}
        >
          <Save size={16} />
          <span>{t(state.busy ? 'modelEditorWorking' : 'modelEditorSave')}</span>
        </button>
      </header>

      {state.ready && (
        <nav className={styles.views} aria-label={t('modelEditorViews')}>
          {(['front', 'side', 'top', 'saved'] as const).map((view) => (
            <button key={view} disabled={state.busy} onClick={() => editor.cameraView(view)}>
              {t(`modelEditorView${view[0].toUpperCase()}${view.slice(1)}`)}
            </button>
          ))}
          <button
            disabled={state.busy}
            aria-label={t('modelEditorGrid')}
            title={t('modelEditorGrid')}
            aria-pressed={state.gridVisible}
            onClick={editor.toggleGrid}
          >
            <Grid3X3 size={14} />
          </button>
        </nav>
      )}

      {(!state.ready || state.error) && (
        <div className={styles.message} role="status">
          <span className={state.error ? styles.error : ''}>
            {t(state.error ?? 'modelEditorLoading')}
          </span>
        </div>
      )}

      {state.rectangle && (
        <div
          className={styles.rectangle}
          style={{
            left: `${state.rectangle.left * 100}%`,
            top: `${state.rectangle.top * 100}%`,
            width: `${(state.rectangle.right - state.rectangle.left) * 100}%`,
            height: `${(state.rectangle.bottom - state.rectangle.top) * 100}%`,
          }}
        />
      )}

      {state.ready && (
        <>
          <button
            className={`${styles.inspectorToggle} ${styles.iconButton}`}
            aria-expanded={inspectorOpen}
            aria-label={t('modelEditorInspector')}
            onClick={() => setInspectorOpen((value) => !value)}
          >
            <SlidersHorizontal size={18} />
          </button>
          <aside
            key={state.tool}
            className={`${styles.inspector} ${inspectorOpen ? styles.inspectorOpen : ''}`}
          >
            <div className={styles.panelHeading}>
              <div>
                <span className={styles.eyebrow}>
                  {t(regionTool ? 'modelEditorSelection' : 'modelEditorTransform')}
                </span>
                <h3>{t(TOOLS.find((tool) => tool.id === state.tool)!.label)}</h3>
              </div>
              <button
                className={`${styles.iconButton} ${styles.mobileClose}`}
                aria-label={t('close')}
                onClick={() => setInspectorOpen(false)}
              >
                <X size={16} />
              </button>
            </div>
            <p className={styles.hint}>
              {t(
                regionTool
                  ? 'modelEditorRegionHint'
                  : state.tool === 'rectangle'
                    ? 'modelEditorRectangleHint'
                    : 'modelEditorTransformHint',
              )}
            </p>
            {regionTool ? (
              <>
                <section>
                  <h4>{t('modelEditorCenter')}</h4>
                  <div className={styles.fieldGrid}>
                    {(['X', 'Y', 'Z'] as const).map((axis, index) => (
                      <NumberField
                        key={axis}
                        label={axis}
                        value={state.region.center[index]}
                        disabled={state.busy}
                        onCommit={(value) => {
                          const center = [...state.region.center] as [number, number, number];
                          center[index] = value;
                          editor.changeRegion({ ...state.region, center });
                        }}
                      />
                    ))}
                  </div>
                </section>
                <section>
                  <h4>{t(state.tool === 'sphere' ? 'modelEditorRadius' : 'modelEditorSize')}</h4>
                  {state.tool === 'sphere' ? (
                    <NumberField
                      label="R"
                      value={state.region.radius}
                      min={0.00001}
                      disabled={state.busy}
                      onCommit={(radius) => editor.changeRegion({ ...state.region, radius })}
                    />
                  ) : (
                    <div className={styles.fieldGrid}>
                      {(['X', 'Y', 'Z'] as const).map((axis, index) => (
                        <NumberField
                          key={axis}
                          label={axis}
                          value={state.region.size[index]}
                          min={0.00001}
                          disabled={state.busy}
                          onCommit={(value) => {
                            const size = [...state.region.size] as [number, number, number];
                            size[index] = value;
                            editor.changeRegion({ ...state.region, size });
                          }}
                        />
                      ))}
                    </div>
                  )}
                </section>
              </>
            ) : (
              state.tool !== 'rectangle' &&
              state.transform && (
                <>
                  <section>
                    <h4>{t('modelEditorPosition')}</h4>
                    <div className={styles.fieldGrid}>
                      {(['X', 'Y', 'Z'] as const).map((axis) => (
                        <NumberField
                          key={axis}
                          label={axis}
                          value={state.transform![`position${axis}`]}
                          disabled={state.busy}
                          onCommit={(value) => changeTransform(`position${axis}`, value)}
                        />
                      ))}
                    </div>
                  </section>
                  <section>
                    <h4>
                      {t('modelEditorRotation')} <span>°</span>
                    </h4>
                    <div className={styles.fieldGrid}>
                      {(['X', 'Y', 'Z'] as const).map((axis) => (
                        <NumberField
                          key={axis}
                          label={axis}
                          value={(state.transform![`rotation${axis}`] * 180) / Math.PI}
                          disabled={state.busy}
                          onCommit={(value) =>
                            changeTransform(`rotation${axis}`, (value * Math.PI) / 180)
                          }
                        />
                      ))}
                    </div>
                  </section>
                  <section>
                    <h4>{t('modelEditorScale')}</h4>
                    <NumberField
                      label={t('modelEditorUniform')}
                      value={state.transform.scale}
                      min={0.00001}
                      max={10000}
                      disabled={state.busy}
                      onCommit={(value) => changeTransform('scale', value)}
                    />
                  </section>
                </>
              )
            )}
            <section className={styles.selectionSection}>
              <div className={styles.selectionSummary}>
                <span>{t('modelEditorSelected')}</span>
                <strong>{state.selectedCount.toLocaleString()}</strong>
              </div>
              <div className={styles.actionPair}>
                <button disabled={!canDelete} onClick={() => editor.deleteSelection()}>
                  <Trash2 size={15} />
                  {t('modelEditorDelete')}
                </button>
                <button disabled={!canDelete} onClick={() => editor.deleteSelection(true)}>
                  <Eraser size={15} />
                  {t('modelEditorKeep')}
                </button>
              </div>
              <button
                className={styles.clearButton}
                disabled={!canDelete}
                onClick={editor.clearSelection}
              >
                {t('modelEditorClear')}
              </button>
            </section>
            <section>
              <h4>{t('modelEditorCamera')}</h4>
              <button
                className={styles.cameraButton}
                disabled={!controlsReady}
                onClick={editor.setInitialCamera}
              >
                {state.cameraSet ? <Check size={15} /> : <Camera size={15} />}
                {t(state.cameraSet ? 'modelEditorCameraSet' : 'modelEditorSetCamera')}
              </button>
              <p className={styles.hint}>{t('modelEditorCameraHint')}</p>
            </section>
            <section>
              <label className={styles.nameField}>
                <span>{t('modelEditorName')}</span>
                <input
                  maxLength={160}
                  value={name ?? defaultName}
                  disabled={state.busy}
                  onChange={(event) => setName(event.target.value)}
                />
              </label>
              <p className={styles.hint}>{t('modelEditorCopyHint')}</p>
            </section>
          </aside>

          <div className={styles.bottomTools}>
            <div className={styles.toolRail} role="toolbar" aria-label={t('modelEditorTools')}>
              {TOOLS.map(({ id, label, icon: Icon }) => (
                <button
                  key={id}
                  className={state.tool === id ? styles.active : ''}
                  aria-pressed={state.tool === id}
                  disabled={state.busy}
                  onClick={() => selectTool(id)}
                >
                  <Icon size={18} />
                  <span>{t(label)}</span>
                </button>
              ))}
            </div>
            <p className={styles.shortcuts}>
              {t(state.tool === 'rectangle' ? 'modelEditorRectangleKeys' : 'modelEditorOrbitKeys')}
            </p>
          </div>
          <footer className={styles.status} aria-live="polite">
            <span className={styles.statusDot} />
            <span>{t(state.busy ? 'modelEditorWorking' : 'modelEditorReady')}</span>
            <span className={styles.statusDivider} />
            <span>
              {t('modelEditorRetained', {
                pointCount: (state.pointCount - state.deletedCount).toLocaleString(),
              })}
            </span>
            {state.deletedCount > 0 && (
              <span className={styles.removed}>
                {t('modelEditorRemoved', { pointCount: state.deletedCount.toLocaleString() })}
              </span>
            )}
          </footer>
        </>
      )}
      <div className={styles.confirmLayer}>
        <ConfirmDialog
          isOpen={showExit}
          title={t('modelEditorDiscardTitle')}
          message={t('modelEditorDiscardHint')}
          confirmLabel={t('modelEditorDiscard')}
          cancelLabel={t('modelEditorContinue')}
          danger
          onConfirm={close}
          onClose={() => setShowExit(false)}
        />
      </div>
    </div>
  );
}
