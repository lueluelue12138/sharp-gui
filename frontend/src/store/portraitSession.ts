import type { CameraView } from '@/components/portrait/PortraitWorkbench/portraitRenderer';
import type {
  PortraitCapture, PortraitFrame, PortraitModel, PortraitRepair, PortraitSourceUpload, PortraitStageResults, PortraitTask, PortraitUpload,
} from '@/types/portrait';
import type { PhotoItem } from '@/types';

export interface AngleWorkspace {
  id: string;
  photo?: PhotoItem;
  upload?: PortraitSourceUpload;
  uploadName?: string;
}

export interface PortraitTrajectory {
  samples: Array<{ view: CameraView; keyframe: boolean }>;
  sequence: string;
  mode: 'preview' | 'repair';
  nextIndex: number;
  stopped?: boolean;
}

export interface PendingPortrait {
  stage: keyof PortraitStageResults;
  startedAt: number;
  options?: Record<string, unknown>;
  requestId?: string;
  job?: string;
  trajectory?: PortraitTrajectory;
}

export interface PortraitDraft {
  source?: PortraitUpload;
  model?: PortraitModel;
  base?: PortraitRepair;
  refined?: string;
  reference?: PortraitUpload;
  crop?: [number, number, number, number];
  frames?: PortraitFrame[];
  view?: CameraView | null;
  page?: 'frame' | 'compare' | 'refine';
  maskTab?: 'target' | 'reference' | 'result';
  lens?: number;
  ratio?: string;
  edge?: number;
  repairReferenceEdge?: number;
  repairPrompt?: string;
  matchCloseup?: boolean;
  seed?: number;
  strength?: number;
  referenceEdge?: number;
  sampleEdge?: number;
  expand?: number;
  feather?: number;
  color?: number;
  optimize?: boolean;
  prompt?: string;
  releaseOnRepair?: boolean;
  previewReleased?: boolean;
  lastCapture?: { view: CameraView; ratio: string; edge: number; options: PortraitCapture };
  pending?: PendingPortrait;
  error?: { code: string; message: string };
}

interface PortraitSession {
  workspaces: AngleWorkspace[];
  tasks: PortraitTask[];
  active: string | null;
  legacyRecoveryDone?: boolean;
}

export interface PortraitWorkspaceActions {
  dispose: () => void;
  cancel: () => Promise<void>;
}

const sessionKey = 'sharp-portrait-session-v1';
const draftPrefix = `${sessionKey}/`;

function read<T>(key: string): T | undefined {
  try {
    const stored = sessionStorage.getItem(key);
    return stored ? JSON.parse(stored) : undefined;
  } catch {
    return undefined;
  }
}

function write(key: string, value: unknown) {
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    // The workbench remains usable if browser storage is blocked or full.
  }
}

export function readPortraitSession(): PortraitSession {
  const saved = read<PortraitSession>(sessionKey);
  if (!Array.isArray(saved?.workspaces) || !Array.isArray(saved.tasks)) return { workspaces: [], tasks: [], active: null };
  return {
    ...saved,
    tasks: saved.tasks.map((task) => {
      if (task.status !== 'queued' && task.status !== 'running') return task;
      if (readPortraitDraft(task.workspaceId).pending) return task;
      return { ...task, status: 'failed', percent: undefined };
    }),
  };
}

export function savePortraitSession(session: PortraitSession) {
  const workspaces = session.workspaces.map(({ id, photo, upload, uploadName }) => ({
    id, photo, uploadName: upload?.filename ?? uploadName,
  }));
  write(sessionKey, { ...session, workspaces });
}

export function readPortraitDraft(id: string) {
  return read<PortraitDraft>(draftPrefix + id) ?? {};
}

export function savePortraitDraft(id: string, draft: PortraitDraft) {
  write(draftPrefix + id, draft);
}

export function removePortraitDraft(id: string) {
  try {
    sessionStorage.removeItem(draftPrefix + id);
  } catch {
    // Storage may be unavailable.
  }
}

export function clearPortraitSession() {
  try {
    for (let index = sessionStorage.length - 1; index >= 0; index -= 1) {
      const key = sessionStorage.key(index);
      if (key && (key === sessionKey || key.startsWith(draftPrefix))) sessionStorage.removeItem(key);
    }
  } catch {
    // Storage may be unavailable.
  }
}

export function newPortraitId() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
