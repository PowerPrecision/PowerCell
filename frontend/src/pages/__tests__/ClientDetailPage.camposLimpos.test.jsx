/**
 * Ficha do Cliente: apagar o email / telefone / NIF persiste (QA, Out 2026).
 *
 * O modal montava `email: editForm.email || currentContato.email`: apagar o
 * email reenviava o antigo (o toast dizia «sucesso» e o valor ficava), e o
 * payload levava a secção INTEIRA de contacto (índices cegos incluídos). Monta-se
 * a PÁGINA real e afirma-se o que sai para a API.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../layouts/DashboardLayout", () => ({
  default: ({ children }) => <div data-testid="layout">{children}</div>,
}));

const api = vi.hoisted(() => ({
  getClient: vi.fn(),
  getClientFiles: vi.fn(() => Promise.resolve({ data: { files: [] } })),
  updateClient: vi.fn(() => Promise.resolve({ data: {} })),
  restoreClient: vi.fn(),
}));

vi.mock("../../services/api", async (original) => ({ ...(await original()), ...api }));

import ClientDetailPage from "../ClientDetailPage";

const CLIENTE = {
  id: "cli-1",
  nome: "Ana Martins",
  // `email_hash` vem na resposta real: não pode voltar no payload.
  contacto: { email: "ana@exemplo.pt", telefone: "912345678", email_hash: "h-e" },
  dados_pessoais: { nif: "123456789", naturalidade: "Porto", nif_hash: "h-n" },
  processes: [],
};

function montar() {
  return render(
    <MemoryRouter initialEntries={["/cliente/cli-1"]}>
      <Routes>
        <Route path="/cliente/:id" element={<ClientDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

async function abrirModal(utilizador) {
  await screen.findByText("Editar Cliente");
  await utilizador.click(screen.getByRole("button", { name: /Editar Cliente/i }));
  return screen.findByLabelText("Email");
}

async function guardar(utilizador) {
  const dialogo = screen.getByRole("dialog");
  await utilizador.click(within(dialogo).getByRole("button", { name: /Guardar/i }));
  await waitFor(() => expect(api.updateClient).toHaveBeenCalledTimes(1));
  return api.updateClient.mock.calls[0];
}

beforeEach(() => {
  api.updateClient.mockClear();
  api.getClient.mockReset();
  api.getClient.mockResolvedValue({ data: CLIENTE });
});

describe("ClientDetailPage — modal de edição", () => {
  it("apagar o email envia o email VAZIO (e só o email, sem os índices cegos)", async () => {
    const utilizador = userEvent.setup();
    montar();
    const campo = await abrirModal(utilizador);

    await utilizador.clear(campo);
    const [id, payload] = await guardar(utilizador);

    expect(id).toBe("cli-1");
    expect(payload.contacto).toEqual({ email: "" });
    expect(payload).not.toHaveProperty("dados_pessoais");
    expect(payload).not.toHaveProperty("nome");
  });

  it("apagar o NIF envia o NIF vazio", async () => {
    const utilizador = userEvent.setup();
    montar();
    await abrirModal(utilizador);

    await utilizador.clear(screen.getByLabelText("NIF"));
    const [, payload] = await guardar(utilizador);

    expect(payload.dados_pessoais).toEqual({ nif: "" });
    expect(payload).not.toHaveProperty("contacto");
  });

  it("apagar o telefone envia o telefone vazio e deixa o email em paz", async () => {
    const utilizador = userEvent.setup();
    montar();
    await abrirModal(utilizador);

    await utilizador.clear(screen.getByLabelText("Telefone"));
    const [, payload] = await guardar(utilizador);

    expect(payload.contacto).toEqual({ telefone: "" });
  });

  it("alterar só um campo envia só esse campo", async () => {
    const utilizador = userEvent.setup();
    montar();
    await abrirModal(utilizador);

    const telefone = screen.getByLabelText("Telefone");
    await utilizador.clear(telefone);
    await utilizador.type(telefone, "966666666");
    const [, payload] = await guardar(utilizador);

    expect(payload.contacto).toEqual({ telefone: "966666666" });
  });

  it("apagar o NOME é recusado no ecrã e nada é enviado", async () => {
    const utilizador = userEvent.setup();
    montar();
    await abrirModal(utilizador);

    await utilizador.clear(screen.getByLabelText("Nome Completo"));
    await utilizador.click(within(screen.getByRole("dialog")).getByRole("button", { name: /Guardar/i }));

    await new Promise((r) => setTimeout(r, 100));
    expect(api.updateClient).not.toHaveBeenCalled();
  });

  it("sem alterações não há pedido", async () => {
    const utilizador = userEvent.setup();
    montar();
    await abrirModal(utilizador);

    await utilizador.click(within(screen.getByRole("dialog")).getByRole("button", { name: /Guardar/i }));

    await new Promise((r) => setTimeout(r, 100));
    expect(api.updateClient).not.toHaveBeenCalled();
  });
});
