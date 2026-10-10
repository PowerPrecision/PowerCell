/**
 * A vista noturna do Portal do Cliente: o CSS committed tem de ser o que o
 * gerador produz das classes que as fontes do Portal usam HOJE.
 *
 * Sem esta guarda, uma classe de cor nova no Portal (`bg-sky-50`, `text-gray-900`)
 * ficava sem sobreposição e, em vista noturna, era texto escuro em fundo escuro
 * (ou um cartão branco no meio de um ecrã escuro) — sem um erro em lado nenhum.
 */
import { describe, expect, it } from "vitest";

import { readFileSync } from "node:fs";
import { join } from "node:path";
import {
  CLASSES_SEM_SOBREPOSICAO,
  analisarClasse,
  corEscura,
  extrairClasses,
  gerarCss,
} from "./portalEscuroGerador.mjs";

// Lido do disco: o Vite trata um `.css` importado (mesmo com `?raw`) como folha de estilos.
const css = readFileSync(join(process.cwd(), "src", "styles", "portalEscuro.css"), "utf-8");

const fontes = import.meta.glob(
  ["../pages/ClientPortal.jsx", "../components/portal/*.jsx", "!../components/portal/**/*.test.*"],
  { query: "?raw", import: "default", eager: true },
);
const textos = Object.values(fontes);
const classes = extrairClasses(textos);

const luminancia = ([r, g, b]) => {
  const c = [r, g, b].map((v) => {
    const x = v / 255;
    return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
};
const contraste = (a, b) => {
  const [maior, menor] = [luminancia(a), luminancia(b)].sort((x, y) => y - x);
  return (maior + 0.05) / (menor + 0.05);
};
const CARTAO_ESCURO = [17, 24, 39]; // #111827 (bg-white)
const CAIXA_INTERIOR = [31, 41, 55]; // #1f2937 (bg-gray-100)

describe("o leitor das classes lê mesmo as fontes do Portal", () => {
  it("encontra o Portal e os seus componentes", () => {
    expect(Object.keys(fontes).some((f) => f.endsWith("ClientPortal.jsx"))).toBe(true);
    expect(Object.keys(fontes).length).toBeGreaterThanOrEqual(5);
    expect(Object.keys(fontes).some((f) => f.includes(".test."))).toBe(false);
  });

  it("encontra as classes conhecidas, com modificadores", () => {
    expect(classes.length).toBeGreaterThan(100);
    for (const esperada of ["bg-white", "text-gray-800", "border-gray-100", "hover:bg-gray-50", "from-gray-50"]) {
      expect(classes).toContain(esperada);
    }
  });
});

describe("o CSS committed é o que o gerador produz", () => {
  it("está em dia com as classes usadas hoje (yarn gerar:portal-escuro)", () => {
    expect(css).toBe(gerarCss(classes));
  });

  it("é determinístico", () => {
    expect(gerarCss([...classes].reverse())).toBe(gerarCss(classes));
  });
});

describe("só vale no Portal e só em vista noturna", () => {
  const regras = css.split("\n").filter((l) => l.startsWith("html.") || l.startsWith("."));

  it("toda a regra está sob html.portal-ativo.dark (o CRM nunca a vê)", () => {
    expect(regras.length).toBeGreaterThan(80);
    for (const regra of regras) expect(regra.startsWith("html.portal-ativo.dark")).toBe(true);
  });

  it("não há nenhuma regra solta fora desse âmbito", () => {
    const seletores = css.replace(/\/\*[\s\S]*?\*\//g, "").match(/^[^{\n]+(?=\{)/gm) ?? [];
    for (const s of seletores) expect(s.trim().startsWith("html.portal-ativo.dark")).toBe(true);
  });
});

describe("legibilidade em fundo escuro", () => {
  const texto = classes.map(analisarClasse).filter((c) => c && c.prefixo === "text");

  it("todo o texto sobreposto tem contraste AA (≥ 4,5:1) sobre o cartão e sobre a caixa interior", () => {
    let verificadas = 0;
    for (const info of texto) {
      const cor = corEscura(info);
      if (!cor) continue;
      verificadas += 1;
      expect(contraste(cor, CARTAO_ESCURO), info.classe).toBeGreaterThanOrEqual(4.5);
      expect(contraste(cor, CAIXA_INTERIOR), info.classe).toBeGreaterThanOrEqual(4.5);
    }
    expect(verificadas).toBeGreaterThan(20);
  });

  it("nenhum texto ESCURO fica por sobrepor (só brancos e tons 300–400 se mantêm)", () => {
    for (const info of texto) {
      if (corEscura(info)) continue;
      const aceitavel = info.cor === "white" || info.tom === 300 || info.tom === 400;
      expect(aceitavel, `${info.classe} ficaria escuro sobre fundo escuro`).toBe(true);
    }
  });

  it("os fundos claros (white, 50–200) todos escurecem", () => {
    const claros = classes
      .map(analisarClasse)
      .filter((c) => c && c.prefixo === "bg" && (c.cor === "white" || (c.tom != null && c.tom <= 200)));
    expect(claros.length).toBeGreaterThan(10);
    for (const info of claros) {
      const cor = corEscura(info);
      expect(cor, `${info.classe} ficaria claro em vista noturna`).not.toBeNull();
    }
  });

  it("bordas claras (50–300) também escurecem", () => {
    const bordas = classes
      .map(analisarClasse)
      .filter((c) => c && c.prefixo === "border" && c.tom != null && c.tom <= 300);
    for (const info of bordas) expect(corEscura(info), info.classe).not.toBeNull();
  });
});

describe("o gerador recusa o que não sabe tratar (em vez de o ignorar em silêncio)", () => {
  it("um modificador novo falha", () => {
    expect(() => gerarCss(["sm:bg-white"])).toThrow(/Modificador sem suporte/);
    expect(() => gerarCss(["group-hover:text-gray-700"])).toThrow(/Modificador sem suporte/);
  });

  it("uma classe que não analisa falha", () => {
    expect(() => gerarCss(["bg-nada"])).toThrow();
  });

  it("uma classe com sobreposição gera a regra com o âmbito", () => {
    expect(gerarCss(["bg-white"])).toContain("html.portal-ativo.dark .bg-white { background-color: rgb(17 24 39); }");
  });

  it("hover e foco usam a pseudo-classe", () => {
    const gerado = gerarCss(["hover:bg-gray-50", "focus:ring-white"]);
    expect(gerado).toContain(".hover\\:bg-gray-50:hover");
    expect(gerado).toContain(".focus\\:ring-white:focus");
  });

  it("o alfa multiplica (bg-white/70) e a barra é escapada", () => {
    expect(gerarCss(["bg-white/70"])).toContain(".bg-white\\/70 { background-color: rgb(17 24 39 / 0.7); }");
  });

  it("os gradientes redefinem as três variáveis", () => {
    const g = gerarCss(["from-gray-50"]);
    expect(g).toContain("--tw-gradient-from:");
    expect(g).toContain("--tw-gradient-to:");
    expect(g).toContain("--tw-gradient-stops:");
  });

  it("cores vivas (botões sólidos, texto branco) não são tocadas", () => {
    const sem = CLASSES_SEM_SOBREPOSICAO(["bg-emerald-600", "text-white", "bg-indigo-600", "bg-red-500"]);
    expect(sem).toEqual(["bg-emerald-600", "bg-indigo-600", "bg-red-500", "text-white"].sort());
  });
});
