import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const getS3Relink = vi.fn();
const setS3Relink = vi.fn();

vi.mock("@/services/api", () => ({
  getS3Relink: (...a) => getS3Relink(...a),
  setS3Relink: (...a) => setS3Relink(...a),
}));

const toastSuccess = vi.fn();
const toastWarning = vi.fn();
const toastError = vi.fn();
vi.mock("sonner", () => ({
  toast: {
    success: (...a) => toastSuccess(...a),
    warning: (...a) => toastWarning(...a),
    error: (...a) => toastError(...a),
  },
}));

import S3RelinkPanel from "../S3RelinkPanel";

const UUID_CLIENTE = "11111111-1111-4111-8111-111111111111";
const PASTA_POR_ID = `Documentação Clientes/${UUID_CLIENTE}`;
const PASTA_LEGADA = "Documentação Clientes/Carolina_Silva";

const RESPOSTA = {
  data: {
    entidades: [
      {
        tipo: "cliente",
        id: UUID_CLIENTE,
        nome: "Carolina Agostinho da Silva",
        s3_folder: PASTA_POR_ID,
        pasta_por_id: true,
      },
      {
        tipo: "processo",
        id: "p-1",
        nome: "Rui Pereira",
        s3_folder: null,
        pasta_por_id: false,
      },
    ],
    pastas: [
      {
        path: PASTA_POR_ID,
        name: UUID_CLIENTE,
        display_name: "Carolina Agostinho da Silva",
        nomes_dos_clientes: ["Carolina Agostinho da Silva"],
        orfa: false,
        por_id: true,
      },
      {
        path: PASTA_LEGADA,
        name: "Carolina_Silva",
        display_name: "Carolina_Silva",
        nomes_dos_clientes: ["Carolina Silva", "Carolina A. da Silva"],
        orfa: false,
        por_id: false,
      },
    ],
    total: 2,
    stats: { total: 2, sem_pasta: 1, por_id: 1 },
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  getS3Relink.mockResolvedValue(RESPOSTA);
  setS3Relink.mockResolvedValue({
    data: { success: true, nome: "Carolina Agostinho da Silva", aviso: "" },
  });
});

const carregar = async () => {
  render(<S3RelinkPanel />);
  await userEvent.click(screen.getByRole("button", { name: /carregar/i }));
  await waitFor(() => expect(getS3Relink).toHaveBeenCalled());
};

describe("S3RelinkPanel", () => {
  it("não vai à rede até alguém pedir", () => {
    render(<S3RelinkPanel />);
    expect(getS3Relink).not.toHaveBeenCalled();
  });

  it("lista CLIENTES e processos — o cliente da Pool era o que faltava", async () => {
    await carregar();
    // Consulta pela LINHA e não pelo texto: o nome do cliente aparece também
    // dentro das opções do `<select>` (é lá que ele é uma pasta), e um
    // `getByText` daria "Found multiple elements" — a mesma armadilha de
    // fixture do chip da Domus no Lote 4.
    const linhaCliente = await screen.findByTestId(`linha-cliente:${UUID_CLIENTE}`);
    const linhaProcesso = screen.getByTestId("linha-processo:p-1");
    expect(linhaCliente).toHaveTextContent("Carolina Agostinho da Silva");
    expect(linhaCliente).toHaveTextContent("Cliente");
    expect(linhaProcesso).toHaveTextContent("Rui Pereira");
    expect(linhaProcesso).toHaveTextContent("Processo");
  });

  it("marca quem está numa pasta por id", async () => {
    await carregar();
    expect(await screen.findByText("pasta por id")).toBeInTheDocument();
  });

  it("a ficha sem pasta diz-se sem pasta, não finge uma", async () => {
    await carregar();
    expect(await screen.findByText("— sem pasta —")).toBeInTheDocument();
  });

  it("as pastas aparecem pelo NOME do cliente, não pelo uuid", async () => {
    await carregar();
    const selector = await screen.findByLabelText("Pasta de Rui Pereira");
    const opcoes = Array.from(selector.querySelectorAll("option")).map((o) => o.textContent);
    expect(opcoes.some((t) => t.includes("Carolina Agostinho da Silva"))).toBe(true);
    expect(opcoes.some((t) => t.includes(UUID_CLIENTE))).toBe(false);
  });

  it("a pasta com duas fichas é anunciada na própria opção", async () => {
    await carregar();
    const selector = await screen.findByLabelText("Pasta de Rui Pereira");
    const opcoes = Array.from(selector.querySelectorAll("option")).map((o) => o.textContent);
    expect(opcoes.some((t) => t.includes("2 fichas"))).toBe(true);
  });

  it("guardar só fica activo depois de MUDAR a escolha", async () => {
    await carregar();
    const botao = await screen.findByRole("button", {
      name: /guardar pasta de rui pereira/i,
    });
    expect(botao).toBeDisabled();

    await userEvent.selectOptions(
      screen.getByLabelText("Pasta de Rui Pereira"),
      PASTA_LEGADA
    );
    expect(botao).not.toBeDisabled();
  });

  it("religa pelo tipo e id da ficha", async () => {
    await carregar();
    await userEvent.selectOptions(
      screen.getByLabelText("Pasta de Rui Pereira"),
      PASTA_LEGADA
    );
    await userEvent.click(
      screen.getByRole("button", { name: /guardar pasta de rui pereira/i })
    );
    await waitFor(() =>
      expect(setS3Relink).toHaveBeenCalledWith({
        tipo: "processo",
        entityId: "p-1",
        s3Folder: PASTA_LEGADA,
      })
    );
  });

  it("remover o mapeamento envia string vazia, não a opção interna", async () => {
    await carregar();
    await userEvent.selectOptions(
      screen.getByLabelText("Pasta de Carolina Agostinho da Silva"),
      "__sem_mapeamento__"
    );
    await userEvent.click(
      screen.getByRole("button", {
        name: /guardar pasta de carolina agostinho da silva/i,
      })
    );
    await waitFor(() =>
      expect(setS3Relink).toHaveBeenCalledWith({
        tipo: "cliente",
        entityId: UUID_CLIENTE,
        s3Folder: "",
      })
    );
  });

  it("o aviso de partilha fica na linha, não só no instante do clique", async () => {
    setS3Relink.mockResolvedValue({
      data: {
        success: true,
        nome: "Rui Pereira",
        aviso: "Esta pasta já está associada a: Carolina Silva.",
      },
    });
    await carregar();
    await userEvent.selectOptions(
      screen.getByLabelText("Pasta de Rui Pereira"),
      PASTA_LEGADA
    );
    await userEvent.click(
      screen.getByRole("button", { name: /guardar pasta de rui pereira/i })
    );
    await waitFor(() => expect(toastWarning).toHaveBeenCalled());
    expect(
      await screen.findByText(/já está associada a: Carolina Silva/i)
    ).toBeInTheDocument();
  });

  it("um 400 do servidor mostra a mensagem DELE, não uma genérica", async () => {
    setS3Relink.mockRejectedValue({
      response: { data: { detail: "A pasta tem de estar dentro de «Documentação Clientes»." } },
    });
    await carregar();
    await userEvent.selectOptions(
      screen.getByLabelText("Pasta de Rui Pereira"),
      PASTA_LEGADA
    );
    await userEvent.click(
      screen.getByRole("button", { name: /guardar pasta de rui pereira/i })
    );
    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith(
        "A pasta tem de estar dentro de «Documentação Clientes»."
      )
    );
  });

  it("os filtros vão no pedido", async () => {
    await carregar();
    getS3Relink.mockClear();
    await userEvent.selectOptions(screen.getByLabelText("Tipo de ficha"), "cliente");
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: /actualizar/i }));
    await waitFor(() =>
      expect(getS3Relink).toHaveBeenCalledWith(
        expect.objectContaining({ tipo: "cliente", apenas_por_resolver: true })
      )
    );
  });

  it("lista vazia explica-se em vez de ficar em branco", async () => {
    getS3Relink.mockResolvedValue({
      data: { entidades: [], pastas: [], total: 0, stats: {} },
    });
    await carregar();
    expect(
      await screen.findByText(/nenhuma ficha corresponde/i)
    ).toBeInTheDocument();
  });
});
