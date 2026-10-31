/**
 * O Portal do Parceiro tem as calculadoras do CRM (`/parceiro/calculadoras`).
 *
 *  1. a ligação está no menu e a página monta com as três calculadoras;
 *  2. a Prestação calcula no browser e o DSTI abre — sem pedir nada ao servidor
 *     do parceiro;
 *  3. o painel partilhado e as calculadoras não importam o cliente HTTP nem o
 *     contexto do staff (o parceiro não pode levar o `X-Company-Id`);
 *  4. a Euribor vai ao BACKEND (`API_BASE_URL`), não a `/api/...` relativo ao
 *     domínio do frontend — na Vercel isso devolvia o `index.html`.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axios from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/services/partnerApi", () => ({
  entrar: vi.fn(),
  obterPerfil: vi.fn(),
  lerConvite: vi.fn(),
  aceitarConvite: vi.fn(),
  mudarPalavraPasse: vi.fn(),
  obterPainel: vi.fn(),
  listarCasos: vi.fn(),
  obterCaso: vi.fn(),
  submeterLead: vi.fn(),
  obterDestinos: vi.fn(),
  obterUrlDeDescarga: vi.fn(),
  enviarFicheiro: vi.fn(),
  obterFormularioDoCliente: vi.fn(),
  guardarFormularioDoCliente: vi.fn(),
  escreverNota: vi.fn(),
}));

import * as api from "@/services/partnerApi";
import { API_BASE_URL } from "@/utils/apiBaseUrl";
import { obterEuribor } from "@/utils/euribor";
import { montar, prepararApi } from "./montagem";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const ler = (...p) => readFileSync(join(SRC, ...p), "utf8");
const semComentarios = (codigo) => codigo.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

beforeEach(() => prepararApi());

describe("calculadoras no Portal do Parceiro", () => {
  it("o menu tem «Calculadoras» e leva à página", async () => {
    const user = userEvent.setup();
    montar("/parceiro");
    const nav = await screen.findByRole("navigation", { name: "Navegação principal" });
    await user.click(within(nav).getByRole("link", { name: "Calculadoras" }));
    expect(await screen.findByRole("heading", { name: "Calculadoras", level: 1 })).toBeInTheDocument();
  });

  it("mostra as três calculadoras e a prestação é calculada logo", async () => {
    montar("/parceiro/calculadoras");
    expect(await screen.findByText("Prestação de Crédito Habitação")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Abrir DSTI (Taxa de Esforço)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Abrir Risco de Crédito" })).toBeInTheDocument();
    expect(screen.getByTestId("prestacao-mensal").textContent).toMatch(/\d/);
  });

  it("o DSTI abre num dialog e não chama o servidor do parceiro", async () => {
    const user = userEvent.setup();
    montar("/parceiro/calculadoras");
    await user.click(await screen.findByRole("button", { name: "Abrir DSTI (Taxa de Esforço)" }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(api.submeterLead).not.toHaveBeenCalled();
    expect(api.listarCasos).not.toHaveBeenCalled();
  });
});

describe("as calculadoras não tocam no plano do staff", () => {
  it("nem o painel nem as calculadoras importam o cliente Axios, o AuthContext ou os cabeçalhos do CRM", () => {
    const proibido = [
      /from\s+["'](?:@|\.\.?)\/?(?:[./]*)contexts\/AuthContext["']/,
      /from\s+["'](?:@\/|[./]+\/)services\/api["']/,
      /localStorage/,
      /X-Company-Id|X-Active-Role/,
    ];
    const ficheiros = [
      ["pages", "partner", "PartnerCalculatorsPage.jsx"],
      ["components", "calculators", "CalculatorsPanel.jsx"],
      ["components", "calculators", "MortgageSimulator.jsx"],
      ["components", "DSTICalculator.js"],
      ["components", "RiskCalculator.js"],
      ["utils", "euribor.js"],
    ];
    for (const f of ficheiros) {
      const codigo = semComentarios(ler(...f));
      for (const re of proibido) expect(codigo, `${f.join("/")} ~ ${re}`).not.toMatch(re);
    }
  });
});

describe("Euribor", () => {
  it("vai ao backend pelo API_BASE_URL, sem cabeçalhos de sessão", async () => {
    const get = vi.spyOn(axios, "get").mockResolvedValue({ data: { euribor_12m: 2.1 } });
    await expect(obterEuribor()).resolves.toEqual({ euribor_12m: 2.1 });
    expect(get).toHaveBeenCalledWith(`${API_BASE_URL}/public/euribor`, expect.not.objectContaining({ headers: expect.anything() }));
    get.mockRestore();
  });

  it("nenhuma calculadora volta a pedir `/api/public/euribor` relativo ao frontend", () => {
    for (const f of [["components", "RiskCalculator.js"], ["components", "portal", "SimulatorCH.jsx"]]) {
      expect(semComentarios(ler(...f)), f.join("/")).not.toMatch(/fetch\(\s*["'`]\/api\/public\/euribor/);
    }
  });
});
