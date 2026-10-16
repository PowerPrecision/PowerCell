/**
 * «Novo» no separador Emails do processo: o «Para» leva o cliente e os intermediários (Lote 7.3).
 * Monta o EmailsTab REAL (com o painel de histórico falseado) e afirma o URL que sai para o Webmail.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const navegar = vi.hoisted(() => vi.fn());
vi.mock("react-router-dom", () => ({ useNavigate: () => navegar }));
vi.mock("../../../EmailHistoryPanel", () => ({ default: () => null }));
const api = vi.hoisted(() => ({ getUsers: vi.fn() }));
vi.mock("../../../../services/api", () => api);

import EmailsTab from "../EmailsTab";

const PROCESSO = {
  client_email: "joana@exemplo.pt",
  titular2_data: { email: "tiago@exemplo.pt" },
  assigned_mediador_ids: ["m1"],
};
const montar = (process = PROCESSO) => render(
  <EmailsTab id="p-1" savedProcessRef={{ current: process }} process={process} token="t" />,
);
const urlDeSaida = () => new URL(navegar.mock.calls[0][0], "http://x");

beforeEach(() => {
  vi.clearAllMocks();
  api.getUsers.mockResolvedValue({ data: [{ id: "m1", email: "ines@precision.pt" }, { id: "x", email: "x@precision.pt" }] });
});

describe("EmailsTab — «Novo»", () => {
  it("o «Para» leva cliente, 2.º titular e intermediário atribuído; o processo vai ligado", async () => {
    montar();
    fireEvent.click(screen.getByRole("button", { name: /novo/i }));

    await waitFor(() => expect(navegar).toHaveBeenCalled());
    const url = urlDeSaida();
    expect(url.pathname).toBe("/webmail");
    expect(url.searchParams.get("compose")).toBe("new");
    expect(url.searchParams.get("process_id")).toBe("p-1");
    expect(url.searchParams.get("to")).toBe("joana@exemplo.pt, tiago@exemplo.pt, ines@precision.pt");
    expect(api.getUsers).toHaveBeenCalledWith(undefined, { processId: "p-1", skipErrorToast: true });
  });

  it("nunca se pré-seleccionam anexos nem documentos", async () => {
    montar();
    fireEvent.click(screen.getByRole("button", { name: /novo/i }));
    await waitFor(() => expect(navegar).toHaveBeenCalled());
    const chaves = [...urlDeSaida().searchParams.keys()].sort();
    expect(chaves).toEqual(["compose", "process_id", "to"]);
  });

  it("se a equipa não carrega, o email abre na mesma, só com o cliente", async () => {
    api.getUsers.mockRejectedValue({ response: { status: 500 } });
    montar();
    fireEvent.click(screen.getByRole("button", { name: /novo/i }));
    await waitFor(() => expect(navegar).toHaveBeenCalled());
    expect(urlDeSaida().searchParams.get("to")).toBe("joana@exemplo.pt, tiago@exemplo.pt");
  });

  it("processo sem nenhum email: abre o compositor sem «Para»", async () => {
    montar({ assigned_mediador_ids: [] });
    fireEvent.click(screen.getByRole("button", { name: /novo/i }));
    await waitFor(() => expect(navegar).toHaveBeenCalled());
    expect(urlDeSaida().searchParams.has("to")).toBe(false);
  });
});
