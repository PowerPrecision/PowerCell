/**
 * portalHub — o Hub do Portal do Cliente (D-42): um cliente, vários processos.
 *
 * O servidor devolve, no login, o `hub_token` (credencial ancorada ao CLIENTE) e a lista
 * `processos` activos. Com mais do que um, o cliente escolhe qual consulta; escolher troca o
 * token de sessão pelo DESSE processo e o resto do Portal (documentos, mensagens, perfil…) não
 * sabe que o Hub existe. Este módulo é o ponto único do que se guarda e das decisões — o
 * ecrã (`PortalHub.jsx`) e o contentor (`ClientPortal.jsx`) só chamam estas funções.
 *
 * REGRAS (cada uma tem teste):
 *  * uma lista que não seja um ARRAY é «sem processos» — `Array.isArray`, nunca `|| []`
 *    (um objecto é truthy e o erro mudava de sítio em vez de desaparecer, § 27.38);
 *  * o Hub só existe com 2+ processos: com um, entra-se directamente e não se guarda nada;
 *  * «escolhido» tem de ser um dos processos listados — um id velho no armazenamento volta a
 *    mostrar o Hub em vez de entrar num processo que já não é do cliente;
 *  * o armazenamento pode estar bloqueado (modo privado): nada aqui levanta.
 */

export const CHAVE_DO_TOKEN_DO_HUB = "portalHubToken";
export const CHAVE_DOS_PROCESSOS_DO_HUB = "portalHubProcessos";
export const CHAVE_DO_PROCESSO_ESCOLHIDO = "portalProcessoEscolhido";

/** Tudo o que o Hub guarda. É esta lista que o logout e a sessão deslizante apagam. */
export const CHAVES_DO_HUB = [
  CHAVE_DO_TOKEN_DO_HUB,
  CHAVE_DOS_PROCESSOS_DO_HUB,
  CHAVE_DO_PROCESSO_ESCOLHIDO,
];

/** Avisa o contentor de que a sessão do Portal mudou (login, escolha, logout). */
export const EVENTO_DA_SESSAO_DO_PORTAL = "portal:sessao-alterada";

export const listaDeProcessos = (valor) =>
  Array.isArray(valor)
    ? valor.filter((p) => p && typeof p === "object" && typeof p.id === "string" && p.id)
    : [];

export const temHub = (processos) => listaDeProcessos(processos).length > 1;

const ler = (chave) => {
  try {
    return window.localStorage.getItem(chave) || "";
  } catch {
    return "";
  }
};

const escrever = (chave, valor) => {
  try {
    window.localStorage.setItem(chave, valor);
  } catch {
    /* storage indisponível — o Hub simplesmente não persiste */
  }
};

export function limparHub() {
  for (const chave of CHAVES_DO_HUB) {
    try {
      window.localStorage.removeItem(chave);
    } catch {
      /* ignorar */
    }
  }
}

export function avisarMudancaDeSessao() {
  try {
    window.dispatchEvent(new Event(EVENTO_DA_SESSAO_DO_PORTAL));
  } catch {
    /* ignorar */
  }
}

/**
 * Guarda o Hub que veio numa resposta de login. Devolve `true` se há Hub.
 *
 * @param {{hub_token?: string, processos?: unknown}} resposta
 * @param {{escolhido?: string}} [opcoes] `escolhido`: o processo em que o cliente já entrou
 *   (um link a levava a um processo); vazio = ainda tem de escolher.
 */
export function guardarHub(resposta, { escolhido = "" } = {}) {
  const processos = listaDeProcessos(resposta?.processos);
  const token = typeof resposta?.hub_token === "string" ? resposta.hub_token : "";
  if (!token || processos.length < 2) {
    limparHub();
    return false;
  }
  escrever(CHAVE_DO_TOKEN_DO_HUB, token);
  escrever(CHAVE_DOS_PROCESSOS_DO_HUB, JSON.stringify(processos));
  escrever(CHAVE_DO_PROCESSO_ESCOLHIDO, escolhido || "");
  return true;
}

/** O que está guardado, já validado. */
export function lerHub() {
  let processos = [];
  try {
    processos = listaDeProcessos(JSON.parse(ler(CHAVE_DOS_PROCESSOS_DO_HUB) || "null"));
  } catch {
    processos = [];
  }
  return {
    token: ler(CHAVE_DO_TOKEN_DO_HUB),
    processos,
    escolhido: ler(CHAVE_DO_PROCESSO_ESCOLHIDO),
  };
}

/** Falta escolher? Só com token, 2+ processos e nenhum escolhido que ainda seja da lista. */
export function precisaDeEscolher(hub) {
  const processos = listaDeProcessos(hub?.processos);
  if (!hub?.token || processos.length < 2) return false;
  return !processos.some((p) => p.id === hub?.escolhido);
}

/** O cliente pode trocar de processo? (O botão «Trocar de processo» só existe então.) */
export function podeTrocarDeProcesso(hub) {
  return Boolean(hub?.token) && listaDeProcessos(hub?.processos).length > 1;
}

/** «Crédito Habitação · Power Real Estate». Sem empresa, só o tipo. */
export function rotuloDoProcesso(processo) {
  const tipo = (processo?.tipo_rotulo || "Processo").trim();
  const empresa = typeof processo?.empresa === "string" ? processo.empresa.trim() : "";
  return empresa ? `${tipo} · ${empresa}` : tipo;
}

/** A linha por baixo do título: nº do processo e fase. */
export function detalheDoProcesso(processo) {
  const partes = [];
  if (processo?.numero !== undefined && processo?.numero !== null && processo?.numero !== "") {
    partes.push(`Processo n.º ${processo.numero}`);
  }
  const estado = typeof processo?.estado_rotulo === "string" ? processo.estado_rotulo.trim() : "";
  if (estado) partes.push(estado);
  return partes.join(" · ");
}

/** Aplica a escolha: o token de sessão passa a ser o do processo escolhido. */
export function aplicarEscolha(resposta) {
  if (typeof resposta?.token !== "string" || !resposta.token || typeof resposta?.process_id !== "string") {
    return false;
  }
  escrever("portalToken", resposta.token);
  escrever("portal_token", resposta.token);
  escrever("portalProcessId", resposta.process_id);
  escrever(CHAVE_DO_PROCESSO_ESCOLHIDO, resposta.process_id);
  escrever("portalLastActivity", String(Date.now()));
  avisarMudancaDeSessao();
  return true;
}

/** «Trocar de processo»: volta ao Hub sem terminar a sessão. */
export function voltarAoHub() {
  escrever(CHAVE_DO_PROCESSO_ESCOLHIDO, "");
  avisarMudancaDeSessao();
}
