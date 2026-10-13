/**
 * Quem vê os botões de IA sobre os documentos de um processo («Analisar», «Renomear IA»,
 * «Extrair dados»).
 *
 * O gate era só o cargo (`MANAGEMENT_ROLES.includes(effectiveRole)`), por isso a equipa
 * que trata de um processo PARTILHADO na rede de destino — consultor e intermediário
 * atribuídos — nunca via o botão, embora o servidor lhe devesse permitir a ferramenta:
 * a regra é «gestão OU atribuído ao processo, dentro da fronteira de rede».
 *
 * A resposta «estou atribuído?» NÃO se calcula aqui: a lista de campos de atribuição tem
 * 15 nomes e vive no servidor (`collect_assigned_ids`); uma cópia no ecrã divergiria sem
 * dar erro e esconderia o botão a quem tem direito. O detalhe do processo devolve
 * `pode_usar_ia_documentos`, calculado pela MESMA função que as rotas usam para recusar.
 *
 * O cargo continua a contar (OU, nunca E): se o servidor não respondeu — sessão anterior ao
 * deploy, ecrã que não carrega o processo — a gestão não perde o botão que sempre teve.
 * A parede é o servidor, que recusa na mesma.
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
  // Só o `true` estrito conta: um campo em falta ou "true" em texto não abre nada.
  if (permissaoDoServidor === true) return true;
  return MANAGEMENT_ROLES.includes(effectiveRole);
}
