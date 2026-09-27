/**
 * O ErrorBoundary sai do estado de erro quando o sítio muda (Lote 6, ponto 2).
 *
 * O DEFEITO (produção, Set 2026)
 * ==============================
 * Um `ErrorBoundary` do React fica no estado de erro até ser remontado ou
 * reposto à mão. Este só se repunha no clique do botão "Tentar novamente".
 *
 * Como o boundary vive DENTRO do `element` de cada rota, sobrevive a uma
 * mudança de `:id` na mesma rota: a partir do PRIMEIRO crash, toda a
 * navegação para aquela rota mostrava o ecrã de erro — de um processo que
 * já não era o aberto, e mesmo que a causa já tivesse desaparecido.
 *
 * Em produção apareceu como uma assimetria difícil de explicar: as setas
 * Anterior/Seguinte funcionavam e o "Voltar" do browser dava ecrã em
 * branco. A aplicação declara DUAS rotas para os detalhes do processo
 * (`/processo/:id` e `/process/:id`), cada uma com o seu `element` e
 * portanto com o seu boundary — um ficava latido e o outro não. As duas
 * rotas passaram também a partilhar um só `element`.
 *
 * O que este ficheiro NÃO prova: qual era o crash original. Isto corrige
 * o ecrã ficar QUEBRADO; se a causa persistir, o erro volta a aparecer —
 * e é isso que se quer, porque aí há uma mensagem para ler.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

import ErrorBoundary from "../ErrorBoundary";

/** Rebenta só para os ids que lhe dissermos — como um processo com dados maus. */
function PaginaQuePodeRebentar({ id, idsMaus }) {
  if (idsMaus.includes(id)) {
    throw new Error(`boom em ${id}`);
  }
  return <div data-testid="pagina">processo {id}</div>;
}

let erroDaConsola;

beforeEach(() => {
  // O React escreve o erro apanhado na consola; silenciar mantém a saída
  // do teste legível sem esconder o comportamento.
  erroDaConsola = vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => erroDaConsola.mockRestore());

describe("ErrorBoundary — resetKey", () => {
  it("mostra o erro quando a página rebenta", () => {
    render(
      <ErrorBoundary variant="page" moduleName="Detalhes" resetKey="/process/b">
        <PaginaQuePodeRebentar id="b" idsMaus={["b"]} />
      </ErrorBoundary>,
    );
    expect(screen.queryByTestId("pagina")).not.toBeInTheDocument();
  });

  it("recupera quando o resetKey muda (o 'Voltar' do browser)", () => {
    const { rerender } = render(
      <ErrorBoundary variant="page" moduleName="Detalhes" resetKey="/process/b">
        <PaginaQuePodeRebentar id="b" idsMaus={["b"]} />
      </ErrorBoundary>,
    );
    expect(screen.queryByTestId("pagina")).not.toBeInTheDocument();

    // O utilizador volta ao processo A, que está perfeitamente bem.
    rerender(
      <ErrorBoundary variant="page" moduleName="Detalhes" resetKey="/processo/a">
        <PaginaQuePodeRebentar id="a" idsMaus={["b"]} />
      </ErrorBoundary>,
    );

    expect(screen.getByTestId("pagina")).toHaveTextContent("processo a");
  });

  it("com o MESMO resetKey continua a mostrar o erro", () => {
    /**
     * Contraprova: sem ela, um reset a cada render satisfaria o teste de
     * cima e reintroduzia o ciclo infinito que o `retryCount` existe para
     * travar — renderizar, rebentar, repor, renderizar.
     */
    const { rerender } = render(
      <ErrorBoundary variant="page" moduleName="Detalhes" resetKey="/process/b">
        <PaginaQuePodeRebentar id="b" idsMaus={["b"]} />
      </ErrorBoundary>,
    );
    rerender(
      <ErrorBoundary variant="page" moduleName="Detalhes" resetKey="/process/b">
        <PaginaQuePodeRebentar id="b" idsMaus={["b"]} />
      </ErrorBoundary>,
    );
    expect(screen.queryByTestId("pagina")).not.toBeInTheDocument();
  });

  it("uma página que nunca rebentou não é afectada por resetKey nenhum", () => {
    const { rerender } = render(
      <ErrorBoundary variant="page" moduleName="Detalhes" resetKey="/processo/a">
        <PaginaQuePodeRebentar id="a" idsMaus={[]} />
      </ErrorBoundary>,
    );
    rerender(
      <ErrorBoundary variant="page" moduleName="Detalhes" resetKey="/processo/c">
        <PaginaQuePodeRebentar id="c" idsMaus={[]} />
      </ErrorBoundary>,
    );
    expect(screen.getByTestId("pagina")).toHaveTextContent("processo c");
  });
});
