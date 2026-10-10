import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import TemaToggle from "../TemaToggle";

describe("TemaToggle", () => {
  it("em vista clara oferece ativar a noturna", () => {
    render(<TemaToggle escuro={false} onAlternar={() => {}} />);
    const botao = screen.getByRole("button", { name: "Ativar vista noturna" });
    expect(botao).toHaveAttribute("aria-pressed", "false");
  });

  it("em vista noturna oferece desativá-la", () => {
    render(<TemaToggle escuro onAlternar={() => {}} />);
    expect(screen.getByRole("button", { name: "Desativar vista noturna" })).toHaveAttribute("aria-pressed", "true");
  });

  it("clicar pede a alternância", async () => {
    const onAlternar = vi.fn();
    render(<TemaToggle escuro={false} onAlternar={onAlternar} />);
    await userEvent.click(screen.getByRole("button"));
    expect(onAlternar).toHaveBeenCalledTimes(1);
  });

  it("nunca submete um formulário em que esteja", async () => {
    let submetido = false;
    render(
      <form onSubmit={(e) => { e.preventDefault(); submetido = true; }}>
        <TemaToggle escuro={false} onAlternar={() => {}} />
      </form>,
    );
    await userEvent.click(screen.getByRole("button"));
    expect(submetido).toBe(false);
  });
});
