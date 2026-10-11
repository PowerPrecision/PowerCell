/**
 * O formulário público é POR EMPRESA (D-37): o link leva `?empresa=<id>`.
 *
 * Monta a PÁGINA: é só aí que se prova que o identificador chega ao servidor no GET
 * dos campos e no POST do registo, que um link inválido NÃO mostra formulário nenhum
 * e que o rascunho de uma empresa não se mistura com o de outra.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("axios", () => {
  const get = vi.fn();
  const post = vi.fn();
  return { default: { get, post }, get, post };
});
vi.mock("@sentry/react", () => ({ captureException: vi.fn(), captureMessage: vi.fn() }));

import axios from "axios";
import PublicClientForm from "../PublicClientForm";

const CAMPOS_DA_DOMUS = [
  { field_key: "name", label: "Nome", field_type: "text", step: 1, order: 1, is_required: true, is_visible: true },
  { field_key: "campo_da_domus", label: "Campo só da Domus", field_type: "text", step: 1, order: 2, is_required: true, is_visible: true },
];

function montar(url) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <PublicClientForm />
    </MemoryRouter>,
  );
}

describe("PublicClientForm — empresa do link", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  it("pede ao servidor o formulário DA empresa do link e mostra o nome dela", async () => {
    axios.get.mockResolvedValue({
      data: {
        custom_fields: [], all_fields: CAMPOS_DA_DOMUS, step_config: {}, step_labels: {},
        empresa: { id: "cmp-domus", nome: "Domus" },
      },
    });
    montar("/registo?empresa=cmp-domus");

    expect(await screen.findByLabelText(/Campo só da Domus/i)).toBeInTheDocument();
    expect(axios.get).toHaveBeenCalledTimes(1);
    expect(axios.get.mock.calls[0][0]).toMatch(/\/public\/form-config$/);
    expect(axios.get.mock.calls[0][1]).toEqual({ params: { empresa: "cmp-domus" } });
    expect(screen.getByTestId("registo-empresa")).toHaveTextContent("Domus");
  });

  it("um link antigo, sem empresa, continua a funcionar e não manda parâmetro", async () => {
    axios.get.mockResolvedValue({
      data: { custom_fields: [], all_fields: CAMPOS_DA_DOMUS, step_config: {}, step_labels: {} },
    });
    montar("/registo");

    expect(await screen.findByLabelText(/Campo só da Domus/i)).toBeInTheDocument();
    expect(axios.get.mock.calls[0][1]).toEqual({ params: undefined });
    expect(screen.queryByTestId("registo-empresa")).toBeNull();
  });

  it("um link com empresa inexistente (404) não mostra formulário e di-lo", async () => {
    axios.get.mockRejectedValue({ response: { status: 404 } });
    montar("/registo?empresa=cmp-que-nao-existe");

    expect(await screen.findByTestId("registo-link-invalido")).toHaveTextContent(/não é válido/i);
    expect(screen.queryByLabelText(/Nome/i)).toBeNull();
  });

  it("um erro de rede num link COM empresa não é «link inválido» (só o 404 é)", async () => {
    axios.get.mockRejectedValue({ response: { status: 500 } });
    montar("/registo?empresa=cmp-domus");

    await waitFor(() => expect(screen.queryByText(/A carregar configuração/i)).toBeNull());
    expect(screen.queryByTestId("registo-link-invalido")).toBeNull();
  });

  it("o rascunho de uma empresa não se mistura com o de outra", async () => {
    window.localStorage.setItem("public_client_form_draft:cmp-power", JSON.stringify({ name: "Da Power" }));
    axios.get.mockResolvedValue({
      data: { custom_fields: [], all_fields: CAMPOS_DA_DOMUS, step_config: {}, step_labels: {} },
    });
    montar("/registo?empresa=cmp-domus");

    await screen.findByLabelText(/Campo só da Domus/i);
    expect(window.localStorage.getItem("public_client_form_draft:cmp-domus")).toBeNull();
    expect(window.localStorage.getItem("public_client_form_draft:cmp-power")).toContain("Da Power");
  });
});

describe("PublicClientForm — o registo leva a empresa", () => {
  it("o POST do registo envia o `empresa_id` do link (guarda sobre a fonte, com contraprova)", async () => {
    const { readFileSync } = await import("node:fs");
    const { join, dirname } = await import("node:path");
    const { fileURLToPath } = await import("node:url");
    const fonte = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "..", "PublicClientForm.js"), "utf8")
      .split("\n").filter((l) => !l.trim().startsWith("//")).join("\n");
    const i = fonte.lastIndexOf("/public/client-registration");
    expect(i).toBeGreaterThan(0); // contraprova: encontrou o POST
    expect(fonte.slice(i, i + 400)).toMatch(/empresa_id:\s*empresaId/);
  });
});
