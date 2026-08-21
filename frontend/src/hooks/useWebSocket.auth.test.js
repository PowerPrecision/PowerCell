/**
 * Pacote DX — WebSocket polling path and auth-close guards.
 * Run: node --test src/hooks/useWebSocket.auth.test.js
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const source = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "useWebSocket.js"),
  "utf8",
);

describe("useWebSocket Pacote DX", () => {
  it("polls the live alerts notifications endpoint, not the ghost /api/notifications", () => {
    assert.match(source, /\/api\/alerts\/notifications/);
    assert.match(source, /unread_only=true/);
    assert.doesNotMatch(source, /\/api\/notifications\?/);
    assert.doesNotMatch(source, /\/api\/notifications`/);
  });

  it("accepts event as an alias of type for new_email payloads", () => {
    assert.match(source, /data\.type \|\| data\.event/);
    assert.match(source, /NEW_EMAIL: 'new_email'/);
  });
});
