/**
 * Ponto 8, Fase 3 — os separadores por Empresa (regras puras).
 *
 * PORQUÊ SEPARADORES: o Webmail misturava as empresas num dropdown de
 * contas e obrigava a trocar de perfil no Context Switcher para ver a
 * caixa certa. Um separador por empresa resolve o problema do
 * multi-perfil POR DESENHO: a empresa deixa de ser um estado escondido
 * do cabeçalho e passa a ser o sítio onde se está.
 *
 * A lista vem de `GET /emails/webmail/companies` — as empresas onde o
 * utilizador tem um UCR válido. Nenhum separador pode nomear uma
 * empresa que ele não tenha, e o backend devolve 404 a quem tentar
 * (Fase 1): o isolamento não depende desta camada, mas também não a
 * contradiz.
 */

/**
 * Vale a pena desenhar a barra de separadores?
 *
 * Com uma empresa só, não: um separador solitário é ruído puro e rouba
 * uma linha de ecrã à caixa de correio. Mostra-se a caixa directamente.
 */
export function deveMostrarSeparadores(empresas) {
  return (Array.isArray(empresas) ? empresas : []).length > 1;
}

/**
 * Qual o separador activo.
 *
 * Uma empresa pedida (URL, sessão anterior) só vale se ainda constar da
 * lista: um `company_id` guardado de um acesso que já não existe levaria
 * a pedidos que o backend recusa com 404, e o utilizador via uma caixa
 * vazia sem perceber porquê. Cai na primeira empresa.
 *
 * @returns {?object} a empresa activa, ou `null` se não houver nenhuma
 */
export function resolverEmpresaActiva(empresas, pedida) {
  const lista = (Array.isArray(empresas) ? empresas : []).filter(
    (e) => e && e.company_id,
  );
  if (!lista.length) return null;

  const alvo = typeof pedida === "string" ? pedida.trim() : "";
  if (alvo) {
    const encontrada = lista.find((e) => e.company_id === alvo);
    if (encontrada) return encontrada;
  }
  return lista[0];
}

/** Rótulo de um separador — nunca um id cru onde se espera um nome. */
export function rotuloDaEmpresa(empresa) {
  if (!empresa) return "";
  const nome = (empresa.company_name || "").trim();
  return nome || (empresa.company_id || "").trim();
}

/**
 * Minutos inteiros entre duas datas — `null` quando a data não se lê.
 *
 * Um resultado NEGATIVO é possível (relógio do cliente adiantado) e cai
 * de propósito no ramo "Actualizado agora" de quem chama: `minutos < 1`
 * já o cobre. Tive aqui uma guarda `diff < 0 → 0` que nenhuma mutação
 * conseguia matar — porque não mudava nada. Código defensivo que nenhum
 * teste pode derrubar é código morto, e código morto mente sobre o que
 * o programa faz.
 */
function minutosDesde(data, agora) {
  const inicio = data instanceof Date ? data.getTime() : Number(data);
  if (!Number.isFinite(inicio)) return null;
  const fim = agora instanceof Date ? agora.getTime() : Date.now();
  return Math.floor((fim - inicio) / 60000);
}

/**
 * Estado da sincronização, em texto curto.
 *
 * Substitui o botão "Sincronizar" de largura total que ocupava a barra
 * lateral. A sincronização é uma operação de fundo: o que o utilizador
 * precisa de saber é se está actualizada, e isso cabe numa linha.
 *
 * @returns {{estado: string, texto: string, emCurso: boolean}}
 */
export function estadoDaSincronizacao({ syncing, ultimaSinc, agora } = {}) {
  if (syncing) {
    return { estado: "a-sincronizar", texto: "A sincronizar…", emCurso: true };
  }

  const minutos = ultimaSinc ? minutosDesde(ultimaSinc, agora) : null;
  if (minutos === null) {
    // Nunca sincronizou nesta sessão. Não é um erro — é o estado normal
    // ao abrir a página —, por isso não se pinta de vermelho.
    return { estado: "por-sincronizar", texto: "Por sincronizar", emCurso: false };
  }
  if (minutos < 1) {
    return { estado: "actualizado", texto: "Actualizado agora", emCurso: false };
  }
  if (minutos < 60) {
    return {
      estado: "actualizado",
      texto: `Actualizado há ${minutos} min`,
      emCurso: false,
    };
  }
  const horas = Math.floor(minutos / 60);
  return {
    estado: "desactualizado",
    texto: `Actualizado há ${horas}h`,
    emCurso: false,
  };
}
