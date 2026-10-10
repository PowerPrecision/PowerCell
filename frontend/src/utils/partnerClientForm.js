/**
 * Regras PURAS do formulário «Dados do cliente» do Portal do Parceiro.
 *
 * O servidor devolve o esquema por passos (1 = titular, 2 = 2.º titular) e os
 * valores actuais. Tudo o que o ecrã decide — que campos mostrar, o que
 * enviar — está aqui, sem React, para se poder provar.
 */

const CHAVE_DO_SEGUNDO_TITULAR = "compra_tipo";
const VALOR_LIGADO = "outra_pessoa";
const PASSO_DO_SEGUNDO_TITULAR = 2;

const lista = (v) => (Array.isArray(v) ? v : []);

/** O 2.º titular está ligado nestes valores? */
export function segundoTitularLigado(valores) {
  return valores?.[CHAVE_DO_SEGUNDO_TITULAR] === VALOR_LIGADO;
}

/**
 * Os passos do titular — todos menos o 2.º titular — SEM o campo que liga o
 * 2.º titular (esse é o interruptor, não um selector com «outra_pessoa»).
 */
export function passosDoTitular(passos) {
  return lista(passos)
    .filter((p) => p && p.step !== PASSO_DO_SEGUNDO_TITULAR)
    .map((p) => ({
      ...p,
      fields: lista(p.fields).filter((f) => f && f.field_key !== CHAVE_DO_SEGUNDO_TITULAR),
    }))
    .filter((p) => p.fields.length > 0);
}

export function passoDoSegundoTitular(passos) {
  return lista(passos).find((p) => p && p.step === PASSO_DO_SEGUNDO_TITULAR) || null;
}

const igual = (a, b) => JSON.stringify(a ?? "") === JSON.stringify(b ?? "");

/**
 * Só o que mudou — um campo que o parceiro não tocou não vai no pedido
 * (enviar tudo escrevia `null` por cima de campos que a equipa preencheu).
 *
 * Os campos do 2.º titular só vão se estiver ligado; ao desligar, vai a
 * chave que o liga (o servidor apaga os dados do 2.º titular).
 */
export function camposAlterados(inicial, actuais, passos, { ligado }) {
  const chavesDoSegundo = new Set(lista(passoDoSegundoTitular(passos)?.fields).map((f) => f.field_key));
  const todas = new Set(
    lista(passos).flatMap((p) => lista(p?.fields).map((f) => f.field_key))
  );
  const alterados = {};
  for (const chave of todas) {
    if (chavesDoSegundo.has(chave) && !ligado) continue;
    if (!igual(inicial?.[chave], actuais?.[chave])) {
      alterados[chave] = actuais?.[chave] ?? "";
    }
  }
  return alterados;
}
