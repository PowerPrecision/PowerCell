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

describe("useWebSocket Pacote FG / A2", () => {
  it("does not store lastMessage in React state", () => {
    assert.doesNotMatch(source, /lastMessage/);
    assert.doesNotMatch(source, /setLastMessage/);
  });

  it("does not notify React state listeners from _handleMessage", () => {
    const start = source.indexOf("_handleMessage(event)");
    assert.ok(start > 0);
    const end = source.indexOf("_handleAuthFailure()", start);
    const body = source.slice(start, end);
    assert.match(body, /_dispatchEvent\(type, payload, data\)/);
    assert.doesNotMatch(body, /_notifyStateListeners/);
  });

  it("connection subscribe payload is isConnected + connectionError only", () => {
    assert.match(
      source,
      /subscribe\(\(\{ isConnected: connected, connectionError: error \}\)/,
    );
  });
});

describe("useWebSocket Pacote FP", () => {
  it("aborts reconnect on expired JWT and waits for a fresh token", () => {
    assert.match(source, /_waitingForFreshToken/);
    assert.match(source, /_handleExpiredToken/);
    assert.match(source, /isExpiredTokenWebSocketClose/);
    assert.match(source, /isJwtExpired/);
    assert.match(source, /Token expirado — a abortar reconexão automática com o mesmo JWT/);
    assert.match(source, /do not reconnect with the expired JWT/);
  });

  it("uses exponential backoff with a hard cap of consecutive reconnects", () => {
    assert.match(source, /MAX_RECONNECT_ATTEMPTS = 8/);
    assert.match(source, /INITIAL_RECONNECT_INTERVAL = 1000/);
    assert.match(source, /MAX_RECONNECT_INTERVAL = 30000/);
    assert.match(source, /_scheduleReconnect/);
    assert.match(source, /Limite de \$\{MAX_RECONNECT_ATTEMPTS\} reconexões atingido/);
  });

  it("does not reset backoff on onopen until the connection stays stable", () => {
    assert.match(source, /STABLE_CONNECTION_MS = 3000/);
    assert.match(source, /Do NOT reset backoff here/);
    assert.match(source, /_markConnectionStable/);
    const onopen = source.slice(source.indexOf("this.ws.onopen"), source.indexOf("this.ws.onmessage"));
    assert.ok(onopen.includes("this.ws.onopen"));
    assert.doesNotMatch(onopen, /this\._reconnectAttempts = 0/);
  });

  it("reconnects from updateToken even when the socket is down", () => {
    const start = source.indexOf("updateToken(newToken)");
    const body = source.slice(start, source.indexOf("_handleMessage(event)"));
    assert.match(body, /this\.connect\(newToken\)/);
  });

  it("keeps the option-callback event subscriptions on a stable \[\] effect", () => {
    assert.match(source, /wsManager\.on\(WSEventType\.PROCESS_CREATED/);
    assert.match(source, /wsManager\.on\(WSEventType\.NEW_NOTIFICATION/);
    assert.match(source, /wsManager\.on\(WSEventType\.NEW_CHAT_MESSAGE/);
    assert.match(source, /return \(\) => unsubs\.forEach/);
  });
});
