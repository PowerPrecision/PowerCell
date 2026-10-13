/**
 * Payloads de gravação do modal rápido de detalhes (Kanban).
 *
 * O modal montava o payload com `campo || undefined`: apagar um campo era
 * indistinguível de «não mexi nele» e o valor antigo voltava depois do toast de
 * sucesso. Aqui só entram os campos que MUDARAM, e apagar é um vazio EXPLÍCITO
 * (`""` no cliente, `null` nas secções do processo). Ver `utils/camposLimpos.js`.
 */
import { alteracoesDeTexto, estaVazio } from "../../utils/camposLimpos";

/** [campo do modal, secção do processo, campo na secção, numérico?] */
const CAMPOS_DO_PROCESSO = Object.freeze([
  ["property_type", "real_estate_data", "tipo_imovel", false],
  ["property_location", "real_estate_data", "localizacao", false],
  ["property_value", "real_estate_data", "valor_imovel", true],
  ["loan_amount", "real_estate_data", "valor_financiado", true],
  ["spread", "credit_data", "spread", false],
  ["taxa_esforco", "credit_data", "taxa_esforco", false],
  ["banco_avaliacao", "credit_data", "valuation_bank", false],
  ["valor_avaliacao", "credit_data", "valuation_value", true],
]);

/**
 * `PUT /clients/{id}` do modal: só o que mudou.
 *
 * @returns {{payload: object, nomeEmFalta: boolean}} `nomeEmFalta` — o nome
 *   (obrigatório) foi apagado: quem chama recusa a gravação e di-lo.
 */
export function payloadDoClienteDoModal(original, atual) {
  const payload = {};
  let nomeEmFalta = false;
  if ((original?.nome ?? "") !== (atual?.nome ?? "")) {
    if (estaVazio(atual?.nome)) nomeEmFalta = true;
    else payload.nome = atual.nome.trim();
  }
  const contacto = alteracoesDeTexto(original, atual, ["email", "telefone"]);
  if (Object.keys(contacto.definidos).length > 0) payload.contacto = contacto.definidos;
  const pessoais = alteracoesDeTexto(original, atual, ["nif", "estado_civil"]);
  if (Object.keys(pessoais.definidos).length > 0) payload.dados_pessoais = pessoais.definidos;
  return { payload, nomeEmFalta };
}

/**
 * Secções de negócio do `PUT /processes/{id}` do modal: só o que mudou; um campo
 * apagado vai como `null` (o servidor retira-o da secção). Um número ilegível
 * não se envia (não é um pedido para apagar).
 */
export function seccoesDoProcessoDoModal(original, atual) {
  const seccoes = {};
  for (const [chave, seccao, destino, numerico] of CAMPOS_DO_PROCESSO) {
    const antes = original?.[chave];
    const agora = atual?.[chave];
    if (String(antes ?? "") === String(agora ?? "")) continue;
    let valor = null;
    if (!estaVazio(agora)) {
      valor = numerico ? Number(agora) : agora;
      if (numerico && Number.isNaN(valor)) continue;
    }
    seccoes[seccao] = { ...(seccoes[seccao] || {}), [destino]: valor };
  }
  return seccoes;
}
