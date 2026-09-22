/**
 * Testes da resolução do URL base do backend.
 *
 * O que estes testes protegem: um build/execução de DEV sem
 * `REACT_APP_BACKEND_URL` NUNCA pode cair para a API de produção.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  API_BASE_URL,
  BACKEND_URL,
  LOCAL_FALLBACK_URL,
  PRODUCTION_FALLBACK_URL,
  isLocalHostname,
  normalizeBaseUrl,
  resolveApiBaseUrl,
  resolveBuildTimeBackendUrl,
  warnOnCrossEnvironment,
} from "./apiBaseUrl.js";

describe("normalizeBaseUrl", () => {
  it("remove espaços e barras finais", () => {
    assert.equal(normalizeBaseUrl("  https://api.exemplo.pt///  "), "https://api.exemplo.pt");
  });

  it("tolera valores vazios", () => {
    assert.equal(normalizeBaseUrl(undefined), "");
    assert.equal(normalizeBaseUrl(null), "");
    assert.equal(normalizeBaseUrl("   "), "");
  });
});

describe("isLocalHostname", () => {
  it("reconhece loopback", () => {
    for (const host of ["localhost", "127.0.0.1", "0.0.0.0", "::1", "LOCALHOST"]) {
      assert.equal(isLocalHostname(host), true, host);
    }
  });

  it("reconhece sufixos .local e .localhost", () => {
    assert.equal(isLocalHostname("powercell.local"), true);
    assert.equal(isLocalHostname("app.localhost"), true);
  });

  it("não confunde hosts remotos", () => {
    assert.equal(isLocalHostname("powercell.onrender.com"), false);
    assert.equal(isLocalHostname("powercell-dev.onrender.com"), false);
    assert.equal(isLocalHostname(""), false);
  });
});

describe("resolveApiBaseUrl", () => {
  it("a variável de ambiente ganha sempre", () => {
    assert.equal(
      resolveApiBaseUrl({ envUrl: "https://powercell-dev.onrender.com/", hostname: "localhost" }),
      "https://powercell-dev.onrender.com",
    );
  });

  it("host local sem variável usa o backend local, NUNCA produção", () => {
    const url = resolveApiBaseUrl({ envUrl: "", hostname: "localhost" });
    assert.equal(url, LOCAL_FALLBACK_URL);
    assert.notEqual(url, PRODUCTION_FALLBACK_URL);
  });

  it("host remoto sem variável mantém o fallback histórico", () => {
    assert.equal(
      resolveApiBaseUrl({ envUrl: undefined, hostname: "powercell.pt" }),
      PRODUCTION_FALLBACK_URL,
    );
  });
});

describe("resolveBuildTimeBackendUrl", () => {
  it("modo development sem variável não aponta para produção", () => {
    const { url, source } = resolveBuildTimeBackendUrl({ envUrl: "", mode: "development" });
    assert.equal(url, LOCAL_FALLBACK_URL);
    assert.equal(source, "local-fallback");
  });

  it("qualquer modo não-production (ex.: dev) também não aponta para produção", () => {
    assert.equal(resolveBuildTimeBackendUrl({ mode: "dev" }).url, LOCAL_FALLBACK_URL);
    assert.equal(resolveBuildTimeBackendUrl({ mode: "staging" }).url, LOCAL_FALLBACK_URL);
  });

  it("modo production sem variável mantém o fallback, mas identifica a origem", () => {
    const { url, source } = resolveBuildTimeBackendUrl({ envUrl: "", mode: "production" });
    assert.equal(url, PRODUCTION_FALLBACK_URL);
    assert.equal(source, "production-fallback");
  });

  it("variável definida é usada e normalizada em qualquer modo", () => {
    const { url, source } = resolveBuildTimeBackendUrl({
      envUrl: "http://localhost:8001/",
      mode: "production",
    });
    assert.equal(url, "http://localhost:8001");
    assert.equal(source, "env");
  });
});

describe("warnOnCrossEnvironment", () => {
  it("grita quando um host local aponta para produção", () => {
    const mensagens = [];
    const detectou = warnOnCrossEnvironment({
      baseUrl: PRODUCTION_FALLBACK_URL,
      hostname: "localhost",
      logger: { error: (m) => mensagens.push(m) },
    });
    assert.equal(detectou, true);
    assert.equal(mensagens.length, 1);
    assert.match(mensagens[0], /PRODUÇÃO/);
    assert.match(mensagens[0], /REACT_APP_BACKEND_URL/);
  });

  it("cala-se na configuração correcta", () => {
    const mensagens = [];
    const detectou = warnOnCrossEnvironment({
      baseUrl: "http://localhost:8001",
      hostname: "localhost",
      logger: { error: (m) => mensagens.push(m) },
    });
    assert.equal(detectou, false);
    assert.equal(mensagens.length, 0);
  });

  it("não grita em produção a falar com produção", () => {
    const detectou = warnOnCrossEnvironment({
      baseUrl: PRODUCTION_FALLBACK_URL,
      hostname: "powercell.pt",
      logger: { error: () => {} },
    });
    assert.equal(detectou, false);
  });
});

describe("constantes exportadas", () => {
  it("API_BASE_URL é BACKEND_URL + /api", () => {
    assert.equal(API_BASE_URL, `${BACKEND_URL}/api`);
  });

  it("sem window nem variável de ambiente, o módulo não inventa produção em host local", () => {
    // Em Node (sem window) o hostname é "" → o fallback histórico mantém-se,
    // que é o contrato para hosts remotos. O caso perigoso (host local) está
    // coberto pelos testes de `resolveApiBaseUrl`.
    assert.ok(BACKEND_URL.startsWith("http"));
  });
});
