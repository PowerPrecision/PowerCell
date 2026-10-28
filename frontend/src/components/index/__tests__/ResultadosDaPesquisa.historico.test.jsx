/**
 * O arquivo histórico na pesquisa avançada (Out 2026): linhas SEM processo; com ficheiro só se a importação o
 * guardou (`has_file`, desde 28/10/2026).
 * Forma real do `GET /api/index/advanced-search` por documento (`historical`, `import_label`, `process_id: null`).
 */
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { ResultadosDaPesquisa } from "../ResultadosDaPesquisa";
import { documentosDoResultado } from "../../../utils/pesquisaIndex";

const HISTORICO = {
  document_id: "hist_abc", document_type: "recibo", process_id: null, process_number: null, company_name: null,
  period: "2019-05", needs_review: false, historical: true, import_label: "OneDrive 2019",
  employer: { nif: "501964843", name: "Empresa Antiga, Lda", location: "Porto" }, job_title: "Técnico",
  contract_type: "efetivo", net_salary: 1432.1,
};
const NORMAL = {
  document_id: "doc-1", document_type: "recibo", process_id: "p1", process_number: 4711, company_name: "Casa Alfa",
  period: "2026-09", needs_review: false, historical: false,
  employer: { nif: "509442013", name: "Outra SA", location: "Faro" }, job_title: "Gerente",
  contract_type: "efetivo", net_salary: 2000,
};

function montar(itens) {
  return render(
    <MemoryRouter>
      <ResultadosDaPesquisa
        vista="documents" tipo="recibo" itens={itens} onVerDocumento={vi.fn()} onDescarregar={vi.fn()} emCurso={new Set()}
      />
    </MemoryRouter>,
  );
}

describe("ResultadosDaPesquisa — arquivo histórico", () => {
  it("mostra o selo e a etiqueta em vez do processo, sem ligação nenhuma", () => {
    montar([HISTORICO]);
    const linha = screen.getByTestId("pesquisa-linha");
    expect(within(linha).getByText("Arquivo histórico")).toBeInTheDocument();
    expect(within(linha).getByText("OneDrive 2019")).toBeInTheDocument();
    expect(within(linha).queryByTestId("resultado-processo")).not.toBeInTheDocument();
    expect(within(linha).queryByRole("link")).not.toBeInTheDocument();
  });

  it("não oferece Ver documento nem Download: não há ficheiro, e di-lo", () => {
    montar([HISTORICO]);
    expect(screen.queryByTestId("ver-documento")).not.toBeInTheDocument();
    expect(screen.queryByTestId("download-documento")).not.toBeInTheDocument();
    expect(screen.getByText(/ficheiro não guardado/i)).toBeInTheDocument();
  });

  it("os dados continuam à vista (entidade, líquido, localidade)", () => {
    montar([HISTORICO]);
    const linha = screen.getByTestId("pesquisa-linha");
    expect(within(linha).getByText("Empresa Antiga, Lda")).toBeInTheDocument();
    expect(linha).toHaveTextContent("Porto");
    expect(linha).toHaveTextContent("1432");
  });

  it("contraprova: um documento normal ao lado mantém a ligação e os dois botões", () => {
    montar([HISTORICO, NORMAL]);
    const [, normal] = screen.getAllByTestId("pesquisa-linha");
    expect(within(normal).getByTestId("resultado-processo")).toHaveAttribute("href", "/index/p1");
    expect(within(normal).getByTestId("ver-documento")).toBeInTheDocument();
    expect(within(normal).getByTestId("download-documento")).toBeInTheDocument();
    expect(within(normal).queryByText("Arquivo histórico")).not.toBeInTheDocument();
  });

  it("só `historical === true` conta: um texto ou 1 não faz de uma linha normal um arquivo", () => {
    expect(documentosDoResultado({ ...NORMAL, historical: "true" }, "documents")).toHaveLength(1);
    expect(documentosDoResultado({ ...NORMAL, historical: 1 }, "documents")).toHaveLength(1);
    expect(documentosDoResultado({ ...NORMAL, historical: true }, "documents")).toEqual([]);
    expect(documentosDoResultado(HISTORICO, "jobs")).toEqual([]);
  });

  it("com o ficheiro guardado (`has_file`) oferece Ver documento e Download, pelo id da linha", () => {
    const onVer = vi.fn();
    render(
      <MemoryRouter>
        <ResultadosDaPesquisa
          vista="documents" tipo="recibo" itens={[{ ...HISTORICO, has_file: true }]}
          onVerDocumento={onVer} onDescarregar={vi.fn()} emCurso={new Set()}
        />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("download-documento")).toBeInTheDocument();
    expect(screen.queryByText(/ficheiro não guardado/i)).not.toBeInTheDocument();
    screen.getByTestId("ver-documento").click();
    expect(onVer).toHaveBeenCalledWith([expect.objectContaining({ id: "hist_abc" })], expect.any(String));
  });

  it("só `has_file === true` conta (um texto não inventa um ficheiro)", () => {
    expect(documentosDoResultado({ ...HISTORICO, has_file: "true" }, "documents")).toEqual([]);
    expect(documentosDoResultado({ ...HISTORICO, has_file: true }, "documents")).toHaveLength(1);
  });
});
