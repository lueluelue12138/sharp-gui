import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import * as THREE from 'three';

import { resolveModelAssetSource } from './modelAssets.js';
import { getNextModelReloadToken } from './modelPreviewState.js';
import { resolveViewerOrientation } from './viewerOrientation.js';
import {
  composeViewerModelQuaternion,
  getViewerModelLoadKey,
  isViewerLoadCurrent,
} from './viewerRuntime.js';

import type {
  CurrentModelDescriptor,
  ViewerOrientationInput,
} from '../types/modelPreview.js';
import type { ModelAsset } from '../types/modelAsset.js';

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

  it('falls back conservatively for imports and invalid or missing context', () => {
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
    };
    const plySource = resolveModelAssetSource(asset, 'ply');
    const spzSource = resolveModelAssetSource(asset, 'spz');

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
