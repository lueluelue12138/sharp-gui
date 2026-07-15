import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  hasActiveTask,
  reconcileTaskSnapshot,
} from './tasks.js';

import type { Task, TaskStatus } from '../types/task.js';

function makeTask(id: string, status: TaskStatus): Task {
  return {
    id,
    filename: `${id}.jpg`,
    status,
  };
}

describe('reconcileTaskSnapshot', () => {
  it('accepts an authoritative server snapshot when local tasks did not change', () => {
    const originalTask = makeTask('first', 'processing');
    const serverTask = makeTask('first', 'completed');

    assert.deepEqual(
      reconcileTaskSnapshot([originalTask], [serverTask], [originalTask]),
      [serverTask],
    );
  });

  it('preserves a task added while the poll request was in flight', () => {
    const originalTask = makeTask('first', 'processing');
    const addedTask = makeTask('second', 'pending');
    const completedTask = makeTask('first', 'completed');

    const result = reconcileTaskSnapshot(
      [addedTask, originalTask],
      [completedTask],
      [originalTask],
    );

    assert.deepEqual(result, [addedTask, completedTask]);
    assert.equal(hasActiveTask(result), true);
  });

  it('does not resurrect a task removed while the poll request was in flight', () => {
    const cancelledTask = makeTask('cancelled', 'pending');
    const staleServerTask = makeTask('cancelled', 'processing');

    assert.deepEqual(reconcileTaskSnapshot([], [staleServerTask], [cancelledTask]), []);
  });

  it('keeps a newer local update for an existing task', () => {
    const originalTask = makeTask('first', 'pending');
    const localTask = makeTask('first', 'cancelled');
    const staleServerTask = makeTask('first', 'processing');

    assert.deepEqual(
      reconcileTaskSnapshot([localTask], [staleServerTask], [originalTask]),
      [localTask],
    );
  });
});
