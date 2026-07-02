import { useEffect, useRef } from 'react';

import * as THREE from 'three';

import { uploadModelAssetCover } from '@/api';
import type { ModelAsset } from '@/types';

const MAX_CONCURRENT_COVERS = 2;
const COVER_WIDTH = 360;
const COVER_HEIGHT = 225;

async function renderPlaceholderCover(asset: ModelAsset): Promise<File> {
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

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(35, COVER_WIDTH / COVER_HEIGHT, 0.1, 100);
  camera.position.set(2.8, 2.1, 4);
  camera.lookAt(0, 0, 0);

  const light = new THREE.DirectionalLight(0xffffff, 2.2);
  light.position.set(2, 3, 4);
  scene.add(light);
  scene.add(new THREE.AmbientLight(0x6aa7ff, 1.15));

  const format = (asset.primary_format ?? asset.formats[0] ?? 'ply').toUpperCase();
  const geometry = new THREE.IcosahedronGeometry(1.15, 2);
  const material = new THREE.MeshStandardMaterial({
    color: new THREE.Color('#0a84ff'),
    roughness: 0.45,
    metalness: 0.18,
    transparent: true,
    opacity: 0.88,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.rotation.set(-0.35, 0.55, 0.15);
  scene.add(mesh);

  const wire = new THREE.LineSegments(
    new THREE.WireframeGeometry(geometry),
    new THREE.LineBasicMaterial({ color: 0xd7e7ff, transparent: true, opacity: 0.42 }),
  );
  wire.rotation.copy(mesh.rotation);
  scene.add(wire);

  renderer.render(scene, camera);

  const context = canvas.getContext('2d');
  if (context) {
    const gradient = context.createLinearGradient(0, 0, COVER_WIDTH, COVER_HEIGHT);
    gradient.addColorStop(0, 'rgba(8, 14, 24, 0.92)');
    gradient.addColorStop(1, 'rgba(0, 113, 227, 0.38)');
    context.globalCompositeOperation = 'destination-over';
    context.fillStyle = gradient;
    context.fillRect(0, 0, COVER_WIDTH, COVER_HEIGHT);
    context.globalCompositeOperation = 'source-over';
    context.fillStyle = 'rgba(255, 255, 255, 0.9)';
    context.font = '700 22px -apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif';
    context.fillText(format, 22, COVER_HEIGHT - 24);
  }

  geometry.dispose();
  material.dispose();
  wire.geometry.dispose();
  (wire.material as THREE.Material).dispose();
  renderer.dispose();

  const blob = await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((result) => {
      if (result) {
        resolve(result);
      } else {
        reject(new Error('Cover render failed'));
      }
    }, 'image/png', 0.88);
  });

  return new File([blob], `${asset.id}-cover.png`, { type: 'image/png' });
}

function shouldGenerateCover(asset: ModelAsset): boolean {
  return Boolean(
    asset.is_imported
    && asset.available
    && !asset.thumb_url
    && asset.thumbnail_state !== 'error',
  );
}

export function useModelAssetCoverQueue(
  assets: ModelAsset[],
  onCoverUpdated: (asset: ModelAsset) => void,
): void {
  const failedIdsRef = useRef(new Set<string>());
  const pendingIdsRef = useRef(new Set<string>());
  const activeCountRef = useRef(0);

  useEffect(() => {
    let cancelled = false;
    const queue = assets.filter((asset) =>
      shouldGenerateCover(asset)
      && !failedIdsRef.current.has(asset.id)
      && !pendingIdsRef.current.has(asset.id),
    );

    const runNext = () => {
      if (cancelled || activeCountRef.current >= MAX_CONCURRENT_COVERS) {
        return;
      }

      const next = queue.shift();
      if (!next) {
        return;
      }

      pendingIdsRef.current.add(next.id);
      activeCountRef.current += 1;
      void renderPlaceholderCover(next)
        .then((file) => uploadModelAssetCover(next.id, file, 'system'))
        .then((updated) => {
          if (!cancelled) {
            onCoverUpdated(updated);
          }
        })
        .catch(() => {
          failedIdsRef.current.add(next.id);
        })
        .finally(() => {
          pendingIdsRef.current.delete(next.id);
          activeCountRef.current -= 1;
          runNext();
        });

      runNext();
    };

    runNext();

    return () => {
      cancelled = true;
    };
  }, [assets, onCoverUpdated]);
}
