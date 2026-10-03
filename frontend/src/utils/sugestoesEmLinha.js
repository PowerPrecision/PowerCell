/**
 * Preenchimento em linha das sugestões da IA (Lote 3, ponto 1).
 *
 * O QUE MUDA
 * O resultado da extracção vivia num diálogo sobreposto (`AIReviewDialog`):
 * o consultor lia pares «Atual → Sugerido» numa janela que TAPAVA a ficha,
 * decidia tudo de uma vez e só depois via o efeito. Duas consequências:
 *   · para comparar com o resto da ficha tinha de fechar o diálogo;
 *   · a decisão era um bloco — aceitar sete campos para corrigir um.
 *
 * Agora a sugestão aparece NO campo, com destaque e com aprovar/rejeitar ao
 * lado. O valor vê-se no sítio onde vai ficar, ao lado dos campos vizinhos
 * que lhe dão contexto.
 *
 * A REGRA DE OURO NÃO MUDA — E É O QUE ESTE MÓDULO PROTEGE
 * «A IA nunca grava dados pessoais ou financeiros sem confirmação.» Mostrar
 * um valor sugerido **não é gravá-lo**: o que o input desenha é o valor
 * PENDENTE, e o que vai no payload é o que `valoresAprovados` devolve. É
 * essa a distinção que torna o preenchimento em linha seguro em vez de uma
 * escrita automática com um passo decorativo por cima — e é por isso que
 * `valorAMostrar` e `valoresAprovados` são funções diferentes.
 *
 * Um campo rejeitado **não volta** ao estado pendente: o consultor já
 * respondeu. Repor a pergunta a cada render fazia o ecrã perguntar a mesma
 * coisa para sempre.
 */

export const PENDENTE = "pendente";
export const APROVADA = "aprovada";
export const REJEITADA = "rejeitada";

/**
 * Cria o conjunto de sugestões a partir do que a extracção devolveu.
 *
 * Recebe a `revisao` de `prepararRevisaoDaExtraccao` (o módulo que já
 * separa conflitos de valores novos) — não se reimplementa essa separação
 * aqui, porque é ela que o guarda da regra de ouro afirma.
 *
 * @param {Object} revisao
 * @returns {{campos: Object<string, {valorSugerido:any, valorAnterior:any, estado:string, eConflito:boolean}>, sourceDocument:string, targetTitular:string}}
 */
export function criarSugestoes(revisao) {
  if (!revisao || typeof revisao !== "object") return null;

  const campos = {};
  const conflitos = Array.isArray(revisao.conflicts) ? revisao.conflicts : [];
  const novos = Array.isArray(revisao.newValues) ? revisao.newValues : [];

  for (const conflito of conflitos) {
    if (!conflito?.field) continue;
    campos[conflito.field] = {
      valorSugerido: conflito.new_value,
      valorAnterior: conflito.existing_value,
      estado: PENDENTE,
      // Um conflito é diferente de um campo vazio: há um valor humano a
      // perder, e a UI tem de o dizer.
      eConflito: true,
    };
  }

  for (const novo of novos) {
    if (!novo?.field) continue;
    if (campos[novo.field]) continue;
    campos[novo.field] = {
      valorSugerido: novo.value,
      valorAnterior: null,
      estado: PENDENTE,
      eConflito: false,
    };
  }

  if (Object.keys(campos).length === 0) return null;

  return {
    campos,
    sourceDocument: revisao.sourceDocument || "",
    targetTitular: revisao.targetTitular || "titular1",
    documentsProcessed: revisao.documentsProcessed || 1,
  };
}

function comEstado(sugestoes, campo, estado) {
  if (!sugestoes?.campos?.[campo]) return sugestoes;
  return {
    ...sugestoes,
    campos: {
      ...sugestoes.campos,
      [campo]: { ...sugestoes.campos[campo], estado },
    },
  };
}

export function aprovar(sugestoes, campo) {
  return comEstado(sugestoes, campo, APROVADA);
}

export function rejeitar(sugestoes, campo) {
  return comEstado(sugestoes, campo, REJEITADA);
}

function todosComEstado(sugestoes, estado) {
  if (!sugestoes?.campos) return sugestoes;
  const campos = {};
  for (const [nome, dados] of Object.entries(sugestoes.campos)) {
    // Só o que está PENDENTE muda: um "aprovar tudo" que reabrisse decisões
    // já tomadas desfazia as rejeições do consultor em silêncio.
    campos[nome] = dados.estado === PENDENTE ? { ...dados, estado } : dados;
  }
  return { ...sugestoes, campos };
}

export function aprovarTodas(sugestoes) {
  return todosComEstado(sugestoes, APROVADA);
}

export function rejeitarTodas(sugestoes) {
  return todosComEstado(sugestoes, REJEITADA);
}

/** O estado de um campo, ou `null` se a IA não sugeriu nada para ele. */
export function estadoDoCampo(sugestoes, campo) {
  return sugestoes?.campos?.[campo]?.estado || null;
}

export function sugestaoDoCampo(sugestoes, campo) {
  return sugestoes?.campos?.[campo] || null;
}

/**
 * O que o input DESENHA.
 *
 * Pendente ou aprovada → o valor sugerido (é o ponto do preenchimento em
 * linha: ver o valor onde ele vai ficar). Rejeitada ou sem sugestão → o
 * valor do formulário.
 *
 * **Isto não é o que se grava.** Ver `valoresAprovados`.
 */
export function valorAMostrar(sugestoes, campo, valorDoFormulario) {
  const sugestao = sugestoes?.campos?.[campo];
  if (!sugestao) return valorDoFormulario;
  if (sugestao.estado === REJEITADA) return valorDoFormulario;
  return sugestao.valorSugerido;
}

/**
 * O que vai para o payload: SÓ o que foi aprovado.
 *
 * É aqui que a regra de ouro se cumpre. Um campo pendente não entra — por
 * muito que o ecrã já o mostre.
 */
export function valoresAprovados(sugestoes) {
  const out = {};
  if (!sugestoes?.campos) return out;
  for (const [campo, dados] of Object.entries(sugestoes.campos)) {
    if (dados.estado === APROVADA) out[campo] = dados.valorSugerido;
  }
  return out;
}

export function contarPorEstado(sugestoes) {
  const contagem = { [PENDENTE]: 0, [APROVADA]: 0, [REJEITADA]: 0 };
  if (!sugestoes?.campos) return contagem;
  for (const dados of Object.values(sugestoes.campos)) {
    if (dados.estado in contagem) contagem[dados.estado] += 1;
  }
  return contagem;
}

export function temPendentes(sugestoes) {
  return contarPorEstado(sugestoes)[PENDENTE] > 0;
}

/** Todas decididas (e havia alguma coisa a decidir). */
export function todasDecididas(sugestoes) {
  const total = Object.keys(sugestoes?.campos || {}).length;
  return total > 0 && !temPendentes(sugestoes);
}

/**
 * A classe de destaque de um campo.
 *
 * Fundo amarelado só enquanto está PENDENTE — é um pedido de atenção, e um
 * destaque permanente deixa de ser um destaque. Aprovada fica verde um
 * instante (o consultor vê que a acção pegou) e rejeitada não destaca nada,
 * porque o valor voltou a ser o da ficha.
 */
export function classeDeDestaque(estado) {
  if (estado === PENDENTE) {
    return "bg-amber-50 border-amber-300 dark:bg-amber-950/30 dark:border-amber-800";
  }
  if (estado === APROVADA) {
    return "bg-emerald-50 border-emerald-300 dark:bg-emerald-950/30 dark:border-emerald-800";
  }
  return "";
}

/**
 * Limpa as sugestões já decididas, deixando as pendentes.
 *
 * Chamado depois de gravar: as aprovadas passaram a ser o valor da ficha e
 * manter o destaque verde para sempre mentia sobre a origem.
 */
export function limparDecididas(sugestoes) {
  if (!sugestoes?.campos) return null;
  const campos = {};
  for (const [nome, dados] of Object.entries(sugestoes.campos)) {
    if (dados.estado === PENDENTE) campos[nome] = dados;
  }
  if (Object.keys(campos).length === 0) return null;
  return { ...sugestoes, campos };
}
