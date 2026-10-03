import { describe, it, expect } from "vitest";

import {
  ARRASTO_PARADO,
  arrastoEntrou,
  arrastoSaiu,
  arrastoTerminou,
  eArrastoDeFicheiros,
  extensaoDe,
  extensoesAceites,
  ficheirosDoEvento,
  mensagemDeRecusa,
  separarPorTipoAceite,
} from "./dropzone";

const ficheiro = (name) => ({ name });
const evento = (dataTransfer) => ({ dataTransfer });

describe("distinguir o arrasto do sistema do arrasto INTERNO", () => {
  it("um arrasto com ficheiros é do sistema", () => {
    expect(eArrastoDeFicheiros(evento({ types: ["Files"], files: [ficheiro("a.pdf")] }))).toBe(true);
  });

  it("o arrasto interno (mover entre categorias) NÃO é", () => {
    // É isto que impede o upload por arrasto de partir o mover que já existia
    // no separador Documentos.
    expect(eArrastoDeFicheiros(evento({ types: ["text/plain"], files: [] }))).toBe(false);
  });

  it("sem `types` decide pela presença de ficheiros", () => {
    expect(eArrastoDeFicheiros(evento({ files: [ficheiro("a.pdf")] }))).toBe(true);
    expect(eArrastoDeFicheiros(evento({ files: [] }))).toBe(false);
  });

  it("sem dataTransfer nenhum não rebenta", () => {
    expect(eArrastoDeFicheiros({})).toBe(false);
    expect(eArrastoDeFicheiros(null)).toBe(false);
  });

  it("os ficheiros saem como array", () => {
    const e = evento({ files: [ficheiro("a.pdf"), ficheiro("b.png")] });
    expect(ficheirosDoEvento(e).map((f) => f.name)).toEqual(["a.pdf", "b.png"]);
    expect(ficheirosDoEvento({})).toEqual([]);
  });
});

describe("o arrasto respeita o MESMO accept do botão", () => {
  const ACCEPT = ".pdf,.jpg,.jpeg,.png,.doc,.docx";

  it("lê as extensões do accept e ignora os media types", () => {
    expect(extensoesAceites(".pdf,.jpg,image/*")).toEqual(["pdf", "jpg"]);
    expect(extensoesAceites("")).toEqual([]);
    expect(extensoesAceites(null)).toEqual([]);
  });

  it("extrai a extensão, insensível a maiúsculas", () => {
    expect(extensaoDe("IRS.PDF")).toBe("pdf");
    expect(extensaoDe("recibo.final.docx")).toBe("docx");
    expect(extensaoDe("semextensao")).toBe("");
    expect(extensaoDe(".oculto")).toBe("");
    expect(extensaoDe("acaba.com.ponto.")).toBe("");
    expect(extensaoDe(null)).toBe("");
  });

  it("separa aceites de recusados", () => {
    const { aceites, recusados } = separarPorTipoAceite(
      [ficheiro("irs.pdf"), ficheiro("virus.exe"), ficheiro("foto.PNG")],
      ACCEPT
    );
    expect(aceites.map((f) => f.name)).toEqual(["irs.pdf", "foto.PNG"]);
    expect(recusados.map((f) => f.name)).toEqual(["virus.exe"]);
  });

  it("sem accept NADA é recusado", () => {
    // Um botão sem restrição não pode ficar mais restrito pelo arrasto.
    const { aceites, recusados } = separarPorTipoAceite([ficheiro("x.exe")], "");
    expect(aceites).toHaveLength(1);
    expect(recusados).toEqual([]);
  });

  it("a mensagem NOMEIA os recusados", () => {
    const msg = mensagemDeRecusa([ficheiro("virus.exe")], ACCEPT);
    expect(msg).toContain("virus.exe");
    expect(msg).toContain("pdf");
  });

  it("sem recusados não há mensagem", () => {
    expect(mensagemDeRecusa([], ACCEPT)).toBe("");
    expect(mensagemDeRecusa(null, ACCEPT)).toBe("");
  });
});

describe("o contador de entradas e saídas", () => {
  it("entrar activa o realce", () => {
    expect(arrastoEntrou(ARRASTO_PARADO)).toEqual({ profundidade: 1, activo: true });
  });

  it("passar sobre um FILHO não apaga o realce", () => {
    // O defeito que isto resolve: `onDragLeave` dispara ao entrar num filho, e
    // uma zona que apague o realce aí pisca enquanto o rato atravessa o
    // conteúdo — o utilizador larga sem saber se vai acertar.
    let e = arrastoEntrou(ARRASTO_PARADO); // entra na zona
    e = arrastoEntrou(e); // entra no filho
    e = arrastoSaiu(e); // sai do filho
    expect(e.activo).toBe(true);
    e = arrastoSaiu(e); // sai da zona
    expect(e.activo).toBe(false);
  });

  it("nunca desce abaixo de zero", () => {
    const e = arrastoSaiu(arrastoSaiu(ARRASTO_PARADO));
    expect(e.profundidade).toBe(0);
    expect(e.activo).toBe(false);
  });

  it("o drop põe tudo a zero", () => {
    expect(arrastoTerminou()).toEqual(ARRASTO_PARADO);
  });

  it("sem estado inicial assume parado", () => {
    expect(arrastoEntrou().activo).toBe(true);
    expect(arrastoSaiu().activo).toBe(false);
  });
});
