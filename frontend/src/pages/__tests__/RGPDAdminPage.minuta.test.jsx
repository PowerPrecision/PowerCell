/**
 * Separador «Minuta de Exclusividade» do RGPD admin (Bloco 5, ponto 36).
 *
 * O modelo por omissão da minuta é TEXTO SIMPLES com parágrafos separados por
 * linhas vazias. O `ReactQuill` recebe o `value` como HTML — onde `\n` é um
 * espaço —, pelo que o modelo entrava no editor como um bloco só e era assim
 * que se guardava: a quebra de linha perdia-se na primeira edição, antes de o
 * PDF existir. A página é montada A SÉRIO; só o editor é falseado, para ler o
 * que a página lhe entrega.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const entregueAoEditor = vi.hoisted(() => ({ valores: [] }));

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: { id: "u1", role: "admin" } }),
}));
vi.mock("../../layouts/DashboardLayout", () => ({ default: ({ children }) => <div>{children}</div> }));
vi.mock("../../components/ui/SmartRichEditor", () => ({
  default: ({ value }) => {
    entregueAoEditor.valores.push(value);
    return <div data-testid="editor">{value}</div>;
  },
}));
vi.mock("../../services/api", () => ({
  getRGPDTemplate: vi.fn(async () => ({ status: 200, data: { content: "RGPD", is_default: true } })),
  updateRGPDTemplate: vi.fn(),
  getMinutaTemplate: vi.fn(),
  updateMinutaTemplate: vi.fn(),
}));

import { getMinutaTemplate } from "../../services/api";
import RGPDAdminPage from "../RGPDAdminPage";

const MODELO_SIMPLES =
  "MINUTA DE EXCLUSIVIDADE\n\nEu, {{NOME}}, venho por este meio.\nSegunda linha do mesmo parágrafo.\n\nFim.";

async function abrirSeparadorDaMinuta() {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ items: [], total: 0, requests: [] }) })));
  render(<RGPDAdminPage embedded />);
  await userEvent.setup().click(await screen.findByRole("tab", { name: /Minuta de Exclusividade/ }));
}

beforeEach(() => {
  entregueAoEditor.valores = [];
  vi.mocked(getMinutaTemplate).mockReset();
});

describe("Minuta — o texto simples chega ao editor como parágrafos", () => {
  it("linhas vazias viram parágrafos e quebras simples viram <br>", async () => {
    vi.mocked(getMinutaTemplate).mockResolvedValue({ status: 200, data: { content: MODELO_SIMPLES, is_default: true } });
    await abrirSeparadorDaMinuta();

    await waitFor(() => {
      expect(entregueAoEditor.valores).toContain(
        "<p>MINUTA DE EXCLUSIVIDADE</p><p>Eu, {{NOME}}, venho por este meio.<br>Segunda linha do mesmo parágrafo.</p><p>Fim.</p>",
      );
    });
  });

  it("um modelo que já é HTML chega tal e qual", async () => {
    const html = "<p>Eu, <strong>{{NOME}}</strong>.</p><p class=\"ql-align-center\">Centro</p>";
    vi.mocked(getMinutaTemplate).mockResolvedValue({ status: 200, data: { content: html, is_default: false } });
    await abrirSeparadorDaMinuta();

    await waitFor(() => expect(entregueAoEditor.valores).toContain(html));
  });

  it("carregar o modelo não deixa o separador com «alterações por guardar»", async () => {
    vi.mocked(getMinutaTemplate).mockResolvedValue({ status: 200, data: { content: MODELO_SIMPLES, is_default: true } });
    await abrirSeparadorDaMinuta();
    await waitFor(() => expect(entregueAoEditor.valores.some((v) => String(v).includes("<p>"))).toBe(true));

    // Original e conteúdo derivam do mesmo valor normalizado: o botão de guardar
    // não pode ficar activo sem ninguém ter tocado em nada.
    const guardar = await screen.findByRole("button", { name: /Guardar Minuta/ });
    expect(guardar).toBeDisabled();
  });
});
