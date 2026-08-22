/**
 * Shared Web Audio beep for in-app notifications.
 *
 * Reuses a single AudioContext (creating one per beep leaks the audio graph
 * and can hit browser limits). Oscillator/gain nodes are disconnected onended.
 */

let sharedAudioContext = null;
let secondBeepTimer = null;

function getSharedAudioContext() {
  if (typeof window === "undefined") return null;
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!Ctx) return null;

  if (!sharedAudioContext || sharedAudioContext.state === "closed") {
    sharedAudioContext = new Ctx();
  }
  if (sharedAudioContext.state === "suspended") {
    sharedAudioContext.resume().catch(() => {});
  }
  return sharedAudioContext;
}

function playTone(audioContext, frequency, durationSeconds) {
  const oscillator = audioContext.createOscillator();
  const gainNode = audioContext.createGain();

  oscillator.connect(gainNode);
  gainNode.connect(audioContext.destination);

  oscillator.frequency.value = frequency;
  oscillator.type = "sine";
  gainNode.gain.value = 0.3;

  const stopAt = audioContext.currentTime + durationSeconds;
  oscillator.start();
  oscillator.stop(stopAt);

  const teardown = () => {
    try {
      oscillator.disconnect();
    } catch {
      /* already disconnected */
    }
    try {
      gainNode.disconnect();
    } catch {
      /* already disconnected */
    }
  };
  oscillator.onended = teardown;
}

/**
 * Two-tone notification beep. Safe to call repeatedly; reuses one AudioContext.
 */
export function playNotificationBeep() {
  try {
    const audioContext = getSharedAudioContext();
    if (!audioContext) return;

    if (secondBeepTimer) {
      clearTimeout(secondBeepTimer);
      secondBeepTimer = null;
    }

    playTone(audioContext, 800, 0.15);
    secondBeepTimer = setTimeout(() => {
      secondBeepTimer = null;
      playTone(audioContext, 1000, 0.15);
    }, 150);
  } catch {
    // Audio not available (autoplay policy, missing API, etc.)
  }
}

/** Test/debug helper — not used in production UI. */
export function getNotificationAudioContextForTests() {
  return sharedAudioContext;
}
