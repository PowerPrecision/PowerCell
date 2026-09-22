/**
 * useAudioRecorder — invólucro do `MediaRecorder` (Épico 7, Eixo 1).
 *
 * É a ÚNICA peça do épico que toca em APIs do browser. Toda a decisão
 * (formato, limites, validação, formatação) vive em `utils/voiceNote.js`,
 * que se testa sem jsdom; aqui fica só o que é imperativo: pedir o
 * microfone, acumular os pedaços e parar.
 *
 * GRAVAR PODE SIMPLESMENTE NÃO SER POSSÍVEL:
 *   Safari antigo sem `MediaRecorder`, permissão negada, `getUserMedia`
 *   indisponível fora de HTTPS. O hook não esconde isso — expõe
 *   `suportado` e `erro` para o componente oferecer o upload de ficheiro
 *   em vez de mostrar um botão que não faz nada.
 *
 * O MICROFONE É SEMPRE LIBERTADO:
 *   Cada faixa do `MediaStream` é parada ao terminar, ao cancelar e ao
 *   desmontar. Sem isso o indicador de gravação do browser fica aceso
 *   depois de o diálogo fechar — o utilizador julga que continua a ser
 *   ouvido, e com razão.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import {
  DURACAO_MAXIMA_SEGUNDOS,
  escolherMimeDeGravacao,
  nomeParaGravacao,
} from "../utils/voiceNote";

/**
 * @typedef {Object} EstadoDeGravacao
 * @property {boolean} suportado - O browser sabe gravar áudio.
 * @property {boolean} aGravar
 * @property {number} duracao - Segundos decorridos.
 * @property {string|null} erro - Mensagem legível, se algo correu mal.
 * @property {() => Promise<void>} iniciar
 * @property {() => void} parar - Termina e entrega o ficheiro por `onGravacao`.
 * @property {() => void} cancelar - Termina e deita fora a gravação.
 */

/**
 * @param {Object} opcoes
 * @param {(ficheiro: File) => void} opcoes.onGravacao - Recebe o ficheiro final.
 * @param {number} [opcoes.duracaoMaxima] - Segundos até parar sozinho.
 * @returns {EstadoDeGravacao}
 */
export default function useAudioRecorder({
  onGravacao,
  duracaoMaxima = DURACAO_MAXIMA_SEGUNDOS,
} = {}) {
  const [aGravar, setAGravar] = useState(false);
  const [duracao, setDuracao] = useState(0);
  const [erro, setErro] = useState(null);

  const gravadorRef = useRef(null);
  const pedacosRef = useRef([]);
  const streamRef = useRef(null);
  const intervaloRef = useRef(null);
  const descartarRef = useRef(false);
  const onGravacaoRef = useRef(onGravacao);

  // O callback é guardado numa ref para que trocá-lo não obrigue a
  // reconstruir `iniciar`/`parar` — e, sobretudo, para que o `onstop` do
  // gravador use sempre a versão mais recente.
  useEffect(() => {
    onGravacaoRef.current = onGravacao;
  }, [onGravacao]);

  const suportado =
    typeof window !== "undefined" &&
    typeof window.MediaRecorder !== "undefined" &&
    Boolean(navigator?.mediaDevices?.getUserMedia);

  const limpar = useCallback(() => {
    if (intervaloRef.current) {
      clearInterval(intervaloRef.current);
      intervaloRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((faixa) => faixa.stop());
      streamRef.current = null;
    }
    gravadorRef.current = null;
    pedacosRef.current = [];
  }, []);

  const parar = useCallback(() => {
    descartarRef.current = false;
    try {
      gravadorRef.current?.stop();
    } catch {
      // Já parado (duplo clique, ou paragem automática pelo limite).
      limpar();
      setAGravar(false);
    }
  }, [limpar]);

  const cancelar = useCallback(() => {
    descartarRef.current = true;
    try {
      gravadorRef.current?.stop();
    } catch {
      limpar();
      setAGravar(false);
    }
  }, [limpar]);

  // `parar` é usado dentro de `iniciar` (limite de duração) através de uma
  // ref: declarar as funções por esta ordem sem a ref deixaria `parar` na
  // zona morta temporal no momento em que `iniciar` é construída.
  const pararRef = useRef(parar);
  useEffect(() => {
    pararRef.current = parar;
  }, [parar]);

  const iniciar = useCallback(async () => {
    setErro(null);

    if (!suportado) {
      setErro("Este browser não permite gravar áudio. Carregue um ficheiro.");
      return;
    }

    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      setErro(
        e?.name === "NotAllowedError"
          ? "Acesso ao microfone recusado. Autorize o microfone e tente de novo."
          : "Não foi possível aceder ao microfone.",
      );
      return;
    }

    const mime = escolherMimeDeGravacao((tipo) =>
      window.MediaRecorder.isTypeSupported?.(tipo),
    );
    if (!mime) {
      stream.getTracks().forEach((faixa) => faixa.stop());
      setErro(
        "Este browser não grava num formato suportado. Carregue um ficheiro.",
      );
      return;
    }

    let gravador;
    try {
      gravador = new window.MediaRecorder(stream, { mimeType: mime });
    } catch {
      stream.getTracks().forEach((faixa) => faixa.stop());
      setErro("Não foi possível iniciar a gravação.");
      return;
    }

    pedacosRef.current = [];
    descartarRef.current = false;

    gravador.ondataavailable = (evento) => {
      if (evento.data?.size) pedacosRef.current.push(evento.data);
    };

    gravador.onstop = () => {
      const pedacos = pedacosRef.current;
      const descartar = descartarRef.current;
      limpar();
      setAGravar(false);
      setDuracao(0);

      if (descartar || pedacos.length === 0) return;

      const blob = new Blob(pedacos, { type: mime });
      const ficheiro = new File([blob], nomeParaGravacao(mime), { type: mime });
      onGravacaoRef.current?.(ficheiro);
    };

    gravadorRef.current = gravador;
    streamRef.current = stream;
    gravador.start();
    setAGravar(true);
    setDuracao(0);

    intervaloRef.current = setInterval(() => {
      setDuracao((anterior) => {
        const seguinte = anterior + 1;
        // Parar sozinho protege a memória do browser e o limite do
        // endpoint: uma gravação esquecida não pode crescer sem fim.
        if (seguinte >= duracaoMaxima) pararRef.current();
        return seguinte;
      });
    }, 1000);
  }, [duracaoMaxima, limpar, suportado]);

  // Fechar o diálogo a meio de uma gravação não pode deixar o microfone
  // aberto: o browser continuaria a mostrar o indicador de gravação.
  useEffect(() => () => limpar(), [limpar]);

  return { suportado, aGravar, duracao, erro, iniciar, parar, cancelar };
}
