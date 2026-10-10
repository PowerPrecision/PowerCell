/**
 * Gerador da vista noturna do Portal do Cliente.
 *
 * O Portal escreve as cores com classes Tailwind CRUAS (`bg-white`,
 * `text-gray-700`, `border-emerald-200`…) — o `dark:` do Tailwind não as
 * alcança, e reescrever ~900 ocorrências para tokens semânticos é uma
 * refactorização que não cabe numa "vista noturna". Em vez disso, gera-se um
 * ficheiro CSS com uma sobreposição por cada classe de cor usada, ACTIVA SÓ
 * sob `html.portal-ativo.dark` (o CRM nunca a vê).
 *
 * O CSS é um PRODUTO deste módulo: `portalEscuro.css` não se edita à mão.
 * `portalEscuro.test.js` falha se o ficheiro committed divergir do que sai
 * daqui para as classes que as fontes do Portal usam hoje — uma classe de cor
 * nova no Portal sem sobreposição é um ecrã com texto claro em fundo claro no
 * modo noturno, e isso não dá erro em lado nenhum.
 *
 * Regenerar: `yarn gerar:portal-escuro`.
 */

/** Fontes do Portal analisadas (relativas a `src/`). */
export const FICHEIROS_DO_PORTAL = ["pages/ClientPortal.jsx"];
export const PASTAS_DO_PORTAL = ["components/portal"];

const CORES = [
  "white", "black", "gray", "slate", "zinc", "neutral", "stone", "red", "orange", "amber",
  "yellow", "lime", "green", "emerald", "teal", "cyan", "sky", "blue", "indigo", "violet",
  "purple", "fuchsia", "pink", "rose",
];
const NEUTRAS = new Set(["gray", "slate", "zinc", "neutral", "stone"]);
const PREFIXOS = ["bg", "text", "border", "ring", "from", "via", "to", "divide", "placeholder"];
const MODIFICADORES_SUPORTADOS = { hover: ":hover", focus: ":focus" };

const PADRAO = new RegExp(
  `(?<![\\w:/-])((?:[a-z-]+:)*(?:${PREFIXOS.join("|")})-(?:${CORES.join("|")})(?:-\\d{2,3})?(?:/\\d+)?)(?![\\w-])`,
  "g",
);

/** rgb de cada cor no tom 500 (a base das translúcidas) e os tons claros (texto). */
const BASE_500 = {
  red: [239, 68, 68], orange: [249, 115, 22], amber: [245, 158, 11], yellow: [234, 179, 8],
  lime: [132, 204, 22], green: [34, 197, 94], emerald: [16, 185, 129], teal: [20, 184, 166],
  cyan: [6, 182, 212], sky: [14, 165, 233], blue: [59, 130, 246], indigo: [99, 102, 241],
  violet: [139, 92, 246], purple: [168, 85, 247], fuchsia: [217, 70, 239], pink: [236, 72, 153],
  rose: [244, 63, 94],
};
const TOM_400 = {
  red: [248, 113, 113], orange: [251, 146, 60], amber: [251, 191, 36], yellow: [250, 204, 21],
  lime: [163, 230, 53], green: [74, 222, 128], emerald: [52, 211, 153], teal: [45, 212, 191],
  cyan: [34, 211, 238], sky: [56, 189, 248], blue: [96, 165, 250], indigo: [129, 140, 248],
  violet: [167, 139, 250], purple: [192, 132, 252], fuchsia: [232, 121, 249], pink: [244, 114, 182],
  rose: [251, 113, 133],
};
const TOM_300 = {
  red: [252, 165, 165], orange: [253, 186, 116], amber: [252, 211, 77], yellow: [253, 224, 71],
  lime: [190, 242, 100], green: [134, 239, 172], emerald: [110, 231, 183], teal: [94, 234, 212],
  cyan: [103, 232, 249], sky: [125, 211, 252], blue: [147, 197, 253], indigo: [165, 180, 252],
  violet: [196, 181, 253], purple: [216, 180, 254], fuchsia: [240, 171, 252], pink: [249, 168, 212],
  rose: [253, 164, 175],
};

const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));

// Neutros: a escala é INVERTIDA (o que era claro fica escuro e vice-versa).
const FUNDO_NEUTRO = { white: hex("#111827"), 50: hex("#1a2332"), 100: hex("#1f2937"), 200: hex("#374151"), 300: hex("#4b5563") };
const FUNDO_DE_GRADIENTE_NEUTRO = { white: hex("#111827"), 50: hex("#0b1220"), 100: hex("#111827"), 200: hex("#1f2937") };
const BORDA_NEUTRA = { white: hex("#374151"), 50: hex("#1f2937"), 100: hex("#1f2937"), 200: hex("#374151"), 300: hex("#4b5563") };
const TEXTO_NEUTRO = {
  900: hex("#f9fafb"), 800: hex("#f3f4f6"), 700: hex("#e5e7eb"), 600: hex("#d1d5db"),
  // 500 e 400 eram cinzentos de apoio (ícones, ajudas): em fundo escuro têm de
  // continuar legíveis (≥ 4,5:1), por isso sobem em vez de se inverterem.
  500: hex("#9ca3af"), 400: hex("#8b94a3"), 300: hex("#8b94a3"), 200: hex("#8b94a3"),
};

// Cores: tons claros (50–300) viram translúcidos da cor 500; texto escuro vira claro.
const ALFA_FUNDO = { 50: 0.12, 100: 0.2, 200: 0.3, 300: 0.4 };
const ALFA_BORDA = { 50: 0.2, 100: 0.25, 200: 0.35, 300: 0.45 };

/** `[r,g,b,a]` ou `null` (sem sobreposição: a classe mantém-se como está). */
export function corEscura({ prefixo, cor, tom, alfa }) {
  const multiplicar = (a) => (alfa == null ? a : Number((a * alfa).toFixed(3)));
  const chave = tom ?? "white";

  if (cor === "white") {
    if (prefixo === "bg" || prefixo === "from" || prefixo === "to" || prefixo === "via") {
      const tabela = prefixo === "bg" ? FUNDO_NEUTRO : FUNDO_DE_GRADIENTE_NEUTRO;
      return [...tabela.white, multiplicar(1)];
    }
    if (prefixo === "border") return [...BORDA_NEUTRA.white, multiplicar(1)];
    if (prefixo === "ring") return [...FUNDO_NEUTRO.white, multiplicar(1)];
    return null; // text-white fica branco
  }
  if (cor === "black") return null;

  if (NEUTRAS.has(cor)) {
    const tabela = {
      bg: FUNDO_NEUTRO, from: FUNDO_DE_GRADIENTE_NEUTRO, to: FUNDO_DE_GRADIENTE_NEUTRO,
      via: FUNDO_DE_GRADIENTE_NEUTRO, border: BORDA_NEUTRA, text: TEXTO_NEUTRO,
    }[prefixo];
    const c = tabela?.[chave];
    return c ? [...c, multiplicar(1)] : null;
  }

  const base = BASE_500[cor];
  if (!base) return null;
  if (prefixo === "bg" || prefixo === "from" || prefixo === "to" || prefixo === "via") {
    const a = ALFA_FUNDO[chave];
    return a ? [...base, multiplicar(a)] : null;
  }
  if (prefixo === "border") {
    const a = ALFA_BORDA[chave];
    return a ? [...base, multiplicar(a)] : null;
  }
  if (prefixo === "text") {
    // 500–700 escuros em fundo claro passam ao tom 400; 800–900 ao 300. O
    // 500 também: ícones e textos a vermelho/azul/violeta-500 ficam abaixo de
    // 4,5:1 sobre o cartão escuro.
    if (chave === 500 || chave === 600 || chave === 700) return [...TOM_400[cor], 1];
    if (chave === 800 || chave === 900) return [...TOM_300[cor], 1];
    return null;
  }
  return null;
}

const rgba = ([r, g, b, a]) => (a === 1 ? `rgb(${r} ${g} ${b})` : `rgb(${r} ${g} ${b} / ${a})`);
const transparente = ([r, g, b]) => `rgb(${r} ${g} ${b} / 0)`;

/** Divide `hover:bg-gray-50/70` em partes; `null` se o modificador não é suportado. */
export function analisarClasse(classe) {
  const partes = classe.split(":");
  const nucleo = partes.pop();
  const modificadores = partes;
  const m = nucleo.match(new RegExp(`^(${PREFIXOS.join("|")})-(${CORES.join("|")})(?:-(\\d{2,3}))?(?:/(\\d+))?$`));
  if (!m) return null;
  return {
    classe,
    modificadores,
    prefixo: m[1],
    cor: m[2],
    tom: m[3] ? Number(m[3]) : undefined,
    alfa: m[4] ? Number(m[4]) / 100 : undefined,
  };
}

const escapar = (classe) => classe.replace(/([:/.\\[\]()%])/g, "\\$1");

function declaracoes(prefixo, cor) {
  const valor = rgba(cor);
  switch (prefixo) {
    case "bg": return `background-color: ${valor};`;
    case "text": return `color: ${valor};`;
    case "border": return `border-color: ${valor};`;
    case "ring": return `--tw-ring-color: ${valor};`;
    case "from":
      return `--tw-gradient-from: ${valor} var(--tw-gradient-from-position); `
        + `--tw-gradient-to: ${transparente(cor)} var(--tw-gradient-to-position); `
        + "--tw-gradient-stops: var(--tw-gradient-from), var(--tw-gradient-to);";
    case "via":
      return `--tw-gradient-stops: var(--tw-gradient-from), ${valor} var(--tw-gradient-via-position), var(--tw-gradient-to);`;
    case "to": return `--tw-gradient-to: ${valor} var(--tw-gradient-to-position);`;
    default: throw new Error(`Prefixo sem suporte na vista noturna: ${prefixo}`);
  }
}

/** Extrai as classes de cor (únicas, ordenadas) de textos de código-fonte. */
export function extrairClasses(textos) {
  const achadas = new Set();
  for (const texto of textos) {
    for (const m of texto.matchAll(PADRAO)) achadas.add(m[1]);
  }
  return [...achadas].sort();
}

/** O CSS da vista noturna para este conjunto de classes. Pura e determinística. */
export function gerarCss(classes) {
  const regras = [];
  const semSobreposicao = [];
  for (const classe of [...classes].sort()) {
    const info = analisarClasse(classe);
    if (!info) throw new Error(`Classe de cor que não sei analisar: ${classe}`);
    const desconhecido = info.modificadores.find((mod) => !(mod in MODIFICADORES_SUPORTADOS));
    if (desconhecido) throw new Error(`Modificador sem suporte na vista noturna: ${desconhecido}: (${classe})`);
    const cor = corEscura(info);
    if (!cor) {
      semSobreposicao.push(classe);
      continue;
    }
    const pseudo = info.modificadores.map((mod) => MODIFICADORES_SUPORTADOS[mod]).join("");
    regras.push(`html.portal-ativo.dark .${escapar(classe)}${pseudo} { ${declaracoes(info.prefixo, cor)} }`);
  }
  return [
    "/* GERADO por src/styles/portalEscuroGerador.mjs — NÃO editar à mão (`yarn gerar:portal-escuro`).",
    " * Vista noturna do Portal do Cliente: só vale sob `html.portal-ativo.dark`.",
    ` * Classes mantidas como estão (cores vivas / já legíveis em fundo escuro): ${semSobreposicao.length}. */`,
    "html.portal-ativo.dark { color-scheme: dark; }",
    "html.portal-ativo.dark body { background-color: #0b1220; color: #e5e7eb; }",
    ...regras,
    "",
  ].join("\n");
}

export const CLASSES_SEM_SOBREPOSICAO = (classes) =>
  [...classes].filter((c) => {
    const info = analisarClasse(c);
    return info && !corEscura(info);
  }).sort();
