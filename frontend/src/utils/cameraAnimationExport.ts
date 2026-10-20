import * as THREE from 'three';
import type { ViewerContext } from '@/hooks/useViewer';
import { applyCameraPose, captureCameraPose, animationDuration, animationFrameCount, animationFrameTime, sampleCameraAnimation } from '@/utils/cameraAnimation';
import type { CameraAnimationProject } from '@/utils/cameraAnimation';
import { encodeAnimationVideo } from '@/utils/webmVideo';

/** Own the renderer only until the finally block; never write model data. */
export async function exportCameraAnimation(
  ctx: ViewerContext, project: CameraAnimationProject,
  width: number, height: number, fps: number, signal: AbortSignal,
  onProgress: (progress: number) => void,
): Promise<Blob> {
  const mesh = ctx.splatMesh;
  if (!mesh || mesh.paged || !mesh.packedSplats) throw new Error('animationFullModelRequired');
  const { renderer, camera, controls, sparkRenderer: spark, scene } = ctx;
  const duration = animationDuration(project.frames);
  const frames = animationFrameCount(duration, fps);
  const saved = {
    size: renderer.getSize(new THREE.Vector2()), pixelRatio: renderer.getPixelRatio(),
    pose: captureCameraPose(camera, controls.target), aspect: camera.aspect, up: camera.up.clone(),
    background: scene.background, autoUpdate: spark.autoUpdate, minSort: spark.minSortIntervalMs,
    sparkLod: spark.enableLod, meshLod: mesh.enableLod, enabled: controls.enabled,
    damping: controls.enableDamping, autoRotate: controls.autoRotate,
  };
  ctx.animationExporting = true;
  controls.enabled = false; controls.autoRotate = false; controls.enableDamping = false;
  spark.autoUpdate = false;
  try {
    // Allow any sort initiated by the ordinary render loop to complete first.
    const deadline = performance.now() + 30000;
    while (spark.sorting) {
      signal.throwIfAborted();
      if (performance.now() > deadline) throw new Error('animationEncodeFailed');
      await new Promise<void>(resolve => setTimeout(resolve, 8));
    }
    signal.throwIfAborted();
    spark.minSortIntervalMs = 0; spark.enableLod = false; mesh.enableLod = false;
    mesh.updateVersion();
    renderer.setPixelRatio(1); renderer.setSize(width, height, false);
    camera.aspect = width / height;
    scene.background = new THREE.Color(0x000000);
    return await encodeAnimationVideo({
      width, height, fps, frames, signal, onProgress,
      render: async index => {
        signal.throwIfAborted();
        const pose = sampleCameraAnimation(project.frames, animationFrameTime(index, frames, duration), project.easing)!;
        applyCameraPose(camera, controls.target, pose);
        // onBeforeRender sets Spark's exact render size; explicit update awaits its sort.
        renderer.render(scene, camera);
        await spark.update({ scene, camera });
        signal.throwIfAborted();
        renderer.render(scene, camera);
        return renderer.domElement;
      },
    });
  } finally {
    spark.autoUpdate = saved.autoUpdate; spark.minSortIntervalMs = saved.minSort;
    spark.enableLod = saved.sparkLod; mesh.enableLod = saved.meshLod; mesh.updateVersion();
    scene.background = saved.background;
    if (!ctx.disposed) { renderer.setPixelRatio(saved.pixelRatio); renderer.setSize(saved.size.x, saved.size.y, false); }
    camera.aspect = saved.aspect; applyCameraPose(camera, controls.target, saved.pose); camera.up.copy(saved.up);
    controls.enabled = saved.enabled; controls.enableDamping = saved.damping; controls.autoRotate = saved.autoRotate;
    ctx.animationExporting = false;
  }
}
