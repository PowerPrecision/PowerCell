/**
 * O hook das descargas do Index (Out 2026): sequencial, uma descarga por chave de cada vez, e um aviso por falha.
 * O botão fica desactivado enquanto descarrega, por isso o duplo clique só se prova AQUI (a chamada directa).
 */
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock("../../services/api", () => ({
  getIndexDocumentContent: vi.fn(),
  readBlobErrorBody: vi.fn(async () => null),
}));

import { toast } from "sonner";
import { getIndexDocumentContent } from "../../services/api";
import { useDescarregarDocumentos } from "../useDescarregarDocumentos";

const PDF = () => ({ data: new Blob(["x"], { type: "application/pdf" }), headers: { "content-type": "application/pdf" } });

beforeEach(() => {
  vi.clearAllMocks();
  URL.createObjectURL = vi.fn(() => "blob:t");
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
});
afterEach(() => vi.restoreAllMocks());

describe("useDescarregarDocumentos", () => {
  it("um segundo pedido com a mesma chave enquanto o primeiro decorre não faz outro pedido ao servidor", async () => {
    let libertar;
    getIndexDocumentContent.mockImplementationOnce(() => new Promise((r) => { libertar = () => r(PDF()); }));
    const { result } = renderHook(() => useDescarregarDocumentos());
    let primeira;
    let segunda;
    await act(async () => {
      primeira = result.current.descarregar("k", [{ id: "d1", rotulo: "Recibo" }]);
      segunda = await result.current.descarregar("k", [{ id: "d1", rotulo: "Recibo" }]);
    });
    expect(segunda).toEqual({ feitos: 0, falhados: 0 });
    expect(getIndexDocumentContent).toHaveBeenCalledTimes(1);
    expect(result.current.emCurso.has("k")).toBe(true);
    await act(async () => {
      libertar();
      await primeira;
    });
    expect(result.current.emCurso.has("k")).toBe(false);
  });

  it("chaves diferentes não se bloqueiam", async () => {
    getIndexDocumentContent.mockResolvedValue(PDF());
    const { result } = renderHook(() => useDescarregarDocumentos());
    await act(async () => {
      await Promise.all([
        result.current.descarregar("a", [{ id: "d1", rotulo: "A" }]),
        result.current.descarregar("b", [{ id: "d2", rotulo: "B" }]),
      ]);
    });
    expect(getIndexDocumentContent).toHaveBeenCalledTimes(2);
  });

  it("pede sempre com download:true e uma falha liberta a chave e avisa", async () => {
    getIndexDocumentContent.mockRejectedValueOnce({ response: { status: 404 } });
    const { result } = renderHook(() => useDescarregarDocumentos());
    let r;
    await act(async () => {
      r = await result.current.descarregar("k", [{ id: "d1", rotulo: "A" }]);
    });
    expect(getIndexDocumentContent).toHaveBeenCalledWith("d1", { download: true });
    expect(r).toEqual({ feitos: 0, falhados: 1 });
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(result.current.emCurso.size).toBe(0);
    getIndexDocumentContent.mockResolvedValueOnce(PDF());
    await act(async () => {
      r = await result.current.descarregar("k", [{ id: "d1", rotulo: "A" }]);
    });
    expect(r.feitos).toBe(1);
  });

  it("vários documentos descarregam-se por ordem e uma falha parcial di-lo", async () => {
    getIndexDocumentContent.mockResolvedValueOnce(PDF()).mockRejectedValueOnce({ response: { status: 403 } }).mockResolvedValueOnce(PDF());
    const { result } = renderHook(() => useDescarregarDocumentos());
    let r;
    await act(async () => {
      r = await result.current.descarregar("k", [{ id: "a" }, { id: "b" }, { id: "c" }]);
    });
    expect(getIndexDocumentContent.mock.calls.map((c) => c[0])).toEqual(["a", "b", "c"]);
    expect(r).toEqual({ feitos: 2, falhados: 1 });
    expect(toast.error.mock.calls[0][0]).toMatch(/1 de 3 documentos/);
  });
});
