import { useCallback, useEffect, useRef } from 'react';
import type { RefObject } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { Line2 } from 'three/addons/lines/Line2.js';
import { LineGeometry } from 'three/addons/lines/LineGeometry.js';
import { LineMaterial } from 'three/addons/lines/LineMaterial.js';
import type { ViewerContext } from '@/hooks/useViewer';
import { captureCameraPose, sampleCameraAnimation } from '@/utils/cameraAnimation';
import type { CameraAnimationCurve, CameraKeyframe, CameraPose } from '@/utils/cameraAnimation';
import { cameraFrustumVertices, CAMERA_PATH_LAYER, cameraPathSampleTimes, disposeCameraPath, isolateCameraPath } from '@/utils/cameraPathGeometry';
import { getShareBoundsView } from '@/utils/shareFraming';

interface CameraGlyph {
  group: THREE.Group;
  wire: THREE.LineSegments<THREE.BufferGeometry, THREE.LineBasicMaterial>;
  marker: THREE.Mesh<THREE.SphereGeometry, THREE.MeshBasicMaterial>;
}
interface OverviewRuntime {
  ctx: ViewerContext;
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  group: THREE.Group;
  staticGroup: THREE.Group;
  current: CameraGlyph;
  length: number;
  bounds: THREE.Box3;
  glyphs: Map<string, CameraGlyph>;
  labels: THREE.Sprite[];
  didFit: boolean;
  lastFrameCount: number;
  pathMaterial: LineMaterial | null;
}

function createGlyph(length: number, color: string): CameraGlyph {
  const group = new THREE.Group();
  const wire = new THREE.LineSegments(
    new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(cameraFrustumVertices(1, 90, 1), 3)),
    new THREE.LineBasicMaterial({ color, depthTest: false, depthWrite: false, transparent: true, opacity: 0.9 }),
  );
  const marker = new THREE.Mesh(new THREE.SphereGeometry(length * 0.07, 12, 8),
    new THREE.MeshBasicMaterial({ color, depthTest: false, depthWrite: false }));
  group.add(wire, marker); isolateCameraPath(group);
  return { group, wire, marker };
}

function positionGlyph(glyph: CameraGlyph, pose: CameraPose, length: number, aspect: number) {
  glyph.group.position.fromArray(pose.position);
  glyph.group.quaternion.fromArray(pose.quaternion);
  const tangent = Math.tan(THREE.MathUtils.degToRad(pose.fov) / 2);
  const depth = length / Math.max(1, tangent * aspect);
  glyph.wire.scale.set(depth * tangent * aspect, depth * tangent, depth);
}

function numberedLabel(index: number, position: CameraPose['position']) {
  const canvas = document.createElement('canvas'); canvas.width = 64; canvas.height = 64;
  const context = canvas.getContext('2d')!;
  context.fillStyle = '#0071e3'; context.beginPath(); context.arc(32, 32, 27, 0, Math.PI * 2); context.fill();
  context.strokeStyle = 'rgba(255,255,255,0.8)'; context.lineWidth = 2; context.stroke();
  context.fillStyle = '#fff'; context.font = '600 30px system-ui'; context.textAlign = 'center'; context.textBaseline = 'middle'; context.fillText(String(index), 32, 33);
  const texture = new THREE.CanvasTexture(canvas); texture.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, depthTest: false, depthWrite: false }));
  sprite.position.fromArray(position); sprite.center.set(0.5, -0.35);
  isolateCameraPath(sprite);
  return sprite;
}

export function useCameraPathOverview(
  viewerRef: RefObject<ViewerContext | null>, enabled: boolean, frames: CameraKeyframe[],
  easing: CameraAnimationCurve, portrait: boolean, selected: string | null,
) {
  const runtimeRef = useRef<OverviewRuntime | null>(null);
  const selectedRef = useRef(selected);
  useEffect(() => { selectedRef.current = selected; }, [selected]);

  const fit = useCallback(() => {
    const runtime = runtimeRef.current;
    if (!runtime || runtime.ctx.disposed) return;
    const direction = runtime.didFit
      ? runtime.camera.position.clone().sub(runtime.controls.target).normalize()
      : new THREE.Vector3(1, 0.65, 1).normalize();
    const view = getShareBoundsView(runtime.bounds, runtime.camera.aspect, runtime.camera.fov, direction);
    if (!view) return;
    runtime.camera.position.copy(view.position); runtime.controls.target.copy(view.target);
    runtime.camera.near = Math.max(0.0001, view.radius / 10000);
    runtime.camera.far = Math.max(1000, view.radius * 100);
    runtime.camera.updateProjectionMatrix(); runtime.controls.update(); runtime.didFit = true;
  }, []);

  useEffect(() => {
    if (!enabled) return;
    const ctx = viewerRef.current;
    if (!ctx || !ctx.splatMesh) return;
    const camera = new THREE.PerspectiveCamera(50, ctx.camera.aspect, 0.001, 10000);
    camera.layers.enable(CAMERA_PATH_LAYER);
    const controls = new OrbitControls(camera, ctx.renderer.domElement);
    controls.enableDamping = true; controls.dampingFactor = 0.08; controls.minDistance = 0.001;
    controls.mouseButtons = { LEFT: THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.PAN };
    controls.rotateSpeed = ctx.controls.rotateSpeed;
    controls.panSpeed = ctx.controls.panSpeed;
    controls.zoomSpeed = ctx.controls.zoomSpeed;
    ctx.controls.enabled = false;
    const group = new THREE.Group(); const staticGroup = new THREE.Group();
    const current = createGlyph(0.5, '#ffffff');
    group.add(staticGroup, current.group); isolateCameraPath(group); ctx.scene.add(group);
    const runtime: OverviewRuntime = { ctx, camera, controls, group, staticGroup, current,
      length: 0.5, bounds: new THREE.Box3(), glyphs: new Map(), labels: [], didFit: false, lastFrameCount: 0, pathMaterial: null };
    runtimeRef.current = runtime;
    ctx.cameraOverview = {
      camera, controls,
      update: () => {
        positionGlyph(runtime.current, captureCameraPose(ctx.camera, ctx.controls.target), runtime.length * 1.15, ctx.camera.aspect);
        for (const [id, glyph] of runtime.glyphs) {
          glyph.wire.material.color.set(id === selectedRef.current ? '#b9dfff' : '#4fa3ff');
        }
        const viewportHeight = Math.max(1, ctx.renderer.domElement.clientHeight);
        runtime.pathMaterial?.resolution.set(Math.max(1, ctx.renderer.domElement.clientWidth), viewportHeight);
        for (const label of runtime.labels) {
          const size = 2 * camera.position.distanceTo(label.position) * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2) / viewportHeight * 25;
          label.scale.setScalar(size);
        }
      },
    };
    return () => {
      controls.dispose(); disposeCameraPath(group);
      if (ctx.cameraOverview?.camera === camera) ctx.cameraOverview = undefined;
      // Playback may have started or stopped while observing. Panel teardown restores
      // its own original controls snapshot; mode switches use the current playback state.
      if (!ctx.disposed && ctx.animationActive) ctx.controls.enabled = !ctx.cameraPlayback;
      runtimeRef.current = null;
    };
  }, [enabled, viewerRef]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!enabled || !runtime) return;
    const { ctx } = runtime;
    disposeCameraPath(runtime.staticGroup);
    disposeCameraPath(runtime.current.group);
    const staticGroup = new THREE.Group(); runtime.staticGroup = staticGroup; runtime.group.add(staticGroup);
    const bounds = ctx.debugBounds?.clone() ?? new THREE.Box3();
    for (const frame of frames) bounds.expandByPoint(new THREE.Vector3().fromArray(frame.position));
    if (bounds.isEmpty()) bounds.set(new THREE.Vector3(-1, -1, -1), new THREE.Vector3(1, 1, 1));
    const length = Math.max(0.001, bounds.getSize(new THREE.Vector3()).length() * 0.09);
    runtime.length = length;
    runtime.current = createGlyph(length, '#ffffff'); runtime.group.add(runtime.current.group);
    runtime.glyphs.clear(); runtime.labels = [];
    runtime.pathMaterial = null;
    const aspect = portrait ? 9 / 16 : 16 / 9;
    frames.forEach((frame, index) => {
      const glyph = createGlyph(length, '#4fa3ff'); positionGlyph(glyph, frame, length, aspect);
      const label = numberedLabel(index + 1, frame.position);
      staticGroup.add(glyph.group, label); runtime.glyphs.set(frame.id, glyph); runtime.labels.push(label);
    });
    if (frames.length >= 2) {
      const points = cameraPathSampleTimes(frames).map(time =>
        new THREE.Vector3().fromArray(sampleCameraAnimation(frames, time, easing)!.position));
      const count = points.length - 1;
      for (const point of points) bounds.expandByPoint(point);
      const pathMaterial = new LineMaterial({ color: '#79c2ff', linewidth: 2.5, depthTest: false, depthWrite: false, transparent: true, opacity: 0.95 });
      runtime.pathMaterial = pathMaterial;
      staticGroup.add(new Line2(new LineGeometry().setPositions(points.flatMap(point => point.toArray())), pathMaterial));
      for (let index = 1; index < 8; index += 1) {
        const i = Math.floor(count * index / 8);
        const direction = points[i + 1].clone().sub(points[i]);
        if (direction.length() < length * 0.001) continue;
        const arrow = new THREE.Mesh(new THREE.ConeGeometry(length * 0.09, length * 0.3, 8),
          new THREE.MeshBasicMaterial({ color: '#4fa3ff', depthTest: false, depthWrite: false }));
        arrow.position.copy(points[i]); arrow.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.normalize());
        staticGroup.add(arrow);
      }
    }
    isolateCameraPath(staticGroup);
    runtime.bounds = bounds.expandByScalar(length * 2);
    const needsFit = !runtime.didFit || (runtime.lastFrameCount === 0 && frames.length > 0);
    runtime.lastFrameCount = frames.length;
    if (needsFit) fit();
  }, [enabled, frames, easing, portrait, fit]);

  return { fit };
}
