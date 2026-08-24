/**
 * Pacote DX — session expiry, WS auth close codes, fetch 401 guard.
 * Run: node --test src/services/sessionExpiry.test.js
 */
import { describe, it, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import {
  isAuthWebSocketClose,
  isExpiredTokenWebSocketClose,
  isJwtExpired,
  isAuthExemptUrl,
  isStaffApiUrl,
  isSessionInvalid,
  forceSessionExpired,
  resetSessionExpiryForTests,
  clearStaffAuthStorage,
  createAuthFetch,
  registerSessionCleanup,
  requestUsedStaffToken,
  WS_CLOSE_TOKEN_EXPIRED,
  WS_CLOSE_TOKEN_INVALID,
  WS_CLOSE_TOKEN_EXPIRED_LEGACY,
  WS_CLOSE_TOKEN_INVALID_LEGACY,
} from "./sessionExpiry.js";

function makeJwt(exp) {
  const header = Buffer.from(JSON.stringify({ alg: "none" })).toString("base64url");
  const payload = Buffer.from(JSON.stringify({ exp })).toString("base64url");
  return `${header}.${payload}.sig`;
}

function mockStorage() {
  const store = {};
  return {
    getItem: (key) => (Object.prototype.hasOwnProperty.call(store, key) ? store[key] : null),
    setItem: (key, value) => {
      store[key] = String(value);
    },
    removeItem: (key) => {
      delete store[key];
    },
    clear: () => {
      Object.keys(store).forEach((key) => delete store[key]);
    },
  };
}

describe("isAuthWebSocketClose", () => {
  it("detects backend JWT close codes 4001/4002 and legacy 4001/4002", () => {
    assert.equal(isAuthWebSocketClose({ code: WS_CLOSE_TOKEN_EXPIRED, reason: "" }), true);
    assert.equal(isAuthWebSocketClose({ code: WS_CLOSE_TOKEN_INVALID, reason: "" }), true);
    assert.equal(isAuthWebSocketClose({ code: WS_CLOSE_TOKEN_EXPIRED_LEGACY, reason: "" }), true);
    assert.equal(isAuthWebSocketClose({ code: WS_CLOSE_TOKEN_INVALID_LEGACY, reason: "" }), true);
    assert.equal(WS_CLOSE_TOKEN_EXPIRED, 4001);
    assert.equal(WS_CLOSE_TOKEN_INVALID, 4002);
  });

  it("detects HTTP 403/401 reasons from handshake rejection", () => {
    assert.equal(isAuthWebSocketClose({ code: 1006, reason: "HTTP 403" }), true);
    assert.equal(isAuthWebSocketClose({ code: 1006, reason: "Token expirado" }), true);
    assert.equal(isAuthWebSocketClose({ code: 1006, reason: "Unauthorized" }), true);
  });

  it("does not treat a normal network drop as auth failure", () => {
    assert.equal(isAuthWebSocketClose({ code: 1006, reason: "" }), false);
    assert.equal(isAuthWebSocketClose({ code: 1001, reason: "Going away" }), false);
  });
});

describe("isExpiredTokenWebSocketClose / isJwtExpired (Pacote FP)", () => {
  it("treats backend 4001, legacy 4001 and expiry reasons as expired-token closes", () => {
    assert.equal(isExpiredTokenWebSocketClose({ code: 4001, reason: "" }), true);
    assert.equal(isExpiredTokenWebSocketClose({ code: 4001, reason: "" }), true);
    assert.equal(isExpiredTokenWebSocketClose({ code: 1006, reason: "Token expirado" }), true);
    assert.equal(isExpiredTokenWebSocketClose({ code: 4002, reason: "" }), false);
    assert.equal(isExpiredTokenWebSocketClose({ code: 1006, reason: "" }), false);
  });

  it("detects JWT exp locally so reconnect can abort before opening a socket", () => {
    const past = Math.floor(Date.now() / 1000) - 60;
    const future = Math.floor(Date.now() / 1000) + 3600;
    assert.equal(isJwtExpired(makeJwt(past)), true);
    assert.equal(isJwtExpired(makeJwt(future)), false);
    assert.equal(isJwtExpired("not-a-jwt"), false);
    assert.equal(isJwtExpired(""), false);
  });
});

describe("URL helpers", () => {
  it("identifies staff API URLs and exempts login/refresh", () => {
    assert.equal(isStaffApiUrl("http://localhost:8001/api/emails/webmail-stats"), true);
    assert.equal(isStaffApiUrl("https://bucket.s3.amazonaws.com/file"), false);
    assert.equal(isAuthExemptUrl("http://localhost:8001/api/auth/login-v2"), true);
    assert.equal(isAuthExemptUrl("http://localhost:8001/api/auth/refresh"), true);
    assert.equal(isAuthExemptUrl("http://localhost:8001/api/emails/webmail-stats"), false);
  });
});

describe("forceSessionExpired", () => {
  let originalWindow;
  let redirects;

  beforeEach(() => {
    resetSessionExpiryForTests();
    globalThis.localStorage = mockStorage();
    globalThis.sessionStorage = mockStorage();
    redirects = [];
    originalWindow = globalThis.window;
    globalThis.window = {
      location: {
        pathname: "/staff",
        replace(url) {
          redirects.push(url);
          this.pathname = url;
        },
      },
    };
    localStorage.setItem("token", "abc");
    localStorage.setItem("refreshToken", "def");
    localStorage.setItem("user", "{}");
  });

  afterEach(() => {
    resetSessionExpiryForTests();
    globalThis.window = originalWindow;
  });

  it("clears auth storage, blocks later requests and redirects to /login", () => {
    let cleaned = 0;
    registerSessionCleanup(() => {
      cleaned += 1;
    });

    forceSessionExpired({ silent: true });

    assert.equal(isSessionInvalid(), true);
    assert.equal(localStorage.getItem("token"), null);
    assert.equal(localStorage.getItem("refreshToken"), null);
    assert.equal(cleaned, 1);
    assert.deepEqual(redirects, ["/login"]);

    forceSessionExpired({ silent: true });
    assert.equal(cleaned, 1);
    assert.equal(redirects.length, 1);
  });
});

describe("createAuthFetch", () => {
  beforeEach(() => {
    resetSessionExpiryForTests();
    globalThis.localStorage = mockStorage();
    globalThis.sessionStorage = mockStorage();
    globalThis.window = {
      location: {
        pathname: "/webmail",
        replace() {},
      },
    };
    localStorage.setItem("token", "staff-token");
  });

  afterEach(() => {
    resetSessionExpiryForTests();
  });

  it("retries once after silent refresh on staff 401", async () => {
    const calls = [];
    const originalFetch = async (url, init) => {
      calls.push({ url, auth: init?.headers?.get?.("Authorization") || init?.headers?.Authorization });
      if (calls.length === 1) return { status: 401 };
      return { status: 200 };
    };
    const fetch = createAuthFetch(originalFetch, {
      getRefreshedToken: async () => "new-token",
    });

    const res = await fetch("http://localhost:8001/api/emails/webmail-stats", {
      headers: { Authorization: "Bearer staff-token" },
    });

    assert.equal(res.status, 200);
    assert.equal(calls.length, 2);
    assert.match(String(calls[1].auth), /new-token/);
    assert.equal(isSessionInvalid(), false);
  });

  it("blocks subsequent fetch after a dead session", async () => {
    const originalFetch = async () => ({ status: 401 });
    const fetch = createAuthFetch(originalFetch, {
      getRefreshedToken: async () => null,
    });

    const first = await fetch("http://localhost:8001/api/emails/webmail-stats", {
      headers: { Authorization: "Bearer staff-token" },
    });
    assert.equal(first.status, 401);
    assert.equal(isSessionInvalid(), true);

    await assert.rejects(
      () => fetch("http://localhost:8001/api/emails/webmail-stats", {
        headers: { Authorization: "Bearer staff-token" },
      }),
      /Session expired/,
    );
  });

  it("does not expire the session on login 401", async () => {
    const fetch = createAuthFetch(async () => ({ status: 401 }), {
      getRefreshedToken: async () => null,
    });
    const res = await fetch("http://localhost:8001/api/auth/login-v2", {
      headers: { Authorization: "Bearer staff-token" },
    });
    assert.equal(res.status, 401);
    assert.equal(isSessionInvalid(), false);
  });
});

describe("requestUsedStaffToken / clearStaffAuthStorage", () => {
  beforeEach(() => {
    globalThis.localStorage = mockStorage();
    globalThis.sessionStorage = mockStorage();
    localStorage.setItem("token", "t1");
  });

  it("matches bearer token from the request headers", () => {
    assert.equal(
      requestUsedStaffToken("http://x/api/y", { headers: { Authorization: "Bearer t1" } }),
      true,
    );
    assert.equal(
      requestUsedStaffToken("http://x/api/y", { headers: { Authorization: "Bearer other" } }),
      false,
    );
  });

  it("clears staff keys", () => {
    localStorage.setItem("refreshToken", "r");
    sessionStorage.setItem("activeRole", "admin");
    clearStaffAuthStorage();
    assert.equal(localStorage.getItem("token"), null);
    assert.equal(sessionStorage.getItem("activeRole"), null);
  });
});
