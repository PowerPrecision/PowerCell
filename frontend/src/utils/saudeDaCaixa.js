/**
 * O aviso de uma caixa de correio que está a falhar (Lote 7, ponto 4).
 *
 * O QUE A AUDITORIA ENCONTROU
 * ===========================
 * Quando a password do IMAP expira, a sincronização MANUAL falha o job e o
 * ecrã mostra um toast — transitório. A sincronização AUTOMÁTICA (de 10 em 10
 * minutos, a que mantém a caixa fresca) morria num `logger.warning` no
 * servidor: a caixa deixava de receber email e o ecrã mostrava a lista antiga
 * **sem um único aviso**. O utilizador só descobre quando repara que não
 * recebe email há dias — e o diagnóstico natural («o servidor está em baixo»)
 * aponta para o sítio errado.
 *
 * O backend passou a persistir o estado (`services/mailbox_health.py`) e a
 * devolvê-lo em cada conta. Este módulo decide o que se MOSTRA.
 *
 * TRÊS REGRAS
 * ===========
 * 1. **Só a falha de AUTENTICAÇÃO merece um aviso permanente.** Um servidor
 *    inatingível e um limite de tráfego passam sozinhos; avisar deles com a
 *    mesma força ensina a ignorar o aviso todo — é o `desactivado ≠ em baixo`
 *    do painel de sinais vitais.
 * 2. **`desconhecido` não é uma falha.** Uma conta que nunca sincronizou não
 *    tem erro nenhum, e pintá-la de vermelho seria um aviso falso no primeiro
 *    dia de todos.
 * 3. **O aviso diz desde QUANDO.** «Falha desde ontem» e «falha desde há duas
 *    semanas» exigem urgências diferentes, e é esse número que distingue um
 *    soluço de uma caixa parada.
 */

/** A conta precisa de um aviso permanente no ecrã? */
export function precisaDeAviso(conta) {
  if (!conta || typeof conta !== "object") return false;
  // `sync_requires_action` é decidido no SERVIDOR (classificação da mensagem
  // do servidor de email). O ecrã não reclassifica: duas classificações da
  // mesma mensagem divergem, e a que divergir avisa do que não deve.
  return Boolean(conta.sync_requires_action);
}

/** As contas que precisam de aviso, pela ordem em que vieram. */
export function contasComProblema(contas) {
  if (!Array.isArray(contas)) return [];
  return contas.filter(precisaDeAviso);
}

const UM_DIA = 24 * 60 * 60 * 1000;

/** Quantos dias inteiros desde `desde`, ou `null` se não se souber. */
export function diasEmFalha(desde, agora = new Date()) {
  if (!desde) return null;
  const inicio = new Date(desde);
  if (Number.isNaN(inicio.getTime())) return null;
  const decorrido = agora.getTime() - inicio.getTime();
  if (decorrido < 0) return null;
  return Math.floor(decorrido / UM_DIA);
}

/**
 * A frase do aviso.
 *
 * A mensagem vem do SERVIDOR (`sync_message`): é ela que diz o que fazer, e
 * duplicá-la aqui fazia-a divergir da que o administrador vê. O que se
 * acrescenta é a antiguidade, que o servidor não formata.
 */
export function textoDoAviso(conta, agora = new Date()) {
  if (!precisaDeAviso(conta)) return "";
  const base = String(conta.sync_message || "").trim()
    || "A sincronização desta caixa está a falhar.";
  const dias = diasEmFalha(conta.sync_failing_since, agora);
  if (dias === null) return base;
  if (dias === 0) return `${base} (desde hoje)`;
  if (dias === 1) return `${base} (desde ontem)`;
  return `${base} (há ${dias} dias)`;
}

/** O rótulo curto para o separador da caixa: um ponto de atenção. */
export function rotuloCurto(conta) {
  return precisaDeAviso(conta) ? "Credenciais recusadas" : "";
}
