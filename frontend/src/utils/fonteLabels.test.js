/**
 * Testes unitários (node --test) — PACOTE 11 (Eixo 3): dicionário de
 * labels PT-PT para o campo `fonte` dos clientes.
 * Correr: node --test src/utils/fonteLabels.test.js
 */
import { test } from "node:test";
import assert from "node:assert/strict";

import { FONTE_LABELS, formatFonteLabel } from "./fonteLabels.js";

test("valores técnicos do backend mapeiam para PT-PT legível", () => {
  assert.equal(formatFonteLabel("staff_created"), "Criado pela Equipa");
  assert.equal(formatFonteLabel("auto_created"), "Criação Automática");
  assert.equal(formatFonteLabel("public_form"), "Registo no Portal");
  assert.equal(formatFonteLabel("onboarding_auto"), "Onboarding Automático");
  assert.equal(formatFonteLabel("migrated_from_process"), "Migração de Processo");
  assert.equal(formatFonteLabel("segundo_titular"), "Segundo Titular");
});

test("valores legados/manuais mantêm-se legíveis", () => {
  assert.equal(formatFonteLabel("Manual"), "Manual");
  assert.equal(formatFonteLabel("Website"), "Website");
  assert.equal(formatFonteLabel("trello"), "Trello");
  assert.equal(formatFonteLabel("Indicação"), "Indicação");
});

test("valor desconhecido é humanizado (não mostrado cru)", () => {
  assert.equal(formatFonteLabel("novo_canal_x"), "Novo Canal X");
  assert.equal(formatFonteLabel("parceiro-externo"), "Parceiro Externo");
});

test("vazio devolve em-dash", () => {
  assert.equal(formatFonteLabel(null), "—");
  assert.equal(formatFonteLabel(""), "—");
  assert.equal(formatFonteLabel(undefined), "—");
});

test("dicionário exportado contém as chaves essenciais", () => {
  assert.ok(FONTE_LABELS["staff_created"]);
  assert.ok(FONTE_LABELS["public_form"]);
  assert.ok(FONTE_LABELS["auto_created"]);
});
