import { clsx } from "clsx";
import { twMerge } from "tailwind-merge"
import { parseISO, format } from "date-fns";

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

/**
 * Normaliza uma string de data para formato compatível com Safari/iOS.
 * Safari não consegue fazer parse de 'YYYY-MM-DD HH:mm:ss' — precisa de
 * 'YYYY/MM/DD HH:mm:ss' ou 'YYYY-MM-DDTHH:mm:ss'.
 *
 * Retorna a string normalizada, ou null se a data for inválida.
 *
 * ⚠️ NOTA: Quando retorna null, parseISO(null) crasha com "Invalid time value".
 * Use safeParseISO() para parse seguro, ou safeFormat() para formatação segura.
 */
export const safeDateStr = (dateString) => {
  if (!dateString) return null;
  if (typeof dateString !== "string") {
    // Pode já ser um Date object
    if (dateString instanceof Date) return isNaN(dateString.getTime()) ? null : dateString;
    return null;
  }
  // Substituir dash por slash na parte da data (antes do T ou espaço)
  // Isto converte '2025-03-15 14:30:00' → '2025/03/15T14:30:00'
  // e '2025-03-15T14:30:00' → '2025/03/15T14:30:00'
  const normalized = dateString
    .replace(/(\d{4})-(\d{2})-(\d{2})/, "$1/$2/$3")
    .replace(" ", "T"); // garante formato ISO
  // Verificar se o resultado é uma data válida antes de retornar
  try {
    const testDate = new Date(normalized);
    if (isNaN(testDate.getTime())) return null;
  } catch {
    return null;
  }
  return normalized;
};

/**
 * Faz parseISO de forma segura — retorna null em vez de crashar com
 * "Invalid time value" quando safeDateStr retorna null ou a data é inválida.
 */
export const safeParseISO = (dateString) => {
  try {
    const normalized = safeDateStr(dateString);
    if (!normalized) return null;
    const parsed = parseISO(normalized);
    return isNaN(parsed.getTime()) ? null : parsed;
  } catch {
    return null;
  }
};

/**
 * Formata uma data com date-fns de forma segura — nunca crasha.
 * Retorna fallback (default "-") se a data for inválida.
 */
export const safeFormat = (dateString, formatStr, { locale } = {}) => {
  try {
    const parsed = safeParseISO(dateString);
    if (!parsed) return "-";
    return format(parsed, formatStr, { locale });
  } catch {
    return "-";
  }
};

/**
 * Cria um Date de forma segura em Safari/iOS.
 * Retorna null se a data for inválida.
 */
export const safeDate = (dateString) => {
  if (!dateString) return null;
  if (dateString instanceof Date) {
    return isNaN(dateString.getTime()) ? null : dateString;
  }
  try {
    const d = new Date(safeDateStr(dateString));
    return isNaN(d.getTime()) ? null : d;
  } catch {
    return null;
  }
};

/**
 * Formata uma data para exibição (dd/MM/yyyy) — seguro em Safari/iOS.
 */
export const formatDate = (dateString) => {
  if (!dateString) return "-";
  try {
    const d = safeDate(dateString);
    if (!d) return "-";
    return new Intl.DateTimeFormat("pt-PT", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    }).format(d);
  } catch {
    return "-";
  }
};

/**
 * Formata uma data+hora para exibição (dd/MM/yyyy HH:mm) — seguro em Safari/iOS.
 */
export const formatDateTime = (dateString) => {
  if (!dateString) return "-";
  try {
    const d = safeDate(dateString);
    if (!d) return "-";
    return new Intl.DateTimeFormat("pt-PT", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(d);
  } catch {
    return "-";
  }
};
