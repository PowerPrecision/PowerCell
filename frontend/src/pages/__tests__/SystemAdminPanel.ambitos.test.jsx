/**
 * Painel de Administração — dois âmbitos (Lote 4, ponto 6).
 *
 * Monta a PÁGINA: um separador acrescentado só ao registo (ou só ao JSX) não
 * produz erro nenhum — é a regra do `SystemConfigPage.seccoes.test.jsx`.
 * Aqui afirma-se que (a) o Master tem os dois âmbitos e cada separador vive só
 * no seu; (b) quem é local NUNCA vê o âmbito global nem o seletor; (c) todos os
 * separadores desenhados estão no registo e vice-versa.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import fonteDaPagina from "../SystemAdminPanel.jsx?raw";
import { SECCOES_DO_PAINEL } from "../../utils/painelAdminAmbitos";

const auth = vi.hoisted(() => ({ user: null, activeCompanyId: null }));
vi.mock("../../contexts/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("../../layouts/DashboardLayout", () => ({
  default: ({ children }) => <div data-testid="layout">{children}</div>,
}));
vi.mock("../../components/admin/UsersAccessAdminTab", () => ({ default: () => <div data-testid="conteudo-utilizadores" /> }));
vi.mock("../../components/admin/CompaniesAdminTab", () => ({ default: () => <div /> }));
vi.mock("../AutomationPage", () => ({ default: () => <div /> }));
vi.mock("../../components/admin/PermissionsTab", () => ({ default: () => <div /> }));
vi.mock("../../components/admin/HistoryTrackingPanel", () => ({ default: () => <div /> }));
vi.mock("../../components/admin/RgpdAnonimizacaoPanel", () => ({ default: () => <div /> }));

import SystemAdminPanel from "../SystemAdminPanel";

const MASTER = {
  id: "m1", name: "M", role: "master",
  companies: [
    { company_id: "cmp-domus", company_name: "Domus", role: "master" },
    { company_id: "cmp-power", company_name: "Power", role: "master" },
  ],
};

const montar = () =>
  render(
    <MemoryRouter>
      <SystemAdminPanel />
    </MemoryRouter>,
  );

const separadores = () =>
  screen.queryAllByRole("tab").filter((t) => t.dataset.testid?.startsWith("tab-"));
const ids = () => separadores().map((t) => t.dataset.testid.replace("tab-", ""));

beforeEach(() => {
  auth.user = MASTER;
  auth.activeCompanyId = "cmp-domus";
});

describe("SystemAdminPanel — âmbitos", () => {
  it("o Master entra na EMPRESA em contexto e vê só os separadores dela", () => {
    montar();
    expect(screen.getByTestId("ambito-empresa")).toHaveAttribute("aria-selected", "true");
    expect(ids()).toEqual(
      expect.arrayContaining(["users-mgmt", "config", "empresas", "financas", "customizacao", "compliance"]),
    );
    expect(ids()).not.toContain("tecnico");
    expect(ids()).not.toContain("comunicacoes");
  });

  it("o aviso do âmbito da empresa diz QUAL é a empresa em contexto", () => {
    montar();
    expect(screen.getByTestId("aviso-do-ambito")).toHaveTextContent("Configurações da Empresa (Tenant Ativo)");
    expect(screen.getByTestId("aviso-do-ambito")).toHaveTextContent("Domus");
  });

  it("sem empresa que se consiga nomear, o aviso não inventa um nome", () => {
    auth.activeCompanyId = "cmp-que-nao-existe";
    montar();
    const aviso = screen.getByTestId("aviso-do-ambito");
    expect(aviso).not.toHaveTextContent("cmp-que-nao-existe");
    expect(aviso).toHaveTextContent(/empresa em contexto/i);
  });

  it("mudar para o SISTEMA troca os separadores e avisa que vale para todas as redes", () => {
    montar();
    fireEvent.click(screen.getByTestId("ambito-sistema"));

    expect(screen.getByTestId("ambito-sistema")).toHaveAttribute("aria-selected", "true");
    expect(ids()).toEqual(expect.arrayContaining(["comunicacoes", "tecnico"]));
    expect(ids()).not.toContain("users-mgmt");
    expect(ids()).not.toContain("compliance");
    expect(screen.getByTestId("aviso-do-ambito")).toHaveTextContent(/TODAS as empresas/i);
    expect(screen.getByTestId("aviso-do-ambito")).toHaveTextContent("Configurações Globais (Sistema)");
  });

  it("ao mudar de âmbito o separador activo passa a ser do novo âmbito (não fica o antigo órfão)", () => {
    montar();
    expect(screen.getByTestId("conteudo-utilizadores")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("ambito-sistema"));
    expect(screen.queryByTestId("conteudo-utilizadores")).not.toBeInTheDocument();
    expect(screen.getByTestId("tab-comunicacoes")).toHaveAttribute("aria-selected", "true");

    fireEvent.click(screen.getByTestId("ambito-empresa"));
    expect(screen.getByTestId("conteudo-utilizadores")).toBeInTheDocument();
  });

  it.each(["admin", "ceo"])("%s (perfil LOCAL) não vê o seletor nem nenhum separador global", (papel) => {
    auth.user = { id: "u2", name: "L", role: papel, companies: [] };
    montar();

    expect(screen.queryByTestId("seletor-de-ambito")).not.toBeInTheDocument();
    expect(screen.queryByTestId("ambito-sistema")).not.toBeInTheDocument();
    expect(ids()).not.toContain("tecnico");
    expect(ids()).not.toContain("comunicacoes");
    expect(ids()).toContain("users-mgmt");
    expect(screen.getByTestId("aviso-do-ambito")).toHaveTextContent("Configurações da Empresa (Tenant Ativo)");
  });
});

describe("SystemAdminPanel — o registo e a página concordam", () => {
  it("todo o separador desenhado está no registo, e todo o do registo está desenhado", () => {
    const desenhados = [...fonteDaPagina.matchAll(/data-testid="tab-([\w-]+)"/g)].map((m) => m[1]);
    expect(desenhados.length).toBeGreaterThan(0);
    expect([...desenhados].sort()).toEqual(Object.keys(SECCOES_DO_PAINEL).sort());
  });

  it("o Master alcança TODOS os separadores do registo, repartidos pelos dois âmbitos", () => {
    montar();
    const empresa = ids();
    fireEvent.click(screen.getByTestId("ambito-sistema"));
    const sistema = ids();
    expect([...empresa, ...sistema].sort()).toEqual(Object.keys(SECCOES_DO_PAINEL).sort());
    expect(empresa.filter((i) => sistema.includes(i))).toEqual([]);
  });
});
