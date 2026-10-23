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
  publicDuplicateMessage,
  PUBLIC_DUPLICATE_MESSAGE,
} from "./duplicateClient.js";

const axiosError = (status, detail) => ({
  response: { status, data: { detail } },
});

test("parseDuplicateClientError extrai o 409 estruturado do backend", () => {
  const parsed = parseDuplicateClientError(
    axiosError(409, {
      // PACOTE 12 — a mensagem genérica do backend é ignorada: a mensagem
      // do banner é construída a partir dos matched_fields (granular).
      message: "Já existe um cliente com este NIF ou Email: João Silva",
      existing_client_id: "cli-123",
      existing_client_name: "João Silva",
      matched_fields: ["nif"],
    })
  );
  assert.equal(parsed.existing_client_id, "cli-123");
  assert.equal(parsed.existing_client_name, "João Silva");
  assert.deepEqual(parsed.matched_fields, ["nif"]);
  assert.match(parsed.message, /Já existe um cliente com este NIF: João Silva/);
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
  assert.match(parsed.message, /Já existe um cliente com este NIF e este Email: Maria/);
});

test("mensagem granular por campo: email isolado (PACOTE 12)", () => {
  const parsed = parseDuplicateClientError(
    axiosError(409, {
      existing_client_id: "cli-7",
      existing_client_name: "Ana Costa",
      matched_fields: ["email"],
    })
  );
  assert.match(parsed.message, /Já existe um cliente com este Email: Ana Costa/);
});

test("mensagem granular sem nome do cliente existente (PACOTE 12)", () => {
  const parsed = parseDuplicateClientError(
    axiosError(409, { matched_fields: ["nif"] })
  );
  assert.match(parsed.message, /Já existe um cliente com este NIF\.$/);
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
    axiosError(409, { message: "dup", matched_fields: ["cartao"] })
  );
  assert.deepEqual(parsed.matched_fields, ["nif", "email"]);
  assert.equal(duplicateFieldLabel(parsed.matched_fields), "NIF e Email");
  // Sem discriminação de campos, a mensagem não afirma que ambos coincidiram.
  assert.match(parsed.message, /Já existe um cliente com este NIF ou Email\.$/);
});

test("D-42: o telemóvel já não é um campo em conflito (o servidor que o devolva é ignorado)", () => {
  const parsed = parseDuplicateClientError(
    axiosError(409, {
      existing_client_id: "cli-5",
      existing_client_name: "Rui",
      matched_fields: ["telefone"],
    })
  );
  assert.deepEqual(parsed.matched_fields, ["nif", "email"]);
  assert.equal(duplicateFieldLabel(["telefone"]), "NIF ou Email");
});

test("D-42: NIF e Email dizem-se pela ordem NIF, Email", () => {
  const parsed = parseDuplicateClientError(
    axiosError(409, { matched_fields: ["email", "nif"] })
  );
  assert.equal(duplicateFieldLabel(["email", "nif"]), "NIF e Email");
  assert.match(parsed.message, /Já existe um cliente com este NIF e este Email\.$/);
});

test("D-42: o 409 opaco da equipa (cliente de outra rede) não traz id nem nome e não oferece 'usar existente'", () => {
  const parsed = parseDuplicateClientError(
    axiosError(409, {
      code: "DUPLICATE_CLIENT",
      message: "Já existe um registo associado a este NIF ou Email.",
    })
  );
  assert.equal(parsed.opaco, true);
  assert.equal(parsed.existing_client_id, null);
  assert.equal(parsed.existing_client_name, null);
  assert.equal(parsed.message, "Já existe um registo associado a este NIF ou Email.");
});

test("D-42: um 409 estruturado COM id continua a ser o da própria rede (não é opaco)", () => {
  const parsed = parseDuplicateClientError(
    axiosError(409, { code: "DUPLICATE_CLIENT", existing_client_id: "cli-1", existing_client_name: "Ana" })
  );
  assert.equal(parsed.opaco, undefined);
  assert.equal(parsed.existing_client_id, "cli-1");
});

test("D-42: o 409 anónimo do formulário público tem o seu reconhecedor", () => {
  const erro = {
    response: {
      status: 409,
      data: {
        success: false,
        code: "DUPLICATE_CLIENT",
        detail: "Já existe um registo associado a este NIF ou Email.",
      },
    },
  };
  assert.equal(
    publicDuplicateMessage(erro),
    "Já existe um registo associado a este NIF ou Email."
  );
  // Não se confunde com o da equipa (detail é uma string, não um objecto).
  assert.equal(isDuplicateClientError(erro), false);
});

test("D-42: sem mensagem do servidor usa a por omissão; outros 409 não contam", () => {
  assert.equal(
    publicDuplicateMessage({ response: { status: 409, data: { code: "DUPLICATE_CLIENT" } } }),
    PUBLIC_DUPLICATE_MESSAGE
  );
  assert.equal(publicDuplicateMessage({ response: { status: 409, data: { detail: "x" } } }), null);
  assert.equal(
    publicDuplicateMessage({ response: { status: 400, data: { code: "DUPLICATE_CLIENT" } } }),
    null
  );
  assert.equal(publicDuplicateMessage(null), null);
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
