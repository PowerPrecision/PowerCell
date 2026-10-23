/**
 * Separador Parceiros — as acções de gestão do menu «⋯»: Editar, Mudar Empresa, Gerar Nova Password
 * e Eliminar. As três últimas (e o email) são só do Master: quem não o é não as vê.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import parceiros from "@/test/fixtures/parceiro/parceiros.json";

const api = vi.hoisted(() => ({
  getPartners: vi.fn(), getCompanies: vi.fn(), invitePartner: vi.fn(), updatePartner: vi.fn(),
  resendPartnerInvite: vi.fn(), changePartnerCompany: vi.fn(), resetPartnerPassword: vi.fn(), deletePartner: vi.fn(),
}));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("../../../services/api", () => api);
vi.mock("sonner", () => ({ toast }));

import PartnersAdminTab from "../PartnersAdminTab";

const EMPRESAS = [{ id: "cmp-power", name: "Power Real Estate" }, { id: "cmp-prec", name: "Precision" }];
const erro = (status, detail) => Object.assign(new Error("x"), { response: { status, data: { detail } } });

const montar = (props = {}) => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(<QueryClientProvider client={queryClient}><PartnersAdminTab {...props} /></QueryClientProvider>);
};

const abrirMenu = async (id) => {
  const linha = await screen.findByTestId(`parceiro-${id}`);
  await userEvent.click(within(linha).getByRole("button", { name: /^Ações de / }));
};
const escolher = async (id, nome) => {
  await abrirMenu(id);
  await userEvent.click(await screen.findByRole("menuitem", { name: nome }));
};

describe("PartnersAdminTab — gestão", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getPartners.mockResolvedValue({ data: parceiros });
    api.getCompanies.mockResolvedValue({ data: EMPRESAS });
    api.updatePartner.mockResolvedValue({ data: {} });
    api.changePartnerCompany.mockResolvedValue({ data: { alterado: true } });
    api.resetPartnerPassword.mockResolvedValue({ data: { sent: true, email: "rui@p.pt" } });
    api.deletePartner.mockResolvedValue({ data: { deleted: true } });
  });

  describe("quem vê o quê", () => {
    it("o Master vê as quatro acções novas", async () => {
      montar({ isMaster: true });
      await abrirMenu("pt-1");
      for (const nome of ["Editar", "Mudar Empresa", "Gerar Nova Password", "Eliminar"]) {
        expect(await screen.findByRole("menuitem", { name: nome })).toBeInTheDocument();
      }
    });

    it("Admin e CEO só vêem Editar (nome e telefone) — o resto é do Master", async () => {
      montar({ isMaster: false });
      await abrirMenu("pt-1");
      expect(await screen.findByRole("menuitem", { name: "Editar" })).toBeInTheDocument();
      for (const nome of ["Mudar Empresa", "Gerar Nova Password", "Eliminar"]) {
        expect(screen.queryByRole("menuitem", { name: nome })).toBeNull();
      }
    });

    it("sem a prop, a omissão é a de menos poder", async () => {
      montar();
      await abrirMenu("pt-1");
      await screen.findByRole("menuitem", { name: "Editar" });
      expect(screen.queryByRole("menuitem", { name: "Eliminar" })).toBeNull();
    });

    it("«Gerar Nova Password» fica desactivada a quem ainda não activou a conta", async () => {
      const convidado = structuredClone(parceiros);
      convidado.partners[0].status = "invited";
      api.getPartners.mockResolvedValue({ data: convidado });
      montar({ isMaster: true });
      await abrirMenu("pt-1");
      expect(await screen.findByRole("menuitem", { name: "Gerar Nova Password" })).toHaveAttribute("aria-disabled", "true");
    });
  });

  describe("Editar", () => {
    it("abre com os dados do parceiro", async () => {
      montar({ isMaster: true });
      await escolher("parceiro-novo", "Editar");
      const dialogo = await screen.findByTestId("editar-parceiro-dialog");
      expect(within(dialogo).getByLabelText("Nome *")).toHaveValue("Rui Parceiro");
      expect(within(dialogo).getByLabelText("Email")).toHaveValue("rui@parceiros.pt");
    });

    it("o Admin não consegue escrever no email", async () => {
      montar({ isMaster: false });
      await escolher("parceiro-novo", "Editar");
      expect(await screen.findByLabelText("Email")).toBeDisabled();
    });

    it("só envia o que mudou (nome)", async () => {
      montar({ isMaster: true });
      await escolher("parceiro-novo", "Editar");
      const nome = await screen.findByLabelText("Nome *");
      await userEvent.clear(nome);
      await userEvent.type(nome, "Rui Novo");
      await userEvent.click(screen.getByRole("button", { name: "Guardar" }));
      await waitFor(() => expect(api.updatePartner).toHaveBeenCalledWith("parceiro-novo", { name: "Rui Novo" }));
      await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Parceiro actualizado"));
      await waitFor(() => expect(screen.queryByTestId("editar-parceiro-dialog")).toBeNull());
    });

    it("o Admin nunca envia o email, mesmo que o corpo o permitisse", async () => {
      montar({ isMaster: false });
      await escolher("parceiro-novo", "Editar");
      const telefone = await screen.findByLabelText("Telefone");
      await userEvent.type(telefone, "912345678");
      await userEvent.click(screen.getByRole("button", { name: "Guardar" }));
      await waitFor(() => expect(api.updatePartner).toHaveBeenCalledWith("parceiro-novo", { phone: "912345678" }));
    });

    it("o Master muda o email", async () => {
      montar({ isMaster: true });
      await escolher("parceiro-novo", "Editar");
      const email = await screen.findByLabelText("Email");
      await userEvent.clear(email);
      await userEvent.type(email, "novo@parceiros.pt");
      await userEvent.click(screen.getByRole("button", { name: "Guardar" }));
      await waitFor(() => expect(api.updatePartner).toHaveBeenCalledWith("parceiro-novo", { email: "novo@parceiros.pt" }));
    });

    it("um email inválido não sai e diz porquê", async () => {
      montar({ isMaster: true });
      await escolher("parceiro-novo", "Editar");
      const email = await screen.findByLabelText("Email");
      await userEvent.clear(email);
      await userEvent.type(email, "isto-nao-e-email");
      await userEvent.click(screen.getByRole("button", { name: "Guardar" }));
      expect(await screen.findByText("Indique um email válido.")).toBeInTheDocument();
      expect(api.updatePartner).not.toHaveBeenCalled();
    });

    it("sem alterações, fecha sem pedir nada", async () => {
      montar({ isMaster: true });
      await escolher("parceiro-novo", "Editar");
      await userEvent.click(await screen.findByRole("button", { name: "Guardar" }));
      await waitFor(() => expect(screen.queryByTestId("editar-parceiro-dialog")).toBeNull());
      expect(api.updatePartner).not.toHaveBeenCalled();
    });

    it("o erro do servidor fica no diálogo e o que se escreveu mantém-se", async () => {
      api.updatePartner.mockRejectedValue(erro(409, "Este email não pode ser usado para um parceiro."));
      montar({ isMaster: true });
      await escolher("parceiro-novo", "Editar");
      const email = await screen.findByLabelText("Email");
      await userEvent.clear(email);
      await userEvent.type(email, "outro@parceiros.pt");
      await userEvent.click(screen.getByRole("button", { name: "Guardar" }));
      expect(await screen.findByTestId("editar-parceiro-erro")).toHaveTextContent("Este email não pode ser usado");
      expect(screen.getByLabelText("Email")).toHaveValue("outro@parceiros.pt");
      expect(toast.success).not.toHaveBeenCalled();
    });

    it("se o servidor emitiu um convite novo, mostra o link", async () => {
      api.updatePartner.mockResolvedValue({ data: { name: "Rui Parceiro", invite_path: "/parceiro/convite/NOVO-TOKEN-1234567890" } });
      montar({ isMaster: true });
      await escolher("parceiro-novo", "Editar");
      const email = await screen.findByLabelText("Email");
      await userEvent.clear(email);
      await userEvent.type(email, "novo@parceiros.pt");
      await userEvent.click(screen.getByRole("button", { name: "Guardar" }));
      expect(await screen.findByLabelText("Link do convite")).toHaveValue(
        `${window.location.origin}/parceiro/convite/NOVO-TOKEN-1234567890`,
      );
    });
  });

  describe("Mudar Empresa", () => {
    it("só confirma com uma empresa escolhida e envia o id", async () => {
      montar({ isMaster: true });
      await escolher("pt-1", "Mudar Empresa");
      const dialogo = await screen.findByTestId("mudar-empresa-parceiro-dialog");
      const botao = within(dialogo).getByRole("button", { name: "Mudar empresa" });
      expect(botao).toBeDisabled();
      await screen.findByRole("option", { name: "Precision" });
      await userEvent.selectOptions(within(dialogo).getByLabelText("Nova empresa"), "cmp-prec");
      await userEvent.click(botao);
      await waitFor(() => expect(api.changePartnerCompany).toHaveBeenCalledWith("pt-1", "cmp-prec"));
      await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Empresa do parceiro alterada"));
      await waitFor(() => expect(api.getPartners.mock.calls.length).toBeGreaterThan(1));
    });

    it("«já estava» diz-se e não finge uma mudança", async () => {
      api.changePartnerCompany.mockResolvedValue({ data: { alterado: false } });
      montar({ isMaster: true });
      await escolher("pt-1", "Mudar Empresa");
      await screen.findByRole("option", { name: "Power Real Estate" });
      await userEvent.selectOptions(screen.getByLabelText("Nova empresa"), "cmp-power");
      await userEvent.click(screen.getByRole("button", { name: "Mudar empresa" }));
      await waitFor(() => expect(toast.success).toHaveBeenCalledWith("O parceiro já estava nesta empresa"));
    });

    it("o erro fica no diálogo, que não fecha", async () => {
      api.changePartnerCompany.mockRejectedValue(erro(404, "Empresa não encontrada"));
      montar({ isMaster: true });
      await escolher("pt-1", "Mudar Empresa");
      await screen.findByRole("option", { name: "Precision" });
      await userEvent.selectOptions(screen.getByLabelText("Nova empresa"), "cmp-prec");
      await userEvent.click(screen.getByRole("button", { name: "Mudar empresa" }));
      expect(await screen.findByTestId("mudar-empresa-erro")).toHaveTextContent("Empresa não encontrada");
      expect(screen.getByTestId("mudar-empresa-parceiro-dialog")).toBeInTheDocument();
    });
  });

  describe("Gerar Nova Password", () => {
    it("pede ao servidor, diz para que email foi e nunca mostra a password", async () => {
      montar({ isMaster: true });
      await escolher("pt-1", "Gerar Nova Password");
      const dialogo = await screen.findByTestId("nova-password-parceiro-dialog");
      expect(dialogo).toHaveTextContent("rui@p.pt");
      await userEvent.click(within(dialogo).getByRole("button", { name: "Gerar e enviar" }));
      await waitFor(() => expect(api.resetPartnerPassword).toHaveBeenCalledWith("pt-1"));
      await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Nova palavra-passe enviada para rui@p.pt"));
    });

    it("sem entrega (502) o erro fica no diálogo", async () => {
      api.resetPartnerPassword.mockRejectedValue(erro(502, "Não foi possível enviar o email com a nova palavra-passe. Nada foi alterado."));
      montar({ isMaster: true });
      await escolher("pt-1", "Gerar Nova Password");
      await userEvent.click(await screen.findByRole("button", { name: "Gerar e enviar" }));
      expect(await screen.findByTestId("nova-password-erro")).toHaveTextContent("Nada foi alterado");
      expect(toast.success).not.toHaveBeenCalled();
    });
  });

  describe("Eliminar", () => {
    it("exige a password e envia-a com o id", async () => {
      montar({ isMaster: true });
      await escolher("pt-2", "Eliminar");
      const dialogo = await screen.findByTestId("eliminar-parceiro-dialog");
      const botao = within(dialogo).getByRole("button", { name: "Eliminar parceiro" });
      expect(botao).toBeDisabled();
      await userEvent.type(screen.getByLabelText("A sua password actual"), "Segredo-1!");
      await userEvent.click(botao);
      await waitFor(() => expect(api.deletePartner).toHaveBeenCalledWith("pt-2", "Segredo-1!"));
      await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Parceiro eliminado"));
      await waitFor(() => expect(api.getPartners.mock.calls.length).toBeGreaterThan(1));
    });

    it("password errada: diz-se no diálogo, que não fecha, e nada é eliminado", async () => {
      api.deletePartner.mockRejectedValue(erro(403, "Password incorrecta."));
      montar({ isMaster: true });
      await escolher("pt-2", "Eliminar");
      await userEvent.type(await screen.findByLabelText("A sua password actual"), "errada");
      await userEvent.click(screen.getByRole("button", { name: "Eliminar parceiro" }));
      expect(await screen.findByTestId("eliminar-parceiro-erro")).toHaveTextContent("Password incorrecta.");
      expect(screen.getByTestId("eliminar-parceiro-dialog")).toBeInTheDocument();
      expect(toast.success).not.toHaveBeenCalled();
    });

    it("cancelar não elimina", async () => {
      montar({ isMaster: true });
      await escolher("pt-2", "Eliminar");
      await userEvent.click(await screen.findByRole("button", { name: "Cancelar" }));
      await waitFor(() => expect(screen.queryByTestId("eliminar-parceiro-dialog")).toBeNull());
      expect(api.deletePartner).not.toHaveBeenCalled();
    });
  });
});
