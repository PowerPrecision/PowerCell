/**
 * Teste do diálogo de ficheiro duplicado no upload (Épico 8, Eixo 2).
 *
 * A regra que aqui interessa: não se avança sem decisão. Avançar sem ela
 * deixaria o contentor a retomar o upload sem saber o que fazer com o
 * ficheiro — e o S3 sobrepõe por omissão.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import UploadConflictDialog from "../UploadConflictDialog";

const props = (overrides = {}) => ({
  open: true,
  conflicts: [{ original_filename: "irs_2025.pdf", category: "Financeiros" }],
  currentIndex: 0,
  resolutions: {},
  category: "Financeiros",
  onResolve: vi.fn(),
  onNext: vi.fn(),
  onCancel: vi.fn(),
  ...overrides,
});

describe("UploadConflictDialog", () => {
  it("fechado não rende nada", () => {
    render(<UploadConflictDialog {...props({ open: false })} />);

    expect(screen.queryByText("Ficheiro Duplicado Detetado")).not.toBeInTheDocument();
  });

  it("mostra o ficheiro em conflito", () => {
    render(<UploadConflictDialog {...props()} />);

    expect(screen.getByText("Ficheiro Duplicado Detetado")).toBeInTheDocument();
    expect(screen.getAllByText(/irs_2025\.pdf/).length).toBeGreaterThan(0);
  });

  it("com vários conflitos mostra o progresso", () => {
    render(
      <UploadConflictDialog
        {...props({
          conflicts: [
            { original_filename: "a.pdf", category: "Financeiros" },
            { original_filename: "b.pdf", category: "Financeiros" },
          ],
        })}
      />,
    );

    expect(screen.getByText(/Conflito 1 de 2/)).toBeInTheDocument();
  });

  it("com um só conflito não mostra progresso", () => {
    render(<UploadConflictDialog {...props()} />);

    expect(screen.queryByText(/Conflito 1 de/)).not.toBeInTheDocument();
  });

  it("escolher 'substituir' avisa o contentor", async () => {
    const utilizador = userEvent.setup();
    const onResolve = vi.fn();
    render(<UploadConflictDialog {...props({ onResolve })} />);

    await utilizador.click(screen.getByText(/Substituir/i));

    expect(onResolve).toHaveBeenCalledWith("overwrite");
  });

  it("sem decisão, avançar está bloqueado", () => {
    // O S3 sobrepõe por omissão: avançar sem decisão apagava o ficheiro
    // que já lá estava.
    render(<UploadConflictDialog {...props()} />);

    expect(screen.getByRole("button", { name: /Continuar Upload|Próximo/ })).toBeDisabled();
  });

  it("com decisão, avançar liberta", () => {
    render(
      <UploadConflictDialog {...props({ resolutions: { 0: { action: "overwrite" } } })} />,
    );

    expect(screen.getByRole("button", { name: /Continuar Upload/ })).toBeEnabled();
  });

  it("no último conflito o botão diz 'Continuar Upload'", () => {
    render(
      <UploadConflictDialog {...props({ resolutions: { 0: { action: "skip" } } })} />,
    );

    expect(screen.getByRole("button", { name: "Continuar Upload" })).toBeInTheDocument();
  });

  it("havendo mais conflitos o botão diz 'Próximo'", () => {
    render(
      <UploadConflictDialog
        {...props({
          conflicts: [
            { original_filename: "a.pdf", category: "X" },
            { original_filename: "b.pdf", category: "X" },
          ],
          resolutions: { 0: { action: "skip" } },
        })}
      />,
    );

    expect(screen.getByRole("button", { name: "Próximo" })).toBeInTheDocument();
  });

  it("Cancelar Tudo aborta o lote inteiro", async () => {
    const utilizador = userEvent.setup();
    const onCancel = vi.fn();
    const onNext = vi.fn();
    render(<UploadConflictDialog {...props({ onCancel, onNext })} />);

    await utilizador.click(screen.getByRole("button", { name: "Cancelar Tudo" }));

    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onNext).not.toHaveBeenCalled();
  });
});
