/**
 * useEstadoNaUrl — estado de uma listagem que sobrevive a «entrar e voltar».
 *
 * O PROBLEMA: uma listagem que guarda a pesquisa e os filtros em `useState`
 * perde-os quando o utilizador abre um processo e carrega em «Voltar» — o
 * componente desmonta e volta a montar com os valores por omissão. Guardá-los
 * no URL resolve-o de graça: «Voltar» devolve o URL da listagem tal como estava
 * (`?kb_q=ana&kb_urg=high`), e um link já filtrado passa a poder partilhar-se.
 *
 * REGRAS
 *  * Escreve com `replace`: mexer num filtro não é um passo de navegação — se
 *    fosse, «Voltar» desfazia filtros um a um em vez de regressar de onde se veio.
 *  * Escreve por actualização FUNCIONAL sobre o URL actual: outros parâmetros
 *    da página (consultor, página, ordenação…) nunca são pisados.
 *  * O valor por omissão NÃO vai para o URL (um URL limpo é o estado limpo).
 *  * `omissao` tem de ser ESTÁVEL entre renders (uma constante de módulo para
 *    listas): serve de dependência de memoização.
 *  * Um valor ilegível no URL (escrito à mão) cai na omissão em vez de rebentar.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

/** Texto: o vazio é a omissão. */
export const CODEC_TEXTO = {
  descodificar: (cru) => cru,
  codificar: (valor) => (valor === "" || valor == null ? null : String(valor)),
};

/** Booleano: só `true` vai para o URL (`false` é a omissão). */
export const CODEC_BOOLEANO = {
  descodificar: (cru) => cru === "true",
  codificar: (valor) => (valor === true ? "true" : null),
};

/** Número inteiro: um valor que não o seja cai na omissão (lança → o hook recua). */
export const CODEC_NUMERO = {
  descodificar: (cru) => {
    const n = Number(cru);
    if (!Number.isInteger(n)) throw new Error("não é um inteiro");
    return n;
  },
  codificar: (valor) => (Number.isInteger(valor) ? String(valor) : null),
};

/** Lista de textos, separados por vírgula (sem vazios). */
export const CODEC_LISTA = {
  descodificar: (cru) => cru.split(",").map((s) => s.trim()).filter(Boolean),
  codificar: (valor) => {
    const itens = (Array.isArray(valor) ? valor : []).map((s) => String(s).trim()).filter(Boolean);
    return itens.length ? itens.join(",") : null;
  },
};

/**
 * @template T
 * @param {string} chave — nome do parâmetro no URL
 * @param {T} omissao — valor quando o parâmetro não existe (ESTÁVEL entre renders)
 * @param {{descodificar: (cru: string) => T, codificar: (v: T) => string|null}} [codec]
 * @returns {[T, (novo: T | ((atual: T) => T)) => void]}
 */
export function useEstadoNaUrl(chave, omissao, codec = CODEC_TEXTO) {
  const [params, setParams] = useSearchParams();
  const cru = params.get(chave);

  const valor = useMemo(() => {
    if (cru === null) return omissao;
    try {
      return codec.descodificar(cru);
    } catch {
      return omissao;
    }
  }, [cru, omissao, codec]);

  const definir = useCallback((novo) => {
    setParams((anterior) => {
      const seguinte = new URLSearchParams(anterior);
      const bruto = seguinte.get(chave);
      const actual = bruto === null ? omissao : codec.descodificar(bruto);
      const escolhido = typeof novo === "function" ? novo(actual) : novo;
      const codificado = codec.codificar(escolhido);
      if (codificado === null || codificado === codec.codificar(omissao)) seguinte.delete(chave);
      else seguinte.set(chave, codificado);
      return seguinte;
    }, { replace: true });
  }, [setParams, chave, omissao, codec]);

  return [valor, definir];
}

/**
 * Caixa de pesquisa: o texto escrito é local e IMEDIATO (a caixa nunca atrasa);
 * o URL só é actualizado depois de o utilizador parar de escrever. Quando o URL
 * muda por outra via (Voltar/Avançar do browser), a caixa acompanha-o.
 *
 * @param {string} chave
 * @param {{atrasoMs?: number}} [opcoes]
 * @returns {[string, (texto: string) => void]}
 */
export function useTextoNaUrl(chave, { atrasoMs = 300 } = {}) {
  const [doUrl, definirNoUrl] = useEstadoNaUrl(chave, "", CODEC_TEXTO);
  const [local, setLocal] = useState(doUrl);
  const ultimoNoUrl = useRef(doUrl);

  // O URL mudou por fora (Voltar/Avançar): a caixa acompanha.
  useEffect(() => {
    if (doUrl !== ultimoNoUrl.current) {
      ultimoNoUrl.current = doUrl;
      setLocal(doUrl);
    }
  }, [doUrl]);

  // O utilizador escreveu: o URL segue depois de ele parar.
  useEffect(() => {
    if (local === ultimoNoUrl.current) return undefined;
    const temporizador = setTimeout(() => {
      ultimoNoUrl.current = local;
      definirNoUrl(local);
    }, atrasoMs);
    return () => clearTimeout(temporizador);
  }, [local, atrasoMs, definirNoUrl]);

  return [local, setLocal];
}
