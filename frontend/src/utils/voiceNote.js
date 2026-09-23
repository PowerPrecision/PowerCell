/**
 * voiceNote.js — lógica pura das notas de voz do consultor (Épico 7, Eixo 1).
 *
 * PORQUÊ UM MÓDULO À PARTE: a gravação no browser depende de APIs que o jsdom
 * não tem (`MediaRecorder`, `getUserMedia`). Tudo o que é decisão — que
 * formato pedir, que ficheiro aceitar, como mostrar o tempo, que mensagem
 * dar — vive aqui e testa-se sem browser. O hook fica só com o que é
 * mesmo imperativo.
 *
 * Os limites são deliberadamente iguais aos do backend
 * (`services/voice_note_api.py`): rejeitar cedo poupa ao consultor um upload
 * de 20 MB para receber um 413 no fim.
 */

/**
 * Formatos pedidos ao `MediaRecorder`, por ordem de preferência.
 * O webm/opus é o que o Chrome e o Firefox gravam nativamente; o mp4 é o
 * caminho do Safari, que não suporta webm.
 */
export const MIMES_PREFERIDOS = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/mp4",
];

/** Extensões aceites pelo backend, por mime base. */
export const EXTENSOES_POR_MIME = {
  "audio/webm": ".webm",
  "audio/ogg": ".ogg",
  "audio/mpeg": ".mp3",
  "audio/mp3": ".mp3",
  "audio/mp4": ".m4a",
  "audio/x-m4a": ".m4a",
  "audio/aac": ".aac",
  "audio/wav": ".wav",
  "audio/x-wav": ".wav",
  "audio/wave": ".wav",
};

/** Filtro do `<input type="file">` no caminho de recurso. */
export const ACEITA_FICHEIROS = ".webm,.ogg,.mp3,.m4a,.aac,.wav,audio/*";

export const TAMANHO_MAXIMO_BYTES = 25 * 1024 * 1024; // igual ao VOICE_NOTE_MAX_MB
export const DURACAO_MAXIMA_SEGUNDOS = 5 * 60;
/** A partir daqui o cronómetro avisa que falta pouco. */
export const DURACAO_DE_AVISO_SEGUNDOS = DURACAO_MAXIMA_SEGUNDOS - 30;

/**
 * Mime base, sem os codecs que o browser anexa.
 * @param {string} mime - Ex.: `"audio/webm;codecs=opus"`.
 * @returns {string} Ex.: `"audio/webm"`.
 */
export function mimeBase(mime) {
  return String(mime || "")
    .split(";")[0]
    .trim()
    .toLowerCase();
}

/**
 * Extensão canónica de um mime de áudio.
 * @param {string} mime
 * @returns {string|null} `null` quando o formato não é suportado.
 */
export function extensaoParaMime(mime) {
  return EXTENSOES_POR_MIME[mimeBase(mime)] || null;
}

/**
 * Primeiro formato da lista de preferência que este browser sabe gravar.
 *
 * @param {(mime: string) => boolean} suporta - Normalmente
 *   `MediaRecorder.isTypeSupported`. Recebido como argumento para o teste
 *   não precisar de um `MediaRecorder` verdadeiro.
 * @returns {string|null} `null` quando nenhum serve — o chamador cai no
 *   upload de ficheiro em vez de gravar num formato que o backend recusa.
 */
export function escolherMimeDeGravacao(suporta) {
  if (typeof suporta !== "function") return null;
  return MIMES_PREFERIDOS.find((mime) => suporta(mime)) || null;
}

/**
 * Cronómetro da gravação.
 * @param {number} segundos
 * @returns {string} `"MM:SS"` (ou `"H:MM:SS"` se passar da hora).
 */
export function formatarDuracao(segundos) {
  const total = Math.max(0, Math.floor(Number(segundos) || 0));
  const horas = Math.floor(total / 3600);
  const minutos = Math.floor((total % 3600) / 60);
  const resto = total % 60;
  const doisDigitos = (n) => String(n).padStart(2, "0");

  if (horas > 0) return `${horas}:${doisDigitos(minutos)}:${doisDigitos(resto)}`;
  return `${doisDigitos(minutos)}:${doisDigitos(resto)}`;
}

/**
 * Tamanho legível de um ficheiro.
 * @param {number} bytes
 * @returns {string}
 */
export function formatarTamanho(bytes) {
  const valor = Number(bytes) || 0;
  if (valor < 1024) return `${valor} B`;
  if (valor < 1024 * 1024) return `${Math.round(valor / 1024)} KB`;
  return `${(valor / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Valida o que o consultor escolheu ou gravou, antes de subir.
 *
 * @param {{name?: string, size?: number, type?: string}|null} ficheiro
 * @returns {{valido: boolean, erro: string|null}}
 */
export function validarFicheiroDeAudio(ficheiro) {
  if (!ficheiro) {
    return { valido: false, erro: "Nenhum ficheiro selecionado." };
  }
  if (!ficheiro.size) {
    return { valido: false, erro: "O ficheiro está vazio." };
  }
  if (ficheiro.size > TAMANHO_MAXIMO_BYTES) {
    return {
      valido: false,
      erro: `A gravação tem ${formatarTamanho(
        ficheiro.size,
      )} e o limite é ${formatarTamanho(TAMANHO_MAXIMO_BYTES)}.`,
    };
  }
  // Alguns browsers não preenchem o `type` de um ficheiro arrastado; nesse
  // caso vale o nome. Recusar por falta de `type` bloquearia uploads válidos.
  const porMime = extensaoParaMime(ficheiro.type);
  const porNome = Object.values(EXTENSOES_POR_MIME).some((extensao) =>
    String(ficheiro.name || "")
      .toLowerCase()
      .endsWith(extensao),
  );
  if (!porMime && !porNome) {
    return {
      valido: false,
      erro: "Formato não suportado. Use webm, ogg, mp3, m4a ou wav.",
    };
  }
  return { valido: true, erro: null };
}

/**
 * Nome do ficheiro gerado a partir de uma gravação do browser.
 *
 * O blob do `MediaRecorder` não tem nome, e sem extensão o motor de
 * transcrição recusa o ficheiro. A data no nome torna a pasta S3 legível.
 *
 * @param {string} mime
 * @param {Date} [agora]
 * @returns {string}
 */
export function nomeParaGravacao(mime, agora = new Date()) {
  const extensao = extensaoParaMime(mime) || ".webm";
  const d = agora;
  const p = (n) => String(n).padStart(2, "0");
  const carimbo =
    `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}` +
    `-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
  return `nota-de-voz-${carimbo}${extensao}`;
}

/**
 * Frase de conclusão a mostrar ao consultor.
 *
 * @param {{task_ids?: string[], aviso?: string|null}} resultado - O
 *   `result_data` do evento `task_completed`.
 * @returns {string}
 */
export function mensagemDeConclusao(resultado) {
  const dados = resultado || {};
  if (dados.aviso) {
    return "Transcrição guardada no histórico, mas a análise por IA falhou — nenhuma tarefa foi criada.";
  }
  const total = Array.isArray(dados.task_ids) ? dados.task_ids.length : 0;
  if (total === 0) {
    return "Nota adicionada ao histórico. Não foram identificadas tarefas.";
  }
  if (total === 1) {
    return "Nota adicionada ao histórico e 1 tarefa criada.";
  }
  return `Nota adicionada ao histórico e ${total} tarefas criadas.`;
}

/**
 * Diz se um evento `task_*` diz respeito a uma nota de voz deste processo.
 *
 * Existe para o contentor não invalidar as queries do processo a cada
 * tarefa de fundo do CRM (importações, análises em massa, PDFs).
 *
 * @param {{task_type?: string, process_id?: string}} payload
 * @param {string} processId
 * @returns {boolean}
 */
export function eNotaDeVozDoProcesso(payload, processId) {
  if (!payload || !processId) return false;
  return payload.task_type === "VOICE_NOTE" && payload.process_id === processId;
}
