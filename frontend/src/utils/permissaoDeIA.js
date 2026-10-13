/**
 * Quem vê os botões de IA MANUAL sobre os documentos de um processo («Analisar», «Renomear IA»,
 * «Extrair dados»).
 *
 * REGRA (decisão da direcção, Out 2026 — controlo de custos da API): SÓ os altos perfis
 * (Master, Admin, CEO, Diretor), pelo perfil activo. Estar atribuído ao processo NÃO dá o
 * botão (uma iteração anterior abriu-o a «gestão OU atribuído»; foi revogada). O fluxo normal
 * não depende do clique: a IA corre sozinha quando um documento cai na `Index`.
 *
 * O cargo é a condição; a resposta do servidor (`pode_usar_ia_documentos`, calculada pela MESMA
 * função que as rotas usam para recusar) só pode ESTREITAR — um `false` explícito quer dizer
 * «o processo está fora do teu âmbito de rede», e mostrar um botão que dá 403 é o que o QA
 * reportou. Sem resposta (`undefined`: sessão anterior ao deploy, ecrã que não carrega o
 * processo) vale o cargo: a parede é o servidor, que recusa na mesma.
 */
import { MANAGEMENT_ROLES } from "./roleUtils";

/**
 * @param {Object} p
 * @param {string} [p.effectiveRole] perfil activo do utilizador.
 * @param {boolean|undefined} [p.permissaoDoServidor] `process.pode_usar_ia_documentos`.
 * @param {boolean} [p.somenteLeitura] processo fechado: ver sim, alterar não.
 * @returns {boolean}
 */
export function podeUsarFerramentasDeIA({
  effectiveRole,
  permissaoDoServidor,
  somenteLeitura = false,
} = {}) {
  if (somenteLeitura) return false;
  if (!MANAGEMENT_ROLES.includes(effectiveRole)) return false;
  // Só o `false` ESTRITO estreita: um campo em falta nunca tira o botão à gestão.
  return permissaoDoServidor !== false;
}
