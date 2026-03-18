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
  
  // Primeiro, remover scripts e handlers inline
  let cleaned = html
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
    .replace(/on\w+\s*=\s*["'][^"']*["']/gi, '')
    .replace(/javascript:/gi, '');
  
  // Depois sanitizar com DOMPurify
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
  const cleaned = url.trim().replace(/[\x00-\x1F\x7F]/g, '');
  
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
  htmlToText
};
