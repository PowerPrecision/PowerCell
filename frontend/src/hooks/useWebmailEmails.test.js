/**
 * Pacote EC — query keys and silent invalidate for Webmail auto-sync.
 * Run: node --test src/hooks/useWebmailEmails.test.js
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const dir = dirname(fileURLToPath(import.meta.url));
const webmailSource = readFileSync(join(dir, "useWebmailEmails.js"), "utf8");
const realtimeSource = readFileSync(join(dir, "useNewEmailRealtime.js"), "utf8");
const pageSource = readFileSync(join(dir, "../pages/WebmailPage.jsx"), "utf8");
const layoutSource = readFileSync(join(dir, "../layouts/DashboardLayout.js"), "utf8");
const queryClientSource = readFileSync(join(dir, "../lib/queryClient.js"), "utf8");

describe("Pacote EC webmail React Query", () => {
  it("uses a 1-minute staleTime and emails query key", () => {
    assert.match(webmailSource, /WEBMAIL_STALE_TIME_MS = 60 \* 1000/);
    assert.match(webmailSource, /staleTime: WEBMAIL_STALE_TIME_MS/);
    assert.match(webmailSource, /queryKeys\.emails\.webmail/);
    assert.match(queryClientSource, /webmail: \(filters\) => \[\.\.\.queryKeys\.emails\.all, 'webmail', filters\]/);
  });

  it("invalidates ['emails'] on new_email for silent refetch", () => {
    assert.match(realtimeSource, /invalidateQueries\(\{ queryKey: queryKeys\.emails\.all \}\)/);
    assert.match(realtimeSource, /onNewEmail/);
    assert.match(pageSource, /useNewEmailRealtime/);
    assert.match(layoutSource, /invalidateEmailQueries|onNewEmail/);
  });
});
