/**
 * Portal do Parceiro — as regras do ecrã, sem React.
 *
 * A FORMA DOS DADOS É A DO SERVIDOR, lida no backend e fixada por fixtures
 * geradas pelos próprios serviços (`test_parceiro_contrato_frontend.py`):
 *
 *   GET /partner/dashboard → { funil: [{etapa, label, total}], total_de_casos,
 *                              escriturados, leads, taxa_de_conversao|null,
 *                              pedidos_pendentes }
 *   GET /partner/cases     → { items: [caso], total, page, size, pages }
 *   GET /partner/cases/:id → caso + { pedidos: [...], ficheiros: [...] }
 *
 * `Array.isArray`, nunca `|| []` (um objecto é *truthy* e o erro só muda de
 * sítio), e a forma normaliza-se UMA vez, aqui — a regra do
 * `utils/kanbanColunas.js`.
 */

/** Os tipos que o botão E o arrasto aceitam: uma constante por superfície. */
export const TIPOS_ACEITES_NO_PARCEIRO = ".pdf,.jpg,.jpeg,.png,.doc,.docx";

export const ETAPA_LEAD = "lead";
export const ETAPA_CONCLUIDO = "concluido";
export const ETAPA_PERDIDO = "perdido";
// O filtro de viabilidade: a lead fica RETIDA do lado do parceiro até haver
// um Comprovativo de Pagamento.
export const ETAPA_PENDENTE = "pendente";
export const ETAPA_DEVOLVIDA = "devolvida";
export const ETAPA_EXPIRADO = "expirado";

/** A categoria que liberta uma lead retida (o valor que o servidor reconhece). */
export const CATEGORIA_DO_COMPROVATIVO = "Comprovativo_Pagamento";

/** Etapas em que o parceiro ainda pode editar os dados e enviar ficheiros. */
export const ETAPAS_DE_LEAD_RETIDA = [ETAPA_PENDENTE, ETAPA_DEVOLVIDA];

/** Variante do `Badge` por etapa — tokens semânticos, nunca cores cruas. */
export function variantDaEtapa(etapa) {
  switch (etapa) {
    case ETAPA_CONCLUIDO:
      return "default";
    case ETAPA_PERDIDO:
    case ETAPA_DEVOLVIDA:
      return "destructive";
    case ETAPA_LEAD:
    case ETAPA_PENDENTE:
      return "secondary";
    default:
      return "outline";
  }
}

const numero = (v) => (typeof v === "number" && Number.isFinite(v) ? v : 0);
const texto = (v) => (typeof v === "string" ? v : "");

/** O painel, com a forma garantida (a lista do funil é SEMPRE um array). */
export function normalizarPainel(resposta) {
  const r = resposta && typeof resposta === "object" ? resposta : {};
  return {
    funil: (Array.isArray(r.funil) ? r.funil : [])
      .filter((e) => e && typeof e === "object" && texto(e.etapa))
      .map((e) => ({ etapa: texto(e.etapa), label: texto(e.label) || texto(e.etapa), total: numero(e.total) })),
    totalDeCasos: numero(r.total_de_casos),
    escriturados: numero(r.escriturados),
    leads: numero(r.leads),
    pendentes: numero(r.pendentes),
    // `null` é «sem base» — NÃO é zero: «0 %» a quem ainda não trouxe nada lê-se como fracasso.
    taxaDeConversao: typeof r.taxa_de_conversao === "number" ? r.taxa_de_conversao : null,
    pedidosPendentes: numero(r.pedidos_pendentes),
  };
}

export function formatarConversao(taxa) {
  if (typeof taxa !== "number" || !Number.isFinite(taxa)) return "—";
  return `${taxa.toLocaleString("pt-PT", { minimumFractionDigits: 0, maximumFractionDigits: 1 })} %`;
}

/** A lista de casos, com a forma garantida. */
export function normalizarCasos(resposta) {
  const r = resposta && typeof resposta === "object" ? resposta : {};
  const items = Array.isArray(r.items) ? r.items.filter((c) => c && typeof c === "object" && c.id) : [];
  return {
    items,
    total: numero(r.total) || items.length,
    page: Math.max(1, numero(r.page) || 1),
    pages: Math.max(1, numero(r.pages) || 1),
  };
}

/** O detalhe de um caso: pedidos e ficheiros são SEMPRE arrays. */
export function normalizarCaso(resposta) {
  const r = resposta && typeof resposta === "object" ? resposta : {};
  const ficheiros = (lista) =>
    (Array.isArray(lista) ? lista : []).filter((f) => f && typeof f === "object" && f.id);
  return {
    ...r,
    pedidos: (Array.isArray(r.pedidos) ? r.pedidos : [])
      .filter((p) => p && typeof p === "object" && p.id)
      .map((p) => ({ ...p, ficheiros: ficheiros(p.ficheiros) })),
    ficheiros: ficheiros(r.ficheiros),
    // As categorias que o parceiro pode escolher (as do Portal do Cliente +
    // o Comprovativo de Pagamento), sempre uma lista.
    categorias: (Array.isArray(r.categorias) ? r.categorias : []).filter(
      (c) => c && typeof c === "object" && texto(c.value)
    ),
  };
}

/** A lead está retida (pendente ou devolvida): falta o Comprovativo de Pagamento. */
export function leadRetida(caso) {
  return caso?.kind === "lead" && ETAPAS_DE_LEAD_RETIDA.includes(caso?.etapa);
}

/** Uma lead que expirou (60 dias sem actividade): vê-se, já não se trabalha. */
export function leadExpirada(caso) {
  return caso?.kind === "lead" && caso?.etapa === ETAPA_EXPIRADO;
}

/**
 * Documentos «Pendentes» e «Submetidos» — a divisão que o parceiro vê.
 *
 * Pendentes: os pedidos por satisfazer (e, numa lead retida, o comprovativo
 * obrigatório — tratado à parte pela página). Submetidos: os pedidos já
 * recebidos e os ficheiros soltos que enviou ou que o cliente enviou.
 */
export function separarDocumentos(caso) {
  return {
    pendentes: pedidosPendentes(caso),
    pedidosSubmetidos: pedidosRecebidos(caso),
    ficheirosSubmetidos: caso?.ficheiros || [],
  };
}

/** Pode descarregar? O que o próprio parceiro submeteu não se descarrega. */
export function podeDescarregar(ficheiro) {
  return ficheiro?.by !== "eu";
}

/** Os pedidos por satisfazer, primeiro — é com eles que parceiro e consultor falam. */
export function pedidosPendentes(caso) {
  return (caso?.pedidos || []).filter((p) => p.estado === "pendente");
}

export function pedidosRecebidos(caso) {
  return (caso?.pedidos || []).filter((p) => p.estado !== "pendente");
}

/**
 * `1/3` — o progresso de um pedido com várias peças.
 *
 * `uploaded_count` é a contagem que decide o estado do pedido no servidor e
 * inclui ficheiros que a EQUIPA juntou; o ecrã não a mostra acima do pedido
 * (um «4/1» não diz nada ao parceiro e deixaria adivinhar o que não vê).
 */
export function progressoDoPedido(pedido) {
  const esperados = Math.max(1, numero(pedido?.expected_count) || 1);
  return { enviados: Math.min(numero(pedido?.uploaded_count), esperados), esperados };
}

export function rotuloDeAutoria(by) {
  return by === "eu" ? "Enviado por si" : "Enviado pelo cliente";
}

export function tamanhoLegivel(bytes) {
  const n = numero(bytes);
  if (n <= 0) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatarData(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("pt-PT", { day: "2-digit", month: "short", year: "numeric" });
}

/** A mensagem de um erro do servidor (`detail` em texto ou a lista do 422). */
export function mensagemDeErro(erro, recuo = "Ocorreu um erro. Tente novamente.") {
  const detail = erro?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length) {
    const primeiro = detail[0];
    const msg = typeof primeiro === "string" ? primeiro : primeiro?.msg;
    if (typeof msg === "string" && msg.trim()) return msg;
  }
  if (detail && typeof detail === "object" && typeof detail.message === "string") return detail.message;
  if (erro?.response?.status === 429) return "Demasiados pedidos. Aguarde um momento.";
  if (!erro?.response && erro?.message) return "Sem ligação ao servidor. Verifique a sua internet.";
  return recuo;
}

// ── A lead ──────────────────────────────────────────────────────────
export const TIPOS_DE_PROCESSO = [
  { value: "credito_habitacao", label: "Crédito habitação" },
  { value: "credito_pessoal", label: "Crédito pessoal" },
  { value: "compra_direta", label: "Compra directa" },
  { value: "refinanciamento", label: "Refinanciamento" },
  { value: "arrendamento", label: "Arrendamento" },
  { value: "seguros", label: "Seguros" },
  { value: "consultoria", label: "Consultoria" },
  { value: "outro", label: "Outro" },
];

export const LEAD_VAZIA = {
  name: "",
  email: "",
  phone: "",
  nif: "",
  process_type: "credito_habitacao",
  has_property: false,
  notes: "",
  consent_confirmed: false,
};

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

/** Erros por campo. Vazio = pode enviar. A validação real é a do servidor. */
export function validarLead(form) {
  const f = { ...LEAD_VAZIA, ...(form || {}) };
  const erros = {};
  if (texto(f.name).trim().length < 2) erros.name = "Indique o nome do cliente.";
  if (!EMAIL.test(texto(f.email).trim())) erros.email = "Indique um email válido.";
  const nif = texto(f.nif).replace(/\s/g, "");
  if (nif && !/^\d{9}$/.test(nif)) erros.nif = "O NIF tem 9 dígitos.";
  if (!f.consent_confirmed) erros.consent_confirmed = "Confirme que tem autorização do cliente.";
  return erros;
}

/**
 * O corpo do pedido: SÓ os campos que o servidor aceita (`extra="forbid"`),
 * sem os opcionais vazios. Nada de carimbos — rede, empresa, estado e autor
 * são do servidor, e enviá-los seria um 422.
 */
export function construirPayloadDaLead(form, redeEscolhida) {
  const f = { ...LEAD_VAZIA, ...(form || {}) };
  const payload = {
    name: texto(f.name).trim(),
    email: texto(f.email).trim(),
    process_type: f.process_type || LEAD_VAZIA.process_type,
    has_property: Boolean(f.has_property),
    consent_confirmed: Boolean(f.consent_confirmed),
  };
  const opcionais = {
    phone: texto(f.phone).trim(),
    nif: texto(f.nif).replace(/\s/g, ""),
    notes: texto(f.notes).trim(),
  };
  for (const [chave, valor] of Object.entries(opcionais)) {
    if (valor) payload[chave] = valor;
  }
  if (redeEscolhida) payload.network_id = redeEscolhida;
  return payload;
}

/** Ligações activas do parceiro (para escolher a rede quando há mais do que uma). */
export function redesActivas(partner) {
  return (Array.isArray(partner?.redes) ? partner.redes : []).filter(
    (r) => r && r.network_id && (r.status || "active") === "active"
  );
}

/** O caminho do detalhe de um caso. */
export const caminhoDoCaso = (id) => `/parceiro/casos/${encodeURIComponent(id)}`;
