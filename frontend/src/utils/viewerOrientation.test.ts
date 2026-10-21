import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import * as THREE from 'three';

import { canEditModelAsset, resolveModelAssetSource } from './modelAssets.js';
import { getShareBoundsView } from './shareFraming.js';
import { getNextModelReloadToken } from './modelPreviewState.js';
import { resolveViewerOrientation } from './viewerOrientation.js';
import { detectImportedModelOrientation, hasMlSharpPlyHeader } from './importedModelPreview.js';
import {
  composeViewerModelQuaternion,
  getReconstructionCameraView,
  getViewerModelLoadKey,
  isViewerLoadCurrent,
} from './viewerRuntime.js';

import type {
  CurrentModelDescriptor,
  ViewerCameraHint,
  ViewerOrientationInput,
} from '../types/modelPreview.js';
import type { ModelAsset } from '../types/modelAsset.js';

const cameraHint: ViewerCameraHint = {
  position: [1, 2, 3], target: [1, 2, 6], up: [0, 1, 0],
  fov_y_degrees: 50, aspect: 16 / 9,
};

describe('bounded external model detection', () => {
  const sharpHeader = [
    'ply', 'format binary_little_endian 1.0', 'element vertex 9',
    ...['x', 'y', 'z', 'f_dc_0', 'f_dc_1', 'f_dc_2', 'opacity', 'scale_0', 'scale_1',
      'scale_2', 'rot_0', 'rot_1', 'rot_2', 'rot_3'].map((name) => `property float ${name}`),
    'element extrinsic 16', 'property float extrinsic',
    'element intrinsic 9', 'property float intrinsic',
    'element image_size 2', 'property uint image_size',
    'element frame 2', 'property int frame',
    'element disparity 2', 'property float disparity',
    'element color_space 1', 'property uchar color_space',
    'element version 3', 'property uchar version', 'end_header', '',
  ].join('\n');

  it('recognizes complete ml-sharp PLY structure in temporary previews', async () => {
    assert.equal(hasMlSharpPlyHeader(sharpHeader), true);
    assert.equal(hasMlSharpPlyHeader(sharpHeader.replaceAll('\n', '\r\n')), true);
    assert.equal(await detectImportedModelOrientation(new Blob([sharpHeader]), 'ply'), 'default');
  });

  it('does not guess from incomplete schemas, filenames or compressed formats', async () => {
    for (const header of [sharpHeader.replace('element intrinsic 9', 'element camera 9'),
      sharpHeader.replace('element extrinsic 16', 'element extrinsic 12'),
      sharpHeader.replace('property uint image_size', 'property float image_size'),
      sharpHeader.replace('element vertex 9', 'element vertex NaN'),
      sharpHeader.replace('end_header', ''), 'ply\ncomment ml-sharp\nend_header\n']) {
      assert.equal(hasMlSharpPlyHeader(header), false);
      assert.equal(await detectImportedModelOrientation(new Blob([header]), 'ply'), 'y-front');
    }
    assert.equal(await detectImportedModelOrientation(new Blob([sharpHeader]), 'spz'), 'y-front');
  });
});

it('edit capability comes from the verified file structure, not format or media labels', () => {
  const asset: ModelAsset = {
    id: 'source', name: 'source', source_type: 'video', primary_format: 'ply',
    formats: ['ply', 'spz'], size: 100, available: true, tags: [],
  };
  assert.equal(canEditModelAsset(asset), false);
  assert.equal(canEditModelAsset({ ...asset, editor_supported: false }), false);
  assert.equal(canEditModelAsset({ ...asset, source_type: 'generated', source_media_type: 'image', editor_supported: true }), true);
  assert.equal(canEditModelAsset({ ...asset, editor_supported: true, available: false }), false);
});

describe('reconstruction camera framing', () => {
  it('transforms the source camera with the model, preserving input data', () => {
    const original = structuredClone(cameraHint);
    const matrix = new THREE.Matrix4().compose(
      new THREE.Vector3(4, 5, 6),
      new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI / 2),
      new THREE.Vector3(2, 2, 2),
    );
    const view = getReconstructionCameraView(cameraHint, matrix, 16 / 9);
    assert.ok(view);
    assert.ok(view.position.distanceTo(new THREE.Vector3(6, -1, 10)) < 1e-9);
    assert.ok(view.target.distanceTo(new THREE.Vector3(6, -7, 10)) < 1e-9);
    assert.ok(view.up.distanceTo(new THREE.Vector3(0, 0, 1)) < 1e-9);
    assert.ok(Math.abs(view.fov - 50) < 1e-9);
    assert.deepEqual(cameraHint, original);
  });

  it('keeps horizontal coverage in a portrait panel and falls back for invalid hints', () => {
    const matrix = new THREE.Matrix4();
    const view = getReconstructionCameraView(cameraHint, matrix, 0.8);
    assert.ok(view && view.fov > 50);
    assert.equal(getReconstructionCameraView(null, matrix, 1), null);
    assert.equal(getReconstructionCameraView({ ...cameraHint, target: cameraHint.position }, matrix, 1), null);
    assert.equal(getReconstructionCameraView({ ...cameraHint, up: [0, 0, 1] }, matrix, 1), null);
    assert.equal(getReconstructionCameraView({ ...cameraHint, aspect: NaN }, matrix, 1), null);
    assert.equal(getReconstructionCameraView(cameraHint, matrix, 0), null);
  });
});

describe('resolveViewerOrientation', () => {
  it('gives actionable explicit hints precedence over conflicting source metadata', () => {
    assert.deepEqual(
      resolveViewerOrientation({
        viewerOrientation: 'default',
        sourceMediaType: 'video',
      }),
      {
        mode: 'default',
        reason: 'explicit-default',
      },
    );
    assert.deepEqual(
      resolveViewerOrientation({
        viewerOrientation: 'y-front',
        sourceMediaType: 'image',
      }),
      {
        mode: 'y-front',
        reason: 'explicit-y-front',
      },
    );
  });

  it('uses trusted image and video source metadata when the hint is unknown or missing', () => {
    assert.deepEqual(
      resolveViewerOrientation({
        viewerOrientation: 'unknown',
        sourceMediaType: 'image',
      }),
      {
        mode: 'default',
        reason: 'source-image',
      },
    );
    assert.deepEqual(
      resolveViewerOrientation({
        sourceMediaType: 'video',
      }),
      {
        mode: 'y-front',
        reason: 'source-video',
      },
    );
  });

  it('uses verified legacy-video evidence only after explicit and source metadata', () => {
    assert.deepEqual(
      resolveViewerOrientation({
        viewerOrientation: 'unknown',
        sourceMediaType: null,
        legacyVideo: true,
      }),
      {
        mode: 'y-front',
        reason: 'legacy-video',
      },
    );
  });

  it('keeps generated models on their existing fallback when context is missing', () => {
    assert.deepEqual(
      resolveViewerOrientation({
        viewerOrientation: 'sideways',
        sourceMediaType: 'mesh',
      }),
      {
        mode: 'default',
        reason: 'unknown-fallback',
      },
    );
    assert.deepEqual(resolveViewerOrientation({}), {
      mode: 'default',
      reason: 'unknown-fallback',
    });
  });

  it('uses the video branch only for unknown external sources, after saved or trusted hints', () => {
    for (const source of ['temporary', 'model-asset-imported'] as const) {
      assert.deepEqual(resolveViewerOrientation({ source, viewerOrientation: 'unknown' }), {
        mode: 'y-front', reason: 'external-fallback',
      });
      assert.equal(resolveViewerOrientation({ source, viewerOrientation: 'default' }).mode, 'default');
      assert.equal(resolveViewerOrientation({ source, sourceMediaType: 'image' }).mode, 'default');
    }
    assert.equal(resolveViewerOrientation({ source: 'model-asset-generated' }).mode, 'default');
  });

  it('does not use flat image bounds as an orientation signal', () => {
    const flatImageContext: ViewerOrientationInput & {
      bounds: { x: number; y: number; z: number };
    } = {
      viewerOrientation: null,
      sourceMediaType: 'image',
      bounds: {
        x: 9.29,
        y: 6.70,
        z: 4.86,
      },
    };

    assert.deepEqual(resolveViewerOrientation(flatImageContext), {
      mode: 'default',
      reason: 'source-image',
    });
  });

  it('keeps stable asset identity and orientation across companion formats', () => {
    const asset: ModelAsset = {
      id: 'asset-stable-id',
      name: 'example',
      source_type: 'video',
      primary_format: 'spz',
      formats: ['ply', 'spz'],
      files: [
        {
          format: 'ply',
          filename: 'example.ply',
          size: 1024,
          url: '/files/outputs/example.ply',
          source_media_type: 'video',
          viewer_orientation: 'y-front',
        },
        {
          format: 'spz',
          filename: 'example.spz',
          size: 512,
          url: '/files/outputs/example.spz',
          source_media_type: 'video',
          viewer_orientation: 'y-front',
        },
      ],
      size: 1536,
      available: true,
      tags: [],
      source_media_type: 'video',
      viewer_orientation: 'y-front',
      viewer_camera: cameraHint,
    };
    const plySource = resolveModelAssetSource(asset, 'ply');
    const spzSource = resolveModelAssetSource(asset, 'spz');
    assert.deepEqual(plySource.viewerCamera, cameraHint);
    assert.deepEqual(spzSource.viewerCamera, cameraHint);

    const plyDescriptor: CurrentModelDescriptor = {
      id: asset.id,
      url: plySource.url ?? '',
      format: plySource.format,
      size: plySource.size,
      source: 'model-asset-generated',
      sourceMediaType: plySource.sourceMediaType,
      viewerOrientation: plySource.viewerOrientation,
    };
    const spzDescriptor: CurrentModelDescriptor = {
      id: asset.id,
      url: spzSource.url ?? '',
      format: spzSource.format,
      size: spzSource.size,
      source: 'model-asset-generated',
      sourceMediaType: spzSource.sourceMediaType,
      viewerOrientation: spzSource.viewerOrientation,
    };

    assert.equal(plyDescriptor.id, spzDescriptor.id);
    assert.deepEqual(
      resolveViewerOrientation(plyDescriptor),
      resolveViewerOrientation(spzDescriptor),
    );
  });
});

describe('viewer runtime isolation', () => {
  it('composes source correction before the saved user rotation without mutating it', () => {
    const savedUserRotation = {
      rotationX: Math.PI / 3,
      rotationY: -Math.PI / 5,
      rotationZ: Math.PI / 7,
    };
    const userQuaternion = new THREE.Quaternion().setFromEuler(new THREE.Euler(
      savedUserRotation.rotationX,
      savedUserRotation.rotationY,
      savedUserRotation.rotationZ,
    ));
    const sourceCorrection = new THREE.Quaternion().setFromAxisAngle(
      new THREE.Vector3(1, 0, 0),
      Math.PI / 2,
    );
    const expected = sourceCorrection.clone().multiply(userQuaternion);

    const actual = composeViewerModelQuaternion(savedUserRotation, 'y-front');

    assert.ok(actual.angleTo(expected) < 1e-10);
    assert.deepEqual(savedUserRotation, {
      rotationX: Math.PI / 3,
      rotationY: -Math.PI / 5,
      rotationZ: Math.PI / 7,
    });
  });

  it('repeatedly derives the same source-corrected orientation without accumulation', () => {
    const userRotation = {
      rotationX: Math.PI,
      rotationY: 0,
      rotationZ: 0,
    };

    const firstReset = composeViewerModelQuaternion(userRotation, 'y-front');
    const repeatedReset = composeViewerModelQuaternion(userRotation, 'y-front');
    const defaultOrientation = composeViewerModelQuaternion(userRotation, 'default');

    assert.ok(firstReset.angleTo(repeatedReset) < 1e-10);
    assert.ok(firstReset.angleTo(defaultOrientation) > 1);
  });

  it('rejects cancelled, superseded, and previous-context load commits', () => {
    const imageContext = {};
    const videoContext = {};
    const currentLoad = {
      cancelled: false,
      generation: 4,
      activeGeneration: 4,
      context: imageContext,
      activeContext: imageContext,
    };

    assert.equal(isViewerLoadCurrent(currentLoad), true);
    assert.equal(isViewerLoadCurrent({ ...currentLoad, cancelled: true }), false);
    assert.equal(isViewerLoadCurrent({ ...currentLoad, activeGeneration: 5 }), false);
    assert.equal(isViewerLoadCurrent({
      ...currentLoad,
      activeContext: videoContext,
    }), false);
    assert.equal(isViewerLoadCurrent({
      ...currentLoad,
      generation: 6,
      activeGeneration: 6,
      context: imageContext,
      activeContext: videoContext,
    }), false);
  });

  it('uses the complete descriptor for switch and companion-format load identity', () => {
    const baseDescriptor: CurrentModelDescriptor = {
      id: 'stable-asset',
      url: '/files/outputs/model.ply',
      format: 'ply',
      size: 1024,
      source: 'model-asset-generated',
      sourceMediaType: 'video',
      viewerOrientation: 'y-front',
    };
    const sameDescriptor = { ...baseDescriptor };
    const companionFormat: CurrentModelDescriptor = {
      ...baseDescriptor,
      url: '/files/outputs/model.spz',
      format: 'spz',
      size: 512,
    };
    const switchedModel: CurrentModelDescriptor = {
      ...baseDescriptor,
      id: 'another-asset',
      sourceMediaType: 'image',
      viewerOrientation: 'default',
    };

    assert.equal(
      getViewerModelLoadKey(baseDescriptor),
      getViewerModelLoadKey(sameDescriptor),
    );
    assert.notEqual(
      getViewerModelLoadKey(baseDescriptor),
      getViewerModelLoadKey(companionFormat),
    );
    assert.notEqual(
      getViewerModelLoadKey(baseDescriptor),
      getViewerModelLoadKey(switchedModel),
    );
    assert.equal(getViewerModelLoadKey(null), null);
    assert.notEqual(getViewerModelLoadKey(baseDescriptor), getViewerModelLoadKey({
      ...baseDescriptor, viewerCamera: cameraHint,
    }));
  });

  it('keeps a saved override stable through image to video to image switching', () => {
    const savedUserRotation = {
      rotationX: Math.PI,
      rotationY: Math.PI / 9,
      rotationZ: 0,
    };
    const imageOrientation = resolveViewerOrientation({
      viewerOrientation: 'default',
      sourceMediaType: 'image',
    });
    const videoOrientation = resolveViewerOrientation({
      viewerOrientation: 'y-front',
      sourceMediaType: 'video',
    });

    const firstImage = composeViewerModelQuaternion(
      savedUserRotation,
      imageOrientation.mode,
    );
    const video = composeViewerModelQuaternion(
      savedUserRotation,
      videoOrientation.mode,
    );
    const reopenedImage = composeViewerModelQuaternion(
      savedUserRotation,
      imageOrientation.mode,
    );

    assert.equal(firstImage.equals(reopenedImage), true);
    assert.ok(firstImage.angleTo(video) > 1);
    assert.deepEqual(savedUserRotation, {
      rotationX: Math.PI,
      rotationY: Math.PI / 9,
      rotationZ: 0,
    });
  });

  it('supersedes a same-descriptor reload without changing stable model identity', () => {
    const descriptor: CurrentModelDescriptor = {
      id: 'stable-asset',
      url: '/files/outputs/model.spz',
      format: 'spz',
      size: 512,
      source: 'model-asset-generated',
      sourceMediaType: 'video',
      viewerOrientation: 'y-front',
    };
    const context = {};
    const firstGeneration = 7;
    const reloadGeneration = getNextModelReloadToken(firstGeneration, true);

    assert.equal(getViewerModelLoadKey(descriptor), getViewerModelLoadKey({
      ...descriptor,
    }));
    assert.equal(reloadGeneration, 8);
    assert.equal(getNextModelReloadToken(reloadGeneration, false), reloadGeneration);
    assert.equal(isViewerLoadCurrent({
      cancelled: false,
      generation: firstGeneration,
      activeGeneration: reloadGeneration,
      context,
      activeContext: context,
    }), false);
    assert.equal(isViewerLoadCurrent({
      cancelled: false,
      generation: reloadGeneration,
      activeGeneration: reloadGeneration,
      context,
      activeContext: context,
    }), true);
  });
});


describe('standalone sharing full-model framing', () => {
  for (const aspect of [0.4, 1, 16 / 9, 4]) {
    for (const direction of [new THREE.Vector3(0, 0, 1), new THREE.Vector3(1, 2, 3)]) {
      it(`keeps all corners visible at aspect ${aspect} and direction ${direction.toArray()}`, () => {
        const bounds = new THREE.Box3(new THREE.Vector3(-8, 2, -30), new THREE.Vector3(12, 6, 20));
        const view = getShareBoundsView(bounds, aspect, 50, direction, new THREE.Vector3(0.2, 1, 0.3))!;
        const camera = new THREE.PerspectiveCamera(view.fov, aspect, 0.0001, 10000);
        camera.position.copy(view.position); camera.up.copy(view.up); camera.lookAt(view.target); camera.updateMatrixWorld(true);
        assert.ok(view.target.distanceTo(new THREE.Vector3(2, 4, -5)) < 1e-8);
        for (const x of [-8, 12]) for (const y of [2, 6]) for (const z of [-30, 20]) {
          const clip = new THREE.Vector3(x, y, z).project(camera);
          assert.ok(Math.abs(clip.x) < 1 && Math.abs(clip.y) < 1 && clip.z > -1 && clip.z < 1);
        }
      });
    }
  }
  it('keeps depth-only models in front of the camera and rejects invalid bounds', () => {
    const bounds = new THREE.Box3(new THREE.Vector3(0, 0, -5), new THREE.Vector3(0, 0, 5));
    const view = getShareBoundsView(bounds, 1, 50)!;
    assert.ok(view.position.z > 5);
    assert.equal(getShareBoundsView(new THREE.Box3(), 1, 50), null);
    assert.equal(getShareBoundsView(bounds, 0, 50), null);
    assert.equal(getShareBoundsView(bounds, 1, NaN), null);
    assert.equal(getShareBoundsView(new THREE.Box3(new THREE.Vector3(NaN, 0, 0), new THREE.Vector3(1, 1, 1)), 1, 50), null);
  });
});
