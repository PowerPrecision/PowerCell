/**
 * Gestão de parceiros (lado do staff) — as regras do separador, sem React.
 *
 * A forma dos dados é a do servidor (`partner_accounts.publico`):
 *   { id, name, email, phone, status: "invited"|"active"|"suspended",
 *     redes: [{ network_id, company_id, company_name, status }],
 *     invite_pending, created_at, last_login_at }
 * — nunca o hash, o convite nem os termos.
 *
 * `redes` vazio = agente INDEPENDENTE (Lote 5): um parceiro é um operador externo
 * e não pertence a uma empresa; a primeira lead que submete a uma empresa de
 * destino cria a ligação. Para ele a suspensão actua na conta (`status`).
 */

const lista = (v) => (Array.isArray(v) ? v : []);

/** `{partners, total}` → array de parceiros com a forma garantida. */
export function normalizarParceiros(resposta) {
  const r = resposta && typeof resposta === "object" ? resposta : {};
  return lista(r.partners)
    .filter((p) => p && typeof p === "object" && p.id)
    .map((p) => ({ ...p, redes: lista(p.redes).filter((x) => x && typeof x === "object") }));
}

/** O estado que a equipa lê: o da CONTA e o das LIGAÇÕES às redes. */
export function estadoDoParceiro(parceiro) {
  const redes = lista(parceiro?.redes);
  const activas = redes.filter((r) => (r.status || "active") === "active");
  if (parceiro?.status === "invited") return { chave: "convidado", rotulo: "Convite pendente", variant: "outline" };
  if (parceiro?.status === "suspended") return { chave: "suspenso", rotulo: "Suspenso", variant: "destructive" };
  if (redes.length > 0 && activas.length === 0) return { chave: "suspenso", rotulo: "Suspenso", variant: "destructive" };
  if (activas.length < redes.length) return { chave: "parcial", rotulo: "Activo (parcial)", variant: "secondary" };
  return { chave: "activo", rotulo: "Activo", variant: "default" };
}

export const eIndependente = (parceiro) => lista(parceiro?.redes).length === 0;

/** Há algo activo que se possa suspender? (o botão diz «Suspender») */
export const podeSuspender = (parceiro) =>
  !parceiro
    ? false
    : eIndependente(parceiro)
      ? parceiro.status !== "suspended"
      : lista(parceiro?.redes).some((r) => (r.status || "active") === "active");

export const ROTULO_INDEPENDENTE = "Independente";

export const nomesDasEmpresas = (parceiro) =>
  eIndependente(parceiro)
    ? ROTULO_INDEPENDENTE
    : lista(parceiro?.redes).map((r) => r.company_name || r.network_id).filter(Boolean).join(", ");

/** O link completo do convite, a partir do caminho que o servidor devolve. */
export function linkDoConvite(caminho, origem) {
  const base = String(origem || "").replace(/\/+$/, "");
  const sufixo = String(caminho || "");
  return sufixo.startsWith("/") ? `${base}${sufixo}` : `${base}/${sufixo}`;
}

export const CONVITE_VAZIO = { name: "", email: "", phone: "", company_id: "" };

export function validarConvite(form) {
  const f = { ...CONVITE_VAZIO, ...(form || {}) };
  const erros = {};
  if (String(f.name).trim().length < 2) erros.name = "Indique o nome do parceiro.";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(String(f.email).trim())) erros.email = "Indique um email válido.";
  // A empresa é OPCIONAL (Lote 5): o parceiro é independente e escolhe o destino de cada lead.
  return erros;
}

/** O corpo do convite: só o que o servidor aceita (`extra="forbid"`). */
export function corpoDoConvite(form) {
  const f = { ...CONVITE_VAZIO, ...(form || {}) };
  const corpo = {
    name: String(f.name).trim(),
    email: String(f.email).trim(),
  };
  const empresa = String(f.company_id).trim();
  if (empresa) corpo.company_id = empresa;
  const telefone = String(f.phone).trim();
  if (telefone) corpo.phone = telefone;
  return corpo;
}

const EMAIL_VALIDO = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

/** O formulário de edição, a partir do parceiro que vem do servidor. */
export const formularioDeEdicao = (parceiro) => ({
  name: parceiro?.name || "",
  email: parceiro?.email || "",
  phone: parceiro?.phone || "",
});

export function validarEdicao(form, { podeMudarEmail = false } = {}) {
  const f = { name: "", email: "", phone: "", ...(form || {}) };
  const erros = {};
  if (String(f.name).trim().length < 2) erros.name = "Indique o nome do parceiro.";
  if (podeMudarEmail && !EMAIL_VALIDO.test(String(f.email).trim())) erros.email = "Indique um email válido.";
  return erros;
}

/**
 * O corpo do PATCH: SÓ o que mudou (o servidor recusa o email a quem não é Master, e um corpo com o
 * email inalterado não pode falhar por isso). Email igual — sem distinguir maiúsculas — não vai.
 * `null` = nada a gravar.
 */
export function corpoDaEdicao(parceiro, form, { podeMudarEmail = false } = {}) {
  const base = formularioDeEdicao(parceiro);
  const f = { ...base, ...(form || {}) };
  const corpo = {};
  const nome = String(f.name).trim();
  if (nome !== base.name) corpo.name = nome;
  const telefone = String(f.phone).trim();
  if (telefone !== base.phone) corpo.phone = telefone;
  const email = String(f.email).trim();
  if (podeMudarEmail && email.toLowerCase() !== base.email.toLowerCase()) corpo.email = email;
  return Object.keys(corpo).length ? corpo : null;
}
