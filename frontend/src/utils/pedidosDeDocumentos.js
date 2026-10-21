/**
 * Pedidos de documentos com várias peças («últimos 3 recibos»): a quantidade é uma
 * RECOMENDAÇÃO, nunca um mínimo (decisão da direcção, Out 2026).
 *
 * O servidor dá o pedido por cumprido no PRIMEIRO ficheiro (`document_portal_counts`)
 * e manda `expected_count`/`suggested_count` com o número recomendado. O que o ecrã faz
 * com isso — e que este módulo decide num ponto único, para o Portal do Cliente e o do
 * Parceiro não divergirem — é convidar a juntar mais sem bloquear nada.
 */

function inteiro(valor) {
  const n = Number(valor);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
}

/** Quantos ficheiros se recomenda (≥ 1). `suggested_count` vence o legado `expected_count`. */
export function quantidadeRecomendada(pedido) {
  return Math.max(1, inteiro(pedido?.suggested_count) || inteiro(pedido?.expected_count) || 1);
}

/** Quantos já estão no pedido: a lista manda; o contador é recurso. */
export function ficheirosEnviados(pedido) {
  if (Array.isArray(pedido?.attached_files)) return pedido.attached_files.length;
  return inteiro(pedido?.uploaded_count);
}

/** O pedido recomenda mais do que o que lá está? (um pedido de 1 nunca convida) */
export function convidaAJuntarMais(pedido) {
  const recomendada = quantidadeRecomendada(pedido);
  return recomendada > 1 && ficheirosEnviados(pedido) < recomendada;
}

/**
 * O convite, em texto. Vazio quando não há nada a sugerir.
 * - sem ficheiros: diz que se pode enviar menos (não é obrigatório);
 * - com ficheiros: «Pode juntar mais — recomendado: N».
 */
export function textoDoConvite(pedido) {
  if (!convidaAJuntarMais(pedido)) return "";
  const recomendada = quantidadeRecomendada(pedido);
  if (ficheirosEnviados(pedido) === 0) {
    return `Recomendado: ${recomendada} ficheiros — pode enviar menos.`;
  }
  return `Pode juntar mais — recomendado: ${recomendada}.`;
}

/** Rótulo do botão de envio: «Submeter» → «Adicionar mais» a partir do 1.º ficheiro. */
export function rotuloDoBotao(pedido) {
  return ficheirosEnviados(pedido) > 0 ? "Adicionar mais" : "Submeter";
}

/** Pedidos já cumpridos que ainda convidam a juntar mais (a secção «Pode juntar mais»). */
export function pedidosParaJuntarMais(recebidos) {
  return (Array.isArray(recebidos) ? recebidos : []).filter(convidaAJuntarMais);
}
