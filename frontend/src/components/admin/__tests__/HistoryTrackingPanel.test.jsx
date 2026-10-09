/**
 * Controlo de histórico — o painel montado a sério (Bloco 1, ponto 4).
 *
 * Falseia só a fronteira de rede (`services/api`). Formas REAIS dos dois
 * endpoints, e valores do fixture diferentes das omissões: os perfis
 * começam com o consultor DESLIGADO e uma pessoa com excepção.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  getHistoryTracking: vi.fn(),
  listUsersHistoryTracking: vi.fn(),
  setRoleHistoryTracking: vi.fn(),
  setUserHistoryTracking: vi.fn(),
}));
vi.mock("../../../services/api", () => api);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import HistoryTrackingPanel from "../HistoryTrackingPanel";

const PERFIS = {
  perfis: [
    { role: "diretor", enabled: true, locked: false, motivo: null },
    { role: "consultor", enabled: false, locked: false, motivo: null },
    {
      role: "indexacao",
      enabled: false,
      locked: true,
      motivo: "O perfil Indexação é sempre silencioso: as suas acções nunca geram registos.",
    },
  ],
  padrao: true,
};

const PESSOAS = {
  utilizadores: [
    { id: "u1", name: "Ana Consultora", email: "ana@x.pt", role: "consultor", is_active: true, track_history: true, efectivo: true, bloqueado: false },
    { id: "u2", name: "Rui Diretor", email: "rui@x.pt", role: "diretor", is_active: true, track_history: null, efectivo: true, bloqueado: false },
    { id: "u3", name: "Inês Indexação", email: "ines@x.pt", role: "indexacao", is_active: true, track_history: null, efectivo: false, bloqueado: true },
  ],
  total: 3,
  page: 1,
  size: 15,
};

describe("HistoryTrackingPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getHistoryTracking.mockResolvedValue({ data: PERFIS });
    api.listUsersHistoryTracking.mockResolvedValue({ data: PESSOAS });
    api.setRoleHistoryTracking.mockResolvedValue({ data: { success: true } });
    api.setUserHistoryTracking.mockResolvedValue({ data: { success: true } });
  });

  it("mostra o estado REAL de cada perfil, e não as omissões", async () => {
    render(<HistoryTrackingPanel />);

    const consultor = await screen.findByRole("switch", { name: /Consultor/ });
    expect(consultor.getAttribute("aria-checked")).toBe("false");
    expect(screen.getByRole("switch", { name: /Diretor/ }).getAttribute("aria-checked")).toBe("true");
  });

  it("a Indexação aparece BLOQUEADA, com o motivo — não escondida", async () => {
    render(<HistoryTrackingPanel />);

    const interruptor = await screen.findByRole("switch", { name: /Indexação/ });
    expect(interruptor.hasAttribute("disabled")).toBe(true);
    expect(within(screen.getByTestId("history-roles")).getByText(/sempre silencioso/i)).toBeTruthy();
  });

  it("ligar um perfil pede ao servidor e recarrega as DUAS listas", async () => {
    render(<HistoryTrackingPanel />);
    const consultor = await screen.findByRole("switch", { name: /Consultor/ });
    const perfisAntes = api.getHistoryTracking.mock.calls.length;
    const pessoasAntes = api.listUsersHistoryTracking.mock.calls.length;

    fireEvent.click(consultor);

    await waitFor(() => expect(api.setRoleHistoryTracking).toHaveBeenCalledWith("consultor", true));
    // O estado efectivo das pessoas depende do perfil.
    await waitFor(() => {
      expect(api.getHistoryTracking.mock.calls.length).toBeGreaterThan(perfisAntes);
      expect(api.listUsersHistoryTracking.mock.calls.length).toBeGreaterThan(pessoasAntes);
    });
  });

  it("mostra a excepção pessoal e o estado efectivo de cada pessoa", async () => {
    render(<HistoryTrackingPanel />);

    const ana = await screen.findByRole("combobox", { name: /Ana Consultora/ });
    expect(ana.value).toBe("ativo");
    expect(screen.getByRole("combobox", { name: /Rui Diretor/ }).value).toBe("perfil");
  });

  it("«Segue o perfil» envia null — remove o override, nunca o põe a false", async () => {
    render(<HistoryTrackingPanel />);
    const ana = await screen.findByRole("combobox", { name: /Ana Consultora/ });

    fireEvent.change(ana, { target: { value: "perfil" } });

    await waitFor(() => expect(api.setUserHistoryTracking).toHaveBeenCalledWith("u1", null));
  });

  it("«Desligado» envia false e «Sempre ativo» envia true", async () => {
    render(<HistoryTrackingPanel />);
    const rui = await screen.findByRole("combobox", { name: /Rui Diretor/ });

    fireEvent.change(rui, { target: { value: "desligado" } });
    await waitFor(() => expect(api.setUserHistoryTracking).toHaveBeenCalledWith("u2", false));

    fireEvent.change(rui, { target: { value: "ativo" } });
    await waitFor(() => expect(api.setUserHistoryTracking).toHaveBeenCalledWith("u2", true));
  });

  it("uma pessoa Indexação tem o selector desactivado", async () => {
    render(<HistoryTrackingPanel />);
    const ines = await screen.findByRole("combobox", { name: /Inês Indexação/ });
    expect(ines.hasAttribute("disabled")).toBe(true);
    expect(within(screen.getByTestId("history-users")).getByText(/Sempre silencioso/)).toBeTruthy();
  });

  it("pesquisar volta à página 1 e envia o termo", async () => {
    render(<HistoryTrackingPanel />);
    await screen.findByRole("combobox", { name: /Ana Consultora/ });

    fireEvent.change(screen.getByRole("searchbox", { name: /Pesquisar/ }), { target: { value: "rui" } });

    await waitFor(() =>
      expect(api.listUsersHistoryTracking).toHaveBeenLastCalledWith({ search: "rui", page: 1, size: 15 }),
    );
  });

  it("um erro ao carregar os perfis diz-se, em vez de mostrar uma lista vazia", async () => {
    api.getHistoryTracking.mockRejectedValue({ response: { data: { detail: "sem acesso" } } });
    render(<HistoryTrackingPanel />);

    expect(await screen.findByText(/Não foi possível carregar os perfis/)).toBeTruthy();
    expect(screen.queryByTestId("history-roles")).toBeNull();
  });
});
