import type { ViewerCameraHint } from '@/types/modelPreview';

export interface ModelEditorDescriptor {
  asset_id: string;
  name: string;
  format: 'ply' | 'spz' | 'splat';
  point_count: number;
  fingerprint: string;
  source_url: string;
}

export interface ModelEditorSaveInput {
  fingerprint: string;
  point_count: number;
  deleted_mask: string;
  matrix: number[];
  camera: ViewerCameraHint;
  name: string;
  save_mode?: EditorSaveMode;
}

export type EditorSaveMode = 'copy' | 'overwrite';
export type EditorTool = 'origin' | 'rotate' | 'rectangle' | 'sphere' | 'box';
export type EditorSelectionMode = 'intersect' | 'center' | 'contain';
export interface EditorAlignment {
  origin: [number, number, number];
  /** Calibration angles in radians, relative to the orientation on editor entry. */
  rotation: [number, number, number];
}
export interface EditorRegion {
  center: [number, number, number];
  radius: number;
  size: [number, number, number];
}
