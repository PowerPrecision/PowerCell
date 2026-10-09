/**
 * useConfirmarProcessosActivos — pergunta «este cliente já tem processos
 * activos?» antes de o adicionar a um processo (Bloco 1, ponto 5).
 *
 * Devolve `{ confirmar, dialog }`:
 *
 *   const { confirmar, dialog } = useConfirmarProcessosActivos();
 *   ...
 *   if (!(await confirmar(client.id, { nome, excludeProcessId }))) return;
 *   ...
 *   return (<>... {dialog}</>);
 *
 * `confirmar` resolve `true` quando o fluxo pode continuar (nada a avisar, o
 * utilizador confirmou, ou a verificação falhou) e `false` quando o utilizador
 * cancelou. É uma Promise para o contentor poder escrever o fluxo em linha,
 * sem partir a função em duas metades unidas por estado.
 *
 * **Falha aberta e DITA**: um erro na verificação não bloqueia o trabalho
 * (o aviso é consultivo), mas avisa que não foi verificado.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import ActiveProcessesConfirmDialog from "../components/shared/ActiveProcessesConfirmDialog";
import { getClientActiveProcesses } from "../services/api";
import {
  AVISO_NAO_VERIFICADO,
  deveAvisar,
  normalizarProcessosActivos,
} from "../utils/processosActivos";

export default function useConfirmarProcessosActivos() {
  const [pendente, setPendente] = useState(null); // {resposta, nome}
  const resolverRef = useRef(null);

  // Se o contentor desmontar com a pergunta aberta, não deixar a Promise
  // pendurada: quem esperava recebe «cancelado».
  useEffect(
    () => () => {
      if (resolverRef.current) resolverRef.current(false);
    },
    [],
  );

  const fechar = useCallback((resposta) => {
    const resolver = resolverRef.current;
    resolverRef.current = null;
    setPendente(null);
    if (resolver) resolver(resposta);
  }, []);

  const confirmar = useCallback(async (clientId, { nome, excludeProcessId } = {}) => {
    if (!clientId) return true;
    let resposta;
    try {
      const res = await getClientActiveProcesses(clientId, excludeProcessId);
      resposta = normalizarProcessosActivos(res?.data);
    } catch (error) {
      console.warn("Verificação de processos activos falhou:", error);
      toast.warning(AVISO_NAO_VERIFICADO);
      return true;
    }
    if (!deveAvisar(resposta)) return true;

    return new Promise((resolve) => {
      resolverRef.current = resolve;
      setPendente({ resposta, nome });
    });
  }, []);

  const dialog = (
    <ActiveProcessesConfirmDialog
      open={Boolean(pendente)}
      nome={pendente?.nome}
      resposta={pendente?.resposta ?? null}
      onConfirm={() => fechar(true)}
      onCancel={() => fechar(false)}
    />
  );

  return { confirmar, dialog };
}
