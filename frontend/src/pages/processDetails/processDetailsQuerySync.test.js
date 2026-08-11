/**
 * Unit tests for ProcessDetails TanStack helpers.
 */
import { queryKeys, invalidateProcessDetailsQueries } from '../../lib/queryClient';

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
    expect(serialized).toContain(JSON.stringify(queryKeys.processes.detail('p1')));
    expect(serialized).toContain(JSON.stringify(queryKeys.activities.byProcess('p1')));
    expect(serialized).toContain(JSON.stringify(queryKeys.deadlines.byProcess('p1')));
    expect(serialized).toContain(JSON.stringify(queryKeys.history.byProcess('p1')));
    expect(serialized).toContain(JSON.stringify(queryKeys.clients.detail('c1')));
    expect(serialized).toContain(JSON.stringify(queryKeys.processes.kanban({})));
  });

  it('skips client invalidation when clientId omitted', async () => {
    const calls = [];
    const queryClient = {
      invalidateQueries: async (arg) => {
        calls.push(arg.queryKey);
      },
    };

    await invalidateProcessDetailsQueries(queryClient, 'p2');
    expect(calls.some((k) => k[0] === 'clients')).toBe(false);
  });
});
