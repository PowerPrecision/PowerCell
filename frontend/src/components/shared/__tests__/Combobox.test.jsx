import React, { useState } from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import Combobox from "../Combobox";

const OPCOES = [
  { value: "cliente:1", label: "Ana Costa", hint: "Cliente" },
  { value: "processo:2", label: "Rui Pereira", hint: "Processo" },
];

function Host({ onChange = () => {}, ...extra }) {
  const [v, setV] = useState(null);
  return (
    <Combobox
      ariaLabel="Ficha" opcoes={OPCOES} value={v}
      onChange={(x) => { setV(x); onChange(x); }} {...extra}
    />
  );
}

describe("Combobox", () => {
  it("só se escolhe uma opção da lista: o valor que sai é o da opção", async () => {
    const aoMudar = vi.fn();
    const u = userEvent.setup();
    render(<Host onChange={aoMudar} />);
    await u.click(screen.getByRole("combobox", { name: "Ficha" }));
    await u.click(await screen.findByText("Rui Pereira"));
    expect(aoMudar).toHaveBeenCalledWith("processo:2");
    expect(screen.getByRole("combobox", { name: "Ficha" })).toHaveTextContent("Rui Pereira");
  });

  it("escrever na pesquisa filtra e NUNCA cria um valor", async () => {
    const aoMudar = vi.fn();
    const u = userEvent.setup();
    render(<Host onChange={aoMudar} />);
    await u.click(screen.getByRole("combobox", { name: "Ficha" }));
    await u.type(screen.getByPlaceholderText("Pesquisar…"), "rui");
    expect(screen.queryByText("Ana Costa")).not.toBeInTheDocument();
    expect(screen.getByText("Rui Pereira")).toBeInTheDocument();
    await u.type(screen.getByPlaceholderText("Pesquisar…"), "{Enter}");
    expect(aoMudar).toHaveBeenCalledWith("processo:2");
    expect(aoMudar).not.toHaveBeenCalledWith("rui");
  });

  it("sem resultados diz-se", async () => {
    const u = userEvent.setup();
    render(<Host textoSemResultados="Nenhuma ficha." />);
    await u.click(screen.getByRole("combobox", { name: "Ficha" }));
    await u.type(screen.getByPlaceholderText("Pesquisar…"), "zzzz");
    expect(await screen.findByText("Nenhuma ficha.")).toBeInTheDocument();
  });

  it("com pesquisa no servidor o texto vai para fora e a lista não é refiltrada aqui", async () => {
    const aoPesquisar = vi.fn();
    const u = userEvent.setup();
    render(<Host onPesquisar={aoPesquisar} />);
    await u.click(screen.getByRole("combobox", { name: "Ficha" }));
    await u.type(screen.getByPlaceholderText("Pesquisar…"), "xy");
    expect(aoPesquisar).toHaveBeenLastCalledWith("xy");
    // a lista é a que o servidor devolveu: as duas continuam visíveis
    expect(screen.getByText("Ana Costa")).toBeInTheDocument();
    expect(screen.getByText("Rui Pereira")).toBeInTheDocument();
  });

  it("abrir avisa quem carrega a pedido; o botão limpa a escolha", async () => {
    const aoAbrir = vi.fn();
    const u = userEvent.setup();
    render(<Host onAbrir={aoAbrir} />);
    await u.click(screen.getByRole("combobox", { name: "Ficha" }));
    expect(aoAbrir).toHaveBeenCalledTimes(1);
    await u.click(await screen.findByText("Ana Costa"));
    await u.click(screen.getByRole("button", { name: /limpar escolha/i }));
    expect(screen.getByRole("combobox", { name: "Ficha" })).toHaveTextContent("Escolher…");
  });
});
