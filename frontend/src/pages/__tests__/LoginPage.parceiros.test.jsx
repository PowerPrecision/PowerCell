/**
 * Atalho «Acesso a Parceiros» no login do CRM (Lote 4, Out 2026).
 *
 * O Portal do Parceiro tem sessão e login próprios (`/parceiro/entrar`). Quem chegava ao endereço
 * principal não tinha por onde entrar. O atalho existe, aponta para o sítio certo e NÃO é um
 * segundo formulário de login (o do CRM continua só um).
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ login: vi.fn(), user: null }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

import LoginPage from "../LoginPage";

function montar() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/parceiro/entrar" element={<div>login do parceiro</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("LoginPage — Acesso a Parceiros", () => {
  it("há um atalho para o login do Portal do Parceiro", () => {
    montar();
    const atalho = screen.getByRole("link", { name: /Acesso a Parceiros/i });
    expect(atalho).toHaveAttribute("href", "/parceiro/entrar");
  });

  it("continua a haver UM só formulário de login (o atalho não é outro)", () => {
    montar();
    expect(screen.getAllByTestId("login-submit-btn")).toHaveLength(1);
    expect(screen.getAllByTestId("login-email-input")).toHaveLength(1);
  });
});
