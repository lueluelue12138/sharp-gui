import type { Task, TaskStatus } from '@/types';

const ACTIVE_TASK_STATUSES: ReadonlySet<TaskStatus> = new Set([
  'pending',
  'running',
  'processing',
]);

export function isActiveTaskStatus(status: TaskStatus | undefined): boolean {
  return status != null && ACTIVE_TASK_STATUSES.has(status);
}

export function hasActiveTask(tasks: Task[]): boolean {
  return tasks.some((task) => isActiveTaskStatus(task.status));
}

export function sourceTask(
  item: { id: string; source_id?: string; size?: number | null; updated_at?: string | null },
  link: { source_id: string | null } | undefined,
  tasks: Task[],
): Task | undefined {
  const sourceId = link?.source_id ?? item.source_id;
  const matching = tasks.filter((task) => {
    if (task.source_id && sourceId) return task.source_id === sourceId;
    if (task.source_media_id !== item.id) return false;
    if (!task.source_media_version || item.id.startsWith('model-sources_')) return true;
    const mtime = item.updated_at ? Date.parse(item.updated_at) / 1000 : NaN;
    return (item.size == null || task.source_media_version.size === item.size)
      && (!Number.isFinite(mtime) || Math.abs(task.source_media_version.mtime - mtime) < 0.002);
  });
  const timestamp = (task: Task) => typeof task.created_at === 'number'
    ? task.created_at * 1000 : Date.parse(task.created_at ?? '') || 0;
  matching.sort((a, b) => timestamp(b) - timestamp(a));
  const active = matching.find((task) => isActiveTaskStatus(task.status));
  // Successful retries clear older failure badges; an active concurrent run remains visible.
  return active ?? (matching[0]?.status === 'failed' ? matching[0] : undefined);
}

export function mergeTaskUpdates(currentTasks: Task[], updatedTasks: Task[]): Task[] {
  if (updatedTasks.length === 0) {
    return currentTasks;
  }

  const updatedIds = new Set(updatedTasks.map((task) => task.id));
  return [
    ...updatedTasks,
    ...currentTasks.filter((task) => !updatedIds.has(task.id)),
  ];
}

export function reconcileTaskSnapshot(
  currentTasks: Task[],
  serverTasks: Task[],
  tasksAtRequestStart: readonly Task[],
): Task[] {
  const startById = new Map(tasksAtRequestStart.map((task) => [task.id, task]));
  const currentById = new Map(currentTasks.map((task) => [task.id, task]));
  const locallyChangedIds = new Set<string>();

  for (const taskId of new Set([...startById.keys(), ...currentById.keys()])) {
    if (startById.get(taskId) !== currentById.get(taskId)) {
      locallyChangedIds.add(taskId);
    }
  }

  const unchangedServerTasks = serverTasks.filter((task) => !locallyChangedIds.has(task.id));
  const locallyChangedTasks = currentTasks.filter((task) => locallyChangedIds.has(task.id));
  return mergeTaskUpdates(unchangedServerTasks, locallyChangedTasks);
}

export function createTaskStatusMap(tasks: Task[]): Map<string, TaskStatus> {
  return new Map(tasks.map((task) => [task.id, task.status]));
}

export function hasNewlyCompletedTask(
  previousStatuses: ReadonlyMap<string, TaskStatus>,
  nextTasks: Task[],
): boolean {
  return nextTasks.some(
    (task) => task.status === 'completed' && isActiveTaskStatus(previousStatuses.get(task.id)),
  );
}
