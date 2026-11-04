/**
 * «Administração» — o painel único em cinco grupos (revisão do Flavio, Nov 2026).
 *
 * Monta a PÁGINA com o registo real (`painelAdminGrupos.js`): prova-se a LIGAÇÃO
 * entre o registo, o perfil efectivo, o URL e o conteúdo de cada secção. As folhas
 * pesadas são substituídas por marcadores que dizem que props receberam.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const auth = {
  user: { id: "u1", name: "A", role: "master" },
  effectiveRole: "master",
  activeCompanyId: null,
};
vi.mock("../../contexts/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("../../layouts/DashboardLayout", () => ({
  default: ({ children }) => <div data-testid="layout">{children}</div>,
}));

const { marcador } = vi.hoisted(() => ({
  marcador: (nome) => ({
    default: (props) => (
      <div
        data-testid={`conteudo-${nome}`}
        data-master={String(props.isMaster)}
        data-so-leitura={String(Boolean(props.soLeitura))}
        data-ambito={props.ambito || ""}
      />
    ),
  }),
}));
vi.mock("../../components/admin/UsersAccessAdminTab", () => marcador("utilizadores"));
vi.mock("../../components/admin/CompaniesAdminTab", () => marcador("dados"));
vi.mock("../../components/admin/PartnersAdminTab", () => marcador("parceiros"));
vi.mock("../../components/admin/PermissionsTab", () => marcador("permissoes"));
vi.mock("../../components/admin/HistoryTrackingPanel", () => marcador("historico"));
vi.mock("../../components/admin/RgpdAnonimizacaoPanel", () => marcador("anonimizacao"));
vi.mock("../../components/admin/WorkflowSoLeitura", () => marcador("workflow-so-leitura"));
vi.mock("../../components/admin/FinanceTab", () => marcador("financas"));
vi.mock("../AutomationPage", () => marcador("automacoes"));
vi.mock("../SystemConfigPage", () => marcador("config"));
vi.mock("../WorkflowStatusesPage", () => marcador("workflow"));
vi.mock("../FormManagementPage", () => marcador("formulario"));
vi.mock("../EmailAccountsPage", () => marcador("contas-email"));
vi.mock("../NotificationSettingsPage", () => marcador("notificacoes"));
vi.mock("../RGPDAdminPage", () => marcador("rgpd"));
vi.mock("../AuditTrailPage", () => marcador("auditoria"));
vi.mock("../BackupsPage", () => marcador("backups"));
vi.mock("../UnifiedLogsPage", () => marcador("logs"));
vi.mock("../DiagnosticsPage", () => marcador("diagnosticos"));
vi.mock("../AIConfigPage", () => marcador("ia"));
vi.mock("../BackgroundJobsPage", () => marcador("processos-bg"));

import SystemAdminPanel from "../SystemAdminPanel";

let ultimaPesquisa = "";
function EspiaDoUrl() {
  ultimaPesquisa = useLocation().search;
  return null;
}

const montar = (url = "/system-admin") =>
  render(
    <MemoryRouter initialEntries={[url]}>
      <SystemAdminPanel />
      <EspiaDoUrl />
    </MemoryRouter>,
  );

const comPerfil = (perfil, { conta = perfil } = {}) => {
  auth.user = { id: "u", name: "X", role: conta };
  auth.effectiveRole = perfil;
};

const gruposDesenhados = () =>
  [...screen.getByTestId("grupos-do-painel").querySelectorAll("button")].map((b) =>
    b.dataset.testid.replace("grupo-", ""),
  );

const seccoesDesenhadas = () => screen.getAllByRole("tab").map((t) => t.dataset.testid.replace("seccao-", ""));

beforeEach(() => {
  comPerfil("master");
  auth.activeCompanyId = null;
  ultimaPesquisa = "";
});

describe("Administração — quem vê que grupos", () => {
  it("o Master vê os cinco grupos, pela ordem do registo", () => {
    montar();
    expect(gruposDesenhados()).toEqual(["equipa", "empresa", "operacao", "conformidade", "sistema"]);
  });

  it("o CEO gere tudo da empresa, mas não vê o Sistema (4b)", () => {
    comPerfil("ceo");
    montar();
    expect(gruposDesenhados()).toEqual(["equipa", "empresa", "operacao", "conformidade"]);
  });

  it("o Admin vê Equipa, Operação e Conformidade — sem «A empresa» (4b)", () => {
    comPerfil("admin");
    montar();
    expect(gruposDesenhados()).toEqual(["equipa", "operacao", "conformidade"]);
  });

  it("o Diretor só consulta Utilizadores, Finanças e Workflow (3a)", async () => {
    comPerfil("diretor");
    montar("/system-admin?grupo=empresa");
    expect(gruposDesenhados()).toEqual(["equipa", "empresa", "operacao"]);
    expect(seccoesDesenhadas()).toEqual(["financas"]);
    expect(screen.getByTestId("aviso-so-consulta")).toBeInTheDocument();
    expect((await screen.findByTestId("conteudo-financas")).dataset.soLeitura).toBe("true");
  });

  it("no Workflow o Diretor recebe a lista só de leitura, não o editor", async () => {
    comPerfil("diretor");
    montar("/system-admin?grupo=operacao&seccao=workflow");
    expect(await screen.findByTestId("conteudo-workflow-so-leitura")).toBeInTheDocument();
    expect(screen.queryByTestId("conteudo-workflow")).toBeNull();
  });

  it.each(["consultor", "administrativo", "intermediario"])("o %s não tem nada para configurar", (perfil) => {
    comPerfil(perfil);
    montar();
    expect(screen.getByTestId("painel-sem-acesso")).toBeInTheDocument();
    expect(screen.queryByTestId("grupos-do-painel")).toBeNull();
  });

  it("decide pelo perfil EFECTIVO: um CEO a trabalhar como consultor não vê o painel", () => {
    comPerfil("consultor", { conta: "ceo" });
    montar();
    expect(screen.getByTestId("painel-sem-acesso")).toBeInTheDocument();
  });

  it("a CONTA Master vê tudo, qualquer que seja o perfil activo", () => {
    comPerfil("consultor", { conta: "master" });
    montar();
    expect(gruposDesenhados()).toContain("sistema");
  });
});

describe("Administração — secções e conteúdo", () => {
  it("o grupo e a secção vêm do URL e o conteúdo é o da secção", async () => {
    montar("/system-admin?grupo=sistema&seccao=backups");
    expect(screen.getByTestId("grupo-sistema")).toHaveAttribute("aria-current", "page");
    expect(await screen.findByTestId("conteudo-backups")).toBeInTheDocument();
  });

  it("escolher outro grupo grava-o no URL e abre a primeira secção dele", async () => {
    montar();
    fireEvent.click(screen.getByTestId("grupo-conformidade"));
    expect(ultimaPesquisa).toContain("grupo=conformidade");
    expect(await screen.findByTestId("conteudo-rgpd")).toBeInTheDocument();
  });

  it("A empresa › Definições e Sistema › Configuração global são âmbitos diferentes da mesma página", async () => {
    const { unmount } = montar("/system-admin?grupo=empresa&seccao=definicoes");
    expect((await screen.findByTestId("conteudo-config")).dataset.ambito).toBe("empresa");
    unmount();
    montar("/system-admin?grupo=sistema&seccao=configuracao");
    expect((await screen.findByTestId("conteudo-config")).dataset.ambito).toBe("sistema");
  });

  it("a Anonimização recebe o isMaster certo (o lote é só do Master)", async () => {
    montar("/system-admin?grupo=conformidade&seccao=anonimizacao");
    expect((await screen.findByTestId("conteudo-anonimizacao")).dataset.master).toBe("true");
  });

  it.each(["admin", "ceo"])("o %s vê a Anonimização, mas sem ser Master", async (perfil) => {
    comPerfil(perfil);
    montar("/system-admin?grupo=conformidade&seccao=anonimizacao");
    expect((await screen.findByTestId("conteudo-anonimizacao")).dataset.master).toBe("false");
  });

  it.each(["admin", "ceo"])("o Registo de histórico é só do Master: o %s não o vê", (perfil) => {
    comPerfil(perfil);
    montar("/system-admin?grupo=conformidade");
    expect(seccoesDesenhadas()).not.toContain("historico");
  });

  it("uma secção que o perfil não vê (link partilhado) cai na primeira do grupo", () => {
    comPerfil("admin");
    montar("/system-admin?grupo=sistema&seccao=backups");
    expect(gruposDesenhados()).not.toContain("sistema");
    expect(screen.getByTestId("grupo-equipa")).toHaveAttribute("aria-current", "page");
  });

  it("links antigos (`?tab=`) são traduzidos para o sítio novo", async () => {
    montar("/system-admin?tab=comunicacoes");
    expect(await screen.findByTestId("conteudo-contas-email")).toBeInTheDocument();
    expect(ultimaPesquisa).toContain("grupo=sistema");
    expect(ultimaPesquisa).not.toContain("tab=");
  });

  it("o grupo Sistema avisa que vale para todas as empresas", () => {
    montar("/system-admin?grupo=sistema");
    expect(screen.getByTestId("descricao-do-grupo")).toHaveTextContent(/TODAS as empresas/);
  });
});
