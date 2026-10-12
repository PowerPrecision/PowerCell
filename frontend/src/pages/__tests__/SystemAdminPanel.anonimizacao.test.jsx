/**
 * O separador «Anonimização» (Compliance) existe — para o Master, o Admin e o CEO — e o painel recebe
 * o `isMaster` certo (é ele que mostra o LOTE). O painel tem teste próprio; aqui prova-se a LIGAÇÃO:
 * um separador escrito mas inalcançável (ou visível a quem não pode usá-lo) não produz erro nenhum.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const auth = { user: { id: "u1", name: "A", role: "master" } };
vi.mock("../../contexts/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("../../layouts/DashboardLayout", () => ({
  default: ({ children }) => <div data-testid="layout">{children}</div>,
}));
vi.mock("../../components/admin/UsersAccessAdminTab", () => ({ default: () => <div /> }));
vi.mock("../../components/admin/CompaniesAdminTab", () => ({ default: () => <div /> }));
vi.mock("../AutomationPage", () => ({ default: () => <div /> }));
vi.mock("../../components/admin/PermissionsTab", () => ({ default: () => <div /> }));
vi.mock("../../components/admin/HistoryTrackingPanel", () => ({ default: () => <div /> }));
vi.mock("../../components/admin/RgpdAnonimizacaoPanel", () => ({
  default: ({ isMaster }) => <div data-testid="anonimizacao-stub" data-master={String(isMaster)} />,
}));

import SystemAdminPanel from "../SystemAdminPanel";

const abrirCompliance = () => {
  render(
    <MemoryRouter>
      <SystemAdminPanel />
    </MemoryRouter>,
  );
  // Radix Tabs activa no `mousedown`, não no `click`.
  fireEvent.mouseDown(screen.getAllByRole("tab").find((t) => /compliance/i.test(t.textContent)));
};

describe("SystemAdminPanel — o separador da anonimização RGPD", () => {
  beforeEach(() => {
    auth.user = { id: "u1", name: "A", role: "master" };
  });

  it("o Master vê o separador e o painel com isMaster=true", async () => {
    abrirCompliance();
    fireEvent.mouseDown(await screen.findByRole("tab", { name: /Anonimização|Anon\./ }));
    expect((await screen.findByTestId("anonimizacao-stub")).dataset.master).toBe("true");
  });

  it.each(["admin", "ceo"])("o %s vê o separador, mas o painel sabe que NÃO é Master (sem lote)", async (papel) => {
    auth.user = { id: "u2", name: "L", role: papel };
    abrirCompliance();
    fireEvent.mouseDown(await screen.findByRole("tab", { name: /Anonimização|Anon\./ }));
    expect((await screen.findByTestId("anonimizacao-stub")).dataset.master).toBe("false");
  });

  it.each(["diretor", "consultor", "administrativo"])("o %s não vê o separador", async (papel) => {
    auth.user = { id: "u3", name: "X", role: papel };
    abrirCompliance();
    await screen.findByRole("tab", { name: /Auditoria|Audit/ });
    expect(screen.queryByRole("tab", { name: /Anonimização|Anon\./ })).toBeNull();
  });
});
