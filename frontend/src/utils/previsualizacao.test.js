// @vitest-environment node
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import {
  TIPOS_COM_PREVISUALIZACAO,
  mensagemDaFalhaDePrevisualizacao,
  podePrevisualizar,
  tipoDaPrevisualizacao,
  tipoDaResposta,
} from "./previsualizacao";

describe("tipoDaPrevisualizacao", () => {
  it.each([
    ["a.pdf", "application/pdf", "pdf"],
    ["A.PDF", "application/pdf", "pdf"],
    ["foto.JPG", "image/jpeg", "imagem"],
    ["foto.jpeg", "image/jpeg", "imagem"],
    ["x.png", "image/png", "imagem"],
    ["x.webp", "image/webp", "imagem"],
    ["x.gif", "image/gif", "imagem"],
  ])("%s → %s", (nome, mime, forma) => {
    expect(tipoDaPrevisualizacao(nome)).toEqual({ mime, forma });
  });

  it.each(["c.docx", "c.xlsx", "pdf", "x.pdf.exe", "", null, undefined, 42])("%s não tem pré-visualização", (nome) => {
    expect(tipoDaPrevisualizacao(nome)).toBeNull();
  });
});

describe("podePrevisualizar", () => {
  it("sem file_id nunca (não há como pedir)", () => {
    expect(podePrevisualizar({ filename: "a.pdf", previsualizavel: true })).toBe(false);
    expect(podePrevisualizar(null)).toBe(false);
  });
  it("o servidor manda quando envia o campo", () => {
    expect(podePrevisualizar({ file_id: "1", filename: "a.pdf", previsualizavel: false })).toBe(false);
    expect(podePrevisualizar({ file_id: "1", filename: "a.pdf", previsualizavel: true })).toBe(true);
  });
  it("mas um «true» não inventa um tipo que o ecrã não sabe desenhar", () => {
    expect(podePrevisualizar({ file_id: "1", filename: "a.docx", previsualizavel: true })).toBe(false);
  });
  it("sem o campo (servidor antigo) recua para a extensão", () => {
    expect(podePrevisualizar({ file_id: "1", filename: "a.png" })).toBe(true);
    expect(podePrevisualizar({ file_id: "1", filename: "a.docx" })).toBe(false);
  });
});

describe("mensagemDaFalhaDePrevisualizacao", () => {
  it("o motivo do servidor vence", () => {
    expect(mensagemDaFalhaDePrevisualizacao(500, "  Motivo X ")).toBe("Motivo X");
  });
  it.each([[413, /grande/], [415, /tipo/], [404, /disponível/], [403, /permissão/], [500, /Não foi possível/]])(
    "%s",
    (estado, padrao) => expect(mensagemDaFalhaDePrevisualizacao(estado, "")).toMatch(padrao),
  );
});

describe("concordância com o servidor", () => {
  const python = readFileSync(
    fileURLToPath(new URL("../../../backend/services/previsualizacao_de_ficheiros.py", import.meta.url)),
    "utf-8",
  );
  // a tabela, e só ela: do literal `TIPOS_COM_PREVISUALIZACAO = {` ao `}` que a fecha (o módulo também
  // menciona o nome na documentação, por isso não se corta pela primeira ocorrência do texto)
  const inicio = python.indexOf("TIPOS_COM_PREVISUALIZACAO = {");
  const bloco = python.slice(inicio, python.indexOf("}", inicio));
  const doServidor = Object.fromEntries([...bloco.matchAll(/"(\.[a-z]+)"\s*:\s*"([a-z/]+)"/g)].map((m) => [m[1], m[2]]));

  it("contraprova: o leitor leu mesmo a tabela do Python", () => {
    expect(Object.keys(doServidor).length).toBeGreaterThanOrEqual(6);
    expect(doServidor[".pdf"]).toBe("application/pdf");
  });

  it("mesmas extensões e mesmos tipos nos dois lados", () => {
    const doEcra = Object.fromEntries(Object.entries(TIPOS_COM_PREVISUALIZACAO).map(([e, t]) => [e, t.mime]));
    expect(doEcra).toEqual(doServidor);
  });
});

describe("tipoDaResposta", () => {
  it.each([
    ["application/pdf", "pdf"],
    ["application/pdf; charset=binary", "pdf"],
    ["IMAGE/PNG", "imagem"],
    ["image/jpeg", "imagem"],
  ])("%s → %s", (cabecalho, forma) => {
    expect(tipoDaResposta(cabecalho).forma).toBe(forma);
  });

  it.each(["text/html", "application/octet-stream", "image/svg+xml", "", null, undefined, 7])(
    "%s nunca vira pré-visualização (um HTML não é um <iframe>)",
    (cabecalho) => expect(tipoDaResposta(cabecalho)).toBeNull(),
  );
});
