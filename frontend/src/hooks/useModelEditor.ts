import { useEffect, useRef, useState } from 'react';
import type { RefObject } from 'react';
import { dyno, RgbaArray, readRgbaArray, SplatMesh } from '@sparkjsdev/spark';
import * as THREE from 'three';
import { TransformControls } from 'three/addons/controls/TransformControls.js';

import { fetchEditorSource, saveEditedModel } from '@/api/modelEditor';
import { getSplatFileTypeFromFormat } from '@/constants/spark';
import type { ViewerContext } from '@/hooks/useViewer';
import type { ModelAsset } from '@/types/modelAsset';
import type { EditorRegion, EditorTool, ModelEditorDescriptor } from '@/types/modelEditor';
import type { ViewerCameraHint } from '@/types/modelPreview';
import type { ViewerTransformState } from '@/types/viewerQuickControls';
import {
  combineSelection,
  countMask,
  createRectanglePreview,
  encodeMask,
  inRegion,
  inScreenRectangle,
  maskBit,
  selectPoints,
  setMaskBit,
} from '@/utils/modelEditor';
import type { ScreenRectangle } from '@/utils/modelEditor';
import { getReconstructionCameraView } from '@/utils/viewerRuntime';

interface Snapshot {
  deleted: Uint8Array;
  transform: ViewerTransformState;
  camera: ViewerCameraHint;
}

interface Session {
  ctx: ViewerContext;
  original: SplatMesh;
  mesh: SplatMesh;
  descriptor: ModelEditorDescriptor;
  positions: Float32Array;
  mask: RgbaArray;
  deleted: Uint8Array;
  selected: Uint8Array;
  tool: EditorTool;
  region: EditorRegion;
  camera: ViewerCameraHint;
  startCamera: ViewerCameraHint;
  history: Snapshot[];
  historyIndex: number;
  revision: number;
  busy: boolean;
  closed: boolean;
  gizmo: TransformControls;
  regionObject: THREE.Object3D;
  transformObject: THREE.Object3D;
  pivotLocal: THREE.Vector3;
  sphere: THREE.LineSegments;
  box: THREE.LineSegments;
  grid: THREE.GridHelper;
  restore: () => void;
}

export interface EditorState {
  ready: boolean;
  busy: boolean;
  error: string | null;
  pointCount: number;
  deletedCount: number;
  selectedCount: number;
  tool: EditorTool;
  transform: ViewerTransformState | null;
  region: EditorRegion;
  canUndo: boolean;
  canRedo: boolean;
  dirty: boolean;
  cameraSet: boolean;
  gridVisible: boolean;
  rectangle: ScreenRectangle | null;
  name: string;
}

const INITIAL_REGION: EditorRegion = { center: [0, 0, 0], radius: 1, size: [2, 2, 2] };
const INITIAL_STATE: EditorState = {
  ready: false,
  busy: false,
  error: null,
  pointCount: 0,
  deletedCount: 0,
  selectedCount: 0,
  tool: 'move',
  transform: null,
  region: INITIAL_REGION,
  canUndo: false,
  canRedo: false,
  dirty: false,
  cameraSet: false,
  gridVisible: false,
  rectangle: null,
  name: '',
};

function captureCamera(ctx: ViewerContext): ViewerCameraHint {
  return {
    position: ctx.camera.position.toArray(),
    target: ctx.controls.target.toArray(),
    up: ctx.camera.up.toArray(),
    fov_y_degrees: ctx.camera.fov,
    aspect: ctx.camera.aspect,
  };
}

function applyCamera(ctx: ViewerContext, hint: ViewerCameraHint) {
  ctx.camera.position.fromArray(hint.position);
  ctx.camera.up.fromArray(hint.up);
  const fitted = getReconstructionCameraView(hint, new THREE.Matrix4(), ctx.camera.aspect);
  ctx.camera.fov = fitted?.fov ?? hint.fov_y_degrees;
  ctx.camera.updateProjectionMatrix();
  ctx.controls.target.fromArray(hint.target);
  ctx.controls.update();
}

function getTransform(mesh: SplatMesh): ViewerTransformState {
  return {
    positionX: mesh.position.x,
    positionY: mesh.position.y,
    positionZ: mesh.position.z,
    rotationX: mesh.rotation.x,
    rotationY: mesh.rotation.y,
    rotationZ: mesh.rotation.z,
    scale: mesh.scale.x,
  };
}

function setTransform(mesh: SplatMesh, value: ViewerTransformState) {
  mesh.position.set(value.positionX, value.positionY, value.positionZ);
  mesh.rotation.set(value.rotationX, value.rotationY, value.rotationZ);
  mesh.scale.setScalar(value.scale);
  mesh.updateMatrixWorld(true);
  mesh.updateVersion();
}

function snapshot(session: Session): Snapshot {
  return {
    deleted: session.deleted.slice(),
    transform: getTransform(session.mesh),
    camera: structuredClone(session.camera),
  };
}

function recordHistory(session: Session) {
  const next = snapshot(session);
  const previous = session.history[session.historyIndex];
  if (
    JSON.stringify(next.transform) === JSON.stringify(previous.transform) &&
    JSON.stringify(next.camera) === JSON.stringify(previous.camera) &&
    next.deleted.every((value, index) => value === previous.deleted[index])
  )
    return;
  session.history = session.history.slice(0, session.historyIndex + 1);
  session.history.push(next);
  // Bound bitmap memory as well as entry count for multi-million point models.
  const limit = Math.max(2, Math.min(40, Math.floor((32 * 1024 * 1024) / next.deleted.byteLength)));
  if (session.history.length > limit) session.history.splice(0, session.history.length - limit);
  session.historyIndex = session.history.length - 1;
}

function updateMask(session: Session) {
  const array = session.mask.ensureCapacity(session.descriptor.point_count);
  for (let i = 0; i < session.descriptor.point_count; i++) {
    array[i * 4] = maskBit(session.deleted, i) ? 255 : 0;
    array[i * 4 + 1] = maskBit(session.selected, i) ? 255 : 0;
    array[i * 4 + 3] = 255;
  }
  session.mask.needsUpdate = true;
  session.mesh.updateVersion();
}

function syncHelpers(session: Session) {
  const { region, regionObject, sphere, box, tool } = session;
  regionObject.position.fromArray(region.center);
  sphere.position.copy(regionObject.position);
  sphere.scale.setScalar(region.radius);
  box.position.copy(regionObject.position);
  box.scale.fromArray(region.size);
  sphere.visible = tool === 'sphere';
  box.visible = tool === 'box';
  session.gizmo.setMode(tool === 'rotate' ? 'rotate' : 'translate');
  session.mesh.updateMatrixWorld(true);
  session.transformObject.position.copy(session.pivotLocal).applyMatrix4(session.mesh.matrixWorld);
  session.transformObject.quaternion.copy(session.mesh.quaternion);
  session.transformObject.updateMatrixWorld(true);
  session.gizmo.attach(
    tool === 'sphere' || tool === 'box' ? regionObject : session.transformObject,
  );
  session.gizmo.enabled = tool !== 'rectangle' && !session.busy;
  session.gizmo.getHelper().visible = tool !== 'rectangle';
}

function createMaskModifier(mask: RgbaArray) {
  return dyno.dynoBlock({ gsplat: dyno.Gsplat }, { gsplat: dyno.Gsplat }, ({ gsplat }) => {
    const flags = readRgbaArray(mask.dyno, dyno.splitGsplat(gsplat!).outputs.index!);
    const node = new dyno.Dyno({
      inTypes: { gsplat: dyno.Gsplat, flags: 'vec4' },
      outTypes: { gsplat: dyno.Gsplat },
      inputs: { gsplat, flags },
      statements: ({ inputs, outputs }) =>
        dyno.unindentLines(`
        ${outputs.gsplat} = ${inputs.gsplat};
        if (${inputs.flags}.r > 0.5) {
          ${outputs.gsplat}.rgba.a = 0.0;
        } else if (${inputs.flags}.g > 0.5) {
          ${outputs.gsplat}.rgba.rgb = mix(${outputs.gsplat}.rgba.rgb, vec3(1.0, 0.68, 0.13), 0.65);
        }
      `),
    });
    return node.outputs;
  });
}

function createSphereOutline() {
  const points: number[] = [];
  for (let axis = 0; axis < 3; axis++) {
    for (let step = 0; step < 96; step++) {
      for (const angle of [(step * Math.PI) / 48, ((step + 1) * Math.PI) / 48]) {
        const point = [Math.cos(angle), Math.sin(angle), 0];
        points.push(
          ...(axis === 0 ? point : axis === 1 ? [point[0], 0, point[1]] : [0, point[0], point[1]]),
        );
      }
    }
  }
  return new THREE.BufferGeometry().setAttribute(
    'position',
    new THREE.Float32BufferAttribute(points, 3),
  );
}

export function useModelEditor(viewerRef: RefObject<ViewerContext | null>, assetId: string) {
  const sessionRef = useRef<Session | null>(null);
  const [state, setState] = useState<EditorState>(INITIAL_STATE);
  const publish = (session: Session) => {
    if (session.closed) return;
    setState((previous) => ({
      ...previous,
      ready: true,
      busy: session.busy,
      pointCount: session.descriptor.point_count,
      deletedCount: countMask(session.deleted),
      selectedCount: countMask(session.selected),
      tool: session.tool,
      gridVisible: session.grid.visible,
      transform: getTransform(session.mesh),
      region: structuredClone(session.region),
      canUndo: session.historyIndex > 0,
      canRedo: session.historyIndex < session.history.length - 1,
      dirty: session.history.length > 1 || session.historyIndex > 0,
    }));
  };

  const runSelection = async (
    session: Session,
    predicate: (x: number, y: number, z: number) => boolean,
    mode: 'replace' | 'add' | 'subtract' = 'replace',
  ) => {
    const revision = ++session.revision;
    session.busy = true;
    syncHelpers(session);
    publish(session);
    setState((previous) => ({ ...previous, error: null }));
    try {
      const selection = await selectPoints(
        session.positions,
        session.deleted,
        predicate,
        () => session.closed || revision !== session.revision,
      );
      if (!selection || session.closed) return;
      session.selected = combineSelection(session.selected, selection, mode);
      updateMask(session);
    } catch {
      if (!session.closed && revision === session.revision) {
        setState((previous) => ({ ...previous, error: 'modelEditorSelectionError' }));
      }
    } finally {
      if (!session.closed && revision === session.revision) {
        session.busy = false;
        syncHelpers(session);
        publish(session);
      }
    }
  };

  const selectRegion = (session: Session) => {
    session.mesh.updateMatrixWorld(true);
    const matrix = session.mesh.matrixWorld.elements.slice();
    const region = structuredClone(session.region);
    void runSelection(session, (x, y, z) =>
      inRegion(x, y, z, matrix, region, session.tool === 'sphere'),
    );
  };

  useEffect(() => {
    let closed = false;
    let loadingMesh: SplatMesh | null = null;
    const abort = new AbortController();
    const initialize = async () => {
      try {
        const descriptor = await fetchEditorSource(assetId, abort.signal);
        const ctx = viewerRef.current;
        if (closed || !ctx?.splatMesh) return;
        const original = ctx.splatMesh;
        const mesh = new SplatMesh({
          url: descriptor.source_url + '?v=' + descriptor.fingerprint,
          fileType: getSplatFileTypeFromFormat(descriptor.format),
          lod: false,
          nonLod: true,
          editable: true,
        });
        loadingMesh = mesh;
        await mesh.initialized;
        if (closed) {
          mesh.dispose();
          loadingMesh = null;
          return;
        }
        if (viewerRef.current !== ctx || ctx.splatMesh !== original)
          throw new Error('model_editor_source_changed');
        if (mesh.splats?.getNumSplats() !== descriptor.point_count)
          throw new Error('model_editor_source_changed');
        mesh.position.copy(original.position);
        mesh.quaternion.copy(original.quaternion);
        mesh.scale.copy(original.scale);
        mesh.updateMatrixWorld(true);
        const positions = new Float32Array(descriptor.point_count * 3);
        mesh.forEachSplat((i, center) => center.toArray(positions, i * 3));
        const mask = new RgbaArray({
          capacity: descriptor.point_count,
          count: descriptor.point_count,
        });
        // Spark only reads options.count when options.array is supplied.
        mask.count = descriptor.point_count;
        mesh.objectModifier = createMaskModifier(mask);
        mesh.updateGenerator();
        const gizmo = new TransformControls(ctx.camera, ctx.renderer.domElement);
        gizmo.setSize(0.85);
        const sphere = new THREE.LineSegments(
          createSphereOutline(),
          new THREE.LineBasicMaterial({
            color: 0x3986ff,
            transparent: true,
            opacity: 0.7,
            depthTest: false,
          }),
        );
        const box = new THREE.LineSegments(
          new THREE.EdgesGeometry(new THREE.BoxGeometry(1, 1, 1)),
          new THREE.LineBasicMaterial({ color: 0x3986ff, depthTest: false }),
        );
        sphere.renderOrder = box.renderOrder = 1000;
        const camera = captureCamera(ctx);
        const distance = Math.max(0.01, ctx.camera.position.distanceTo(ctx.controls.target));
        const radius = distance * Math.tan(THREE.MathUtils.degToRad(ctx.camera.fov / 2)) * 0.7;
        const gridSize = 10 ** Math.ceil(Math.log10(Math.max(radius * 6, 0.001)));
        const grid = new THREE.GridHelper(gridSize, 20, 0x667b9b, 0x667b9b);
        grid.visible = false;
        grid.position.copy(ctx.controls.target);
        const gridMaterial = grid.material as THREE.Material;
        gridMaterial.transparent = true;
        gridMaterial.opacity = 0.15;
        const controls = ctx.controls;
        const controlsBackup = {
          minPolarAngle: controls.minPolarAngle,
          maxPolarAngle: controls.maxPolarAngle,
          minAzimuthAngle: controls.minAzimuthAngle,
          maxAzimuthAngle: controls.maxAzimuthAngle,
          enabled: controls.enabled,
          enablePan: controls.enablePan,
          mouseButtons: { ...controls.mouseButtons },
        };
        controls.minPolarAngle = 0;
        controls.maxPolarAngle = Math.PI;
        controls.minAzimuthAngle = -Infinity;
        controls.maxAzimuthAngle = Infinity;
        controls.enablePan = true;
        const session: Session = {
          ctx,
          original,
          mesh,
          descriptor,
          positions,
          mask,
          deleted: new Uint8Array(Math.ceil(descriptor.point_count / 8)),
          selected: new Uint8Array(Math.ceil(descriptor.point_count / 8)),
          tool: 'move',
          region: {
            center: ctx.controls.target.toArray(),
            radius,
            size: [radius * 2, radius * 2, radius * 2],
          },
          camera,
          startCamera: structuredClone(camera),
          history: [],
          historyIndex: 0,
          revision: 0,
          busy: false,
          closed: false,
          gizmo,
          sphere,
          box,
          grid,
          regionObject: new THREE.Object3D(),
          transformObject: new THREE.Object3D(),
          pivotLocal: ctx.controls.target.clone().applyMatrix4(mesh.matrixWorld.clone().invert()),
          restore: () => {},
        };
        session.history.push(snapshot(session));
        sessionRef.current = session;
        ctx.editorActive = true;
        const framingBackup = ctx.lastFramingMode;
        ctx.lastFramingMode = 'default';
        original.visible = false;
        ctx.splatMesh = mesh;
        ctx.scene.add(
          mesh,
          gizmo.getHelper(),
          sphere,
          box,
          grid,
          session.regionObject,
          session.transformObject,
        );
        updateMask(session);
        syncHelpers(session);
        let start: {
          x: number;
          y: number;
          mode: 'replace' | 'add' | 'subtract';
          pointerId: number;
        } | null = null;
        const canvas = ctx.renderer.domElement;
        const editorResize = new ResizeObserver(() => {
          if (session.closed || session.busy) return;
          const bounds = canvas.getBoundingClientRect();
          if (!bounds.width || !bounds.height) return;
          ctx.camera.aspect = bounds.width / bounds.height;
          const fitted = getReconstructionCameraView(
            camera,
            new THREE.Matrix4(),
            ctx.camera.aspect,
          );
          if (fitted) ctx.camera.fov = fitted.fov;
          ctx.camera.updateProjectionMatrix();
        });
        editorResize.observe(canvas);
        const point = (event: PointerEvent) => {
          const rect = canvas.getBoundingClientRect();
          return {
            x: (event.clientX - rect.left) / rect.width,
            y: (event.clientY - rect.top) / rect.height,
          };
        };
        const rectangle = (end: { x: number; y: number }): ScreenRectangle => ({
          left: Math.min(start!.x, end.x),
          right: Math.max(start!.x, end.x),
          top: Math.min(start!.y, end.y),
          bottom: Math.max(start!.y, end.y),
        });
        const rectanglePreview = createRectanglePreview((rect) => {
          setState((previous) => ({ ...previous, rectangle: rect }));
        });
        const onDown = (event: PointerEvent) => {
          if (session.tool !== 'rectangle' || event.button !== 0 || session.busy) return;
          event.preventDefault();
          event.stopImmediatePropagation();
          canvas.setPointerCapture(event.pointerId);
          start = {
            ...point(event),
            pointerId: event.pointerId,
            mode: event.ctrlKey || event.metaKey ? 'subtract' : event.shiftKey ? 'add' : 'replace',
          };
        };
        const onMove = (event: PointerEvent) => {
          if (!start || event.pointerId !== start.pointerId) return;
          event.stopImmediatePropagation();
          // Continuous pointer updates can be applied after pointerup clears start.
          // Capture the rectangle now; React's updater must only read this snapshot.
          const rect = rectangle(point(event));
          rectanglePreview.update(rect);
        };
        const onUp = (event: PointerEvent) => {
          if (!start || event.pointerId !== start.pointerId) return;
          event.preventDefault();
          event.stopImmediatePropagation();
          const rect = rectangle(point(event));
          const mode = start.mode;
          start = null;
          canvas.releasePointerCapture(event.pointerId);
          rectanglePreview.clear();
          if (rect.right - rect.left < 0.002 || rect.bottom - rect.top < 0.002) return;
          ctx.camera.updateMatrixWorld(true);
          mesh.updateMatrixWorld(true);
          const projection = new THREE.Matrix4()
            .multiplyMatrices(ctx.camera.projectionMatrix, ctx.camera.matrixWorldInverse)
            .multiply(mesh.matrixWorld).elements;
          void runSelection(
            session,
            (x, y, z) => inScreenRectangle(x, y, z, projection, rect),
            mode,
          );
        };
        const onCancel = () => {
          start = null;
          rectanglePreview.clear();
        };
        let dragPivotInverse: THREE.Matrix4 | null = null;
        let dragModelMatrix: THREE.Matrix4 | null = null;
        const onDragging = (event: { value: unknown }) => {
          controls.enabled = !event.value;
          if (event.value) {
            session.transformObject.updateMatrixWorld(true);
            mesh.updateMatrixWorld(true);
            dragPivotInverse = session.transformObject.matrixWorld.clone().invert();
            dragModelMatrix = mesh.matrixWorld.clone();
          }
        };
        const onChange = () => {
          if (session.tool === 'sphere' || session.tool === 'box') {
            session.region.center = session.regionObject.position.toArray();
            sphere.position.copy(session.regionObject.position);
            box.position.copy(session.regionObject.position);
          } else if (dragPivotInverse && dragModelMatrix) {
            session.transformObject.updateMatrixWorld(true);
            new THREE.Matrix4()
              .multiplyMatrices(session.transformObject.matrixWorld, dragPivotInverse)
              .multiply(dragModelMatrix)
              .decompose(mesh.position, mesh.quaternion, mesh.scale);
            mesh.updateVersion();
          }
          mesh.updateMatrixWorld(true);
          publish(session);
        };
        const onCommit = () => {
          if (session.tool === 'sphere' || session.tool === 'box') selectRegion(session);
          else {
            recordHistory(session);
            publish(session);
          }
          dragPivotInverse = null;
          dragModelMatrix = null;
          syncHelpers(session);
        };
        gizmo.addEventListener('dragging-changed', onDragging);
        gizmo.addEventListener('objectChange', onChange);
        gizmo.addEventListener('mouseUp', onCommit);
        canvas.addEventListener('pointerdown', onDown, true);
        canvas.addEventListener('pointermove', onMove, true);
        canvas.addEventListener('pointerup', onUp, true);
        canvas.addEventListener('pointercancel', onCancel, true);
        session.restore = () => {
          if (session.closed) return;
          session.closed = true;
          session.revision++;
          rectanglePreview.clear();
          editorResize.disconnect();
          canvas.removeEventListener('pointerdown', onDown, true);
          canvas.removeEventListener('pointermove', onMove, true);
          canvas.removeEventListener('pointerup', onUp, true);
          canvas.removeEventListener('pointercancel', onCancel, true);
          gizmo.detach();
          ctx.scene.remove(
            mesh,
            gizmo.getHelper(),
            sphere,
            box,
            grid,
            session.regionObject,
            session.transformObject,
          );
          gizmo.dispose();
          sphere.geometry.dispose();
          (sphere.material as THREE.Material).dispose();
          box.geometry.dispose();
          (box.material as THREE.Material).dispose();
          grid.geometry.dispose();
          gridMaterial.dispose();
          mask.dispose();
          mesh.dispose();
          loadingMesh = null;
          if (viewerRef.current === ctx && ctx.splatMesh === mesh) {
            ctx.splatMesh = original;
            original.visible = true;
            ctx.editorActive = false;
            ctx.lastFramingMode = framingBackup;
            Object.assign(controls, controlsBackup);
            applyCamera(ctx, session.startCamera);
          } else original.dispose();
        };
        setState((previous) => ({
          ...previous,
          name: descriptor.name.slice(0, 140),
        }));
        publish(session);
      } catch (error) {
        if (!closed) {
          loadingMesh?.dispose();
          loadingMesh = null;
          setState((previous) => ({
            ...previous,
            error:
              error instanceof Error && error.message === 'model_editor_source_changed'
                ? 'modelEditorSourceChanged'
                : 'modelEditorLoadError',
          }));
        }
      }
    };
    void initialize();
    return () => {
      closed = true;
      abort.abort();
      sessionRef.current?.restore();
      sessionRef.current = null;
      if (loadingMesh) {
        void loadingMesh.initialized.then(
          () => loadingMesh?.dispose(),
          () => loadingMesh?.dispose(),
        );
      }
    };
    // A session owns these handlers until the editor is closed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assetId, viewerRef]);

  function changeTool(tool: EditorTool) {
    const session = sessionRef.current;
    if (!session || session.busy) return;
    session.tool = tool;
    session.ctx.controls.mouseButtons.LEFT = tool === 'rectangle' ? null : THREE.MOUSE.ROTATE;
    session.ctx.controls.mouseButtons.MIDDLE = THREE.MOUSE.ROTATE;
    session.ctx.controls.mouseButtons.RIGHT = THREE.MOUSE.PAN;
    syncHelpers(session);
    if (tool === 'sphere' || tool === 'box') selectRegion(session);
    else publish(session);
  }

  function changeTransform(value: ViewerTransformState) {
    const session = sessionRef.current;
    if (
      !session ||
      session.busy ||
      !Object.values(value).every(Number.isFinite) ||
      value.scale < 0.00001 ||
      value.scale > 10000
    )
      return;
    setTransform(session.mesh, value);
    syncHelpers(session);
    recordHistory(session);
    publish(session);
  }

  function changeRegion(region: EditorRegion) {
    const session = sessionRef.current;
    if (
      !session ||
      session.busy ||
      ![...region.center, ...region.size, region.radius].every(Number.isFinite) ||
      region.radius <= 0 ||
      region.size.some((v) => v <= 0)
    )
      return;
    session.region = region;
    syncHelpers(session);
    selectRegion(session);
  }

  function deleteSelection(keep = false) {
    const session = sessionRef.current;
    if (!session || session.busy || countMask(session.selected) === 0) return;
    for (let i = 0; i < session.descriptor.point_count; i++) {
      if (keep ? !maskBit(session.selected, i) : maskBit(session.selected, i))
        setMaskBit(session.deleted, i);
    }
    session.selected.fill(0);
    recordHistory(session);
    updateMask(session);
    publish(session);
  }

  function clearSelection() {
    const session = sessionRef.current;
    if (!session || session.busy) return;
    session.selected.fill(0);
    updateMask(session);
    publish(session);
  }

  function toggleGrid() {
    const session = sessionRef.current;
    if (!session || session.busy) return;
    session.grid.visible = !session.grid.visible;
    publish(session);
  }

  function travelHistory(direction: number) {
    const session = sessionRef.current;
    if (!session || session.busy) return;
    const index = session.historyIndex + direction;
    if (index < 0 || index >= session.history.length) return;
    session.historyIndex = index;
    const entry = session.history[index];
    session.deleted = entry.deleted.slice();
    session.selected.fill(0);
    session.camera = structuredClone(entry.camera);
    setTransform(session.mesh, entry.transform);
    syncHelpers(session);
    applyCamera(session.ctx, entry.camera);
    updateMask(session);
    publish(session);
  }

  function setInitialCamera() {
    const session = sessionRef.current;
    if (!session || session.busy) return;
    session.camera = captureCamera(session.ctx);
    recordHistory(session);
    publish(session);
    setState((previous) => ({ ...previous, cameraSet: true }));
  }

  function cameraView(view: 'front' | 'side' | 'top' | 'saved') {
    const session = sessionRef.current;
    if (!session || session.busy) return;
    const { ctx } = session;
    if (view === 'saved') {
      applyCamera(ctx, session.camera);
      return;
    }
    const distance = ctx.camera.position.distanceTo(ctx.controls.target);
    ctx.camera.up.set(0, view === 'top' ? 0 : 1, view === 'top' ? -1 : 0);
    ctx.camera.position
      .copy(ctx.controls.target)
      .add(
        new THREE.Vector3(
          view === 'side' ? distance : 0,
          view === 'top' ? distance : 0,
          view === 'front' ? distance : 0,
        ),
      );
    ctx.controls.update();
  }

  async function save(name: string): Promise<ModelAsset | null> {
    const session = sessionRef.current;
    if (!session || session.busy || countMask(session.deleted) === session.descriptor.point_count)
      return null;
    session.busy = true;
    syncHelpers(session);
    publish(session);
    setState((previous) => ({ ...previous, error: null }));
    const controlsEnabled = session.ctx.controls.enabled;
    session.ctx.controls.enabled = false;
    session.mesh.updateMatrixWorld(true);
    let saved = false;
    try {
      const asset = await saveEditedModel(assetId, {
        fingerprint: session.descriptor.fingerprint,
        point_count: session.descriptor.point_count,
        deleted_mask: encodeMask(session.deleted),
        matrix: session.mesh.matrixWorld.toArray(),
        camera: session.camera,
        name,
      });
      saved = true;
      return asset;
    } catch {
      if (!session.closed) setState((previous) => ({ ...previous, error: 'modelEditorSaveError' }));
      return null;
    } finally {
      if (!session.closed && !saved) {
        session.busy = false;
        session.ctx.controls.enabled = controlsEnabled;
        syncHelpers(session);
        publish(session);
      }
    }
  }

  async function captureCover(): Promise<Blob | null> {
    const session = sessionRef.current;
    if (!session || session.closed) return null;
    const { ctx } = session;
    const previousCamera = captureCamera(ctx);
    const helpers = [session.gizmo.getHelper(), session.sphere, session.box, session.grid];
    const visibility = helpers.map((helper) => helper.visible);
    const previousSelection = session.selected;
    try {
      helpers.forEach((helper) => {
        helper.visible = false;
      });
      session.selected = new Uint8Array(previousSelection.length);
      updateMask(session);
      applyCamera(ctx, session.camera);
      // Spark updates its sorted render data asynchronously before the next frame.
      for (let i = 0; i < 3; i++)
        await new Promise<void>((resolve) =>
          requestAnimationFrame(() => {
            ctx.renderer.render(ctx.scene, ctx.camera);
            resolve();
          }),
        );
      return await new Promise<Blob | null>((resolve) =>
        ctx.renderer.domElement.toBlob(resolve, 'image/jpeg', 0.9),
      );
    } catch {
      return null;
    } finally {
      if (!session.closed) {
        helpers.forEach((helper, i) => {
          helper.visible = visibility[i];
        });
        session.selected = previousSelection;
        updateMask(session);
        applyCamera(ctx, previousCamera);
      }
    }
  }

  return {
    state,
    changeTool,
    changeTransform,
    changeRegion,
    deleteSelection,
    clearSelection,
    toggleGrid,
    travelHistory,
    setInitialCamera,
    cameraView,
    save,
    captureCover,
    close: () => sessionRef.current?.restore(),
  };
}
