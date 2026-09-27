/**
 * useProcessNeighbours — vizinhos do processo aberto (Ponto 17).
 *
 * Junta as três camadas descritas em `utils/processNavigation.js`:
 *
 *   1. o contexto que veio no `state` do router (o caminho normal);
 *   2. o mesmo contexto em `sessionStorage`, para sobreviver ao F5;
 *   3. `GET /processes/{id}/neighbours`, SÓ na fronteira da página.
 *
 * Custo por navegação: zero pedidos dentro da página; um pedido
 * minúsculo (dois ids) quando a seta sai da página aberta.
 *
 * Degradação: qualquer falha da camada 3 deixa a seta desactivada e a
 * página de Detalhes abre na mesma. As setas são uma conveniência — não
 * podem ser um caminho para a página não carregar.
 */
import { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { getProcessNeighbours } from "../services/api";
import {
  vizinhosNoContexto,
  comVizinhosDoServidor,
  lerContexto,
  paramsDeVizinhos,
} from "../utils/processNavigation";

export function useProcessNeighbours(processId) {
  const location = useLocation();

  // O `state` manda sobre a sessão: é o contexto da listagem de onde o
  // utilizador acabou de vir. A sessão só entra quando o `state` não
  // existe (refresh, ou uma seta clicada depois de um refresh).
  const contexto = useMemo(
    () => location.state?.contextoDeNavegacao || lerContexto(),
    [location.state],
  );

  const base = useMemo(
    () => vizinhosNoContexto(contexto, processId),
    [contexto, processId],
  );

  const [doServidor, setDoServidor] = useState(null);
  const [aCarregar, setACarregar] = useState(false);

  const { disponivel, precisaDeAnterior, precisaDeSeguinte, params } = base;

  useEffect(() => {
    setDoServidor(null);
    if (!disponivel || (!precisaDeAnterior && !precisaDeSeguinte)) return undefined;

    let cancelado = false;
    setACarregar(true);
    getProcessNeighbours(processId, paramsDeVizinhos(params))
      .then((res) => {
        if (!cancelado) setDoServidor(res?.data || null);
      })
      .catch(() => {
        // Sem vizinho de fronteira a seta fica desactivada. Um toast de
        // erro aqui seria ruído: o utilizador não pediu nada, só abriu
        // um processo.
        if (!cancelado) setDoServidor(null);
      })
      .finally(() => {
        if (!cancelado) setACarregar(false);
      });

    return () => {
      cancelado = true;
    };
  }, [processId, disponivel, precisaDeAnterior, precisaDeSeguinte, params]);

  const vizinhos = useMemo(
    () => comVizinhosDoServidor(base, doServidor),
    [base, doServidor],
  );

  return { ...vizinhos, aCarregar, contexto };
}

export default useProcessNeighbours;
