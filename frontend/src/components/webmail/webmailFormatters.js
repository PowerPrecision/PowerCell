/**
 * Formatadores partilhados do Webmail.
 *
 * Extraídos de `pages/WebmailPage.jsx` (Épico 6): viviam no topo do
 * monolito e são precisos por mais do que um dos componentes extraídos.
 * Movidos SEM alteração de comportamento — só mudaram de casa.
 */
import { format, isToday, isYesterday } from "date-fns";
import { pt } from "date-fns/locale";
import { File, FileSpreadsheet, FileText, Image } from "lucide-react";

import { safeFormat } from "../../lib/utils";

/** Data relativa ("HH:mm" hoje, "ontem", senão "dd/MM/yyyy"). */
export const formatEmailDate = (dateStr) => {
  if (!dateStr) return "";
  try {
    const date = new Date(dateStr);
    if (isNaN(date.getTime())) return "";
    if (isToday(date)) {
      return format(date, "HH:mm", { locale: pt });
    }
    if (isYesterday(date)) {
      return "ontem";
    }
    return format(date, "dd/MM/yyyy", { locale: pt });
  } catch {
    return "";
  }
};

/** Data por extenso para o painel de leitura. */
export const formatFullDate = (dateStr) => {
  if (!dateStr) return "-";
  return safeFormat(dateStr, "dd 'de' MMMM 'de' yyyy 'às' HH:mm", { locale: pt });
};

/** Tamanho de ficheiro legível (B / KB / MB). */
export const formatFileSize = (bytes) => {
  if (!bytes) return "";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
};

/** Ícone lucide adequado à extensão do anexo. */
export const getAttachmentIcon = (filename) => {
  if (!filename) return File;
  const lower = filename.toLowerCase();
  if (/\.(jpg|jpeg|png|gif|bmp|webp|svg|ico|tiff?)$/i.test(lower)) return Image;
  if (/\.(xls|xlsx|csv|ods)$/i.test(lower)) return FileSpreadsheet;
  if (/\.(doc|docx|pdf|txt|rtf|odt)$/i.test(lower)) return FileText;
  return File;
};
