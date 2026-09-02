/**
 * emailAccountsApi — Helper partilhado de fetch para os cartões de
 * configuração de email da página EmailAccountsPage.
 */
export const API_URL = process.env.REACT_APP_BACKEND_URL;

export async function fetchSystemConfig(token) {
  const res = await fetch(`${API_URL}/api/system-config`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Erro ao carregar configuração do sistema");
  const response = await res.json();
  return response.config || response;
}
