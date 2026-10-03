/**
 * De quem é este evento, e para onde se vai a partir dele (Lote 7, ponto 3).
 *
 * O QUE A AUDITORIA ENCONTROU
 * ===========================
 * O backend devolve `client_name` em cada linha do calendário desde o Pacote
 * DQ — e o ecrã **quase não o usava**:
 *
 * * o chip da grelha mostrava `[Responsável] Título`. Num calendário de
 *   equipa, doze «Escritura» num dia não dizem de quem são: o nome do
 *   responsável responde «quem trata», não «de quem é»;
 * * o nome do cliente aparecia só no painel do dia seleccionado, como texto
 *   morto — **não havia como chegar à ficha**. O utilizador lia o nome,
 *   abria a pesquisa e procurava à mão.
 *
 * As duas peças são separadas de propósito: `etiquetaDoCliente` é o que se
 * MOSTRA, `rotaDaFicha` é para onde se VAI. É a regra do `nomeVisivel` do
 * Explorador — o nome que se mostra nunca é o que se usa para operar.
 *
 * A ROTA PREFERE O PROCESSO
 * =========================
 * Um evento de processo abre a ficha do processo (`/processo/{id}`), que é
 * onde está a documentação, a timeline e os prazos. Só quando não há
 * processo — um cliente da Pool, que é precisamente quem vive sozinho — se
 * cai na ficha do cliente (`/cliente/{id}`). Sem id nenhum devolve `null`, e
 * **quem recebe `null` não desenha a ligação**: um link que não leva a
 * lado nenhum é pior do que texto.
 */

/** Uma ausência/férias não é de um cliente — é de uma pessoa. */
export function eEventoDeCliente(evento) {
  if (!evento) return false;
  const tipo = String(evento.type || "").toLowerCase();
  if (["absence", "ausencia", "ausência", "ferias", "férias"].includes(tipo)) {
    return false;
  }
  return Boolean(evento.process_id || evento.client_id);
}

/**
 * O nome do cliente a mostrar, ou "" quando não há cliente.
 *
 * `"Evento Geral"` e `"Ausência"` são os recuos que o BACKEND escreve em
 * `client_name` quando não há processo (`_enrich_calendar_rows`). Mostrá-los
 * como se fossem um cliente punha «Evento Geral» debaixo de cada bloco de
 * agenda — daí entrarem na lista de recuos e não no ecrã.
 */
const RECUOS_DO_SERVIDOR = new Set(["evento geral", "ausência", "ausencia"]);

export function etiquetaDoCliente(evento) {
  if (!eEventoDeCliente(evento)) return "";
  const nome = String(evento?.client_name || "").trim();
  if (!nome || RECUOS_DO_SERVIDOR.has(nome.toLowerCase())) return "";
  return nome;
}

/**
 * A rota da ficha, ou `null`.
 *
 * Prefere o PROCESSO (é onde está a documentação e a timeline); o cliente é
 * o recuo para quem vive na Pool sem processo.
 */
export function rotaDaFicha(evento) {
  if (!eEventoDeCliente(evento)) return null;
  const processo = String(evento?.process_id || "").trim();
  if (processo) return `/processo/${encodeURIComponent(processo)}`;
  const cliente = String(evento?.client_id || "").trim();
  if (cliente) return `/cliente/${encodeURIComponent(cliente)}`;
  return null;
}

/** O texto do botão de navegação — diz o destino, não «ver». */
export function textoDaFicha(evento) {
  const processo = String(evento?.process_id || "").trim();
  return processo ? "Abrir processo" : "Abrir ficha do cliente";
}

/**
 * O que o chip da grelha mostra, por ordem de utilidade.
 *
 * Num calendário de equipa a pergunta é «de quem é isto?», logo o CLIENTE
 * vem primeiro e o título a seguir. Na agenda pessoal o utilizador já sabe
 * que é dele e o título é o que importa — mostrar o cliente duas vezes
 * (no chip e no painel) só gasta a largura da célula.
 */
export function resumoDoChip(evento, { isTeamView = false } = {}) {
  const titulo = String(evento?.title || "Agendamento").trim() || "Agendamento";
  const cliente = etiquetaDoCliente(evento);
  if (!cliente) return titulo;
  if (!isTeamView) return titulo;
  // O título costuma repetir o nome («Escritura Ana Martins»); repeti-lo
  // outra vez à frente desperdiça a célula e lê-se mal.
  if (titulo.toLowerCase().includes(cliente.toLowerCase())) return titulo;
  return `${cliente} · ${titulo}`;
}
