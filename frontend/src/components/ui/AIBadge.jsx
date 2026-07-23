/**
 * AIBadge — Indicador visual de proveniência de dados (Data Provenance).
 *
 * Mostra um ícone subtil ao lado de campos de formulário para indicar
 * a origem do valor:
 *   - "ai"     → Ícone Sparkles (roxo) + tooltip "Preenchido pela IA"
 *   - "client" → Ícone User (teal) + tooltip "Preenchido pelo Cliente no Portal"
 *   - "manual" → NÃO renderiza nada (o humano sobrepôs o dado)
 *
 * Consome o objeto `field_metadata` que vive nos documentos de clients
 * e processes (Pacote CS — Data Provenance Foundation). Cada entrada tem
 * a forma: { source: "ai"|"manual"|"client", updated_at: "ISO", confidence: 0.95 }
 *
 * @see /home/z/my-project/worklog.md — Pacote CS (backend) + Pacote CT (UI)
 *
 * @example
 * // Ao lado da label de um campo:
 * <Label>NIF</Label>
 * <AIBadge source="ai" updated_at="2026-07-16T10:30:00Z" confidence={0.95} />
 *
 * @example
 * // Lendo do field_metadata:
 * <AIBadge {...(client.field_metadata?.["dados_pessoais.nif"] || {})} />
 */
import { Sparkles, User } from "lucide-react";
import { Badge } from "./badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "./tooltip";
import { cn, safeFormat } from "@/lib/utils";

/**
 * Configuração visual por origem.
 * "manual" é omitido intencionalmente — o componente retorna null para essa source.
 */
export const AI_SOURCE_CONFIG = {
  ai: {
    icon: Sparkles,
    badgeClass:
      "bg-purple-50 text-purple-700 border-purple-200 " +
      "dark:bg-purple-950/40 dark:text-purple-300 dark:border-purple-800",
    label: "Preenchido pela IA",
    shortLabel: "IA",
  },
  client: {
    icon: User,
    badgeClass:
      "bg-teal-50 text-teal-700 border-teal-200 " +
      "dark:bg-teal-950/40 dark:text-teal-300 dark:border-teal-800",
    label: "Preenchido pelo Cliente no Portal",
    shortLabel: "Cliente",
  },
};

/**
 * Formata a data de atualização para apresentação na tooltip.
 * Retorna null se a data for inválida/ausente.
 */
function formatMetaDate(updated_at) {
  if (!updated_at) return null;
  const formatted = safeFormat(updated_at, "dd/MM/yyyy 'às' HH:mm");
  // safeFormat retorna "-" em caso de falha
  return formatted && formatted !== "-" ? formatted : null;
}

/**
 * AIBadge
 *
 * @param {("ai"|"client"|"manual")} source   — origem do dado
 * @param {string}                    [updated_at]  — ISO date string
 * @param {number}                    [confidence]  — 0..1 (apenas para ai)
 * @param {boolean}                   [compact=true] — se true mostra só ícone
 * @param {string}                    [className]   — classes extra
 */
function AIBadge({ source, updated_at, confidence, compact = true, className }) {
  // "manual" ou source ausente/desconhecida → não renderiza nada
  if (!source || source === "manual") return null;

  const config = AI_SOURCE_CONFIG[source];
  if (!config) return null;

  const Icon = config.icon;
  const dateStr = formatMetaDate(updated_at);
  const confidencePct =
    typeof confidence === "number" && !isNaN(confidence)
      ? Math.round(confidence * 100)
      : null;

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge
            variant="outline"
            className={cn(
              "gap-0.5 px-1 py-0 text-[9px] leading-none cursor-help select-none",
              config.badgeClass,
              className
            )}
          >
            <Icon className="h-2.5 w-2.5" />
            {!compact && <span>{config.shortLabel}</span>}
          </Badge>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="max-w-xs">
          <p className="font-semibold">{config.label}</p>
          {confidencePct !== null && (
            <p className="text-xs mt-1">Confiança: {confidencePct}%</p>
          )}
          {dateStr && (
            <p className="text-xs text-muted-foreground mt-0.5">
              Atualizado a {dateStr}
            </p>
          )}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

/**
 * Helper: extrai a entrada de field_metadata para um dado caminho de campo.
 *
 * Aceita tanto um único objecto field_metadata como múltiplos (merge —
 * os últimos ganham prioridade). Útil para combinar client.field_metadata
 * com process.field_metadata.
 *
 * @example
 * const meta = getFieldMeta("dados_pessoais.nif", client.field_metadata);
 * const meta = getFieldMeta("real_estate_data.valor_imovel", process.field_metadata);
 * const meta = getFieldMeta("dados_pessoais.nif", client?.field_metadata, process?.field_metadata);
 *
 * @param {string} fieldPath — ex: "dados_pessoais.nif"
 * @param  {...(object|null|undefined)} metadataSources — objetos field_metadata
 * @returns {{source:string, updated_at:string, confidence:number}|null}
 */
export function getFieldMeta(fieldPath, ...metadataSources) {
  if (!fieldPath) return null;
  for (const src of metadataSources) {
    if (src && typeof src === "object" && src[fieldPath]) {
      return src[fieldPath];
    }
  }
  return null;
}

/**
 * Helper: constrói uma entrada de field_metadata para marcação manual.
 * Usado pelos formulários ao guardar edições feitas pelo Consultor.
 *
 * @returns {{source:"manual", updated_at:string}}
 */
export function buildManualMeta() {
  return {
    source: "manual",
    updated_at: new Date().toISOString(),
  };
}

/**
 * Helper: constrói um sub-objecto field_metadata para um conjunto de campos,
 * marcando todos como "manual". Usado no payload de PUT/PATCH para propagar
 * a proveniência manual ao backend (que fará o merge seguro — Pacote CS).
 *
 * @param {string[]} fieldPaths — ex: ["dados_pessoais.nif", "contacto.email"]
 * @returns {Object<string,{source:"manual",updated_at:string}>}
 */
export function buildManualMetadata(fieldPaths) {
  if (!Array.isArray(fieldPaths) || fieldPaths.length === 0) return null;
  const now = new Date().toISOString();
  const out = {};
  for (const p of fieldPaths) {
    if (p) out[p] = { source: "manual", updated_at: now };
  }
  return Object.keys(out).length > 0 ? out : null;
}

export { AIBadge };
export default AIBadge;
