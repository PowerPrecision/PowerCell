/**
 * processLabels — etiquetas (tags) dos processos.
 *
 * O PEDIDO (Lote 5, Secção B, ponto 15)
 *   Marcadores personalizados ("Sub 35", "VIP", "Urgente") para
 *   segmentar processos, porque as fases já não chegam.
 *
 * O QUE JÁ EXISTIA
 *   `labels: List[str]` está no modelo do processo desde sempre e o
 *   `ProcessDetails` até renderiza os crachás. O que faltava era o
 *   EDITOR: o comentário no código dizia que a edição tinha sido
 *   "movida para um Dialog accionado pelo botão +" — esse Dialog nunca
 *   chegou a ser construído. O PACOTE DD removeu o cartão de Etiquetas
 *   e o substituto ficou por fazer, o que deixou o campo só acessível
 *   pela API.
 *
 * PORQUE É QUE A COR DERIVA DO TEXTO
 *   Guardar a cor obrigaria a uma segunda colecção de definições de
 *   etiqueta, ou a mudar `labels` para objectos — migrando os dados e
 *   todas as projecções. Derivá-la dá a mesma garantia sem nada para
 *   manter: "VIP" é da mesma cor em todos os ecrãs porque é a mesma
 *   palavra, não porque alguém a configurou igual em dois sítios.
 *
 * A NORMALIZAÇÃO ESPELHA A DO BACKEND (`services/process_labels.py`).
 * Divergirem daria um editor que aceita o que a API recusa.
 *
 * @module utils/processLabels
 */

/** Uma etiqueta é um marcador, não um campo de notas. */
export const MAX_COMPRIMENTO = 40;
/** Acima disto deixa de segmentar e passa a ser ruído no cabeçalho. */
export const MAX_ETIQUETAS = 20;

/**
 * Paleta de crachás. Tokens semânticos do Shadcn — a regra ESLint do
 * PACOTE 11 bloqueia cores Tailwind cruas, e um crachá com
 * `bg-blue-500` fica ilegível em dark mode.
 */
const PALETA = [
  "bg-primary/10 text-primary border-primary/20",
  "bg-secondary text-secondary-foreground border-border",
  "bg-accent text-accent-foreground border-border",
  "bg-muted text-muted-foreground border-border",
  "bg-destructive/10 text-destructive border-destructive/20",
];

const chave = (valor) => String(valor ?? "").trim().toLowerCase();

/**
 * Etiquetas limpas, sem repetições e em número comportável.
 *
 * Compara sem olhar à capitalização mas preserva a forma da primeira
 * ocorrência. Devolve sempre uma lista — vazia é uma resposta legítima
 * (limpar as etiquetas), não um erro.
 *
 * @param {string|Array} [valor]
 * @returns {string[]}
 */
export function normalizarEtiquetas(valor) {
  let cruas;
  if (typeof valor === "string") cruas = valor.split(",");
  else if (Array.isArray(valor)) cruas = valor;
  else return [];

  const etiquetas = [];
  const vistas = new Set();
  for (const crua of cruas) {
    if (crua == null) continue;
    const texto = String(crua).trim().slice(0, MAX_COMPRIMENTO).trim();
    if (!texto) continue;
    const k = chave(texto);
    if (vistas.has(k)) continue;
    vistas.add(k);
    etiquetas.push(texto);
    if (etiquetas.length >= MAX_ETIQUETAS) break;
  }
  return etiquetas;
}

/**
 * Classes do crachá de uma etiqueta, derivadas do próprio texto.
 *
 * Usa a chave normalizada: "VIP" e " vip " são a MESMA etiqueta depois
 * de normalizadas e não podem aparecer de cores diferentes.
 *
 * @param {string} [etiqueta]
 * @returns {string}
 */
export function corDaEtiqueta(etiqueta) {
  const k = chave(etiqueta);
  let hash = 0;
  for (let i = 0; i < k.length; i += 1) {
    hash = (hash * 31 + k.charCodeAt(i)) % 100000;
  }
  return PALETA[hash % PALETA.length];
}

/**
 * Se uma etiqueta pode ser acrescentada, e porquê não.
 *
 * O motivo não é decorativo: um botão que não faz nada e não diz porquê
 * é o silêncio do Bug 1 outra vez, noutro sítio.
 *
 * @param {string[]} existentes
 * @param {string} candidata
 * @returns {{ok: true, etiqueta: string} | {ok: false, motivo: string}}
 */
export function podeAcrescentar(existentes, candidata) {
  const actuais = normalizarEtiquetas(existentes);
  const [etiqueta] = normalizarEtiquetas([candidata]);

  if (!etiqueta) return { ok: false, motivo: "Escreva o nome da etiqueta." };
  if (actuais.some((e) => chave(e) === chave(etiqueta))) {
    return { ok: false, motivo: `A etiqueta "${etiqueta}" já está neste processo.` };
  }
  if (actuais.length >= MAX_ETIQUETAS) {
    return { ok: false, motivo: `Máximo de ${MAX_ETIQUETAS} etiquetas por processo.` };
  }
  return { ok: true, etiqueta };
}
