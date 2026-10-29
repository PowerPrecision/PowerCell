/**
 * Avisos do mesmo processo juntos: o servidor reenvia o MESMO id com `agrupada: true`.
 * O sino não conta outra vez nem mostra outro toast — é o que tira o ruído da rajada.
 */
import { render, screen, act, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const getNotifications = vi.fn();
const toastInfo = vi.fn();
let handlers = {};

vi.mock("../../services/api", () => ({
  getNotifications: (...args) => getNotifications(...args),
  markNotificationRead: vi.fn().mockResolvedValue({ data: {} }),
}));

vi.mock("../../hooks/useWebSocket", () => ({
  useWebSocket: (opcoes) => {
    if (opcoes?.onNotification) handlers = opcoes;
    return { isConnected: true };
  },
  WSEventType: {},
}));

vi.mock("../../utils/notificationSound", () => ({ playNotificationBeep: vi.fn() }));
vi.mock("sonner", () => ({ toast: { info: (...a) => toastInfo(...a), success: vi.fn(), error: vi.fn() } }));

import NotificationsDropdown from "../NotificationsDropdown";

beforeEach(() => {
  toastInfo.mockReset();
  getNotifications.mockReset();
  getNotifications.mockResolvedValue({ data: { notifications: [], unread: 0 } });
});

describe("aviso agrupado", () => {
  it("o primeiro conta e faz toast; os agrupados não", async () => {
    render(
      <MemoryRouter>
        <NotificationsDropdown />
      </MemoryRouter>,
    );
    await waitFor(() => expect(getNotifications).toHaveBeenCalled());

    act(() => {
      handlers.onNotification({ id: "n1", message: "Processo atribuído", read: false });
    });
    expect(await screen.findByText("1")).toBeTruthy();
    expect(toastInfo).toHaveBeenCalledTimes(1);

    act(() => {
      handlers.onNotification({ id: "n1", message: "3 novidades no processo nº 12", read: false, agrupada: true });
      handlers.onNotification({ id: "n1", message: "4 novidades no processo nº 12", read: false, agrupada: true });
    });
    expect(screen.getByText("1")).toBeTruthy();
    expect(screen.queryByText("3")).toBeNull();
    expect(toastInfo).toHaveBeenCalledTimes(1);
  });
});
