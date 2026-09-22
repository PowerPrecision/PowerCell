/**
 * Teste do diálogo de pedido de consentimento RGPD (Épico 8, Eixo 1).
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import RGPDRequestDialog from "../RGPDRequestDialog";

const props = (overrides = {}) => ({
  open: true,
  onOpenChange: vi.fn(),
  clientName: "Ana Martins",
  clientEmail: "ana@exemplo.pt",
  message: "",
  onMessageChange: vi.fn(),
  onConfirm: vi.fn(),
  sending: false,
  ...overrides,
});

describe("RGPDRequestDialog", () => {
  it("fechado não rende nada", () => {
    render(<RGPDRequestDialog {...props({ open: false })} />);

    expect(screen.queryByText("Solicitar Consentimento RGPD")).not.toBeInTheDocument();
  });

  it("diz a quem e para que endereço vai o pedido", () => {
    // O consultor tem de poder confirmar o destinatário antes de enviar:
    // um pedido RGPD para o email errado expõe dados a terceiros.
    render(<RGPDRequestDialog {...props()} />);

    expect(screen.getByText("Ana Martins")).toBeInTheDocument();
    expect(screen.getByText(/ana@exemplo\.pt/)).toBeInTheDocument();
  });

  it("um cliente sem email não mostra 'undefined'", () => {
    render(<RGPDRequestDialog {...props({ clientEmail: null })} />);

    expect(screen.queryByText(/undefined/)).not.toBeInTheDocument();
  });

  it("escrever a mensagem avisa o contentor", async () => {
    const utilizador = userEvent.setup();
    const onMessageChange = vi.fn();
    render(<RGPDRequestDialog {...props({ onMessageChange })} />);

    await utilizador.type(screen.getByLabelText(/Mensagem personalizada/), "Olá");

    expect(onMessageChange).toHaveBeenCalled();
  });

  it("o texto mostrado vem das props, não de estado interno", () => {
    render(<RGPDRequestDialog {...props({ message: "Mensagem gravada" })} />);

    expect(screen.getByDisplayValue("Mensagem gravada")).toBeInTheDocument();
  });

  it("Solicitar chama o contentor", async () => {
    const utilizador = userEvent.setup();
    const onConfirm = vi.fn();
    render(<RGPDRequestDialog {...props({ onConfirm })} />);

    await utilizador.click(screen.getByRole("button", { name: /Solicitar RGPD/ }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("a enviar, o botão bloqueia", () => {
    // Sem isto, dois cliques mandam dois pedidos ao mesmo cliente.
    render(<RGPDRequestDialog {...props({ sending: true })} />);

    expect(screen.getByRole("button", { name: /Solicitar RGPD/ })).toBeDisabled();
  });

  it("Cancelar fecha sem enviar", async () => {
    const utilizador = userEvent.setup();
    const onOpenChange = vi.fn();
    const onConfirm = vi.fn();
    render(<RGPDRequestDialog {...props({ onOpenChange, onConfirm })} />);

    await utilizador.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
