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
