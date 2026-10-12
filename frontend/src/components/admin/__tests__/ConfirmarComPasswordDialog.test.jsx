/**
 * O diálogo GENÉRICO de confirmação com password (o «Repor ao Modelo» é um invólucro dele).
 * Os comportamentos comuns (cancelar, erro no sítio, password limpa) provam-se no teste do
 * invólucro; aqui provam-se as peças que o genérico acrescenta: textos, ícone e testids por omissão.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import ConfirmarComPasswordDialog from "../ConfirmarComPasswordDialog";

const erro = (status, detail) => Object.assign(new Error("x"), { response: { status, data: { detail } } });

describe("ConfirmarComPasswordDialog", () => {
  it("por omissão: botão «Confirmar» e testids confirmar-password-*", async () => {
    const user = userEvent.setup();
    const onConfirmar = vi.fn().mockResolvedValue({ data: {} });
    render(
      <ConfirmarComPasswordDialog open onOpenChange={() => {}} titulo="Eliminar empresa" descricao={<p>Perde-se.</p>} onConfirmar={onConfirmar} />,
    );
    expect(screen.getByTestId("confirmar-password-dialog")).toBeTruthy();
    const botao = screen.getByRole("button", { name: /^confirmar$/i });
    expect(botao).toBeDisabled();
    await user.type(screen.getByLabelText(/a sua password actual/i), "Segredo-1!");
    await user.click(botao);
    await waitFor(() => expect(onConfirmar).toHaveBeenCalledWith("Segredo-1!"));
  });

  it("usa o rótulo e o prefixo de testids pedidos", () => {
    render(
      <ConfirmarComPasswordDialog
        open onOpenChange={() => {}} titulo="T" descricao={<p>d</p>} onConfirmar={vi.fn()}
        rotuloConfirmar="Eliminar empresa" testIdBase="eliminar-empresa"
      />,
    );
    expect(screen.getByTestId("eliminar-empresa-dialog")).toBeTruthy();
    expect(screen.getByRole("button", { name: /^eliminar empresa$/i })).toBeTruthy();
  });

  it("a leitura de erros por omissão é a genérica (403 → password errada, campo limpo)", async () => {
    const user = userEvent.setup();
    render(
      <ConfirmarComPasswordDialog
        open onOpenChange={() => {}} titulo="T" descricao={<p>d</p>}
        onConfirmar={vi.fn().mockRejectedValue(erro(403, "Password incorrecta."))}
      />,
    );
    const campo = screen.getByLabelText(/a sua password actual/i);
    await user.type(campo, "errada");
    await user.click(screen.getByRole("button", { name: /^confirmar$/i }));
    expect(await screen.findByTestId("confirmar-password-erro")).toHaveAttribute("data-tipo", "password_errada");
    expect(campo).toHaveValue("");
  });
});
