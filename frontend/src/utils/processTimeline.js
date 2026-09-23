/**
 * processTimeline — a verdade do motor de workflow, em fases.
 *
 * "UI DE FASES MENTIROSA" (Lote 5, Prioridade 0)
 *   Os estados do workflow (colecção `workflow_statuses`, configuráveis
 *   pelo admin) estavam certos; era a timeline do CRM que lhes passava
 *   por cima. Três defeitos, todos dentro de um componente onde não se
 *   conseguia testar nada:
 *
 *   1. ALIASES A MANDAR NO MOTOR. Um mapa cravado em código reescrevia o
 *      estado ACTUAL e o histórico (`cpcv → fase_escritura`,
 *      `escriturado → concluidos`, …) e nunca tocava na lista de fases.
 *      Basta o admin criar uma fase chamada `cpcv` — nome natural num CRM
 *      de crédito — para o processo que lá está ser reescrito para outra:
 *      a fase actual deixava de existir no mapa, o crachá do cabeçalho
 *      sumia e `currentOrder` caía para 0, o que punha TODAS as fases a
 *      ler-se como futuras.
 *   2. OS DIAS ERAM SEMPRE CONTRA HOJE, para cada fase concluída. O
 *      cabeçalho somava-os: "5 fases • 812 dias" num processo com 6
 *      meses. Uma fase dura da sua entrada até à entrada na seguinte.
 *   3. `currentPhaseInfo?.order || 0` não distinguia a fase de ordem 0 de
 *      uma fase desconhecida.
 *
 * A REGRA
 *   O motor é a fonte de verdade. O alias é um RECURSO para dados
 *   antigos: só se aplica quando o nome guardado não existe no motor E o
 *   destino existe. Nunca ao contrário.
 *
 * @module utils/processTimeline
 */

/**
 * Nomes antigos de fases, de versões anteriores do produto, que ainda
 * aparecem em processos e no histórico. NÃO é a lista de fases — essa
 * vem do motor. É só um recurso de leitura, e perde sempre para o motor.
 */
const ALIASES_LEGADOS = {
  clientes_em_espera: "clientes_espera",
  enviado_ao_bruno: "enviado_bruno",
  enviado_ao_luis: "enviado_luis",
  banco_em_analise: "fase_bancaria",
  aprovado_pelo_banco: "ch_aprovado",
  cpcv: "fase_escritura",
  a_escriturar: "escritura_agendada",
  escriturado: "concluidos",
  recusado: "desistencias",
  desistiu: "desistencias",
};

const MS_POR_DIA = 86400000;

const paraData = (valor) => {
  if (!valor) return null;
  const d = valor instanceof Date ? valor : new Date(valor);
  return Number.isNaN(d.getTime()) ? null : d;
};

/**
 * Traduz um nome de fase antigo para o nome actual — mas só quando o
 * motor não conhece o original E conhece o destino.
 *
 * @param {string} estado - Nome guardado no processo ou no histórico.
 * @param {Set<string>|null} nomesDoMotor - Nomes que o motor tem mesmo.
 * @returns {string} O nome a usar.
 */
export function normalizarEstado(estado, nomesDoMotor) {
  if (!estado || !nomesDoMotor || typeof nomesDoMotor.has !== "function") return estado;
  // O motor manda: um nome que ele tem nunca é reescrito.
  if (nomesDoMotor.has(estado)) return estado;
  const destino = ALIASES_LEGADOS[estado];
  // E traduzir para um destino que o motor também não tem só trocaria um
  // nome desconhecido por outro.
  return destino && nomesDoMotor.has(destino) ? destino : estado;
}

/**
 * Constrói a linha de fases de um processo.
 *
 * @param {object} [entrada]
 * @param {Array}  [entrada.fases] - `workflow_statuses` do motor.
 * @param {string} [entrada.estadoActual] - `process.status`.
 * @param {Array}  [entrada.historico] - Registos de `db.history`.
 * @param {Date}   [entrada.agora] - Injectável para os testes.
 * @returns {Array<{phase, phaseInfo, date, isCurrent, isCompleted,
 *   isSkipped, isPendente, daysInPhase}>}
 */
export function construirTimeline({ fases, estadoActual, historico, agora } = {}) {
  const lista = Array.isArray(fases) ? fases.filter((f) => f && f.name) : [];
  if (lista.length === 0) return [];

  const nomesDoMotor = new Set(lista.map((f) => f.name));
  const ordenadas = [...lista].sort(
    (a, b) => (a.order ?? Number.MAX_SAFE_INTEGER) - (b.order ?? Number.MAX_SAFE_INTEGER),
  );

  const actual = normalizarEstado(estadoActual, nomesDoMotor);
  // `null` — e não 0 — quando o motor não conhece a fase actual. Com 0,
  // tudo o que tem ordem maior parecia futuro; a página inteira mentia
  // por causa de um nome só.
  const faseActual = nomesDoMotor.has(actual) ? ordenadas.find((f) => f.name === actual) : null;
  const ordemActual = faseActual ? (faseActual.order ?? null) : null;

  const alcancadas = new Set();
  if (nomesDoMotor.has(actual)) alcancadas.add(actual);

  /** Primeira entrada em cada fase, segundo o histórico. */
  const entradas = {};
  const registos = Array.isArray(historico) ? [...historico] : [];
  registos.sort((a, b) => {
    const da = paraData(a?.timestamp || a?.created_at);
    const db = paraData(b?.timestamp || b?.created_at);
    if (!da && !db) return 0;
    if (!da) return 1;
    if (!db) return -1;
    return da - db;
  });

  for (const registo of registos) {
    const bruto = registo?.new_value || registo?.new_status || registo?.status;
    const nome = normalizarEstado(bruto, nomesDoMotor);
    if (!nome || !nomesDoMotor.has(nome)) continue;
    alcancadas.add(nome);
    if (!(nome in entradas)) entradas[nome] = registo?.timestamp || registo?.created_at || null;
  }

  // Momentos de entrada por ordem cronológica: é o que permite medir
  // quanto tempo cada fase durou DE FACTO (até à seguinte).
  const marcos = ordenadas
    .filter((f) => alcancadas.has(f.name) && paraData(entradas[f.name]))
    .map((f) => ({ nome: f.name, quando: paraData(entradas[f.name]) }))
    .sort((a, b) => a.quando - b.quando);

  const momentoAgora = paraData(agora) || new Date();

  return ordenadas.map((fase) => {
    const alcancada = alcancadas.has(fase.name);
    const isCurrent = !!faseActual && fase.name === faseActual.name;
    // Sem fase actual conhecida não se sabe o que é passado nem futuro:
    // não se marca nada como saltado, que seria uma afirmação sem base.
    const antes = ordemActual !== null && (fase.order ?? Number.MAX_SAFE_INTEGER) < ordemActual;
    const depois = ordemActual !== null && (fase.order ?? Number.MAX_SAFE_INTEGER) > ordemActual;

    const isCompleted = alcancada && !isCurrent;
    const isSkipped = !alcancada && antes;
    const isPendente = !alcancada && depois;

    const date = alcancada ? entradas[fase.name] || null : null;

    let daysInPhase;
    const entrou = paraData(date);
    if (entrou) {
      const idx = marcos.findIndex((m) => m.nome === fase.name);
      const seguinte = idx >= 0 ? marcos[idx + 1] : undefined;
      // A fase actual (e a última alcançada) contam até hoje; as outras
      // até à entrada na fase seguinte.
      const fim = seguinte ? seguinte.quando : momentoAgora;
      const dias = Math.max(0, Math.round((fim - entrou) / MS_POR_DIA));
      if (dias > 0) daysInPhase = dias;
    }

    return {
      phase: fase.name,
      phaseInfo: fase,
      date,
      isCurrent,
      isCompleted,
      isSkipped,
      isPendente,
      daysInPhase,
    };
  });
}
