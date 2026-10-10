import { beforeEach, describe, expect, it, vi } from "vitest";

const baixar = vi.hoisted(() => vi.fn());
vi.mock("../../utils/executivo", async (importOriginal) => ({
  ...(await importOriginal()),
  descarregarBlob: baixar,
}));

import { descarregarPdf } from "./descarregarPdf";

beforeEach(() => vi.clearAllMocks());

describe("descarregarPdf", () => {
  it("descarrega com o nome do servidor", async () => {
    const blob = new Blob(["%PDF-"]);
    const r = await descarregarPdf(
      async () => ({ data: blob, headers: { "content-disposition": 'attachment; filename="r_1.pdf"' } }),
      "recuo.pdf",
    );
    expect(r).toEqual({ ok: true, nome: "r_1.pdf" });
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
