/**
 * Atribuição Rápida no formulário de criação (Lote 4, ponto 11).
 *
 * O formulário enviava `{name, email, phone, role, password}` — sem
 * empresa nenhuma — e o próprio diálogo assumia-o na descrição: "Os
 * acessos por empresa (UCR) definem-se depois em Gerir Acessos". Entre o
 * "Criar" e esse "depois", a conta não pertencia a lado nenhum, e TUDO
 * lê UCRs: ContextSwitcher, resolução de perfil, config de email por
 * empresa e o isolamento por rede.
 *
 * Regra de negócio: empresa ESTRITAMENTE obrigatória, excepto parceiros
 * (contas fantasma sem acesso à plataforma).
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { UserCreateDialog } from "../UserAccountDialogs";

const EMPRESAS = [
  { id: "cmp-power", name: "Power Real Estate" },
  { id: "cmp-domus", name: "Domus" },
];

function montar(props = {}) {
  const onSubmit = vi.fn(async () => true);
  render(
    <UserCreateDialog
      open
      onOpenChange={() => {}}
      onSubmit={onSubmit}
      saving={false}
      companies={EMPRESAS}
      {...props}
    />,
  );
  return { onSubmit };
}

async function preencherIdentificacao(utilizador) {
  await utilizador.type(screen.getByTestId("user-create-name"), "Nova Pessoa");
  await utilizador.type(screen.getByTestId("user-create-email"), "nova@power.pt");
  await utilizador.type(screen.getByTestId("user-create-password"), "Segura123!");
}

describe("Acessos no acto da criação", () => {
  it("o formulário pede a empresa", async () => {
    // Asserção sobre o CONTROLO, não sobre a palavra: procurar /empresa/i
    // no texto casava também com a descrição do diálogo e passava sem o
    // campo existir.
    montar();
    expect(await screen.findByTestId("user-create-company-0")).toBeTruthy();
  });

  it("deixa de dizer que os acessos se definem depois", () => {
    // A frase descrevia exactamente o defeito. Mantê-la seria documentar
    // o buraco em vez de o fechar.
    montar();
    expect(screen.queryByText(/definem-se depois/i)).toBeNull();
  });

  it("envia a empresa escolhida no payload", async () => {
    const utilizador = userEvent.setup();
    const { onSubmit } = montar();

    await preencherIdentificacao(utilizador);
    await utilizador.click(screen.getByTestId("user-create-company-0"));
    await utilizador.click(await screen.findByRole("option", { name: "Domus" }));
    await utilizador.click(screen.getByTestId("user-create-submit"));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    const payload = onSubmit.mock.calls[0][0];
    expect(payload.companies).toEqual([
      expect.objectContaining({ company_id: "cmp-domus" }),
    ]);
  });

  it("não submete sem empresa", async () => {
    // A guarda existe também no backend; aqui evita-se a ida e volta.
    const utilizador = userEvent.setup();
    const { onSubmit } = montar();

    await preencherIdentificacao(utilizador);
    await utilizador.click(screen.getByTestId("user-create-submit"));

    await waitFor(() => expect(onSubmit).not.toHaveBeenCalled());
  });

  it("permite mais do que uma empresa, com cargos diferentes", async () => {
    // É o caso de uso do enunciado: Consultor numa, Intermediário noutra.
    const utilizador = userEvent.setup();
    const { onSubmit } = montar();

    await preencherIdentificacao(utilizador);
    await utilizador.click(screen.getByTestId("user-create-company-0"));
    await utilizador.click(await screen.findByRole("option", { name: "Power Real Estate" }));

    await utilizador.click(screen.getByRole("button", { name: /acrescentar empresa/i }));
    await utilizador.click(screen.getByTestId("user-create-company-1"));
    await utilizador.click(await screen.findByRole("option", { name: "Domus" }));
    await utilizador.click(screen.getByTestId("user-create-role-1"));
    await utilizador.click(await screen.findByRole("option", { name: /intermediário/i }));

    await utilizador.click(screen.getByTestId("user-create-submit"));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    const { companies } = onSubmit.mock.calls[0][0];
    expect(companies).toHaveLength(2);
    expect(companies[1].role).toBe("intermediario");
  });

  it("uma linha sem cargo herda o perfil principal", async () => {
    const utilizador = userEvent.setup();
    const { onSubmit } = montar();

    await preencherIdentificacao(utilizador);
    await utilizador.click(screen.getByTestId("user-create-company-0"));
    await utilizador.click(await screen.findByRole("option", { name: "Domus" }));
    await utilizador.click(screen.getByTestId("user-create-submit"));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0].companies[0].role).toBe("consultor");
  });

  it("o parceiro continua a poder ser criado sem empresa", async () => {
    // Contas fantasma: não acedem à plataforma e não têm onde trabalhar.
    const utilizador = userEvent.setup();
    const { onSubmit } = montar();

    await utilizador.type(screen.getByTestId("user-create-name"), "Notário Silva");
    await utilizador.click(screen.getByTestId("user-create-role"));
    await utilizador.click(await screen.findByRole("option", { name: /parceiro/i }));
    await utilizador.click(screen.getByTestId("user-create-submit"));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0].companies).toBeUndefined();
  });

  it("o parceiro não vê sequer o bloco de empresas", async () => {
    const utilizador = userEvent.setup();
    montar();

    await utilizador.click(screen.getByTestId("user-create-role"));
    await utilizador.click(await screen.findByRole("option", { name: /parceiro/i }));

    expect(screen.queryByTestId("user-create-company-0")).toBeNull();
  });

  it("uma linha pode ser removida", async () => {
    const utilizador = userEvent.setup();
    montar();

    await utilizador.click(screen.getByRole("button", { name: /acrescentar empresa/i }));
    expect(screen.getByTestId("user-create-company-1")).toBeTruthy();

    await utilizador.click(screen.getAllByRole("button", { name: /remover empresa/i })[1]);
    expect(screen.queryByTestId("user-create-company-1")).toBeNull();
  });

  it("sem empresas configuradas explica-o em vez de mostrar um select vazio", async () => {
    // Um select sem opções é indistinguível de um erro de carregamento.
    montar({ companies: [] });
    expect(
      await screen.findByText(/não há empresas configuradas/i),
    ).toBeTruthy();
  });
});
