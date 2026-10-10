/**
 * Login do Portal com credenciais certas e processo inativo.
 *
 * O servidor devolve 403 com código — antes disto a mensagem perdia-se
 * («Erro ao fazer login») porque o `detail` é um objecto e o ramo final só
 * aceitava texto. Um 401 tem de continuar a dizer «credenciais inválidas».
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../utils/apiBaseUrl", () => ({
  API_BASE_URL: "http://localhost:8001",
  BACKEND_URL: "http://localhost:8001",
}));

const resposta = (status, corpo) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => corpo,
  headers: { get: () => "application/json" },
});

vi.setConfig({ testTimeout: 20000 });

beforeEach(() => localStorage.clear());
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function entrarCom(status, corpo) {
  vi.stubGlobal("fetch", vi.fn(async () => resposta(status, corpo)));
  const { default: ClientPortalLogin } = await import("../ClientPortalLogin");
  render(<ClientPortalLogin onLoginSuccess={vi.fn()} />);
  await userEvent.type(await screen.findByPlaceholderText("exemplo@email.com"), "joana@exemplo.pt");
  await userEvent.type(screen.getByPlaceholderText("A4B-9X2"), "ABC123");
  await userEvent.click(screen.getByRole("button", { name: /entrar|aceder|continuar/i }));
}

describe("Login do Portal", () => {
  it("processo inativo: mostra a mensagem do servidor", async () => {
    await entrarCom(403, {
      detail: { codigo: "portal_inativo", mensagem: "Processo 42 concluído: acesso encerrado." },
    });
    expect(await screen.findByText("Processo 42 concluído: acesso encerrado.")).toBeInTheDocument();
    expect(localStorage.getItem("portalToken")).toBeNull();
  });

  it("credenciais inválidas continuam a dizer-se como antes", async () => {
    await entrarCom(401, { detail: "Credenciais inválidas. Verifique o seu email e código de acesso." });
    await waitFor(() =>
      expect(screen.getByText(/credenciais inválidas/i)).toBeInTheDocument(),
    );
  });
});
