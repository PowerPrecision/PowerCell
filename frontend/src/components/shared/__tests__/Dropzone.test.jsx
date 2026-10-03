import React from "react";
import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import Dropzone from "../Dropzone";

const ACCEPT = ".pdf,.jpg,.png";

const ficheiro = (name) => new File(["x"], name, { type: "application/octet-stream" });

const dtDeFicheiros = (...nomes) => ({
  types: ["Files"],
  files: nomes.map(ficheiro),
  dropEffect: "",
});

const dtInterno = () => ({ types: ["text/plain"], files: [], dropEffect: "" });

const montar = (props = {}) =>
  render(
    <Dropzone accept={ACCEPT} {...props}>
      <button type="button">Submeter</button>
    </Dropzone>
  );

describe("Dropzone", () => {
  it("entrega os ficheiros largados", () => {
    const onFicheiros = vi.fn();
    montar({ onFicheiros });
    const zona = screen.getByTestId("dropzone");
    fireEvent.drop(zona, { dataTransfer: dtDeFicheiros("irs.pdf") });
    expect(onFicheiros).toHaveBeenCalledTimes(1);
    expect(onFicheiros.mock.calls[0][0].map((f) => f.name)).toEqual(["irs.pdf"]);
  });

  it("realça durante o arrasto e apaga no drop", () => {
    montar();
    const zona = screen.getByTestId("dropzone");
    fireEvent.dragEnter(zona, { dataTransfer: dtDeFicheiros("a.pdf") });
    expect(zona).toHaveAttribute("data-arrasto-activo", "true");
    expect(screen.getByText(/largue os ficheiros/i)).toBeInTheDocument();
    fireEvent.drop(zona, { dataTransfer: dtDeFicheiros("a.pdf") });
    expect(zona).toHaveAttribute("data-arrasto-activo", "false");
  });

  it("passar sobre o CONTEÚDO não apaga o realce", () => {
    montar();
    const zona = screen.getByTestId("dropzone");
    const filho = screen.getByRole("button", { name: "Submeter" });
    fireEvent.dragEnter(zona, { dataTransfer: dtDeFicheiros("a.pdf") });
    fireEvent.dragEnter(filho, { dataTransfer: dtDeFicheiros("a.pdf") });
    fireEvent.dragLeave(filho, { dataTransfer: dtDeFicheiros("a.pdf") });
    expect(zona).toHaveAttribute("data-arrasto-activo", "true");
    fireEvent.dragLeave(zona, { dataTransfer: dtDeFicheiros("a.pdf") });
    expect(zona).toHaveAttribute("data-arrasto-activo", "false");
  });

  it("IGNORA o arrasto interno — é o mover entre categorias", () => {
    const onFicheiros = vi.fn();
    montar({ onFicheiros });
    const zona = screen.getByTestId("dropzone");
    fireEvent.dragEnter(zona, { dataTransfer: dtInterno() });
    expect(zona).toHaveAttribute("data-arrasto-activo", "false");
    fireEvent.drop(zona, { dataTransfer: dtInterno() });
    expect(onFicheiros).not.toHaveBeenCalled();
  });

  it("recusa o que o botão também recusaria, e diz QUAL", () => {
    const onFicheiros = vi.fn();
    const onRecusados = vi.fn();
    montar({ onFicheiros, onRecusados });
    fireEvent.drop(screen.getByTestId("dropzone"), {
      dataTransfer: dtDeFicheiros("irs.pdf", "virus.exe"),
    });
    expect(onFicheiros.mock.calls[0][0].map((f) => f.name)).toEqual(["irs.pdf"]);
    expect(onRecusados).toHaveBeenCalledTimes(1);
    expect(onRecusados.mock.calls[0][1]).toContain("virus.exe");
  });

  it("um largar só com ficheiros recusados não chama onFicheiros", () => {
    const onFicheiros = vi.fn();
    const onRecusados = vi.fn();
    montar({ onFicheiros, onRecusados });
    fireEvent.drop(screen.getByTestId("dropzone"), {
      dataTransfer: dtDeFicheiros("virus.exe"),
    });
    expect(onFicheiros).not.toHaveBeenCalled();
    expect(onRecusados).toHaveBeenCalled();
  });

  it("desactivada não reage", () => {
    const onFicheiros = vi.fn();
    montar({ onFicheiros, disabled: true });
    const zona = screen.getByTestId("dropzone");
    fireEvent.dragEnter(zona, { dataTransfer: dtDeFicheiros("a.pdf") });
    expect(zona).toHaveAttribute("data-arrasto-activo", "false");
    fireEvent.drop(zona, { dataTransfer: dtDeFicheiros("a.pdf") });
    expect(onFicheiros).not.toHaveBeenCalled();
  });

  it("o conteúdo continua lá — a zona embrulha, não substitui", () => {
    montar();
    expect(screen.getByRole("button", { name: "Submeter" })).toBeInTheDocument();
  });

  it("a zona NÃO é um alvo de tabulação", () => {
    // O botão é o caminho acessível por teclado; duplicar o alvo só faz ruído
    // para quem usa leitor de ecrã.
    montar();
    expect(screen.getByTestId("dropzone")).not.toHaveAttribute("tabindex");
  });

  it("o dragover marca `copy` — sem isso o browser abre o ficheiro", () => {
    montar();
    const dt = dtDeFicheiros("a.pdf");
    fireEvent.dragOver(screen.getByTestId("dropzone"), { dataTransfer: dt });
    expect(dt.dropEffect).toBe("copy");
  });
});

describe("a ordem dos avisos num largar MISTO", () => {
  it("entrega os aceites ANTES de reportar os recusados", () => {
    // Ao contrário, um largar misto apagava o aviso: quem trata os aceites
    // costuma limpar o estado do envio anterior, e esse "limpar" apagava a
    // recusa acabada de escrever.
    const ordem = [];
    render(
      <Dropzone
        accept=".pdf"
        onFicheiros={() => ordem.push("aceites")}
        onRecusados={() => ordem.push("recusados")}
      >
        <span>conteúdo</span>
      </Dropzone>
    );
    fireEvent.drop(screen.getByTestId("dropzone"), {
      dataTransfer: dtDeFicheiros("irs.pdf", "virus.exe"),
    });
    expect(ordem).toEqual(["aceites", "recusados"]);
  });
});
