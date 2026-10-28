import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const api = vi.hoisted(() => ({ obterConversaIndex: vi.fn(), enviarConversaIndex: vi.fn() }));
vi.mock("@/services/partnerApi", () => api);

import ConversaComAEquipa from "../ConversaComAEquipa";

const montar = (props = {}) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ConversaComAEquipa caseId="p1" {...props} />
    </QueryClientProvider>,
  );
};

describe("ConversaComAEquipa — o parceiro fala com o Index", () => {
  beforeEach(() => vi.clearAllMocks());

  it("mostra a mensagem da equipa e envia a resposta", async () => {
    api.obterConversaIndex.mockResolvedValue({
      interlocutor: { name: "Ana Index" },
      messages: [{ id: "m1", content: "Falta o IRS", sender_name: "Ana Index", mine: false, created_at: "2026-10-28T10:00:00Z" }],
    });
    api.enviarConversaIndex.mockResolvedValue({ success: true });
    montar();
    expect(await screen.findByText("Falta o IRS")).toBeInTheDocument();
    await userEvent.type(screen.getByTestId("conversa-texto"), "Envio amanhã");
    await userEvent.click(screen.getByTestId("conversa-enviar"));
    expect(api.enviarConversaIndex).toHaveBeenCalledWith("p1", "Envio amanhã");
  });

  it("sem mensagens e sem ninguém do Index o cartão não aparece", async () => {
    api.obterConversaIndex.mockResolvedValue({ interlocutor: null, messages: [] });
    montar();
    await vi.waitFor(() => expect(api.obterConversaIndex).toHaveBeenCalled());
    expect(screen.queryByTestId("conversa-com-a-equipa")).not.toBeInTheDocument();
  });

  it("um erro do servidor fica junto à caixa e o texto não se perde", async () => {
    api.obterConversaIndex.mockResolvedValue({ interlocutor: { name: "Ana" }, messages: [] });
    api.enviarConversaIndex.mockRejectedValue({ response: { data: { detail: "Este processo está fechado — já não aceita mensagens." } } });
    montar();
    await userEvent.type(await screen.findByTestId("conversa-texto"), "Olá");
    await userEvent.click(screen.getByTestId("conversa-enviar"));
    expect(await screen.findByRole("alert")).toHaveTextContent(/fechado/);
    expect(screen.getByTestId("conversa-texto")).toHaveValue("Olá");
  });
});
