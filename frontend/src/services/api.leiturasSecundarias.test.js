/**
 * Leituras secundárias do detalhe do processo (prazos, pedidos do Portal, alertas, histórico):
 * a recusa 403/404 é por desenho e NÃO pode disparar o toast global «Acesso Negado» por cima de
 * um ecrã que abriu bem. Afirma-se (1) que cada chamada leva `skipErrorToast`, (2) que o
 * interceptor REAL cala o toast com essa marca e (3) que SEM ela o toast continua (contraprova:
 * as acções do utilizador não perdem o aviso). O erro propaga sempre.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  chamar: vi.fn(),
  erroDoInterceptor: null,
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

vi.mock("sonner", () => ({ toast: h.toast }));
vi.mock("axios", () => {
  // `api.get` é um invólucro de deduplicação que chama a INSTÂNCIA como função: `api(config)`.
  const instancia = Object.assign(h.chamar, {
    post: vi.fn(), put: vi.fn(), delete: vi.fn(), patch: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn((_ok, erro) => { h.erroDoInterceptor = erro; }) },
    },
    defaults: { headers: { common: {} } },
  });
  return { default: { create: () => instancia, ...instancia, isCancel: () => false }, create: () => instancia };
});

import {
  getActivities,
  getDeadlines,
  getHistory,
  getPortalDocRequests,
  getProcessAlerts,
  getProcessTimeline,
} from "./api";

beforeEach(() => {
  h.chamar.mockReset();
  h.chamar.mockResolvedValue({ data: [] });
  Object.values(h.toast).forEach((f) => f.mockReset());
});

const config = () => h.chamar.mock.calls.at(-1)[0];

describe("cada leitura secundária leva skipErrorToast", () => {
  it.each([
    ["getDeadlines", () => getDeadlines("p1")],
    ["getPortalDocRequests", () => getPortalDocRequests("p1")],
    ["getProcessAlerts", () => getProcessAlerts("p1")],
    ["getHistory", () => getHistory("p1")],
    ["getProcessTimeline", () => getProcessTimeline("p1")],
    ["getActivities (de um processo)", () => getActivities("p1")],
  ])("%s", async (_nome, chamar) => {
    await chamar();
    expect(config().skipErrorToast).toBe(true);
  });

  it("os parâmetros que já levavam continuam a ir (a marca não os substitui)", async () => {
    await getDeadlines("p1");
    expect(config().params).toEqual({ process_id: "p1" });
    await getActivities("p1", 10);
    expect(config().params).toEqual({ process_id: "p1", limit: 10 });
  });

  it("as actividades SEM processo (feed global) mantêm o aviso", async () => {
    await getActivities(undefined);
    expect(config().skipErrorToast).toBeUndefined();
  });
});

describe("o interceptor real", () => {
  const erro403 = (skipErrorToast) => ({
    config: { url: "/documents/portal-requests/p1", skipErrorToast },
    response: { status: 403, data: { detail: "Sem permissão" }, headers: {} },
  });

  it("403 com skipErrorToast: sem toast, e o erro propaga", async () => {
    const e = erro403(true);
    await expect(h.erroDoInterceptor(e)).rejects.toBe(e);
    expect(h.toast.error).not.toHaveBeenCalled();
  });

  it("contraprova — 403 SEM a marca continua a avisar", async () => {
    await expect(h.erroDoInterceptor(erro403(undefined))).rejects.toBeTruthy();
    expect(h.toast.error).toHaveBeenCalledWith("Acesso Negado", expect.anything());
  });

  it("404 com skipErrorToast: sem toast", async () => {
    const e = { config: { url: "/deadlines", skipErrorToast: true }, response: { status: 404, data: {}, headers: {} } };
    await expect(h.erroDoInterceptor(e)).rejects.toBe(e);
    expect(h.toast.error).not.toHaveBeenCalled();
  });
});
