/**
 * Pacote FG / A2 — shared AudioContext for notification beeps.
 * Run: node --test src/utils/notificationSound.test.js
 */
import { describe, it, before } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const source = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "notificationSound.js"),
  "utf8",
);

describe("notificationSound source", () => {
  it("reuses a module-level AudioContext and disconnects nodes", () => {
    assert.match(source, /let sharedAudioContext = null/);
    assert.match(source, /state === "closed"/);
    assert.match(source, /oscillator\.disconnect/);
    assert.match(source, /gainNode\.disconnect/);
    assert.match(source, /oscillator\.onended/);
  });
});

class FakeOscillator {
  constructor() {
    this.frequency = { value: 0 };
    this.type = "";
    this.onended = null;
  }
  connect() {}
  disconnect() {
    this.disconnected = true;
  }
  start() {}
  stop() {
    if (typeof this.onended === "function") this.onended();
  }
}

class FakeGain {
  constructor() {
    this.gain = { value: 0 };
  }
  connect() {}
  disconnect() {
    this.disconnected = true;
  }
}

class FakeAudioContext {
  constructor() {
    FakeAudioContext.created += 1;
    this.state = "running";
    this.currentTime = 0;
    this.destination = {};
  }
  createOscillator() {
    return new FakeOscillator();
  }
  createGain() {
    return new FakeGain();
  }
  resume() {
    return Promise.resolve();
  }
}
FakeAudioContext.created = 0;

describe("playNotificationBeep", () => {
  let playNotificationBeep;
  let getNotificationAudioContextForTests;

  before(async () => {
    globalThis.window = {
      AudioContext: FakeAudioContext,
      webkitAudioContext: FakeAudioContext,
    };
    const mod = await import("./notificationSound.js");
    playNotificationBeep = mod.playNotificationBeep;
    getNotificationAudioContextForTests = mod.getNotificationAudioContextForTests;
  });

  it("creates a single AudioContext across multiple beeps", () => {
    playNotificationBeep();
    playNotificationBeep();
    playNotificationBeep();
    assert.equal(FakeAudioContext.created, 1);
    assert.ok(getNotificationAudioContextForTests());
  });
});
