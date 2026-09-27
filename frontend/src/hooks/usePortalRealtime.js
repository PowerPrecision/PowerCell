/**
 * usePortalRealtime — ligação WebSocket do CLIENTE do Portal.
 *
 * Substitui o polling de 15s das mensagens por uma ligação a
 * `/api/ws/portal`, **mantendo o polling como recurso**: é a regra do Épico
 * 10 (para quando o WS liga, retoma quando cai) e é o que impede o Portal de
 * ficar sem mensagens quando o socket não liga — num browser atrás de um
 * proxy que bloqueia WebSockets, por exemplo.
 *
 * AS REGRAS DO CONTRATO (`FRONTEND_GUIDELINES.md` § 9)
 * ===================================================
 * * **Endpoint próprio.** `/api/ws/portal`, nunca o `/ws/notifications` da
 *   equipa — esse recusa tokens de Portal com o código de fecho 4002.
 * * **Nunca enviar `join_process_room`.** A sala é derivada do token NO
 *   SERVIDOR; um pedido de sala é ignorado e registado como sondagem.
 * * **`ping` é a única mensagem que se envia**, de 30 em 30s: é ela que
 *   renova a presença do lado do servidor.
 * * **Dois eventos, e só dois.** O servidor retém os internos por uma lista
 *   de permissão; a decisão do que fazer com cada um vive em
 *   `utils/portalRealtime.js`.
 *
 * O QUE ESTE HOOK NÃO FAZ
 * =======================
 * Não guarda mensagens. O estado da conversa continua no contentor
 * (`ClientPortal`), que é quem o mostra — este hook só diz "vai buscar" e
 * "estou ligado". É a mesma fronteira do `useTaskEvents`/`utils/taskEvents`.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { BACKEND_URL } from "../utils/apiBaseUrl";
import { construirUrlDoSocket, decidirDoEvento } from "../utils/portalRealtime";

/** Batimento. O servidor renova a presença a cada `ping` (TTL de 90s). */
const INTERVALO_DO_PING_MS = 30000;

/** Backoff: começa em 1s e duplica até 30s. */
const ESPERA_INICIAL_MS = 1000;
const ESPERA_MAXIMA_MS = 30000;

/**
 * Códigos de fecho em que NÃO se reconecta.
 *
 * 4001 (sessão expirada) e 4002 (acesso inválido) são veredictos sobre o
 * TOKEN: reconectar com o mesmo token repete o mesmo veredicto para sempre e
 * transforma um erro de autenticação num ciclo de pedidos. Quem resolve é o
 * cliente, pedindo um magic link novo.
 */
const CODIGOS_SEM_RECONEXAO = new Set([4001, 4002]);

/**
 * @param {Object} opcoes
 * @param {boolean} opcoes.enabled - Só liga com a sessão verificada. Como no
 *   `useProcessPortalMessages`, quem sabe que não há sessão é a página; ligar
 *   e ser recusado seria um 4002 por cada montagem.
 * @param {() => string|null} opcoes.obterToken - Lê o token no momento da
 *   ligação (e não uma vez na montagem): o token pode ter sido renovado entre
 *   tentativas de reconexão.
 * @param {() => void} opcoes.onMensagens - Chamado quando há mensagens novas.
 * @param {() => void} [opcoes.onDocumentos] - Chamado quando o Estado
 *   entregou documentos novos.
 * @param {(aviso: {tipo: string, texto: string}) => void} [opcoes.onAviso]
 * @param {() => Array} [opcoes.mensagensActuais] - Para desduplicar o eco da
 *   própria mensagem. Função e não valor: o hook não pode depender da lista
 *   nas dependências do efeito sem reabrir o socket a cada mensagem.
 * @returns {{isConnected: boolean}}
 */
export function usePortalRealtime({
  enabled = false,
  obterToken,
  onMensagens,
  onDocumentos,
  onAviso,
  mensagensActuais,
}) {
  const [isConnected, setIsConnected] = useState(false);

  const socketRef = useRef(null);
  const pingRef = useRef(null);
  const reconexaoRef = useRef(null);
  const esperaRef = useRef(ESPERA_INICIAL_MS);
  const desmontadoRef = useRef(false);

  // As callbacks vivem em refs para não entrarem nas dependências do efeito
  // que abre o socket: uma função nova a cada render do contentor fecharia e
  // reabriria a ligação em cada tecla escrita na caixa de mensagem.
  const callbacksRef = useRef({});
  callbacksRef.current = {
    onMensagens,
    onDocumentos,
    onAviso,
    mensagensActuais,
    obterToken,
  };

  const limparTemporizadores = useCallback(() => {
    if (pingRef.current) {
      clearInterval(pingRef.current);
      pingRef.current = null;
    }
    if (reconexaoRef.current) {
      clearTimeout(reconexaoRef.current);
      reconexaoRef.current = null;
    }
  }, []);

  useEffect(() => {
    desmontadoRef.current = false;

    if (!enabled) {
      // Desligado: garante que não fica socket nem temporizador vivos de uma
      // sessão anterior (ex.: o cliente fez logout).
      limparTemporizadores();
      if (socketRef.current) {
        socketRef.current.close(1000, "desligado");
        socketRef.current = null;
      }
      setIsConnected(false);
      return undefined;
    }

    const agendarReconexao = () => {
      if (desmontadoRef.current || reconexaoRef.current) return;
      const espera = esperaRef.current;
      esperaRef.current = Math.min(espera * 2, ESPERA_MAXIMA_MS);
      reconexaoRef.current = setTimeout(() => {
        reconexaoRef.current = null;
        ligar();
      }, espera);
    };

    function ligar() {
      if (desmontadoRef.current) return;

      const token = callbacksRef.current.obterToken?.();
      // `BACKEND_URL` e NÃO `API_BASE_URL`: o segundo já termina em
      // `/api` e o `construirUrlDoSocket` acrescenta `/api/ws/portal`. O
      // resultado era `wss://…/api/api/ws/portal`, que o servidor não
      // encaminha — o socket do Portal nunca ligou em produção.
      const url = construirUrlDoSocket(BACKEND_URL, token);
      if (!url) {
        // Sem token não há handshake possível — não se insiste, e o polling
        // do contentor continua a ser o caminho (ele só para com `isConnected`).
        return;
      }

      let socket;
      try {
        socket = new WebSocket(url);
      } catch {
        agendarReconexao();
        return;
      }
      socketRef.current = socket;

      socket.onopen = () => {
        if (desmontadoRef.current) return;
        esperaRef.current = ESPERA_INICIAL_MS;
        setIsConnected(true);

        // Recuperação da lacuna: enquanto o socket estava em baixo podem ter
        // chegado mensagens, e o polling estava parado. Uma leitura à entrada
        // fecha esse buraco — sem ela, reconectar deixava a conversa
        // silenciosamente desactualizada até à mensagem SEGUINTE.
        callbacksRef.current.onMensagens?.();

        pingRef.current = setInterval(() => {
          try {
            if (socket.readyState === WebSocket.OPEN) {
              socket.send(JSON.stringify({ type: "ping" }));
            }
          } catch {
            // Um ping perdido não é motivo para fechar: o `onclose` trata da
            // ligação morta e a presença do servidor tolera um batimento
            // falhado (TTL de 90s para um ping de 30s).
          }
        }, INTERVALO_DO_PING_MS);
      };

      socket.onmessage = (evento) => {
        if (desmontadoRef.current) return;
        let envelope;
        try {
          envelope = JSON.parse(evento.data);
        } catch {
          return;
        }

        const decisao = decidirDoEvento(envelope, {
          mensagens: callbacksRef.current.mensagensActuais?.() || [],
        });

        if (decisao.recarregarMensagens) callbacksRef.current.onMensagens?.();
        if (decisao.recarregarDocumentos) callbacksRef.current.onDocumentos?.();
        if (decisao.aviso) callbacksRef.current.onAviso?.(decisao.aviso);
      };

      socket.onerror = () => {
        // O `onclose` vem sempre a seguir e é lá que se decide reconectar —
        // agendar aqui também duplicava as tentativas.
      };

      socket.onclose = (evento) => {
        if (pingRef.current) {
          clearInterval(pingRef.current);
          pingRef.current = null;
        }
        socketRef.current = null;
        if (desmontadoRef.current) return;
        setIsConnected(false);

        if (CODIGOS_SEM_RECONEXAO.has(evento?.code)) {
          // Veredicto sobre o token: insistir repetia-o para sempre. O
          // polling do contentor volta a ser o caminho, porque
          // `isConnected` ficou `false`.
          return;
        }
        agendarReconexao();
      };
    }

    ligar();

    return () => {
      desmontadoRef.current = true;
      limparTemporizadores();
      const socket = socketRef.current;
      socketRef.current = null;
      if (socket) {
        // `onclose` limpo antes de fechar: sem isto, o fecho do desmonte
        // agendava uma reconexão para um componente que já não existe.
        socket.onclose = null;
        socket.onmessage = null;
        socket.onopen = null;
        try {
          socket.close(1000, "desmontado");
        } catch {
          // Fechar um socket que já morreu levanta em alguns browsers.
        }
      }
      setIsConnected(false);
    };
  }, [enabled, limparTemporizadores]);

  return { isConnected };
}

export default usePortalRealtime;
