/**
 * Ligação: o `ProcessDetails` pede as três listas de atribuição (staff,
 * indexação, parceiro) COM o id do processo. A guarda é sobre a fonte porque
 * montar a página não distingue uma lista do Master de outra (o `api` é um
 * duplo); a contraprova garante que o leitor leu mesmo a função.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const AQUI = dirname(fileURLToPath(import.meta.url));
const semComentarios = (f) =>
  f.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
const fonte = semComentarios(readFileSync(join(AQUI, "..", "ProcessDetails.js"), "utf8"));

const corpoDeFetchUsers = () => {
  const inicio = fonte.indexOf("const fetchUsers = async () => {");
  expect(inicio).toBeGreaterThan(-1);
  return fonte.slice(inicio, inicio + 1200);
};

describe("ProcessDetails — listas de atribuição do processo", () => {
  it("o staff, a indexação e o parceiro levam o processId", () => {
    const corpo = corpoDeFetchUsers();
    expect(corpo).toMatch(/getStaffUsers\(\{ processId: id \}\)/);
    // O Index é uma lista de ATRIBUIÇÃO: `forAssignment` faz o servidor juntar os indexadores da rede.
    expect(corpo).toMatch(/getUsers\("indexacao", \{ processId: id, forAssignment: true \}\)/);
    expect(corpo).toMatch(/getUsers\("parceiro", \{ processId: id \}\)/);
  });

  it("contraprova: o leitor lê mesmo a função (as três chamadas existem)", () => {
    const corpo = corpoDeFetchUsers();
    expect((corpo.match(/getStaffUsers\(|getUsers\(/g) || []).length).toBe(3);
  });
});
