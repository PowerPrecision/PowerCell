/**
 * Tempo real do Portal do Cliente — lógica PURA.
 *
 * O `/api/ws/portal` é o socket dos clientes externos (ver
 * `FRONTEND_GUIDELINES.md` § 9 e, no backend,
 * `services/ws_client_identity.py`). Este módulo tem tudo o que se pode
 * decidir sem um socket aberto, para ser testável sem um: a construção do
 * URL, o que fazer com cada evento e o texto que o cliente lê.
 *
 * DUAS ARMADILHAS QUE ESTE MÓDULO EXISTE PARA NÃO SE PERDEREM
 * ===========================================================
 *
 * 1. **O evento `portal_message` NÃO é a mensagem.** O backend trunca o
 *    conteúdo a 200 caracteres (`content[:200]`, em
 *    `portal_client_messages` e `process_portal_messages`). Inserir o
 *    payload na lista como se fosse o registo deixava uma mensagem longa
 *    truncada no ecrã **para sempre**, até um refetch acidental. Por isso o
 *    evento é tratado como SINAL e a lista vem do GET.
 *
 *    É deliberadamente DIFERENTE do `utils/webmailRealtime.js`, que insere
 *    a linha sem GET — lá o evento transporta o registo completo. A
 *    diferença está no payload, não na preferência.
 *
 * 2. **O cliente recebe o eco da sua própria mensagem.** O
 *    `portal_client_messages` difunde para a sala **sem** `exclude_user_id`
 *    (ao contrário do caminho do staff). Filtrar por `sender_type` seria o
 *    reflexo errado: um processo pode ter DOIS titulares com magic links
 *    próprios, ambos `sender_type: "client"`, e filtrá-los fazia o titular 2
 *    deixar de ver as mensagens do titular 1 — uma regressão, porque o
 *    polling está parado enquanto o socket está ligado.
 *
 *    A desduplicação é por **id da mensagem**: a minha já está na lista (o
 *    POST refez o fetch), a do meu co-titular não está.
 */

/** Os dois — e só dois — eventos que o servidor entrega a um cliente. */
export const EVENTOS_DO_PORTAL = {
  MENSAGEM: "portal_message",
  PROGRESSO_GOV: "portal_gov_progress",
};

/**
 * URL do WebSocket do Portal a partir do URL base da API.
 *
 * `http` → `ws`, `https` → `wss`. Não se escreve o protocolo à mão: um
 * `ws://` contra um backend em `https` é recusado pelo browser com
 * "insecure WebSocket", e em produção isso só aparece no browser do cliente.
 *
 * @param {string} baseUrl - `API_BASE_URL` (ex.: `https://api.exemplo.pt`).
 * @param {string} token - O magic token do Portal (vai na query string
 *   porque a API de WebSocket do browser não permite headers).
 * @returns {string|null} `null` sem base ou sem token — sem token não há
 *   handshake possível e tentar seria um 4002 garantido.
 */
export function construirUrlDoSocket(baseUrl, token) {
  if (!baseUrl || !token) return null;
  const base = String(baseUrl).replace(/\/+$/, "");
  const comProtocolo = base.replace(/^http(s?):\/\//i, (_m, s) => (s ? "wss://" : "ws://"));
  // Uma base sem protocolo (ex.: "//api.exemplo.pt" ou "api.exemplo.pt")
  // ficaria sem esquema e o `new WebSocket` levantaria SyntaxError.
  if (!/^wss?:\/\//i.test(comProtocolo)) return null;
  return `${comProtocolo}/api/ws/portal?token=${encodeURIComponent(token)}`;
}

/**
 * Já temos esta mensagem na lista?
 *
 * A desduplicação é por `id`, não por `sender_type` — ver a armadilha 2 no
 * cabeçalho. Um evento sem `id` conta como novo: perder uma mensagem é pior
 * do que um GET a mais.
 */
export function mensagemJaConhecida(payload, mensagens) {
  const id = payload?.id;
  if (!id) return false;
  return (mensagens || []).some((m) => m?.id === id);
}

/**
 * Motivos de falha da recolha no Estado → texto para o cliente.
 *
 * O conjunto é FECHADO e vem do backend (`portal_gov_fetch`
 * `MOTIVOS_VISIVEIS_AO_CLIENTE`), que já colapsa os erros internos em
 * `indisponivel` para não expor a topologia do sistema. Aqui só se traduz.
 *
 * Um motivo desconhecido cai no texto genérico: um `motivo` novo do backend
 * nunca aparece cru no ecrã de um cliente.
 */
export const TEXTOS_DOS_MOTIVOS = {
  credenciais_invalidas:
    "As credenciais do Portal das Finanças não foram aceites. Verifique-as e tente novamente.",
  confirmacao_necessaria:
    "É necessário confirmar o acesso na sua app das Finanças para continuarmos.",
  confirmacao_expirada:
    "O pedido de confirmação expirou. Pode voltar a tentar quando quiser.",
  confirmacao_incorreta:
    "O código de confirmação não estava correcto. Tente novamente.",
  indisponivel:
    "Não foi possível obter os documentos neste momento. O seu consultor já foi avisado.",
};

const TEXTO_GENERICO_DE_FALHA = TEXTOS_DOS_MOTIVOS.indisponivel;

/**
 * O que mostrar ao cliente para um evento `portal_gov_progress`.
 *
 * @returns {{tipo: "sucesso"|"erro", texto: string, recarregarDocumentos: boolean}}
 */
export function avisoDoProgressoGov(payload) {
  const origem = payload?.source || "";
  const entidade = origem.includes("seguranca_social")
    ? "da Segurança Social"
    : "das Finanças";

  if (payload?.estado === "falhou") {
    return {
      tipo: "erro",
      texto: TEXTOS_DOS_MOTIVOS[payload?.motivo] || TEXTO_GENERICO_DE_FALHA,
      recarregarDocumentos: false,
    };
  }

  const quantos = Number(payload?.documents_count) || 0;
  const plural = quantos === 1 ? "documento" : "documentos";
  return {
    tipo: "sucesso",
    texto:
      quantos > 0
        ? `Recebemos ${quantos} ${plural} ${entidade}.`
        : `A recolha ${entidade} terminou sem documentos novos.`,
    // Só se recarrega a lista quando há de facto algo novo — recarregar por
    // zero documentos é um pedido para não mostrar diferença nenhuma.
    recarregarDocumentos: quantos > 0,
  };
}

/**
 * A decisão de alto nível para um envelope recebido.
 *
 * Separado do hook de propósito: é isto que se testa sem abrir sockets, e é
 * aqui que se lê, num sítio só, tudo o que o cliente faz com o tempo real.
 *
 * @param {{type?: string, data?: Object}} envelope - `create_ws_message` do
 *   servidor: `{type, data, timestamp}`.
 * @param {{mensagens?: Array}} estado
 * @returns {{recarregarMensagens: boolean, recarregarDocumentos: boolean,
 *   aviso: null|{tipo: string, texto: string}}}
 */
export function decidirDoEvento(envelope, estado = {}) {
  const semEfeito = {
    recarregarMensagens: false,
    recarregarDocumentos: false,
    aviso: null,
  };

  const tipo = envelope?.type;
  const payload = envelope?.data || {};

  if (tipo === EVENTOS_DO_PORTAL.MENSAGEM) {
    // Sinal, não registo (armadilha 1). E desduplicado por id (armadilha 2).
    if (mensagemJaConhecida(payload, estado.mensagens)) return semEfeito;
    return { ...semEfeito, recarregarMensagens: true };
  }

  if (tipo === EVENTOS_DO_PORTAL.PROGRESSO_GOV) {
    const aviso = avisoDoProgressoGov(payload);
    return {
      recarregarMensagens: false,
      recarregarDocumentos: aviso.recarregarDocumentos,
      aviso: { tipo: aviso.tipo, texto: aviso.texto },
    };
  }

  // Qualquer outro evento não tem efeito nenhum. Não é defesa a mais: o
  // servidor retém os eventos internos por uma lista de permissão, e um
  // handler para eles aqui seria código morto que sugere que chegam.
  return semEfeito;
}
