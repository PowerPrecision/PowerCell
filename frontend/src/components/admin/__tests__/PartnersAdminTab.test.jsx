/**
 * Separador Parceiros — convidar e gerir (lado da equipa).
 * Respostas = fixtures geradas pelos serviços do servidor.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import conviteCriado from "@/test/fixtures/parceiro/convite_criado.json";
import parceiros from "@/test/fixtures/parceiro/parceiros.json";

const api = vi.hoisted(() => ({
  getPartners: vi.fn(), getCompanies: vi.fn(), invitePartner: vi.fn(), updatePartner: vi.fn(), resendPartnerInvite: vi.fn(),
}));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("../../../services/api", () => api);
vi.mock("sonner", () => ({ toast }));

import PartnersAdminTab from "../PartnersAdminTab";

const EMPRESAS = [{ id: "cmp-power", name: "Power Real Estate" }, { id: "cmp-prec", name: "Precision" }];

const montar = () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return { queryClient, ...render(<QueryClientProvider client={queryClient}><PartnersAdminTab /></QueryClientProvider>) };
};

const abrirConvite = async () => {
  await userEvent.click(screen.getByRole("button", { name: /Convidar parceiro/ }));
  return screen.findByRole("dialog");
};

describe("PartnersAdminTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getPartners.mockResolvedValue({ data: parceiros });
    api.getCompanies.mockResolvedValue({ data: EMPRESAS });
    api.invitePartner.mockResolvedValue({ data: conviteCriado });
    api.updatePartner.mockResolvedValue({ data: {} });
    api.resendPartnerInvite.mockResolvedValue({ data: conviteCriado });
  });

  it("lista os parceiros com nome, email, empresa e estado", async () => {
    montar();
    const linha = await screen.findByTestId("parceiro-parceiro-novo");
    expect(linha.textContent).toContain("Rui Parceiro");
    expect(linha.textContent).toContain("rui@parceiros.pt");
    expect(linha.textContent).toContain("Power Real Estate");
    expect(within(linha).getByText("Activo")).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(1 + 3);
  });

  it("sem parceiros, convida o primeiro", async () => {
    api.getPartners.mockResolvedValue({ data: { partners: [], total: 0 } });
    montar();
    expect(await screen.findByText("Ainda não há parceiros")).toBeInTheDocument();
  });

  it("uma lista que falha diz porquê (não finge «sem parceiros»)", async () => {
    api.getPartners.mockRejectedValue({ response: { data: { detail: "Sem permissão." } } });
    montar();
    expect(await screen.findByRole("alert")).toHaveTextContent("Sem permissão.");
    expect(screen.queryByText("Ainda não há parceiros")).toBeNull();
  });

  it("o formulário valida antes de enviar", async () => {
    montar();
    await screen.findByTestId("parceiro-pt-1");
    await abrirConvite();
    await userEvent.click(screen.getByRole("button", { name: "Criar convite" }));
    expect(await screen.findByText("Indique o nome do parceiro.")).toBeInTheDocument();
    expect(screen.getByText("Indique um email válido.")).toBeInTheDocument();
    expect(screen.getByText("Escolha a empresa.")).toBeInTheDocument();
    expect(api.invitePartner).not.toHaveBeenCalled();
  });

  it("convida: envia SÓ o que o servidor aceita, mostra o link UMA vez e recarrega a lista", async () => {
    montar();
    await screen.findByTestId("parceiro-pt-1");
    await abrirConvite();
    await userEvent.type(screen.getByLabelText("Nome *"), "Rui Parceiro");
    await userEvent.type(screen.getByLabelText("Email *"), "rui@parceiros.pt");
    await userEvent.selectOptions(await screen.findByRole("option", { name: "Power Real Estate" }).then(() => screen.getByLabelText("Empresa *")), "cmp-power");
    await userEvent.click(screen.getByRole("button", { name: "Criar convite" }));

    await waitFor(() => expect(api.invitePartner).toHaveBeenCalledWith({
      name: "Rui Parceiro", email: "rui@parceiros.pt", company_id: "cmp-power",
    }));
    const link = await screen.findByLabelText("Link do convite");
    expect(link).toHaveValue(`${window.location.origin}/parceiro/convite/TOKEN-DO-CONVITE`);
    await waitFor(() => expect(api.getPartners.mock.calls.length).toBeGreaterThan(1));
  });

  it("um erro do convite fica no formulário e os dados mantêm-se", async () => {
    api.invitePartner.mockRejectedValue({ response: { data: { detail: "Já existe uma conta com este email." } } });
    montar();
    await screen.findByTestId("parceiro-pt-1");
    await abrirConvite();
    await userEvent.type(screen.getByLabelText("Nome *"), "Rui Parceiro");
    await userEvent.type(screen.getByLabelText("Email *"), "rui@parceiros.pt");
    await screen.findByRole("option", { name: "Precision" });
    await userEvent.selectOptions(screen.getByLabelText("Empresa *"), "cmp-prec");
    await userEvent.click(screen.getByRole("button", { name: "Criar convite" }));
    expect(await screen.findByText("Já existe uma conta com este email.")).toBeInTheDocument();
    expect(screen.getByLabelText("Nome *")).toHaveValue("Rui Parceiro");
  });

  it("suspender envia `suspended: true` ao parceiro certo e recarrega", async () => {
    montar();
    const linha = await screen.findByTestId("parceiro-pt-2");
    await userEvent.click(within(linha).getByRole("button", { name: "Suspender" }));
    await waitFor(() => expect(api.updatePartner).toHaveBeenCalledWith("pt-2", { suspended: true }));
    await waitFor(() => expect(api.getPartners.mock.calls.length).toBeGreaterThan(1));
  });

  it("um parceiro todo suspenso oferece «Reactivar» (suspended: false)", async () => {
    const suspenso = structuredClone(parceiros);
    suspenso.partners[0].redes[0].status = "suspended";
    api.getPartners.mockResolvedValue({ data: suspenso });
    montar();
    const linha = await screen.findByTestId("parceiro-pt-1");
    expect(within(linha).getByText("Suspenso")).toBeInTheDocument();
    await userEvent.click(within(linha).getByRole("button", { name: "Reactivar" }));
    await waitFor(() => expect(api.updatePartner).toHaveBeenCalledWith("pt-1", { suspended: false }));
  });

  it("novo convite: pede ao servidor, nomeia o parceiro e mostra o link", async () => {
    montar();
    const linha = await screen.findByTestId("parceiro-parceiro-novo");
    await userEvent.click(within(linha).getByRole("button", { name: "Novo convite para Rui Parceiro" }));
    await waitFor(() => expect(api.resendPartnerInvite).toHaveBeenCalledWith("parceiro-novo"));
    expect(await screen.findByLabelText("Link do convite")).toHaveValue(`${window.location.origin}/parceiro/convite/TOKEN-DO-CONVITE`);
    expect(screen.getByText("Rui Parceiro", { selector: "strong" })).toBeInTheDocument();
  });

  it("nunca mostra hash, convite nem termos (a forma do servidor não os traz, e o ecrã não os inventa)", async () => {
    const { container } = montar();
    await screen.findByTestId("parceiro-pt-1");
    expect(container.textContent).not.toMatch(/hash|token_hash|password/i);
  });
});
