/**
 * A vista noturna do Portal do Cliente — a página montada a sério.
 *
 * O botão tem de existir em TODOS os estados do Portal (aqui, no login: o
 * cliente ainda não entrou) e a escolha tem de chegar ao `<html>`.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../hooks/useSlidingSession", () => ({
  __esModule: true,
  default: () => ({ logout: vi.fn() }),
  useSlidingSession: () => ({ logout: vi.fn() }),
}));
vi.mock("../../utils/apiBaseUrl", () => ({
  API_BASE_URL: "http://localhost:8001",
  BACKEND_URL: "http://localhost:8001",
}));

vi.setConfig({ testTimeout: 20000 });
const raiz = () => document.documentElement;

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  raiz().classList.remove("dark", "portal-ativo");
  vi.stubGlobal("fetch", vi.fn(async () => ({
    ok: false, status: 401, json: async () => ({}), clone() { return this; }, headers: { get: () => "application/json" },
  })));
});
afterEach(() => {
  vi.unstubAllGlobals();
  raiz().classList.remove("dark", "portal-ativo");
});

async function montar() {
  const { default: ClientPortal } = await import("../ClientPortal");
  return render(<ClientPortal />);
}

describe("Portal do Cliente — vista noturna", () => {
  it("há um botão explícito no ecrã de entrada, e o Portal abre claro", async () => {
    await montar();
    expect(await screen.findByRole("button", { name: "Ativar vista noturna" })).toBeInTheDocument();
    expect(raiz().classList.contains("dark")).toBe(false);
    expect(raiz().classList.contains("portal-ativo")).toBe(true);
  });

  it("clicar liga a vista noturna no <html>, guarda-a e o botão muda de sentido", async () => {
    await montar();
    await userEvent.click(await screen.findByRole("button", { name: "Ativar vista noturna" }));
    await waitFor(() => expect(raiz().classList.contains("dark")).toBe(true));
    expect(localStorage.getItem("portal-theme")).toBe("dark");
    expect(screen.getByRole("button", { name: "Desativar vista noturna" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Desativar vista noturna" }));
    await waitFor(() => expect(raiz().classList.contains("dark")).toBe(false));
    expect(localStorage.getItem("portal-theme")).toBe("light");
  });

  it("uma escolha anterior é respeitada à entrada", async () => {
    localStorage.setItem("portal-theme", "dark");
    await montar();
    await screen.findByRole("button", { name: "Desativar vista noturna" });
    expect(raiz().classList.contains("dark")).toBe(true);
  });

  it("o tema do CRM não passa para o Portal, e é reposto ao sair", async () => {
    raiz().classList.add("dark"); // CRM em modo escuro
    const { unmount } = await montar();
    await screen.findByRole("button", { name: "Ativar vista noturna" });
    expect(raiz().classList.contains("dark")).toBe(false);
    unmount();
    expect(raiz().classList.contains("dark")).toBe(true);
  });
});
