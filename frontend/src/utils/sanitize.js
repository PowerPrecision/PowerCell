/**
 * Utilitário de Sanitização HTML - SEGURANÇA
 * 
 * Usa DOMPurify para prevenir ataques XSS quando renderizar HTML dinâmico.
 * NUNCA use dangerouslySetInnerHTML sem sanitização prévia!
 * 
 * Exemplo de uso:
 *   import { sanitizeHtml } from '../utils/sanitize';
 *   <div dangerouslySetInnerHTML={{ __html: sanitizeHtml(userContent) }} />
 */
import DOMPurify from 'dompurify';

// Configuração padrão - permite tags HTML seguras mas remove scripts
const DEFAULT_CONFIG = {
  ALLOWED_TAGS: [
    'a', 'b', 'i', 'u', 'strong', 'em', 'br', 'p', 'div', 'span',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'ul', 'ol', 'li', 'table', 'thead', 'tbody', 'tr', 'td', 'th',
    'img', 'hr', 'blockquote', 'pre', 'code',
    'sub', 'sup', 'small', 'mark', 'del', 'ins'
  ],
  ALLOWED_ATTR: [
    'href', 'src', 'alt', 'title', 'class', 'id',
    'style', 'width', 'height', 'target', 'rel',
    'colspan', 'rowspan'
  ],
  ALLOW_DATA_ATTR: false, // Não permitir atributos data-*
  ADD_ATTR: ['target', 'rel'], // Permitir target e rel para links
  FORCE_BODY: true, // Forçar parsing como body (previne ataques com head)
};

// Configuração para emails - mais permissiva para formatação
// PACOTE DM: permitir data:image e cid: para imagens da assinatura
const EMAIL_URI_REGEXP = /^(?:(?:(?:f|ht)tps?|mailto|tel|cid|data|blob):|[^a-z]|[a-z+.-]+(?:[^a-z+.-:]|$))/i;

const EMAIL_CONFIG = {
  ...DEFAULT_CONFIG,
  ALLOWED_TAGS: [
    ...DEFAULT_CONFIG.ALLOWED_TAGS,
    'font', 'center', 'strike', 'tt'
  ],
  ALLOWED_ATTR: [
    ...DEFAULT_CONFIG.ALLOWED_ATTR,
    'color', 'face', 'size', 'align', 'bgcolor', 'border',
    'cellpadding', 'cellspacing', 'valign'
  ],
  ALLOWED_URI_REGEXP: EMAIL_URI_REGEXP,
};

/**
 * Sanitiza HTML para prevenir XSS.
 * 
 * @param {string} html - HTML a sanitizar
 * @param {object} options - Opções de configuração (opcional)
 * @returns {string} HTML sanitizado
 */
export function sanitizeHtml(html, options = {}) {
  if (!html || typeof html !== 'string') {
    return '';
  }
  
  const config = { ...DEFAULT_CONFIG, ...options };
  return DOMPurify.sanitize(html, config);
}

/**
 * Se o HTML foi gravado com entidades (&lt;p&gt;), devolve o markup real.
 * Evita mostrar tags como texto cru na Área Pessoal e no compositor.
 */
export function unescapeHtmlIfNeeded(html) {
  if (!html || typeof html !== 'string') {
    return '';
  }

  const trimmed = html.trim();
  const looksEscaped = /^&lt;[a-z!/]/i.test(trimmed)
    || (trimmed.includes('&lt;') && !trimmed.includes('<'));
  if (!looksEscaped) {
    return html;
  }

  return trimmed
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, '&');
}

/**
 * Sanitiza HTML de emails.
 * Mais permissivo para compatibilidade com emails formatados.
 * 
 * @param {string} html - HTML do email a sanitizar
 * @returns {string} HTML sanitizado
 */
export function sanitizeEmailHtml(html) {
  if (!html || typeof html !== 'string') {
    return '';
  }

  const unescaped = unescapeHtmlIfNeeded(html);

  // Primeiro, remover scripts e handlers inline
  let cleaned = unescaped
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
    .replace(/on\w+\s*=\s*["'][^"']*["']/gi, '')
    .replace(/javascript:/gi, '');
  
  // Depois sanitizar com DOMPurify (imagens data:/https/cid permitidas)
  return DOMPurify.sanitize(cleaned, EMAIL_CONFIG);
}

/**
 * Sanitiza URL para prevenir javascript: e outros protocolos perigosos.
 * 
 * @param {string} url - URL a verificar
 * @returns {string|null} URL segura ou null se perigosa
 */
export function sanitizeUrl(url) {
  if (!url || typeof url !== 'string') {
    return null;
  }
  
  // Remover espaços e caracteres de controlo
  const cleaned = url.trim().replace(/[\x00-\x1F\x7F]/gu, ''); // eslint-disable-line no-control-regex
  
  // Verificar protocolos perigosos
  const dangerousProtocols = [
    'javascript:', 'vbscript:', 'data:text/html',
    'data:application/javascript'
  ];
  
  const lowerUrl = cleaned.toLowerCase();
  for (const protocol of dangerousProtocols) {
    if (lowerUrl.startsWith(protocol)) {
      console.warn('[SECURITY] URL bloqueada por protocolo perigoso:', url);
      return null;
    }
  }
  
  // Permitir apenas http, https, mailto, tel
  const safeProtocols = ['http://', 'https://', 'mailto:', 'tel:', '/', '#'];
  const hasSafeProtocol = safeProtocols.some(p => lowerUrl.startsWith(p));
  
  if (!hasSafeProtocol && !cleaned.startsWith('.')) {
    // URL relativa ou sem protocolo - assumir segura
    return cleaned;
  }
  
  return cleaned;
}

/**
 * Remove todos os elementos HTML, retornando apenas texto.
 * Útil para previews ou quando não se quer nenhuma formatação.
 * 
 * @param {string} html - HTML a converter
 * @returns {string} Texto puro
 */
export function htmlToText(html) {
  if (!html || typeof html !== 'string') {
    return '';
  }
  
  return DOMPurify.sanitize(html, { ALLOWED_TAGS: [] });
}

export default {
  sanitizeHtml,
  sanitizeEmailHtml,
  sanitizeUrl,
  htmlToText,
  unescapeHtmlIfNeeded,
};
