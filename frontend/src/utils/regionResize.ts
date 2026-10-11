import * as THREE from 'three';

import type { EditorRegion, EditorTool } from '@/types/modelEditor';

const MIN_SIZE = 0.00001;
const AXES = [new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 1, 0), new THREE.Vector3(0, 0, 1)];
// Generous invisible grab area around the screen-space arrow.
const HANDLE_WIDTH = 40;
const HANDLE_HEIGHT = 28;
const HANDLE_RADIUS = 9;
const HANDLE_HIT_PADDING = 8;

/** Move one box face, keeping the opposite face fixed, including at the minimum size. */
export function resizeBoxFace(region: EditorRegion, axis: number, sign: number, delta: number): EditorRegion {
  const next = structuredClone(region);
  const change = Math.max(MIN_SIZE - region.size[axis], delta);
  next.size[axis] += change;
  next.center[axis] += sign * change / 2;
  return next;
}

/** Project a world direction to CSS pixels per world unit at the grabbed boundary. */
export function projectResizeDirection(
  camera: THREE.PerspectiveCamera, point: THREE.Vector3, direction: THREE.Vector3,
  width: number, height: number,
): THREE.Vector2 | null {
  const p = point.clone().applyMatrix4(camera.matrixWorldInverse);
  if (p.z >= -camera.near) return null;
  const d = direction.clone().transformDirection(camera.matrixWorldInverse);
  // Depth-facing handles overlap the center gizmo and make edge drags ambiguous.
  // Resize that axis from a side/top view rather than through perspective shrinkage.
  if (Math.hypot(d.x, d.y) < 0.15) return null;
  const m = camera.projectionMatrix.elements;
  const axis = new THREE.Vector2(
    width * m[0] * (-d.x * p.z + p.x * d.z) / (2 * p.z * p.z),
    -height * m[5] * (-d.y * p.z + p.y * d.z) / (2 * p.z * p.z),
  );
  // A face aimed straight at the camera cannot be resized reliably from this view.
  return axis.lengthSq() > 1e-8 ? axis : null;
}

interface ResizeOptions {
  canvas: HTMLCanvasElement;
  camera: THREE.PerspectiveCamera;
  getRegion: () => EditorRegion;
  getTool: () => EditorTool;
  enabled: () => boolean;
  begin: () => void;
  change: (region: EditorRegion) => void;
  finish: () => void;
}

interface Boundary {
  point: THREE.Vector3;
  direction: THREE.Vector3;
  axis: number;
  sign: number;
}

export function createRegionResizeControls(options: ResizeOptions) {
  const { camera, canvas } = options;
  const group = new THREE.Group();
  const arrowShape = new THREE.Shape();
  arrowShape.moveTo(-12, 0);
  [
    [-5.7, 6.3], [-4.3, 4.9], [-8.2, 1], [8.2, 1], [4.3, 4.9], [5.7, 6.3],
    [12, 0], [5.7, -6.3], [4.3, -4.9], [8.2, -1], [-8.2, -1], [-4.3, -4.9], [-5.7, -6.3],
  ].forEach(([x, y]) => arrowShape.lineTo(x, y));
  arrowShape.closePath();
  const arrowGeometry = new THREE.ShapeGeometry(arrowShape);
  // A 30 px glyph stays discoverable without a button surface around it.
  arrowGeometry.scale(1.25, 1.25, 1);
  const handles = Array.from({ length: 6 }, () => {
    // Transparent rendering keeps the controls above the Gaussian pass.
    const arrow = new THREE.Mesh(arrowGeometry, new THREE.MeshBasicMaterial({
      color: 0x94c7ff, transparent: true, depthTest: false, depthWrite: false,
    }));
    arrow.renderOrder = 1002;
    arrow.frustumCulled = false;
    group.add(arrow);
    return arrow;
  });
  const circlePoints = Array.from({ length: 96 }, (_, i) => {
    const angle = i * Math.PI / 48;
    return new THREE.Vector3(Math.cos(angle), Math.sin(angle), 0);
  });
  const circle = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(circlePoints),
    new THREE.LineBasicMaterial({ color: 0x64abff, depthTest: false, depthWrite: false, transparent: true, opacity: 0.75 }));
  circle.renderOrder = 1001;
  circle.frustumCulled = false;
  group.add(circle);
  let boundaries: Boundary[] = [];
  let drag: { pointerId: number; x: number; y: number; boundary: Boundary; screen: THREE.Vector2; region: EditorRegion } | null = null;
  let hovered = -1;
  const originalCursor = canvas.style.cursor;
  const project = (point: THREE.Vector3, rect: DOMRect) => {
    const p = point.clone().project(camera);
    return { x: rect.left + (p.x + 1) * rect.width / 2, y: rect.top + (1 - p.y) * rect.height / 2, z: p.z };
  };
  const update = () => {
    const tool = options.getTool(), region = options.getRegion();
    group.visible = (tool === 'sphere' || tool === 'box') && options.enabled();
    if (!group.visible) return;
    camera.updateMatrixWorld(true);
    const center = new THREE.Vector3().fromArray(region.center);
    const rect = canvas.getBoundingClientRect();
    circle.visible = tool === 'sphere';
    circle.position.copy(center);
    circle.quaternion.copy(camera.quaternion);
    circle.scale.setScalar(region.radius);
    const ringActive = tool === 'sphere' && (hovered !== -1 || !!drag);
    circle.material.color.setHex(ringActive ? 0xb4d9ff : 0x64abff);
    circle.material.opacity = ringActive ? 1 : 0.75;
    boundaries = Array.from({ length: tool === 'sphere' ? 4 : 6 }, (_, i) => {
      const axis = Math.floor(i / 2), sign = i % 2 === 0 ? 1 : -1;
      const direction = AXES[axis].clone().multiplyScalar(sign);
      if (tool === 'sphere') direction.applyQuaternion(camera.quaternion);
      const point = center.clone().addScaledVector(direction, tool === 'sphere' ? region.radius : region.size[axis] / 2);
      return { point, direction, axis, sign };
    });
    handles.forEach((handle, i) => {
      const boundary = boundaries[i];
      handle.visible = !!boundary;
      if (!boundary) return;
      const screen = projectResizeDirection(camera, boundary.point, boundary.direction, rect.width, rect.height);
      handle.visible = !!screen;
      if (!screen) return;
      handle.position.copy(boundary.point);
      // Billboard the arrow, then align it with the projected face normal/radius.
      const rotation = new THREE.Quaternion().setFromAxisAngle(AXES[2], Math.atan2(-screen.y, screen.x));
      handle.quaternion.copy(camera.quaternion).multiply(rotation);
      const depth = -boundary.point.clone().applyMatrix4(camera.matrixWorldInverse).z;
      const unitPerPixel = 2 * depth * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2))
        / (Math.max(rect.height, 1) * camera.zoom);
      handle.scale.setScalar(Math.max(0.000001, unitPerPixel));
      const active = i === hovered;
      handle.material.color.setHex(active ? 0xffffff : 0x94c7ff);
    });
    group.updateMatrixWorld(true);
  };
  const pick = (event: PointerEvent): Boundary | null => {
    if (!group.visible) return null;
    const rect = canvas.getBoundingClientRect();
    let closest: Boundary | null = null, distance = Infinity, depth = Infinity;
    hovered = -1;
    boundaries.forEach((boundary, i) => {
      if (!handles[i].visible) return;
      const p = project(boundary.point, rect);
      if (p.z < -1 || p.z > 1) return;
      const screen = projectResizeDirection(camera, boundary.point, boundary.direction, rect.width, rect.height);
      if (!screen) return;
      screen.normalize();
      const dx = event.clientX - p.x, dy = event.clientY - p.y;
      // Keep a forgiving invisible target around the rotated glyph.
      const along = Math.abs(dx * screen.x + dy * screen.y);
      const across = Math.abs(-dx * screen.y + dy * screen.x);
      const cornerX = Math.max(0, along - (HANDLE_WIDTH / 2 - HANDLE_RADIUS));
      const cornerY = Math.max(0, across - (HANDLE_HEIGHT / 2 - HANDLE_RADIUS));
      if (Math.hypot(cornerX, cornerY) > HANDLE_RADIUS + HANDLE_HIT_PADDING) return;
      const d = Math.hypot(dx, dy);
      if (d < distance || (Math.abs(d - distance) < 0.5 && p.z < depth)) {
        closest = boundary; distance = d; depth = p.z; hovered = i;
      }
    });
    if (closest) return closest;
    if (options.getTool() === 'box') {
      const region = options.getRegion();
      const center = new THREE.Vector3().fromArray(region.center);
      const pc = project(center, rect);
      // Grab an outline edge as well as a face arrow. Highlight its arrow so the
      // axis to be resized is visible before pressing the mouse.
      let edgeDistance = 7;
      for (let edgeAxis = 0; edgeAxis < 3; edgeAxis++) {
        const faceAxes = [0, 1, 2].filter((axis) => axis !== edgeAxis);
        for (const firstSign of [-1, 1]) for (const secondSign of [-1, 1]) {
          const a = center.clone();
          a.setComponent(edgeAxis, a.getComponent(edgeAxis) - region.size[edgeAxis] / 2);
          a.setComponent(faceAxes[0], a.getComponent(faceAxes[0]) + firstSign * region.size[faceAxes[0]] / 2);
          a.setComponent(faceAxes[1], a.getComponent(faceAxes[1]) + secondSign * region.size[faceAxes[1]] / 2);
          const b = a.clone().addScaledVector(AXES[edgeAxis], region.size[edgeAxis]);
          const pa = project(a, rect), pb = project(b, rect);
          if (pa.z < -1 || pa.z > 1 || pb.z < -1 || pb.z > 1) continue;
          const dx = pb.x - pa.x, dy = pb.y - pa.y;
          const t = THREE.MathUtils.clamp(((event.clientX - pa.x) * dx + (event.clientY - pa.y) * dy) / Math.max(dx * dx + dy * dy, 1e-12), 0, 1);
          const d = Math.hypot(event.clientX - pa.x - t * dx, event.clientY - pa.y - t * dy);
          if (d >= edgeDistance) continue;
          const point = a.lerp(b, t);
          const outward = new THREE.Vector2(event.clientX - pc.x, event.clientY - pc.y).normalize();
          let score = -Infinity;
          for (let i = 0; i < 2; i++) {
            const axis = faceAxes[i], sign = i === 0 ? firstSign : secondSign;
            const direction = AXES[axis].clone().multiplyScalar(sign);
            const screen = projectResizeDirection(camera, point, direction, rect.width, rect.height);
            if (!screen) continue;
            const candidate = screen.normalize().dot(outward);
            if (candidate <= score) continue;
            score = candidate;
            closest = { point, direction, axis, sign };
            hovered = axis * 2 + (sign > 0 ? 0 : 1);
          }
          if (score > -Infinity) edgeDistance = d;
        }
      }
      return closest;
    }
    // The camera-facing circumference is draggable anywhere, not just at its arrows.
    let nearest: THREE.Vector3 | null = null;
    for (let i = 0; i < circlePoints.length; i++) {
      const a = circlePoints[i].clone().applyMatrix4(circle.matrixWorld);
      const b = circlePoints[(i + 1) % circlePoints.length].clone().applyMatrix4(circle.matrixWorld);
      const pa = project(a, rect), pb = project(b, rect);
      if (pa.z < -1 || pa.z > 1 || pb.z < -1 || pb.z > 1) continue;
      const dx = pb.x - pa.x, dy = pb.y - pa.y;
      const t = THREE.MathUtils.clamp(((event.clientX - pa.x) * dx + (event.clientY - pa.y) * dy) / Math.max(dx * dx + dy * dy, 1e-12), 0, 1);
      const d = Math.hypot(event.clientX - pa.x - t * dx, event.clientY - pa.y - t * dy);
      if (d < Math.min(distance, 7)) { nearest = a.lerp(b, t); distance = d; }
    }
    if (!nearest) return null;
    hovered = -2;
    return { point: nearest, direction: nearest.clone().sub(new THREE.Vector3().fromArray(options.getRegion().center)).normalize(), axis: 0, sign: 1 };
  };
  const down = (event: PointerEvent) => {
    if (event.button !== 0 || drag || !options.enabled()) return;
    update();
    const boundary = pick(event);
    if (!boundary) return;
    const rect = canvas.getBoundingClientRect();
    const screen = projectResizeDirection(camera, boundary.point, boundary.direction, rect.width, rect.height);
    if (!screen) return;
    event.preventDefault(); event.stopImmediatePropagation();
    options.begin();
    drag = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, boundary, screen, region: structuredClone(options.getRegion()) };
    canvas.setPointerCapture(event.pointerId);
    canvas.style.cursor = 'grabbing';
    update();
  };
  const move = (event: PointerEvent) => {
    if (!drag) {
      if (!options.enabled() || event.buttons) return;
      update();
      const boundary = pick(event);
      canvas.style.cursor = boundary ? 'grab' : originalCursor;
      update();
      return;
    }
    if (event.pointerId !== drag.pointerId) return;
    event.preventDefault(); event.stopImmediatePropagation();
    const delta = ((event.clientX - drag.x) * drag.screen.x + (event.clientY - drag.y) * drag.screen.y)
      / drag.screen.lengthSq() * (event.shiftKey ? 0.1 : 1);
    drag.x = event.clientX; drag.y = event.clientY;
    drag.region = options.getTool() === 'sphere'
      ? { ...drag.region, radius: Math.max(MIN_SIZE, drag.region.radius + delta) }
      : resizeBoxFace(drag.region, drag.boundary.axis, drag.boundary.sign, delta);
    options.change(drag.region);
    update();
  };
  const finish = (event?: PointerEvent) => {
    if (!drag || (event && event.pointerId !== drag.pointerId)) return;
    event?.preventDefault(); event?.stopImmediatePropagation();
    const pointerId = drag.pointerId;
    drag = null;
    hovered = -1;
    if (canvas.hasPointerCapture(pointerId)) canvas.releasePointerCapture(pointerId);
    canvas.style.cursor = originalCursor;
    options.finish();
    update();
  };
  const leave = () => { if (!drag) { hovered = -1; canvas.style.cursor = originalCursor; update(); } };
  const blur = () => finish();
  canvas.addEventListener('pointerdown', down, true);
  canvas.addEventListener('pointermove', move, true);
  canvas.addEventListener('pointerup', finish, true);
  canvas.addEventListener('pointercancel', finish, true);
  canvas.addEventListener('lostpointercapture', finish, true);
  canvas.addEventListener('pointerleave', leave);
  window.addEventListener('blur', blur);
  return {
    group, update,
    cancel: () => finish(),
    dispose: () => {
      finish();
      canvas.removeEventListener('pointerdown', down, true);
      canvas.removeEventListener('pointermove', move, true);
      canvas.removeEventListener('pointerup', finish, true);
      canvas.removeEventListener('pointercancel', finish, true);
      canvas.removeEventListener('lostpointercapture', finish, true);
      canvas.removeEventListener('pointerleave', leave);
      window.removeEventListener('blur', blur);
      arrowGeometry.dispose();
      handles.forEach((handle) => handle.material.dispose());
      circle.geometry.dispose(); circle.material.dispose();
      canvas.style.cursor = originalCursor;
    },
  };
}
