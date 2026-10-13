/**
 * «Enviar por Email» (magic link) fala por Axios com `skipErrorToast`: a falha — 400 sem remetente,
 * 502 serviço de email, 500 — é mostrada UMA vez por `mostrarFalhaDoEnvioDeEmail`, que também troca
 * o toast «retry agendado» por um de erro. Com o toast global por cima eram dois avisos.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const { post } = vi.hoisted(() => ({ post: vi.fn() }));

vi.mock("axios", () => {
  const instancia = {
    get: vi.fn(), post, put: vi.fn(), delete: vi.fn(), patch: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    defaults: { headers: { common: {} } },
  };
  return { default: { create: () => instancia, ...instancia, isCancel: () => false }, create: () => instancia };
});

import { sendMagicLinkEmail } from "./api";

beforeEach(() => {
  post.mockReset();
  post.mockResolvedValue({ data: {} });
});

describe("sendMagicLinkEmail", () => {
  it("POST ao caminho do envio, sem corpo, com skipErrorToast", async () => {
    await sendMagicLinkEmail("proc-1");

    expect(post).toHaveBeenCalledWith(
      "/processes/proc-1/generate-magic-link/send",
      null,
      { skipErrorToast: true },
    );
  });

  it("deixa o erro propagar (quem chama decide o aviso)", async () => {
    const erro = { response: { status: 500, data: { detail: "x" } } };
    post.mockRejectedValueOnce(erro);

    await expect(sendMagicLinkEmail("proc-1")).rejects.toBe(erro);
  });
});
