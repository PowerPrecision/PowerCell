import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AlertMatrix, ficheirosDoAlerta } from "../AlertMatrix";

const FICHEIROS = [
  { id: "doc-extrato-agosto", filename: "extrato_agosto.pdf" },
  { id: "doc-extrato-junho", filename: "extrato_junho.pdf" },
];

const alerta = (extra = {}) => ({
  id: "a1",
  code: "saldo_nao_bate",
  severity: "aviso",
  message: "O saldo de um extrato não bate certo com os movimentos listados.",
  detail: "Saldo inicial 381,00 € + créditos 2.419,75 € − débitos 1.762,67 € dá 1.038,08 €.",
  refs: [{ document_id: "doc-extrato-agosto", page: null }],
  dismissed: false,
  ...extra,
});

describe("AlertMatrix — de que ficheiro é o aviso", () => {
  it("mostra o nome do ficheiro a que o aviso se refere", () => {
    render(<AlertMatrix alertas={[alerta()]} ficheiros={FICHEIROS} />);
    expect(screen.getByTestId("alerta-ficheiro")).toHaveTextContent("Ficheiro: extrato_agosto.pdf");
  });

  it("dois avisos iguais de ficheiros diferentes distinguem-se pelo ficheiro", () => {
    render(
      <AlertMatrix
        alertas={[
          alerta({ id: "a1", refs: [{ document_id: "doc-extrato-agosto" }] }),
          alerta({ id: "a2", refs: [{ document_id: "doc-extrato-junho", page: 2 }] }),
        ]}
        ficheiros={FICHEIROS}
      />,
    );
    const linhas = screen.getAllByTestId("alerta-ficheiro").map((l) => l.textContent);
    expect(linhas.some((t) => t.includes("extrato_agosto.pdf"))).toBe(true);
    expect(linhas.some((t) => t.includes("extrato_junho.pdf") && t.includes("pág. 2"))).toBe(true);
  });

  it("o ficheiro aparece uma vez mesmo com várias referências, e as páginas ordenam-se", () => {
    const f = ficheirosDoAlerta(
      alerta({ refs: [{ document_id: "doc-extrato-junho", page: 3 }, { document_id: "doc-extrato-junho", page: 1 }, { document_id: "doc-extrato-junho", page: 3 }] }),
      FICHEIROS,
    );
    expect(f).toEqual([{ id: "doc-extrato-junho", nome: "extrato_junho.pdf", paginas: [1, 3] }]);
  });

  it("«Ver» abre o ficheiro certo", async () => {
    const onVerDocumento = vi.fn();
    render(<AlertMatrix alertas={[alerta()]} ficheiros={FICHEIROS} onVerDocumento={onVerDocumento} />);
    await userEvent.click(screen.getByRole("button", { name: "Ver ficheiro do alerta — extrato_agosto.pdf" }));
    expect(onVerDocumento).toHaveBeenCalledWith([{ id: "doc-extrato-agosto", rotulo: "extrato_agosto.pdf" }], "extrato_agosto.pdf");
  });

  it("sem a função de abrir não há botão (mas o nome continua a ver-se)", () => {
    render(<AlertMatrix alertas={[alerta()]} ficheiros={FICHEIROS} />);
    expect(screen.queryByRole("button", { name: /Ver ficheiro do alerta/ })).not.toBeInTheDocument();
    expect(screen.getByTestId("alerta-ficheiro")).toBeInTheDocument();
  });

  it("um ficheiro que já não está na lista não rebenta: diz «Documento»", () => {
    render(<AlertMatrix alertas={[alerta({ refs: [{ document_id: "desconhecido" }] })]} ficheiros={FICHEIROS} />);
    expect(screen.getByTestId("alerta-ficheiro")).toHaveTextContent("Ficheiro: Documento");
  });

  it("um aviso sem referências (ex.: «extrato em falta») não desenha ficheiro nenhum", () => {
    render(<AlertMatrix alertas={[alerta({ refs: [] })]} ficheiros={FICHEIROS} />);
    expect(screen.queryByTestId("alerta-ficheiro")).not.toBeInTheDocument();
  });

  it("refs que não são um array ou lixo não rebentam (a lista do servidor é uma hipótese)", () => {
    const { rerender } = render(<AlertMatrix alertas={[alerta({ refs: null })]} ficheiros={FICHEIROS} />);
    rerender(<AlertMatrix alertas={[alerta({ refs: [null, {}, { document_id: 5 }] })]} ficheiros={undefined} />);
    expect(screen.queryByTestId("alerta-ficheiro")).not.toBeInTheDocument();
    expect(within(screen.getByTestId("alert-matrix")).getByText(/Saldo inicial/)).toBeInTheDocument();
  });
});
