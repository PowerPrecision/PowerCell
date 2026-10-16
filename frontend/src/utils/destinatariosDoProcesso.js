/**
 * Quem vai no campo «Para» quando se escreve um email a partir de um processo (Lote 7.3).
 *
 * Os endereços do CLIENTE (titular e, havendo, 2.º titular) e os do(s) INTERMEDIÁRIO(S) atribuídos
 * ao processo vêm preenchidos; os anexos continuam vazios — pré-seleccionar documentos enviaria
 * dados do cliente por omissão. Puro: o que vem do servidor entra por argumento.
 */

const EMAIL = /^[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+$/;

/** Endereço em minúsculas, ou `""` se não for um email utilizável. */
export function normalizarEmail(valor) {
  if (typeof valor !== "string") return "";
  const texto = valor.trim().toLowerCase();
  return EMAIL.test(texto) ? texto : "";
}

function semRepetidos(lista) {
  const vistos = new Set();
  const saida = [];
  for (const email of lista) {
    const e = normalizarEmail(email);
    if (e && !vistos.has(e)) {
      vistos.add(e);
      saida.push(e);
    }
  }
  return saida;
}

/** Emails do titular e do 2.º titular, nesta ordem. */
export function emailsDosClientes(processo) {
  const p = processo || {};
  const titular2 = p.titular2_data && typeof p.titular2_data === "object" ? p.titular2_data : {};
  return semRepetidos([
    p.client_email,
    p.second_client_email,
    titular2.email,
    titular2.contacto && typeof titular2.contacto === "object" ? titular2.contacto.email : "",
  ]);
}

/** Ids dos intermediários (mediadores) atribuídos ao processo, sem repetidos. */
export function idsDosIntermediarios(processo) {
  const p = processo || {};
  const ids = [
    ...(Array.isArray(p.assigned_mediador_ids) ? p.assigned_mediador_ids : []),
    p.assigned_mediador_id,
    p.mediador_id,
  ].filter((v) => typeof v === "string" && v);
  return [...new Set(ids)];
}

/**
 * @param {object} processo   O processo como o servidor o serve.
 * @param {object[]} [equipa] Utilizadores que o processo alcança (`GET /users?process_id=`), com `id` e `email`.
 * @returns {{clientes: string[], intermediarios: string[], para: string[]}}
 */
export function destinatariosDoProcesso(processo, equipa) {
  const clientes = emailsDosClientes(processo);
  const lista = Array.isArray(equipa) ? equipa : [];
  const porId = new Map(lista.filter((u) => u && u.id).map((u) => [u.id, u]));
  const intermediarios = semRepetidos(
    idsDosIntermediarios(processo).map((id) => porId.get(id)?.email),
  ).filter((e) => !clientes.includes(e));
  return { clientes, intermediarios, para: [...clientes, ...intermediarios] };
}
