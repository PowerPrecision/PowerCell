/**
 * Utilitário para formatação de erros de validação
 * Converte erros do Pydantic/FastAPI em mensagens amigáveis em português
 */

// Mapeamento de campos para nomes amigáveis
export const FIELD_LABELS = {
  // Dados pessoais
  "client_email": "Email do Cliente",
  "client_phone": "Telefone do Cliente",
  "email": "Email",
  "phone": "Telefone",
  "nif": "NIF",
  "nome": "Nome",
  "name": "Nome",
  "data_nascimento": "Data de Nascimento",
  "nacionalidade": "Nacionalidade",
  "morada": "Morada",
  "address": "Morada",
  "codigo_postal": "Código Postal",
  "localidade": "Localidade",
  "profissao": "Profissão",
  "entidade_patronal": "Entidade Patronal",
  "tipo_contrato": "Tipo de Contrato",
  "antiguidade_empresa": "Antiguidade na Empresa",
  
  // Dados financeiros
  "valor_pretendido": "Valor Pretendido",
  "valor_entrada": "Valor de Entrada",
  "capital_proprio": "Capital Próprio",
  "valor_financiado": "Valor Financiado",
  "renda_habitacao_atual": "Renda Habitação Atual",
  "monthly_income": "Rendimento Mensal",
  "other_income": "Outros Rendimentos",
  "monthly_expenses": "Despesas Mensais",
  
  // Dados do imóvel
  "preco": "Preço",
  "price": "Preço",
  "localizacao": "Localização",
  "location": "Localização",
  "tipologia": "Tipologia",
  "area": "Área",
  "quartos": "Quartos",
  "casas_banho": "Casas de Banho",
  
  // Secções
  "personal_data": "Dados Pessoais",
  "financial_data": "Dados Financeiros",
  "real_estate_data": "Dados do Imóvel",
  "credit_data": "Dados de Crédito",
  "titular2_data": "Dados do 2º Titular",
  
  // Leads
  "url": "URL",
  "title": "Título",
  "description": "Descrição",
  "consultant": "Consultor",
  
  // Geral
  "password": "Palavra-passe",
  "status": "Estado",
  "role": "Perfil",
};

// Traduções de mensagens Pydantic comuns
const MESSAGE_TRANSLATIONS = {
  "Input should be a valid string": "deve ser texto",
  "Input should be a valid number": "deve ser um número",
  "unable to parse string as a number": "formato de número inválido",
  "Input should be a valid email": "email inválido",
  "value is not a valid email address": "email inválido",
  "Field required": "campo obrigatório",
  "field required": "campo obrigatório",
  "String should have at least": "texto muito curto",
  "String should have at most": "texto muito longo",
  "Input should be a valid integer": "deve ser um número inteiro",
  "Input should be a valid boolean": "deve ser verdadeiro ou falso",
  "Input should be a valid date": "data inválida",
  "Input should be a valid datetime": "data/hora inválida",
  "Value error": "valor inválido",
  "none is not an allowed value": "campo obrigatório",
  "ensure this value has at least": "valor muito curto",
  "ensure this value has at most": "valor muito longo",
};

/**
 * Traduz uma mensagem de erro Pydantic para português
 */
function translateErrorMessage(msg) {
  if (!msg) return "valor inválido";
  
  for (const [english, portuguese] of Object.entries(MESSAGE_TRANSLATIONS)) {
    if (msg.toLowerCase().includes(english.toLowerCase())) {
      return portuguese;
    }
  }
  
  return msg;
}

/**
 * Obtém o nome amigável de um campo
 */
function getFieldLabel(fieldPath) {
  if (!fieldPath || !fieldPath.length) return "campo";
  
  // O último elemento é geralmente o nome do campo
  const fieldName = fieldPath[fieldPath.length - 1];
  
  // Se é um índice numérico, usar o elemento anterior
  if (typeof fieldName === 'number' && fieldPath.length > 1) {
    return FIELD_LABELS[fieldPath[fieldPath.length - 2]] || fieldPath[fieldPath.length - 2];
  }
  
  return FIELD_LABELS[fieldName] || fieldName;
}

/**
 * Formata um erro de validação individual
 */
function formatSingleError(err) {
  const fieldPath = err.loc || [];
  const friendlyName = getFieldLabel(fieldPath);
  const message = translateErrorMessage(err.msg);
  
  return {
    field: fieldPath[fieldPath.length - 1] || "unknown",
    fieldLabel: friendlyName,
    message: message,
    fullMessage: `${friendlyName}: ${message}`,
    original: err
  };
}

/**
 * Processa erros de resposta do backend e retorna mensagens formatadas
 * 
 * @param {Error} error - Erro do Axios ou similar
 * @returns {Object} { message: string, errors: Array, hasMultiple: boolean }
 */
export function parseBackendError(error) {
  // Mensagem padrão
  let result = {
    message: "Ocorreu um erro inesperado",
    errors: [],
    hasMultiple: false,
    fields: [] // Lista de campos com erro
  };
  
  // Verificar se há resposta do servidor
  if (!error.response?.data) {
    if (error.message) {
      result.message = error.message;
    }
    return result;
  }
  
  const detail = error.response.data.detail;
  
  // String simples
  if (typeof detail === 'string') {
    result.message = detail;
    return result;
  }
  
  // Array de erros (formato Pydantic)
  if (Array.isArray(detail)) {
    const formattedErrors = detail.map(formatSingleError);
    
    result.errors = formattedErrors;
    result.hasMultiple = formattedErrors.length > 1;
    result.fields = formattedErrors.map(e => e.field);
    result.message = formattedErrors.map(e => e.fullMessage).join('\n');
    
    return result;
  }
  
  // Objecto com msg/message
  if (typeof detail === 'object') {
    result.message = detail.msg || detail.message || JSON.stringify(detail);
    return result;
  }
  
  return result;
}

/**
 * Retorna uma mensagem de erro formatada para exibição ao utilizador
 * 
 * @param {Error} error - Erro do Axios ou similar
 * @param {string} defaultMessage - Mensagem padrão se não conseguir extrair
 * @returns {string} Mensagem formatada
 */
export function getErrorMessage(error, defaultMessage = "Ocorreu um erro") {
  const parsed = parseBackendError(error);
  return parsed.message || defaultMessage;
}

/**
 * Verifica se um campo específico tem erro
 */
export function hasFieldError(error, fieldName) {
  const parsed = parseBackendError(error);
  return parsed.fields.includes(fieldName);
}

/**
 * Cria um componente React com lista de erros
 * Para usar com toast.error()
 */
export function createErrorToastContent(error, title = "Erro ao guardar") {
  const parsed = parseBackendError(error);
  
  if (!parsed.hasMultiple) {
    return parsed.message;
  }
  
  // Retorna JSX para múltiplos erros
  return (
    <div>
      <strong>{title}:</strong>
      <ul style={{margin: '8px 0 0 0', paddingLeft: '16px', listStyle: 'disc'}}>
        {parsed.errors.map((e, i) => (
          <li key={i}>{e.fullMessage}</li>
        ))}
      </ul>
    </div>
  );
}

export default {
  parseBackendError,
  getErrorMessage,
  hasFieldError,
  createErrorToastContent,
  FIELD_LABELS
};
