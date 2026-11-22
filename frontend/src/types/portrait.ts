export interface PortraitAvailability {
  ready: boolean;
  code: string | null;
  missing: string[];
  can_start?: boolean;
  repair_prompt?: string;
}

export interface PortraitLaunch {
  state: 'starting' | 'online';
}

export interface PortraitCacheRelease {
  requested: boolean;
  removed: number;
  failed: number;
}

export interface PortraitUpload {
  token: string;
  url: string;
}

export interface PortraitCamera {
  w2c: number[][];
  K: number[][];
  width: number;
  height: number;
}

export interface PortraitReferenceCrop {
  width: number;
  height: number;
  bounds: [number, number, number, number];
}

export interface PortraitCapture {
  source: string;
  model: string;
  capture: string;
  camera: PortraitCamera;
  lens: number;
  edge: number;
  referenceCrop?: PortraitReferenceCrop;
}

export interface PortraitModel {
  model: string;
  url: string;
  intrinsics: number[][];
}

export interface PortraitRepair {
  image: string;
  rough: string;
  reference: string;
  base: string;
}

export interface PortraitFrame {
  image: string;
  manifest: string;
}

export interface RecoveredPortrait {
  id: string;
  stage: 'build' | 'repair';
  job: string;
  started_at: number;
  source: PortraitUpload;
  model?: PortraitModel;
  camera?: PortraitCamera;
  lens: number;
  edge: number;
}

export interface PortraitStageResults {
  build: PortraitModel;
  repair: PortraitRepair;
  refine: { image: string };
  frame: PortraitFrame;
}

export interface PortraitProgress {
  state: 'queued' | 'running';
  node?: string;
  value?: number;
  max?: number;
}

export type PortraitTaskStage = keyof PortraitStageResults | 'upload';

export interface PortraitTask {
  workspaceId: string;
  filename: string;
  stage: PortraitTaskStage;
  status: PortraitProgress['state'] | 'completed' | 'failed';
  startedAt: number;
  percent?: number;
}

export interface PortraitSourceUpload {
  filename: string;
  startedAt: number;
  result: Promise<PortraitUpload>;
  abort: () => void;
}

export type PortraitCancellation = { job: string } | { request_id: string; source: string };

export type PortraitJob<T> =
  | PortraitProgress
  | { state: 'error'; message: string }
  | { state: 'done'; result: T };
