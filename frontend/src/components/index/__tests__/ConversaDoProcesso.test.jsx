import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const api = vi.hoisted(() => ({
  getIndexConversa: vi.fn(),
  sendIndexConversa: vi.fn(),
  getProcessConversaIndex: vi.fn(),
  sendProcessConversaIndex: vi.fn(),
}));
vi.mock("../../../services/api", () => api);
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { toast } from "sonner";
import { ConversaDoProcesso } from "../ConversaDoProcesso";

const montar = (props) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ConversaDoProcesso processoId="p1" {...props} />
    </QueryClientProvider>,
  );
};

const MSG = {
  id: "m1", sender_name: "Rui Intermediário", content: "Já carreguei o recibo", created_at: "2026-10-28T10:00:00Z", mine: false,
};

describe("ConversaDoProcesso — Index ↔ quem carregou", () => {
  beforeEach(() => vi.clearAllMocks());

  it("na bancada mostra com quem se fala e as mensagens", async () => {
    api.getIndexConversa.mockResolvedValue({ data: { interlocutor: { id: "u1", name: "Rui Intermediário" }, messages: [MSG] } });
    montar({ lado: "index" });
    expect(await screen.findByText("Já carreguei o recibo")).toBeInTheDocument();
    expect(screen.getByTestId("conversa-interlocutor")).toHaveTextContent("Rui Intermediário");
  });

  it("Enter envia a mensagem a quem carregou e limpa o campo", async () => {
    api.getIndexConversa.mockResolvedValue({ data: { interlocutor: { id: "u1", name: "Rui" }, messages: [] } });
    api.sendIndexConversa.mockResolvedValue({ data: { success: true } });
    montar({ lado: "index" });
    const campo = await screen.findByTestId("conversa-texto");
    await userEvent.type(campo, "Falta o IRS{Enter}");
    expect(api.sendIndexConversa).toHaveBeenCalledWith("p1", "Falta o IRS");
    expect(await screen.findByDisplayValue("")).toBe(campo);
  });

  it("no processo responde ao Index pelo outro endpoint", async () => {
    api.getProcessConversaIndex.mockResolvedValue({ data: { interlocutor: { id: "u2", name: "Ana Index" }, messages: [] } });
    api.sendProcessConversaIndex.mockResolvedValue({ data: { success: true } });
    montar({ lado: "processo" });
    await userEvent.type(await screen.findByTestId("conversa-texto"), "Já está");
    await userEvent.click(screen.getByTestId("conversa-enviar"));
    expect(api.sendProcessConversaIndex).toHaveBeenCalledWith("p1", "Já está");
    expect(api.sendIndexConversa).not.toHaveBeenCalled();
  });

  it("sem interlocutor explica porquê e não deixa escrever", async () => {
    api.getProcessConversaIndex.mockResolvedValue({ data: { interlocutor: null, messages: [] } });
    montar({ lado: "processo" });
    expect(await screen.findByText(/ainda não tem ninguém do Index/i)).toBeInTheDocument();
    expect(screen.queryByTestId("conversa-texto")).not.toBeInTheDocument();
  });

  it("um erro de validação vira texto no toast (nunca um objecto)", async () => {
    api.getIndexConversa.mockResolvedValue({ data: { interlocutor: { id: "u1", name: "Rui" }, messages: [] } });
    api.sendIndexConversa.mockRejectedValue({ response: { data: { detail: [{ msg: "Texto demasiado longo" }] } } });
    montar({ lado: "index" });
    await userEvent.type(await screen.findByTestId("conversa-texto"), "x{Enter}");
    await vi.waitFor(() => expect(toast.error).toHaveBeenCalledWith("Texto demasiado longo"));
  });
});

describe("ConversaDoProcesso — quando foi um parceiro a carregar", () => {
  it("identifica o parceiro e explica que ele responde no portal", async () => {
    api.getIndexConversa.mockResolvedValue({
      data: { interlocutor: { id: "pt-1", name: "Rui", tipo: "parceiro" }, messages: [] },
    });
    montar({ lado: "index" });
    expect(await screen.findByTestId("conversa-interlocutor")).toHaveTextContent("Rui (Parceiro)");
    expect(screen.getByText(/Portal do Parceiro/)).toBeInTheDocument();
  });
});
