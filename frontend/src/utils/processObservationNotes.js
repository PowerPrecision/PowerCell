/**
 * processObservationNotes — o texto livre do processo, todo ele.
 *
 * O DEFEITO QUE ISTO FECHA (Lote 5, Secção B, ponto 14)
 *   O Resumo do processo tem de mostrar o contexto que as pessoas
 *   escreveram, sem as obrigar a procurá-lo noutros ecrãs. Havia TRÊS
 *   sítios onde esse texto vive e o Resumo lia um e meio:
 *
 *   - `observation_notes` — o feed, escrito no cartão do Resumo.
 *   - `notes` / `observations` — o escalar legado, e é ali que o modal do
 *     Kanban (`ProcessDetailsModal`) ainda escreve HOJE.
 *   - `ai_extracted_notes` — o que a IA leu dos documentos, visível só no
 *     modal do Kanban.
 *
 *   A função fazia `if (feed.length > 0) return feed;`: tratava o escalar
 *   como FALLBACK. Bastava alguém acrescentar uma nota no Resumo para o
 *   que tinha sido escrito no Kanban desaparecer de vez — sem apagar
 *   nada, apenas deixando de o ler.
 *
 * A REGRA
 *   Juntar, não escolher. Cada nota diz de onde vem (`origin`), a
 *   duplicação é apanhada pelo texto normalizado (o backend sincroniza
 *   `notes` e `observations`, e o modal do Kanban chegou a copiar a
 *   última nota do feed para o escalar) e nada é descartado em silêncio.
 *
 * @module utils/processObservationNotes
 */

const texto = (valor) => (valor == null ? "" : String(valor));
const chave = (valor) => texto(valor).trim().toLowerCase();

const comData = (nota) => {
  const d = nota.created_at ? new Date(nota.created_at) : null;
  return d && !Number.isNaN(d.getTime()) ? d.getTime() : null;
};

/**
 * Todas as notas de texto livre de um processo, por ordem cronológica.
 *
 * @param {object} [process]
 * @returns {Array<{id, text, created_at, user_id, user_name, origin}>}
 *   `origin`: `"feed"` (cartão do Resumo) · `"legacy"` (escalar, hoje
 *   escrito pelo modal do Kanban) · `"ai"` (lido dos documentos).
 */
export function resolveProcessObservationNotes(process) {
  if (!process || typeof process !== "object") return [];

  const notas = [];
  const vistos = new Set();

  const acrescentar = (nota) => {
    const t = texto(nota.text);
    if (!t.trim()) return;
    const k = chave(t);
    if (vistos.has(k)) return;
    vistos.add(k);
    notas.push({ ...nota, text: t });
  };

  const feed = Array.isArray(process.observation_notes) ? process.observation_notes : [];
  for (const nota of feed) {
    if (!nota || typeof nota !== "object") continue;
    acrescentar({
      id: nota.id,
      text: nota.text,
      created_at: nota.created_at ?? null,
      user_id: nota.user_id ?? null,
      user_name: nota.user_name ?? null,
      origin: "feed",
    });
  }

  // O escalar legado. `notes` e `observations` são sincronizados pelo
  // backend — normalmente são o mesmo texto e a deduplicação trata
  // disso; quando divergem, os dois são coisas que alguém escreveu.
  for (const campo of ["observations", "notes"]) {
    acrescentar({
      id: `legacy-${campo}`,
      text: process[campo],
      created_at: process.updated_at || process.created_at || null,
      user_id: null,
      user_name: null,
      origin: "legacy",
    });
  }

  acrescentar({
    id: "ai",
    text: process.ai_extracted_notes,
    created_at: process.updated_at || process.created_at || null,
    user_id: null,
    user_name: null,
    origin: "ai",
  });

  // Cronológico, com as notas sem data a manter a ordem em que vieram
  // (uma nota sem data é antiga ou é legada — empurrá-la para o fim
  // fá-la-ia passar por recente).
  return notas
    .map((nota, indice) => ({ nota, indice, quando: comData(nota) }))
    .sort((a, b) => {
      if (a.quando === null && b.quando === null) return a.indice - b.indice;
      if (a.quando === null) return -1;
      if (b.quando === null) return 1;
      if (a.quando === b.quando) return a.indice - b.indice;
      return a.quando - b.quando;
    })
    .map(({ nota }) => nota);
}
