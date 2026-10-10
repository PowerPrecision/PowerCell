import { describe, expect, it } from "vitest";

import { getDraftNavigationTarget } from "./draftNavigation";

describe("getDraftNavigationTarget", () => {
  it("o rascunho automático de email abre o editor no Webmail, pelo id", () => {
    // É a forma que o backend devolve em `GET /emails/auto-drafts`.
    const alvo = getDraftNavigationTarget({
      id: "auto-1", is_auto_draft: true, status: "draft", process_id: "p-1", kind: "email",
      subject: "Documento necessário: IRS",
    });
    expect(alvo).toEqual({ href: "/webmail?folder=drafts&id=auto-1", kind: "email" });
  });

  it("o rascunho de email NUNCA vai para o detalhe do processo, mesmo com process_id", () => {
    const { href } = getDraftNavigationTarget({ id: "d1", is_auto_draft: true, process_id: "p-1" });
    expect(href).not.toContain("/processo/");
  });

  it("reconhece o rascunho pelos outros sinais (pasta, tipo, assunto)", () => {
    for (const item of [
      { id: "a", folder: "drafts" },
      { id: "b", kind: "email" },
      { id: "c", status: "draft", subject: "x" },
      { id: "d", doc_type: "irs" },
    ]) {
      expect(getDraftNavigationTarget(item).kind).toBe("email");
    }
  });

  it("um rascunho de email sem id abre a pasta de rascunhos", () => {
    expect(getDraftNavigationTarget({ is_auto_draft: true }).href).toBe("/webmail?folder=drafts");
  });

  it("o id vai codificado", () => {
    expect(getDraftNavigationTarget({ id: "a b&c", is_auto_draft: true }).href).toBe(
      "/webmail?folder=drafts&id=a+b%26c",
    );
  });

  it("uma lead em pré-registo abre o registo do cliente", () => {
    expect(getDraftNavigationTarget({ id: "p1", status: "pre_registo", client_id: "c1" })).toEqual({
      href: "/registos-clientes?clientId=c1", kind: "lead",
    });
  });

  it("um processo em fase inicial abre o processo", () => {
    expect(getDraftNavigationTarget({ id: "p2", status: "fase_documental" })).toEqual({
      href: "/processo/p2", kind: "process",
    });
  });

  it("sem nada que o identifique volta à página de rascunhos", () => {
    expect(getDraftNavigationTarget(null).href).toBe("/rascunhos");
    expect(getDraftNavigationTarget({}).href).toBe("/rascunhos");
  });
});
