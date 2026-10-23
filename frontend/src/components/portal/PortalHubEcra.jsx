import { useCallback, useState } from "react";

import { API_BASE_URL } from "../../utils/apiBaseUrl";
import { eBloqueioDoPortal, limparSessaoDoPortal, mensagemDoBloqueio } from "../../utils/portalInativo";
import { aplicarEscolha, avisarMudancaDeSessao, guardarHub, listaDeProcessos } from "../../utils/portalHub";
import PortalHub from "./PortalHub";

/**
 * O contentor do Hub: faz os dois pedidos (`GET /portal/hub`, `POST /portal/hub/select`) e traduz
 * o que o servidor responde numa decisão de ecrã. A lista e o token vêm do armazenamento (quem
 * fez o login guardou-os); o ecrã é o `PortalHub`.
 *
 * O que cada resposta quer dizer:
 *  * 200 → o token de sessão passa a ser o do processo escolhido e o contentor remonta o Portal;
 *  * 403 «Portal inactivo» → o processo foi suspenso entretanto: diz-se, e a lista refaz-se;
 *  * 404 → já não é uma escolha possível (deixou de ser do cliente): refaz-se a lista;
 *  * 401 → a sessão do Hub expirou: sai-se para o login (um cliente não fica preso num ecrã
 *    que já não responde).
 *
 * @param {object} props
 * @param {{token: string, processos: Array}} props.hub O que `lerHub()` devolveu.
 * @param {string} [props.nome]
 */
export default function PortalHubEcra({ hub, nome }) {
  const [aEscolher, setAEscolher] = useState(null);
  const [erro, setErro] = useState(null);

  const cabecalhos = useCallback(
    () => ({ "Content-Type": "application/json", Authorization: `Bearer ${hub.token}` }),
    [hub.token],
  );

  const sairParaOLogin = useCallback(() => {
    limparSessaoDoPortal();
    avisarMudancaDeSessao();
  }, []);

  /** Pede ao servidor o token de sessão de UM processo. */
  const pedirEscolha = useCallback(
    async (processId) => {
      const res = await fetch(`${API_BASE_URL}/portal/hub/select`, {
        method: "POST",
        headers: cabecalhos(),
        body: JSON.stringify({ process_id: processId }),
      });
      const corpo = await res.json().catch(() => undefined);
      return { res, corpo };
    },
    [cabecalhos],
  );

  /**
   * Volta a pedir a lista: o servidor é quem sabe o que o cliente ainda pode escolher.
   * Com 2+ processos o Hub continua; com UM entra-se nele (não há o que escolher); com nenhum, sai-se.
   */
  const refazerAListaDoServidor = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/portal/hub`, { headers: cabecalhos() });
      const corpo = await res.json().catch(() => undefined);
      if (res.status === 401 || eBloqueioDoPortal(res.status, corpo)) return sairParaOLogin();
      if (!res.ok) return undefined;
      const lista = listaDeProcessos(corpo?.processos);
      if (lista.length === 0) return sairParaOLogin();
      if (lista.length === 1) {
        const escolha = await pedirEscolha(lista[0].id);
        return escolha.res.ok && aplicarEscolha(escolha.corpo) ? undefined : sairParaOLogin();
      }
      guardarHub({ hub_token: hub.token, processos: lista }, { escolhido: "" });
      avisarMudancaDeSessao();
    } catch {
      /* sem rede: a lista que há continua a servir */
    }
    return undefined;
  }, [cabecalhos, hub.token, pedirEscolha, sairParaOLogin]);

  const escolher = useCallback(
    async (processId) => {
      if (aEscolher) return;
      setAEscolher(processId);
      setErro(null);
      try {
        const { res, corpo } = await pedirEscolha(processId);
        if (res.ok && aplicarEscolha(corpo)) return;

        if (res.status === 401) return sairParaOLogin();
        if (eBloqueioDoPortal(res.status, corpo)) {
          setErro(mensagemDoBloqueio(corpo));
        } else if (res.status === 404) {
          setErro("Este processo já não está disponível.");
        } else if (res.status === 429) {
          setErro("Demasiados pedidos. Aguarde um momento e tente novamente.");
        } else {
          setErro("Não foi possível abrir o processo. Tente novamente.");
        }
        if (res.status === 403 || res.status === 404) await refazerAListaDoServidor();
      } catch {
        setErro("Sem ligação ao servidor. Verifique a sua internet e tente novamente.");
      } finally {
        setAEscolher(null);
      }
      return undefined;
    },
    [aEscolher, pedirEscolha, refazerAListaDoServidor, sairParaOLogin],
  );

  return (
    <PortalHub
      nome={nome}
      processos={hub.processos}
      aEscolher={aEscolher}
      erro={erro}
      onEscolher={escolher}
      onSair={sairParaOLogin}
    />
  );
}
