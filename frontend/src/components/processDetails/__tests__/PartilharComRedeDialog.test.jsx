/**
 * «Partilhar com…» — multi-fornecedor. Falseia só a rede; a forma das
 * respostas é a REAL (`run_list_share_targets` / `run_share_process`).
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  getProcessShareTargets: vi.fn(),
  shareProcessWithNetwork: vi.fn(),
  revokeProcessPartner: vi.fn(),
}));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("../../../services/api", () => api);
vi.mock("sonner", () => ({ toast }));

import PartilhaCard from "../PartilhaCard";
import PartilharComRedeDialog from "../PartilharComRedeDialog";

// Valores DIFERENTES das omissões (via_verde do processo = true, por exemplo).
const ALVOS = {
  process_id: "p1",
  via_verde: true,
  destinos: [
    { network_id: "grupo_power_precision", empresas: ["Power Real Estate", "Precision Crédito"], tem_index: true, ja_partilhado: false },
    { network_id: "rede:omega", empresas: ["Omega Crédito"], tem_index: true, ja_partilhado: false },
    { network_id: "rede:zeta", empresas: ["Zeta"], tem_index: false, ja_partilhado: false },
    { network_id: "rede:ja", empresas: ["Já Tem"], tem_index: true, ja_partilhado: true },
  ],
};
const PARCEIROS_DEPOIS = [
  { company_id: "cmp-omega", company_name: "Omega Crédito", network_id: "rede:omega", added_at: "2026-10-11T10:00:00Z" },
];

function abrir(props = {}) {
  const onOpenChange = vi.fn();
  const onShared = vi.fn();
  render(<PartilharComRedeDialog processId="p1" open onOpenChange={onOpenChange} onShared={onShared} {...props} />);
  return { onOpenChange, onShared };
}

beforeEach(() => {
  vi.clearAllMocks();
  api.getProcessShareTargets.mockResolvedValue({ data: ALVOS });
  api.shareProcessWithNetwork.mockResolvedValue({
    data: { success: true, partilhado: true, ja_partilhado: false, triagem: "triagem", parceiros: PARCEIROS_DEPOIS },
  });
});

describe("PartilharComRedeDialog", () => {
  it("lista as redes de destino com o nome das empresas e se têm Index", async () => {
    abrir();
    expect(await screen.findByText("Omega Crédito")).toBeInTheDocument();
    expect(screen.getByText("Power Real Estate / Precision Crédito")).toBeInTheDocument();
    expect(screen.getAllByText("Tem equipa de Index").length).toBe(2);
    expect(screen.getByText("Sem equipa de Index")).toBeInTheDocument();
    expect(screen.getByText("Já partilhado")).toBeInTheDocument();
  });

  it("começa com a Via Verde que o processo já tem e não deixa confirmar sem escolher", async () => {
    abrir();
    await screen.findByText("Omega Crédito");
    expect(screen.getByRole("switch", { name: /via verde/i })).toBeChecked();
    expect(screen.getByTestId("partilhar-confirmar")).toBeDisabled();
  });

  it("diz o efeito: Index, Via Verde, e destino sem Index", async () => {
    abrir();
    await screen.findByText("Omega Crédito");
    await userEvent.click(screen.getByRole("radio", { name: /omega crédito/i }));
    expect(screen.getByTestId("efeito-da-partilha")).toHaveTextContent(/salta o Index/i);

    await userEvent.click(screen.getByRole("switch", { name: /via verde/i }));
    expect(screen.getByTestId("efeito-da-partilha")).toHaveTextContent(/fila de Index desta rede/i);

    await userEvent.click(screen.getByRole("radio", { name: /zeta/i }));
    expect(screen.getByTestId("efeito-da-partilha")).toHaveTextContent(/não tem equipa de Index/i);
  });

  it("envia a rede ESCOLHIDA e a Via Verde mostrada, e devolve os parceiros", async () => {
    const { onShared, onOpenChange } = abrir();
    await screen.findByText("Omega Crédito");
    await userEvent.click(screen.getByRole("radio", { name: /omega crédito/i }));
    await userEvent.click(screen.getByRole("switch", { name: /via verde/i })); // desliga

    await userEvent.click(screen.getByTestId("partilhar-confirmar"));

    await waitFor(() => expect(api.shareProcessWithNetwork).toHaveBeenCalledWith(
      "p1", { networkId: "rede:omega", viaVerde: false },
    ));
    expect(onShared).toHaveBeenCalledWith(PARCEIROS_DEPOIS);
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(toast.success).toHaveBeenCalledWith(expect.stringContaining("Omega Crédito"));
  });

  it("uma rede já partilhada não se pode escolher outra vez", async () => {
    abrir();
    await screen.findByText("Já Tem");
    await userEvent.click(screen.getByRole("radio", { name: /já tem/i }));
    expect(screen.getByTestId("partilhar-confirmar")).toBeDisabled();
  });

  it("o motivo do servidor aparece no diálogo (403 «só a casa dona…») e o diálogo fica aberto", async () => {
    api.shareProcessWithNetwork.mockRejectedValue({
      response: { data: { detail: "Só a empresa dona do processo pode partilhá-lo com outra rede." } },
    });
    const { onOpenChange } = abrir();
    await screen.findByText("Omega Crédito");
    await userEvent.click(screen.getByRole("radio", { name: /omega crédito/i }));
    await userEvent.click(screen.getByTestId("partilhar-confirmar"));

    expect(await screen.findByTestId("erro-da-partilha")).toHaveTextContent(/empresa dona/i);
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });

  it("sem redes de destino diz-se, em vez de uma lista vazia sem explicação", async () => {
    api.getProcessShareTargets.mockResolvedValue({ data: { destinos: [] } });
    abrir();
    expect(await screen.findByTestId("sem-destinos")).toBeInTheDocument();
  });

  it("falha a carregar: diz o motivo e não deixa enviar", async () => {
    api.getProcessShareTargets.mockRejectedValue({ response: { data: { detail: "Sem permissão." } } });
    abrir();
    expect(await screen.findByTestId("erro-da-partilha")).toHaveTextContent(/sem permissão/i);
    expect(screen.getByTestId("partilhar-confirmar")).toBeDisabled();
  });

  it("uma resposta com a forma errada não rebenta (Array.isArray, nunca || [])", async () => {
    api.getProcessShareTargets.mockResolvedValue({ data: { destinos: { x: 1 } } });
    abrir();
    expect(await screen.findByTestId("sem-destinos")).toBeInTheDocument();
  });
});

describe("PartilhaCard — o botão «Partilhar com…»", () => {
  const SEM_PARCEIROS = { id: "p1" };

  it("quem pode partilhar vê o cartão e o botão mesmo sem parceiros", () => {
    render(<PartilhaCard process={SEM_PARCEIROS} podePartilhar />);
    expect(screen.getByTestId("partilhar-com-btn")).toBeInTheDocument();
    expect(screen.getByTestId("partilha-vazia")).toBeInTheDocument();
  });

  it("quem não pode não vê cartão nenhum num processo sem parceiros", () => {
    const { container } = render(<PartilhaCard process={SEM_PARCEIROS} podePartilhar={false} />);
    expect(container.firstChild).toBeNull();
  });

  it("um processo FECHADO não se partilha: sem botão (e sem cartão, se não há parceiros)", () => {
    const { container } = render(<PartilhaCard process={SEM_PARCEIROS} podePartilhar processoFechado />);
    expect(container.firstChild).toBeNull();
  });

  it("fechado mas com parceiros: lista-os, sem o botão de partilhar", () => {
    render(<PartilhaCard
      process={{ id: "p1", partner_companies: PARCEIROS_DEPOIS }}
      podePartilhar processoFechado podeRevogar
    />);
    expect(screen.getByTestId("cartao-partilha")).toHaveTextContent("Omega Crédito");
    expect(screen.queryByTestId("partilhar-com-btn")).toBeNull();
  });

  it("o botão abre o diálogo e pede as redes ao servidor", async () => {
    render(<PartilhaCard process={SEM_PARCEIROS} podePartilhar />);
    expect(api.getProcessShareTargets).not.toHaveBeenCalled();
    await userEvent.click(screen.getByTestId("partilhar-com-btn"));
    expect(await screen.findByTestId("dialogo-partilhar-com-rede")).toBeInTheDocument();
    await waitFor(() => expect(api.getProcessShareTargets).toHaveBeenCalledWith("p1"));
  });
});
