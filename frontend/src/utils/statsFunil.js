/**
 * statsFunil — o funil e os SLAs do servidor traduzidos em dados de gráfico.
 *
 * PORQUE É QUE ISTO É PURO
 *   A página não pode agregar. Fazia `getProcesses()` sem filtro, trazia os
 *   12.450 processos para o browser e contava em JavaScript — com listas de
 *   nomes de fases cravadas (`['concluidos', 'desistencias']`) e agrupando
 *   pelo valor CRU de `status`, o que punha os 205 processos em
 *   `cpcv`/`escriturado` e as 12 gralhas em barras próprias. O quadro
 *   resolvia-os para a coluna certa e o gráfico não.
 *
 *   Agora a agregação vem do servidor e o que sobra aqui é APRESENTAÇÃO:
 *   escolher etiquetas, ordenar, converter unidades. Puro e testado — é a
 *   única parte que pode divergir do que o servidor diz.
 *
 * O QUE NUNCA ENTRA AQUI
 *   Nomes de fases, listas de estados, regras de negócio. Se uma função
 *   deste ficheiro precisar de saber que fase é terminal, está no sítio
 *   errado: quem sabe isso é o motor de workflow, no servidor.
 *
 * @module utils/statsFunil
 */

/** Um payload em falta não é um erro — é um gráfico vazio. */
const vazio = (valor, alternativa) =>
  valor === null || valor === undefined ? alternativa : valor;

/**
 * Barras do funil: uma por etapa, pela ordem que o servidor mandou.
 *
 * A ordem vem do servidor de propósito (`ORDEM_DO_FUNIL`): reordenar aqui
 * era duplicar a regra do funil em dois sítios.
 */
export function barrasDoFunil(funil) {
  const etapas = vazio(funil?.etapas, []);
  return etapas.map((etapa) => ({
    key: etapa.macro_fase,
    name: etapa.label,
    processos: vazio(etapa.processos, 0),
    alcancaram: vazio(etapa.alcancaram, 0),
    conversao: etapa.conversao_para_seguinte,
  }));
}

/**
 * Barras de valor por macro-fase, em MILHARES de euros.
 *
 * Milhares e não euros porque um eixo com sete dígitos por rótulo fica
 * ilegível — era o que a página já fazia, e é a única razão da divisão.
 */
export function barrasDeValor(funil, campo = "valor_imovel") {
  return vazio(funil?.etapas, []).map((etapa) => ({
    key: etapa.macro_fase,
    name: etapa.label,
    valor: Math.round(vazio(etapa[campo], 0) / 1000),
  }));
}

/**
 * As linhas que NÃO são etapas do funil, para mostrar à parte.
 *
 * `perdido` fica fora da cadeia de conversão (um processo perde-se de
 * qualquer etapa) e a reconciliação são processos cuja fase o motor não
 * conhece. Esconder qualquer uma delas fazia a soma das barras não dar o
 * total sem nada no ecrã a dizê-lo — a política do Épico 10: nunca varrer
 * os problemas para baixo do tapete.
 */
export function linhasForaDoFunil(funil) {
  const linhas = [];
  for (const chave of ["perdidos", "desconhecidos"]) {
    const linha = funil?.[chave];
    if (linha && vazio(linha.processos, 0) > 0) {
      linhas.push({
        key: linha.macro_fase,
        name: linha.label,
        processos: linha.processos,
      });
    }
  }
  return linhas;
}

/** Fatias do gráfico de prioridade, já sem as vazias. */
export function fatiasDePrioridade(funil) {
  const contagens = vazio(funil?.por_prioridade, {});
  const etiquetas = { alta: "Alta", media: "Média", baixa: "Baixa", sem: "Sem prioridade" };
  return Object.entries(etiquetas)
    .map(([chave, name]) => ({ key: chave, name, value: vazio(contagens[chave], 0) }))
    .filter((fatia) => fatia.value > 0);
}

/**
 * Linhas do painel de SLAs, prontas para a tabela e para o histograma.
 *
 * `emRisco` é o que o servidor contou acima do limiar — nunca recalculado
 * aqui. Recalcular obrigava a UI a saber o limiar e a regra das bandas, e
 * eram duas verdades sobre o mesmo número.
 */
export function linhasDeSla(sla) {
  return vazio(sla?.macro_fases, []).map((linha) => ({
    key: linha.macro_fase,
    limiarDias: linha.limiar_dias,
    emCurso: vazio(linha.em_curso, 0),
    emRisco: vazio(linha.acima_do_limiar, 0),
    diasMedios: linha.dias_medios_em_curso,
    bandaMediana: linha.banda_mediana_em_curso,
    diasMediosHistorico: linha.dias_medios_historico,
    amostraHistorico: vazio(linha.amostra_historico, 0),
    bandas: vazio(linha.bandas, []).map((banda) => ({
      name: banda.banda,
      processos: vazio(banda.processos, 0),
    })),
  }));
}

/**
 * Há alguma coisa que o utilizador precisa de saber sobre a AMOSTRA?
 *
 * Um gráfico que mistura medido com estimado sem o dizer é pior do que um
 * gráfico vazio. Isto devolve as frases a mostrar — e devolve-as vazias
 * quando não há nada a avisar, para a UI não ter de decidir.
 */
export function avisosDaAmostra(funil, sla) {
  const avisos = [];

  const semClassificacao = vazio(funil?.macro_fases_sem_classificacao, []);
  if (semClassificacao.length) {
    avisos.push(
      `${semClassificacao.length} fase(s) sem grupo atribuído: ` +
        `${semClassificacao.join(", ")}. Os processos delas aparecem em ` +
        `"Fases desconhecidas" até um administrador as classificar.`,
    );
  }

  const excluidos = vazio(sla?.excluidos_da_amostra, []);
  if (excluidos.length) {
    avisos.push(
      "As médias de permanência excluem os processos cuja data de entrada " +
        "na fase é uma estimativa aberrante (anterior ao registo automático " +
        "de transições).",
    );
  }

  const semHistorico = vazio(sla?.macro_fases, []).every(
    (linha) => !vazio(linha.amostra_historico, 0),
  );
  if (semHistorico && vazio(sla?.macro_fases, []).length) {
    avisos.push(
      "Ainda não há histórico de permanência medido: os tempos médios por " +
        "fase começam a contar nas transições registadas de agora em diante.",
    );
  }

  return avisos;
}
