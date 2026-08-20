/**
 * Pacote DU — deep linking de tabs do processo.
 * Run: node --test src/utils/processDeepLink.test.js
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { processDeepLink, resolveProcessTabsFromQuery } from "./processDeepLink.js";

describe("resolveProcessTabsFromQuery", () => {
  it("abre Mensagens do Portal com tab=portal", () => {
    assert.deepEqual(resolveProcessTabsFromQuery("portal"), {
      mainTab: "resumo",
      activeTab: "mensagens",
    });
  });

  it("abre Documentos e Histórico no tab de topo", () => {
    assert.equal(resolveProcessTabsFromQuery("documentos").mainTab, "documentos");
    assert.equal(resolveProcessTabsFromQuery("historico").mainTab, "historico");
  });

  it("default é resumo/cliente", () => {
    assert.deepEqual(resolveProcessTabsFromQuery(""), {
      mainTab: "resumo",
      activeTab: "personal",
    });
  });
});

describe("processDeepLink", () => {
  it("usa /processo/:id?tab=portal", () => {
    assert.equal(processDeepLink("abc", "portal"), "/processo/abc?tab=portal");
  });
});
