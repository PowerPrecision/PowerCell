/**
 * O cliente HTTP do Portal do Parceiro.
 *
 * Prova-se ao nível do ADAPTADOR do Axios (o que SAI do browser), não ao
 * nível do resultado: é a regra do «duplo demasiado esperto» — um mock que
 * reimplementa o cliente valida o mock.
 */
import { AxiosError } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/utils/s3Put", () => ({ putParaS3: vi.fn(async () => undefined) }));

import { putParaS3 } from "@/utils/s3Put";
import { EVENTO_SESSAO_EXPIRADA, guardarSessao, lerToken } from "@/utils/partnerSession";
import fonteDoCliente from "../partnerApi.js?raw";
import * as api from "../partnerApi";

let pedidos;
let respostas;

function instalarAdaptador() {
  pedidos = [];
  respostas = {};
  api.partnerHttp.defaults.adapter = async (config) => {
    pedidos.push(config);
    const chave = `${config.method.toUpperCase()} ${config.url}`;
    const r = respostas[chave] ?? { status: 200, data: { ok: true } };
    const resposta = { data: r.data, status: r.status, statusText: "", headers: {}, config };
    if (r.status >= 400) throw new AxiosError("falhou", "ERR_BAD_REQUEST", config, null, resposta);
    return resposta;
  };
}

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  instalarAdaptador();
  vi.clearAllMocks();
});
afterEach(() => vi.restoreAllMocks());

describe("o cliente do parceiro NÃO é o do staff", () => {
  it("aponta para /api/partner", () => {
    expect(api.partnerHttp.defaults.baseURL).toMatch(/\/api\/partner$/);
  });

  it("a fonte não importa o cliente do staff nem fala dos cabeçalhos dele", () => {
    const codigo = fonteDoCliente.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
    expect(codigo).not.toMatch(/from\s+["'][^"']*services\/api["']|from\s+["']\.\/api["']/);
    expect(codigo).not.toMatch(/X-Company-Id|X-Active-Role/i);
    expect(codigo).not.toMatch(/localStorage/);
    expect(codigo).toMatch(/partnerSession/);
  });

  it("sem sessão não envia Authorization", async () => {
    await api.obterPainel();
    expect(pedidos[0].headers.Authorization).toBeUndefined();
  });

  it("com sessão envia o token do parceiro — e NUNCA cabeçalhos de empresa ou perfil", async () => {
    guardarSessao("tok-do-parceiro", 3600);
    localStorage.setItem("token", "tok-do-staff");
    sessionStorage.setItem("activeRole", "admin");
    sessionStorage.setItem("activeCompanyId", "cmp-power");
    await api.obterPainel();
    const h = pedidos[0].headers;
    expect(h.Authorization).toBe("Bearer tok-do-parceiro");
    expect(JSON.stringify(h)).not.toMatch(/tok-do-staff|X-Company-Id|X-Active-Role/i);
  });
});

describe("a sessão que morre", () => {
  it("um 401 fora da entrada limpa o token e avisa a árvore do parceiro", async () => {
    guardarSessao("tok", 3600);
    respostas["GET /cases"] = { status: 401, data: { detail: "Sessão expirada" } };
    const ouvinte = vi.fn();
    window.addEventListener(EVENTO_SESSAO_EXPIRADA, ouvinte);
    await expect(api.listarCasos()).rejects.toBeTruthy();
    window.removeEventListener(EVENTO_SESSAO_EXPIRADA, ouvinte);
    expect(ouvinte).toHaveBeenCalledTimes(1);
    expect(lerToken()).toBeNull();
  });

  it.each([
    ["POST /auth/login", () => api.entrar("a@b.pt", "x")],
    ["POST /auth/accept-invite", () => api.aceitarConvite({ token: "t".repeat(20), password: "x", accept_terms: true })],
    ["GET /auth/invite/abc", () => api.lerConvite("abc")],
  ])("um 401 na entrada (%s) é só «credenciais erradas» e não toca na sessão", async (chave, chamar) => {
    guardarSessao("tok", 3600);
    respostas[chave] = { status: 401, data: { detail: "Email ou palavra-passe incorrectos." } };
    const ouvinte = vi.fn();
    window.addEventListener(EVENTO_SESSAO_EXPIRADA, ouvinte);
    await expect(chamar()).rejects.toBeTruthy();
    window.removeEventListener(EVENTO_SESSAO_EXPIRADA, ouvinte);
    expect(ouvinte).not.toHaveBeenCalled();
    expect(lerToken()).toBe("tok");
  });

  it("um 400 ao mudar a palavra-passe (actual errada) não mata a sessão", async () => {
    guardarSessao("tok", 3600);
    respostas["POST /auth/change-password"] = { status: 400, data: { detail: "A palavra-passe actual não está correcta." } };
    await expect(api.mudarPalavraPasse("a", "b")).rejects.toBeTruthy();
    expect(lerToken()).toBe("tok");
  });
});

describe("os pedidos", () => {
  it("a listagem só envia os filtros preenchidos", async () => {
    await api.listarCasos({ etapa: "", q: "", page: 2, size: 15 });
    expect(pedidos[0].params).toEqual({ page: 2, size: 15 });
    await api.listarCasos({ etapa: "lead", q: "ana" });
    expect(pedidos[1].params).toEqual({ etapa: "lead", q: "ana" });
  });

  it("os ids vão escapados no caminho", async () => {
    await api.obterCaso("a/b?c");
    expect(pedidos[0].url).toBe("/cases/a%2Fb%3Fc");
    await api.obterUrlDeDescarga("caso 1", "../../x");
    expect(pedidos[1].url).toBe("/cases/caso%201/files/..%2F..%2Fx/download-url");
  });

  it("devolve o CORPO e não a resposta do Axios", async () => {
    respostas["GET /dashboard"] = { status: 200, data: { total_de_casos: 7 } };
    expect(await api.obterPainel()).toEqual({ total_de_casos: 7 });
  });
});

describe("enviarFicheiro — os três passos", () => {
  const ficheiro = new File(["%PDF-1.4"], "cc final.pdf", { type: "application/pdf" });

  beforeEach(() => {
    respostas["POST /cases/caso-1/upload-url"] = {
      status: 200,
      data: { upload_url: "https://s3.exemplo/put", file_key: "Documentação Clientes/c/Index/cc_final.pdf" },
    };
    respostas["POST /cases/caso-1/confirm-upload"] = { status: 200, data: { success: true, id: "f-1" } };
  });

  it("pede o URL, faz o PUT e confirma, por esta ordem", async () => {
    const r = await api.enviarFicheiro("caso-1", ficheiro, { requestId: "req-1", category: "Identificação" });
    expect(r).toEqual({ success: true, id: "f-1" });
    expect(pedidos.map((p) => `${p.method} ${p.url}`)).toEqual([
      "post /cases/caso-1/upload-url",
      "post /cases/caso-1/confirm-upload",
    ]);
    expect(putParaS3).toHaveBeenCalledWith("https://s3.exemplo/put", ficheiro, expect.anything());
    // a ordem: o PUT acontece ENTRE os dois pedidos
    const ordem = [pedidos[0], putParaS3.mock.invocationCallOrder[0], pedidos[1]];
    expect(ordem[1]).toBeGreaterThan(0);
  });

  it("o pedido do URL leva nome, tipo, categoria pedida e pedido — sem tamanho", async () => {
    await api.enviarFicheiro("caso-1", ficheiro, { requestId: "req-1", category: "Identificação" });
    expect(JSON.parse(pedidos[0].data)).toEqual({
      filename: "cc final.pdf",
      content_type: "application/pdf",
      category: "Identificação",
      request_id: "req-1",
    });
  });

  it("a confirmação NÃO envia tamanho nem tipo: o servidor lê os reais do objecto", async () => {
    await api.enviarFicheiro("caso-1", ficheiro, { requestId: "req-1" });
    const corpo = JSON.parse(pedidos[1].data);
    expect(corpo).toEqual({
      file_key: "Documentação Clientes/c/Index/cc_final.pdf",
      original_filename: "cc final.pdf",
      request_id: "req-1",
    });
    expect(Object.keys(corpo)).not.toEqual(expect.arrayContaining(["file_size", "content_type"]));
  });

  it("sem pedido nem categoria não envia os campos", async () => {
    await api.enviarFicheiro("caso-1", ficheiro);
    expect(JSON.parse(pedidos[0].data)).toEqual({ filename: "cc final.pdf", content_type: "application/pdf" });
  });

  it("se o PUT falha, NÃO confirma", async () => {
    putParaS3.mockRejectedValueOnce(new Error("Erro ao enviar o ficheiro."));
    await expect(api.enviarFicheiro("caso-1", ficheiro)).rejects.toThrow(/enviar/);
    expect(pedidos).toHaveLength(1);
  });

  it("um ficheiro sem tipo envia octet-stream", async () => {
    await api.enviarFicheiro("caso-1", new File(["x"], "x.bin"));
    expect(JSON.parse(pedidos[0].data).content_type).toBe("application/octet-stream");
  });
});
