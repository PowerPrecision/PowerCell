/**
 * D-34 — num processo fechado a equipa não envia mensagens novas ao cliente.
 * O histórico continua legível; o compositor desaparece e diz porquê.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import PortalMessagesTab from "../PortalMessagesTab";

const MENSAGENS = [
  { id: "m1", sender_type: "client", sender_name: "Rui Cliente", content: "Obrigado!", created_at: "2026-10-01T10:00:00Z" },
  { id: "m2", sender_type: "staff", sender_name: "Ana", content: "De nada.", created_at: "2026-10-01T11:00:00Z" },
];

const montar = (props = {}) => render(
  <PortalMessagesTab
    messages={MENSAGENS} newMessage="" setNewMessage={vi.fn()}
    onRefresh={vi.fn()} onSend={vi.fn()} {...props}
  />,
);

describe("PortalMessagesTab — processo fechado", () => {
  it("aberto: há compositor e botão Enviar (contraprova)", () => {
    montar();
    expect(screen.getByPlaceholderText(/escreva uma mensagem para o cliente/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /enviar/i })).toBeInTheDocument();
    expect(screen.queryByTestId("mensagens-somente-leitura")).toBeNull();
  });

  it("fechado: sem compositor nem Enviar, com o motivo", () => {
    montar({ somenteLeitura: true });
    expect(screen.queryByPlaceholderText(/escreva uma mensagem/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /enviar/i })).toBeNull();
    expect(screen.getByTestId("mensagens-somente-leitura")).toHaveTextContent(/reabra o processo/i);
  });

  it("fechado: a conversa anterior continua a ler-se e o Actualizar mantém-se", () => {
    montar({ somenteLeitura: true });
    expect(screen.getByText("Obrigado!")).toBeInTheDocument();
    expect(screen.getByText("De nada.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /actualizar/i })).toBeInTheDocument();
  });

  it("fechado: nem o Enter envia (não há textarea para o disparar)", () => {
    const onSend = vi.fn();
    montar({ somenteLeitura: true, onSend, newMessage: "olá" });
    expect(onSend).not.toHaveBeenCalled();
    expect(screen.queryByRole("textbox")).toBeNull();
  });
});
