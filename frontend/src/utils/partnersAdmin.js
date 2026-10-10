/**
 * Gestão de parceiros (lado do staff) — as regras do separador, sem React.
 *
 * A forma dos dados é a do servidor (`partner_accounts.publico`):
 *   { id, name, email, phone, status: "invited"|"active"|"suspended",
 *     redes: [{ network_id, company_id, company_name, status }],
 *     invite_pending, created_at, last_login_at }
 * — nunca o hash, o convite nem os termos.
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
  if (redes.length > 0 && activas.length === 0) return { chave: "suspenso", rotulo: "Suspenso", variant: "destructive" };
  if (activas.length < redes.length) return { chave: "parcial", rotulo: "Activo (parcial)", variant: "secondary" };
  return { chave: "activo", rotulo: "Activo", variant: "default" };
}

/** Há ligações activas que se possam suspender? (o botão diz «Suspender») */
export const podeSuspender = (parceiro) =>
  lista(parceiro?.redes).some((r) => (r.status || "active") === "active");

export const nomesDasEmpresas = (parceiro) =>
  lista(parceiro?.redes).map((r) => r.company_name || r.network_id).filter(Boolean).join(", ");

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
  if (!String(f.company_id).trim()) erros.company_id = "Escolha a empresa.";
  return erros;
}

/** O corpo do convite: só o que o servidor aceita (`extra="forbid"`). */
export function corpoDoConvite(form) {
  const f = { ...CONVITE_VAZIO, ...(form || {}) };
  const corpo = {
    name: String(f.name).trim(),
    email: String(f.email).trim(),
    company_id: String(f.company_id).trim(),
  };
  const telefone = String(f.phone).trim();
  if (telefone) corpo.phone = telefone;
  return corpo;
}
