/**
 * Pacote FI — staleTime/gcTime do bundle ProcessDetails.
 * Run: node --test src/hooks/queries/useProcessQuery.test.js
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const dir = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(dir, "useProcessQuery.js"), "utf8");
const detailsSource = readFileSync(
  join(dir, "../../pages/ProcessDetails.js"),
  "utf8",
);

describe("Pacote FI ProcessDetails React Query cache", () => {
  it("uses 60s staleTime and 5min gcTime (not 0)", () => {
    assert.match(source, /PROCESS_STALE_TIME_MS = 60 \* 1000/);
    assert.match(source, /PROCESS_GC_TIME_MS = 5 \* 60 \* 1000/);
    assert.match(source, /staleTime: PROCESS_STALE_TIME_MS/);
    assert.match(source, /gcTime: PROCESS_GC_TIME_MS/);
    assert.doesNotMatch(source, /staleTime:\s*0/);
    assert.doesNotMatch(source, /gcTime:\s*0/);
  });

  it("consumes side-panel queries directly instead of copying to useState", () => {
    assert.match(detailsSource, /const deadlines = processBundle\.deadlines/);
    assert.match(detailsSource, /const activities = processBundle\.activities/);
    assert.match(detailsSource, /const history = processBundle\.history/);
    assert.match(detailsSource, /const workflowStatuses = processBundle\.workflowStatuses/);
    assert.doesNotMatch(detailsSource, /setDeadlines\(/);
    assert.doesNotMatch(detailsSource, /setActivities\(/);
    assert.doesNotMatch(detailsSource, /setHistory\(/);
    assert.doesNotMatch(detailsSource, /setWorkflowStatuses\(/);
    assert.doesNotMatch(detailsSource, /removeQueries\(\{ queryKey: queryKeys\.processes\.detail/);
  });
});
