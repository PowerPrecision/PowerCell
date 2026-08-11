/**
 * Validação de NIF português para clientes particulares.
 *
 * PORQUÊ: esta era a versão "fraca" (sem checksum) enquanto 3 formulários
 * (`PublicClientForm`, `CPCVModal`, `RGPDPage`) mantinham cada um a sua própria
 * cópia local com o algoritmo de checksum (módulo 11) — o formulário interno
 * (`ProcessDetails`) validava menos do que os formulários públicos. Esta função
 * passa a incluir o mesmo checksum, tornando-se a única fonte de verdade.
 *
 * Algoritmo de checksum (norma NIF/NIPC português):
 * - Multiplicar os primeiros 8 dígitos pelos pesos [9,8,7,6,5,4,3,2].
 * - Somar, calcular o resto da divisão por 11.
 * - Dígito de controlo = 0 se resto < 2, senão 11 - resto.
 * - O 9º dígito do NIF deve ser igual ao dígito de controlo calculado.
 *
 * @param {Object} [options]
 * @param {boolean} [options.allowCompanyNIF=false] - Se true, permite NIFs de
 *   empresa (a começar por 5) — usado em contextos onde a contraparte pode ser
 *   uma pessoa colectiva (ex. CPCV: vendedor/comprador de um imóvel).
 * @returns {{ valid: boolean, error: string|null }}
 */
export function validateNIF(nif, options = {}) {
  const { allowCompanyNIF = false } = options;

  if (!nif) return { valid: true, error: null };

  const nifClean = nif.replace(/[^\d]/g, "");

  if (nifClean.length !== 9) {
    return { valid: false, error: `NIF deve ter 9 dígitos (tem ${nifClean.length})` };
  }

  if (!/^\d+$/.test(nifClean)) {
    return { valid: false, error: "NIF deve conter apenas dígitos" };
  }

  // NIFs que começam com 5 são de empresas
  if (!allowCompanyNIF && nifClean.startsWith("5")) {
    return {
      valid: false,
      error: "NIF de empresa (começa por 5) não é permitido para clientes particulares",
    };
  }

  const digits = nifClean.split("").map(Number);
  const weights = [9, 8, 7, 6, 5, 4, 3, 2];
  const sum = digits.slice(0, 8).reduce((acc, d, i) => acc + d * weights[i], 0);
  const remainder = sum % 11;
  const checkDigit = remainder < 2 ? 0 : 11 - remainder;

  if (checkDigit !== digits[8]) {
    return { valid: false, error: "NIF inválido (dígito de controlo incorreto)" };
  }

  return { valid: true, error: null };
}
