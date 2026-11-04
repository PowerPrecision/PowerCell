import { describe, expect, it } from "vitest";
import {
  DESTINOS_ANTIGOS,
  GRUPOS_DO_PAINEL,
  acessoASeccao,
  gruposVisiveis,
  podeAbrirOPainel,
  seccaoEmVigor,
  urlDoPainel,
} from "./painelAdminGrupos";

const seccao = (id) => GRUPOS_DO_PAINEL.flatMap((g) => g.seccoes).find((s) => s.id === id);
const ids = (grupos) => grupos.map((g) => g.id);

describe("painelAdminGrupos — o registo", () => {
  it("cada secção aparece num só sítio", () => {
    const todas = GRUPOS_DO_PAINEL.flatMap((g) => g.seccoes.map((s) => s.id));
    expect(new Set(todas).size).toBe(todas.length);
  });

  it("todo o destino antigo existe no registo", () => {
    for (const [tab, { grupo, seccao: s }] of Object.entries(DESTINOS_ANTIGOS)) {
      const g = GRUPOS_DO_PAINEL.find((x) => x.id === grupo);
      expect(g, tab).toBeTruthy();
      expect(g.seccoes.map((x) => x.id), tab).toContain(s);
    }
  });

  it("o Sistema inteiro é só da conta Master", () => {
    const sistema = GRUPOS_DO_PAINEL.find((g) => g.id === "sistema");
    expect(sistema.seccoes.every((s) => s.soContaMaster)).toBe(true);
  });
});

describe("painelAdminGrupos — acessos (respostas do Flavio)", () => {
  it("4b: o CEO grava Dados, Definições e Finanças; o Admin não vê nenhuma", () => {
    for (const id of ["dados", "definicoes", "financas"]) {
      expect(acessoASeccao(seccao(id), { perfil: "ceo" }), id).toBe("edita");
      expect(acessoASeccao(seccao(id), { perfil: "admin" }), id).toBeNull();
    }
  });

  it("3a: o Diretor consulta Utilizadores, Workflow e Finanças, e nada mais", () => {
    const vistas = gruposVisiveis({ perfil: "diretor" }).flatMap((g) => g.seccoes);
    expect(vistas.map((s) => s.id).sort()).toEqual(["financas", "utilizadores", "workflow"]);
    expect(vistas.every((s) => s.acesso === "consulta")).toBe(true);
  });

  it("a conta Master edita tudo, mesmo com outro perfil activo", () => {
    const vistas = gruposVisiveis({ perfil: "consultor", contaMaster: true });
    expect(ids(vistas)).toEqual(GRUPOS_DO_PAINEL.map((g) => g.id));
    expect(vistas.flatMap((g) => g.seccoes).every((s) => s.acesso === "edita")).toBe(true);
  });

  it("o perfil compara-se sem maiúsculas", () => {
    expect(acessoASeccao(seccao("workflow"), { perfil: "ADMIN" })).toBe("edita");
  });

  it("quem não é da gestão não abre o painel", () => {
    expect(podeAbrirOPainel({ perfil: "consultor" })).toBe(false);
    expect(podeAbrirOPainel({ perfil: "diretor" })).toBe(true);
  });
});

describe("painelAdminGrupos — URL", () => {
  it("um grupo ou secção desconhecidos caem no primeiro visível", () => {
    const grupos = gruposVisiveis({ perfil: "admin" });
    expect(seccaoEmVigor(grupos, "sistema", "backups").grupo.id).toBe("equipa");
    expect(seccaoEmVigor(grupos, "operacao", "nada").seccao.id).toBe("workflow");
    expect(seccaoEmVigor([], "x", "y")).toEqual({ grupo: null, seccao: null });
  });

  it("urlDoPainel monta o endereço", () => {
    expect(urlDoPainel()).toBe("/system-admin");
    expect(urlDoPainel("empresa", "dados")).toBe("/system-admin?grupo=empresa&seccao=dados");
  });
});
