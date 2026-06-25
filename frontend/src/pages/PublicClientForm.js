/**
 * PublicClientForm — Formulário público multi-passo para registo de novos clientes.
 *
 * PORQUÊ: O PowerCell capta novos clientes potenciais via formulário público no site.
 * Este formulário recolhe todos os dados necessários para iniciar um processo de
 * crédito habitação em 6 passos organizados: dados pessoais, 2º titular, imóvel,
 * situação profissional/financeira, bancos e consentimentos. A experiência multi-passo
 * reduz a taxa de abandono comparativamente a um formulário longo numa só página.
 *
 * DECISÕES ARQUITECTURAIS:
 * - Auto-save com debounce (2s) para localStorage — o cliente pode fechar e retomar
 *   sem perder dados preenchidos.
 * - Validação progressiva por passo com erros por campo (fieldErrors) e scroll
 *   automático para o primeiro campo com erro.
 * - Validação de NIF português com checksum (algoritmo oficial de 2 dígitos).
 * - Deteção de duplicados no backend (bloqueia registo com mesmo email/NIF),
 * com reporte ao Sentry para análise de friction de conversão.
 * - Suporte a campos personalizados dinâmicos (configuráveis via backend).
 * - Modo preview para testes internos e simulação com dados MOCK_DATA.
 * - Mercado-alvo: 90% dos clientes acedem via telemóvel (mobile-first).
 * - Bancos portugueses pré-definidos com cores institucionais.
 *
 * @param {Object} props
 * @param {boolean} [props.previewMode=false] — Se verdadeiro, desactiva submissão e auto-save
 *
 * @route / — Rota pública (landing page do formulário)
 *
 * @example
 * <PublicClientForm previewMode={false} />
 * // No modo normal, submete para /api/public/client-registration
 */
import { useState, useEffect, useCallback, useRef, useMemo, forwardRef } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import DynamicFormField from "../components/DynamicFormField";
import { Checkbox } from "../components/ui/checkbox";
import { Progress } from "../components/ui/progress";
import { Building2, Loader2, ArrowLeft, ArrowRight, Check, User, Briefcase, Home, Users, CreditCard, HelpCircle, Info, Save, Clock, AlertCircle, Eye, FlaskConical, Play, ClipboardList } from "lucide-react";
import { toast } from "sonner";
import axios from "axios";
import * as Sentry from "@sentry/react";
import { cn, safeDateStr } from "../lib/utils";

const API_URL = process.env.REACT_APP_BACKEND_URL + "/api";

// Chave para localStorage
const DRAFT_STORAGE_KEY = "public_client_form_draft";
const DRAFT_TIMESTAMP_KEY = "public_client_form_draft_timestamp";

// Helper component for field hints
function FieldHint({ children }) {
  return (
  <p className="text-xs text-muted-foreground mt-1 flex items-start gap-1">
    <Info className="h-3 w-3 mt-0.5 flex-shrink-0" />
    <span>{children}</span>
  </p>
  );
}

// Helper component for field errors
function FieldError({ children }) {
  return (
  <p className="text-xs text-red-600 mt-1 flex items-start gap-1 font-medium">
    <AlertCircle className="h-3 w-3 mt-0.5 flex-shrink-0" />
    <span>{children}</span>
  </p>
  );
}

// Helper for required field labels
function RequiredLabel({ htmlFor, children, required: isRequired = true }) {
  return (
  <Label htmlFor={htmlFor}>
    {children}
    {isRequired && (
      <>
        {" "}<span className="text-red-600 font-semibold">*</span>
        <span className="text-red-600 text-[10px] ml-1 font-medium">(obrigatório)</span>
      </>
    )}
  </Label>
  );
}

// Validated Input Component - com forwardRef para suportar refs
const ValidatedInput = forwardRef(function ValidatedInput({ 
  error, 
  required,
  className,
  ...props 
}, ref) {
  return (
  <div className="space-y-1">
    <Input
      ref={ref}
      className={cn(
        className,
        error && "border-red-500 focus-visible:ring-red-500 bg-red-50"
      )}
      {...props}
    />
    {error && <FieldError>{error}</FieldError>}
  </div>
  );
});
ValidatedInput.displayName = 'ValidatedInput';

// Validated Select Wrapper
function ValidatedSelect({ 
  error, 
  children,
  triggerClassName,
  ...props 
}) {
  return (
  <div className="space-y-1">
    <Select {...props}>
      <SelectTrigger className={cn(
        triggerClassName,
        error && "border-red-500 focus:ring-red-500 bg-red-50"
      )}>
        {children}
      </SelectTrigger>
    </Select>
    {error && <FieldError>{error}</FieldError>}
  </div>
  );
}

// Progress Bar Component com percentagem
function FormProgressBar({ currentStep, totalSteps, completedFields, totalFields }) {
  const stepProgress = ((currentStep - 1) / totalSteps) * 100;
  const fieldProgress = totalFields > 0 ? (completedFields / totalFields) * 100 : 0;
  
  return (
    <div className="space-y-2 mb-6">
      <div className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">
          Passo {currentStep} de {totalSteps}
        </span>
        <span className="font-medium text-teal-600">
          {Math.round(fieldProgress)}% completo
        </span>
      </div>
      <Progress value={fieldProgress} className="h-2" />
      <div className="flex justify-between">
        {Array.from({ length: totalSteps }).map((_, idx) => (
          <div 
            key={idx}
            className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-medium transition-colors ${
              idx + 1 < currentStep 
                ? "bg-teal-600 text-white" 
                : idx + 1 === currentStep 
                  ? "bg-teal-100 text-teal-700 border-2 border-teal-600" 
                  : "bg-muted text-muted-foreground"
            }`}
          >
            {idx + 1 < currentStep ? <Check className="h-4 w-4" /> : idx + 1}
          </div>
        ))}
      </div>
    </div>
  );
}

// Auto-save indicator
function AutoSaveIndicator({ lastSaved, isSaving }) {
  if (isSaving) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Loader2 className="h-3 w-3 animate-spin" />
        A guardar...
      </div>
    );
  }
  
  if (lastSaved) {
    return (
      <div className="flex items-center gap-2 text-xs text-green-600">
        <Save className="h-3 w-3" />
        Rascunho guardado às {lastSaved.toLocaleTimeString("pt-PT", { hour: "2-digit", minute: "2-digit" })}
      </div>
    );
  }
  
  return null;
}

const ESTADOS_CIVIS = [
  { value: "solteiro", label: "Solteiro/a" },
  { value: "casado", label: "Casado/a" },
  { value: "casado_adquiridos", label: "Casado/a: Comunhão de Adquiridos" },
  { value: "casado_geral", label: "Casado/a: Comunhão Geral de Bens" },
  { value: "casado_separacao", label: "Casado/a: Separação de Bens" },
  { value: "divorciado", label: "Divorciado/a" },
  { value: "viuvo", label: "Viúvo/a" },
  { value: "uniao_facto", label: "União de Facto" },
];

const TIPOS_IMOVEL = [
  { value: "apartamento", label: "Apartamento" },
  { value: "moradia", label: "Moradia" },
  { value: "terreno", label: "Terreno" },
  { value: "outro", label: "Outro" },
];

const QUARTOS = [
  { value: "T0", label: "T0" },
  { value: "T1", label: "T1" },
  { value: "T2", label: "T2" },
  { value: "T3", label: "T3" },
  { value: "T4", label: "T4" },
  { value: "T5+", label: "T5+" },
];

const CARACTERISTICAS = [
  { value: "elevador", label: "Elevador" },
  { value: "2_wcs", label: "2 ou mais WCs" },
  { value: "transportes", label: "Proximidade de transportes públicos" },
  { value: "garagem", label: "Garagem" },
  { value: "piscina", label: "Piscina" },
  { value: "varanda", label: "Varanda" },
  { value: "andar_maximo", label: "Andar máximo" },
  { value: "outro", label: "Outro" },
];

const BANCOS = [
  "ABANCA", "BBVA", "BEST", "BIG", "BPI", "CGD", "Crédito Agrícola",
  "CTT", "Millennium bcp", "Novo Banco", "Popular", "Santander Totta", "Outro"
];

// E1.3 - Cores dos bancos (bg / text)
const BANCO_COLORS = {
  "BPI":              { bg: "#003E7E", text: "#fff" },
  "CGD":              { bg: "#008552", text: "#fff" },
  "Santander Totta":  { bg: "#EC0000", text: "#fff" },
  "Millennium bcp":   { bg: "#C8102E", text: "#fff" },
  "Novo Banco":       { bg: "#E30613", text: "#fff" },
  "Crédito Agrícola": { bg: "#006633", text: "#fff" },
  "CTT":              { bg: "#E2001A", text: "#fff" },
  "BBVA":             { bg: "#004481", text: "#fff" },
  "ABANCA":           { bg: "#00718F", text: "#fff" },
  "BEST":             { bg: "#002D62", text: "#fff" },
  "BIG":              { bg: "#1A1A2E", text: "#fff" },
  "Popular":          { bg: "#DD0031", text: "#fff" },
  "Outro":            { bg: "#6B7280", text: "#fff" },
};

// REQUIRED_FIELDS is now derived dynamically from allFieldsConfig (see dynamicRequiredFields memo below)

// Dados de simulação para testar o formulário
const MOCK_DATA = {
  // Step 1 - Dados Pessoais
  name: "João Pedro da Silva Santos",
  email: "joao.santos.teste@email.pt",
  phone: "+351912345678",
  nif: "291654738", // NIF válido (checksum OK)
  niss: "12345678901",
  documento_id: "00123456",
  data_validade_cc: "2030-06-15",
  naturalidade: "Lisboa",
  nacionalidade: "Portuguesa",
  morada_fiscal: "Rua Augusta, 123, 4º Esq, 1100-053 Lisboa",
  birth_date: "1992-03-15",
  estado_civil: "solteiro",
  compra_tipo: "individual",
  menor_35_anos: false,
  // Step 2 - 2º Titular (vazio, compra individual)
  titular2_name: "",
  titular2_email: "",
  titular2_nif: "",
  titular2_documento_id: "",
  titular2_naturalidade: "",
  titular2_nacionalidade: "",
  titular2_phone: "",
  titular2_morada_fiscal: "",
  titular2_birth_date: "",
  titular2_estado_civil: "",
  // Step 3 - Imóvel
  finalidade: "compra_imovel",
  tipo_imovel: "apartamento",
  num_quartos: "T3",
  localizacao: "Lisboa, zona do Parque das Nações",
  caracteristicas: ["elevador", "garagem", "transportes"],
  outras_caracteristicas: "",
  area_pretendida: "120",
  valor_maximo_imovel: "350000",
  ja_tem_casa_escolhida: true,
  proprietario_nome: "Carlos Ferreira",
  proprietario_contacto: "+351911111111",
  caracteristicas_imovel: "Apartamento com vista rio, 2 casas de banho",
  // Step 4 - Profissional + Financeira
  employment_type: "efetivo",
  employment_duration: "3",
  employer_name: "Tech Solutions Lda.",
  employer_nif: "516253487",
  trabalha_estrangeiro: "nao",
  acesso_portal_financas: "seguranca_social",
  chave_movel_digital: "sim",
  salario_liquido: "1850",
  renda_habitacao_atual: "800",
  precisa_vender_casa: "nao",
  efetivo: "30000",
  fiador: "nao",
  // Step 5 - Bancos
  bancos_creditos: ["CGD", "Santander Totta"],
  bancos_simulacoes: ["Millennium bcp", "Novo Banco"],
  tempo_restante_credito: "240",
  capital_proprio: "70000",
  valor_financiado: "280000",
  prazo_pretendido: "30",
  valor_transferencia: "",
  valor_extra: "",
  // Step 6 - Outras
  outras_informacoes: "Teste de simulação — dados fictícios",
  consent_data: true,
  consent_contact: true,
};

export default function PublicClientForm({ previewMode = false }) {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [blockedMessage, setBlockedMessage] = useState(null);

  // Estado para erros de validação por campo
  const [fieldErrors, setFieldErrors] = useState({});
  
  // Refs para campos do formulário (substitui document.querySelector)
  const fieldRefs = useRef({});
  const formContainerRef = useRef(null);

  // ⚠️ CRITICAL: Declared BEFORE any useCallback/useMemo that references them
  // to avoid TDZ (Temporal Dead Zone) — const is hoisted but not initialized
  const [customFields, setCustomFields] = useState([]);
  const [allFieldsConfig, setAllFieldsConfig] = useState([]);
  const [configLoaded, setConfigLoaded] = useState(false); // true once backend config is fetched

  // Função para registar refs de campos de forma declarativa
  const registerFieldRef = useCallback((fieldName) => (element) => {
    if (element) {
      fieldRefs.current[fieldName] = element;
    }
  }, []);
  
  // Função helper para encontrar campo por nome (scoped ao container)
  const findFieldElement = useCallback((fieldName) => {
    // Primeiro tenta o ref registado
    if (fieldRefs.current[fieldName]) {
      return fieldRefs.current[fieldName];
    }
    // Fallback: query scoped ao container do formulário (não ao document global)
    if (formContainerRef.current) {
      return formContainerRef.current.querySelector(`[name="${fieldName}"], [data-testid="${fieldName}"], #${fieldName}`);
    }
    return null;
  }, []);
  
  // Auto-save state
  const [lastSaved, setLastSaved] = useState(null);
  const [isSaving, setIsSaving] = useState(false);
  const [hasDraft, setHasDraft] = useState(false);
  
  // Carregar rascunho do localStorage
  const loadDraft = useCallback(() => {
    try {
      const saved = localStorage.getItem(DRAFT_STORAGE_KEY);
      const timestamp = localStorage.getItem(DRAFT_TIMESTAMP_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        setHasDraft(true);
        return { data: parsed, timestamp: timestamp ? new Date(safeDateStr(timestamp)) : null };
      }
    } catch (e) {
      console.error("Erro ao carregar rascunho:", e);
    }
    return null;
  }, []);

  // Guardar rascunho no localStorage
  const saveDraft = useCallback((data) => {
    try {
      setIsSaving(true);
      localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(data));
      localStorage.setItem(DRAFT_TIMESTAMP_KEY, new Date().toISOString());
      setLastSaved(new Date());
      setHasDraft(true);
    } catch (e) {
      console.error("Erro ao guardar rascunho:", e);
    } finally {
      setIsSaving(false);
    }
  }, []);

  // Limpar rascunho
  const clearDraft = useCallback(() => {
    localStorage.removeItem(DRAFT_STORAGE_KEY);
    localStorage.removeItem(DRAFT_TIMESTAMP_KEY);
    setHasDraft(false);
    setLastSaved(null);
  }, []);

  // Simular preenchimento completo do formulário (apenas para testes)
  // Preenche MOCK_DATA (campos hardcoded) + gera dados mock para campos dinâmicos
  const simulateFill = useCallback(() => {
    // Gerar dados mock para campos dinâmicos do backend
    const dynamicMock = {};
    allFieldsConfig.forEach(field => {
      // Só preencher campos que ainda não estão em MOCK_DATA
      if (field.field_key in MOCK_DATA) return;
      const key = field.field_key;
      const type = field.field_type;
      if (type === 'text' || type === 'email' || type === 'tel') {
        dynamicMock[key] = `Mock ${field.label || key}`;
      } else if (type === 'number') {
        dynamicMock[key] = '100';
      } else if (type === 'date') {
        dynamicMock[key] = '2000-01-15';
      } else if (type === 'select' && field.options?.length > 0) {
        dynamicMock[key] = field.options[0];
      } else if (type === 'checkbox' && field.options?.length > 0) {
        dynamicMock[key] = [field.options[0]];
      } else if (type === 'radio') {
        dynamicMock[key] = 'sim';
      } else if (type === 'textarea') {
        dynamicMock[key] = 'Texto de teste para ' + (field.label || key);
      }
    });

    setFormData(prev => ({ ...prev, ...MOCK_DATA, ...dynamicMock }));
    setStep(1);
    setFieldErrors({});
    clearDraft();
    toast.success("Formulário preenchido com dados de teste — navegue pelos passos para rever", {
      duration: 4000,
    });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [clearDraft, allFieldsConfig]);

  const [formData, setFormData] = useState(() => {
    const defaults = {
      // Dados Pessoais - Titular
      name: "",
      email: "",
      nif: "",
      niss: "",
      documento_id: "",
      data_validade_cc: "",
      naturalidade: "",
      nacionalidade: "",
      phone: "",
      morada_fiscal: "",
      birth_date: "",
      estado_civil: "",
      compra_tipo: "",
      menor_35_anos: false,
      sexo: "",
      profissao: "",
      codigo_postal: "",
      
      // Dados do 2º Titular
      titular2_name: "",
      titular2_email: "",
      titular2_nif: "",
      titular2_documento_id: "",
      titular2_naturalidade: "",
      titular2_nacionalidade: "",
      titular2_phone: "",
      titular2_morada_fiscal: "",
      titular2_birth_date: "",
      titular2_estado_civil: "",
      
      // Imóvel Pretendido
      tipo_imovel: "",
      num_quartos: "",
      localizacao: "",
      caracteristicas: [],
      outras_caracteristicas: "",
      
      // Novos campos de imóvel - área, valor e finalidade
      area_pretendida: "",           // Área pretendida em m²
      valor_maximo_imovel: "",       // Valor máximo do imóvel
      finalidade: "",                // compra_imovel, refinanciamento
      ja_tem_casa_escolhida: false,  // Se já tem casa escolhida
      proprietario_nome: "",         // Nome do proprietário (se já tem casa)
      proprietario_contacto: "",     // Contacto do proprietário
      caracteristicas_imovel: "",    // Características básicas do imóvel escolhido
      
      // Campos de refinanciamento
      valor_transferencia: "",       // Valor a transferir/consolidar
      valor_extra: "",               // Valor extra necessário
      prazo_pretendido: "",          // Prazo pretendido em anos
      
      // Outras Informações
      outras_informacoes: "",
      
      // Situação Financeira
      acesso_portal_financas: "",
      chave_movel_digital: "",
      renda_habitacao_atual: "",
      precisa_vender_casa: "",
      efetivo: "",
      fiador: "",
      salario_liquido: "",
      
      // Situação Profissional (campos de emprego)
      employment_type: "",
      employment_duration: "",
      employer_name: "",
      employer_nif: "",
      trabalha_estrangeiro: "",
    
    // Bancos com créditos ativos
    bancos_creditos: [],
    
    // Bancos onde efetuou simulações de crédito
    bancos_simulacoes: [],
    
    // Tempo restante do crédito atual (refinanciamento)
    tempo_restante_credito: "",
    
    // Capital e Financiamento
    capital_proprio: "",
    valor_financiado: "",

    // Contas abertas (Créditos e Capital)
    tem_creditos_activos: "",
    valor_creditos_activos: "",
    
    // Consentimento
    consent_data: false,
    consent_contact: false,
  };
    // Tentar carregar rascunho ao iniciar - merge com defaults para garantir que campos novos existem
    const draft = loadDraft();
    if (draft?.data) {
      return { ...defaults, ...draft.data, 
        caracteristicas: Array.isArray(draft.data.caracteristicas) ? draft.data.caracteristicas : defaults.caracteristicas,
        bancos_creditos: Array.isArray(draft.data.bancos_creditos) ? draft.data.bancos_creditos : defaults.bancos_creditos,
        bancos_simulacoes: Array.isArray(draft.data.bancos_simulacoes) ? draft.data.bancos_simulacoes : defaults.bancos_simulacoes,
      };
    }
    return defaults;
  });

  // Keep a ref to formData so checkDependsOn always reads the LATEST value
  // (avoids stale closure issues in the useCallback chain)
  const formDataRef = useRef(formData);
  formDataRef.current = formData;

  // Carregar campos personalizados do backend (useState already declared above)
  const [stepConfig, setStepConfig] = useState({});
  const [stepLabels, setStepLabels] = useState({});
  // Default step config: step 2 is conditional on compra_tipo
  const DEFAULT_STEP_CONFIG = { "2": { "depends_on": { "field": "compra_tipo", "value": "outra_pessoa" } } };
  const effectiveStepConfig = useMemo(() => {
    const dbConfig = stepConfig || {};
    const merged = {};
    // Collect all step numbers from both default and DB config
    const allSteps = new Set([...Object.keys(DEFAULT_STEP_CONFIG), ...Object.keys(dbConfig)]);
    for (const stepNum of allSteps) {
      const defaultEntry = DEFAULT_STEP_CONFIG[stepNum];
      const dbEntry = dbConfig[stepNum];
      if (defaultEntry && dbEntry) {
        // Deep merge: DB entry wins for most fields, but depends_on needs special handling
        merged[stepNum] = { ...defaultEntry, ...dbEntry };
        // If DB has no depends_on but default does, keep the default
        if (!dbEntry.depends_on && defaultEntry.depends_on) {
          merged[stepNum].depends_on = defaultEntry.depends_on;
        }
        // If DB has depends_on, deep-merge with special care for "value":
        // The DB may store the DISPLAY LABEL (e.g. "Com outra pessoa") instead of
        // the internal VALUE KEY (e.g. "outra_pessoa"). The DEFAULT always has the
        // correct internal key, so we prefer it when there's a mismatch.
        if (dbEntry.depends_on && defaultEntry.depends_on) {
          merged[stepNum].depends_on = { ...defaultEntry.depends_on, ...dbEntry.depends_on };
          // CRITICAL: Always prefer the DEFAULT depends_on value over DB.
          // The DB may contain display labels saved by the admin UI, while the
          // DEFAULT has the correct internal field value key that matches formData.
          // e.g., default: "outra_pessoa" (key) vs db: "Com outra pessoa" (label)
          if (defaultEntry.depends_on.value !== undefined) {
            merged[stepNum].depends_on.value = defaultEntry.depends_on.value;
          }
          // Clean up: remove value_in if it's null/undefined/empty (can cause false negatives)
          if (!dbEntry.depends_on.value_in && defaultEntry.depends_on.value) {
            delete merged[stepNum].depends_on.value_in;
          }
        }
      } else {
        merged[stepNum] = dbEntry || defaultEntry;
      }
    }
    return merged;
  }, [stepConfig]);
  useEffect(() => {
    const fetchFormConfig = async () => {
      try {
        const res = await axios.get(`${API_URL}/public/form-config`);
        setCustomFields(res.data.custom_fields || []);
        setAllFieldsConfig(res.data.all_fields || []);
        setStepConfig(res.data.step_config || {});
        setStepLabels(res.data.step_labels || {});
      } catch {
        // Endpoint pode não existir em deployments mais antigos
      } finally {
        setConfigLoaded(true);
      }
    };
    fetchFormConfig();
  }, []);

  // ─── Helper: check depends_on condition ─────────────
  // depends_on can be:
  //   {"field": X, "value": V}     → visible when formData[X] == V
  //   {"field": X, "value_in": [V1, V2]} → visible when formData[X] is in array
  //   {"field": X, "not_value": V} → visible when formData[X] != V
  //   {"field": X, "contains": V}  → visible when formData[X] (array) contains V
  const checkDependsOn = useCallback((dependsOn) => {
    if (!dependsOn) return true;
    const { field, value, value_in, not_value, contains } = dependsOn;
    // Use ref to always read the LATEST formData (avoids stale closures)
    let fieldValue = formDataRef.current[field];

    // Normalize "Sim"/"Não" to boolean for checkbox comparisons
    if (value === "Sim" || value === "Não" || not_value === "Sim" || not_value === "Não" ||
        (Array.isArray(value_in) && value_in.some(v => v === "Sim" || v === "Não"))) {
      if (fieldValue === true) fieldValue = "Sim";
      else if (fieldValue === false) fieldValue = "Não";
    }

    // Prefer "value" (exact match) over "value_in" (array match) when BOTH are present.
    // This prevents bugs where DB stores value_in: null/[] alongside value, which would
    // cause value_in to take precedence and always return false.
    if (value !== undefined) {
      // For boolean values, compare strictly
      if (value === true) return fieldValue === true;
      if (value === false) return fieldValue === false;
      return fieldValue === value;
    }
    if (value_in !== undefined && value_in !== null) {
      // Only use value_in if it's a valid non-empty array
      if (Array.isArray(value_in) && value_in.length > 0) {
        return value_in.includes(fieldValue);
      }
      // value_in is null, undefined, or empty array — skip this condition
    }
    if (not_value !== undefined) {
      return fieldValue !== not_value;
    }
    if (contains !== undefined) {
      return Array.isArray(fieldValue) && fieldValue.includes(contains);
    }
    return true;
  }, []); // stable — reads formData via ref, no closure dependency

  // ─── Conditional Step Logic (dynamic based on step_config) ─────────────
  // step_config: { "2": { "depends_on": { "field": "compra_tipo", "value": "outra_pessoa" } } }
  // Returns true if the step should be visible based on current formData
  const isStepVisible = useCallback((stepNum) => {
    const config = effectiveStepConfig[String(stepNum)];
    if (!config || !config.depends_on) return true;
    return checkDependsOn(config.depends_on);
  }, [effectiveStepConfig, checkDependsOn, formData]); // formData triggers re-creation so downstream hooks update

  // Maximum step number (supports custom steps beyond 6)
  const maxStepNum = useMemo(() => {
    if (allFieldsConfig.length === 0) return 6;
    return Math.max(6, ...allFieldsConfig.map(f => f.step || 1), ...Object.keys(effectiveStepConfig).map(Number));
  }, [allFieldsConfig, effectiveStepConfig]);

  // Total de steps efetivos (exclui passos invisíveis)
  const totalSteps = useMemo(() => {
    let count = 0;
    for (let s = 1; s <= maxStepNum; s++) {
      if (isStepVisible(s)) count++;
    }
    return count;
  }, [isStepVisible, maxStepNum]);

  // Map logical step (1..totalSteps) → real step number (1..maxStepNum)
  const logicalToRealStep = useCallback((logicalStep) => {
    let logical = 0;
    for (let s = 1; s <= maxStepNum; s++) {
      if (isStepVisible(s)) {
        logical++;
        if (logical === logicalStep) return s;
      }
    }
    return logicalStep;
  }, [isStepVisible, maxStepNum]);

  // Map real step (1..maxStepNum) → logical step (1..totalSteps)
  const realToLogicalStep = useCallback((realStep) => {
    let logical = 0;
    for (let s = 1; s <= maxStepNum; s++) {
      if (isStepVisible(s)) {
        logical++;
        if (s === realStep) return logical;
      }
    }
    return realStep;
  }, [isStepVisible, maxStepNum]);

  // Get next visible real step (skipping hidden steps)
  const getNextRealStep = useCallback((currentStep) => {
    for (let s = currentStep + 1; s <= maxStepNum; s++) {
      if (isStepVisible(s)) return s;
    }
    return maxStepNum + 1; // past the end
  }, [isStepVisible, maxStepNum]);

  // Get previous visible real step (skipping hidden steps)
  const getPrevRealStep = useCallback((currentStep) => {
    for (let s = currentStep - 1; s >= 1; s--) {
      if (isStepVisible(s)) return s;
    }
    return 0; // before the start
  }, [isStepVisible]);

  // Auto-skip when a step becomes hidden (e.g., compra_tipo changes, or stepConfig loads)
  useEffect(() => {
    if (!isStepVisible(step)) {
      // Current step is now hidden — jump to next visible step
      const nextVisible = getNextRealStep(step - 1);
      if (nextVisible <= maxStepNum) {
        setStep(nextVisible);
      }
    }
  }, [isStepVisible, step, getNextRealStep, maxStepNum]);

  // ─── Campos obrigatórios hardcoded (por passo) ────────────────────────────
  // Estes campos são sempre obrigatórios, independentemente do config do backend.
  // Os campos condicionais (ex: titular2) só contam se o passo estiver visível.
  const HARDCODED_REQUIRED_BY_STEP = useMemo(() => ({
    1: ["name", "email", "phone", "nif", "documento_id", "data_validade_cc",
        "naturalidade", "nacionalidade", "morada_fiscal", "birth_date",
        "estado_civil", "compra_tipo"],
    2: ["titular2_name", "titular2_email", "titular2_nif",
        "titular2_documento_id", "titular2_naturalidade",
        "titular2_nacionalidade", "titular2_phone", "titular2_morada_fiscal",
        "titular2_birth_date", "titular2_estado_civil"],
    3: ["finalidade", "tipo_imovel", "localizacao"],
    4: ["employment_type", "employer_name", "salario_liquido"],
    5: [], // Bancos — nenhum obrigatório por defeito
    6: ["consent_data", "consent_contact"],
  }), []);

  // Dynamic required fields derived from allFieldsConfig
  const dynamicRequiredFields = useMemo(() => {
    if (allFieldsConfig.length === 0) {
      // Config not loaded yet — return empty so progress bar doesn't show wrong data
      return [];
    }
    return allFieldsConfig
      .filter(f => f.is_required && f.is_visible !== false)
      .map(f => f.field_key);
  }, [allFieldsConfig]);

  // Lista completa de campos obrigatórios visíveis (hardcoded + dinâmicos)
  // Apenas inclui campos de passos que estão visíveis (respeita depends_on)
  const allRequiredVisibleFields = useMemo(() => {
    const fields = new Set();

    // 1. Adicionar campos hardcoded de passos visíveis
    for (const [stepNum, stepFields] of Object.entries(HARDCODED_REQUIRED_BY_STEP)) {
      if (isStepVisible(Number(stepNum))) {
        stepFields.forEach(f => fields.add(f));
      }
    }

    // 2. Adicionar campos dinâmicos obrigatórios (que não estão já nos hardcoded)
    dynamicRequiredFields.forEach(f => {
      // Verificar se o campo está num passo visível
      const fieldConfig = allFieldsConfig.find(fc => fc.field_key === f);
      if (fieldConfig) {
        const fieldStep = fieldConfig.step || 1;
        if (isStepVisible(fieldStep)) {
          // Respeitar depends_on do campo individual (se existir)
          if (fieldConfig.depends_on) {
            if (checkDependsOn(fieldConfig.depends_on)) {
              fields.add(f);
            }
          } else {
            fields.add(f);
          }
        }
      } else {
        // Campo dinâmico sem step definido — incluir se não está nos hardcoded
        if (!fields.has(f)) {
          fields.add(f);
        }
      }
    });

    return Array.from(fields);
  }, [HARDCODED_REQUIRED_BY_STEP, dynamicRequiredFields, isStepVisible, allFieldsConfig, checkDependsOn]);

  // Calcular campos preenchidos para progresso
  // Lógica: (campos_preenchidos / total_campos_obrigatórios_visíveis) * 100
  // Inicia estritamente a 0% e termina a 100%
  const calculateProgress = useCallback(() => {
    if (allRequiredVisibleFields.length === 0) {
      return { completed: 0, total: 0 };
    }
    let filled = 0;
    allRequiredVisibleFields.forEach(field => {
      const val = formData[field];
      // Contar como preenchido se tem valor não-vazio
      // Campos booleanos (consent_data, consent_contact): true conta como preenchido
      if (typeof val === 'boolean') {
        if (val === true) filled++;
      } else if (val && val !== "" && !(Array.isArray(val) && val.length === 0)) {
        filled++;
      }
    });
    return { completed: filled, total: allRequiredVisibleFields.length };
  }, [formData, allRequiredVisibleFields]);

  const progress = calculateProgress();

  // Auto-save com debounce (desativado em modo preview)
  useEffect(() => {
    if (previewMode) return;
    const timer = setTimeout(() => {
      // Só guardar se houver dados preenchidos
      if (formData.name || formData.email || formData.nif) {
        saveDraft(formData);
      }
    }, 2000); // 2 segundos de debounce

    return () => clearTimeout(timer);
  }, [formData, saveDraft, previewMode]);

  // Mostrar toast se existe rascunho ao carregar (desativado em modo preview)
  useEffect(() => {
    if (previewMode) return;
    const draft = loadDraft();
    if (draft?.data && draft.timestamp) {
      const timeAgo = new Date() - draft.timestamp;
      const hoursAgo = Math.floor(timeAgo / (1000 * 60 * 60));
      
      if (hoursAgo < 48) { // Só mostrar se foi há menos de 48 horas
        toast.info(
          <div className="flex flex-col gap-1">
            <span className="font-medium">Rascunho encontrado</span>
            <span className="text-xs">Guardado há {hoursAgo > 0 ? `${hoursAgo}h` : "poucos minutos"}</span>
          </div>,
          { duration: 5000 }
        );
      }
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Mapa de ordem dos campos: field_key -> order (do config do admin)
  // Usado para aplicar CSS order nos campos hardcoded de cada step
  const fieldOrderMap = useMemo(() => {
    const map = {};
    allFieldsConfig.forEach((f) => {
      map[f.field_key] = f.order ?? 0;
    });
    return map;
  }, [allFieldsConfig]);

  // Conjunto de campos que estão is_visible=false (devem ser escondidos)
  const hiddenFields = useMemo(() => {
    const set = new Set();
    allFieldsConfig.forEach((f) => {
      if (!f.is_visible) set.add(f.field_key);
    });
    return set;
  }, [allFieldsConfig]);

  // Mapa de labels personalizados: field_key -> custom label (do admin)
  const customLabelMap = useMemo(() => {
    const map = {};
    allFieldsConfig.forEach((f) => {
      if (f.label) map[f.field_key] = f.label;
    });
    return map;
  }, [allFieldsConfig]);

  // Mapa de obrigatoriedade dinâmica: field_key -> is_required (do admin)
  const requiredOverrideMap = useMemo(() => {
    const map = {};
    allFieldsConfig.forEach((f) => {
      if (f.is_required !== undefined) map[f.field_key] = f.is_required;
    });
    return map;
  }, [allFieldsConfig]);

  // Helper: retorna style object com CSS order para campos do config
  const getFieldStyle = (fieldKey) => {
    if (!(fieldKey in fieldOrderMap)) return undefined;
    return {
      order: fieldOrderMap[fieldKey],
      ...(hiddenFields.has(fieldKey) ? { display: 'none' } : {}),
    };
  };

  // Helper: retorna label personalizado ou fallback para label padrão
  const getFieldLabel = (fieldKey, defaultLabel) => {
    return customLabelMap[fieldKey] || defaultLabel;
  };

  // Helper: retorna is_required do admin config ou fallback para valor padrão
  const isFieldRequired = (fieldKey, defaultRequired = false) => {
    return fieldKey in requiredOverrideMap ? requiredOverrideMap[fieldKey] : defaultRequired;
  };

  // Build map of field configs by key (includes ALL fields from config, not just custom)
  const fieldConfigMap = useMemo(() => {
    const map = {};
    allFieldsConfig.forEach((f) => {
      map[f.field_key] = f;
    });
    return map;
  }, [allFieldsConfig]);

  // Renderizar um campo personalizado dinâmico
  const renderCustomField = (field) => {
    const value = formData[field.field_key] || "";
    const updateCustom = (v) => updateField(field.field_key, v);

    return (
      <div key={field.field_key} className="space-y-2" data-testid={`custom-field-${field.field_key}`}>
        {isFieldRequired(field.field_key, field.is_required) ? (
          <RequiredLabel htmlFor={field.field_key} required={isFieldRequired(field.field_key, field.is_required)}>{getFieldLabel(field.field_key, field.label)}</RequiredLabel>
        ) : (
          <Label htmlFor={field.field_key}>{getFieldLabel(field.field_key, field.label)}</Label>
        )}

        {field.field_type === "text" && (
          <Input
            id={field.field_key}
            value={value}
            onChange={(e) => updateCustom(e.target.value)}
            placeholder={field.placeholder || ""}
          />
        )}

        {field.field_type === "number" && (
          <Input
            id={field.field_key}
            type="number"
            value={value}
            onChange={(e) => updateCustom(e.target.value)}
            placeholder={field.placeholder || ""}
          />
        )}

        {field.field_type === "date" && (
          <Input
            id={field.field_key}
            type="date"
            lang="pt"
            value={value}
            onChange={(e) => updateCustom(e.target.value)}
            placeholder="DD/MM/AAAA"
          />
        )}

        {field.field_type === "select" && field.options && (
          <Select value={value} onValueChange={updateCustom}>
            <SelectTrigger>
              <SelectValue placeholder={field.placeholder || "Selecione"} />
            </SelectTrigger>
            <SelectContent>
              {field.options.map((opt) => (
                <SelectItem key={opt} value={opt}>{opt}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        {field.field_type === "checkbox" && field.options && (
          <div className="flex flex-wrap gap-2">
            {field.options.map((opt) => {
              const arr = Array.isArray(formData[field.field_key]) ? formData[field.field_key] : [];
              const checked = arr.includes(opt);
              return (
                <button
                  key={opt}
                  type="button"
                  onClick={() => {
                    const updated = checked ? arr.filter(v => v !== opt) : [...arr, opt];
                    updateCustom(updated);
                  }}
                  className={`px-3 py-1.5 rounded-full text-sm font-medium border-2 transition-all ${
                    checked
                      ? "ring-2 ring-offset-1 ring-primary scale-105 bg-primary text-primary-foreground border-primary"
                      : "opacity-60 hover:opacity-80 bg-transparent text-foreground border-border"
                  }`}
                >
                  {checked && <span className="mr-1">&#10003;</span>}
                  {opt}
                </button>
              );
            })}
          </div>
        )}

        {field.field_type === "radio" && (
          <div className="flex gap-3">
            <Button
              type="button"
              variant={value === "sim" ? "default" : "outline"}
              className="flex-1"
              onClick={() => updateCustom("sim")}
            >
              Sim
            </Button>
            <Button
              type="button"
              variant={value === "nao" ? "default" : "outline"}
              className="flex-1"
              onClick={() => updateCustom("nao")}
            >
              Não
            </Button>
          </div>
        )}

        {field.hint && <FieldHint>{field.hint}</FieldHint>}
      </div>
    );
  };

  // Obter campos personalizados para um passo específico
  const getCustomFieldsForStep = (stepNum) => {
    return customFields
      .filter(f => f.step === stepNum)
      .sort((a, b) => (a.order_index ?? a.order ?? 0) - (b.order_index ?? b.order ?? 0));
  };

  // ─── Field update helpers ──────────────────────────────────────────────
  // ⚠️ MUST be declared BEFORE renderDynamicField useCallback that uses them.
  // Using const (not function declarations) means they are NOT hoisted,
  // so order matters — TDZ will crash if referenced before initialization.

  const updateField = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const toggleCaracteristica = (value) => {
    setFormData(prev => ({
      ...prev,
      caracteristicas: (prev.caracteristicas || []).includes(value)
        ? prev.caracteristicas.filter(c => c !== value)
        : [...(prev.caracteristicas || []), value]
    }));
  };

  const toggleBanco = (banco) => {
    setFormData(prev => {
      const current = prev.bancos_creditos || [];
      const exists = current.some(item => typeof item === 'object' ? item.banco === banco : item === banco);
      if (exists) {
        return { ...prev, bancos_creditos: current.filter(item => typeof item === 'object' ? item.banco !== banco : item !== banco) };
      }
      return { ...prev, bancos_creditos: [...current, { banco, valor: "" }] };
    });
  };

  const updateBancoValor = (banco, valor) => {
    setFormData(prev => ({
      ...prev,
      bancos_creditos: (prev.bancos_creditos || []).map(item => {
        if (typeof item === 'object' && item.banco === banco) return { ...item, valor };
        if (item === banco) return { banco, valor };
        return item;
      })
    }));
  };

  const toggleBancoSimulacoes = (banco) => {
    setFormData(prev => ({
      ...prev,
      bancos_simulacoes: (prev.bancos_simulacoes || []).includes(banco)
        ? prev.bancos_simulacoes.filter(b => b !== banco)
        : [...(prev.bancos_simulacoes || []), banco]
    }));
  };

  const toggleContasAbertas = (banco) => {
    setFormData(prev => ({
      ...prev,
      tem_creditos_activos: (prev.tem_creditos_activos || []).includes(banco)
        ? prev.tem_creditos_activos.filter(b => b !== banco)
        : [...(prev.tem_creditos_activos || []), banco]
    }));
  };

  // ─── Dynamic field rendering helpers ───────────────────────────────────

  // Known fields that should span both grid columns (md:col-span-2)
  const FULL_WIDTH_FIELD_KEYS = new Set([
    "name", "morada_fiscal", "compra_tipo", "menor_35_anos",
    "finalidade", "caracteristicas", "outras_caracteristicas",
    "ja_tem_casa_escolhida", "caracteristicas_imovel",
    "outras_informacoes", "valor_transferencia", "salario_liquido",
    "titular2_name", "titular2_morada_fiscal", "localizacao",
    "bancos_creditos", "tem_creditos_activos", "bancos_simulacoes",
    "tempo_restante_credito",
  ]);

  // Fields that render as simple sim/nao selects
  const SIM_NAO_SELECT_FIELDS = new Set([
    "chave_movel_digital", "precisa_vender_casa", "efetivo",
    "trabalha_estrangeiro", "fiador",
  ]);

  // Fields that use the NIF pattern (digit-only, maxLength=9)
  const NIF_PATTERN_FIELDS = new Set(["nif", "titular2_nif", "employer_nif"]);

  // Fields that use ESTADOS_CIVIS options
  const ESTADO_CIVIL_FIELDS = new Set(["estado_civil", "titular2_estado_civil"]);

  // Fallback hints for well-known fields (used when config has no hint)
  const FIELD_HINT_FALLBACKS = {
    email: "Utilizaremos este email para comunicar consigo sobre o seu processo.",
    phone: "Número de contacto direto para agendar visitas e reuniões.",
    nif: "Número de Identificação Fiscal - 9 dígitos, encontra-se no Cartão de Cidadão.",
    titular2_nif: "Número de Identificação Fiscal - 9 dígitos",
    documento_id: "Número do documento de identificação válido.",
    titular2_documento_id: "Número do documento de identificação válido.",
    data_validade_cc: "Data de validade do Cartão de Cidadão.",
    naturalidade: "Freguesia/concelho onde nasceu.",
    titular2_naturalidade: "Freguesia/concelho onde nasceu.",
    morada_fiscal: "Morada completa conforme registada nas Finanças.",
    titular2_morada_fiscal: "Morada completa conforme registada nas Finanças.",
    estado_civil: "Se casado/a, indique o regime de bens do casamento.",
    titular2_estado_civil: "Regime de bens do casamento.",
    compra_tipo: "Se comprar com outra pessoa (cônjuge, familiar, etc.), selecione \"Com outra pessoa\" para preencher os dados do 2º titular no próximo passo.",
    access_portal_financas: "Indique a que portais oficiais tem acesso. As credenciais serão solicitadas posteriormente se necessário.",
    chave_movel_digital: "A Chave Móvel Digital facilita a assinatura digital de documentos.",
    renda_habitacao_atual: "Se vive em casa própria ou com familiares, deixe em branco ou coloque 0.",
    precisa_vender_casa: "Se precisa vender para ter capital de entrada ou liquidar crédito existente.",
    efetivo: "Se tem contrato de trabalho sem termo (efetivo) ou está em período experimental.",
    trabalha_estrangeiro: "Indique se trabalha fora de Portugal. Pode influenciar as condições do crédito.",
    employment_type: "Indique a sua situação profissional atual.",
    employment_duration: "Quanto tempo trabalha na empresa atual ou como independente.",
    employer_nif: "O NIF da empresa onde trabalha (encontra-se no recibo de vencimento).",
    fiador: "Ter um fiador disponível pode ajudar na aprovação do crédito.",
    area_pretendida: "Valor aproximado/médio em metros quadrados",
    bancos_creditos: "Inclui crédito habitação, automóvel, pessoal, ou cartões de crédito com saldo em dívida.",
    tem_creditos_activos: "Selecione os bancos onde tem contas de crédito abertas (habitação, automóvel, pessoal, cartões).",
    bancos_simulacoes: "Indique os bancos onde já efetuou simulações ou pedidos de crédito habitação.",
    capital_proprio: "Dinheiro que tem disponível para entrada + despesas (escritura, IMT, seguros).",
    valor_financiado: "Pode indicar um valor fixo ou percentagem (ex: \"90% do valor do imóvel\").",
    valor_transferencia: "Valor total dos créditos que pretende consolidar/transferir.",
    valor_extra: "Se precisa de capital adicional além do refinanciamento.",
  };

  // Fields that control step visibility — must NEVER be hidden even if admin sets is_visible: false
  const STEP_TRIGGER_FIELDS = useMemo(() => {
    const fields = new Set();
    for (const stepCfg of Object.values(effectiveStepConfig)) {
      if (stepCfg?.depends_on?.field) {
        fields.add(stepCfg.depends_on.field);
      }
    }
    return fields;
  }, [effectiveStepConfig]);

  // Get visible fields for a given step, sorted by order, filtered by depends_on
  // Step trigger fields (e.g., compra_tipo) are always shown even if is_visible: false
  const getFieldsForStep = useCallback((stepNum) => {
    return allFieldsConfig
      .filter(f => {
        if (f.step !== stepNum) return false;
        // Step trigger fields are ALWAYS visible — they control step visibility
        if (STEP_TRIGGER_FIELDS.has(f.field_key)) return true;
        if (f.is_visible === false) return false;
        // Check depends_on_all (ALL conditions must be met) if present
        if (f.depends_on_all && Array.isArray(f.depends_on_all)) {
          return f.depends_on_all.every(cond => checkDependsOn(cond));
        }
        return checkDependsOn(f.depends_on);
      })
      .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  }, [allFieldsConfig, checkDependsOn, formData, STEP_TRIGGER_FIELDS]); // formData triggers re-filter when field values change

  // Render a single field dynamically based on its config
  // Special fields use their existing specialized rendering; others use DynamicFormField
  const renderDynamicField = useCallback((field) => {
    const key = field.field_key;
    const label = getFieldLabel(key, field.label) || key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    const required = isFieldRequired(key, field.is_required);
    const error = fieldErrors[key] || null;
    const value = formData[key];
    const fw = FULL_WIDTH_FIELD_KEYS.has(key);
    const cls = fw ? "md:col-span-2" : "";
    const style = getFieldStyle(key);
    const hint = field.hint || FIELD_HINT_FALLBACKS[key] || null;
    const errCls = error ? "border-red-500 focus-visible:ring-red-500 bg-red-50" : "";

    // ── NIF pattern fields (digit-only, maxLength=9) ──────────────────────
    if (NIF_PATTERN_FIELDS.has(key)) {
      return (
        <div className={cn("space-y-2 relative", cls)} key={key} style={style}>
          <RequiredLabel htmlFor={key} required={required}>{label}</RequiredLabel>
          <Input
            id={key} name={key} type="text"
            value={value || ""}
            onChange={(e) => updateField(key, e.target.value.replace(/\D/g, ""))}
            placeholder="123456789" maxLength={9}
            className={errCls}
          />
          {error && <FieldError>{error}</FieldError>}
          {hint && <FieldHint>{hint}</FieldHint>}
        </div>
      );
    }

    // ── birth_date (date with max 18 years ago) ──────────────────────────
    if (key === "birth_date" || key === "titular2_birth_date") {
      const maxDate = key === "birth_date"
        ? new Date(Date.now() - 18 * 365.25 * 24 * 60 * 60 * 1000).toISOString().split('T')[0]
        : undefined;
      return (
        <div className={cn("space-y-2 relative", cls)} key={key} style={style}>
          <RequiredLabel htmlFor={key} required={required}>{label}</RequiredLabel>
          <Input
            id={key} name={key} type="date"
            lang="pt"
            value={value || ""}
            onChange={(e) => updateField(key, e.target.value)}
            max={maxDate}
            className={errCls}
          />
          {error && <FieldError>{error}</FieldError>}
        </div>
      );
    }

    // ── estado_civil / titular2_estado_civil (select with ESTADOS_CIVIS) ─
    if (ESTADO_CIVIL_FIELDS.has(key)) {
      return (
        <div className={cn("space-y-2", cls)} key={key} style={style}>
          <RequiredLabel htmlFor={key} required={required}>{label}</RequiredLabel>
          <Select value={value || ""} onValueChange={(v) => updateField(key, v)}>
            <SelectTrigger className={errCls}>
              <SelectValue placeholder="Selecione" />
            </SelectTrigger>
            <SelectContent>
              {ESTADOS_CIVIS.map((ec) => (
                <SelectItem key={ec.value} value={ec.value}>{ec.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          {error && <FieldError>{error}</FieldError>}
          {hint && <FieldHint>{hint}</FieldHint>}
        </div>
      );
    }

    // ── tipo_imovel (select with TIPOS_IMOVEL) ───────────────────────────
    if (key === "tipo_imovel") {
      return (
        <div className={cn("space-y-2", cls)} key={key} style={style}>
          <RequiredLabel htmlFor={key} required={required}>{label}</RequiredLabel>
          <Select value={value || ""} onValueChange={(v) => updateField(key, v)}>
            <SelectTrigger className={errCls}>
              <SelectValue placeholder="Selecione" />
            </SelectTrigger>
            <SelectContent>
              {TIPOS_IMOVEL.map((ti) => (
                <SelectItem key={ti.value} value={ti.value}>{ti.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          {error && <FieldError>{error}</FieldError>}
        </div>
      );
    }

    // ── num_quartos (select with QUARTOS) ────────────────────────────────
    if (key === "num_quartos") {
      return (
        <div className={cn("space-y-2", cls)} key={key} style={style}>
          <RequiredLabel htmlFor={key} required={required}>{label}</RequiredLabel>
          <Select value={value || ""} onValueChange={(v) => updateField(key, v)}>
            <SelectTrigger className={errCls}>
              <SelectValue placeholder="Selecione" />
            </SelectTrigger>
            <SelectContent>
              {QUARTOS.map((q) => (
                <SelectItem key={q.value} value={q.value}>{q.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <FieldHint>T0 = Estúdio/Loft, T1 = 1 quarto, T2 = 2 quartos, etc.</FieldHint>
          {error && <FieldError>{error}</FieldError>}
        </div>
      );
    }

    // ── finalidade (select with dynamic hint) ────────────────────────────
    if (key === "finalidade") {
      return (
        <div className={cn("space-y-2", cls)} key={key} style={style}>
          <RequiredLabel htmlFor={key} required={required}>{label}</RequiredLabel>
          <Select value={value || ""} onValueChange={(v) => updateField(key, v)}>
            <SelectTrigger>
              <SelectValue placeholder="Selecione a finalidade" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="compra_imovel">Compra de Imóvel</SelectItem>
              <SelectItem value="refinanciamento">Refinanciamento / Transferência de Crédito</SelectItem>
            </SelectContent>
          </Select>
          <FieldHint>
            {value === "refinanciamento"
              ? "Seleccionou refinanciamento - não será necessário preencher dados do imóvel."
              : "Seleccionou compra - preencha os dados do imóvel pretendido abaixo."}
          </FieldHint>
          {error && <FieldError>{error}</FieldError>}
        </div>
      );
    }

    // ── compra_tipo (select individual/outra_pessoa) ─────────────────────
    if (key === "compra_tipo") {
      return (
        <div className={cn("space-y-2", cls)} key={key} style={style}>
          <RequiredLabel htmlFor={key} required={required}>{label}</RequiredLabel>
          <Select value={value} onValueChange={(v) => updateField(key, v)}>
            <SelectTrigger>
              <SelectValue placeholder="Selecione" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="individual">Individual</SelectItem>
              <SelectItem value="outra_pessoa">Com outra pessoa</SelectItem>
            </SelectContent>
          </Select>
          {hint && <FieldHint>{hint}</FieldHint>}
          {error && <FieldError>{error}</FieldError>}
        </div>
      );
    }

    // ── menor_35_anos (amber callout checkbox) ───────────────────────────
    if (key === "menor_35_anos") {
      return (
        <div className="space-y-3 md:col-span-2 p-4 bg-amber-50 border border-amber-200 rounded-lg" key={key} style={style}>
          <div className="flex items-start space-x-3">
            <Checkbox
              id={key}
              checked={!!value}
              onCheckedChange={(checked) => updateField(key, checked)}
            />
            <div className="space-y-1">
              <Label htmlFor={key} className="text-sm font-medium cursor-pointer">
                {label}
              </Label>
              <p className="text-xs text-amber-700">
                Se tem menos de 35 anos, pode ser elegível para benefícios fiscais na compra da primeira habitação própria permanente (isenção/redução de IMT e Imposto de Selo).
              </p>
            </div>
          </div>
        </div>
      );
    }

    // ── caracteristicas (checkbox group with CARACTERISTICAS) ────────────
    if (key === "caracteristicas") {
      return (
        <div className={cn("space-y-3", cls)} key={key} style={style}>
          <Label>{label}</Label>
          <FieldHint>Selecione apenas características que são absolutamente essenciais. Menos seleções = mais opções de imóveis.</FieldHint>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {CARACTERISTICAS.map((c) => (
              <div key={c.value} className="flex items-center space-x-2">
                <Checkbox
                  id={c.value}
                  checked={(value || []).includes(c.value)}
                  onCheckedChange={() => toggleCaracteristica(c.value)}
                />
                <Label htmlFor={c.value} className="text-sm cursor-pointer">{c.label}</Label>
              </div>
            ))}
          </div>
        </div>
      );
    }

    // ── ja_tem_casa_escolhida (boolean checkbox) ─────────────────────────
    if (key === "ja_tem_casa_escolhida") {
      return (
        <div className={cn("space-y-2", cls)} key={key} style={style}>
          <div className="flex items-center space-x-2">
            <Checkbox
              id={key}
              checked={!!value}
              onCheckedChange={(checked) => updateField(key, checked)}
            />
            <Label htmlFor={key} className="cursor-pointer">{label}</Label>
          </div>
        </div>
      );
    }

    // ── prazo_pretendido (select with year range) ────────────────────────
    if (key === "prazo_pretendido") {
      return (
        <div className={cn("space-y-2", cls)} key={key} style={style}>
          <RequiredLabel htmlFor={key} required={required}>{label}</RequiredLabel>
          <Select value={value || ""} onValueChange={(v) => updateField(key, v)}>
            <SelectTrigger>
              <SelectValue placeholder="Selecione" />
            </SelectTrigger>
            <SelectContent>
              {[5, 10, 15, 20, 25, 30, 35, 40].map((anos) => (
                <SelectItem key={anos} value={anos.toString()}>{anos} anos</SelectItem>
              ))}
            </SelectContent>
          </Select>
          {error && <FieldError>{error}</FieldError>}
        </div>
      );
    }

    // ── tempo_restante_credito (select with time ranges) ─────────────────
    if (key === "tempo_restante_credito") {
      return (
        <div className={cn("space-y-2 p-4 bg-amber-50 border border-amber-200 rounded-lg", cls)} key={key} style={style}>
          <RequiredLabel htmlFor={key} required={required}>{label}</RequiredLabel>
          <Select value={value || ""} onValueChange={(v) => updateField(key, v)}>
            <SelectTrigger>
              <SelectValue placeholder="Selecione o tempo restante" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="menos_1_ano">Menos de 1 ano</SelectItem>
              <SelectItem value="1_5_anos">1 a 5 anos</SelectItem>
              <SelectItem value="5_10_anos">5 a 10 anos</SelectItem>
              <SelectItem value="10_15_anos">10 a 15 anos</SelectItem>
              <SelectItem value="15_20_anos">15 a 20 anos</SelectItem>
              <SelectItem value="mais_20_anos">Mais de 20 anos</SelectItem>
            </SelectContent>
          </Select>
          {hint && <FieldHint>{hint}</FieldHint>}
          {error && <FieldError>{error}</FieldError>}
        </div>
      );
    }

    // ── acesso_portal_financas (select with custom options) ──────────────
    if (key === "acesso_portal_financas") {
      return (
        <div className={cn("space-y-2", cls)} key={key} style={style}>
          <Label>{label}</Label>
          <Select value={value || ""} onValueChange={(v) => updateField(key, v)}>
            <SelectTrigger>
              <SelectValue placeholder="Selecione" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="portal_financas">Portal das Finanças</SelectItem>
              <SelectItem value="seguranca_social">Segurança Social Direta</SelectItem>
              <SelectItem value="ambos">Ambos</SelectItem>
              <SelectItem value="nenhuma">Nenhuma</SelectItem>
            </SelectContent>
          </Select>
          {hint && <FieldHint>{hint}</FieldHint>}
        </div>
      );
    }

    // ── employment_type (select with custom options) ─────────────────────
    if (key === "employment_type") {
      return (
        <div className={cn("space-y-2", cls)} key={key} style={style}>
          <RequiredLabel htmlFor={key} required={required}>{label}</RequiredLabel>
          <Select value={value || ""} onValueChange={(v) => updateField(key, v)}>
            <SelectTrigger>
              <SelectValue placeholder="Selecione" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="efetivo">Contrato Efetivo (Sem Termo)</SelectItem>
              <SelectItem value="termo_certo">Contrato a Termo Certo</SelectItem>
              <SelectItem value="termo_incerto">Contrato a Termo Incerto</SelectItem>
              <SelectItem value="independente">Trabalhador Independente</SelectItem>
              <SelectItem value="empresario">Empresário em Nome Individual</SelectItem>
              <SelectItem value="reformado">Reformado/Pensionista</SelectItem>
              <SelectItem value="desempregado">Desempregado</SelectItem>
            </SelectContent>
          </Select>
          {hint && <FieldHint>{hint}</FieldHint>}
          {error && <FieldError>{error}</FieldError>}
        </div>
      );
    }

    // ── sim/nao selects ──────────────────────────────────────────────────
    if (SIM_NAO_SELECT_FIELDS.has(key)) {
      return (
        <div className={cn("space-y-2", cls)} key={key} style={style}>
          {required ? (
            <RequiredLabel htmlFor={key} required={required}>{label}</RequiredLabel>
          ) : (
            <Label>{label}</Label>
          )}
          <Select value={value || ""} onValueChange={(v) => updateField(key, v)}>
            <SelectTrigger>
              <SelectValue placeholder="Selecione" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="sim">Sim</SelectItem>
              <SelectItem value="nao">Não</SelectItem>
            </SelectContent>
          </Select>
          {hint && <FieldHint>{hint}</FieldHint>}
          {error && <FieldError>{error}</FieldError>}
        </div>
      );
    }

    // ── bancos_creditos (bank pills with value inputs) ──────────────────
    if (key === "bancos_creditos") {
      return (
        <div className={cn("space-y-3", cls)} key={key} style={style}>
          <RequiredLabel htmlFor={key} required={required}>{label}</RequiredLabel>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setFormData(prev => ({ ...prev, bancos_creditos: [] }))}
              className={`px-3 py-1.5 rounded-full text-sm font-medium border-2 transition-all ${
                (value || []).length === 0
                  ? 'ring-2 ring-offset-1 ring-primary scale-105 bg-slate-700 text-white border-slate-700'
                  : 'opacity-50 hover:opacity-80 bg-transparent text-slate-600 border-slate-400'
              }`}
            >
              {(value || []).length === 0 && <span className="mr-1">✓</span>}
              Nenhuma
            </button>
            {BANCOS.map((banco) => {
              const item = (value || []).find(i => typeof i === 'object' ? i.banco === banco : i === banco);
              const selected = !!item;
              const colors = BANCO_COLORS[banco] || { bg: "#6B7280", text: "#fff" };
              return (
                <button
                  key={banco}
                  type="button"
                  onClick={() => toggleBanco(banco)}
                  className={`px-3 py-1.5 rounded-full text-sm font-medium border-2 transition-all ${selected ? 'ring-2 ring-offset-1 ring-primary scale-105' : 'opacity-50 hover:opacity-80'}`}
                  style={selected
                    ? { backgroundColor: colors.bg, color: colors.text, borderColor: colors.bg }
                    : { backgroundColor: 'transparent', color: colors.bg, borderColor: colors.bg }
                  }
                >
                  {selected && <span className="mr-1">✓</span>}
                  {banco}
                </button>
              );
            })}
          </div>
          {(value || []).length > 0 && (
            <div className="space-y-2 mt-2">
              {(value || []).map((item) => {
                const banco = typeof item === 'object' ? item.banco : item;
                const valor = typeof item === 'object' ? (item.valor || '') : '';
                const colors = BANCO_COLORS[banco] || { bg: "#6B7280", text: "#fff" };
                return (
                  <div key={banco} className="flex items-center gap-3">
                    <span
                      className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium min-w-[100px] justify-center"
                      style={{ backgroundColor: colors.bg, color: colors.text }}
                    >
                      {banco}
                    </span>
                    <div className="flex-1 relative">
                      <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">€</span>
                      <Input
                        type="number" step="0.01" min="0"
                        placeholder="Valor do crédito (ex: 150000)"
                        value={valor}
                        onChange={(e) => updateBancoValor(banco, e.target.value)}
                        className="pl-7 h-9"
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
          {hint && <FieldHint>{hint}</FieldHint>}
        </div>
      );
    }

    // ── tem_creditos_activos (bank toggle pills) ─────────────────────────
    if (key === "tem_creditos_activos") {
      return (
        <div className={cn("space-y-3", cls)} key={key} style={style}>
          <RequiredLabel htmlFor={key} required={required}>{label}</RequiredLabel>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setFormData(prev => ({ ...prev, tem_creditos_activos: [] }))}
              className={`px-3 py-1.5 rounded-full text-sm font-medium border-2 transition-all ${
                (value || []).length === 0
                  ? 'ring-2 ring-offset-1 ring-primary scale-105 bg-slate-700 text-white border-slate-700'
                  : 'opacity-50 hover:opacity-80 bg-transparent text-slate-600 border-slate-400'
              }`}
            >
              {(value || []).length === 0 && <span className="mr-1">✓</span>}
              Nenhuma
            </button>
            {BANCOS.map((banco) => {
              const selected = (value || []).includes(banco);
              const colors = BANCO_COLORS[banco] || { bg: "#6B7280", text: "#fff" };
              return (
                <button
                  key={`contas-${banco}`}
                  type="button"
                  onClick={() => toggleContasAbertas(banco)}
                  className={`px-3 py-1.5 rounded-full text-sm font-medium border-2 transition-all ${selected ? 'ring-2 ring-offset-1 ring-primary scale-105' : 'opacity-50 hover:opacity-80'}`}
                  style={selected
                    ? { backgroundColor: colors.bg, color: colors.text, borderColor: colors.bg }
                    : { backgroundColor: 'transparent', color: colors.bg, borderColor: colors.bg }
                  }
                >
                  {selected && <span className="mr-1">✓</span>}
                  {banco}
                </button>
              );
            })}
          </div>
          {hint && <FieldHint>{hint}</FieldHint>}
        </div>
      );
    }

    // ── bancos_simulacoes (bank toggle pills) ───────────────────────────
    if (key === "bancos_simulacoes") {
      return (
        <div className={cn("space-y-3", cls)} key={key} style={style}>
          <Label htmlFor={key}>{label}</Label>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setFormData(prev => ({ ...prev, bancos_simulacoes: [] }))}
              className={`px-3 py-1.5 rounded-full text-sm font-medium border-2 transition-all ${
                (value || []).length === 0
                  ? 'ring-2 ring-offset-1 ring-primary scale-105 bg-slate-700 text-white border-slate-700'
                  : 'opacity-50 hover:opacity-80 bg-transparent text-slate-600 border-slate-400'
              }`}
            >
              {(value || []).length === 0 && <span className="mr-1">✓</span>}
              Nenhuma
            </button>
            {BANCOS.map((banco) => {
              const selected = (value || []).includes(banco);
              const colors = BANCO_COLORS[banco] || { bg: "#6B7280", text: "#fff" };
              return (
                <button
                  key={`sim-${banco}`}
                  type="button"
                  onClick={() => toggleBancoSimulacoes(banco)}
                  className={`px-3 py-1.5 rounded-full text-sm font-medium border-2 transition-all ${selected ? 'ring-2 ring-offset-1 ring-primary scale-105' : 'opacity-50 hover:opacity-80'}`}
                  style={selected
                    ? { backgroundColor: colors.bg, color: colors.text, borderColor: colors.bg }
                    : { backgroundColor: 'transparent', color: colors.bg, borderColor: colors.bg }
                  }
                >
                  {selected && <span className="mr-1">✓</span>}
                  {banco}
                </button>
              );
            })}
          </div>
          {hint && <FieldHint>{hint}</FieldHint>}
        </div>
      );
    }

    // ── consent_data / consent_contact (styled consent checkboxes) ───────
    if (key === "consent_data" || key === "consent_contact") {
      const consentLabel = key === "consent_data"
        ? "Autorizo o tratamento dos meus dados pessoais para análise do meu pedido de crédito/imobiliário, nos termos do RGPD. *"
        : "Aceito ser contactado pela equipa para dar seguimento ao meu processo. *";
      return (
        <div className="flex items-start space-x-3" key={key} style={style}>
          <Checkbox
            id={key}
            checked={!!value}
            onCheckedChange={(checked) => updateField(key, checked)}
          />
          <Label htmlFor={key} className="text-sm leading-relaxed cursor-pointer">
            {label !== key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
              ? label
              : consentLabel}
          </Label>
        </div>
      );
    }

    // ── outras_caracteristicas (conditional text, rendered when visible) ─
    if (key === "outras_caracteristicas") {
      return (
        <div className={cn("space-y-2", cls)} key={key} style={style}>
          <Label htmlFor={key}>{label}</Label>
          <Input
            id={key} name={key}
            value={value || ""}
            onChange={(e) => updateField(key, e.target.value)}
            placeholder="Especifique outras características"
          />
        </div>
      );
    }

    // ── Textarea fields ─────────────────────────────────────────────────
    if (key === "caracteristicas_imovel" || key === "outras_informacoes") {
      return (
        <div className={cn("space-y-2", cls)} key={key} style={style}>
          <Label htmlFor={key}>{label}</Label>
          <Textarea
            id={key} name={key}
            value={value || ""}
            onChange={(e) => updateField(key, e.target.value)}
            placeholder={hint || ""}
            rows={key === "outras_informacoes" ? 3 : 2}
          />
        </div>
      );
    }

    // ── DEFAULT: Generic rendering via DynamicFormField ──────────────────
    // This handles text, email, tel, number, date, select, checkbox, radio, textarea
    // for all fields NOT matched above (including sexo, profissao, codigo_postal,
    // titular2_* fields, and any custom fields from the admin config)

    return (
      <div style={style} key={key} className={cls || undefined}>
        <DynamicFormField
          field={{
            ...field,
            label: label,
            hint: hint,
          }}
          value={value}
          onChange={updateField}
          error={error}
          className={cls || undefined}
        />
      </div>
    );
  }, [formData, fieldErrors, updateField, setFormData, toggleCaracteristica, toggleBanco, updateBancoValor, toggleContasAbertas, toggleBancoSimulacoes, checkDependsOn, allFieldsConfig]);

  // Validação de NIF português
  const validateNIF = (nif) => {
    if (!nif) return { valid: false, message: "NIF é obrigatório" };
    const cleanNif = nif.replace(/[^\d]/g, '');
    if (cleanNif.length !== 9) return { valid: false, message: "NIF deve ter 9 dígitos" };
    if (!/^\d{9}$/.test(cleanNif)) return { valid: false, message: "NIF deve conter apenas números" };
    
    // Validar checksum
    const digits = cleanNif.split('').map(Number);
    const weights = [9, 8, 7, 6, 5, 4, 3, 2];
    const sum = digits.slice(0, 8).reduce((acc, d, i) => acc + d * weights[i], 0);
    const remainder = sum % 11;
    const checkDigit = remainder > 1 ? 11 - remainder : 0;
    
    if (checkDigit !== digits[8]) {
      return { valid: false, message: "NIF inválido (dígito de controlo incorreto)" };
    }
    return { valid: true };
  };

  // Validação de email
  const validateEmail = (email) => {
    if (!email) return { valid: false, message: "Email é obrigatório" };
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) return { valid: false, message: "Email inválido" };
    return { valid: true };
  };

  // Validação de telefone
  const validatePhone = (phone) => {
    if (!phone) return { valid: false, message: "Telefone é obrigatório" };
    const cleanPhone = phone.replace(/[^\d+]/g, '');
    if (cleanPhone.length < 9) return { valid: false, message: "Telefone deve ter pelo menos 9 dígitos" };
    return { valid: true };
  };

  // Validação completa do formulário
  const validateForm = () => {
    const errors = [];

    // Validações obrigatórias
    if (!formData.name || formData.name.trim().length < 2) {
      errors.push("Nome completo é obrigatório (mínimo 2 caracteres)");
    }

    const emailCheck = validateEmail(formData.email);
    if (!emailCheck.valid) errors.push(emailCheck.message);

    const phoneCheck = validatePhone(formData.phone);
    if (!phoneCheck.valid) errors.push(phoneCheck.message);

    const nifCheck = validateNIF(formData.nif);
    if (!nifCheck.valid) errors.push(nifCheck.message);

    // Validar titular 2 se aplicável
    if (formData.compra_tipo === "outra_pessoa") {
      if (!formData.titular2_name || formData.titular2_name.trim().length < 2) {
        errors.push("Nome do 2º titular é obrigatório");
      }
      if (formData.titular2_nif) {
        const nif2Check = validateNIF(formData.titular2_nif);
        if (!nif2Check.valid) errors.push(`2º Titular: ${nif2Check.message}`);
      }
      if (formData.titular2_email) {
        const email2Check = validateEmail(formData.titular2_email);
        if (!email2Check.valid) errors.push(`2º Titular: ${email2Check.message}`);
      }
    }

    return errors;
  };

  const handleSubmit = async () => {
    // Validar formulário antes de submeter
    const validationErrors = validateForm();
    if (validationErrors.length > 0) {
      validationErrors.forEach(err => toast.error(err));
      // Reportar erros de validação ao Sentry para análise de friction
      Sentry.withScope((scope) => {
        scope.setLevel('info');
        scope.setTransactionName('form-validation');
        scope.setExtra('step', step);
        scope.setExtra('errors', validationErrors);
        scope.setExtra('formData_preview', {
          name: formData.name,
          email: formData.email,
          phone: formData.phone,
          nif: formData.nif ? '***' : null,
          compra_tipo: formData.compra_tipo,
          titular2_name: formData.titular2_name,
        });
        Sentry.captureMessage(`Formulário: ${validationErrors.length} erro(s) de validação`);
      });
      return;
    }

    if (!formData.consent_data || !formData.consent_contact) {
      toast.error("Por favor, aceite os termos para continuar");
      return;
    }

    setLoading(true);
    setBlockedMessage(null);

    try {
      const response = await axios.post(`${API_URL}/public/client-registration`, {
        name: formData.name,
        email: formData.email,
        phone: formData.phone,
        process_type: "ambos",
        personal_data: {
          nif: formData.nif,
          niss: formData.niss,
          documento_id: formData.documento_id,
          data_validade_cc: formData.data_validade_cc || null,
          naturalidade: formData.naturalidade,
          nacionalidade: formData.nacionalidade,
          morada_fiscal: formData.morada_fiscal,
          birth_date: formData.birth_date,
          estado_civil: formData.estado_civil,
          compra_tipo: formData.compra_tipo,
          menor_35_anos: formData.menor_35_anos,
          sexo: formData.sexo || null,
          profissao: formData.profissao || null,
          codigo_postal: formData.codigo_postal || null,
        },
        titular2_data: formData.compra_tipo === "outra_pessoa" ? {
          name: formData.titular2_name,
          email: formData.titular2_email,
          nif: formData.titular2_nif,
          documento_id: formData.titular2_documento_id,
          naturalidade: formData.titular2_naturalidade,
          nacionalidade: formData.titular2_nacionalidade,
          phone: formData.titular2_phone,
          morada_fiscal: formData.titular2_morada_fiscal,
          birth_date: formData.titular2_birth_date,
          estado_civil: formData.titular2_estado_civil,
        } : null,
        real_estate_data: {
          tipo_imovel: formData.tipo_imovel,
          num_quartos: formData.num_quartos,
          localizacao: formData.localizacao,
          caracteristicas: formData.caracteristicas,
          outras_caracteristicas: formData.outras_caracteristicas,
          outras_informacoes: formData.outras_informacoes,
          // Novos campos
          area_pretendida: formData.area_pretendida || null,
          valor_maximo_imovel: formData.valor_maximo_imovel || null,
          finalidade: formData.finalidade || null,
          ja_tem_casa_escolhida: formData.ja_tem_casa_escolhida || false,
          ja_tem_imovel: formData.ja_tem_casa_escolhida || false,  // Alias for ProcessDetails compatibility
          has_property: formData.ja_tem_casa_escolhida || false,   // Alias for ProcessDetails compatibility
          proprietario_nome: formData.proprietario_nome || null,
          proprietario_contacto: formData.proprietario_contacto || null,
          caracteristicas_imovel: formData.caracteristicas_imovel || null,
          // Campos de refinanciamento
          valor_transferencia: formData.valor_transferencia || null,
          valor_extra: formData.valor_extra || null,
          prazo_pretendido: formData.prazo_pretendido || null,
        },
        financial_data: {
          acesso_portal_financas: formData.acesso_portal_financas,
          chave_movel_digital: formData.chave_movel_digital,
          renda_habitacao_atual: formData.renda_habitacao_atual ? parseFloat(formData.renda_habitacao_atual) : null,
          precisa_vender_casa: formData.precisa_vender_casa,
          efetivo: formData.efetivo,
          fiador: formData.fiador,
          monthly_income: formData.salario_liquido ? parseFloat(formData.salario_liquido) : null,
          rendimento_mensal: formData.salario_liquido ? parseFloat(formData.salario_liquido) : null,  // Alias for ProcessDetails
          rendimento_anual: formData.salario_liquido ? parseFloat(formData.salario_liquido) * 12 : null,  // Calculated from monthly
          salario_liquido: formData.salario_liquido ? parseFloat(formData.salario_liquido) : null,  // Alias
          bancos_creditos: formData.bancos_creditos && formData.bancos_creditos.length > 0
            ? formData.bancos_creditos.map(item => ({
                banco: typeof item === 'object' ? item.banco : item,
                valor: typeof item === 'object' && item.valor ? parseFloat(item.valor) : null,
              }))
            : null,
          bancos_simulacoes: formData.bancos_simulacoes,
          tempo_restante_credito: formData.tempo_restante_credito || null,
          capital_proprio: formData.capital_proprio ? parseFloat(formData.capital_proprio) : null,
          valor_financiado: formData.valor_financiado,
          // Contas abertas (Créditos e Capital) — lista de bancos
          tem_creditos_activos: formData.tem_creditos_activos && formData.tem_creditos_activos.length > 0 ? formData.tem_creditos_activos : null,
          // Campos de emprego
          employment_type: formData.employment_type,
          tipo_contrato: formData.employment_type,  // Alias for ProcessDetails backward-compat
          employment_duration: formData.employment_duration,
          antiguidade_emprego: formData.employment_duration,  // Alias for ProcessDetails backward-compat
          employer_name: formData.employer_name,
          empresa: formData.employer_name,  // Alias for ProcessDetails backward-compat
          employer_nif: formData.employer_nif,
          trabalha_estrangeiro: formData.trabalha_estrangeiro,
        },
        // Campos personalizados
        custom_fields: customFields.length > 0 ? customFields.reduce((acc, f) => {
          if (formData[f.field_key] !== undefined && formData[f.field_key] !== "") {
            acc[f.field_key] = formData[f.field_key];
          }
          return acc;
        }, {}) : null,
      });

      // Verificar se o registo foi bloqueado por duplicado
      if (response.data.blocked) {
        setBlockedMessage(response.data.message);
        toast.info(response.data.message);
        // Reportar duplicado ao Sentry
        Sentry.withScope((scope) => {
          scope.setLevel('info');
          scope.setTransactionName('form-duplicate');
          scope.setTag('duplicate_reason', response.data.reason);
          scope.setExtra('email', formData.email);
          scope.setExtra('nif', formData.nif ? '***' : null);
          Sentry.captureMessage(`Registo bloqueado: duplicado (${response.data.reason})`);
        });
      } else {
        // Limpar rascunho após submissão com sucesso
        clearDraft();
        setSubmitted(true);
        toast.success("Registo enviado com sucesso!");
      }
    } catch (error) {
      console.error("Error submitting form:", error);
      // Tratar diferentes formatos de erro do backend
      let errorMessage = "Erro ao enviar registo";
      let statusCode = null;
      if (error.response?.data?.detail) {
        statusCode = error.response?.status;
        const detail = error.response.data.detail;
        if (typeof detail === 'string') {
          errorMessage = detail;
        } else if (Array.isArray(detail)) {
          // Erro de validação Pydantic (lista de erros)
          errorMessage = detail.map(err => err.msg || err.message || JSON.stringify(err)).join(', ');
        } else if (typeof detail === 'object') {
          errorMessage = detail.msg || detail.message || JSON.stringify(detail);
        }
      }
      toast.error(errorMessage);
      // Reportar erro de submissão ao Sentry
      Sentry.withScope((scope) => {
        scope.setLevel(statusCode >= 500 ? 'error' : 'warning');
        scope.setTransactionName('form-submission');
        scope.setExtra('statusCode', statusCode);
        scope.setExtra('errorMessage', errorMessage);
        scope.setExtra('step', step);
        scope.setExtra('formData_preview', {
          name: formData.name,
          email: formData.email,
          phone: formData.phone,
          nif: formData.nif ? '***' : null,
          compra_tipo: formData.compra_tipo,
          process_type: formData.process_type,
        });
        if (error.response) {
          scope.setExtra('responseData', error.response.data);
        }
        Sentry.captureException(error);
      });
    } finally {
      setLoading(false);
    }
  };

  const renderStepIndicator = () => (
    <div className="flex items-center justify-center mb-8 flex-wrap gap-2">
      {[1, 2, 3, 4, 5, 6].map((s) => (
        <div key={s} className="flex items-center">
          <div
            className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-colors
              ${step >= s ? "bg-teal-600 text-white" : "bg-muted text-muted-foreground"}`}
          >
            {step > s ? <Check className="h-4 w-4" /> : s}
          </div>
          {s < 6 && <div className={`w-8 md:w-12 h-0.5 ${step > s ? "bg-teal-600" : "bg-muted"}`} />}
        </div>
      ))}
    </div>
  );

  // Step 1: Dados Pessoais - Titular (dynamic from allFieldsConfig)
  const renderStep1 = () => {
    const stepFields = getFieldsForStep(1);

    return (
      <div className="space-y-6">
        <div className="text-center mb-6">
          <User className="h-10 w-10 mx-auto mb-2 text-primary" />
          <h2 className="text-xl font-semibold mb-2 text-foreground">Dados Pessoais - Titular</h2>
          <p className="text-muted-foreground">Informações do titular principal</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {stepFields.map(field => renderDynamicField(field))}
        </div>
      </div>
    );
  };

  // Step 2: Dados do 2º Titular (dynamic from allFieldsConfig, conditional on compra_tipo)
  const renderStep2 = () => {
    const stepFields = getFieldsForStep(2);

    return (
      <div className="space-y-6">
        <div className="text-center mb-6">
          <Users className="h-10 w-10 mx-auto mb-2 text-primary" />
          <h2 className="text-xl font-semibold mb-2">Dados do 2º Titular</h2>
          <p className="text-muted-foreground">
            {stepFields.length > 0
              ? "Preencha os dados do segundo titular"
              : "Não aplicável - compra individual"}
          </p>
        </div>

        {stepFields.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {stepFields.map(field => renderDynamicField(field))}
          </div>
        ) : (
          <div className="text-center py-8 bg-muted/50 rounded-lg">
            <p className="text-muted-foreground">
              Selecione "Com outra pessoa" no passo anterior para preencher os dados do 2º titular.
            </p>
          </div>
        )}
      </div>
    );
  };

  // Step 3: Imóvel Pretendido (dynamic from allFieldsConfig)
  const renderStep3 = () => {
    const stepFields = getFieldsForStep(3);

    return (
      <div className="space-y-6">
        <div className="text-center mb-6">
          <Home className="h-10 w-10 mx-auto mb-2 text-primary" />
          <h2 className="text-xl font-semibold mb-2">Tipo de Pedido</h2>
          <p className="text-muted-foreground">Indique a finalidade do seu pedido</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {stepFields.map(field => renderDynamicField(field))}
        </div>
      </div>
    );
  };

  // Step 4: Situação Financeira (dynamic from allFieldsConfig)
  const renderStep4 = () => {
    const stepFields = getFieldsForStep(4);

    return (
      <div className="space-y-6">
        <div className="text-center mb-6">
          <Briefcase className="h-10 w-10 mx-auto mb-2 text-amber-500" />
          <h2 className="text-xl font-semibold mb-2 text-blue-950">Situação Financeira</h2>
          <p className="text-muted-foreground">Informações sobre a sua situação financeira</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {stepFields.map(field => renderDynamicField(field))}
        </div>
      </div>
    );
  };

  // Step 5: Bancos e Capital (dynamic from allFieldsConfig)
  const renderStep5 = () => {
    const stepFields = getFieldsForStep(5);

    return (
      <div className="space-y-6">
        <div className="text-center mb-6">
          <CreditCard className="h-10 w-10 mx-auto mb-2 text-primary" />
          <h2 className="text-xl font-semibold mb-2">Créditos e Capital</h2>
          <p className="text-muted-foreground">Informações sobre créditos e capital disponível</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {stepFields.map(field => renderDynamicField(field))}
        </div>
      </div>
    );
  };

  // Step 6: Confirmação
  const renderStep6 = () => (
    <div className="space-y-6">
      <div className="text-center mb-6">
        <Check className="h-10 w-10 mx-auto mb-2 text-primary" />
        <h2 className="text-xl font-semibold mb-2">Confirmação</h2>
        <p className="text-muted-foreground">Reveja os seus dados e confirme o registo</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card className="border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Dados Pessoais</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <p><strong>Nome:</strong> {formData.name}</p>
            <p><strong>Email:</strong> {formData.email}</p>
            <p><strong>Telemóvel:</strong> {formData.phone}</p>
            <p><strong>NIF:</strong> {formData.nif}</p>
            <p><strong>Estado Civil:</strong> {ESTADOS_CIVIS.find(e => e.value === formData.estado_civil)?.label || "-"}</p>
          </CardContent>
        </Card>
        
        <Card className="border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Imóvel Pretendido</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <p><strong>Tipo:</strong> {TIPOS_IMOVEL.find(t => t.value === formData.tipo_imovel)?.label || "-"}</p>
            <p><strong>Quartos:</strong> {formData.num_quartos || "-"}</p>
            <p><strong>Localização:</strong> {formData.localizacao || "-"}</p>
            <p><strong>Características:</strong> {(formData.caracteristicas || []).length > 0 ? formData.caracteristicas.join(", ") : "-"}</p>
          </CardContent>
        </Card>
        
        <Card className="border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Situação Financeira</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <p><strong>Salário líquido:</strong> {formData.salario_liquido ? `€${formData.salario_liquido}` : "-"}</p>
            <p><strong>Capital próprio:</strong> {formData.capital_proprio ? `€${formData.capital_proprio}` : "-"}</p>
            <p><strong>Valor a financiar:</strong> {formData.valor_financiado || "-"}</p>
            <p><strong>Efetivo:</strong> {formData.efetivo === "sim" ? "Sim" : formData.efetivo === "nao" ? "Não" : "-"}</p>
            <p><strong>Trabalha no Estrangeiro:</strong> {formData.trabalha_estrangeiro === "sim" ? "Sim" : formData.trabalha_estrangeiro === "nao" ? "Não" : "-"}</p>
          </CardContent>
        </Card>
        
        <Card className="border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Créditos Ativos</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <p><strong>Contas abertas:</strong> {formData.tem_creditos_activos === "sim" ? <span className="text-orange-600">Sim</span> : formData.tem_creditos_activos === "nao" ? <span className="text-green-600">Não</span> : "-"}</p>
            {formData.tem_creditos_activos === "sim" && formData.valor_creditos_activos && (
              <p><strong>Valor total em aberto:</strong> €{formData.valor_creditos_activos}</p>
            )}
            <p><strong>Bancos:</strong> {(formData.bancos_creditos || []).length > 0 ? formData.bancos_creditos.join(", ") : "Nenhum banco selecionado"}</p>
          </CardContent>
        </Card>
        
        <Card className="border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Simulações de Crédito</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <p>{(formData.bancos_simulacoes || []).length > 0 ? formData.bancos_simulacoes.join(", ") : "Nenhuma simulação efetuada"}</p>
          </CardContent>
        </Card>
        
        {formData.finalidade === "refinanciamento" && formData.tempo_restante_credito && (
          <Card className="border-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Tempo Restante do Crédito</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-sm">
              <p>{formData.tempo_restante_credito === "menos_1_ano" ? "Menos de 1 ano" :
                  formData.tempo_restante_credito === "1_5_anos" ? "1 a 5 anos" :
                  formData.tempo_restante_credito === "5_10_anos" ? "5 a 10 anos" :
                  formData.tempo_restante_credito === "10_15_anos" ? "10 a 15 anos" :
                  formData.tempo_restante_credito === "15_20_anos" ? "15 a 20 anos" :
                  formData.tempo_restante_credito === "mais_20_anos" ? "Mais de 20 anos" : "-"}</p>
            </CardContent>
          </Card>
        )}
      </div>

      <div className="space-y-4 pt-4 border-t" style={getFieldStyle("consent_data")}>
        <div className="flex items-start space-x-3">
          <Checkbox
            id="consent_data"
            checked={formData.consent_data}
            onCheckedChange={(checked) => updateField("consent_data", checked)}
            data-testid="consent-data"
          />
          <Label htmlFor="consent_data" className="text-sm leading-relaxed cursor-pointer">
            {getFieldLabel("consent_data", "Autorizo o tratamento dos meus dados pessoais para análise do meu pedido de crédito/imobiliário, nos termos do RGPD. *")}
          </Label>
        </div>
        <div className="flex items-start space-x-3">
          <Checkbox
            id="consent_contact"
            checked={formData.consent_contact}
            onCheckedChange={(checked) => updateField("consent_contact", checked)}
            data-testid="consent-contact"
          />
          <Label htmlFor="consent_contact" className="text-sm leading-relaxed cursor-pointer">
            {getFieldLabel("consent_contact", "Aceito ser contactado pela equipa para dar seguimento ao meu processo. *")}
          </Label>
        </div>
      </div>
    </div>
  );

  // Render custom steps (step > 6) dynamically based on their fields
  const renderDynamicStep = (stepNum) => {
    const stepFields = getFieldsForStep(stepNum);
    // Get step label from stepConfig or default
    const labels = (stepConfig && stepConfig[String(stepNum)]?.label) ? {} : {};
    const customLabel = stepLabels[String(stepNum)] || `Passo ${stepNum}`;
    // Also check if stepConfig has a label for backward compat
    const configLabel = typeof stepConfig[String(stepNum)] === 'object' && stepConfig[String(stepNum)]?.label ? stepConfig[String(stepNum)].label : null;

    return (
      <div className="space-y-6">
        <div className="text-center mb-6">
          <ClipboardList className="h-10 w-10 mx-auto mb-2 text-primary" />
          <h2 className="text-xl font-semibold mb-2">{configLabel || customLabel}</h2>
        </div>
        {stepFields.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <p>Nenhum campo disponível neste passo.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {stepFields.map(field => (
              <div key={field.field_key}>
                {renderDynamicField(field)}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  const renderSuccessMessage = () => (
    <div className="text-center py-12">
      <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
        <Check className="h-8 w-8 text-green-600" />
      </div>
      <h2 className="text-2xl font-semibold mb-2">Registo Enviado com Sucesso!</h2>
      <p className="text-muted-foreground mb-6">
        Obrigado pelo seu interesse. A nossa equipa irá analisar o seu pedido e entrará em contacto consigo brevemente.
      </p>
      <Button onClick={() => window.location.reload()}>Novo Registo</Button>
    </div>
  );

  const renderBlockedMessage = () => (
    <div className="text-center py-12">
      <div className="w-16 h-16 bg-amber-100 rounded-full flex items-center justify-center mx-auto mb-4">
        <Info className="h-8 w-8 text-amber-600" />
      </div>
      <h2 className="text-2xl font-semibold mb-2 text-amber-700 dark:text-amber-400">Processo Já Existente</h2>
      <p className="text-muted-foreground mb-6 max-w-md mx-auto">
        {blockedMessage}
      </p>
      <div className="space-y-3">
        <p className="text-sm text-muted-foreground">
          Caso tenha dúvidas, pode contactar-nos diretamente:
        </p>
        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <a 
            href="mailto:geral@precisioncredito.pt" 
            className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-teal-600 text-white rounded-md hover:bg-teal-700 transition-colors"
          >
            <HelpCircle className="h-4 w-4" />
            Contactar Precision
          </a>
          <a 
            href="mailto:geral@powerealestate.pt" 
            className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-amber-500 text-white rounded-md hover:bg-amber-600 transition-colors"
          >
            <HelpCircle className="h-4 w-4" />
            Contactar Power RE
          </a>
        </div>
      </div>
    </div>
  );

  // Validação por step com mensagens de erro
  const validateStep = (stepNum) => {
    const errors = [];
    const newFieldErrors = {};

    // ── Quando allFieldsConfig carregou, usar validação dinâmica ──────────
    // Respeita is_visible, is_required e depends_on do config (incluindo BD)
    if (configLoaded && allFieldsConfig && allFieldsConfig.length > 0) {
      const stepFields = allFieldsConfig.filter(f => {
        if (f.step !== stepNum) return false;
        if (f.is_visible === false) return false;
        if (!f.is_required) return false;
        // Check depends_on_all (ALL conditions must be met)
        if (f.depends_on_all && Array.isArray(f.depends_on_all)) {
          return f.depends_on_all.every(cond => checkDependsOn(cond));
        }
        return checkDependsOn(f.depends_on);
      });

      for (const field of stepFields) {
        const key = field.field_key;
        // Checkboxes (multi-select) não bloqueiam
        if (field.field_type === 'checkbox') continue;
        const val = formData[key];
        if (val === undefined || val === null || val === '') {
          const label = customLabelMap[key] || field.label || key;
          errors.push(`${label} é obrigatório`);
          newFieldErrors[key] = `${label} é obrigatório`;
        }
      }

      // ── Validações especiais (NIF, email, telefone, idade) ──────────
      // Estas são validações de FORMATO, não apenas de presença
      if (stepNum === 1) {
        const emailCheck = validateEmail(formData.email);
        if (formData.email && !emailCheck.valid) {
          errors.push(emailCheck.message);
          newFieldErrors.email = emailCheck.message;
        }
        const phoneCheck = validatePhone(formData.phone);
        if (formData.phone && !phoneCheck.valid) {
          errors.push(phoneCheck.message);
          newFieldErrors.phone = phoneCheck.message;
        }
        const nifCheck = validateNIF(formData.nif);
        if (formData.nif && !nifCheck.valid) {
          errors.push(nifCheck.message);
          newFieldErrors.nif = nifCheck.message;
        }
        if (formData.birth_date) {
          const birthDate = new Date(safeDateStr(formData.birth_date));
          const today = new Date();
          let age = today.getFullYear() - birthDate.getFullYear();
          const monthDiff = today.getMonth() - birthDate.getMonth();
          if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birthDate.getDate())) {
            age--;
          }
          if (age < 18) {
            errors.push("O cliente deve ter idade igual ou superior a 18 anos");
            newFieldErrors.birth_date = "O cliente deve ter idade igual ou superior a 18 anos";
          } else if (age > 120) {
            errors.push("Data de nascimento inválida");
            newFieldErrors.birth_date = "Data de nascimento inválida";
          }
        }
      }
      if (stepNum === 2 && formData.compra_tipo === "outra_pessoa") {
        if (formData.titular2_email) {
          const email2Check = validateEmail(formData.titular2_email);
          if (!email2Check.valid) {
            errors.push(`2º Titular: ${email2Check.message}`);
            newFieldErrors.titular2_email = email2Check.message;
          }
        }
        if (formData.titular2_phone) {
          const phone2Check = validatePhone(formData.titular2_phone);
          if (!phone2Check.valid) {
            errors.push(`2º Titular: ${phone2Check.message}`);
            newFieldErrors.titular2_phone = phone2Check.message;
          }
        }
        if (formData.titular2_nif) {
          const nif2Check = validateNIF(formData.titular2_nif);
          if (!nif2Check.valid) {
            errors.push(`2º Titular: ${nif2Check.message}`);
            newFieldErrors.titular2_nif = nif2Check.message;
          }
        }
      }

      return { errors, fieldErrors: newFieldErrors };
    }

    // ── Fallback: config não carregou — não bloquear ───────────────────
    // Enquanto o config carrega, não devemos bloquear o utilizador com
    // validações hardcoded que podem não corresponder à configuração
    // do admin (is_visible, is_required, depends_on).
    // O botão "Seguinte" fica desabilitado visualmente enquanto config carrega.
    //
    // Mantemos apenas validações de FORMATO (não de presença) para campos
    // preenchidos — estas são sempre aplicáveis independentemente do config.
    if (stepNum === 1) {
      if (formData.email) {
        const emailCheck = validateEmail(formData.email);
        if (!emailCheck.valid) {
          errors.push(emailCheck.message);
          newFieldErrors.email = emailCheck.message;
        }
      }
      if (formData.phone) {
        const phoneCheck = validatePhone(formData.phone);
        if (!phoneCheck.valid) {
          errors.push(phoneCheck.message);
          newFieldErrors.phone = phoneCheck.message;
        }
      }
      if (formData.nif) {
        const nifCheck = validateNIF(formData.nif);
        if (!nifCheck.valid) {
          errors.push(nifCheck.message);
          newFieldErrors.nif = nifCheck.message;
        }
      }
      if (formData.birth_date) {
        const birthDate = new Date(safeDateStr(formData.birth_date));
        const today = new Date();
        let age = today.getFullYear() - birthDate.getFullYear();
        const monthDiff = today.getMonth() - birthDate.getMonth();
        if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birthDate.getDate())) {
          age--;
        }
        if (age < 18) {
          errors.push("O cliente deve ter idade igual ou superior a 18 anos");
          newFieldErrors.birth_date = "O cliente deve ter idade igual ou superior a 18 anos";
        } else if (age > 120) {
          errors.push("Data de nascimento inválida");
          newFieldErrors.birth_date = "Data de nascimento inválida";
        }
      }
    }
    if (stepNum === 2 && formData.compra_tipo === "outra_pessoa") {
      if (formData.titular2_email) {
        const email2Check = validateEmail(formData.titular2_email);
        if (!email2Check.valid) {
          errors.push(`2º Titular: ${email2Check.message}`);
          newFieldErrors.titular2_email = email2Check.message;
        }
      }
      if (formData.titular2_phone) {
        const phone2Check = validatePhone(formData.titular2_phone);
        if (!phone2Check.valid) {
          errors.push(`2º Titular: ${phone2Check.message}`);
          newFieldErrors.titular2_phone = phone2Check.message;
        }
      }
      if (formData.titular2_nif) {
        const nif2Check = validateNIF(formData.titular2_nif);
        if (!nif2Check.valid) {
          errors.push(`2º Titular: ${nif2Check.message}`);
          newFieldErrors.titular2_nif = nif2Check.message;
        }
      }
    }

    return { errors, fieldErrors: newFieldErrors };
  };

  const handleNextStep = () => {
    const maxRealStep = maxStepNum;
    if (previewMode) {
      const next = getNextRealStep(step);
      setStep(Math.min(maxRealStep, next));
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }
    const { errors, fieldErrors: newFieldErrors } = validateStep(step);
    
    // Limpar erros anteriores e definir novos
    setFieldErrors(newFieldErrors);
    
    if (errors.length > 0) {
      // Mostrar toast com resumo dos erros
      toast.error(`Por favor corrija ${errors.length} erro(s) antes de continuar`);
      // Scroll para o primeiro campo com erro usando ref ou scoped query (React way)
      const firstErrorField = Object.keys(newFieldErrors)[0];
      if (firstErrorField) {
        // Usar helper que tenta ref primeiro, depois scoped query
        const element = findFieldElement(firstErrorField);
        if (element) {
          element.scrollIntoView({ behavior: 'smooth', block: 'center' });
          element.focus?.();
        }
      }
      return;
    }
    
    // Limpar erros se passou na validação
    setFieldErrors({});
    const next = getNextRealStep(step);
    setStep(Math.min(maxRealStep, next));
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // Função helper para obter erro de um campo específico
  const getFieldError = (fieldName) => fieldErrors[fieldName] || null;

  const canProceed = useCallback(() => {
    if (previewMode) return true;

    // ── Config not loaded yet — don't block, just return true ──────────
    // The "Next" button is visually disabled while config loads (see JSX),
    // so the user can't click it prematurely. Once loaded, the dynamic
    // validation below takes over and respects admin is_visible/is_required.
    if (!configLoaded || !allFieldsConfig || allFieldsConfig.length === 0) {
      return true;
    }

    // ── Dinâmico: usa a configuração do formulário ─────────────────────
    // Só bloqueia em campos que sejam:
    //   1. is_required = true
    //   2. is_visible = true (não escondidos pelo admin)
    //   3. depends_on satisfeito (or depends_on_all ALL satisfied)
    const visibleRequired = allFieldsConfig
      .filter(f => {
        if (f.step !== step || !f.is_required || f.is_visible === false) return false;
        // Check depends_on_all (ALL conditions must be met)
        if (f.depends_on_all && Array.isArray(f.depends_on_all)) {
          return f.depends_on_all.every(cond => checkDependsOn(cond));
        }
        return checkDependsOn(f.depends_on);
      })
      .map(f => f.field_key);

    if (visibleRequired.length === 0) return true;

    return visibleRequired.every(key => {
      // Checkboxes (multi-select) não bloqueiam — o utilizador pode seleccionar "Nenhuma"
      const fieldCfg = fieldConfigMap[key];
      if (fieldCfg && fieldCfg.field_type === 'checkbox') return true;

      const val = formData[key];
      if (val === undefined || val === null || val === '') return false;
      return true;
    });
  }, [previewMode, step, allFieldsConfig, formData, checkDependsOn, fieldConfigMap, configLoaded]);

  if (submitted || blockedMessage) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-amber-50">
        {/* Header com cores da marca */}
        <header className="border-b bg-blue-950 text-white">
          <div className="container mx-auto px-4 py-4">
            <div className="flex items-center gap-3">
              <Building2 className="h-8 w-8 text-amber-400" />
              <h1 className="text-xl font-bold">PowerCell</h1>
            </div>
          </div>
        </header>
        <main className="container mx-auto px-4 py-8">
          <Card className="max-w-4xl mx-auto border-blue-200 shadow-lg">
            <CardContent className="pt-6">
              {blockedMessage ? renderBlockedMessage() : renderSuccessMessage()}
            </CardContent>
          </Card>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-amber-50">
      {/* Header com cores da marca */}
      <header className="border-b bg-blue-950 text-white shadow-md">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Building2 className="h-8 w-8 text-amber-400" />
              <h1 className="text-xl font-bold text-white">PowerCell</h1>
            </div>
            {!previewMode && (
            <a 
              href="/login" 
              className="flex items-center gap-2 text-sm text-amber-400 hover:text-amber-300 font-medium transition-colors"
            >
              <User className="h-4 w-4" />
              <span className="hidden sm:inline">Acesso Colaborador</span>
              <span className="sm:hidden">Login</span>
            </a>
            )}
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-8">
        {previewMode && (
          <div className="max-w-4xl mx-auto mb-4 flex items-center justify-between bg-amber-50 border border-amber-200 rounded-lg px-4 py-3" data-testid="preview-mode-banner">
            <div className="flex items-center gap-2 text-amber-800 text-sm font-medium">
              <Eye className="h-4 w-4" />
              Modo de Pré-visualização - Navegue pelo formulário para acompanhar o cliente
            </div>
            <Button variant="outline" size="sm" onClick={() => navigate('/registos-clientes')} data-testid="preview-back-btn">
              <ArrowLeft className="h-4 w-4 mr-1" />
              Voltar
            </Button>
          </div>
        )}
        <Card className="max-w-4xl mx-auto border-blue-200 shadow-lg">
          <CardHeader className="text-center bg-gradient-to-r from-blue-900 to-blue-800 text-white rounded-t-lg">
            <CardTitle className="text-white text-2xl">Formulário de Registo</CardTitle>
            <CardDescription className="text-blue-100">
              Preencha os seus dados para iniciar o processo de análise de crédito habitação
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-6" ref={formContainerRef}>
            {/* Loading indicator while config loads from backend */}
            {!configLoaded && (
              <div className="flex flex-col items-center justify-center py-12 gap-3 text-muted-foreground">
                <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
                <p className="text-sm">A carregar configuração do formulário...</p>
              </div>
            )}
            {configLoaded && (
            <>
            {/* Progress Bar com percentagem */}
            <FormProgressBar 
              currentStep={realToLogicalStep(step)} 
              totalSteps={totalSteps} 
              completedFields={progress.completed}
              totalFields={progress.total}
            />
            
            {/* Auto-save indicator + Simulate button */}
            {previewMode && (
            <div className="flex justify-between items-center mb-4">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="text-muted-foreground hover:text-violet-600 gap-1.5 text-xs"
                onClick={simulateFill}
                data-testid="simulate-fill-btn"
                title="Preencher todos os campos com dados de teste"
              >
                <FlaskConical className="h-3.5 w-3.5" />
                Simular Preenchimento
              </Button>
              <AutoSaveIndicator lastSaved={lastSaved} isSaving={isSaving} />
            </div>
            )}
            
            {step === 1 && renderStep1()}
            {step === 2 && renderStep2()}
            {step === 3 && renderStep3()}
            {step === 4 && renderStep4()}
            {step === 5 && renderStep5()}
            {step === 6 && renderStep6()}
            {step > 6 && renderDynamicStep(step)}

            <div className="flex justify-between mt-8 pt-6 border-t border-border">
              <Button
                variant="outline"
                onClick={() => {
                  const prev = getPrevRealStep(step);
                  setStep(Math.max(1, prev));
                }}
                disabled={step === 1}
              >
                <ArrowLeft className="mr-2 h-4 w-4" />
                Voltar
              </Button>
              
              {getNextRealStep(step) <= 6 ? (
                <Button
                  onClick={handleNextStep}
                  disabled={!configLoaded || !canProceed()}
                  className="bg-teal-600 hover:bg-teal-700 text-white"
                >
                  Próximo
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              ) : previewMode ? (
                <Button
                  onClick={() => navigate('/registos-clientes')}
                  className="bg-teal-600 hover:bg-teal-700 text-white"
                  data-testid="preview-finish-btn"
                >
                  <Check className="mr-2 h-4 w-4" />
                  Fim da Pré-visualização
                </Button>
              ) : (
                <Button
                  onClick={handleSubmit}
                  disabled={loading || !configLoaded || !canProceed()}
                  className="bg-amber-500 hover:bg-amber-600 text-white"
                >
                  {loading ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      A enviar...
                    </>
                  ) : (
                    <>
                      <Check className="mr-2 h-4 w-4" />
                      Submeter
                    </>
                  )}
                </Button>
              )}
            </div>
            </>
            )}
          </CardContent>
        </Card>
        
        {/* Footer com informação das empresas */}
        <div className="max-w-4xl mx-auto mt-8 text-center text-sm text-muted-foreground">
          <p>
            <span className="font-semibold text-foreground">PowerCell</span> - Consultoria Imobiliária | 
            <span className="font-semibold text-primary ml-1">PowerCell</span> - Intermediação de Crédito
          </p>
        </div>
      </main>
    </div>
  );
}


