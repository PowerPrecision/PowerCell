/**
 * Ponto 9 — o formulário público montado a sério.
 *
 * Os utilitários e o painel já têm testes próprios. Este monta a PÁGINA,
 * porque é só aí que se prova a coisa que interessa ao cliente: que ele
 * consegue **avançar sem preencher os campos secundários**. Esconder
 * campos que continuassem a bloquear seria pior do que o problema
 * original — o cliente carregaria em "Seguinte" e receberia um erro
 * sobre um campo que nem está a ver.
 *
 * Falseia só duas fronteiras: o `axios` (o GET do `form-config`) e o
 * `localStorage` do rascunho. Os campos, a validação e a barra de
 * progresso são os REAIS.
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
vi.mock("@sentry/react", () => ({ captureException: vi.fn(), captureMessage: vi.fn() }));

import axios from "axios";
import PublicClientForm from "../PublicClientForm";

// Espelha o `DEFAULT_FORM_CONFIG` do backend no que interessa: o passo 1
// tem obrigatórios E opcionais, e é a divisão entre os dois que está em
// teste.
const CAMPOS = [
  { field_key: "name", label: "Nome", field_type: "text", step: 1, order: 1, is_required: true, is_visible: true },
  { field_key: "email", label: "Email", field_type: "email", step: 1, order: 2, is_required: true, is_visible: true },
  { field_key: "phone", label: "Telemóvel", field_type: "text", step: 1, order: 3, is_required: true, is_visible: true },
  { field_key: "sexo", label: "Sexo", field_type: "text", step: 1, order: 4, is_required: false, is_visible: true },
  { field_key: "altura", label: "Altura", field_type: "text", step: 1, order: 5, is_required: false, is_visible: true },
  { field_key: "profissao", label: "Profissão", field_type: "text", step: 1, order: 6, is_required: false, is_visible: true },
];

function montar() {
  axios.get.mockResolvedValue({
    data: {
      custom_fields: [],
      all_fields: CAMPOS,
      step_config: {},
      step_labels: {},
    },
  });
  return render(
    <MemoryRouter>
      <PublicClientForm />
    </MemoryRouter>,
  );
}

describe("PublicClientForm — stress-free (Ponto 9)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  it("mostra os campos que bloqueiam e esconde os restantes", async () => {
    montar();
    await waitFor(() => expect(screen.getByLabelText(/Nome/i)).toBeInTheDocument());

    expect(screen.getByLabelText(/Email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Telemóvel/i)).toBeInTheDocument();
    // Secundários fechados no painel.
    expect(screen.queryByLabelText(/Sexo/i)).toBeNull();
    expect(screen.queryByLabelText(/Altura/i)).toBeNull();
  });

  it("convida a abrir os adicionais sem falar em obrigações", async () => {
    montar();
    const convite = await screen.findByTestId("abrir-campos-adicionais");
    const texto = convite.textContent.toLowerCase();
    expect(texto).toContain("informação adicional importante");
    expect(texto).not.toContain("obrigat");
    expect(texto).not.toContain("em falta");
  });

  it("revela os campos adicionais ao abrir o painel", async () => {
    const user = userEvent.setup();
    montar();
    await user.click(await screen.findByTestId("abrir-campos-adicionais"));
    expect(await screen.findByLabelText(/Sexo/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Profissão/i)).toBeInTheDocument();
  });

  it("os campos visíveis levam asterisco; os do painel NÃO", async () => {
    // O asterisco vermelho deixa de aparecer onde não bloqueia nada —
    // é o pedido literal do Ponto 9.
    const user = userEvent.setup();
    montar();
    await waitFor(() => expect(screen.getByLabelText(/Nome/i)).toBeInTheDocument());

    const rotuloObrigatorio = screen.getByText("Nome").closest("label");
    expect(rotuloObrigatorio.textContent).toContain("*");

    await user.click(screen.getByTestId("abrir-campos-adicionais"));
    await screen.findByLabelText(/Sexo/i);
    const rotuloOpcional = screen.getByText("Sexo").closest("label");
    expect(rotuloOpcional.textContent).not.toContain("*");
    expect(rotuloOpcional.textContent.toLowerCase()).not.toContain("obrigat");
  });

  it("a barra de progresso conta SÓ os campos que bloqueiam", async () => {
    // Antes somava uma lista fixa por passo com a do config: o cliente
    // preenchia tudo o que bloqueia e a barra continuava a meio.
    const user = userEvent.setup();
    montar();
    await waitFor(() => expect(screen.getByLabelText(/Nome/i)).toBeInTheDocument());

    await user.type(screen.getByLabelText(/Nome/i), "Ana Silva");
    await user.type(screen.getByLabelText(/Email/i), "ana@exemplo.pt");
    await user.type(screen.getByLabelText(/Telemóvel/i), "912345678");

    // Três de três, sem tocar em nenhum campo do painel.
    await waitFor(() => {
      expect(screen.getByText(/3\s*\/\s*3|100\s*%/)).toBeInTheDocument();
    });
  });

  it("deixa avançar de passo sem preencher NADA do painel", async () => {
    // O teste que justifica a funcionalidade inteira.
    const user = userEvent.setup();
    montar();
    await waitFor(() => expect(screen.getByLabelText(/Nome/i)).toBeInTheDocument());

    await user.type(screen.getByLabelText(/Nome/i), "Ana Silva");
    await user.type(screen.getByLabelText(/Email/i), "ana@exemplo.pt");
    await user.type(screen.getByLabelText(/Telemóvel/i), "912345678");

    await user.click(screen.getByRole("button", { name: /próximo/i }));

    await waitFor(() => {
      expect(screen.queryByLabelText(/Nome/i)).toBeNull();
    });
  });
});
