import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import OpcaoAnaliseIA from "./OpcaoAnaliseIA";

describe("OpcaoAnaliseIA", () => {
  it("é uma caixa com nome acessível", () => {
    render(<OpcaoAnaliseIA marcada={false} onChange={() => {}} />);
    expect(screen.getByRole("checkbox", { name: /Incluir análise de IA/ })).not.toBeChecked();
  });

  it("reflecte o valor recebido", () => {
    render(<OpcaoAnaliseIA marcada onChange={() => {}} />);
    expect(screen.getByRole("checkbox", { name: /Incluir análise de IA/ })).toBeChecked();
  });

  it("marcar e desmarcar chama onChange com um booleano", async () => {
    const onChange = vi.fn();
    const { rerender } = render(<OpcaoAnaliseIA marcada={false} onChange={onChange} />);
    await userEvent.click(screen.getByRole("checkbox"));
    expect(onChange).toHaveBeenLastCalledWith(true);
    rerender(<OpcaoAnaliseIA marcada onChange={onChange} />);
    await userEvent.click(screen.getByRole("checkbox"));
    expect(onChange).toHaveBeenLastCalledWith(false);
  });

  it("desactivada, não muda", async () => {
    const onChange = vi.fn();
    render(<OpcaoAnaliseIA marcada={false} onChange={onChange} desactivada />);
    await userEvent.click(screen.getByRole("checkbox"));
    expect(onChange).not.toHaveBeenCalled();
  });
});
