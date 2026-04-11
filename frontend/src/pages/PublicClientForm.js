import { useState, useEffect, useCallback, useRef, forwardRef } from "react";
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
import { Checkbox } from "../components/ui/checkbox";
import { Progress } from "../components/ui/progress";
import { Building2, Loader2, ArrowLeft, ArrowRight, Check, User, Briefcase, Home, Users, CreditCard, HelpCircle, Info, Save, Clock, AlertCircle, Eye, FlaskConical, Play } from "lucide-react";
import { toast } from "sonner";
import axios from "axios";
import * as Sentry from "@sentry/react";
import { cn } from "../lib/utils";

const API_URL = process.env.REACT_APP_BACKEND_URL + "/api";

// Chave para localStorage
const DRAFT_STORAGE_KEY = "public_client_form_draft";
const DRAFT_TIMESTAMP_KEY = "public_client_form_draft_timestamp";

// Helper component for field hints
const FieldHint = ({ children }) => (
  <p className="text-xs text-muted-foreground mt-1 flex items-start gap-1">
    <Info className="h-3 w-3 mt-0.5 flex-shrink-0" />
    <span>{children}</span>
  </p>
);

// Helper component for field errors
const FieldError = ({ children }) => (
  <p className="text-xs text-red-600 mt-1 flex items-start gap-1 font-medium">
    <AlertCircle className="h-3 w-3 mt-0.5 flex-shrink-0" />
    <span>{children}</span>
  </p>
);

// Helper for required field labels
const RequiredLabel = ({ htmlFor, children }) => (
  <Label htmlFor={htmlFor}>
    {children} <span className="text-red-600 font-semibold">*</span>
    <span className="text-red-600 text-[10px] ml-1 font-medium">(obrigatório)</span>
  </Label>
);

// Validated Input Component - com forwardRef para suportar refs
const ValidatedInput = forwardRef(({ 
  error, 
  required,
  className,
  ...props 
}, ref) => (
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
));
ValidatedInput.displayName = 'ValidatedInput';

// Validated Select Wrapper
const ValidatedSelect = ({ 
  error, 
  children,
  triggerClassName,
  ...props 
}) => (
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

// Progress Bar Component com percentagem
const FormProgressBar = ({ currentStep, totalSteps, completedFields, totalFields }) => {
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
};

// Auto-save indicator
const AutoSaveIndicator = ({ lastSaved, isSaving }) => {
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
};

const ESTADOS_CIVIS = [
  { value: "solteiro", label: "Solteiro/a" },
  { value: "divorciado", label: "Divorciado/a" },
  { value: "viuvo", label: "Viúvo/a" },
  { value: "casado_adquiridos", label: "Casado/a: Comunhão de Adquiridos" },
  { value: "casado_geral", label: "Casado/a: Comunhão Geral de Bens" },
  { value: "casado_separacao", label: "Casado/a: Separação de Bens" },
  { value: "outro", label: "Outro" },
];

const TIPOS_IMOVEL = [
  { value: "apartamento", label: "Apartamento" },
  { value: "moradia", label: "Moradia" },
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

// Campos obrigatórios para calcular progresso
const REQUIRED_FIELDS = [
  "name", "email", "nif", "phone", "birth_date", "estado_civil",
  "tipo_imovel", "localizacao", "profissao", "tipo_contrato"
];

// Dados de simulação para testar o formulário
const MOCK_DATA = {
  // Step 1 - Dados Pessoais
  name: "João Pedro da Silva Santos",
  email: "joao.santos.teste@email.pt",
  phone: "+351912345678",
  nif: "291654738", // NIF válido (checksum OK)
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
  acesso_portal_financas: "sim",
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

const PublicClientForm = ({ previewMode = false }) => {
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
        return { data: parsed, timestamp: timestamp ? new Date(timestamp) : null };
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
  const simulateFill = useCallback(() => {
    setFormData(prev => ({ ...prev, ...MOCK_DATA }));
    setStep(1);
    setFieldErrors({});
    clearDraft();
    toast.success("Formulário preenchido com dados de teste — navegue pelos passos para rever", {
      duration: 4000,
    });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [clearDraft]);

  const [formData, setFormData] = useState(() => {
    const defaults = {
      // Dados Pessoais - Titular
      name: "",
      email: "",
      nif: "",
      documento_id: "",
      data_validade_cc: "",
      naturalidade: "",
      nacionalidade: "Portuguesa",
      phone: "",
      morada_fiscal: "",
      birth_date: "",
      estado_civil: "",
      compra_tipo: "individual",
      menor_35_anos: false,
      
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

  // Calcular campos preenchidos para progresso
  const calculateProgress = useCallback(() => {
    let filled = 0;
    REQUIRED_FIELDS.forEach(field => {
      if (formData[field] && formData[field] !== "") {
        filled++;
      }
    });
    return { completed: filled, total: REQUIRED_FIELDS.length };
  }, [formData]);

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

  // Carregar campos personalizados do backend
  const [customFields, setCustomFields] = useState([]);
  useEffect(() => {
    const fetchCustomFields = async () => {
      try {
        const res = await axios.get(`${API_URL}/public/form-config`);
        setCustomFields(res.data.custom_fields || []);
      } catch {
        // Endpoint pode não existir em deployments mais antigos - formulário funciona sem campos personalizados
      }
    };
    fetchCustomFields();
  }, []);

  // Renderizar um campo personalizado dinâmico
  const renderCustomField = (field) => {
    const value = formData[field.field_key] || "";
    const updateCustom = (v) => updateField(field.field_key, v);

    return (
      <div key={field.field_key} className="space-y-2" data-testid={`custom-field-${field.field_key}`}>
        {field.is_required ? (
          <RequiredLabel htmlFor={field.field_key}>{field.label}</RequiredLabel>
        ) : (
          <Label htmlFor={field.field_key}>{field.label}</Label>
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
            value={value}
            onChange={(e) => updateCustom(e.target.value)}
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
    return customFields.filter(f => f.step === stepNum);
  };

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
        scope.setExtra('step', currentStep);
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
          documento_id: formData.documento_id,
          data_validade_cc: formData.data_validade_cc || null,
          naturalidade: formData.naturalidade,
          nacionalidade: formData.nacionalidade,
          morada_fiscal: formData.morada_fiscal,
          birth_date: formData.birth_date,
          estado_civil: formData.estado_civil,
          compra_tipo: formData.compra_tipo,
          menor_35_anos: formData.menor_35_anos,
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
          proprietario_nome: formData.proprietario_nome || null,
          proprietario_contacto: formData.proprietario_contacto || null,
          caracteristicas_imovel: formData.caracteristicas_imovel || null,
        },
        financial_data: {
          acesso_portal_financas: formData.acesso_portal_financas,
          chave_movel_digital: formData.chave_movel_digital,
          renda_habitacao_atual: formData.renda_habitacao_atual ? parseFloat(formData.renda_habitacao_atual) : null,
          precisa_vender_casa: formData.precisa_vender_casa,
          efetivo: formData.efetivo,
          fiador: formData.fiador,
          monthly_income: formData.salario_liquido ? parseFloat(formData.salario_liquido) : null,
          bancos_creditos: formData.bancos_creditos,
          bancos_simulacoes: formData.bancos_simulacoes,
          tempo_restante_credito: formData.tempo_restante_credito || null,
          capital_proprio: formData.capital_proprio ? parseFloat(formData.capital_proprio) : null,
          valor_financiado: formData.valor_financiado,
          // Campos de emprego
          employment_type: formData.employment_type,
          employment_duration: formData.employment_duration,
          employer_name: formData.employer_name,
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
        scope.setExtra('step', currentStep);
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
    setFormData(prev => ({
      ...prev,
      bancos_creditos: (prev.bancos_creditos || []).includes(banco)
        ? prev.bancos_creditos.filter(b => b !== banco)
        : [...(prev.bancos_creditos || []), banco]
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

  // Step 1: Dados Pessoais - Titular
  const renderStep1 = () => (
    <div className="space-y-6">
      <div className="text-center mb-6">
        <User className="h-10 w-10 mx-auto mb-2 text-primary" />
        <h2 className="text-xl font-semibold mb-2 text-foreground">Dados Pessoais - Titular</h2>
        <p className="text-muted-foreground">Informações do titular principal</p>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-2 md:col-span-2">
          <RequiredLabel htmlFor="name">Nome completo</RequiredLabel>
          <Input
            id="name"
            name="name"
            value={formData.name}
            onChange={(e) => updateField("name", e.target.value)}
            placeholder="Nome completo"
            required
            data-testid="client-name"
            className={cn(fieldErrors.name && "border-red-500 focus-visible:ring-red-500 bg-red-50")}
          />
          {fieldErrors.name && <FieldError>{fieldErrors.name}</FieldError>}
        </div>
        
        <div className="space-y-2">
          <RequiredLabel htmlFor="email">Email</RequiredLabel>
          <Input
            id="email"
            name="email"
            type="email"
            value={formData.email}
            onChange={(e) => updateField("email", e.target.value)}
            placeholder="email@exemplo.pt"
            required
            data-testid="client-email"
            className={cn(fieldErrors.email && "border-red-500 focus-visible:ring-red-500 bg-red-50")}
          />
          {fieldErrors.email && <FieldError>{fieldErrors.email}</FieldError>}
          <FieldHint>Utilizaremos este email para comunicar consigo sobre o seu processo.</FieldHint>
        </div>
        
        <div className="space-y-2">
          <RequiredLabel htmlFor="phone">Telemóvel</RequiredLabel>
          <Input
            id="phone"
            name="phone"
            type="tel"
            value={formData.phone}
            onChange={(e) => updateField("phone", e.target.value)}
            placeholder="+351 912 345 678"
            required
            data-testid="client-phone"
            className={cn(fieldErrors.phone && "border-red-500 focus-visible:ring-red-500 bg-red-50")}
          />
          {fieldErrors.phone && <FieldError>{fieldErrors.phone}</FieldError>}
          <FieldHint>Número de contacto direto para agendar visitas e reuniões.</FieldHint>
        </div>
        
        <div className="space-y-2">
          <RequiredLabel htmlFor="nif">NIF</RequiredLabel>
          <Input
            id="nif"
            name="nif"
            type="text"
            value={formData.nif}
            onChange={(e) => updateField("nif", e.target.value.replace(/\D/g, ""))}
            placeholder="123456789"
            maxLength={9}
            required
            data-testid="client-nif"
            className={cn(fieldErrors.nif && "border-red-500 focus-visible:ring-red-500 bg-red-50")}
          />
          {fieldErrors.nif && <FieldError>{fieldErrors.nif}</FieldError>}
          <FieldHint>Número de Identificação Fiscal - 9 dígitos, encontra-se no Cartão de Cidadão.</FieldHint>
        </div>
        
        <div className="space-y-2">
          <RequiredLabel htmlFor="documento_id">Cartão de Cidadão/Passaporte</RequiredLabel>
          <Input
            id="documento_id"
            name="documento_id"
            value={formData.documento_id}
            onChange={(e) => updateField("documento_id", e.target.value)}
            placeholder="Número do documento"
            required
            data-testid="client-documento"
            className={cn(fieldErrors.documento_id && "border-red-500 focus-visible:ring-red-500 bg-red-50")}
          />
          {fieldErrors.documento_id && <FieldError>{fieldErrors.documento_id}</FieldError>}
          <FieldHint>Número do documento de identificação válido.</FieldHint>
        </div>
        
        <div className="space-y-2">
          <Label htmlFor="data_validade_cc">
            Data Validade CC
            <span className="text-xs text-muted-foreground ml-1">(opcional)</span>
          </Label>
          <Input
            id="data_validade_cc"
            type="date"
            value={formData.data_validade_cc}
            onChange={(e) => updateField("data_validade_cc", e.target.value)}
            data-testid="client-data-validade-cc"
          />
          <FieldHint>Data de validade do Cartão de Cidadão.</FieldHint>
        </div>
        
        <div className="space-y-2">
          <RequiredLabel htmlFor="naturalidade">Naturalidade</RequiredLabel>
          <Input
            id="naturalidade"
            name="naturalidade"
            value={formData.naturalidade}
            onChange={(e) => updateField("naturalidade", e.target.value)}
            placeholder="Local de nascimento"
            required
            data-testid="client-naturalidade"
            className={cn(fieldErrors.naturalidade && "border-red-500 focus-visible:ring-red-500 bg-red-50")}
          />
          {fieldErrors.naturalidade && <FieldError>{fieldErrors.naturalidade}</FieldError>}
          <FieldHint>Freguesia/concelho onde nasceu.</FieldHint>
        </div>
        
        <div className="space-y-2">
          <RequiredLabel htmlFor="nacionalidade">Nacionalidade</RequiredLabel>
          <Input
            id="nacionalidade"
            name="nacionalidade"
            value={formData.nacionalidade}
            onChange={(e) => updateField("nacionalidade", e.target.value)}
            placeholder="Portuguesa"
            required
            data-testid="client-nacionalidade"
          />
        </div>
        
        <div className="space-y-2 md:col-span-2">
          <RequiredLabel htmlFor="morada_fiscal">Morada Fiscal</RequiredLabel>
          <Input
            id="morada_fiscal"
            value={formData.morada_fiscal}
            onChange={(e) => updateField("morada_fiscal", e.target.value)}
            placeholder="Rua, número, código postal, localidade"
            required
            data-testid="client-morada"
          />
          <FieldHint>Morada completa conforme registada nas Finanças.</FieldHint>
        </div>
        
        <div className="space-y-2">
          <RequiredLabel htmlFor="birth_date">Data de Nascimento</RequiredLabel>
          <Input
            id="birth_date"
            type="date"
            value={formData.birth_date}
            onChange={(e) => updateField("birth_date", e.target.value)}
            required
            data-testid="client-birth-date"
          />
        </div>
        
        <div className="space-y-2">
          <RequiredLabel htmlFor="estado_civil">Estado Civil</RequiredLabel>
          <Select value={formData.estado_civil} onValueChange={(v) => updateField("estado_civil", v)}>
            <SelectTrigger data-testid="client-estado-civil">
              <SelectValue placeholder="Selecione" />
            </SelectTrigger>
            <SelectContent>
              {ESTADOS_CIVIS.map((ec) => (
                <SelectItem key={ec.value} value={ec.value}>{ec.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <FieldHint>Se casado/a, indique o regime de bens do casamento.</FieldHint>
        </div>
        
        <div className="space-y-3 md:col-span-2 p-4 bg-amber-50 border border-amber-200 rounded-lg">
          <div className="flex items-start space-x-3">
            <Checkbox
              id="menor_35_anos"
              checked={formData.menor_35_anos}
              onCheckedChange={(checked) => updateField("menor_35_anos", checked)}
              data-testid="client-menor-35"
            />
            <div className="space-y-1">
              <Label htmlFor="menor_35_anos" className="text-sm font-medium cursor-pointer">
                Tenho menos de 35 anos e pretendo usufruir do Apoio ao Estado
              </Label>
              <p className="text-xs text-amber-700">
                Se tem menos de 35 anos, pode ser elegível para benefícios fiscais na compra da primeira habitação própria permanente (isenção/redução de IMT e Imposto de Selo).
              </p>
            </div>
          </div>
        </div>
        
        <div className="space-y-2 md:col-span-2">
          <RequiredLabel>Compra individualmente ou com outra pessoa?</RequiredLabel>
          <Select value={formData.compra_tipo} onValueChange={(v) => updateField("compra_tipo", v)}>
            <SelectTrigger data-testid="client-compra-tipo">
              <SelectValue placeholder="Selecione" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="individual">Individual</SelectItem>
              <SelectItem value="outra_pessoa">Com outra pessoa</SelectItem>
            </SelectContent>
          </Select>
          <FieldHint>Se comprar com outra pessoa (cônjuge, familiar, etc.), selecione "Com outra pessoa" para preencher os dados do 2º titular no próximo passo.</FieldHint>
        </div>
      </div>
    </div>
  );

  // Step 2: Dados do 2º Titular (se aplicável)
  const renderStep2 = () => (
    <div className="space-y-6">
      <div className="text-center mb-6">
        <Users className="h-10 w-10 mx-auto mb-2 text-primary" />
        <h2 className="text-xl font-semibold mb-2">Dados do 2º Titular</h2>
        <p className="text-muted-foreground">
          {formData.compra_tipo === "outra_pessoa" 
            ? "Preencha os dados do segundo titular" 
            : "Não aplicável - compra individual"}
        </p>
      </div>
      
      {formData.compra_tipo === "outra_pessoa" ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-2 md:col-span-2">
            <RequiredLabel htmlFor="titular2_name">Nome completo</RequiredLabel>
            <Input
              id="titular2_name"
              value={formData.titular2_name}
              onChange={(e) => updateField("titular2_name", e.target.value)}
              placeholder="Nome completo"
              data-testid="titular2-name"
              className={cn(fieldErrors.titular2_name && "border-red-500 focus-visible:ring-red-500 bg-red-50")}
            />
            {fieldErrors.titular2_name && <FieldError>{fieldErrors.titular2_name}</FieldError>}
          </div>
          
          <div className="space-y-2">
            <Label htmlFor="titular2_email">Email</Label>
            <Input
              id="titular2_email"
              type="email"
              value={formData.titular2_email}
              onChange={(e) => updateField("titular2_email", e.target.value)}
              placeholder="email@exemplo.pt"
              data-testid="titular2-email"
              className={cn(fieldErrors.titular2_email && "border-red-500 focus-visible:ring-red-500 bg-red-50")}
            />
            {fieldErrors.titular2_email && <FieldError>{fieldErrors.titular2_email}</FieldError>}
          </div>
          
          <div className="space-y-2">
            <Label htmlFor="titular2_phone">Telemóvel</Label>
            <Input
              id="titular2_phone"
              type="tel"
              value={formData.titular2_phone}
              onChange={(e) => updateField("titular2_phone", e.target.value)}
              placeholder="+351 912 345 678"
              data-testid="titular2-phone"
              className={cn(fieldErrors.titular2_phone && "border-red-500 focus-visible:ring-red-500 bg-red-50")}
            />
            {fieldErrors.titular2_phone && <FieldError>{fieldErrors.titular2_phone}</FieldError>}
          </div>
          
          <div className="space-y-2">
            <Label htmlFor="titular2_nif">NIF</Label>
            <Input
              id="titular2_nif"
              type="text"
              value={formData.titular2_nif}
              onChange={(e) => updateField("titular2_nif", e.target.value.replace(/\D/g, ""))}
              placeholder="123456789"
              maxLength={9}
              data-testid="titular2-nif"
              className={cn(fieldErrors.titular2_nif && "border-red-500 focus-visible:ring-red-500 bg-red-50")}
            />
            {fieldErrors.titular2_nif && <FieldError>{fieldErrors.titular2_nif}</FieldError>}
            <FieldHint>Número de Identificação Fiscal - 9 dígitos</FieldHint>
          </div>
          
          <div className="space-y-2">
            <Label htmlFor="titular2_documento_id">Cartão de Cidadão/Passaporte</Label>
            <Input
              id="titular2_documento_id"
              value={formData.titular2_documento_id}
              onChange={(e) => updateField("titular2_documento_id", e.target.value)}
              placeholder="Número do documento"
              data-testid="titular2-documento"
              className={cn(fieldErrors.titular2_documento_id && "border-red-500 focus-visible:ring-red-500 bg-red-50")}
            />
            {fieldErrors.titular2_documento_id && <FieldError>{fieldErrors.titular2_documento_id}</FieldError>}
          </div>
          
          <div className="space-y-2">
            <Label htmlFor="titular2_naturalidade">Naturalidade</Label>
            <Input
              id="titular2_naturalidade"
              value={formData.titular2_naturalidade}
              onChange={(e) => updateField("titular2_naturalidade", e.target.value)}
              placeholder="Local de nascimento"
              data-testid="titular2-naturalidade"
              className={cn(fieldErrors.titular2_naturalidade && "border-red-500 focus-visible:ring-red-500 bg-red-50")}
            />
            {fieldErrors.titular2_naturalidade && <FieldError>{fieldErrors.titular2_naturalidade}</FieldError>}
          </div>
          
          <div className="space-y-2">
            <Label htmlFor="titular2_nacionalidade">Nacionalidade</Label>
            <Input
              id="titular2_nacionalidade"
              value={formData.titular2_nacionalidade}
              onChange={(e) => updateField("titular2_nacionalidade", e.target.value)}
              placeholder="Portuguesa"
              data-testid="titular2-nacionalidade"
              className={cn(fieldErrors.titular2_nacionalidade && "border-red-500 focus-visible:ring-red-500 bg-red-50")}
            />
            {fieldErrors.titular2_nacionalidade && <FieldError>{fieldErrors.titular2_nacionalidade}</FieldError>}
          </div>
          
          <div className="space-y-2 md:col-span-2">
            <Label htmlFor="titular2_morada_fiscal">Morada Fiscal</Label>
            <Input
              id="titular2_morada_fiscal"
              value={formData.titular2_morada_fiscal}
              onChange={(e) => updateField("titular2_morada_fiscal", e.target.value)}
              placeholder="Rua, número, código postal, localidade"
              data-testid="titular2-morada"
              className={cn(fieldErrors.titular2_morada_fiscal && "border-red-500 focus-visible:ring-red-500 bg-red-50")}
            />
            {fieldErrors.titular2_morada_fiscal && <FieldError>{fieldErrors.titular2_morada_fiscal}</FieldError>}
          </div>
          
          <div className="space-y-2">
            <Label htmlFor="titular2_birth_date">Data de Nascimento</Label>
            <Input
              id="titular2_birth_date"
              type="date"
              value={formData.titular2_birth_date}
              onChange={(e) => updateField("titular2_birth_date", e.target.value)}
              data-testid="titular2-birth-date"
              className={cn(fieldErrors.titular2_birth_date && "border-red-500 focus-visible:ring-red-500 bg-red-50")}
            />
            {fieldErrors.titular2_birth_date && <FieldError>{fieldErrors.titular2_birth_date}</FieldError>}
          </div>
          
          <div className="space-y-2">
            <Label htmlFor="titular2_estado_civil">Estado Civil</Label>
            <Select value={formData.titular2_estado_civil} onValueChange={(v) => updateField("titular2_estado_civil", v)}>
              <SelectTrigger 
                data-testid="titular2-estado-civil"
                className={cn(fieldErrors.titular2_estado_civil && "border-red-500 focus:ring-red-500 bg-red-50")}
              >
                <SelectValue placeholder="Selecione" />
              </SelectTrigger>
              <SelectContent>
                {ESTADOS_CIVIS.map((ec) => (
                  <SelectItem key={ec.value} value={ec.value}>{ec.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {fieldErrors.titular2_estado_civil && <FieldError>{fieldErrors.titular2_estado_civil}</FieldError>}
          </div>
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

  // Step 3: Imóvel Pretendido
  const renderStep3 = () => (
    <div className="space-y-6">
      <div className="text-center mb-6">
        <Home className="h-10 w-10 mx-auto mb-2 text-primary" />
        <h2 className="text-xl font-semibold mb-2">Tipo de Pedido</h2>
        <p className="text-muted-foreground">Indique a finalidade do seu pedido</p>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* FINALIDADE PRIMEIRO */}
        <div className="space-y-2 md:col-span-2">
          <RequiredLabel>Finalidade do pedido</RequiredLabel>
          <Select value={formData.finalidade} onValueChange={(v) => updateField("finalidade", v)}>
            <SelectTrigger data-testid="imovel-finalidade">
              <SelectValue placeholder="Selecione a finalidade" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="compra_imovel">Compra de Imóvel</SelectItem>
              <SelectItem value="refinanciamento">Refinanciamento / Transferência de Crédito</SelectItem>
            </SelectContent>
          </Select>
          <FieldHint>
            {formData.finalidade === "refinanciamento" 
              ? "Seleccionou refinanciamento - não será necessário preencher dados do imóvel." 
              : "Seleccionou compra - preencha os dados do imóvel pretendido abaixo."}
          </FieldHint>
        </div>
        
        {/* CAMPOS DE IMÓVEL - SÓ SE NÃO FOR REFINANCIAMENTO */}
        {formData.finalidade !== "refinanciamento" && (
          <>
            <div className="space-y-2">
              <RequiredLabel>O que procura?</RequiredLabel>
              <Select value={formData.tipo_imovel} onValueChange={(v) => updateField("tipo_imovel", v)}>
                <SelectTrigger data-testid="imovel-tipo">
                  <SelectValue placeholder="Selecione" />
                </SelectTrigger>
                <SelectContent>
                  {TIPOS_IMOVEL.map((ti) => (
                    <SelectItem key={ti.value} value={ti.value}>{ti.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            
            <div className="space-y-2">
              <RequiredLabel>Número de quartos</RequiredLabel>
              <Select value={formData.num_quartos} onValueChange={(v) => updateField("num_quartos", v)}>
                <SelectTrigger data-testid="imovel-quartos">
                  <SelectValue placeholder="Selecione" />
                </SelectTrigger>
                <SelectContent>
                  {QUARTOS.map((q) => (
                    <SelectItem key={q.value} value={q.value}>{q.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FieldHint>T0 = Estúdio/Loft, T1 = 1 quarto, T2 = 2 quartos, etc.</FieldHint>
            </div>
            
            <div className="space-y-2 md:col-span-2">
              <RequiredLabel htmlFor="localizacao">Localização/Zona(s) preferida(s)</RequiredLabel>
              <Input
                id="localizacao"
                value={formData.localizacao}
                onChange={(e) => updateField("localizacao", e.target.value)}
                placeholder="Ex: Lisboa, Cascais, Sintra"
                required
                data-testid="imovel-localizacao"
              />
              <FieldHint>Pode indicar várias zonas separadas por vírgula. Quanto mais específico, melhor podemos ajudar.</FieldHint>
            </div>
            
            <div className="space-y-3 md:col-span-2">
              <Label>Características obrigatórias (selecione apenas as imprescindíveis)</Label>
              <FieldHint>Selecione apenas características que são absolutamente essenciais. Menos seleções = mais opções de imóveis.</FieldHint>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {CARACTERISTICAS.map((c) => (
                  <div key={c.value} className="flex items-center space-x-2">
                    <Checkbox
                      id={c.value}
                      checked={(formData.caracteristicas || []).includes(c.value)}
                      onCheckedChange={() => toggleCaracteristica(c.value)}
                      data-testid={`caracteristica-${c.value}`}
                    />
                    <Label htmlFor={c.value} className="text-sm cursor-pointer">{c.label}</Label>
                  </div>
                ))}
              </div>
            </div>
            
            {(formData.caracteristicas || []).includes("outro") && (
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="outras_caracteristicas">Outras características</Label>
                <Input
                  id="outras_caracteristicas"
                  value={formData.outras_caracteristicas}
                  onChange={(e) => updateField("outras_caracteristicas", e.target.value)}
                  placeholder="Especifique outras características"
                  data-testid="imovel-outras-caracteristicas"
                />
              </div>
            )}
            
            {/* Novos campos: Área, Valor */}
            <div className="space-y-2">
              <Label htmlFor="area_pretendida">Área pretendida (m²)</Label>
              <Input
                id="area_pretendida"
                type="number"
                value={formData.area_pretendida}
                onChange={(e) => updateField("area_pretendida", e.target.value)}
                placeholder="Ex: 100"
                data-testid="imovel-area-pretendida"
              />
              <FieldHint>Valor aproximado/médio em metros quadrados</FieldHint>
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="valor_maximo_imovel">Valor máximo do imóvel (€)</Label>
              <Input
                id="valor_maximo_imovel"
                type="number"
                value={formData.valor_maximo_imovel}
                onChange={(e) => updateField("valor_maximo_imovel", e.target.value)}
                placeholder="Ex: 300000"
                data-testid="imovel-valor-maximo"
              />
            </div>
            
            <div className="space-y-2 md:col-span-2">
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="ja_tem_casa_escolhida"
                  checked={formData.ja_tem_casa_escolhida}
                  onCheckedChange={(checked) => updateField("ja_tem_casa_escolhida", checked)}
                  data-testid="imovel-ja-tem-casa"
                />
                <Label htmlFor="ja_tem_casa_escolhida" className="cursor-pointer">
                  Já tenho uma casa escolhida
                </Label>
              </div>
            </div>
            
            {/* Campos condicionais se já tem casa escolhida */}
            {formData.ja_tem_casa_escolhida && (
              <>
                <div className="space-y-2">
                  <Label htmlFor="proprietario_nome">Nome do proprietário</Label>
                  <Input
                    id="proprietario_nome"
                    value={formData.proprietario_nome}
                    onChange={(e) => updateField("proprietario_nome", e.target.value)}
                    placeholder="Nome completo do proprietário"
                    data-testid="imovel-proprietario-nome"
                  />
                </div>
                
                <div className="space-y-2">
                  <Label htmlFor="proprietario_contacto">Contacto do proprietário</Label>
                  <Input
                    id="proprietario_contacto"
                    value={formData.proprietario_contacto}
                    onChange={(e) => updateField("proprietario_contacto", e.target.value)}
                    placeholder="Telefone ou email"
                    data-testid="imovel-proprietario-contacto"
                  />
                </div>
                
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="caracteristicas_imovel">Características básicas do imóvel escolhido</Label>
                  <Textarea
                    id="caracteristicas_imovel"
                    value={formData.caracteristicas_imovel}
                    onChange={(e) => updateField("caracteristicas_imovel", e.target.value)}
                    placeholder="Ex: T3, 120m², rés-do-chão, garagem, jardim..."
                    rows={2}
                    data-testid="imovel-caracteristicas"
                  />
                </div>
              </>
            )}
          </>
        )}
        
        {/* Para refinanciamento, mostrar campos específicos */}
        {formData.finalidade === "refinanciamento" && (
          <>
            <div className="space-y-2 md:col-span-2">
              <RequiredLabel htmlFor="valor_transferencia">Valor a Transferir/Consolidar (€)</RequiredLabel>
              <Input
                id="valor_transferencia"
                type="number"
                value={formData.valor_transferencia}
                onChange={(e) => updateField("valor_transferencia", e.target.value)}
                placeholder="Ex: 150000"
                data-testid="imovel-valor-transferencia"
              />
              <FieldHint>Valor total dos créditos que pretende consolidar/transferir.</FieldHint>
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="valor_extra">Valor Extra Necessário (€)</Label>
              <Input
                id="valor_extra"
                type="number"
                value={formData.valor_extra}
                onChange={(e) => updateField("valor_extra", e.target.value)}
                placeholder="Ex: 30000"
                data-testid="imovel-valor-extra"
              />
              <FieldHint>Se precisa de capital adicional além do refinanciamento.</FieldHint>
            </div>
            
            <div className="space-y-2">
              <RequiredLabel htmlFor="prazo_pretendido">Prazo Pretendido (anos)</RequiredLabel>
              <Select value={formData.prazo_pretendido} onValueChange={(v) => updateField("prazo_pretendido", v)}>
                <SelectTrigger data-testid="imovel-prazo">
                  <SelectValue placeholder="Selecione" />
                </SelectTrigger>
                <SelectContent>
                  {[5, 10, 15, 20, 25, 30, 35, 40].map((anos) => (
                    <SelectItem key={anos} value={anos.toString()}>{anos} anos</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="outras_informacoes">Informações sobre o crédito actual</Label>
              <Textarea
                id="outras_informacoes"
                value={formData.outras_informacoes}
                onChange={(e) => updateField("outras_informacoes", e.target.value)}
                placeholder="Indique o banco actual, valor em dívida, spread actual, etc..."
                rows={3}
                data-testid="imovel-outras-info"
              />
            </div>
          </>
        )}
        
        {formData.finalidade !== "refinanciamento" && (
          <div className="space-y-2 md:col-span-2">
            <Label htmlFor="outras_informacoes">Outras informações</Label>
            <Textarea
              id="outras_informacoes"
              value={formData.outras_informacoes}
              onChange={(e) => updateField("outras_informacoes", e.target.value)}
              placeholder="Informações adicionais sobre o que procura..."
              rows={3}
              data-testid="imovel-outras-info"
            />
          </div>
        )}
      </div>
    </div>
  );

  // Step 4: Situação Financeira
  const renderStep4 = () => (
    <div className="space-y-6">
      <div className="text-center mb-6">
        <Briefcase className="h-10 w-10 mx-auto mb-2 text-amber-500" />
        <h2 className="text-xl font-semibold mb-2 text-blue-950">Situação Financeira</h2>
        <p className="text-muted-foreground">Informações sobre a sua situação financeira</p>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label>Tem acesso ao portal das finanças e segurança social direta?</Label>
          <Select value={formData.acesso_portal_financas} onValueChange={(v) => updateField("acesso_portal_financas", v)}>
            <SelectTrigger data-testid="fin-portal-financas">
              <SelectValue placeholder="Selecione" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="portal_financas">Portal das Finanças</SelectItem>
              <SelectItem value="seguranca_social">Segurança Social Direta</SelectItem>
              <SelectItem value="ambos">Ambos</SelectItem>
              <SelectItem value="nenhuma">Nenhuma</SelectItem>
            </SelectContent>
          </Select>
          <FieldHint>Indique a que portais oficiais tem acesso. As credenciais serão solicitadas posteriormente se necessário.</FieldHint>
        </div>
        
        <div className="space-y-2">
          <RequiredLabel>Chave Móvel Digital?</RequiredLabel>
          <Select value={formData.chave_movel_digital} onValueChange={(v) => updateField("chave_movel_digital", v)}>
            <SelectTrigger data-testid="fin-chave-movel">
              <SelectValue placeholder="Selecione" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="sim">Sim</SelectItem>
              <SelectItem value="nao">Não</SelectItem>
            </SelectContent>
          </Select>
          <FieldHint>A CMD facilita a assinatura digital de documentos. Pode ativar em autenticacao.gov.pt</FieldHint>
        </div>
        
        <div className="space-y-2">
          <Label htmlFor="renda_habitacao_atual">Renda da habitação atual (€)</Label>
          <Input
            id="renda_habitacao_atual"
            type="number"
            value={formData.renda_habitacao_atual}
            onChange={(e) => updateField("renda_habitacao_atual", e.target.value)}
            placeholder="0.00"
            data-testid="fin-renda-atual"
          />
          <FieldHint>Se vive em casa própria ou com familiares, deixe em branco ou coloque 0.</FieldHint>
        </div>
        
        <div className="space-y-2">
          <Label>Precisa vender a casa atual?</Label>
          <Select value={formData.precisa_vender_casa} onValueChange={(v) => updateField("precisa_vender_casa", v)}>
            <SelectTrigger data-testid="fin-vender-casa">
              <SelectValue placeholder="Selecione" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="sim">Sim</SelectItem>
              <SelectItem value="nao">Não</SelectItem>
            </SelectContent>
          </Select>
          <FieldHint>Se precisa vender para ter capital de entrada ou liquidar crédito existente.</FieldHint>
        </div>
        
        <div className="space-y-2">
          <Label>Efetivo?</Label>
          <Select value={formData.efetivo} onValueChange={(v) => updateField("efetivo", v)}>
            <SelectTrigger data-testid="fin-efetivo">
              <SelectValue placeholder="Selecione" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="sim">Sim</SelectItem>
              <SelectItem value="nao">Não</SelectItem>
            </SelectContent>
          </Select>
          <FieldHint>Se tem contrato de trabalho sem termo (efetivo) ou está em período experimental.</FieldHint>
        </div>
        
        <div className="space-y-2">
          <Label>Trabalha no estrangeiro?</Label>
          <Select value={formData.trabalha_estrangeiro} onValueChange={(v) => updateField("trabalha_estrangeiro", v)}>
            <SelectTrigger data-testid="fin-trabalha-estrangeiro">
              <SelectValue placeholder="Selecione" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="sim">Sim</SelectItem>
              <SelectItem value="nao">Não</SelectItem>
            </SelectContent>
          </Select>
          <FieldHint>Indique se trabalha fora de Portugal. Pode influenciar as condições do crédito.</FieldHint>
        </div>
        
        <div className="space-y-2">
          <RequiredLabel>Tipo de Contrato de Trabalho</RequiredLabel>
          <Select value={formData.employment_type} onValueChange={(v) => updateField("employment_type", v)}>
            <SelectTrigger data-testid="fin-employment-type">
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
          <FieldHint>Indique a sua situação profissional atual.</FieldHint>
        </div>
        
        <div className="space-y-2">
          <Label htmlFor="employment_duration">Tempo no Emprego Atual</Label>
          <Input
            id="employment_duration"
            value={formData.employment_duration}
            onChange={(e) => updateField("employment_duration", e.target.value)}
            placeholder="Ex: 2 anos e 3 meses"
            data-testid="fin-employment-duration"
          />
          <FieldHint>Quanto tempo trabalha na empresa atual ou como independente.</FieldHint>
        </div>
        
        <div className="space-y-2">
          <Label htmlFor="employer_name">Entidade Empregadora</Label>
          <Input
            id="employer_name"
            value={formData.employer_name}
            onChange={(e) => updateField("employer_name", e.target.value)}
            placeholder="Nome da empresa"
            data-testid="fin-employer-name"
          />
        </div>
        
        <div className="space-y-2">
          <Label htmlFor="employer_nif">NIF da Entidade Empregadora</Label>
          <Input
            id="employer_nif"
            value={formData.employer_nif}
            onChange={(e) => updateField("employer_nif", e.target.value.replace(/\D/g, ""))}
            placeholder="123456789"
            maxLength={9}
            data-testid="fin-employer-nif"
          />
          <FieldHint>O NIF da empresa onde trabalha (encontra-se no recibo de vencimento).</FieldHint>
        </div>
        
        <div className="space-y-2">
          <Label>Fiador (caso seja necessário)?</Label>
          <Select value={formData.fiador} onValueChange={(v) => updateField("fiador", v)}>
            <SelectTrigger data-testid="fin-fiador">
              <SelectValue placeholder="Selecione" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="sim">Sim</SelectItem>
              <SelectItem value="nao">Não</SelectItem>
            </SelectContent>
          </Select>
          <FieldHint>Ter um fiador disponível pode ajudar na aprovação do crédito.</FieldHint>
        </div>
        
        <div className="space-y-2 md:col-span-2">
          <RequiredLabel htmlFor="salario_liquido">Salário mensal líquido (já com descontos) (€)</RequiredLabel>
          <Input
            id="salario_liquido"
            type="number"
            value={formData.salario_liquido}
            onChange={(e) => updateField("salario_liquido", e.target.value)}
            placeholder="0.00"
            required
            data-testid="fin-salario"
          />
        </div>
      </div>
    </div>
  );

  // Step 5: Bancos e Capital
  const renderStep5 = () => (
    <div className="space-y-6">
      <div className="text-center mb-6">
        <CreditCard className="h-10 w-10 mx-auto mb-2 text-primary" />
        <h2 className="text-xl font-semibold mb-2">Créditos e Capital</h2>
        <p className="text-muted-foreground">Informações sobre créditos e capital disponível</p>
      </div>
      
      <div className="space-y-6">
        <div className="space-y-3">
          <RequiredLabel>Bancos onde tem créditos ativos</RequiredLabel>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setFormData(prev => ({ ...prev, bancos_creditos: [] }))}
              data-testid="banco-nenhuma"
              className={`px-3 py-1.5 rounded-full text-sm font-medium border-2 transition-all ${
                (formData.bancos_creditos || []).length === 0 
                  ? 'ring-2 ring-offset-1 ring-primary scale-105 bg-slate-700 text-white border-slate-700' 
                  : 'opacity-50 hover:opacity-80 bg-transparent text-slate-600 border-slate-400'
              }`}
            >
              {(formData.bancos_creditos || []).length === 0 && <span className="mr-1">✓</span>}
              Nenhuma
            </button>
            {BANCOS.map((banco) => {
              const selected = (formData.bancos_creditos || []).includes(banco);
              const colors = BANCO_COLORS[banco] || { bg: "#6B7280", text: "#fff" };
              return (
                <button
                  key={banco}
                  type="button"
                  onClick={() => toggleBanco(banco)}
                  data-testid={`banco-${banco.toLowerCase().replace(/\s+/g, '-')}`}
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
          <FieldHint>Inclui crédito habitação, automóvel, pessoal, ou cartões de crédito com saldo em dívida.</FieldHint>
        </div>
        
        {/* Pergunta sobre simulações de crédito */}
        <div className="space-y-3">
          <Label>Efetuou alguma simulação de crédito, adesão etc junto de algum banco? Quais?</Label>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setFormData(prev => ({ ...prev, bancos_simulacoes: [] }))}
              data-testid="banco-sim-nenhuma"
              className={`px-3 py-1.5 rounded-full text-sm font-medium border-2 transition-all ${
                (formData.bancos_simulacoes || []).length === 0 
                  ? 'ring-2 ring-offset-1 ring-primary scale-105 bg-slate-700 text-white border-slate-700' 
                  : 'opacity-50 hover:opacity-80 bg-transparent text-slate-600 border-slate-400'
              }`}
            >
              {(formData.bancos_simulacoes || []).length === 0 && <span className="mr-1">✓</span>}
              Nenhuma
            </button>
            {BANCOS.map((banco) => {
              const selected = (formData.bancos_simulacoes || []).includes(banco);
              const colors = BANCO_COLORS[banco] || { bg: "#6B7280", text: "#fff" };
              return (
                <button
                  key={`sim-${banco}`}
                  type="button"
                  onClick={() => toggleBancoSimulacoes(banco)}
                  data-testid={`banco-sim-${banco.toLowerCase().replace(/\s+/g, '-')}`}
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
          <FieldHint>Indique os bancos onde já efetuou simulações ou pedidos de crédito habitação.</FieldHint>
        </div>
        
        {/* Pergunta sobre tempo restante do crédito (apenas para refinanciamento) */}
        {formData.finalidade === "refinanciamento" && (
          <div className="space-y-2 p-4 bg-amber-50 border border-amber-200 rounded-lg">
            <RequiredLabel htmlFor="tempo_restante_credito">Quanto tempo falta para acabar de pagar o crédito atual?</RequiredLabel>
            <Select 
              value={formData.tempo_restante_credito} 
              onValueChange={(v) => updateField("tempo_restante_credito", v)}
            >
              <SelectTrigger data-testid="tempo-restante-credito">
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
            <FieldHint>Esta informação ajuda a determinar as condições do refinanciamento.</FieldHint>
          </div>
        )}
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-2">
            <RequiredLabel htmlFor="capital_proprio">Capital próprio disponível (€)</RequiredLabel>
            <Input
              id="capital_proprio"
              type="number"
              value={formData.capital_proprio}
              onChange={(e) => updateField("capital_proprio", e.target.value)}
              placeholder="0.00"
              required
              data-testid="fin-capital-proprio"
            />
            <FieldHint>Dinheiro que tem disponível para entrada + despesas (escritura, IMT, seguros).</FieldHint>
          </div>
          
          <div className="space-y-2">
            <RequiredLabel htmlFor="valor_financiado">Valor a financiar (€)</RequiredLabel>
            <Input
              id="valor_financiado"
              value={formData.valor_financiado}
              onChange={(e) => updateField("valor_financiado", e.target.value)}
              placeholder="Ex: 200.000€ ou 80% do valor"
              required
              data-testid="fin-valor-financiado"
            />
            <FieldHint>Pode indicar um valor fixo ou percentagem (ex: "90% do valor do imóvel").</FieldHint>
          </div>
        </div>
      </div>
    </div>
  );

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
            <p>{(formData.bancos_creditos || []).length > 0 ? formData.bancos_creditos.join(", ") : "Nenhum banco selecionado"}</p>
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

      <div className="space-y-4 pt-4 border-t">
        <div className="flex items-start space-x-3">
          <Checkbox
            id="consent_data"
            checked={formData.consent_data}
            onCheckedChange={(checked) => updateField("consent_data", checked)}
            data-testid="consent-data"
          />
          <Label htmlFor="consent_data" className="text-sm leading-relaxed cursor-pointer">
            Autorizo o tratamento dos meus dados pessoais para análise do meu pedido de crédito/imobiliário, nos termos do RGPD. *
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
            Aceito ser contactado pela equipa para dar seguimento ao meu processo. *
          </Label>
        </div>
      </div>
    </div>
  );

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
    
    switch (stepNum) {
      case 1:
        if (!formData.name || formData.name.trim().length < 2) {
          errors.push("Nome completo é obrigatório");
          newFieldErrors.name = "Nome completo é obrigatório (mínimo 2 caracteres)";
        }
        const emailCheck = validateEmail(formData.email);
        if (!emailCheck.valid) {
          errors.push(emailCheck.message);
          newFieldErrors.email = emailCheck.message;
        }
        const phoneCheck = validatePhone(formData.phone);
        if (!phoneCheck.valid) {
          errors.push(phoneCheck.message);
          newFieldErrors.phone = phoneCheck.message;
        }
        const nifCheck = validateNIF(formData.nif);
        if (!nifCheck.valid) {
          errors.push(nifCheck.message);
          newFieldErrors.nif = nifCheck.message;
        }
        if (!formData.documento_id) {
          errors.push("Nº do documento é obrigatório");
          newFieldErrors.documento_id = "Nº do documento é obrigatório";
        }
        if (!formData.naturalidade) {
          errors.push("Naturalidade é obrigatória");
          newFieldErrors.naturalidade = "Naturalidade é obrigatória";
        }
        if (!formData.nacionalidade) {
          errors.push("Nacionalidade é obrigatória");
          newFieldErrors.nacionalidade = "Nacionalidade é obrigatória";
        }
        if (!formData.morada_fiscal) {
          errors.push("Morada fiscal é obrigatória");
          newFieldErrors.morada_fiscal = "Morada fiscal é obrigatória";
        }
        if (!formData.birth_date) {
          errors.push("Data de nascimento é obrigatória");
          newFieldErrors.birth_date = "Data de nascimento é obrigatória";
        }
        if (!formData.estado_civil) {
          errors.push("Estado civil é obrigatório");
          newFieldErrors.estado_civil = "Estado civil é obrigatório";
        }
        break;
      case 2:
        // Se tem 2º titular, validar os campos
        if (formData.compra_tipo === "outra_pessoa") {
          if (!formData.titular2_name || formData.titular2_name.trim().length < 2) {
            errors.push("Nome do 2º titular é obrigatório");
            newFieldErrors.titular2_name = "Nome do 2º titular é obrigatório";
          }
          if (formData.titular2_nif) {
            const nif2Check = validateNIF(formData.titular2_nif);
            if (!nif2Check.valid) {
              errors.push(`2º Titular: ${nif2Check.message}`);
              newFieldErrors.titular2_nif = nif2Check.message;
            }
          }
          if (formData.titular2_email) {
            const email2Check = validateEmail(formData.titular2_email);
            if (!email2Check.valid) {
              errors.push(`2º Titular: ${email2Check.message}`);
              newFieldErrors.titular2_email = email2Check.message;
            }
          }
        }
        break;
      case 3:
        if (!formData.finalidade) {
          errors.push("Finalidade é obrigatória");
          newFieldErrors.finalidade = "Selecione a finalidade do pedido";
        }
        if (formData.finalidade !== "refinanciamento") {
          if (!formData.tipo_imovel) {
            errors.push("Tipo de imóvel é obrigatório");
            newFieldErrors.tipo_imovel = "Tipo de imóvel é obrigatório";
          }
          if (!formData.num_quartos) {
            errors.push("Número de quartos é obrigatório");
            newFieldErrors.num_quartos = "Número de quartos é obrigatório";
          }
          if (!formData.localizacao) {
            errors.push("Localização é obrigatória");
            newFieldErrors.localizacao = "Localização é obrigatória";
          }
        }
        break;
      case 4:
        if (!formData.chave_movel_digital) {
          errors.push("Chave móvel digital é obrigatória");
          newFieldErrors.chave_movel_digital = "Chave móvel digital é obrigatória";
        }
        if (!formData.salario_liquido) {
          errors.push("Salário líquido é obrigatório");
          newFieldErrors.salario_liquido = "Salário líquido é obrigatório";
        }
        break;
      case 5:
        if (!formData.capital_proprio) {
          errors.push("Capital próprio é obrigatório");
          newFieldErrors.capital_proprio = "Capital próprio é obrigatório";
        }
        if (!formData.valor_financiado) {
          errors.push("Valor a financiar é obrigatório");
          newFieldErrors.valor_financiado = "Valor a financiar é obrigatório";
        }
        break;
      case 6:
        if (!formData.consent_data) {
          errors.push("Deve aceitar o tratamento de dados");
          newFieldErrors.consent_data = "Obrigatório";
        }
        if (!formData.consent_contact) {
          errors.push("Deve aceitar ser contactado");
          newFieldErrors.consent_contact = "Obrigatório";
        }
        break;
      default:
        break;
    }
    
    return { errors, fieldErrors: newFieldErrors };
  };

  const handleNextStep = () => {
    if (previewMode) {
      setStep(Math.min(6, step + 1));
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
    setStep(Math.min(6, step + 1));
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // Função helper para obter erro de um campo específico
  const getFieldError = (fieldName) => fieldErrors[fieldName] || null;

  const canProceed = () => {
    if (previewMode) return true;
    switch (step) {
      case 1:
        return formData.name && formData.email && formData.phone && formData.nif && 
               formData.documento_id && formData.naturalidade && formData.nacionalidade &&
               formData.morada_fiscal && formData.birth_date && formData.estado_civil;
      case 2:
        return true; // Always can proceed (2nd titular is optional)
      case 3:
        // Se for refinanciamento, não precisa dados de imóvel
        if (formData.finalidade === "refinanciamento") {
          return !!formData.finalidade;
        }
        // Se for compra, precisa dados do imóvel
        return formData.finalidade && formData.tipo_imovel && formData.num_quartos && formData.localizacao;
      case 4:
        return formData.chave_movel_digital && formData.salario_liquido;
      case 5:
        return formData.capital_proprio && formData.valor_financiado;
      case 6:
        return formData.consent_data && formData.consent_contact;
      default:
        return true;
    }
  };

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
            {/* Progress Bar com percentagem */}
            <FormProgressBar 
              currentStep={step} 
              totalSteps={6} 
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

            {/* Campos personalizados para o passo atual */}
            {getCustomFieldsForStep(step).length > 0 && (
              <div className="mt-6 pt-4 border-t border-dashed border-emerald-300 space-y-4">
                <p className="text-xs text-emerald-600 font-medium uppercase tracking-wide">Campos adicionais</p>
                {getCustomFieldsForStep(step).map(renderCustomField)}
              </div>
            )}

            <div className="flex justify-between mt-8 pt-6 border-t border-border">
              <Button
                variant="outline"
                onClick={() => setStep(Math.max(1, step - 1))}
                disabled={step === 1}
              >
                <ArrowLeft className="mr-2 h-4 w-4" />
                Voltar
              </Button>
              
              {step < 6 ? (
                <Button
                  onClick={handleNextStep}
                  disabled={!canProceed()}
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
                  disabled={loading || !canProceed()}
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
};

export default PublicClientForm;
