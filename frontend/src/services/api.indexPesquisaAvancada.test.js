/**
 * A pesquisa avançada do Index — o pedido que SAI (Out 2026).
 *
 * Os filtros de lista (`contract_type`) viajam REPETIDOS na query; o `axios` por omissão escreve
 * `contract_type[]=a`, que o FastAPI não reconhece (ignora o parâmetro, e a pesquisa corre sem filtro).
 * Mede-se a URL que o axios REAL constrói com a configuração que a função passa — não um valor
 * suposto.
 */
import axios from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";

import api, { getIndexDocumentContent, searchIndexAdvanced } from "./api";

afterEach(() => vi.restoreAllMocks());

function urlDoPedido(config) {
  return axios.getUri({ url: "/index/advanced-search", params: config.params, paramsSerializer: config.paramsSerializer });
}

describe("searchIndexAdvanced", () => {
  it("GET /index/advanced-search com skipErrorToast", async () => {
    const get = vi.spyOn(api, "get").mockResolvedValue({ data: { items: [] } });
    await searchIndexAdvanced({ min_salary: 1000 });
    const [url, config] = get.mock.calls[0];
    expect(url).toBe("/index/advanced-search");
    expect(config).toMatchObject({ skipErrorToast: true });
  });

  it("os contratos repetem-se, não levam []", async () => {
    const get = vi.spyOn(api, "get").mockResolvedValue({ data: {} });
    await searchIndexAdvanced({ contract_type: ["efetivo", "termo_certo"], min_salary: 1000 });
    const uri = urlDoPedido(get.mock.calls[0][1]);
    expect(uri).toContain("contract_type=efetivo&contract_type=termo_certo");
    expect(uri).not.toContain("%5B%5D");
    expect(uri).not.toContain("[]");
  });

  it("contraprova: sem o serializador o axios escreve contract_type[]", () => {
    const uri = axios.getUri({ url: "/x", params: { contract_type: ["a", "b"] } });
    expect(decodeURIComponent(uri)).toContain("contract_type[]=a");
  });

  it("filtros vazios não vão no pedido, mas o zero vai (0 € é um valor)", async () => {
    const get = vi.spyOn(api, "get").mockResolvedValue({ data: {} });
    await searchIndexAdvanced({ min_salary: 0, max_salary: "", employer_name: null, job_title: undefined, contract_type: [] });
    expect(get.mock.calls[0][1].params).toEqual({ min_salary: 0 });
  });

  it("a pesquisa por documento leva o tipo e o banco (extratos por banco)", async () => {
    const get = vi.spyOn(api, "get").mockResolvedValue({ data: { view: "documents", items: [] } });
    await searchIndexAdvanced({ document_type: "extrato", bank: "CGD", period_from: "2026-09" });
    expect(get.mock.calls[0][1].params).toEqual({ document_type: "extrato", bank: "CGD", period_from: "2026-09" });
    expect(urlDoPedido(get.mock.calls[0][1])).toContain("document_type=extrato&bank=CGD");
  });

  it("um valor exacto são os dois limites iguais — e as declarações por localidade", async () => {
    const get = vi.spyOn(api, "get").mockResolvedValue({ data: {} });
    await searchIndexAdvanced({ document_type: "recibo", min_salary: 1234.56, max_salary: 1234.56 });
    expect(get.mock.calls[0][1].params).toEqual({ document_type: "recibo", min_salary: 1234.56, max_salary: 1234.56 });
    await searchIndexAdvanced({ document_type: "declaracao_efetividade", employer_location: "Lisboa" });
    expect(get.mock.calls[1][1].params).toEqual({ document_type: "declaracao_efetividade", employer_location: "Lisboa" });
  });
});

describe("getIndexDocumentContent — o «Ver documento» da pesquisa", () => {
  it("pede o conteúdo POR ID ao endpoint do Index, em blob e sem toast", async () => {
    const get = vi.spyOn(api, "get").mockResolvedValue({ data: new Blob(["x"]) });
    await getIndexDocumentContent("doc-9");
    const [url, config] = get.mock.calls[0];
    expect(url).toBe("/index/documents/doc-9/content");
    expect(config).toMatchObject({ responseType: "blob", skipErrorToast: true });
  });

  it("sem download não leva o parâmetro; com download:true leva `download=true`", async () => {
    const get = vi.spyOn(api, "get").mockResolvedValue({ data: new Blob(["x"]) });
    await getIndexDocumentContent("doc-9");
    expect(get.mock.calls[0][1].params).toBeUndefined();
    await getIndexDocumentContent("doc-9", { download: true });
    expect(get.mock.calls[1][0]).toBe("/index/documents/doc-9/content");
    expect(get.mock.calls[1][1]).toMatchObject({ params: { download: true }, responseType: "blob", skipErrorToast: true });
  });

  it("o id é escapado (nunca parte do caminho)", async () => {
    const get = vi.spyOn(api, "get").mockResolvedValue({ data: new Blob(["x"]) });
    await getIndexDocumentContent("a/b?c");
    expect(get.mock.calls[0][0]).toBe("/index/documents/a%2Fb%3Fc/content");
  });
});
