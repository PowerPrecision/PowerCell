/**
 * Tradutor do histórico: da chave técnica da base de dados para português (Lote 7.3).
 *
 * A Timeline mostrava `assigned_mediador_ids`, `portal_access` e listas de ids tal como o servidor as
 * grava. Aqui vive o dicionário (ponto único) e as regras de apresentação:
 *
 *   - uma chave conhecida tem rótulo e frase de «atualizado» próprios;
 *   - uma chave DESCONHECIDA nunca aparece crua — é legível por regra (`personal_data.nif` → «Dados pessoais · NIF»);
 *   - o valor de um campo de IDs (`*_id`, `*_ids`) não se mostra: um uuid não diz nada a ninguém;
 *   - listas de texto juntam-se, listas de objectos contam-se, booleanos são Sim/Não.
 *
 * Puro e sem dependências: o servidor continua a gravar a chave técnica (é o contrato do histórico).
 */

/** chave → { rotulo, atualizado } (a frase de «mudou» concorda em género e número). */
export const CAMPOS_DO_HISTORICO = {
  assigned_consultor_id: { rotulo: "Consultor", atualizado: "Consultor atualizado" },
  assigned_consultor_ids: { rotulo: "Consultores", atualizado: "Consultores atualizados" },
  consultor_names: { rotulo: "Consultores", atualizado: "Consultores atualizados" },
  consultor_name: { rotulo: "Consultor", atualizado: "Consultor atualizado" },
  assigned_mediador_id: { rotulo: "Intermediário", atualizado: "Intermediário atualizado" },
  assigned_mediador_ids: { rotulo: "Intermediários", atualizado: "Intermediários atualizados" },
  mediador_names: { rotulo: "Intermediários", atualizado: "Intermediários atualizados" },
  mediador_name: { rotulo: "Intermediário", atualizado: "Intermediário atualizado" },
  assigned_indexacao_id: { rotulo: "Indexação", atualizado: "Responsável da Indexação atualizado" },
  indexacao_name: { rotulo: "Indexação", atualizado: "Responsável da Indexação atualizado" },
  assigned_parceiro_id: { rotulo: "Parceiro", atualizado: "Parceiro atualizado" },
  parceiro_name: { rotulo: "Parceiro", atualizado: "Parceiro atualizado" },
  assignment: { rotulo: "Atribuição", atualizado: "Atribuição atualizada" },
  client_id: { rotulo: "Cliente", atualizado: "Cliente atualizado" },
  client_name: { rotulo: "Nome do cliente", atualizado: "Nome do cliente atualizado" },
  company_name: { rotulo: "Empresa", atualizado: "Empresa atualizada" },
  name: { rotulo: "Nome", atualizado: "Nome atualizado" },
  deadline: { rotulo: "Prazo", atualizado: "Prazo atualizado" },
  document_checklist: { rotulo: "Lista de documentos", atualizado: "Lista de documentos atualizada" },
  documento: { rotulo: "Documento", atualizado: "Documento atualizado" },
  documentos: { rotulo: "Documentos", atualizado: "Documentos atualizados" },
  documents: { rotulo: "Documentos", atualizado: "Documentos atualizados" },
  email: { rotulo: "Email", atualizado: "Email atualizado" },
  filename: { rotulo: "Ficheiro", atualizado: "Ficheiro atualizado" },
  finance_status: { rotulo: "Estado financeiro", atualizado: "Estado financeiro atualizado" },
  is_data_confirmed: { rotulo: "Dados confirmados", atualizado: "Confirmação dos dados atualizada" },
  is_indexed: { rotulo: "Indexação validada", atualizado: "Validação da indexação atualizada" },
  monitored_emails: { rotulo: "Emails monitorizados", atualizado: "Emails monitorizados atualizados" },
  observation_notes: { rotulo: "Observações", atualizado: "Observações atualizadas" },
  onedrive_links: { rotulo: "Ligações OneDrive", atualizado: "Ligações OneDrive atualizadas" },
  origem_financeira: { rotulo: "Origem financeira", atualizado: "Origem financeira atualizada" },
  perfil: { rotulo: "Perfil", atualizado: "Perfil atualizado" },
  portal_access: { rotulo: "Acesso ao Portal", atualizado: "Acesso ao Portal atualizado" },
  portal_impersonate: { rotulo: "Visualização como cliente", atualizado: "Visualização como cliente registada" },
  portal_message: { rotulo: "Mensagem do Portal", atualizado: "Mensagem do Portal registada" },
  process_type: { rotulo: "Tipo de processo", atualizado: "Tipo de processo atualizado" },
  rascunho: { rotulo: "Rascunho", atualizado: "Rascunho atualizado" },
  recommended_properties: { rotulo: "Imóveis recomendados", atualizado: "Imóveis recomendados atualizados" },
  registration_delete: { rotulo: "Registo do cliente", atualizado: "Registo do cliente eliminado" },
  registration_edit: { rotulo: "Registo do cliente", atualizado: "Registo do cliente editado" },
  s3_folder: { rotulo: "Pasta de documentos", atualizado: "Pasta de documentos atualizada" },
  servico_do_parceiro: { rotulo: "Serviço do parceiro", atualizado: "Serviço do parceiro atualizado" },
  servico_do_parceiro_observacoes: { rotulo: "Observações do serviço do parceiro", atualizado: "Observações do serviço do parceiro atualizadas" },
  servico_pago_pelo_parceiro: { rotulo: "Serviço pago pelo parceiro", atualizado: "Pagamento do serviço do parceiro atualizado" },
  status: { rotulo: "Fase", atualizado: "Fase atualizada" },
  cloud_folder_url: { rotulo: "Pasta na cloud", atualizado: "Pasta na cloud atualizada" },
  storage_folder_url: { rotulo: "Pasta de armazenamento", atualizado: "Pasta de armazenamento atualizada" },
  tarefa: { rotulo: "Tarefa", atualizado: "Tarefa atualizada" },
  temp_link: { rotulo: "Ligação temporária", atualizado: "Ligação temporária atualizada" },
  visit: { rotulo: "Visita", atualizado: "Visita atualizada" },
  visita: { rotulo: "Visita", atualizado: "Visita atualizada" },
  partner_companies: { rotulo: "Partilha com empresas", atualizado: "Partilha com empresas atualizada" },
  partner_network_ids: { rotulo: "Partilha com empresas", atualizado: "Partilha com empresas atualizada" },
  hub_triage: { rotulo: "Triagem", atualizado: "Triagem atualizada" },
};

/** Segmentos de um caminho (`personal_data.nif`) e palavras soltas que têm tradução própria. */
const SEGMENTOS = {
  personal_data: "Dados pessoais",
  financial_data: "Dados financeiros",
  real_estate_data: "Imóvel",
  credit_data: "Crédito",
  titular2_data: "2.º titular",
  contacto: "Contacto",
  dados_pessoais: "Dados pessoais",
  dados_financeiros: "Dados financeiros",
  nif: "NIF",
  nome: "Nome",
  phone: "Telefone",
  telefone: "Telefone",
  telemovel: "Telemóvel",
  morada: "Morada",
  address: "Morada",
  email: "Email",
  iban: "IBAN",
  niss: "NISS",
  data_nascimento: "Data de nascimento",
  birth_date: "Data de nascimento",
  estado_civil: "Estado civil",
  nacionalidade: "Nacionalidade",
  naturalidade: "Naturalidade",
  profissao: "Profissão",
  codigo_postal: "Código postal",
  documento_id: "Documento de identificação",
  valor: "Valor",
  prazo: "Prazo",
  taxa: "Taxa",
  banco: "Banco",
  status: "Estado",
};

function capitalizar(texto) {
  return texto ? texto.charAt(0).toUpperCase() + texto.slice(1) : texto;
}

function palavra(segmento) {
  const s = String(segmento || "").trim();
  if (!s) return "";
  if (SEGMENTOS[s]) return SEGMENTOS[s];
  return capitalizar(s.replace(/_/g, " ").toLowerCase());
}

const ID_LIKE = /(^|_)ids?$/;

/** `true` para `assigned_mediador_ids`, `client_id`…: o valor é um identificador técnico. */
export function eCampoDeIds(campo) {
  const chave = String(campo || "").split(".").pop();
  return ID_LIKE.test(chave);
}

/** Rótulo legível de uma chave — conhecida, em caminho (`a.b`) ou desconhecida. Nunca devolve a chave crua. */
export function rotuloDoCampo(campo) {
  const chave = String(campo ?? "").trim();
  if (!chave) return "Valor";
  if (CAMPOS_DO_HISTORICO[chave]) return CAMPOS_DO_HISTORICO[chave].rotulo;
  const partes = chave.split(".").filter(Boolean);
  if (partes.length > 1) return partes.map(palavra).join(" · ");
  // Um `_ids`/`_id` desconhecido perde o sufixo: «Responsável ids» não é português.
  const semSufixo = chave.replace(/_ids?$/, "");
  return palavra(semSufixo) || "Valor";
}

/** Frase de «mudou» da chave (`Intermediários atualizados`); para uma desconhecida, «<Rótulo> atualizado». */
export function fraseAtualizado(campo) {
  const chave = String(campo ?? "").trim();
  if (CAMPOS_DO_HISTORICO[chave]) return CAMPOS_DO_HISTORICO[chave].atualizado;
  return `${rotuloDoCampo(chave)} atualizado`;
}

/** Valor para ler: sem ids, sem JSON cru. `""` quando não há nada que valha a pena mostrar. */
export function valorLegivel(campo, valor) {
  if (valor === null || valor === undefined || valor === "") return "";
  if (eCampoDeIds(campo)) return "";
  if (typeof valor === "boolean") return valor ? "Sim" : "Não";
  if (Array.isArray(valor)) {
    if (valor.length === 0) return "nenhum";
    if (valor.every((v) => ["string", "number"].includes(typeof v))) return valor.join(", ");
    return `${valor.length} ${valor.length === 1 ? "item" : "itens"}`;
  }
  if (typeof valor === "object") return "";
  return String(valor);
}

const TOKEN_TECNICO = /\b[a-z][a-z0-9]*(?:[._][a-z0-9]+)+\b/g;

/** «Alterou personal_data» → «Alterou Dados pessoais»: troca os tokens técnicos dentro de uma frase. */
export function acaoLegivel(acao) {
  const texto = String(acao ?? "").trim();
  if (!texto) return "Atualização";
  return texto.replace(TOKEN_TECNICO, (token) => rotuloDoCampo(token).toLowerCase() === token ? token : rotuloDoCampo(token));
}

/**
 * Descrição de uma alteração de campo: o texto principal e o detalhe (o que se mostra no distintivo).
 * @returns {{ principal: string, detalhe: string }}
 */
export function descreverAlteracao({ action, field, oldValue, newValue }) {
  const acao = acaoLegivel(action);
  if (!field) return { principal: acao, detalhe: "" };

  const rotulo = rotuloDoCampo(field);
  if (eCampoDeIds(field)) {
    // Sem ids: o que mudou é a pessoa/lista, e a frase di-lo.
    return { principal: acao, detalhe: fraseAtualizado(field) };
  }
  const antes = valorLegivel(field, oldValue);
  const depois = valorLegivel(field, newValue);
  if (antes && depois) return { principal: `${acao}: ${rotulo} alterado de ${antes} para ${depois}`, detalhe: `${antes} → ${depois}` };
  if (depois) return { principal: `${acao}: ${rotulo} → ${depois}`, detalhe: `${rotulo}: ${depois}` };
  if (antes) return { principal: `${acao}: ${rotulo} removido (era ${antes})`, detalhe: `${rotulo} removido` };
  return { principal: acao, detalhe: fraseAtualizado(field) };
}
