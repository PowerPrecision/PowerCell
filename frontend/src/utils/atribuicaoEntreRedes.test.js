import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import {
  PREFIXO_DA_RECUSA_DE_ATRIBUICAO_ENTRE_REDES,
  eRecusaDeAtribuicaoEntreRedes,
} from "./atribuicaoEntreRedes";

describe("eRecusaDeAtribuicaoEntreRedes (o toast do 403 diz a verdade)", () => {
  it("reconhece a mensagem que o servidor devolve", () => {
    expect(eRecusaDeAtribuicaoEntreRedes(
      "Só pode atribuir diretamente pessoas da sua própria rede. Para passar o processo a outra empresa use «Partilhar com Empresa…».",
    )).toBe(true);
  });

  it("um 403 de permissões, vazio ou que não é texto NÃO conta", () => {
    expect(eRecusaDeAtribuicaoEntreRedes("Sem permissão para esta acção")).toBe(false);
    expect(eRecusaDeAtribuicaoEntreRedes("")).toBe(false);
    expect(eRecusaDeAtribuicaoEntreRedes(undefined)).toBe(false);
    expect(eRecusaDeAtribuicaoEntreRedes({ detail: PREFIXO_DA_RECUSA_DE_ATRIBUICAO_ENTRE_REDES })).toBe(false);
    expect(eRecusaDeAtribuicaoEntreRedes([PREFIXO_DA_RECUSA_DE_ATRIBUICAO_ENTRE_REDES])).toBe(false);
  });

  it("o prefixo é o MESMO que o servidor escreve (lê o Python)", () => {
    const raiz = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
    const py = readFileSync(
      join(raiz, "backend", "services", "assignment_network_guard.py"), "utf8",
    );
    expect(py).toContain(PREFIXO_DA_RECUSA_DE_ATRIBUICAO_ENTRE_REDES);
  });

  it("o interceptor do Axios usa-o (contraprova de que está ligado)", () => {
    const api = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), "..", "services", "api.js"), "utf8",
    ).split("\n").filter((l) => !l.trim().startsWith("//")).join("\n");
    expect(api).toContain("eRecusaDeAtribuicaoEntreRedes(detalhe)");
  });
});
