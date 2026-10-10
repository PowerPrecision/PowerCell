import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import PasswordInput from "../PasswordInput";

function Campo(props) {
  const [valor, setValor] = useState("");
  return (
    <>
      <label htmlFor="pw">Palavra-passe</label>
      <PasswordInput id="pw" value={valor} onChange={(e) => setValor(e.target.value)} {...props} />
    </>
  );
}

describe("PasswordInput", () => {
  it("começa oculta: o campo é do tipo password", () => {
    render(<Campo />);
    expect(screen.getByLabelText("Palavra-passe")).toHaveAttribute("type", "password");
  });

  it("o rótulo continua a associar-se ao CAMPO e não ao botão", () => {
    render(<Campo />);
    expect(screen.getByLabelText("Palavra-passe").tagName).toBe("INPUT");
  });

  it("o olho mostra a palavra-passe e volta a ocultá-la", async () => {
    render(<Campo />);
    const campo = screen.getByLabelText("Palavra-passe");
    await userEvent.type(campo, "Segredo#2026");

    await userEvent.click(screen.getByRole("button", { name: "Mostrar palavra-passe" }));
    expect(campo).toHaveAttribute("type", "text");
    expect(campo).toHaveValue("Segredo#2026"); // o que se escreveu não se perde ao alternar

    await userEvent.click(screen.getByRole("button", { name: "Ocultar palavra-passe" }));
    expect(campo).toHaveAttribute("type", "password");
  });

  it("o botão diz o estado (aria-pressed) e nunca submete o formulário", async () => {
    let submetido = false;
    render(
      <form onSubmit={(e) => { e.preventDefault(); submetido = true; }}>
        <Campo />
      </form>,
    );
    const botao = screen.getByRole("button", { name: "Mostrar palavra-passe" });
    expect(botao).toHaveAttribute("aria-pressed", "false");
    expect(botao).toHaveAttribute("type", "button");
    await userEvent.click(botao);
    expect(submetido).toBe(false);
    expect(screen.getByRole("button", { name: "Ocultar palavra-passe" })).toHaveAttribute("aria-pressed", "true");
  });

  it("alcança-se pelo teclado", async () => {
    render(<Campo />);
    await userEvent.tab();
    expect(screen.getByLabelText("Palavra-passe")).toHaveFocus();
    await userEvent.tab();
    expect(screen.getByRole("button", { name: "Mostrar palavra-passe" })).toHaveFocus();
  });

  it("desactivado, o olho também fica desactivado", () => {
    render(<Campo disabled />);
    expect(screen.getByLabelText("Palavra-passe")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Mostrar palavra-passe" })).toBeDisabled();
  });

  it("repassa as props do campo (autoComplete, required…)", () => {
    render(<Campo autoComplete="current-password" required />);
    const campo = screen.getByLabelText("Palavra-passe");
    expect(campo).toHaveAttribute("autocomplete", "current-password");
    expect(campo).toBeRequired();
  });
});
