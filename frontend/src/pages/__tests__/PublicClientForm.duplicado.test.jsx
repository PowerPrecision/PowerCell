/**
 * D-38 — o formulário público e o 409 de "já existe um registo".
 *
 * Monta a PÁGINA: só aí se prova que a recusa do servidor chega ao cliente como
 * um aviso claro e PERSISTENTE (não um toast que desaparece), que o formulário
 * não passa para o ecrã de sucesso e que corrigir um dos campos retira o aviso.
 *
 * O 409 é o corpo REAL do servidor (`erro_publico_de_duplicado`), não uma forma inventada.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

vi.mock("axios", () => {
  const get = vi.fn();
  const post = vi.fn();
  return { default: { get, post }, get, post };
});
vi.mock("@sentry/react", () => ({
  captureException: vi.fn(),
  captureMessage: vi.fn(),
  withScope: (fn) => fn({ setLevel() {}, setTransactionName() {}, setTag() {}, setExtra() {} }),
}));

import axios from "axios";
import PublicClientForm from "../PublicClientForm";

// Passos 2 a 5 escondidos (dependem de um valor que ninguém escolhe): ficam só o 1 e o 6 (consentimentos),
// e o botão "Submeter" aparece sem percorrer o formulário todo.
const PASSOS_ESCONDIDOS = Object.fromEntries(
  [2, 3, 4, 5].map((n) => [String(n), { depends_on: { field: "compra_tipo", value: "__nunca__" } }]),
);

const MENSAGEM = "Já existe um registo associado a este NIF ou Email.";

// Os campos que o `validateForm` exige (nome, email, telemóvel e NIF), no passo 1.
const CAMPOS = [
  { field_key: "name", label: "Nome", field_type: "text", step: 1, order: 1, is_required: true, is_visible: true },
  { field_key: "email", label: "Email", field_type: "email", step: 1, order: 2, is_required: true, is_visible: true },
  { field_key: "phone", label: "Telemóvel", field_type: "text", step: 1, order: 3, is_required: true, is_visible: true },
  { field_key: "nif", label: "NIF", field_type: "text", step: 1, order: 4, is_required: true, is_visible: true },
];

function erro409() {
  return {
    response: { status: 409, data: { success: false, code: "DUPLICATE_CLIENT", detail: MENSAGEM } },
  };
}

async function preencherEEnviar(user) {
  await waitFor(() => expect(screen.getByLabelText(/Nome/i)).toBeInTheDocument());
  await user.type(screen.getByLabelText(/Nome/i), "Ana Silva");
  await user.type(screen.getByLabelText(/Email/i), "ana@exemplo.pt");
  await user.type(screen.getByLabelText(/Telemóvel/i), "912345678");
  await user.type(screen.getByLabelText(/NIF/i), "200000004");
  await chegarAoSubmeter(user);
}

/** Avança pelos passos (vazios) até ao botão final e aceita os consentimentos, se pedidos. */
async function chegarAoSubmeter(user) {
  for (let i = 0; i < 8; i += 1) {
    const submeter = screen.queryByRole("button", { name: /submeter/i });
    if (submeter) break;
    await user.click(await screen.findByRole("button", { name: /próximo/i }));
  }
  for (const caixa of screen.queryAllByRole("checkbox")) {
    if (caixa.getAttribute("aria-checked") === "false") await user.click(caixa);
  }
}

describe("PublicClientForm — registo duplicado (D-38)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    axios.get.mockResolvedValue({
      data: { custom_fields: [], all_fields: CAMPOS, step_config: PASSOS_ESCONDIDOS, step_labels: {} },
    });
  });

  it("um 409 do servidor mostra o aviso claro e não passa ao ecrã de sucesso", async () => {
    axios.post.mockRejectedValue(erro409());
    const user = userEvent.setup();
    render(<MemoryRouter><PublicClientForm /></MemoryRouter>);
    await preencherEEnviar(user);

    await user.click(await screen.findByRole("button", { name: /submeter/i }));

    const aviso = await screen.findByTestId("registo-duplicado");
    expect(aviso).toHaveTextContent(MENSAGEM);
    expect(aviso).toHaveAttribute("role", "alert");
    expect(screen.queryByText(/Registo Enviado com Sucesso/i)).toBeNull();
    // O formulário continua lá para o cliente corrigir (e voltar a submeter).
    expect(screen.getByRole("button", { name: /submeter/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /voltar/i })).toBeInTheDocument();
  });

  it("corrigir o email ou o telemóvel retira o aviso", async () => {
    axios.post.mockRejectedValue(erro409());
    const user = userEvent.setup();
    render(<MemoryRouter><PublicClientForm /></MemoryRouter>);
    await preencherEEnviar(user);
    await user.click(await screen.findByRole("button", { name: /submeter/i }));
    await screen.findByTestId("registo-duplicado");

    // Volta ao passo dos contactos e corrige o telemóvel.
    await user.click(screen.getByRole("button", { name: /voltar/i }));
    await user.type(await screen.findByLabelText(/Telemóvel/i), "0");

    await waitFor(() => expect(screen.queryByTestId("registo-duplicado")).toBeNull());
  });

  it("sem duplicado não há aviso (contraprova)", async () => {
    axios.post.mockResolvedValue({ data: { success: true, client_id: "c-1" } });
    const user = userEvent.setup();
    render(<MemoryRouter><PublicClientForm /></MemoryRouter>);
    await preencherEEnviar(user);
    await user.click(await screen.findByRole("button", { name: /submeter/i }));

    expect(await screen.findByText(/Registo Enviado com Sucesso/i)).toBeInTheDocument();
    expect(screen.queryByTestId("registo-duplicado")).toBeNull();
  });

  it("outro 409 (sem o código) não se apresenta como duplicado", async () => {
    axios.post.mockRejectedValue({ response: { status: 409, data: { detail: "Conflito qualquer" } } });
    const user = userEvent.setup();
    render(<MemoryRouter><PublicClientForm /></MemoryRouter>);
    await preencherEEnviar(user);
    await user.click(await screen.findByRole("button", { name: /submeter/i }));

    await waitFor(() => expect(axios.post).toHaveBeenCalled());
    expect(screen.queryByTestId("registo-duplicado")).toBeNull();
  });
});
