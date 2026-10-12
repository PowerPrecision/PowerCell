/**
 * O diálogo de confirmação com password de «Repor ao Modelo».
 *
 * O servidor é que valida; aqui prova-se que o ecrã recolhe a password, a envia, mostra
 * cada tipo de recusa no sítio e nunca deixa a password viva depois de fechar.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import ReporAoModeloDialog from "../ReporAoModeloDialog";

const erro = (status, detail) => Object.assign(new Error("x"), { response: { status, data: { detail } } });

function Pagina({ onConfirmar, onSucesso }) {
  const [aberto, setAberto] = useState(true);
  return (
    <>
      <button type="button" onClick={() => setAberto(true)}>abrir</button>
      <ReporAoModeloDialog
        open={aberto}
        onOpenChange={setAberto}
        titulo="Repor ao modelo"
        descricao={<p>Perde-se tudo.</p>}
        onConfirmar={onConfirmar}
        onSucesso={onSucesso}
      />
    </>
  );
}

const campo = () => screen.getByLabelText(/a sua password actual/i);
const confirmar = () => screen.getByRole("button", { name: /^repor ao modelo$/i });

describe("ReporAoModeloDialog", () => {
  it("o botão de confirmar só se activa com a password escrita", async () => {
    const user = userEvent.setup();
    render(<Pagina onConfirmar={vi.fn()} />);
    expect(confirmar()).toBeDisabled();
    await user.type(campo(), "x");
    expect(confirmar()).toBeEnabled();
  });

  it("o campo é de password, com autocomplete para o gestor de passwords", () => {
    render(<Pagina onConfirmar={vi.fn()} />);
    expect(campo()).toHaveAttribute("type", "password");
    expect(campo()).toHaveAttribute("autocomplete", "current-password");
  });

  it("envia a password escrita e, com sucesso, fecha e avisa", async () => {
    const user = userEvent.setup();
    const onConfirmar = vi.fn().mockResolvedValue({ data: { reposto: true } });
    const onSucesso = vi.fn();
    render(<Pagina onConfirmar={onConfirmar} onSucesso={onSucesso} />);

    await user.type(campo(), "Segredo-1!");
    await user.click(confirmar());

    await waitFor(() => expect(onSucesso).toHaveBeenCalledWith({ reposto: true }));
    expect(onConfirmar).toHaveBeenCalledTimes(1);
    expect(onConfirmar).toHaveBeenCalledWith("Segredo-1!");
    expect(screen.queryByTestId("repor-modelo-dialog")).toBeNull();
  });

  it("password errada: mostra o erro no diálogo, limpa o campo e NÃO fecha", async () => {
    const user = userEvent.setup();
    const onSucesso = vi.fn();
    render(<Pagina onConfirmar={vi.fn().mockRejectedValue(erro(403, "Password incorrecta."))} onSucesso={onSucesso} />);

    await user.type(campo(), "errada");
    await user.click(confirmar());

    const alerta = await screen.findByTestId("repor-modelo-erro");
    expect(alerta).toHaveAttribute("data-tipo", "password_errada");
    expect(alerta).toHaveTextContent("Password incorrecta.");
    expect(campo()).toHaveValue("");
    expect(confirmar()).toBeDisabled();
    expect(onSucesso).not.toHaveBeenCalled();
  });

  it("bloqueio por tentativas: diz o motivo e continua aberto", async () => {
    const user = userEvent.setup();
    render(<Pagina onConfirmar={vi.fn().mockRejectedValue(erro(429, { message: "Muitas tentativas falhadas. Tente novamente em 10 minutos." }))} />);
    await user.type(campo(), "x");
    await user.click(confirmar());
    expect(await screen.findByTestId("repor-modelo-erro")).toHaveAttribute("data-tipo", "bloqueado");
  });

  it("processos em fases que o modelo não tem: lista as fases e quantos processos", async () => {
    const user = userEvent.setup();
    render(<Pagina onConfirmar={vi.fn().mockRejectedValue(erro(409, {
      message: "Há processos em fases que o modelo não tem.",
      fases_em_uso: [{ name: "fase_custom", total: 2 }, { name: "outra", total: 1 }],
    }))} />);
    await user.type(campo(), "x");
    await user.click(confirmar());

    const lista = await screen.findByTestId("repor-modelo-fases");
    expect(lista).toHaveTextContent("fase_custom: 2 processos");
    expect(lista).toHaveTextContent("outra: 1 processo");
    expect(lista).not.toHaveTextContent("outra: 1 processos");
  });

  it("não deixa confirmar duas vezes enquanto o pedido vai a caminho", async () => {
    const user = userEvent.setup();
    let resolver;
    const onConfirmar = vi.fn(() => new Promise((r) => { resolver = r; }));
    render(<Pagina onConfirmar={onConfirmar} />);
    await user.type(campo(), "x");
    await user.click(confirmar());
    expect(confirmar()).toBeDisabled();
    await user.click(confirmar());
    // Nem um segundo envio do formulário (Enter, ou um clique que escapou ao `disabled`).
    fireEvent.submit(screen.getByTestId("repor-modelo-dialog").querySelector("form"));
    expect(onConfirmar).toHaveBeenCalledTimes(1);
    resolver({ data: {} });
  });

  it("a password não sobrevive ao diálogo: cancelar e reabrir mostra o campo vazio", async () => {
    const user = userEvent.setup();
    render(<Pagina onConfirmar={vi.fn()} />);
    await user.type(campo(), "Segredo-1!");
    await user.click(screen.getByRole("button", { name: /cancelar/i }));
    await waitFor(() => expect(screen.queryByTestId("repor-modelo-dialog")).toBeNull());
    await user.click(screen.getByRole("button", { name: /^abrir$/i }));
    expect(campo()).toHaveValue("");
  });

  it("Enter no campo confirma (é um formulário)", async () => {
    const user = userEvent.setup();
    const onConfirmar = vi.fn().mockResolvedValue({});
    render(<Pagina onConfirmar={onConfirmar} />);
    await user.type(campo(), "Segredo-1!{Enter}");
    await waitFor(() => expect(onConfirmar).toHaveBeenCalledWith("Segredo-1!"));
  });
});
