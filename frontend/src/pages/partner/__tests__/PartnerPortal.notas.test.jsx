/**
 * O Portal do Parceiro MONTADO — o parceiro escreve notas no seu processo.
 *
 * A forma do detalhe é a REAL (fixture gerada pelo servidor, com `do_parceiro` / `e_minha`); a nota
 * nova refaz o detalhe — o servidor é quem sabe o que ficou gravado e o que a equipa escreveu entretanto.
 */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/services/partnerApi", () => ({
  entrar: vi.fn(),
  obterPerfil: vi.fn(),
  lerConvite: vi.fn(),
  aceitarConvite: vi.fn(),
  mudarPalavraPasse: vi.fn(),
  obterPainel: vi.fn(),
  listarCasos: vi.fn(),
  obterCaso: vi.fn(),
  submeterLead: vi.fn(),
  obterDestinos: vi.fn(),
  obterUrlDeDescarga: vi.fn(),
  enviarFicheiro: vi.fn(),
  obterFormularioDoCliente: vi.fn(),
  guardarFormularioDoCliente: vi.fn(),
  escreverNota: vi.fn(),
}));

import * as api from "@/services/partnerApi";
import { FIXTURES, erroHttp, montar, prepararApi } from "./montagem";

const NOTA_MINHA = {
  id: "n-minha", text: "O cliente já tem os recibos", created_at: "2026-10-06T10:00:00+00:00",
  author_name: "Rui", do_parceiro: true, e_minha: true,
};
const NOTA_DE_OUTRO = {
  id: "n-outro", text: "Nota de outro parceiro", created_at: "2026-10-05T10:00:00+00:00",
  author_name: "Sara", do_parceiro: true, e_minha: false,
};
const NOTA_DA_EQUIPA = {
  id: "n-equipa", text: "Falta a declaração de IRS", created_at: "2026-10-04T10:00:00+00:00",
  author_name: "Carla Consultora", do_parceiro: false, e_minha: false,
};

const casoCom = (extra = {}) => ({ ...structuredClone(FIXTURES.casoDeProcesso), ...extra });

beforeEach(() => {
  prepararApi();
  api.escreverNota.mockResolvedValue({ success: true, nota: NOTA_MINHA });
});
afterEach(() => vi.restoreAllMocks());

const abrir = async () => {
  montar("/parceiro/casos/a-novo");
  return screen.findByTestId("notas-da-equipa");
};

describe("escrever uma nota", () => {
  it("o dono de um processo aberto tem a caixa «Nova nota»", async () => {
    const cartao = await abrir();
    expect(within(cartao).getByRole("textbox", { name: "Nova nota" })).toBeInTheDocument();
    expect(within(cartao).getByRole("button", { name: /Guardar nota/ })).toBeInTheDocument();
  });

  it("grava o texto aparado no caso certo e refaz o detalhe", async () => {
    const utilizador = userEvent.setup();
    const cartao = await abrir();
    const pedidosAntes = api.obterCaso.mock.calls.length;
    const caixa = within(cartao).getByRole("textbox", { name: "Nova nota" });
    await utilizador.type(caixa, "  O cliente já tem os recibos  ");
    await utilizador.click(within(cartao).getByRole("button", { name: /Guardar nota/ }));

    await waitFor(() => expect(api.escreverNota).toHaveBeenCalledWith("a-novo", "O cliente já tem os recibos"));
    await waitFor(() => expect(api.obterCaso.mock.calls.length).toBeGreaterThan(pedidosAntes));
    expect(caixa).toHaveValue("");
  });

  it("a nota nova aparece marcada «Você» depois do detalhe refeito", async () => {
    const utilizador = userEvent.setup();
    const cartao = await abrir();
    api.obterCaso.mockImplementation(async () => casoCom({
      notas_da_equipa: [NOTA_MINHA, NOTA_DA_EQUIPA],
    }));
    await utilizador.type(within(cartao).getByRole("textbox", { name: "Nova nota" }), "O cliente já tem os recibos");
    await utilizador.click(within(cartao).getByRole("button", { name: /Guardar nota/ }));
    const minha = await screen.findByTestId("nota-minha");
    expect(minha).toHaveTextContent("O cliente já tem os recibos");
    expect(within(minha).getByText("Você")).toBeInTheDocument();
  });

  it("uma nota vazia nunca sai do ecrã", async () => {
    const utilizador = userEvent.setup();
    const cartao = await abrir();
    await utilizador.type(within(cartao).getByRole("textbox", { name: "Nova nota" }), "   ");
    await utilizador.click(within(cartao).getByRole("button", { name: /Guardar nota/ }));
    expect(await within(cartao).findByRole("alert")).toHaveTextContent("Escreva a nota.");
    expect(api.escreverNota).not.toHaveBeenCalled();
  });

  it("uma falha do servidor di-lo e NÃO apaga o que se escreveu", async () => {
    const utilizador = userEvent.setup();
    api.escreverNota.mockRejectedValue(erroHttp(409, "Este processo está fechado — já não aceita notas."));
    const cartao = await abrir();
    const caixa = within(cartao).getByRole("textbox", { name: "Nova nota" });
    await utilizador.type(caixa, "Texto importante");
    await utilizador.click(within(cartao).getByRole("button", { name: /Guardar nota/ }));
    expect(await within(cartao).findByRole("alert")).toHaveTextContent("já não aceita notas");
    expect(caixa).toHaveValue("Texto importante");
  });

  it("não envia duas vezes com duplo clique", async () => {
    const utilizador = userEvent.setup();
    let resolver;
    api.escreverNota.mockImplementation(() => new Promise((r) => { resolver = r; }));
    const cartao = await abrir();
    await utilizador.type(within(cartao).getByRole("textbox", { name: "Nova nota" }), "Uma só vez");
    const botao = within(cartao).getByRole("button", { name: /Guardar nota/ });
    await utilizador.dblClick(botao);
    expect(api.escreverNota).toHaveBeenCalledTimes(1);
    resolver({ success: true, nota: NOTA_MINHA });
  });
});

describe("quem NÃO pode escrever", () => {
  it.each(["concluido", "perdido"])("num processo %s não há formulário (o servidor recusava)", async (etapa) => {
    api.obterCaso.mockImplementation(async () => casoCom({ etapa }));
    const cartao = await abrir();
    expect(within(cartao).queryByRole("textbox")).toBeNull();
    expect(within(cartao).queryByRole("button")).toBeNull();
  });

  it("numa lead não há cartão de notas", async () => {
    montar("/parceiro/casos/lead-1");
    await screen.findByRole("tab", { name: /Documentos/ });
    expect(screen.queryByTestId("notas-da-equipa")).toBeNull();
  });
});

describe("ler as notas", () => {
  it("distingue a minha, a de outro parceiro e a da equipa — sem mostrar ids", async () => {
    api.obterCaso.mockImplementation(async () => casoCom({
      notas_da_equipa: [NOTA_MINHA, NOTA_DE_OUTRO, NOTA_DA_EQUIPA],
    }));
    const cartao = await abrir();
    expect(within(cartao).getByTestId("nota-minha")).toHaveTextContent("Você");
    const doOutro = within(cartao).getByTestId("nota-de-parceiro");
    expect(doOutro).toHaveTextContent("Parceiro");
    expect(doOutro).toHaveTextContent("Sara");
    const daEquipa = within(cartao).getByTestId("nota-da-equipa");
    expect(daEquipa).toHaveTextContent("Carla Consultora");
    expect(daEquipa).not.toHaveTextContent("Parceiro");
  });
});
