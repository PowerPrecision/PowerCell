/**
 * Âmbitos do Painel de Administração (Lote 4, ponto 6).
 *
 * O painel misturava, numa só fila de separadores, o que actua sobre A EMPRESA
 * EM CONTEXTO (utilizadores, workflow, formulários, RGPD…) com o que actua
 * sobre o SISTEMA INTEIRO (backups, logs, IA, contas de email do sistema). Quem
 * editava «Configurações» não sabia se estava a mexer na sua empresa ou em
 * todas — e essa dúvida é o incidente de 2026-09-21 com outra roupa.
 *
 * REGISTO POSITIVO (regra do `SECCOES_DEDICADAS` do SystemConfigPage): cada
 * separador de topo declara AQUI o seu âmbito. Um separador novo que não esteja
 * no registo não aparece em nenhum dos dois âmbitos — e o teste da página
 * exige que todos os separadores desenhados estejam registados. A alternativa
 * (uma lista de exclusão) fazia um separador esquecido cair em silêncio no
 * âmbito errado.
 *
 * O âmbito é APRESENTAÇÃO: quem pode ver/usar cada coisa continua a decidi-lo o
 * servidor (`require_roles`) e as condições `isMaster` do painel.
 */
import { getDistinctCompanies } from "./userProfiles";

export const AMBITO_EMPRESA = "empresa";
export const AMBITO_SISTEMA = "sistema";

/** Rótulos dos dois âmbitos — o que o utilizador lê. */
export const ROTULOS_DOS_AMBITOS = {
  [AMBITO_EMPRESA]: "Configurações da Empresa (Tenant Ativo)",
  [AMBITO_SISTEMA]: "Configurações Globais (Sistema)",
};

/**
 * Separador → âmbito. A ordem é a ordem em que aparecem.
 *
 * Empresa: o que o Admin/CEO da casa também usa e que actua na rede em contexto.
 * Sistema: infraestrutura partilhada por todas as redes (só o Master).
 */
export const SECCOES_DO_PAINEL = {
  "users-mgmt": AMBITO_EMPRESA,
  permissions: AMBITO_EMPRESA,
  config: AMBITO_EMPRESA,
  automation: AMBITO_EMPRESA,
  empresas: AMBITO_EMPRESA,
  financas: AMBITO_EMPRESA,
  customizacao: AMBITO_EMPRESA,
  compliance: AMBITO_EMPRESA,
  comunicacoes: AMBITO_SISTEMA,
  tecnico: AMBITO_SISTEMA,
};

export function ambitoDaSeccao(valor) {
  return SECCOES_DO_PAINEL[valor] || null;
}

/** Separadores de um âmbito, pela ordem do registo. */
export function seccoesDoAmbito(ambito) {
  return Object.keys(SECCOES_DO_PAINEL).filter((v) => SECCOES_DO_PAINEL[v] === ambito);
}

/**
 * O âmbito global é do Master; quem é local nunca o vê (nem o seletor de
 * âmbito: um seletor com uma só opção é ruído).
 */
export function ambitosVisiveis({ isMaster }) {
  return isMaster ? [AMBITO_EMPRESA, AMBITO_SISTEMA] : [AMBITO_EMPRESA];
}

/** Âmbito a mostrar: o pedido se for visível, senão o da empresa. */
export function ambitoEmVigor(pedido, { isMaster }) {
  return ambitosVisiveis({ isMaster }).includes(pedido) ? pedido : AMBITO_EMPRESA;
}

/** O separador por onde se entra ao mudar de âmbito. */
export function primeiraSeccaoDoAmbito(ambito) {
  return seccoesDoAmbito(ambito)[0] || null;
}

/**
 * Aviso que acompanha cada âmbito. O da empresa diz qual é («Domus»), porque é
 * essa a informação que falta a quem trabalha em várias.
 */
export function avisoDoAmbito(ambito, nomeDaEmpresa) {
  if (ambito === AMBITO_SISTEMA) {
    return "Estas definições aplicam-se a TODAS as empresas e redes do sistema.";
  }
  return nomeDaEmpresa
    ? `Estas definições aplicam-se à empresa em contexto: ${nomeDaEmpresa}.`
    : "Estas definições aplicam-se à empresa em contexto (escolhida no topo).";
}

/**
 * Nome da empresa em contexto, a partir dos acessos do utilizador. Devolve
 * `null` quando não se consegue dizer (o aviso então não inventa um nome — um
 * nome errado seria pior do que nenhum).
 */
export function nomeDaEmpresaActiva(user, activeCompanyId) {
  if (!user || !activeCompanyId || activeCompanyId === "default") return null;
  try {
    const empresa = getDistinctCompanies(user).find((c) => c.company_id === activeCompanyId);
    // `getDistinctCompanies` põe o id no lugar de um nome em falta: isso não é um nome.
    return empresa && empresa.company_name !== empresa.company_id ? empresa.company_name : null;
  } catch {
    return null;
  }
}
