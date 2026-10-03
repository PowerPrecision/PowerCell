/**
 * Arrastar e largar ficheiros — as regras, sem React (Lote 6, ponto 3).
 *
 * TRÊS ARMADILHAS QUE ISTO RESOLVE
 * ================================
 *
 * 1. **`onDragLeave` dispara ao passar sobre um FILHO.** Uma zona que só faça
 *    `setDragOver(false)` no leave pisca enquanto o rato atravessa o conteúdo,
 *    e com o realce apagado o utilizador larga sem saber se vai acertar. A
 *    saída é contar entradas e saídas (`arrastoEntrou`/`arrastoSaiu`), que é o
 *    que o `S3FileManager` já fazia à mão para o arrasto INTERNO — e que a
 *    zona de upload do Portal não fazia.
 *
 * 2. **O arrasto de ficheiros do sistema e o arrasto INTERNO são eventos
 *    diferentes com o mesmo nome.** No separador Documentos, arrastar um
 *    ficheiro de uma categoria para outra MOVE-o (não envia nada); arrastar do
 *    Finder/Explorador tem de fazer upload. `eArrastoDeFicheiros` distingue-os
 *    pelo `dataTransfer.types` conter `"Files"` — sem esta distinção, ligar o
 *    upload por arrasto partia o mover que já existia.
 *
 * 3. **O botão filtra tipos e o arrasto não.** O `<input type="file">` tem
 *    `accept`, mas o caminho do `drop` não passa por ele: no Portal, largar um
 *    `.exe` ia direito ao upload. A parede real é a quarentena de magic bytes
 *    do servidor (um `accept` é uma conveniência, não segurança) — mas deixar
 *    o cliente descobrir pelo erro, depois de a rede ter transportado o
 *    ficheiro, é a UX errada. `separarPorTipoAceite` aplica ao arrasto a MESMA
 *    lista do botão, e devolve os recusados para se poder dizer QUAIS.
 */

/** Um arrasto que transporta ficheiros do sistema (e não um arrasto interno). */
export const eArrastoDeFicheiros = (evento) => {
  const dt = evento?.dataTransfer;
  if (!dt) return false;
  const tipos = dt.types;
  if (tipos) {
    // `types` é um DOMStringList no Safari e um array nos outros.
    const lista = Array.from(tipos);
    if (lista.length > 0) return lista.includes("Files");
  }
  // Sem `types` (jsdom antigo, alguns browsers no `drop`): a presença de
  // ficheiros é a própria resposta.
  return (dt.files?.length || 0) > 0;
};

/** Os ficheiros de um evento de `drop`, como array. */
export const ficheirosDoEvento = (evento) =>
  Array.from(evento?.dataTransfer?.files || []);

/** `".pdf,.jpg"` → `["pdf", "jpg"]`. Ignora `image/*` e afins. */
export const extensoesAceites = (accept) =>
  String(accept || "")
    .split(",")
    .map((t) => t.trim().toLowerCase())
    .filter((t) => t.startsWith("."))
    .map((t) => t.slice(1))
    .filter(Boolean);

/** A extensão de um nome de ficheiro, em minúsculas e sem ponto. */
export const extensaoDe = (nome) => {
  const texto = String(nome || "");
  const ponto = texto.lastIndexOf(".");
  if (ponto <= 0 || ponto === texto.length - 1) return "";
  return texto.slice(ponto + 1).toLowerCase();
};

/**
 * Separa os ficheiros pela lista de tipos aceites do botão.
 *
 * Sem `accept` **nada é recusado**: a zona herda o que o botão permite, e um
 * botão sem restrição não pode ficar mais restrito pelo arrasto.
 */
export const separarPorTipoAceite = (ficheiros, accept) => {
  const lista = Array.from(ficheiros || []);
  const permitidas = extensoesAceites(accept);
  if (permitidas.length === 0) return { aceites: lista, recusados: [] };
  const aceites = [];
  const recusados = [];
  for (const f of lista) {
    (permitidas.includes(extensaoDe(f?.name)) ? aceites : recusados).push(f);
  }
  return { aceites, recusados };
};

/** A mensagem para os recusados. Nomeia-os: «2 ficheiros» manda adivinhar. */
export const mensagemDeRecusa = (recusados, accept) => {
  const nomes = Array.from(recusados || [])
    .map((f) => f?.name)
    .filter(Boolean);
  if (nomes.length === 0) return "";
  const tipos = extensoesAceites(accept).join(", ");
  return `Não aceite: ${nomes.join(", ")}${tipos ? ` — só ${tipos}` : ""}`;
};

// ── O contador de entradas/saídas ──────────────────────────────────────

/** O estado inicial. `activo` é o que a UI usa para o realce. */
export const ARRASTO_PARADO = { profundidade: 0, activo: false };

export const arrastoEntrou = (estado = ARRASTO_PARADO) => {
  const profundidade = Math.max(0, estado.profundidade) + 1;
  return { profundidade, activo: true };
};

export const arrastoSaiu = (estado = ARRASTO_PARADO) => {
  const profundidade = Math.max(0, estado.profundidade - 1);
  return { profundidade, activo: profundidade > 0 };
};

/** Depois do `drop` (ou de um cancelamento) o estado volta a zero. */
export const arrastoTerminou = () => ARRASTO_PARADO;
