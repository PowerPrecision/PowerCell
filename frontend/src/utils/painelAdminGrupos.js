/**
 * Painel de Administração — grupos, secções e quem vê cada uma.
 *
 * REVISÃO DO PAINEL (Flavio, Nov 2026)
 * ====================================
 * Havia três ecrãs chamados «Painel de Administração» (`/admin`, `/admin/organizacao`
 * e `/system-admin`), com Empresas e Utilizadores repetidos, e definições que pareciam
 * da empresa mas eram globais. As respostas do Flavio:
 *
 * * 1a — uma só entrada «Administração», em cinco grupos: Equipa, A empresa, Operação,
 *   Conformidade e Sistema;
 * * 3a — o Diretor vê a sua empresa só para consulta (Utilizadores, Workflow, Finanças);
 * * 4b — o CEO gere tudo da empresa; o Admin só a Equipa e a Operação (sem Finanças nem
 *   Dados da empresa). A Conformidade (RGPD, auditoria) fica com o Admin, como estava;
 * * 5a/8a/9a — armazenamento, IA, auditoria e backups automáticos vão para Sistema (só Master);
 * * 10a — o email geral configura-se na ficha da empresa (Dados da empresa);
 * * 11a — os balcões e o template de documentação ficam em «A empresa → Definições».
 *
 * O REGISTO É A AUTORIDADE DO ECRÃ. Quem pode gravar continua a decidi-lo o servidor
 * (`require_roles`, `system_config_scope.exigir_pode_gravar_seccao`). Uma secção que
 * aqui não esteja não se desenha. Decide-se pelo PERFIL EFECTIVO (o escolhido no
 * seletor), nunca pelo `user.role` — a não ser o Master, que é a CONTA (o servidor
 * deixa passar a conta Master com qualquer perfil activo).
 */

const GESTAO_LOCAL = ["master", "admin", "ceo"];
const DA_EMPRESA = ["master", "ceo"];

/** `edita`: perfis que gravam. `consulta`: perfis que só vêem. `soContaMaster`: só a conta Master. */
export const GRUPOS_DO_PAINEL = [
  {
    id: "equipa",
    rotulo: "Equipa",
    descricao: "Utilizadores, parceiros e permissões da empresa escolhida.",
    seccoes: [
      { id: "utilizadores", rotulo: "Utilizadores", edita: GESTAO_LOCAL, consulta: ["diretor"] },
      { id: "parceiros", rotulo: "Parceiros", edita: GESTAO_LOCAL },
      { id: "permissoes", rotulo: "Permissões", edita: GESTAO_LOCAL },
    ],
  },
  {
    id: "empresa",
    rotulo: "A empresa",
    descricao: "Dados, email geral, definições e honorários da empresa escolhida.",
    seccoes: [
      { id: "dados", rotulo: "Dados da empresa", edita: DA_EMPRESA },
      { id: "definicoes", rotulo: "Definições", edita: DA_EMPRESA },
      { id: "financas", rotulo: "Honorários e comissões", edita: DA_EMPRESA, consulta: ["diretor"] },
    ],
  },
  {
    id: "operacao",
    rotulo: "Operação",
    descricao: "Partilhado por todas as empresas da rede: quem altera fica registado e as outras empresas são avisadas.",
    seccoes: [
      { id: "workflow", rotulo: "Workflow", edita: GESTAO_LOCAL, consulta: ["diretor"] },
      { id: "formulario", rotulo: "Formulário público", edita: GESTAO_LOCAL },
      { id: "automacoes", rotulo: "Automações", edita: GESTAO_LOCAL },
    ],
  },
  {
    id: "conformidade",
    rotulo: "Conformidade",
    descricao: "RGPD e registo de auditoria.",
    seccoes: [
      { id: "rgpd", rotulo: "RGPD", edita: GESTAO_LOCAL },
      { id: "auditoria", rotulo: "Registo de auditoria", edita: GESTAO_LOCAL },
      { id: "anonimizacao", rotulo: "Anonimização", edita: GESTAO_LOCAL },
      { id: "historico", rotulo: "Registo de histórico", soContaMaster: true },
    ],
  },
  {
    id: "sistema",
    rotulo: "Sistema",
    descricao: "Vale para TODAS as empresas. Só o Master.",
    seccoes: [
      { id: "configuracao", rotulo: "Configuração global", soContaMaster: true },
      { id: "contas-email", rotulo: "Contas de email do sistema", soContaMaster: true },
      { id: "notificacoes", rotulo: "Notificações", soContaMaster: true },
      { id: "backups", rotulo: "Backups", soContaMaster: true },
      { id: "logs", rotulo: "Logs", soContaMaster: true },
      { id: "diagnosticos", rotulo: "Diagnósticos", soContaMaster: true },
      { id: "ia", rotulo: "Inteligência Artificial", soContaMaster: true },
      { id: "processos-bg", rotulo: "Processos em background", soContaMaster: true },
    ],
  },
];

const _papel = (p) => String(p || "").toLowerCase();

/**
 * O acesso de quem pergunta a uma secção: `"edita"`, `"consulta"` ou `null`.
 * `contaMaster` — a CONTA é Master (vê e grava tudo, qualquer que seja o perfil activo).
 */
export function acessoASeccao(seccao, { perfil, contaMaster = false }) {
  if (!seccao) return null;
  if (contaMaster) return "edita";
  if (seccao.soContaMaster) return null;
  const p = _papel(perfil);
  if ((seccao.edita || []).includes(p)) return "edita";
  if ((seccao.consulta || []).includes(p)) return "consulta";
  return null;
}

/** Os grupos (e dentro deles as secções) que este perfil vê, pela ordem do registo. */
export function gruposVisiveis(contexto) {
  return GRUPOS_DO_PAINEL.map((g) => ({
    ...g,
    seccoes: g.seccoes
      .map((s) => ({ ...s, acesso: acessoASeccao(s, contexto) }))
      .filter((s) => s.acesso),
  })).filter((g) => g.seccoes.length > 0);
}

/** Quem vê ALGUMA coisa do painel (decide o item do menu e a rota). */
export function podeAbrirOPainel(contexto) {
  return gruposVisiveis(contexto).length > 0;
}

/**
 * O grupo e a secção em vigor, a partir do URL (`?grupo=&seccao=`). Um valor que
 * este perfil não vê (um link antigo, um link partilhado por outro perfil) cai na
 * primeira secção visível do grupo, ou no primeiro grupo — nunca num ecrã vazio.
 */
export function seccaoEmVigor(grupos, grupoPedido, seccaoPedida) {
  if (!grupos.length) return { grupo: null, seccao: null };
  const grupo = grupos.find((g) => g.id === grupoPedido) || grupos[0];
  const seccao = grupo.seccoes.find((s) => s.id === seccaoPedida) || grupo.seccoes[0];
  return { grupo, seccao };
}

/**
 * Links antigos → sítio novo. `/admin/organizacao?tab=…` e os separadores do
 * `/system-admin` antigo continuam a abrir onde a coisa agora vive.
 */
export const DESTINOS_ANTIGOS = {
  empresas: { grupo: "empresa", seccao: "dados" },
  utilizadores: { grupo: "equipa", seccao: "utilizadores" },
  acessos: { grupo: "equipa", seccao: "utilizadores" },
  parceiros: { grupo: "equipa", seccao: "parceiros" },
  permissions: { grupo: "equipa", seccao: "permissoes" },
  config: { grupo: "empresa", seccao: "definicoes" },
  financas: { grupo: "empresa", seccao: "financas" },
  automation: { grupo: "operacao", seccao: "automacoes" },
  workflow: { grupo: "operacao", seccao: "workflow" },
  compliance: { grupo: "conformidade", seccao: "rgpd" },
  comunicacoes: { grupo: "sistema", seccao: "contas-email" },
  tecnico: { grupo: "sistema", seccao: "backups" },
};

/** O URL do painel para um grupo/secção. */
export function urlDoPainel(grupo, seccao) {
  const p = new URLSearchParams();
  if (grupo) p.set("grupo", grupo);
  if (seccao) p.set("seccao", seccao);
  const q = p.toString();
  return q ? `/system-admin?${q}` : "/system-admin";
}
