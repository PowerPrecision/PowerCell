/**
 * «Serviço pago pelo parceiro» — as regras do cartão, sem React.
 *
 * O parceiro NÃO recebe comissões: paga-nos pelo tratamento do processo do
 * cliente dele. O controlo é uma caixa e um texto livre, visíveis à equipa
 * interna. Não há valores, taxas nem datas de vencimento (decisão da V1).
 *
 * As listas de papéis ESPELHAM as do servidor
 * (`services/servico_do_parceiro.py`) — que é a parede — e há um teste que
 * LÊ o Python e compara: duas listas escritas à mão divergem sem dar erro, e
 * a divergência tem forma concreta (o botão aparece e o servidor responde 403).
 */

export const LIMITE_DE_OBSERVACOES = 1000;

export const PAPEIS_QUE_VEEM = [
  "master", "admin", "ceo", "diretor", "administrativo", "consultor", "intermediario",
];
export const PAPEIS_QUE_ALTERAM = ["master", "admin", "ceo", "diretor", "administrativo"];

const norm = (papel) => String(papel || "").trim().toLowerCase();

/** O perfil EFECTIVO (e não o da conta) decide se o cartão se pede. */
export const podeVerServicoDoParceiro = (papel) => PAPEIS_QUE_VEEM.includes(norm(papel));
export const podeAlterarServicoDoParceiro = (papel) => PAPEIS_QUE_ALTERAM.includes(norm(papel));

/** O cartão só existe para processos com parceiro atribuído. */
export const processoTemParceiro = (processo) => Boolean(String(processo?.assigned_parceiro_id || "").trim());

/** Normaliza o `GET`: uma forma garantida, sem `|| {}` a esconder um erro. */
export function normalizarServico(resposta) {
  const r = resposta && typeof resposta === "object" ? resposta : {};
  return {
    aplicavel: r.aplicavel === true,
    pago: r.pago === true,
    pagoEm: typeof r.pago_em === "string" ? r.pago_em : null,
    observacoes: typeof r.observacoes === "string" ? r.observacoes : "",
    parceiro: r.parceiro && typeof r.parceiro === "object" ? r.parceiro : null,
    actualizadoPor: typeof r.actualizado_por === "string" ? r.actualizado_por : null,
    actualizadoEm: typeof r.actualizado_em === "string" ? r.actualizado_em : null,
    podeAlterar: r.pode_alterar === true,
  };
}

/** As observações mudaram face ao que está gravado? (espaços nas pontas não contam) */
export const observacoesMudaram = (atual, gravadas) =>
  String(atual ?? "").trim() !== String(gravadas ?? "").trim();

/** Os corpos do `PUT`: SÓ os campos que mudam (o servidor aceita um ou ambos). */
export const corpoDaCaixa = (pago) => ({ pago: Boolean(pago) });
export const corpoDasObservacoes = (texto) => ({ observacoes: String(texto ?? "").slice(0, LIMITE_DE_OBSERVACOES) });
