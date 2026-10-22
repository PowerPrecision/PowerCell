import { afterEach, describe, expect, it, vi } from "vitest";

import {
  extensaoDoTipo,
  guardarBlob,
  mensagemDaFalhaDeDescarga,
  nomeDaDescarga,
  nomeDoCabecalho,
  sanearNomeDeFicheiro,
} from "./descarregarFicheiro";

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("sanearNomeDeFicheiro", () => {
  it("tira caminhos, aspas e caracteres de controlo", () => {
    expect(sanearNomeDeFicheiro('..\\x/Rec"ibo\r\n: a?.pdf')).not.toMatch(/[\\/:*?"<>|\r\n]/);
  });
  it("não deixa um nome começar por ponto (ficheiro escondido)", () => {
    expect(sanearNomeDeFicheiro("...segredo.pdf")).toBe("segredo.pdf");
  });
  it("tem tecto de comprimento", () => {
    expect(sanearNomeDeFicheiro("a".repeat(500)).length).toBeLessThanOrEqual(120);
  });
  it("vazio ou lixo dá vazio (quem chama decide o recuo)", () => {
    expect(sanearNomeDeFicheiro("///")).toBe("");
    expect(sanearNomeDeFicheiro(null)).toBe("");
  });
});

describe("nomeDoCabecalho", () => {
  it("lê o filename* UTF-8 (com acentos)", () => {
    expect(nomeDoCabecalho("attachment; filename=\"Declaracao.pdf\"; filename*=UTF-8''Declara%C3%A7%C3%A3o.pdf")).toBe("Declaração.pdf");
  });
  it("recua para o filename simples", () => {
    expect(nomeDoCabecalho('attachment; filename="extrato.pdf"')).toBe("extrato.pdf");
  });
  it("um percent-encoding inválido não rebenta: cai no filename simples", () => {
    expect(nomeDoCabecalho("attachment; filename=\"ok.pdf\"; filename*=UTF-8''%E0%A4%A")).toBe("ok.pdf");
  });
  it("sem cabeçalho (não exposto no CORS) é null", () => {
    expect(nomeDoCabecalho(undefined)).toBeNull();
    expect(nomeDoCabecalho("")).toBeNull();
    expect(nomeDoCabecalho("attachment")).toBeNull();
  });
  it("o nome do servidor também é saneado", () => {
    expect(nomeDoCabecalho("attachment; filename*=UTF-8''..%2F..%2Fx.pdf")).not.toMatch(/[\\/]/);
  });
});

describe("nomeDaDescarga", () => {
  it("o nome do servidor vence o rótulo", () => {
    expect(nomeDaDescarga({ rotulo: "Extrato · CGD", contentType: "application/pdf", disposicao: 'attachment; filename="a.pdf"' })).toBe("a.pdf");
  });
  it("sem cabeçalho sai do rótulo, com a extensão do tipo que chegou", () => {
    expect(nomeDaDescarga({ rotulo: "Extrato · Caixa Geral de Depósitos · 2026-09", contentType: "application/pdf; charset=binary" }))
      .toBe("Extrato · Caixa Geral de Depósitos · 2026-09.pdf");
    expect(nomeDaDescarga({ rotulo: "Recibo", contentType: "image/png" })).toBe("Recibo.png");
  });
  it("não duplica a extensão", () => {
    expect(nomeDaDescarga({ rotulo: "x.pdf", contentType: "application/pdf" })).toBe("x.pdf");
  });
  it("tipo desconhecido não inventa extensão", () => {
    expect(nomeDaDescarga({ rotulo: "Recibo", contentType: "application/octet-stream" })).toBe("Recibo");
  });
  it("sem rótulo nem cabeçalho há um nome seguro", () => {
    expect(nomeDaDescarga({ contentType: "application/pdf" })).toBe("documento.pdf");
    expect(nomeDaDescarga()).toBe("documento");
  });
});

describe("extensaoDoTipo", () => {
  it("conhece os tipos que o servidor declara", () => {
    expect(extensaoDoTipo("application/pdf")).toBe(".pdf");
    expect(extensaoDoTipo("image/jpeg")).toBe(".jpg");
    expect(extensaoDoTipo("application/vnd.openxmlformats-officedocument.wordprocessingml.document")).toBe(".docx");
    expect(extensaoDoTipo(undefined)).toBe("");
    expect(extensaoDoTipo("text/html")).toBe("");
  });
});

describe("guardarBlob", () => {
  it("cria uma ligação `download` com o nome, clica e liberta o URL depois", () => {
    vi.useFakeTimers();
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();
    const clicado = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function click() {
      clicado.push({ href: this.href, download: this.download });
    });
    const nome = guardarBlob(new Blob(["x"]), "a.pdf");
    expect(nome).toBe("a.pdf");
    expect(clicado).toEqual([{ href: "blob:x", download: "a.pdf" }]);
    expect(document.querySelector("a[download]")).toBeNull(); // não fica no DOM
    expect(URL.revokeObjectURL).not.toHaveBeenCalled();
    vi.advanceTimersByTime(4000);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:x");
  });
});

describe("mensagemDaFalhaDeDescarga", () => {
  it("o motivo do servidor, ou um por código", () => {
    expect(mensagemDaFalhaDeDescarga(404, "Documento não encontrado.")).toBe("Documento não encontrado.");
    expect(mensagemDaFalhaDeDescarga(413)).toMatch(/demasiado grande/);
    expect(mensagemDaFalhaDeDescarga(429)).toMatch(/Demasiados/);
    expect(mensagemDaFalhaDeDescarga(500)).toMatch(/Não foi possível/);
  });
});
