/**
 * Unit tests for ProcessDetails TanStack helpers.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { queryKeys, invalidateProcessDetailsQueries } from '../../lib/queryClient.js';

describe('invalidateProcessDetailsQueries', () => {
  it('invalidates process detail, side panels, list and kanban', async () => {
    const calls = [];
    const queryClient = {
      invalidateQueries: async (arg) => {
        calls.push(arg.queryKey);
      },
    };

    await invalidateProcessDetailsQueries(queryClient, 'p1', { clientId: 'c1' });

    const serialized = calls.map((k) => JSON.stringify(k));
    assert.ok(serialized.includes(JSON.stringify(queryKeys.processes.detail('p1'))));
    assert.ok(serialized.includes(JSON.stringify(queryKeys.activities.byProcess('p1'))));
    assert.ok(serialized.includes(JSON.stringify(queryKeys.deadlines.byProcess('p1'))));
    assert.ok(serialized.includes(JSON.stringify(queryKeys.history.byProcess('p1'))));
    assert.ok(serialized.includes(JSON.stringify(queryKeys.clients.detail('c1'))));
    assert.ok(serialized.includes(JSON.stringify(queryKeys.processes.kanbanAll())));
  });

  it('skips client invalidation when clientId omitted', async () => {
    const calls = [];
    const queryClient = {
      invalidateQueries: async (arg) => {
        calls.push(arg.queryKey);
      },
    };

    await invalidateProcessDetailsQueries(queryClient, 'p2');
    assert.strictEqual(calls.some((k) => k[0] === 'clients'), false);
  });
});
