import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  hasActiveTask,
  reconcileTaskSnapshot,
  sourceTask,
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

describe('sourceTask', () => {
  const item = { id: 'album_file', size: 10, updated_at: '2026-10-11T00:00:00Z' };
  const version = { size: 10, mtime: Date.parse(item.updated_at) / 1000 };

  it('clears an earlier failure after a successful retry regardless of array order', () => {
    const failed = { ...makeTask('failed', 'failed'), source_media_id: item.id, created_at: 1 };
    const completed = { ...makeTask('success', 'completed'), source_media_id: item.id, created_at: 2 };
    assert.equal(sourceTask(item, undefined, [failed, completed]), undefined);
    assert.equal(sourceTask(item, undefined, [completed, failed]), undefined);
  });

  it('keeps an active concurrent generation visible when a model already exists', () => {
    const running = { ...makeTask('running', 'running'), source_id: 'hash', created_at: 1 };
    const completed = { ...makeTask('success', 'completed'), source_id: 'hash', created_at: 2 };
    assert.equal(sourceTask(item, { source_id: 'hash' }, [completed, running]), running);
  });

  it('does not show an old task on a replaced file at the same path', () => {
    const task = { ...makeTask('old', 'running'), source_media_id: item.id, source_media_version: version };
    assert.equal(sourceTask({ ...item, size: 11 }, undefined, [task]), undefined);
    assert.equal(sourceTask({ ...item, updated_at: '2026-10-11T00:00:02Z' }, undefined, [task]), undefined);
    assert.equal(sourceTask(item, undefined, [task]), task);
  });

  it('matches virtual originals by content and rejects different content at the same media ID', () => {
    const task = { ...makeTask('active', 'pending'), source_media_id: item.id, source_id: 'hash' };
    assert.equal(sourceTask({ id: 'model-sources_hash' }, { source_id: 'hash' }, [task]), task);
    assert.equal(sourceTask(item, { source_id: 'different' }, [task]), undefined);
  });
});
