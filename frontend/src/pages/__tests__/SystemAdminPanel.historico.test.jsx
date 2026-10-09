/**
 * O separador «Registo de Histórico» existe — e só para o admin.
 *
 * Bloco 1, ponto 4. O painel (`HistoryTrackingPanel`) tem teste próprio; o
 * que este ficheiro prova é a LIGAÇÃO: um separador escrito mas inalcançável
 * (ou visível a quem não pode usá-lo) não produz erro nenhum. É a regra do
 * `SystemConfigPage.seccoes`: acrescentar um separador exige montar a PÁGINA.
 *
 * Os filhos pesados são stubs; a página, as abas e o `isAdmin` são os REAIS.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const auth = { user: { id: "u1", name: "A", role: "admin" } };
vi.mock("../../contexts/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("../../layouts/DashboardLayout", () => ({
  default: ({ children }) => <div data-testid="layout">{children}</div>,
}));
vi.mock("../../components/admin/UsersAccessAdminTab", () => ({ default: () => <div /> }));
vi.mock("../../components/admin/CompaniesAdminTab", () => ({ default: () => <div /> }));
vi.mock("../AutomationPage", () => ({ default: () => <div /> }));
vi.mock("../../components/admin/PermissionsTab", () => ({ default: () => <div /> }));
vi.mock("../../components/admin/HistoryTrackingPanel", () => ({
  default: () => <div data-testid="history-tracking-panel-stub" />,
}));

import SystemAdminPanel from "../SystemAdminPanel";

const abrirCompliance = () => {
  render(
    <MemoryRouter>
      <SystemAdminPanel />
    </MemoryRouter>,
  );
  // Radix Tabs activa no `mousedown`, não no `click`.
  const tab = screen.getAllByRole("tab").find((t) => /compliance/i.test(t.textContent));
  fireEvent.mouseDown(tab);
};

describe("SystemAdminPanel — o separador do controlo de histórico", () => {
  beforeEach(() => {
    auth.user = { id: "u1", name: "A", role: "admin" };
  });

  it("o admin vê o separador e o painel", async () => {
    abrirCompliance();

    const separador = await screen.findByRole("tab", { name: /Registo de Histórico|Histórico/ });
    fireEvent.mouseDown(separador);
    expect(await screen.findByTestId("history-tracking-panel-stub")).toBeTruthy();
  });

  it("o CEO NÃO vê o separador (master/admin; nem o CEO liga o registo de outros)", async () => {
    auth.user = { id: "u2", name: "C", role: "ceo" };
    abrirCompliance();

    await screen.findByRole("tab", { name: /Auditoria|Audit/ });
    expect(screen.queryByRole("tab", { name: /Registo de Histórico|Histórico/ })).toBeNull();
  });
});
