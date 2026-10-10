import { beforeEach, describe, expect, it, vi } from "vitest";

const baixar = vi.hoisted(() => vi.fn());
vi.mock("../../utils/executivo", async (importOriginal) => ({
  ...(await importOriginal()),
  descarregarBlob: baixar,
}));

import { descarregarPdf, mensagemDoPdf } from "./descarregarPdf";

beforeEach(() => vi.clearAllMocks());

describe("descarregarPdf", () => {
  it("descarrega com o nome do servidor", async () => {
    const blob = new Blob(["%PDF-"]);
    const r = await descarregarPdf(
      async () => ({ data: blob, headers: { "content-disposition": 'attachment; filename="r_1.pdf"' } }),
      "recuo.pdf",
    );
    expect(r).toEqual({ ok: true, nome: "r_1.pdf", analise: null });
    expect(baixar).toHaveBeenCalledWith(blob, "r_1.pdf");
  });

  it("sem Content-Disposition usa o nome de recuo", async () => {
    const r = await descarregarPdf(async () => ({ data: new Blob(["x"]), headers: {} }), "recuo.pdf");
    expect(r.nome).toBe("recuo.pdf");
  });

  it("o corpo de ERRO chega como Blob e o motivo do servidor não se perde", async () => {
    const texto = JSON.stringify({ detail: "O relatório demorou demasiado a calcular." });
    const blob = new Blob([texto]);
    // O jsdom não implementa `Blob.text()` (os navegadores sim): sem isto o
    // teste exercitava o ramo de falha de leitura e não o caminho real.
    blob.text = async () => texto;
    const erroEmBlob = { response: { data: blob } };
    const r = await descarregarPdf(async () => { throw erroEmBlob; }, "x.pdf");
    expect(r).toEqual({ ok: false, erro: "O relatório demorou demasiado a calcular." });
    expect(baixar).not.toHaveBeenCalled();
  });

  it("um erro sem corpo legível dá a mensagem genérica", async () => {
    const r = await descarregarPdf(async () => { throw new Error("rede"); }, "x.pdf");
    expect(r).toEqual({ ok: false, erro: "Não foi possível gerar o PDF" });
  });
});

describe("descarregarPdf — o que aconteceu à análise de IA", () => {
  const com = (valor) => async () => ({ data: new Blob(["x"]), headers: { "x-analise-ia": valor } });

  it.each(["incluida", "simulada", "indisponivel", "nao-pedida"])("devolve o estado «%s» do servidor", async (estado) => {
    const r = await descarregarPdf(com(estado), "x.pdf");
    expect(r.analise).toBe(estado);
  });
});

describe("mensagemDoPdf", () => {
  it("pediu e não veio: AVISA (um PDF sem ela e sem uma palavra parece um defeito)", () => {
    const m = mensagemDoPdf({ analise: "indisponivel" }, true);
    expect(m.tipo).toBe("aviso");
    expect(m.texto).toMatch(/sem a análise de IA/);
  });

  it("não pediu: nunca avisa, mesmo que o servidor diga indisponível", () => {
    expect(mensagemDoPdf({ analise: "indisponivel" }, false)).toEqual({ tipo: "sucesso", texto: "PDF gerado" });
  });

  it("pediu e veio: sucesso simples", () => {
    expect(mensagemDoPdf({ analise: "incluida" }, true)).toEqual({ tipo: "sucesso", texto: "PDF gerado" });
  });

  it("em desenvolvimento diz que a análise é simulada", () => {
    const m = mensagemDoPdf({ analise: "simulada" }, true);
    expect(m.tipo).toBe("sucesso");
    expect(m.texto).toMatch(/simulada/);
  });

  it("um servidor antigo que não envia o cabeçalho não rebenta", () => {
    expect(mensagemDoPdf({ analise: null }, true)).toEqual({ tipo: "sucesso", texto: "PDF gerado" });
    expect(mensagemDoPdf(undefined, true)).toEqual({ tipo: "sucesso", texto: "PDF gerado" });
  });
});
