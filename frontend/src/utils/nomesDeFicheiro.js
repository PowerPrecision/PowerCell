/**
 * Nomes de ficheiros que não pisam os que já existem (upload da bancada do Index).
 *
 * O upload do CRM sobrepõe por omissão um ficheiro com o mesmo nome: carregar `recibo.pdf` duas vezes
 * substituía o primeiro sem ninguém dar por isso — perder um documento do dossier. A bancada nunca sobrepõe:
 * um nome que já existe (ou que já foi usado neste mesmo lote) ganha ` (2)`, ` (3)`… antes da extensão.
 */
const separar = (nome) => {
  const texto = String(nome || "documento");
  const ponto = texto.lastIndexOf(".");
  return ponto > 0 ? [texto.slice(0, ponto), texto.slice(ponto)] : [texto, ""];
};

const chave = (nome) => String(nome || "").trim().toLowerCase();

/**
 * @param {string} nome — o nome pretendido
 * @param {Iterable<string>} ocupados — nomes já existentes (sem distinguir maiúsculas)
 * @returns {string} o mesmo nome se estiver livre; senão `base (n).ext` com o menor n livre
 */
export function nomeLivre(nome, ocupados) {
  const usados = new Set([...(ocupados || [])].map(chave));
  if (!usados.has(chave(nome))) return nome;
  const [base, extensao] = separar(nome);
  for (let n = 2; n < 1000; n += 1) {
    const candidato = `${base} (${n})${extensao}`;
    if (!usados.has(chave(candidato))) return candidato;
  }
  return `${base} (${Date.now()})${extensao}`;
}

/** Atribui um nome livre a cada ficheiro de um lote, contando também os nomes que o lote vai usar. */
export function nomesLivresDoLote(nomes, existentes) {
  const ocupados = new Set([...(existentes || [])].map(chave));
  return (nomes || []).map((nome) => {
    const escolhido = nomeLivre(nome, ocupados);
    ocupados.add(chave(escolhido));
    return escolhido;
  });
}
