import * as THREE from 'three';
import { SparkRenderer, SplatMesh } from '@sparkjsdev/spark';

import { getSplatFileTypeFromFormat, type ViewerModelFormat } from '@/constants/spark';

const COVER_WIDTH = 360;
const COVER_HEIGHT = 225;
// 加载后额外渲染若干帧，给 Spark 的异步排序留出时间，避免抓到空/未排序画面。
const SORT_SETTLE_FRAMES = 10;
const COVER_ASPECT = COVER_WIDTH / COVER_HEIGHT;

let sharedRenderer: THREE.WebGLRenderer | null = null;

/**
 * 复用同一个离屏 WebGLRenderer（单个 WebGL 上下文），避免批量生成封面时
 * 每次都新建上下文触发浏览器上下文数量上限。
 */
function getSharedRenderer(): THREE.WebGLRenderer {
  if (sharedRenderer) {
    return sharedRenderer;
  }
  const canvas = document.createElement('canvas');
  canvas.width = COVER_WIDTH;
  canvas.height = COVER_HEIGHT;
  const renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: true,
    alpha: true,
    preserveDrawingBuffer: true,
  });
  renderer.setSize(COVER_WIDTH, COVER_HEIGHT, false);
  renderer.setPixelRatio(1);
  renderer.setClearColor(0x000000, 0);
  sharedRenderer = renderer;
  return renderer;
}

function nextFrame(): Promise<void> {
  return new Promise((resolve) => {
    window.requestAnimationFrame(() => resolve());
  });
}

function canvasToBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const finalize = (blob: Blob | null) => {
      if (blob) {
        resolve(blob);
      } else {
        reject(new Error('Cover encode failed'));
      }
    };
    // 优先 WebP（更小），浏览器不支持时回退 PNG。
    canvas.toBlob((webp) => {
      if (webp && webp.type === 'image/webp') {
        resolve(webp);
        return;
      }
      canvas.toBlob(finalize, 'image/png');
    }, 'image/webp', 0.85);
  });
}

interface SplatBoundsSource {
  getBoundingBox?: (applyRotation?: boolean) => THREE.Box3;
  packedSplats?: unknown;
  extSplats?: unknown;
  matrixWorld: THREE.Matrix4;
}

function frameCameraToMesh(camera: THREE.PerspectiveCamera, mesh: THREE.Object3D): void {
  const center = new THREE.Vector3(0, 0, 0);
  let radius = 1.6;

  const source = mesh as unknown as SplatBoundsSource;
  try {
    if (typeof source.getBoundingBox === 'function' && (source.packedSplats || source.extSplats)) {
      const box = source.getBoundingBox(true).clone();
      box.applyMatrix4(mesh.matrixWorld);
      if (!box.isEmpty()) {
        const sphere = box.getBoundingSphere(new THREE.Sphere());
        if (Number.isFinite(sphere.radius) && sphere.radius > 0) {
          radius = sphere.radius;
          center.copy(sphere.center);
        }
      }
    }
  } catch {
    // 包围盒不可用时使用默认取景距离。
  }

  const fov = (camera.fov * Math.PI) / 180;
  const distance = (radius / Math.sin(fov / 2)) * 1.35;
  const direction = new THREE.Vector3(0.72, 0.52, 1).normalize();
  camera.position.copy(center).addScaledVector(direction, distance);
  camera.near = Math.max(0.01, distance - radius * 2);
  camera.far = distance + radius * 4;
  camera.updateProjectionMatrix();
  camera.lookAt(center);
}

function disposeSparkRenderer(scene: THREE.Scene, sparkRenderer: SparkRenderer): void {
  scene.remove(sparkRenderer);
  const geometry = (sparkRenderer as unknown as { geometry?: { dispose?: () => void } }).geometry;
  geometry?.dispose?.();
}

/**
 * 在离屏画布中加载真实模型并渲染一张小尺寸封面。任何失败都会抛出，
 * 由调用方回退到占位封面。
 */
export async function renderModelCoverBlob(
  url: string,
  format: ViewerModelFormat,
): Promise<Blob> {
  const renderer = getSharedRenderer();
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, COVER_ASPECT, 0.01, 1000);
  const sparkRenderer = new SparkRenderer({ renderer });
  scene.add(sparkRenderer);
  scene.add(new THREE.AmbientLight(0xffffff, 1.1));

  let mesh: SplatMesh | null = null;
  try {
    mesh = new SplatMesh({ url, fileType: getSplatFileTypeFromFormat(format) });
    await mesh.initialized;
    // 与 viewer 一致地纠正模型上下颠倒。
    mesh.rotation.x = Math.PI;
    mesh.updateMatrixWorld(true);
    scene.add(mesh);
    frameCameraToMesh(camera, mesh);

    for (let frame = 0; frame < SORT_SETTLE_FRAMES; frame += 1) {
      sparkRenderer.sortDirty = true;
      renderer.render(scene, camera);
      await nextFrame();
    }
    renderer.render(scene, camera);

    return await canvasToBlob(renderer.domElement);
  } finally {
    if (mesh) {
      scene.remove(mesh);
      mesh.dispose();
    }
    disposeSparkRenderer(scene, sparkRenderer);
  }
}

/**
 * 稳定占位封面：使用 2D canvas 绘制格式感知的渐变卡片，
 * 不依赖 WebGL，作为真实渲染失败时的最后兜底。
 */
export async function renderPlaceholderCoverBlob(format: string): Promise<Blob> {
  const canvas = document.createElement('canvas');
  canvas.width = COVER_WIDTH;
  canvas.height = COVER_HEIGHT;
  const context = canvas.getContext('2d');
  if (!context) {
    throw new Error('2D canvas unavailable for placeholder cover');
  }

  const gradient = context.createLinearGradient(0, 0, COVER_WIDTH, COVER_HEIGHT);
  gradient.addColorStop(0, '#0b1220');
  gradient.addColorStop(1, '#0a4a9f');
  context.fillStyle = gradient;
  context.fillRect(0, 0, COVER_WIDTH, COVER_HEIGHT);

  context.strokeStyle = 'rgba(215, 231, 255, 0.28)';
  context.lineWidth = 2;
  for (let ring = 0; ring < 3; ring += 1) {
    context.beginPath();
    context.arc(COVER_WIDTH / 2, COVER_HEIGHT / 2 - 12, 46 + ring * 26, 0, Math.PI * 2);
    context.stroke();
  }

  context.fillStyle = 'rgba(255, 255, 255, 0.92)';
  context.font = '700 30px -apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif';
  context.textBaseline = 'alphabetic';
  context.fillText(format.toUpperCase(), 22, COVER_HEIGHT - 24);

  return canvasToBlob(canvas);
}

function blobExtension(blob: Blob): string {
  return blob.type === 'image/webp' ? 'webp' : 'png';
}

/**
 * 生成一个资产的系统封面文件：优先渲染真实模型，失败时回退占位。
 */
export async function generateModelCoverFile(
  assetId: string,
  url: string | null,
  format: ViewerModelFormat,
): Promise<File> {
  if (url) {
    try {
      const blob = await renderModelCoverBlob(url, format);
      return new File([blob], `${assetId}-cover.${blobExtension(blob)}`, { type: blob.type });
    } catch {
      // 渲染失败时继续走占位兜底。
    }
  }

  const fallbackFormat = format ?? 'ply';
  const placeholder = await renderPlaceholderCoverBlob(fallbackFormat);
  return new File([placeholder], `${assetId}-cover.${blobExtension(placeholder)}`, {
    type: placeholder.type,
  });
}
