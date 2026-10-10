/**
 * useVoltar — o botão «Voltar» de uma página de detalhe.
 *
 * Recua na história (a listagem reaparece com os filtros que tinha no URL) e,
 * se a página foi aberta sem história (separador novo), vai para a listagem de
 * origem guardada no contexto de navegação.
 */
import { useCallback } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { CHAVE_DA_PRIMEIRA_ENTRADA, destinoDoVoltar } from "../utils/voltar";

/**
 * @param {{origem?: string}|null} [contexto] — contexto de navegação (`useProcessNeighbours().contexto`)
 * @returns {() => void}
 */
export default function useVoltar(contexto) {
  const navigate = useNavigate();
  const { key } = useLocation();
  const origem = contexto?.origem;
  return useCallback(() => {
    navigate(destinoDoVoltar({ origem, primeiraEntrada: key === CHAVE_DA_PRIMEIRA_ENTRADA }));
  }, [navigate, origem, key]);
}
