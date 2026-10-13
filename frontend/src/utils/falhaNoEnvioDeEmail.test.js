import { beforeEach, describe, expect, it, vi } from "vitest";

const aviso = vi.hoisted(() => ({ error: vi.fn() }));
vi.mock("sonner", () => ({ toast: aviso }));

import {
  ID_DO_TOAST_DE_FALHA,
  MOTIVO_GENERICO,
  MOTIVO_SEM_RESPOSTA,
  TITULO_DA_FALHA,
  _reporRegistoDeToastsDeEmail,
  descreverFalhaDoEnvioDeEmail,
  eTarefaDeEmailDeAcesso,
  esquecerToastDeEmail,
  mostrarFalhaDoEnvioDeEmail,
  registarToastDeEmail,
  substituirToastsDeEmailPorErro,
  toastDeEmailFoiSubstituido,
} from "./falhaNoEnvioDeEmail";

const erroHttp = (status, detail) => ({ response: { status, data: { detail } } });

beforeEach(() => {
  aviso.error.mockReset();
  _reporRegistoDeToastsDeEmail();
});

describe("descreverFalhaDoEnvioDeEmail", () => {
  it.each([
    [400, "A empresa não tem email configurado."],
    [502, "O serviço de email não entregou a mensagem."],
    [500, "Falha interna ao enviar o email de acesso."],
  ])("%s: o motivo do SERVIDOR vence", (status, detail) => {
    expect(descreverFalhaDoEnvioDeEmail(erroHttp(status, detail))).toEqual({
      titulo: TITULO_DA_FALHA,
      motivo: detail,
    });
  });

  it("resposta sem detalhe legível cai no motivo genérico", () => {
    expect(descreverFalhaDoEnvioDeEmail(erroHttp(500, undefined)).motivo).toBe(MOTIVO_GENERICO);
  });

  it("sem resposta (rede) diz que é a ligação", () => {
    expect(descreverFalhaDoEnvioDeEmail(new Error("Network Error")).motivo).toBe(MOTIVO_SEM_RESPOSTA);
    expect(descreverFalhaDoEnvioDeEmail(undefined).motivo).toBe(MOTIVO_SEM_RESPOSTA);
  });

  it("o detalhe em lista (validação) vira texto, não [object Object]", () => {
    const motivo = descreverFalhaDoEnvioDeEmail(
      erroHttp(422, [{ msg: "campo obrigatório" }]),
    ).motivo;
    expect(motivo).not.toContain("[object Object]");
  });
});

describe("eTarefaDeEmailDeAcesso", () => {
  it("reconhece pelo `kind` do servidor", () => {
    expect(eTarefaDeEmailDeAcesso({ kind: "portal_access_email", title: "Outro" })).toBe(true);
  });

  it("e pelo título, que é o que o evento em tempo real traz", () => {
    expect(eTarefaDeEmailDeAcesso({ title: "Email de acesso ao Portal" })).toBe(true);
  });

  it("não confunde outras tarefas", () => {
    expect(eTarefaDeEmailDeAcesso({ kind: "voice_note", title: "Nota de voz" })).toBe(false);
    expect(eTarefaDeEmailDeAcesso(undefined)).toBe(false);
  });
});

describe("substituirToastsDeEmailPorErro", () => {
  it("troca CADA toast de email em curso, com o mesmo id (substitui, não empilha)", () => {
    registarToastDeEmail("bg-task-1");
    registarToastDeEmail("bg-task-2");

    const n = substituirToastsDeEmailPorErro({ titulo: TITULO_DA_FALHA, motivo: "porque sim" });

    expect(n).toBe(2);
    expect(aviso.error).toHaveBeenCalledWith(TITULO_DA_FALHA, expect.objectContaining({
      id: "bg-task-1", description: "porque sim",
    }));
    expect(aviso.error).toHaveBeenCalledWith(TITULO_DA_FALHA, expect.objectContaining({ id: "bg-task-2" }));
    expect(toastDeEmailFoiSubstituido("bg-task-1")).toBe(true);
  });

  it("sem toasts de email devolve 0 e não mostra nada", () => {
    expect(substituirToastsDeEmailPorErro({ titulo: "t", motivo: "m" })).toBe(0);
    expect(aviso.error).not.toHaveBeenCalled();
  });

  it("depois de a tarefa terminar o id deixa de estar marcado", () => {
    registarToastDeEmail("bg-task-1");
    substituirToastsDeEmailPorErro({ titulo: "t", motivo: "m" });
    esquecerToastDeEmail("bg-task-1");

    expect(toastDeEmailFoiSubstituido("bg-task-1")).toBe(false);
  });
});

describe("mostrarFalhaDoEnvioDeEmail", () => {
  it("com um toast «a tentar» em curso, SUBSTITUI-O (um só aviso)", () => {
    registarToastDeEmail("bg-task-9");

    mostrarFalhaDoEnvioDeEmail(erroHttp(500, "Falha interna"));

    expect(aviso.error).toHaveBeenCalledTimes(1);
    expect(aviso.error).toHaveBeenCalledWith(TITULO_DA_FALHA, expect.objectContaining({
      id: "bg-task-9", description: "Falha interna",
    }));
  });

  it("sem toast em curso mostra a falha com id estável (cliques repetidos não empilham)", () => {
    mostrarFalhaDoEnvioDeEmail(erroHttp(400, "Sem remetente"));

    expect(aviso.error).toHaveBeenCalledTimes(1);
    expect(aviso.error).toHaveBeenCalledWith(TITULO_DA_FALHA, expect.objectContaining({
      id: ID_DO_TOAST_DE_FALHA, description: "Sem remetente",
    }));
  });
});
