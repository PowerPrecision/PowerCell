/**
 * «Novo» no separador Emails do processo: o «Para» leva o cliente e os intermediários (Lote 7.3).
 * Monta o EmailsTab REAL (com o painel de histórico falseado) e afirma o URL que sai para o Webmail.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const navegar = vi.hoisted(() => vi.fn());
vi.mock("react-router-dom", () => ({ useNavigate: () => navegar }));
const painel = vi.hoisted(() => ({ props: null }));
vi.mock("../../../EmailHistoryPanel", () => ({ default: (props) => { painel.props = props; return null; } }));
const sessao = vi.hoisted(() => ({ papel: "consultor" }));
vi.mock("../../../../contexts/AuthContext", () => ({ useAuthOpcional: () => ({ effectiveRole: sessao.papel }) }));
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
  sessao.papel = "consultor";
  painel.props = null;
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


describe("EmailsTab — regras de 2026-11-04", () => {
  it("12a: o Index não tem «Novo» e o painel fica só de leitura", () => {
    sessao.papel = "indexacao";
    montar();
    expect(screen.queryByRole("button", { name: /novo/i })).not.toBeInTheDocument();
    expect(painel.props.somenteLeitura).toBe(true);
  });

  it("contraprova: o consultor tem «Novo» e escreve", () => {
    montar();
    expect(screen.getByRole("button", { name: /novo/i })).toBeInTheDocument();
    expect(painel.props.somenteLeitura).toBe(false);
  });

  it("10a: responder abre o compositor do Webmail com o email", () => {
    montar();
    painel.props.onReply("reply_all", { id: "e-5" });
    const url = urlDeSaida();
    expect(url.pathname).toBe("/webmail");
    expect(url.searchParams.get("compose")).toBe("reply_all");
    expect(url.searchParams.get("email_id")).toBe("e-5");
  });
});
