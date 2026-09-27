/**
 * O corte do polling (Épico 10, Fase 3).
 *
 * Este ficheiro monta o componente REAL e mede o que interessa: quantas
 * leituras ao servidor acontecem com o WebSocket de pé, e quantas quando
 * ele cai. Um teste sobre o módulo puro provaria a regra; só montando o
 * componente é que se prova que ela está LIGADA.
 */
import { render, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { INTERVALO_BASE_MS } from "../../utils/realtimeFallback";

const getNotifications = vi.fn();
let estadoDaLigacao = { isConnected: true };

vi.mock("../../services/api", () => ({
  getNotifications: (...args) => getNotifications(...args),
  markNotificationRead: vi.fn().mockResolvedValue({ data: {} }),
}));

vi.mock("../../hooks/useWebSocket", () => ({
  useWebSocket: () => estadoDaLigacao,
  WSEventType: {},
}));

vi.mock("../../utils/notificationSound", () => ({
  playNotificationBeep: vi.fn(),
}));

import NotificationsDropdown from "../NotificationsDropdown";

function montar() {
  return render(
    <MemoryRouter>
      <NotificationsDropdown />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  getNotifications.mockReset();
  getNotifications.mockResolvedValue({ data: { notifications: [], unread: 0 } });
  estadoDaLigacao = { isConnected: true };
});

afterEach(() => {
  vi.useRealTimers();
});

describe("polling das notificações", () => {
  it("faz a leitura inicial e depois CALA-SE enquanto o WS estiver ligado", async () => {
    montar();
    await waitFor(() => expect(getNotifications).toHaveBeenCalledTimes(1));

    // Dez minutos de silêncio: antes da Fase 3 seriam 20 pedidos.
    await vi.advanceTimersByTimeAsync(INTERVALO_BASE_MS * 20);
    expect(getNotifications).toHaveBeenCalledTimes(1);
  });

  it("volta a sondar quando o WebSocket cai", async () => {
    estadoDaLigacao = { isConnected: false };
    montar();
    await waitFor(() => expect(getNotifications).toHaveBeenCalledTimes(1));

    await vi.advanceTimersByTimeAsync(INTERVALO_BASE_MS);
    await waitFor(() => expect(getNotifications).toHaveBeenCalledTimes(2));

    await vi.advanceTimersByTimeAsync(INTERVALO_BASE_MS);
    await waitFor(() => expect(getNotifications).toHaveBeenCalledTimes(3));
  });

  it("o intervalo não foi apagado — é a rede de segurança do WS", async () => {
    // Contraprova do primeiro teste: se o polling tivesse sido REMOVIDO em
    // vez de adormecido, o teste de cima passava na mesma e ficávamos sem
    // nada quando a ligação caísse.
    const { rerender } = montar();
    await waitFor(() => expect(getNotifications).toHaveBeenCalledTimes(1));

    estadoDaLigacao = { isConnected: false };
    rerender(
      <MemoryRouter>
        <NotificationsDropdown />
      </MemoryRouter>,
    );

    await vi.advanceTimersByTimeAsync(INTERVALO_BASE_MS);
    await waitFor(() => expect(getNotifications.mock.calls.length).toBeGreaterThan(1));
  });
});

describe("recuperação na volta da ligação", () => {
  it("lê uma vez quando o WebSocket regressa depois de ter caído", async () => {
    // Os eventos emitidos com o socket em baixo perderam-se e nada os
    // repete. Sem esta leitura, o sino fica calado E desactualizado.
    estadoDaLigacao = { isConnected: false };
    const { rerender } = montar();
    await waitFor(() => expect(getNotifications).toHaveBeenCalledTimes(1));

    const antesDaVolta = getNotifications.mock.calls.length;

    estadoDaLigacao = { isConnected: true };
    rerender(
      <MemoryRouter>
        <NotificationsDropdown />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(getNotifications.mock.calls.length).toBeGreaterThan(antesDaVolta),
    );

    // E depois de recuperar, volta a calar-se.
    const depoisDaVolta = getNotifications.mock.calls.length;
    await vi.advanceTimersByTimeAsync(INTERVALO_BASE_MS * 10);
    expect(getNotifications).toHaveBeenCalledTimes(depoisDaVolta);
  });

  it("não recupera na PRIMEIRA ligação (a montagem já leu)", async () => {
    estadoDaLigacao = { isConnected: true };
    montar();
    await waitFor(() => expect(getNotifications).toHaveBeenCalledTimes(1));
    await vi.advanceTimersByTimeAsync(1000);
    expect(getNotifications).toHaveBeenCalledTimes(1);
  });
});
