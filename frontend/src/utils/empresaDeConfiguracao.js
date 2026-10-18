/**
 * Que empresa mostra o ecrã das Configurações do Sistema.
 *
 * PORQUE É QUE ISTO EXISTE (Bloco 1, ponto 3)
 * ===========================================
 * A página reagia SÓ à empresa activa do `ContextSwitcher`, que lista as
 * empresas dos UCR do utilizador. Para o CEO é o certo (só configura as
 * dele). Para o ADMIN é um beco: tem UCR numa empresa e tem de poder
 * configurar TODAS as do CRM — o servidor já lho permite, faltava o ecrã
 * oferecê-lo.
 *
 * A lista vem de `GET /system-config/companies`, que o servidor já filtra
 * pelo âmbito de quem pergunta (admin: todas; CEO: as dele + a global se a
 * rede dele a possui). **O frontend não decide o que se pode configurar**:
 * só escolhe, de entre o que o servidor devolveu.
 *
 * REGRAS
 * ------
 * 1. Só se oferece um selector quando há MAIS DO QUE UMA empresa — com uma
 *    só, o selector seria um ecrã que muda de forma sem razão.
 * 2. A escolha explícita vence a empresa activa, mas só se ainda estiver
 *    na lista (a lista muda com a sessão).
 * 3. A empresa activa vence a omissão, mas só se o servidor a oferecer: um
 *    CEO de uma ilha não tem a global, e pedi-la daria 403 ao abrir o ecrã.
 * 4. Sem lista (pedido falhado, sessão antiga) o comportamento é o de
 *    sempre: a empresa activa, ou a global. O servidor é a parede.
 */

export const EMPRESA_GLOBAL = "default";

/** Normaliza a resposta de `GET /system-config/companies`. */
export function normalizarEmpresas(data) {
  const lista = Array.isArray(data?.companies) ? data.companies : [];
  const vistas = new Set();
  const resultado = [];
  for (const empresa of lista) {
    const id = empresa?.company_id;
    if (typeof id !== "string" || !id || vistas.has(id)) continue;
    vistas.add(id);
    resultado.push({
      company_id: id,
      company_name:
        typeof empresa.company_name === "string" && empresa.company_name
          ? empresa.company_name
          : id,
    });
  }
  return resultado;
}

export function deveMostrarSeletorDeEmpresa(empresas) {
  return Array.isArray(empresas) && empresas.length > 1;
}

/**
 * A empresa cuja configuração se mostra AGORA.
 *
 * @param {{escolhida: string|null, activa: string|null, empresas: Array}} p
 */
export function empresaEmVigor({ escolhida, activa, empresas }) {
  const ids = (Array.isArray(empresas) ? empresas : []).map((e) => e.company_id);
  if (ids.length === 0) return activa || EMPRESA_GLOBAL;
  if (escolhida && ids.includes(escolhida)) return escolhida;
  const pedida = activa || EMPRESA_GLOBAL;
  return ids.includes(pedida) ? pedida : ids[0];
}

/**
 * O âmbito que o ecrã DIZ ao utilizador (QA-6): as definições da empresa em vigor ou as globais.
 *
 * As categorias genéricas lêem e escrevem a configuração DA EMPRESA escolhida (`company:<id>`;
 * a «global» é a empresa especial `default`). As secções com ecrã próprio (manutenção, portal,
 * documentos obrigatórios, SLAs, atualizações…) são infraestrutura partilhada por todas as
 * empresas e só o Master lhes toca. Misturadas na mesma lista, o administrador não sabia se
 * estava a mexer na sua empresa ou no sistema inteiro.
 */
export function rotuloDaEmpresaEmVigor(companyId, empresas) {
  if (!companyId || companyId === EMPRESA_GLOBAL) return "Sistema (configuração global)";
  const encontrada = (Array.isArray(empresas) ? empresas : []).find((e) => e.company_id === companyId);
  return encontrada?.company_name || companyId;
}
