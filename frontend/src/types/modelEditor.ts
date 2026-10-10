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
}

export type EditorTool = 'move' | 'rotate' | 'rectangle' | 'sphere' | 'box';
export interface EditorRegion {
  center: [number, number, number];
  radius: number;
  size: [number, number, number];
}
