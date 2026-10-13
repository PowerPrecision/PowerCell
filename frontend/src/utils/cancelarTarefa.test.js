import { describe, expect, it } from "vitest";

import {
  descreverRecusaDoCancelamento,
  MOTIVO_FALHA_DO_SERVIDOR,
  MOTIVO_SEM_PERMISSAO,
  MOTIVO_TAREFA_INEXISTENTE,
  MOTIVO_TAREFA_TERMINADA,
  TITULO_RECUSA,
} from "./cancelarTarefa";

const erro = (status, data) => ({ response: { status, data } });

describe("descreverRecusaDoCancelamento", () => {
  it("400 mostra o MOTIVO do servidor e manda ressincronizar a lista", () => {
    const r = descreverRecusaDoCancelamento(
      erro(400, { detail: "Apenas tarefas pendentes/em execução podem ser canceladas" }),
    );
    expect(r).toEqual({
      mostrar: true,
      titulo: TITULO_RECUSA,
      motivo: "Apenas tarefas pendentes/em execução podem ser canceladas",
      ressincronizar: true,
    });
  });

  it("400 sem detalhe usa o motivo por omissão (nunca um toast vazio)", () => {
    for (const data of [undefined, {}, { detail: "" }, { detail: null }]) {
      const r = descreverRecusaDoCancelamento(erro(400, data));
      expect(r.motivo).toBe(MOTIVO_TAREFA_TERMINADA);
      expect(r.ressincronizar).toBe(true);
    }
  });

  it("400 com detalhe estruturado vira texto (React #31)", () => {
    const r = descreverRecusaDoCancelamento(erro(400, { detail: [{ msg: "a" }, { msg: "b" }] }));
    expect(typeof r.motivo).toBe("string");
    expect(r.motivo).toBe("a • b");
  });

  it("404: o interceptor não avisa, por isso avisa-se aqui; e ressincroniza", () => {
    const r = descreverRecusaDoCancelamento(erro(404, { detail: "Tarefa não encontrada" }));
    expect(r.mostrar).toBe(true);
    expect(r.motivo).toBe(MOTIVO_TAREFA_INEXISTENTE);
    expect(r.ressincronizar).toBe(true);
  });

  it("403 diz que falta permissão e NÃO ressincroniza (a tarefa continua activa)", () => {
    const r = descreverRecusaDoCancelamento(erro(403, {}));
    expect(r.motivo).toBe(MOTIVO_SEM_PERMISSAO);
    expect(r.ressincronizar).toBe(false);
  });

  it("5xx diz que o servidor falhou, sem expor o detalhe técnico, e não ressincroniza", () => {
    const r = descreverRecusaDoCancelamento(erro(500, { detail: "Traceback (most recent…" }));
    expect(r.motivo).toBe(MOTIVO_FALHA_DO_SERVIDOR);
    expect(r.ressincronizar).toBe(false);
  });

  it("sem resposta (rede) não mostra: o interceptor já avisou «Erro de Conexão»", () => {
    expect(descreverRecusaDoCancelamento({ message: "Network Error" }).mostrar).toBe(false);
    expect(descreverRecusaDoCancelamento(undefined).mostrar).toBe(false);
  });
});
