/**
 * Testes unitários (node --test) — PACOTE 10: parsing do 409 de cliente duplicado.
 * Correr: node --test src/utils/duplicateClient.test.js
 */
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  isDuplicateClientError,
  parseDuplicateClientError,
  duplicateFieldLabel,
} from "./duplicateClient.js";

const axiosError = (status, detail) => ({
  response: { status, data: { detail } },
});

test("parseDuplicateClientError extrai o 409 estruturado do backend", () => {
  const parsed = parseDuplicateClientError(
    axiosError(409, {
      message: "Já existe um cliente com este NIF ou Email: João Silva",
      existing_client_id: "cli-123",
      existing_client_name: "João Silva",
      matched_fields: ["nif"],
    })
  );
  assert.equal(parsed.existing_client_id, "cli-123");
  assert.equal(parsed.existing_client_name, "João Silva");
  assert.deepEqual(parsed.matched_fields, ["nif"]);
  assert.match(parsed.message, /Já existe um cliente com este NIF ou Email: João Silva/);
});

test("parseDuplicateClientError reconhece match de email e nif simultâneo", () => {
  const parsed = parseDuplicateClientError(
    axiosError(409, {
      message: "Já existe um cliente com este NIF ou Email: Maria",
      existing_client_id: "cli-9",
      existing_client_name: "Maria",
      matched_fields: ["nif", "email"],
    })
  );
  assert.deepEqual(parsed.matched_fields, ["nif", "email"]);
  assert.equal(duplicateFieldLabel(parsed.matched_fields), "NIF e Email");
});

test("parseDuplicateClientError suporta o formato legacy (400 string)", () => {
  const parsed = parseDuplicateClientError(
    axiosError(400, "Já existe um cliente com este NIF ou email: Nome Antigo")
  );
  assert.equal(parsed.existing_client_id, null);
  assert.equal(parsed.existing_client_name, "Nome Antigo");
  assert.deepEqual(parsed.matched_fields, ["nif", "email"]);
  assert.match(parsed.message, /Já existe um cliente/);
});

test("isDuplicateClientError rejeita outros erros", () => {
  assert.equal(isDuplicateClientError(axiosError(409, "Conflito genérico sem estrutura")), false);
  assert.equal(isDuplicateClientError(axiosError(400, "Formato de email inválido.")), false);
  assert.equal(isDuplicateClientError(axiosError(422, [{ msg: "x" }])), false);
  assert.equal(isDuplicateClientError(null), false);
  assert.equal(isDuplicateClientError(new Error("rede")), false);
});

test("parseDuplicateClientError devolve null para erros não-duplicados", () => {
  assert.equal(parseDuplicateClientError(axiosError(400, "NIF inválido.")), null);
  assert.equal(parseDuplicateClientError(axiosError(500, "Erro interno")), null);
  assert.equal(parseDuplicateClientError(undefined), null);
});

test("matched_fields desconhecidos caem no fallback nif|email", () => {
  const parsed = parseDuplicateClientError(
    axiosError(409, { message: "dup", matched_fields: ["telefone"] })
  );
  assert.deepEqual(parsed.matched_fields, ["nif", "email"]);
  assert.equal(duplicateFieldLabel(parsed.matched_fields), "NIF e Email");
});

test("duplicateFieldLabel devolve labels amigáveis", () => {
  assert.equal(duplicateFieldLabel(["nif"]), "NIF");
  assert.equal(duplicateFieldLabel(["email"]), "Email");
  assert.equal(duplicateFieldLabel([]), "NIF ou Email");
  assert.equal(duplicateFieldLabel(undefined), "NIF ou Email");
});

test("parseDuplicateClientError usa mensagem por omissão quando o backend não envia", () => {
  const parsed = parseDuplicateClientError(
    axiosError(409, { existing_client_id: "cli-x" })
  );
  assert.match(parsed.message, /Já existe um cliente com este NIF ou Email/);
  assert.equal(parsed.existing_client_id, "cli-x");
});
