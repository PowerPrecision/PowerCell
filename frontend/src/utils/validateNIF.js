/**
 * Validação de NIF português para clientes particulares.
 * Extraído de ProcessDetails.js.
 *
 * @returns {{ valid: boolean, error: string|null }}
 */
export function validateNIF(nif) {
  if (!nif) return { valid: true, error: null };

  const nifClean = nif.replace(/[^\d]/g, "");

  if (nifClean.length !== 9) {
    return { valid: false, error: `NIF deve ter 9 dígitos (tem ${nifClean.length})` };
  }

  if (!/^\d+$/.test(nifClean)) {
    return { valid: false, error: "NIF deve conter apenas dígitos" };
  }

  // NIFs que começam com 5 são de empresas
  if (nifClean.startsWith("5")) {
    return {
      valid: false,
      error: "NIF de empresa (começa por 5) não é permitido para clientes particulares",
    };
  }

  return { valid: true, error: null };
}
