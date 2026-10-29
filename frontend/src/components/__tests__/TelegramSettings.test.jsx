/**
 * Cartão do Telegram nas Definições:
 * - desligado: «Ligar Telegram» pede o link de uso único e mostra «Abrir o Telegram»;
 * - ligado: um interruptor por categoria, e mudar um guarda só essa preferência;
 * - toda a comunicação passa pelo Axios (`services/api.js`), nunca `fetch` cru.
 */
import { render, screen, fireEvent } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";

vi.mock("../../services/api", () => ({
  getTelegramEstado: vi.fn(),
  ligarTelegram: vi.fn(),
  desligarTelegram: vi.fn(),
  atualizarPreferenciasTelegram: vi.fn(),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

import * as api from "../../services/api";
import TelegramSettings from "../TelegramSettings";

const ok = (data) => Promise.resolve({ data });

const CATEGORIAS = [
  { chave: "atribuicoes", label: "Processos e tarefas atribuídos a mim" },
  { chave: "chat", label: "Mensagens novas no chat" },
];

const estado = (extra = {}) => ({
  configurado: true,
  ligado: false,
  so_fora_da_app: false,
  preferencias: { atribuicoes: true, chat: true },
  categorias: CATEGORIAS,
  ...extra,
});

describe("TelegramSettings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("desligado: gera o link e mostra o botão para abrir o Telegram", async () => {
    api.getTelegramEstado.mockReturnValue(ok(estado()));
    api.ligarTelegram.mockReturnValue(ok({ ok: true, url: "https://t.me/Bot?start=abc" }));

    render(<TelegramSettings />);
    fireEvent.click(await screen.findByRole("button", { name: /ligar telegram/i }));

    const link = await screen.findByRole("link", { name: /abrir o telegram/i });
    expect(link.getAttribute("href")).toBe("https://t.me/Bot?start=abc");
    expect(api.ligarTelegram).toHaveBeenCalledTimes(1);
  });

  it("ligado: desligar uma categoria guarda só essa preferência", async () => {
    api.getTelegramEstado.mockReturnValue(ok(estado({ ligado: true })));
    api.atualizarPreferenciasTelegram.mockReturnValue(
      ok(estado({ ligado: true, preferencias: { atribuicoes: true, chat: false } })),
    );

    render(<TelegramSettings />);
    const interruptor = await screen.findByRole("switch", { name: /mensagens novas no chat/i });
    fireEvent.click(interruptor);

    expect(api.atualizarPreferenciasTelegram).toHaveBeenCalledWith({ preferencias: { chat: false } });
    expect(await screen.findByRole("button", { name: /desligar telegram/i })).toBeTruthy();
  });

  it("servidor sem bot configurado: explica em vez de oferecer o botão", async () => {
    api.getTelegramEstado.mockReturnValue(ok(estado({ configurado: false })));

    render(<TelegramSettings />);
    expect(await screen.findByText(/ainda não está configurado/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /ligar telegram/i })).toBeNull();
  });
});
