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

/**
 * A nota mais recente escrita por uma PESSOA — o que a Listagem de
 * Processos mostra na coluna "Notas do Consultor" (Ponto 9).
 *
 * O QUE ESTAVA A ACONTECER
 *   As duas listagens não mostravam notas nenhumas: mostravam a
 *   ATIVIDADE mais recente, e faziam-no lendo campos que o backend nunca
 *   produziu. `latest_activity_preview`, `latest_note` e
 *   `latest_activity_note` têm **zero** ocorrências em `backend/` — são
 *   nomes inventados no frontend. Na `FilteredProcessList`, onde a
 *   cascata só lia esses três, a coluna dizia "Sem notas recentes" em
 *   TODOS os processos, sempre, desde que foi escrita. Na `ProcessesPage`
 *   a cascata tinha mais sete ramos por baixo e acabava por chegar a
 *   `notes`, pelo que às vezes mostrava alguma coisa — e foi essa metade
 *   a funcionar que escondeu a outra.
 *
 *   É a armadilha do "mock com a forma inventada", desta vez em código de
 *   produção: quem escreveu a cascata assumiu o contrato em vez de o ler.
 *
 * A REGRA (Ponto 9)
 *   A listagem espelha o **Resumo**, que é o local oficial das notas do
 *   consultor. Não lê o Histórico — o Histórico passou a ser uma linha
 *   temporal do sistema, e misturar as duas coisas na mesma coluna é o
 *   que esta separação vem desfazer.
 *
 *   Deriva de `resolveProcessObservationNotes` de propósito: são os
 *   MESMOS campos, pela MESMA ordem cronológica, e por isso a coluna não
 *   pode divergir do cartão sem alguém dar por isso.
 *
 * PORQUE É QUE A IA FICA DE FORA
 *   O cartão do Resumo mostra as notas lidas pela IA com um crachá
 *   próprio, precisamente porque não têm o mesmo peso que o que um
 *   consultor escreveu. A coluna chama-se "Notas do Consultor" e não tem
 *   crachá nenhum: deixar lá entrar texto da IA seria apresentá-lo como
 *   se fosse de uma pessoa. O `ai_extracted_notes` também não vem nas
 *   projecções das listagens — e é texto livre sem limite de tamanho, que
 *   não tem de viajar em todas as linhas de uma tabela.
 *
 * @param {object} [process]
 * @returns {string} A nota mais recente, ou `""` quando não há nenhuma.
 */
export function notaMaisRecenteDoConsultor(process) {
  const daPessoa = resolveProcessObservationNotes(process).filter(
    (nota) => nota.origin !== "ai",
  );
  if (daPessoa.length === 0) return "";
  return texto(daPessoa[daPessoa.length - 1].text).trim();
}
