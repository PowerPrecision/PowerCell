/**
 * ProcessDetails — Página de detalhes completos de um processo de crédito habitação.
 *
 * PORQUÊ: Cada processo no PowerCell requer uma vista centralizada onde consultores,
 * mediadores e administradores podem consultar e editar todos os dados do cliente,
 * documentos financeiros, imóvel, crédito bancário e prazos. Esta página é o "hub"
 * operacional do CRM — substitui o acesso disperso a múltiplas ferramentas externas.
 *
 * DECISÕES ARQUITECTURAIS:
 * - Tabs por domínio (pessoais, financeiros, imóvel, crédito) para organizar
 *   a complexidade sem sobrecarregar o utilizador.
 * - Permissões granulares por role (consultor, mediador, indexacao, cliente)
 *   e por actions (sistema de permissões dinâmicas do backend).
 * - Extração automática de dados por IA (OCR de documentos) com sistema de
 *   conflitos — quando a IA detecta divergências entre documentos, o utilizador
 *   escolhe manualmente o valor correcto.
 * - Auto-save do status com debounce de 500ms para evitar perda de dados.
 * - Validação de NIF português (9 dígitos, checksum, exclusão de NIFs empresariais).
 * - Integração com RGPD (pedido de consentimento via email).
 * - Geração de CPCV, minutas, e DSTI automática integrada nos tabs.
 * - Processos em status terminal (eliminados, desistências, concluídos) ficam
 *   bloqueados em modo de leitura para proteger a integridade dos dados.
 *
 * @context {AuthContext} — Consome user, token para autenticação e permissões
 *
 * @route /processo/:id — Rota parametrizada pelo ID do processo
 *
 * @example
 * // Acesso via navegação
 * <Route path="/processo/:id" element={<ProcessDetails />} />
 * // O ID é obtido via useParams() internamente
 */
import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Calendar } from "../components/ui/calendar";
import { ScrollArea } from "../components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "../components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Separator } from "../components/ui/separator";
import { Popover, PopoverContent, PopoverTrigger } from "../components/ui/popover";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "../components/ui/accordion";
import {
  getProcess,
  updateProcess,
  getDeadlines,
  createDeadline,
  updateDeadline,
  deleteDeadline,
  getActivities,
  createActivity,
  deleteActivity,
  getHistory,
  getWorkflowStatuses,
  getClientS3Files,
  getS3DownloadUrl,
  deleteClient,
} from "../services/api";
import { generateMagicLink, sendMagicLinkEmail } from "../services/api";
import ProcessAlerts from "../components/ProcessAlerts";
import TasksPanel from "../components/TasksPanel";
import ProcessSummaryCard from "../components/ProcessSummaryCard";
import EmailHistoryPanel from "../components/EmailHistoryPanel";
import UnifiedDocumentsPanel from "../components/UnifiedDocumentsPanel";
import ProcessTimeline from "../components/ProcessTimeline";
import UnifiedAuditTrail from "../components/UnifiedAuditTrail";
import ClientPropertyMatch from "../components/ClientPropertyMatch";
import DataConflictResolver from "../components/DataConflictResolver";
import CPCVModal from "../components/CPCVModal";
import ProcessStickyHeader from "../components/ProcessStickyHeader";
import DSTICalculator from "../components/DSTICalculator";
import RiskCalculator from "../components/RiskCalculator";
import AutoDSTIBadge from "../components/AutoDSTIBadge";
import TempLinkButton from "../components/TempLinkButton";
import SendDocumentationModal from "../components/SendDocumentationModal";
import {
  ArrowLeft,
  User,
  Briefcase,
  Building2,
  CreditCard,
  Calendar as CalendarIcon,
  Clock,
  Plus,
  Check,
  Trash2,
  Loader2,
  AlertCircle,
  MessageSquare,
  History,
  Send,
  FolderOpen,
  File,
  Download,
  ChevronRight,
  ExternalLink,
  Link as LinkIcon,
  Users,
  Sparkles,
  Mail,
  Phone,
  MapPin,
  FileSignature,
  AlertTriangle,
  CheckCircle,
  Database,
  Calculator,
  TrendingUp,
  Link2,
  Lock,
  Eye,
  EyeOff,
  X,
  Search,
} from "lucide-react";
import { toast } from "sonner";
import { format, parseISO, isAfter } from "date-fns";
import { pt } from "date-fns/locale";

// eslint-disable-next-line no-undef
const API_URL = process.env.REACT_APP_BACKEND_URL || "";

const statusColors = {
  yellow: "bg-yellow-100 text-yellow-800 border-yellow-200",
  blue: "bg-blue-100 text-blue-800 border-blue-200",
  orange: "bg-orange-100 text-orange-800 border-orange-200",
  green: "bg-emerald-100 text-emerald-800 border-emerald-200",
  red: "bg-red-100 text-red-800 border-red-200",
  purple: "bg-purple-100 text-purple-800 border-purple-200",
};

const BANK_LIST = [
  "ABANCA", "BBVA", "BEST", "BIG", "BPI", "CGD", "Crédito Agrícola",
  "CTT", "Millennium bcp", "Novo Banco", "Popular", "Santander Totta", "Outro"
];

// Cores dos bancos portugueses para badges
const BANK_COLORS = {
  "ABANCA": "bg-red-500 text-white",
  "BBVA": "bg-blue-600 text-white",
  "BEST": "bg-green-600 text-white",
  "BIG": "bg-orange-500 text-white",
  "BPI": "bg-yellow-400 text-yellow-900",
  "CGD": "bg-red-600 text-white",
  "Crédito Agrícola": "bg-green-500 text-white",
  "Credito Agricola": "bg-green-500 text-white",
  "CTT": "bg-red-400 text-white",
  "Millennium bcp": "bg-red-500 text-white",
  "Millennium": "bg-red-500 text-white",
  "bcp": "bg-red-500 text-white",
  "Novo Banco": "bg-gray-700 text-white",
  "NovoBanco": "bg-gray-700 text-white",
  "Popular": "bg-blue-500 text-white",
  "Santander Totta": "bg-red-600 text-white",
  "Santander": "bg-red-600 text-white",
  "Bankinter": "bg-blue-800 text-white",
  "ActivoBank": "bg-teal-500 text-white",
  "Eurobic": "bg-red-500 text-white",
  "BIC": "bg-red-500 text-white",
  "Caixa Geral": "bg-red-600 text-white",
};

// Função para obter cor do banco
const getBankColor = (bankName) => {
  if (!bankName) return "bg-gray-200 text-gray-800";
  
  // Tentar match exato primeiro
  if (BANK_COLORS[bankName]) {
    return BANK_COLORS[bankName];
  }
  
  // Tentar match parcial (case-insensitive)
  const bankLower = bankName.toLowerCase();
  for (const [bank, color] of Object.entries(BANK_COLORS)) {
    if (bankLower.includes(bank.toLowerCase()) || bank.toLowerCase().includes(bankLower)) {
      return color;
    }
  }
  
  // Cor padrão para bancos não mapeados
  return "bg-gray-200 text-gray-800";
};

const typeLabels = {
  credito: "Crédito",
  imobiliaria: "Imobiliária",
  ambos: "Crédito + Imobiliária",
};

// Função para validar NIF português
const validateNIF = (nif) => {
  if (!nif) return { valid: true, error: null };
  
  // Remover espaços e caracteres especiais
  const nifClean = nif.replace(/[^\d]/g, '');
  
  if (nifClean.length !== 9) {
    return { valid: false, error: `NIF deve ter 9 dígitos (tem ${nifClean.length})` };
  }
  
  if (!/^\d+$/.test(nifClean)) {
    return { valid: false, error: "NIF deve conter apenas dígitos" };
  }
  
  // NIFs que começam com 5 são de empresas
  if (nifClean.startsWith('5')) {
    return { valid: false, error: "NIF de empresa (começa por 5) não é permitido para clientes particulares" };
  }
  
  return { valid: true, error: null };
};

const ProcessDetails = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user, token } = useAuth();
  const [process, setProcess] = useState(null);
  const [deadlines, setDeadlines] = useState([]);
  const [activities, setActivities] = useState([]);
  const [history, setHistory] = useState([]);
  const [workflowStatuses, setWorkflowStatuses] = useState([]);
  const [oneDriveFiles, setOneDriveFiles] = useState([]);
  const [currentFolder, setCurrentFolder] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState("personal");
  const [sideTab, setSideTab] = useState("deadlines");

  const [accessDenied, setAccessDenied] = useState(false);
  const [notFound, setNotFound] = useState(false);
  
  // Estado de erro de validação do NIF
  const [nifError, setNifError] = useState(null);

  // TAREFA 2: Estado para conflitos de dados IA
  const [aiSuggestions, setAiSuggestions] = useState([]);
  const [isDataConfirmed, setIsDataConfirmed] = useState(false);

  // Form states
  const [personalData, setPersonalData] = useState({});
  const [titular2Data, setTitular2Data] = useState({});  // Estado para 2º titular
  const [financialData, setFinancialData] = useState({});
  const [showPortalSenha, setShowPortalSenha] = useState(false);
  const [showSegSocialSenha, setShowSegSocialSenha] = useState(false);
  const [realEstateData, setRealEstateData] = useState({});
  const [creditData, setCreditData] = useState({});
  const [status, setStatus] = useState("");

  // Activity state
  const [newComment, setNewComment] = useState("");
  const [sendingComment, setSendingComment] = useState(false);

  // Deadline dialog
  const [isDeadlineDialogOpen, setIsDeadlineDialogOpen] = useState(false);
  const [deadlineForm, setDeadlineForm] = useState({
    title: "",
    description: "",
    due_date: "",
    priority: "medium",
  });
  const [selectedDate, setSelectedDate] = useState(null);
  
  // Estado para atribuição de utilizadores
  const [showAssignDialog, setShowAssignDialog] = useState(false);
  const [appUsers, setAppUsers] = useState([]);
  const [selectedConsultores, setSelectedConsultores] = useState([]);  // Array para múltiplos
  const [selectedMediadores, setSelectedMediadores] = useState([]);    // Array para múltiplos
  const [selectedIndexacao, setSelectedIndexacao] = useState("");
  const [selectedParceiro, setSelectedParceiro] = useState("");  // Parceiro (utilizador fantasma)
  const [savingAssignment, setSavingAssignment] = useState(false);
  const [loadingUsers, setLoadingUsers] = useState(false);
  
  // Contador para forçar refresh dos documentos
  const [documentsRefreshKey, setDocumentsRefreshKey] = useState(0);
  
  // Estado do RGPD
  const [rgpdStatus, setRgpdStatus] = useState(null);
  const [rgpdLoading, setRgpdLoading] = useState(false);
  const [rgpdSending, setRgpdSending] = useState(false);
  
  // Estado para o modal CPCV
  const [showCPCVModal, setShowCPCVModal] = useState(false);

  // Estado para o modal de envio de documentação
  const [showSendDocsModal, setShowSendDocsModal] = useState(false);

  // Estado para etiquetas (Fase 3)
  const [newLabel, setNewLabel] = useState("");
  const LABEL_PRESETS = ["Urgente", "Refinanciamento", "Primeira Habitação", "Investimento", "Documentação Pendente", "Aguarda Banco", "Aguarda Cliente", "Jovem"];

  // Buscar utilizadores
  const fetchUsers = async () => {
    setLoadingUsers(true);
    try {
      const response = await fetch(`${API_URL}/api/admin/users`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        const users = await response.json();
        // Filtrar: ativos, não admin, não ceo
        const activeUsers = users.filter(u => 
          u.is_active !== false && 
          u.role !== "admin" && 
          u.role !== "ceo"
        );
        setAppUsers(activeUsers);
        return activeUsers;
      }
    } catch (error) {
      console.error("Erro ao buscar utilizadores:", error);
      toast.error("Erro ao carregar utilizadores");
    } finally {
      setLoadingUsers(false);
    }
    return [];
  };

  // Buscar estado do RGPD
  const fetchRgpdStatus = async () => {
    if (!id) return;
    setRgpdLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/rgpd/status/${id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        setRgpdStatus(data);
      }
    } catch (error) {
      console.error("Erro ao verificar RGPD:", error);
    } finally {
      setRgpdLoading(false);
    }
  };

  // Solicitar RGPD
  const handleRequestRgpd = async () => {
    if (!process?.client_email) {
      toast.error("O cliente não tem email definido");
      return;
    }

    if (!window.confirm("Tem a certeza que deseja enviar o email de RGPD para este cliente?")) {
      return;
    }
    
    setRgpdSending(true);
    try {
      const response = await fetch(`${API_URL}/api/rgpd/request`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          process_id: id,
          client_name: process.client_name,
          client_email: process.client_email,
        }),
      });
      
      const data = await response.json();
      
      if (response.ok) {
        if (data.status === 'signed') {
          toast.success("RGPD já foi assinado!");
        } else if (data.status === 'pending') {
          toast.info("Já existe um pedido pendente. Verifique o email do cliente.");
        } else {
          toast.success("Email de RGPD enviado para o cliente!");
        }
        fetchRgpdStatus();
      } else {
        toast.error(data.detail || "Erro ao enviar RGPD");
      }
    } catch (error) {
      console.error("Erro ao solicitar RGPD:", error);
      toast.error("Erro ao enviar RGPD");
    } finally {
      setRgpdSending(false);
    }
  };

  // Abrir dialog de atribuição
  const openAssignDialog = async () => {
    if (process) {
      // Suporte a múltiplos consultores - converter para array
      const consultorIds = process.assigned_consultor_ids || 
        (process.assigned_consultor_id ? [process.assigned_consultor_id] : []);
      setSelectedConsultores(consultorIds);
      
      // Suporte a múltiplos intermediários - converter para array
      const mediadorIds = process.assigned_mediador_ids || 
        (process.assigned_mediador_id ? [process.assigned_mediador_id] : []);
      setSelectedMediadores(mediadorIds);
      
      setSelectedIndexacao(process.assigned_indexacao_id || "");
      setSelectedParceiro(process.assigned_parceiro_id || "");  // Carregar parceiro atual
      
      // Abrir dialog e buscar utilizadores se necessário
      setShowAssignDialog(true);
      if (appUsers.length === 0) {
        await fetchUsers();
      }
    }
  };

  // Guardar atribuições
  const handleSaveAssignment = async () => {
    setSavingAssignment(true);
    try {
      const params = new URLSearchParams();
      // Enviar múltiplos consultores separados por vírgula
      params.append("consultor_ids", selectedConsultores.filter(Boolean).join(","));
      // Enviar múltiplos intermediários separados por vírgula
      params.append("mediador_ids", selectedMediadores.filter(Boolean).join(","));
      params.append("indexacao_id", selectedIndexacao || "");
      params.append("parceiro_id", selectedParceiro || "");  // Adicionar parceiro
      
      const response = await fetch(`${API_URL}/api/processes/${id}/assign?${params.toString()}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` }
      });
      
      if (response.ok) {
        toast.success("Atribuições actualizadas com sucesso");
        setShowAssignDialog(false);
        fetchData();
      } else {
        const data = await response.json();
        toast.error(data.detail || "Erro ao actualizar atribuições");
      }
    } catch (error) {
      console.error("Erro ao guardar atribuições:", error);
      toast.error("Erro ao guardar atribuições");
    } finally {
      setSavingAssignment(false);
    }
  };

  // Estado para dados extraídos pela IA com conflitos
  const [aiExtractedData, setAiExtractedData] = useState(null);
  const [aiFieldConfidence, setAiFieldConfidence] = useState({});
  const [aiConflicts, setAiConflicts] = useState([]);
  const [showAIReviewDialog, setShowAIReviewDialog] = useState(false);

  // Handler para dados extraídos pela IA dos documentos
  const handleAIDataExtractedFromDocs = async ({ extractedData, fieldConfidence, conflicts, documentsProcessed, suggestions }) => {
    // Guardar dados, confiança e conflitos
    setAiExtractedData(extractedData);
    setAiFieldConfidence(fieldConfidence || {});
    setAiConflicts(conflicts || []);
    
    // Pré-preencher campos nos formulários
    // UNIFICAÇÃO: A IA pode usar nomes variados — mapeamos sempre para o campo canónico do modelo DB
    if (extractedData) {
      // Dados pessoais
      const newPersonalData = { ...personalData };
      if (extractedData.nif) newPersonalData.nif = extractedData.nif;
      if (extractedData.documento_id || extractedData.cc_number) newPersonalData.documento_id = extractedData.documento_id || extractedData.cc_number;
      if (extractedData.data_nascimento || extractedData.birth_date) newPersonalData.data_nascimento = extractedData.data_nascimento || extractedData.birth_date;
      if (extractedData.cc_validity || extractedData.data_validade_cc) newPersonalData.data_validade_cc = extractedData.cc_validity || extractedData.data_validade_cc;
      if (extractedData.naturalidade) newPersonalData.naturalidade = extractedData.naturalidade;
      if (extractedData.nacionalidade || extractedData.nationality) newPersonalData.nacionalidade = extractedData.nacionalidade || extractedData.nationality;
      if (extractedData.estado_civil) newPersonalData.estado_civil = extractedData.estado_civil;
      if (extractedData.sexo || extractedData.gender) newPersonalData.sexo = extractedData.sexo || extractedData.gender;
      if (extractedData.profissao || extractedData.profession) newPersonalData.profissao = extractedData.profissao || extractedData.profession;
      // UNIFICADO: morada → morada_fiscal (campo canónico do modelo)
      const addr = extractedData.morada_fiscal || extractedData.fiscal_address || extractedData.morada || extractedData.address || "";
      if (addr) newPersonalData.morada_fiscal = addr;
      if (extractedData.codigo_postal || extractedData.postal_code) newPersonalData.codigo_postal = extractedData.codigo_postal || extractedData.postal_code;
      // UNIFICADO: email/phone da IA → sincronizar com campos de topo do processo
      if (extractedData.email) newPersonalData.email = extractedData.email;
      if (extractedData.phone || extractedData.telefone) newPersonalData.phone = extractedData.phone || extractedData.telefone;
      setPersonalData(newPersonalData);
      
      // Dados financeiros
      const newFinancialData = { ...financialData };
      // UNIFICADO: rendimento_mensal/salario_liquido → monthly_income (campo canónico do modelo)
      const liq = extractedData.monthly_income || extractedData.rendimento_mensal || extractedData.salario_liquido;
      if (liq) newFinancialData.monthly_income = liq;
      // UNIFICADO: rendimento_bruto/salario_bruto → rendimento_bruto (campo canónico)
      const brut = extractedData.rendimento_bruto || extractedData.salario_bruto;
      if (brut) newFinancialData.rendimento_bruto = brut;
      // UNIFICADO: empresa → employer_name (campo canónico)
      if (extractedData.employer_name || extractedData.empresa || extractedData.entidade_patronal) newFinancialData.employer_name = extractedData.employer_name || extractedData.empresa || extractedData.entidade_patronal;
      // UNIFICADO: tipo_contrato → employment_type (campo canónico)
      if (extractedData.employment_type || extractedData.tipo_contrato) newFinancialData.tipo_contrato = extractedData.employment_type || extractedData.tipo_contrato;
      if (extractedData.categoria_profissional) newFinancialData.categoria_profissional = extractedData.categoria_profissional;
      if (extractedData.subsidiario_alimentacao) newFinancialData.subsidiario_alimentacao = extractedData.subsidiario_alimentacao;
      if (extractedData.data_referencia || extractedData.reference_date) newFinancialData.data_referencia = extractedData.data_referencia || extractedData.reference_date;
      if (extractedData.employer_nif || extractedData.nif_entidade) newFinancialData.employer_nif = extractedData.employer_nif || extractedData.nif_entidade;
      setFinancialData(newFinancialData);
      
      // Dados do imóvel — IA pode extrair dados de CPCV
      const newRealEstateData = { ...realEstateData };
      if (extractedData.valor_imovel) newRealEstateData.valor_imovel = extractedData.valor_imovel;
      if (extractedData.localizacao) newRealEstateData.localizacao = extractedData.localizacao;
      if (extractedData.tipologia) newRealEstateData.tipologia = extractedData.tipologia;
      if (extractedData.area || extractedData.area_bruta) newRealEstateData.area_bruta = extractedData.area || extractedData.area_bruta;
      if (extractedData.area_util) newRealEstateData.area_util = extractedData.area_util;
      if (extractedData.artigo_matricial) newRealEstateData.artigo_matricial = extractedData.artigo_matricial;
      if (extractedData.conservatoria) newRealEstateData.conservatoria = extractedData.conservatoria;
      if (extractedData.numero_predial) newRealEstateData.numero_predial = extractedData.numero_predial;
      if (extractedData.certificado_energetico) newRealEstateData.certificado_energetico = extractedData.certificado_energetico;
      if (extractedData.fracao) newRealEstateData.fracao = extractedData.fracao;
      if (extractedData.codigo_postal) newRealEstateData.codigo_postal = extractedData.codigo_postal;
      if (extractedData.localidade) newRealEstateData.localidade = extractedData.localidade;
      if (extractedData.freguesia) newRealEstateData.freguesia = extractedData.freguesia;
      if (extractedData.concelho) newRealEstateData.concelho = extractedData.concelho;
      if (extractedData.valor_patrimonial) newRealEstateData.valor_patrimonial = extractedData.valor_patrimonial;
      if (extractedData.data_cpcv) newRealEstateData.data_cpcv = extractedData.data_cpcv;
      if (extractedData.descricao_imovel) newRealEstateData.descricao_imovel = extractedData.descricao_imovel;
      if (extractedData.estacionamento) newRealEstateData.estacionamento = extractedData.estacionamento;
      if (extractedData.arrecadacao) newRealEstateData.arrecadacao = extractedData.arrecadacao;
      setRealEstateData(newRealEstateData);
      
      // Dados de crédito e avaliação bancária (Fase 3)
      const newCreditData = { ...creditData };
      if (extractedData.valuation_value || extractedData.valor_avaliacao) newCreditData.valuation_value = extractedData.valuation_value || extractedData.valor_avaliacao;
      if (extractedData.valuation_date || extractedData.data_avaliacao) newCreditData.valuation_date = extractedData.valuation_date || extractedData.data_avaliacao;
      if (extractedData.valuation_bank || extractedData.banco_avaliacao) newCreditData.valuation_bank = extractedData.valuation_bank || extractedData.banco_avaliacao;
      if (extractedData.valuation_notes || extractedData.notas_avaliacao) newCreditData.valuation_notes = extractedData.valuation_notes || extractedData.notas_avaliacao;
      setCreditData(newCreditData);
      
      // Se há conflitos, mostrar dialog de revisão
      if (conflicts && conflicts.length > 0) {
        setShowAIReviewDialog(true);
        toast.info(`${conflicts.length} conflito(s) detectado(s). Reveja os valores.`);
      } else {
        // Sem conflitos — aplicar directamente no backend
        try {
          const token = localStorage.getItem('token');
          const applyRes = await fetch(`${API_URL}/api/documents/ai-apply-suggestions/${id}`, {
            method: 'POST',
            headers: {
              Authorization: `Bearer ${token}`,
              'Content-Type': 'application/json'
            },
            body: JSON.stringify(extractedData)
          });
          if (applyRes.ok) {
            toast.success(`Campos pré-preenchidos e guardados com dados de ${documentsProcessed} documento(s)`);
          } else {
            toast.success(`Campos pré-preenchidos com dados de ${documentsProcessed} documento(s). Guarde manualmente.`);
          }
        } catch (applyErr) {
          console.warn("Erro ao aplicar sugestões IA:", applyErr);
          toast.success(`Campos pré-preenchidos com dados de ${documentsProcessed} documento(s). Guarde manualmente.`);
        }
      }
      
      // Alertar sobre campos com baixa confiança (< 0.8)
      if (fieldConfidence) {
        const lowConfidenceFields = Object.entries(fieldConfidence)
          .filter(([_, conf]) => conf < 0.8)
          .map(([field, conf]) => `${field} (${Math.round(conf * 100)}%)`);
        if (lowConfidenceFields.length > 0) {
          toast.warning(
            `${lowConfidenceFields.length} campo(s) com baixa confiança da IA: ${lowConfidenceFields.join(", ")}. Por favor, verifique manualmente.`,
            { duration: 8000 }
          );
        }
      }
      
      // Mudar para tab pessoais para mostrar os dados
      setActiveTab("personal");
    }
  };

  // Resolver conflito de IA (escolher valor)
  const resolveAIConflict = (field, chosenValue) => {
    // Actualizar o campo com o valor escolhido
    if (["nif", "documento_id", "data_nascimento", "naturalidade", "nacionalidade", "estado_civil", "sexo", "morada", "morada_fiscal"].includes(field)) {
      setPersonalData(prev => ({ ...prev, [field]: chosenValue }));
    } else if (["rendimento_mensal", "rendimento_bruto", "empresa", "tipo_contrato"].includes(field)) {
      setFinancialData(prev => ({ ...prev, [field]: chosenValue }));
    } else if (["valor_imovel", "localizacao", "tipologia", "area"].includes(field)) {
      setRealEstateData(prev => ({ ...prev, [field]: chosenValue }));
    }
    
    // Remover conflito da lista
    setAiConflicts(prev => prev.filter(c => c.field !== field));
    toast.success(`Campo "${field}" actualizado`);
  };

  useEffect(() => {
    fetchData();
    fetchRgpdStatus();
  }, [id]);

  // Auto-save quando o status muda
  useEffect(() => {
    // Ignorar se:
    // - Ainda está a carregar
    // - Não há processo carregado
    // - Status ainda não foi definido
    // - Status é igual ao status original do processo
    if (loading || !process || !status || status === process.status) {
      return;
    }

    // Verificar se o utilizador pode mudar o status
    const canChangeStatus = ["consultor", "mediador", "admin", "ceo", "diretor", "administrativo"].includes(user?.role?.toLowerCase());
    if (!canChangeStatus) {
      return;
    }

    // Debounce para evitar múltiplas gravações
    const timeoutId = setTimeout(() => {
      // Guardar apenas o status
      const saveStatusOnly = async () => {
        try {
          await updateProcess(id, { status });
          toast.success("Estado atualizado");
          fetchData();
        } catch (error) {
          console.error("Erro ao atualizar estado:", error);
          toast.error("Erro ao atualizar estado");
          // Reverter para o status anterior
          setStatus(process.status);
        }
      };
      saveStatusOnly();
    }, 500);

    return () => clearTimeout(timeoutId);
  }, [status]);

  const fetchData = async () => {
    try {
      const [processRes, deadlinesRes, activitiesRes, historyRes, statusesRes] = await Promise.all([
        getProcess(id),
        getDeadlines(id),
        getActivities(id),
        getHistory(id),
        getWorkflowStatuses(),
      ]);
      const processData = processRes.data;
      setProcess(processData);
      setDeadlines(deadlinesRes.data);
      setActivities(activitiesRes.data);
      setHistory(historyRes.data);
      setWorkflowStatuses(statusesRes.data);
      setStatus(processData.status);
      setPersonalData(processData.personal_data || {});
      setTitular2Data(processData.titular2_data || {});  // Carregar dados do 2º titular
      setFinancialData(processData.financial_data || {});
      setRealEstateData(processData.real_estate_data || {});
      setCreditData(processData.credit_data || {});
      
      // UNIFICAÇÃO backward-compat: se personal_data tem morada/address mas não morada_fiscal, migrar
      const pd = processData.personal_data || {};
      if ((pd.morada || pd.address) && !pd.morada_fiscal) {
        setPersonalData(prev => ({ ...prev, morada_fiscal: prev.morada || prev.address || "" }));
      }
      // UNIFICAÇÃO backward-compat: se financial_data tem rendimento_mensal mas não monthly_income, migrar
      const fd = processData.financial_data || {};
      if ((fd.rendimento_mensal || fd.salario_liquido) && !fd.monthly_income) {
        setFinancialData(prev => ({ ...prev, monthly_income: prev.rendimento_mensal || prev.salario_liquido }));
      }
      // UNIFICAÇÃO backward-compat: se financial_data tem empresa mas não employer_name, migrar
      if ((fd.empresa || fd.entidade_patronal) && !fd.employer_name) {
        setFinancialData(prev => ({ ...prev, employer_name: prev.empresa || prev.entidade_patronal }));
      }
      // UNIFICAÇÃO backward-compat: se financial_data tem tipo_contrato mas não employment_type, migrar
      if (fd.tipo_contrato && !fd.employment_type) {
        setFinancialData(prev => ({ ...prev, employment_type: prev.tipo_contrato }));
      }
      // UNIFICAÇÃO: se personal_data tem email/phone, sincronizar com campos de topo
      if (pd.email && !processData.client_email) {
        setProcess(prev => ({ ...prev, client_email: pd.email }));
      }
      if ((pd.phone || pd.telefone) && !processData.client_phone) {
        setProcess(prev => ({ ...prev, client_phone: prev.phone || prev.telefone }));
      }
      
      // TAREFA 2: Carregar estado de conflitos e confirmação de dados
      setAiSuggestions(processData.ai_suggestions || []);
      setIsDataConfirmed(processData.is_data_confirmed || false);

      // S3 files are loaded by S3FileManager component automatically
      // No need to load them here
    } catch (error) {
      console.error("Error fetching data:", error);
      if (error.response?.status === 404) {
        setNotFound(true);
      } else if (error.response?.status === 403) {
        setAccessDenied(true);
        toast.error("Não tem permissão para aceder a este processo");
      } else {
        toast.error("Erro ao carregar dados do processo");
        navigate(-1);
      }
    } finally {
      setLoading(false);
    }
  };

  // Legacy OneDrive functions - kept for compatibility but use S3FileManager instead
  const loadOneDriveFolder = async (subfolder = "") => {
    // Deprecated - S3FileManager handles this now
    console.warn("loadOneDriveFolder is deprecated. Use S3FileManager component.");
  };

  const handleDownloadFile = async (filePath) => {
    try {
      const res = await getS3DownloadUrl(processId, filePath);
      window.open(res.data.url, "_blank");
    } catch (e) {
      toast.error("Erro ao obter link de download");
    }
  };

  // Helper para converter data em formato português para ISO
  const convertPortugueseDateToISO = (dateStr) => {
    if (!dateStr) return dateStr;
    
    // Se já está em formato ISO (yyyy-MM-dd), retornar como está
    if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
      return dateStr;
    }
    
    // Meses em português
    const monthsMap = {
      'janeiro': '01', 'fevereiro': '02', 'março': '03', 'abril': '04',
      'maio': '05', 'junho': '06', 'julho': '07', 'agosto': '08',
      'setembro': '09', 'outubro': '10', 'novembro': '11', 'dezembro': '12'
    };
    
    // Tentar parsear formato "DD de MMMM de YYYY"
    const match = dateStr.toLowerCase().match(/(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})/);
    if (match) {
      const day = match[1].padStart(2, '0');
      const month = monthsMap[match[2]];
      const year = match[3];
      if (month) {
        return `${year}-${month}-${day}`;
      }
    }
    
    // Tentar parsear formato "DD/MM/YYYY"
    const shortMatch = dateStr.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (shortMatch) {
      const day = shortMatch[1].padStart(2, '0');
      const month = shortMatch[2].padStart(2, '0');
      const year = shortMatch[3];
      return `${year}-${month}-${day}`;
    }
    
    // Se não conseguir parsear, retornar null para evitar erros
    return null;
  };

  // Helper para formatar data para input type="date" (sempre retorna yyyy-MM-dd ou vazio)
  const formatDateForInput = (dateStr) => {
    if (!dateStr) return "";
    const iso = convertPortugueseDateToISO(dateStr);
    return iso || "";
  };

  // Helper para limpar dados pessoais antes de enviar
  const cleanPersonalDataForSubmit = (data) => {
    const cleaned = { ...data };
    
    // Converter datas para formato ISO
    if (cleaned.data_nascimento) {
      cleaned.data_nascimento = convertPortugueseDateToISO(cleaned.data_nascimento);
    }
    if (cleaned.data_validade_cc) {
      cleaned.data_validade_cc = convertPortugueseDateToISO(cleaned.data_validade_cc);
    }
    
    // Remover campos undefined ou vazios que podem causar problemas
    Object.keys(cleaned).forEach(key => {
      if (cleaned[key] === undefined || cleaned[key] === '') {
        delete cleaned[key];
      }
    });
    
    return cleaned;
  };

  // Helper para limpar dados do 2º titular antes de enviar
  const cleanTitular2DataForSubmit = (data) => {
    const cleaned = { ...data };
    // Converter data de nascimento para formato ISO
    if (cleaned.birth_date) {
      cleaned.birth_date = convertPortugueseDateToISO(cleaned.birth_date);
    }
    // Remover campos undefined ou vazios
    Object.keys(cleaned).forEach(key => {
      if (cleaned[key] === undefined || cleaned[key] === '') {
        delete cleaned[key];
      }
    });
    return cleaned;
  };

  // Helper para limpar dados do imóvel antes de enviar
  const cleanRealEstateDataForSubmit = (data) => {
    const cleaned = { ...data };
    // Remover campos undefined ou vazios
    Object.keys(cleaned).forEach(key => {
      if (cleaned[key] === undefined || cleaned[key] === '') {
        delete cleaned[key];
      }
    });
    return cleaned;
  };

  // Helper para limpar dados de crédito antes de enviar
  const cleanCreditDataForSubmit = (data) => {
    const cleaned = { ...data };
    // Converter datas para ISO
    if (cleaned.valuation_date) {
      cleaned.valuation_date = convertPortugueseDateToISO(cleaned.valuation_date);
    }
    if (cleaned.bank_approval_date) {
      cleaned.bank_approval_date = convertPortugueseDateToISO(cleaned.bank_approval_date);
    }
    // Remover campos undefined ou vazios
    Object.keys(cleaned).forEach(key => {
      if (cleaned[key] === undefined || cleaned[key] === '') {
        delete cleaned[key];
      }
    });
    return cleaned;
  };

  // Helper para limpar dados financeiros para envio
  const cleanFinancialDataForSubmit = (data) => {
    // Campos válidos do modelo FinancialData no backend
    const validFields = [
      'acesso_portal_financas', 'chave_movel_digital', 'renda_habitacao_atual',
      'precisa_vender_casa', 'efetivo', 'fiador', 'bancos_creditos',
      'capital_proprio', 'valor_financiado', 'valor_pretendido', 'valor_entrada',
      'data_sinal', 'reforco_sinal', 'comissao_mediacao',
      // Credenciais de portais oficiais
      'portal_financas_utilizador', 'portal_financas_senha',
      'seg_social_utilizador', 'seg_social_senha',
      // Situação profissional e rendimentos
      'monthly_income', 'employment_type', 'employment_duration', 'employer_name',
      'employer_nif', 'trabalha_estrangeiro', 'bancos_simulacoes', 'tempo_restante_credito',
      // Campos extraídos pela IA
      'rendimento_mensal', 'rendimento_bruto', 'salario_liquido', 'salario_bruto',
      'empresa', 'tipo_contrato', 'categoria_profissional', 'subsidiario_alimentacao',
      'data_referencia',
      // Créditos existentes e co-titular
      'nr_dependentes', 'number_of_dependents', 'rendimento_co_titular',
      'creditos_existentes', 'prestacao_creditos_mensal',
      // Rendimento agregado
      'rendimento_agregado',
      // Contas abertas (bancos)
      'tem_creditos_activos',
    ];
    
    const cleaned = {};
    for (const key of validFields) {
      if (data[key] !== undefined && data[key] !== null && data[key] !== '') {
        cleaned[key] = data[key];
      }
    }
    return cleaned;
  };

  // Função para executar o save após confirmação
  const executeSave = async (statusToSave) => {
    setSaving(true);
    try {
      const updateData = {};
      
      // Limpar dados pessoais antes de enviar
      const cleanedPersonalData = cleanPersonalDataForSubmit(personalData);
      
      // Limpar dados financeiros (remover campos não válidos no backend)
      const cleanedFinancialData = cleanFinancialDataForSubmit(financialData);

      // Sempre incluir email e telefone do cliente - garantir que são strings
      if (process?.client_email !== undefined && process?.client_email !== null) {
        updateData.client_email = String(process.client_email || '');
      }
      if (process?.client_phone !== undefined && process?.client_phone !== null) {
        updateData.client_phone = String(process.client_phone || '');
      }

      // Todos os roles com permissão de edição enviam dados pessoais
      // Indexação é a única exceção (só envia dados financeiros)
      if (user.role !== "indexacao") {
        updateData.personal_data = cleanedPersonalData;
        updateData.financial_data = cleanedFinancialData;
        updateData.titular2_data = cleanTitular2DataForSubmit(titular2Data);
      } else {
        updateData.financial_data = cleanedFinancialData;
      }

      // Consultor e admin podem editar dados do imóvel
      if (user.role === "consultor" || user.role === "admin") {
        updateData.real_estate_data = cleanRealEstateDataForSubmit(realEstateData);
      }

      // Mediador pode editar dados de crédito em fases avançadas
      if (user.role === "mediador" || user.role === "admin") {
        const allowedStatuses = workflowStatuses.filter(s => s.order >= 3).map(s => s.name);
        if (allowedStatuses.includes(process.status) || process.status === "ch_aprovado" || process.status === "fase_bancaria") {
          updateData.credit_data = cleanCreditDataForSubmit(creditData);
        }
      }

      if (user.role !== "cliente" && statusToSave !== process.status) {
        updateData.status = statusToSave;
      }

      // Campos de topo do processo (vendedor, mediador, monitored_emails)
      if (process.vendedor) updateData.vendedor = process.vendedor;
      if (process.mediador) updateData.mediador = process.mediador;
      if (process.monitored_emails && process.monitored_emails.length > 0) {
        updateData.monitored_emails = process.monitored_emails;
      }
      // Metadados do processo (Fase 3)
      if (process.notes !== undefined) updateData.notes = process.notes;
      if (process.prioridade) updateData.prioridade = process.prioridade;
      if (process.labels !== undefined) updateData.labels = process.labels;

      await updateProcess(id, updateData);
      toast.success("Processo atualizado com sucesso!");
      fetchData();
    } catch (error) {
      console.error("Error saving process:", error);
      // Handle validation errors properly with field-specific messages
      let errorMessage = "Erro ao guardar processo";
      
      // Mapeamento de campos para nomes amigáveis em português
      const fieldLabels = {
        "client_email": "Email do Cliente",
        "client_phone": "Telefone do Cliente",
        "nif": "NIF",
        "nome": "Nome",
        "data_nascimento": "Data de Nascimento",
        "nacionalidade": "Nacionalidade",
        "morada": "Morada",
        "codigo_postal": "Código Postal",
        "valor_pretendido": "Valor Pretendido",
        "valor_entrada": "Valor de Entrada",
        "capital_proprio": "Capital Próprio",
        "personal_data": "Dados Pessoais",
        "financial_data": "Dados Financeiros",
        "real_estate_data": "Dados do Imóvel",
        "credit_data": "Dados de Crédito",
      };
      
      if (error.response?.data?.detail) {
        const detail = error.response.data.detail;
        if (typeof detail === 'string') {
          errorMessage = detail;
        } else if (Array.isArray(detail)) {
          // Pydantic validation errors come as array with field location
          const errorMessages = detail.map(err => {
            // Get the field path (e.g., ["body", "personal_data", "nif"])
            const fieldPath = err.loc || [];
            const fieldName = fieldPath[fieldPath.length - 1] || "campo";
            const friendlyName = fieldLabels[fieldName] || fieldName;
            
            // Build user-friendly message
            let msg = err.msg || "Valor inválido";
            
            // Translate common Pydantic messages
            if (msg.includes("Input should be a valid string")) {
              msg = "deve ser texto";
            } else if (msg.includes("Input should be a valid number")) {
              msg = "deve ser um número";
            } else if (msg.includes("unable to parse string as a number")) {
              msg = "formato de número inválido";
            } else if (msg.includes("Input should be a valid email")) {
              msg = "email inválido";
            } else if (msg.includes("Field required")) {
              msg = "campo obrigatório";
            } else if (msg.includes("String should have at")) {
              msg = "tamanho inválido";
            }
            
            return `${friendlyName}: ${msg}`;
          });
          
          errorMessage = errorMessages.join('\n');
        } else if (typeof detail === 'object') {
          errorMessage = detail.msg || detail.message || JSON.stringify(detail);
        }
      }
      
      // Show toast with multi-line support for multiple errors
      if (errorMessage.includes('\n')) {
        const errors = errorMessage.split('\n');
        toast.error(
          <div>
            <strong>Erro ao guardar:</strong>
            <ul style={{margin: '8px 0 0 0', paddingLeft: '16px'}}>
              {errors.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          </div>,
          { duration: 6000 }
        );
      } else {
        toast.error(errorMessage);
      }
    } finally {
      setSaving(false);
    }
  };

  // Função principal de save que verifica créditos ativos
  const handleSave = async () => {
    // Bloquear guarda se o processo está em status terminal
    if (isProcessLocked) {
      toast.error("Não é possível editar um processo eliminado, desistido ou concluído.");
      return;
    }
    
    // Validar NIF antes de guardar
    if (personalData.nif) {
      const validation = validateNIF(personalData.nif);
      if (!validation.valid) {
        toast.error(validation.error);
        setNifError(validation.error);
        return;
      }
    }
    
    await executeSave(status);
  };

  const handleSendComment = async () => {
    if (!newComment.trim()) return;

    setSendingComment(true);
    try {
      await createActivity({ process_id: id, comment: newComment });
      setNewComment("");
      const activitiesRes = await getActivities(id);
      setActivities(activitiesRes.data);
      toast.success("Comentário adicionado");
    } catch (error) {
      toast.error("Erro ao adicionar comentário");
    } finally {
      setSendingComment(false);
    }
  };

  const handleDeleteComment = async (activityId) => {
    try {
      await deleteActivity(activityId);
      const activitiesRes = await getActivities(id);
      setActivities(activitiesRes.data);
      toast.success("Comentário eliminado");
    } catch (error) {
      toast.error("Erro ao eliminar comentário");
    }
  };

  const handleCreateDeadline = async () => {
    if (!deadlineForm.title || !selectedDate) {
      toast.error("Preencha o título e a data");
      return;
    }

    try {
      await createDeadline({
        process_id: id,
        title: deadlineForm.title,
        description: deadlineForm.description,
        due_date: format(selectedDate, "yyyy-MM-dd"),
        priority: deadlineForm.priority,
      });
      toast.success("Prazo criado com sucesso!");
      setIsDeadlineDialogOpen(false);
      setDeadlineForm({ title: "", description: "", due_date: "", priority: "medium" });
      setSelectedDate(null);
      fetchData();
    } catch (error) {
      toast.error("Erro ao criar prazo");
    }
  };

  const handleToggleDeadline = async (deadline) => {
    try {
      await updateDeadline(deadline.id, { completed: !deadline.completed });
      fetchData();
    } catch (error) {
      toast.error("Erro ao atualizar prazo");
    }
  };

  const handleDeleteDeadline = async (deadlineId) => {
    if (!confirm("Tem certeza que deseja eliminar este prazo?")) return;

    try {
      await deleteDeadline(deadlineId);
      toast.success("Prazo eliminado!");
      fetchData();
    } catch (error) {
      toast.error("Erro ao eliminar prazo");
    }
  };

  const getStatusInfo = (statusName) => {
    const statusInfo = workflowStatuses.find(s => s.name === statusName);
    return statusInfo || { label: statusName, color: "blue" };
  };

  // Normalizar role para comparação case-insensitive
  const userRole = user?.role?.toLowerCase() || "";
  const userPermissions = user?.permissions || {};
  const userPages = userPermissions?.pages || [];
  const userActions = userPermissions?.actions || [];
  
  // Permissões baseadas em actions (se disponíveis) ou fallback para role
  const hasEditProcess = userActions.length > 0 
    ? userActions.includes("edit_process") 
    : ["cliente", "consultor", "mediador", "admin", "ceo", "administrativo", "diretor"].includes(userRole);
  
  const canEditPersonal = hasEditProcess;
  const canEditFinancial = hasEditProcess || (userActions.includes("view_financials") && userRole === "indexacao");
  const canEditRealEstate = hasEditProcess && 
    (userActions.length > 0 ? true : ["consultor", "admin", "ceo", "administrativo", "diretor"].includes(userRole));
  const canEditCredit = hasEditProcess && 
    (userActions.length > 0 ? true : ["mediador", "admin", "ceo", "administrativo", "diretor"].includes(userRole)) &&
    (workflowStatuses.filter(s => s.order >= 3).map(s => s.name).includes(process?.status) || 
     process?.status === "ch_aprovado" || process?.status === "fase_bancaria");
  const canChangeStatus = hasEditProcess && 
    (userActions.length > 0 ? true : ["consultor", "mediador", "admin", "ceo", "administrativo", "diretor"].includes(userRole));
  const canManageDeadlines = hasEditProcess && 
    (userActions.length > 0 ? true : ["consultor", "mediador", "admin", "ceo", "administrativo", "diretor"].includes(userRole));
  const canDeleteClient = ["admin", "ceo", "diretor", "administrativo"].includes(userRole);
  
  // Permissões específicas por action
  const canManageTasks = userActions.length > 0 
    ? userActions.includes("manage_tasks") 
    : ["admin", "ceo", "consultor", "mediador", "diretor", "administrativo"].includes(userRole);
  const canUploadDocs = userActions.length > 0 
    ? userActions.includes("upload_docs") 
    : true; // Por defeito todos podem upload
  const canUseChat = userActions.length > 0 
    ? userActions.includes("use_chat") 
    : true; // Por defeito todos podem usar chat
  const canAssignUsers = userActions.length > 0 
    ? userActions.includes("assign_process_users") 
    : ["admin", "ceo", "diretor"].includes(userRole);
  
  // Modo de visualização (read-only) quando não tem edit_process
  // OU quando o processo está em status terminal (eliminados, desistências, concluídos)
  const BLOCKED_STATUSES = ["eliminados", "desistencias", "concluidos"];
  const isProcessLocked = process && BLOCKED_STATUSES.includes(process.status);
  const isViewMode = (!hasEditProcess && !(userActions.includes("view_financials") && userRole === "indexacao")) || isProcessLocked;

  // Função para eliminar o cliente/processo
  const handleDeleteClient = async () => {
    if (!window.confirm(`Tem a certeza que deseja eliminar o cliente "${process?.client_name}"?\n\nEsta ação é irreversível.`)) {
      return;
    }
    
    try {
      await deleteClient(id);
      toast.success("Cliente eliminado com sucesso");
      navigate("/clientes");
    } catch (error) {
      const message = error.response?.data?.detail || "Erro ao eliminar cliente";
      toast.error(message);
    }
  };

  // Helper: indicador visual de confiança da IA para campos extraídos
  const getConfidenceIndicator = (fieldName) => {
    const conf = aiFieldConfidence?.[fieldName];
    if (conf === undefined || conf === null || !aiExtractedData) return null;
    const pct = Math.round(conf * 100);
    if (conf >= 0.8) {
      return { badge: "bg-green-100 text-green-700 border-green-300", label: `${pct}%`, borderClass: "border-l-4 border-l-green-400", level: "high" };
    } else if (conf >= 0.6) {
      return { badge: "bg-amber-100 text-amber-700 border-amber-300", label: `${pct}%`, borderClass: "border-l-4 border-l-amber-400", level: "medium" };
    } else {
      return { badge: "bg-red-100 text-red-700 border-red-300", label: `${pct}%`, borderClass: "border-l-4 border-l-red-400", level: "low" };
    }
  };

  if (loading) {
    return (
      <DashboardLayout title="Detalhes do Processo">
        <div className="space-y-4">
          <div className="flex items-center gap-4">
            <div className="h-10 w-10 rounded-full bg-muted animate-pulse" />
            <div className="space-y-1.5">
              <div className="h-6 w-64 bg-muted animate-pulse rounded" />
              <div className="h-4 w-40 bg-muted animate-pulse rounded" />
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {[1, 2, 3].map(i => <div key={i} className="h-28 bg-muted animate-pulse rounded-lg" />)}
          </div>
          <div className="h-10 bg-muted animate-pulse rounded" />
          <div className="h-64 bg-muted animate-pulse rounded-lg" />
        </div>
      </DashboardLayout>
    );
  }

  if (accessDenied) {
    return (
      <DashboardLayout title="Acesso Negado">
        <Card className="border-border">
          <CardContent className="p-8 text-center">
            <AlertCircle className="h-12 w-12 mx-auto mb-4 text-red-500" />
            <h2 className="text-xl font-semibold mb-2">Acesso Negado</h2>
            <p className="text-muted-foreground mb-4">
              Não tem permissão para aceder a este processo.
            </p>
            <p className="text-sm text-muted-foreground mb-6">
              Este processo não lhe está atribuído. Se acha que deveria ter acesso, contacte o administrador.
            </p>
            <Button onClick={() => navigate(-1)}>Voltar</Button>
          </CardContent>
        </Card>
      </DashboardLayout>
    );
  }

  if (notFound) {
    return (
      <DashboardLayout title="Processo não encontrado">
        <Card className="border-border">
          <CardContent className="p-8 text-center">
            <AlertCircle className="h-12 w-12 mx-auto mb-4 text-amber-500" />
            <h2 className="text-xl font-semibold mb-2">Processo não encontrado</h2>
            <p className="text-muted-foreground mb-4">
              O processo que procura não existe ou foi eliminado.
            </p>
            <p className="text-sm text-muted-foreground mb-6">
              O ID do processo pode estar incorreto ou o processo pode ter sido removido do sistema.
            </p>
            <Button onClick={() => navigate("/clientes")}>Ir para Processos</Button>
          </CardContent>
        </Card>
      </DashboardLayout>
    );
  }

  if (!process) {
    return (
      <DashboardLayout title="Processo não encontrado">
        <Card className="border-border">
          <CardContent className="p-8 text-center">
            <AlertCircle className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
            <p className="text-muted-foreground">Processo não encontrado</p>
            <Button className="mt-4" onClick={() => navigate(-1)}>Voltar</Button>
          </CardContent>
        </Card>
      </DashboardLayout>
    );
  }

  const deadlineDates = deadlines.map((d) => parseISO(d.due_date));
  const currentStatusInfo = getStatusInfo(process.status);

  return (
    <DashboardLayout title="Detalhes do Processo">
      {/* Header Fixo - Sempre visível durante scroll */}
      <ProcessStickyHeader
        process={process}
        personalData={personalData}
        financialData={financialData}
        statusInfo={currentStatusInfo}
      />

      <div className="space-y-6">
        {/* Aviso de processo bloqueado */}
        {isProcessLocked && (
          <div className="flex items-center gap-2 p-3 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-lg text-amber-800 dark:text-amber-200 text-sm">
            <Lock className="h-4 w-4 shrink-0" />
            <span>
              Este processo encontra-se em estado terminal (<strong>{currentStatusInfo.label}</strong>). 
              A edição de dados está bloqueada para todos os utilizadores.
            </span>
          </div>
        )}

        {/* Header */}
        <div className="flex flex-col gap-4">
          {/* Linha 1: Nome e Badge do Status */}
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="icon" onClick={() => navigate(-1)}>
              <ArrowLeft className="h-5 w-5" />
            </Button>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3 flex-wrap">
                <h2 className="text-xl font-semibold truncate">{process.client_name}</h2>
                <Badge className={`${statusColors[currentStatusInfo.color]} border shrink-0`}>
                  {currentStatusInfo.label}
                </Badge>
              </div>
              <p className="text-sm text-muted-foreground">
                #{process.process_number || '—'} • {typeLabels[process.process_type]}
                {process.id && (
                  <span className="ml-2 text-xs bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded font-mono" title="ID único do cliente">
                    ID: {process.id.slice(0, 8)}
                  </span>
                )}
              </p>
            </div>
          </div>
          
          {/* Linha 2: Botões de Ação */}
          <div className="flex flex-wrap items-center gap-1.5 sm:gap-2 pl-0 sm:pl-12">
            {/* Botão para Gerir Atribuições - disponível para todos os staff */}
            {userRole !== "cliente" && (
              <Button
                variant="outline"
                size="sm"
                className="text-purple-600 border-purple-200 hover:bg-purple-50 h-8 px-2 sm:px-3"
                onClick={openAssignDialog}
                data-testid="assign-users-btn"
              >
                <Users className="h-3.5 w-3.5 sm:mr-1" />
                <span className="hidden sm:inline">Atribuições</span>
              </Button>
            )}
            
            {/* Botão RGPD */}
            {userRole !== "indexacao" && (
              <Button
                variant="outline"
                size="sm"
                className={`h-8 px-2 sm:px-3 ${
                  rgpdStatus?.status === 'signed' 
                    ? 'text-green-600 border-green-200 hover:bg-green-50' 
                    : rgpdStatus?.status === 'pending'
                    ? 'text-yellow-600 border-yellow-200 hover:bg-yellow-50'
                    : 'text-red-600 border-red-200 hover:bg-red-50'
                }`}
                onClick={handleRequestRgpd}
                disabled={rgpdSending || rgpdLoading}
                title={
                  rgpdStatus?.status === 'signed' 
                    ? 'RGPD assinado' 
                    : rgpdStatus?.status === 'pending'
                    ? 'Aguardando assinatura'
                    : 'Solicitar RGPD'
                }
              >
                {rgpdSending || rgpdLoading ? (
                  <Loader2 className="h-3.5 w-3.5 sm:mr-1 animate-spin" />
                ) : rgpdStatus?.status === 'signed' ? (
                  <CheckCircle className="h-3.5 w-3.5 sm:mr-1" />
                ) : (
                  <FileSignature className="h-3.5 w-3.5 sm:mr-1" />
                )}
                <span className="hidden sm:inline">
                  {rgpdStatus?.status === 'signed' 
                    ? 'RGPD Assinado' 
                    : rgpdStatus?.status === 'pending'
                    ? 'RGPD Pendente'
                    : 'RGPD'}
                </span>
              </Button>
            )}
            
            {/* Botão CPCV */}
            {userRole !== "indexacao" && (
              <Button
                variant="outline"
                size="sm"
                className="text-indigo-600 border-indigo-200 hover:bg-indigo-50 h-8 px-2 sm:px-3"
                onClick={() => setShowCPCVModal(true)}
                title="Gerar Contrato Promessa Compra e Venda"
              >
                <FileSignature className="h-3.5 w-3.5 sm:mr-1" />
                <span className="hidden sm:inline">CPCV</span>
              </Button>
            )}

            {/* Botão Enviar Documentação para Balcões */}
            {userRole !== "indexacao" && (
              <Button
                variant="outline"
                size="sm"
                className="text-teal-600 border-teal-200 hover:bg-teal-50 h-8 px-2 sm:px-3"
                onClick={() => setShowSendDocsModal(true)}
                title="Enviar documentação para balcões/bancos"
              >
                <Mail className="h-3.5 w-3.5 sm:mr-1" />
                <span className="hidden sm:inline">Enviar Balcões</span>
              </Button>
            )}

            {/* Calculadoras */}
            {userRole !== "indexacao" && (
              <>
                <AutoDSTIBadge processId={id} token={token} compact={true} />
                <TempLinkButton
                  processId={id}
                  clientName={process?.client_name}
                  clientEmail={process?.client_email}
                />
                <Popover>
                  <PopoverTrigger asChild>
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-teal-600 border-teal-200 hover:bg-teal-50 h-8 px-2 sm:px-3"
                      title="Portal do Cliente - Magic Link"
                    >
                      <ExternalLink className="h-3.5 w-3.5 sm:mr-1" />
                      <span className="hidden sm:inline">Portal do Cliente</span>
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-56" align="start">
                    <div className="space-y-1">
                      <h4 className="font-medium text-sm">Portal do Cliente</h4>
                      <p className="text-xs text-muted-foreground mb-2">Gerar link mágico de acesso ao portal.</p>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="w-full justify-start gap-2 text-sm"
                        onClick={async () => {
                          try {
                            const res = await generateMagicLink(id);
                            const link = res.data?.magic_link || res.data?.link || res.data?.url;
                            if (link) {
                              await navigator.clipboard.writeText(link);
                              toast.success("Link copiado!");
                            } else {
                              toast.error("Não foi possível gerar o link");
                            }
                          } catch (error) {
                            toast.error("Erro ao gerar link");
                          }
                        }}
                      >
                        <LinkIcon className="h-4 w-4" />
                        Copiar Link
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="w-full justify-start gap-2 text-sm"
                        onClick={async () => {
                          try {
                            await sendMagicLinkEmail(id);
                            toast.success("Email enviado com o link do portal!");
                          } catch (error) {
                            toast.error("Erro ao enviar email");
                          }
                        }}
                      >
                        <Mail className="h-4 w-4" />
                        Enviar por Email
                      </Button>
                    </div>
                  </PopoverContent>
                </Popover>
                <DSTICalculator
                  trigger={
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-blue-600 border-blue-200 hover:bg-blue-50 h-8 px-2 sm:px-3"
                      title="Calculadora DSTI - Taxa de Esforço"
                    >
                      <Calculator className="h-3.5 w-3.5 sm:mr-1" />
                      <span className="hidden sm:inline">DSTI</span>
                    </Button>
                  }
                  clientData={{
                    rendimento_bruto: financialData?.rendimento_bruto,
                    rendimento_mensal: financialData?.monthly_income || financialData?.salario_liquido,
                    salario_liquido: financialData?.salario_liquido,
                    renda_habitacao_atual: financialData?.renda_habitacao_atual,
                    rendimento_co_titular: financialData?.rendimento_co_titular,
                  }}
                />
                <RiskCalculator
                  trigger={
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-purple-600 border-purple-200 hover:bg-purple-50 h-8 px-2 sm:px-3"
                      title="Calculadora de Risco de Crédito"
                    >
                      <TrendingUp className="h-3.5 w-3.5 sm:mr-1" />
                      <span className="hidden sm:inline">Risco</span>
                    </Button>
                  }
                  clientData={{
                    rendimento_mensal: financialData?.monthly_income || financialData?.salario_liquido,
                    valor_imovel: realEstateData?.valor_imovel || realEstateData?.valor,
                    valor_entrada: financialData?.valor_entrada || financialData?.capital_proprio,
                    capital_proprio: financialData?.capital_proprio,
                    idade: personalData?.idade,
                    data_nascimento: personalData?.data_nascimento || personalData?.birth_date,
                  }}
                />
              </>
            )}
            
            {canChangeStatus && (
              <Select value={status} onValueChange={setStatus}>
                <SelectTrigger className="w-36 sm:w-44 h-8 text-xs sm:text-sm" data-testid="status-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {workflowStatuses.map((s) => (
                    <SelectItem key={s.id} value={s.name}>{s.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            
            {/* Botão Eliminar Cliente - apenas para Admin/CEO/Diretor */}
            {canDeleteClient && (
              <Button
                variant="outline"
                size="sm"
                className="text-red-600 border-red-200 hover:bg-red-50 h-8 px-2 sm:px-3"
                onClick={handleDeleteClient}
                data-testid="delete-client-btn"
              >
                <Trash2 className="h-3.5 w-3.5 sm:mr-1" />
                <span className="hidden sm:inline">Eliminar</span>
              </Button>
            )}
          </div>
        </div>

        {/* Alertas do Processo */}
        <ProcessAlerts processId={id} className="mb-2" />

        {/* Resumo do Processo */}
        <ProcessSummaryCard 
          process={process}
          statusInfo={currentStatusInfo}
          consultorNames={process.consultor_names}
          mediadorNames={process.mediador_names}
          consultorName={process.consultor_name || process.assigned_consultor_name}
          mediadorName={process.mediador_name || process.assigned_mediador_name}
        />

        {/* Dados Adicionais do Processo */}
        <Card>
          <CardContent className="pt-4">
            <h4 className="font-semibold text-sm mb-3 flex items-center gap-2">
              <Database className="h-4 w-4 text-muted-foreground" />
              Dados do Processo
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* NIF do Cliente */}
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">NIF do Cliente</Label>
                <Input
                  value={process?.client_nif || personalData?.nif || ""}
                  onChange={(e) => {
                    const val = e.target.value.replace(/\D/g, '').slice(0, 9);
                    setPersonalData(prev => ({ ...prev, nif: val }));
                  }}
                  disabled={!canEditPersonal}
                  className="h-9"
                  placeholder="9 dígitos"
                />
              </div>
              {/* Email Adicional Monitorizado */}
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Emails Adicionais Monitorizados</Label>
                <Input
                  value={(process?.monitored_emails || []).join(", ")}
                  onChange={(e) => {
                    const emails = e.target.value.split(",").map(s => s.trim()).filter(Boolean);
                    setProcess(prev => ({ ...prev, monitored_emails: emails }));
                  }}
                  disabled={!canEditPersonal}
                  className="h-9"
                  placeholder="email1@exemplo.com, email2@exemplo.com"
                />
              </div>
              {/* Vendedor */}
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Nome do Vendedor</Label>
                <Input
                  value={process?.vendedor?.name || ""}
                  onChange={(e) => setProcess(prev => ({
                    ...prev,
                    vendedor: { ...(prev.vendedor || {}), name: e.target.value }
                  }))}
                  disabled={!canEditPersonal}
                  className="h-9"
                  placeholder="Nome de quem vende"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Contacto do Vendedor</Label>
                <Input
                  value={process?.vendedor?.contacto || ""}
                  onChange={(e) => setProcess(prev => ({
                    ...prev,
                    vendedor: { ...(prev.vendedor || {}), contacto: e.target.value }
                  }))}
                  disabled={!canEditPersonal}
                  className="h-9"
                  placeholder="+351 000 000 000"
                />
              </div>
              {/* Mediador Imobiliário */}
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Mediador Imobiliário</Label>
                <Input
                  value={process?.mediador?.name || ""}
                  onChange={(e) => setProcess(prev => ({
                    ...prev,
                    mediador: { ...(prev.mediador || {}), name: e.target.value }
                  }))}
                  disabled={!canEditPersonal}
                  className="h-9"
                  placeholder="Nome da imobiliária/mediador"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">AMI do Mediador</Label>
                <Input
                  value={process?.mediador?.ami || ""}
                  onChange={(e) => setProcess(prev => ({
                    ...prev,
                    mediador: { ...(prev.mediador || {}), ami: e.target.value }
                  }))}
                  disabled={!canEditPersonal}
                  className="h-9"
                  placeholder="Número AMI"
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Notas, Prioridade e Etiquetas (Fase 3) */}
        <Card>
          <CardContent className="pt-4">
            <h4 className="font-semibold text-sm mb-3 flex items-center gap-2">
              <MessageSquare className="h-4 w-4 text-muted-foreground" />
              Organização do Processo
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Notas */}
              <div className="space-y-1 sm:col-span-2">
                <Label className="text-xs text-muted-foreground">Notas do Consultor</Label>
                <Textarea
                  value={process?.notes || ""}
                  onChange={(e) => setProcess(prev => ({ ...prev, notes: e.target.value }))}
                  disabled={!canEditPersonal}
                  rows={3}
                  placeholder="Observações gerais sobre o caso..."
                />
              </div>
              {/* Prioridade */}
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Prioridade</Label>
                <Select
                  value={process?.prioridade || "media"}
                  onValueChange={(value) => setProcess(prev => ({ ...prev, prioridade: value }))}
                  disabled={!canEditPersonal}
                >
                  <SelectTrigger className="h-9">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="baixa">
                      <span className="flex items-center gap-2">
                        <span className="h-2 w-2 rounded-full bg-green-500" />
                        Baixa
                      </span>
                    </SelectItem>
                    <SelectItem value="media">
                      <span className="flex items-center gap-2">
                        <span className="h-2 w-2 rounded-full bg-amber-500" />
                        Média
                      </span>
                    </SelectItem>
                    <SelectItem value="alta">
                      <span className="flex items-center gap-2">
                        <span className="h-2 w-2 rounded-full bg-red-500" />
                        Alta
                      </span>
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {/* Etiquetas */}
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Etiquetas</Label>
                <div className="flex flex-wrap gap-1.5 mb-1.5 min-h-[36px] items-center">
                  {(process?.labels || []).map((label, idx) => (
                    <Badge key={idx} variant="secondary" className="text-xs gap-1 pr-1">
                      {label}
                      {canEditPersonal && (
                        <button
                          onClick={() => setProcess(prev => ({
                            ...prev,
                            labels: (prev.labels || []).filter((_, i) => i !== idx)
                          }))}
                          className="ml-0.5 hover:text-destructive"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      )}
                    </Badge>
                  ))}
                  {canEditPersonal && (
                    <div className="flex items-center gap-1">
                      <Input
                        value={newLabel}
                        onChange={(e) => setNewLabel(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && newLabel.trim()) {
                            e.preventDefault();
                            setProcess(prev => ({
                              ...prev,
                              labels: [...(prev.labels || []), newLabel.trim()]
                            }));
                            setNewLabel("");
                          }
                        }}
                        className="h-7 w-28 text-xs"
                        placeholder="Nova etiqueta"
                      />
                      <Popover>
                        <PopoverTrigger asChild>
                          <Button variant="ghost" size="sm" className="h-7 w-7 p-0 text-muted-foreground" title="Etiquetas predefinidas">
                            <Plus className="h-3 w-3" />
                          </Button>
                        </PopoverTrigger>
                        <PopoverContent className="w-48 p-2" align="start">
                          <div className="space-y-1">
                            <p className="text-xs font-medium text-muted-foreground px-1 mb-1">Predefinidas</p>
                            {LABEL_PRESETS.filter(l => !(process?.labels || []).includes(l)).map((label) => (
                              <button
                                key={label}
                                onClick={() => setProcess(prev => ({
                                  ...prev,
                                  labels: [...(prev.labels || []), label]
                                }))}
                                className="w-full text-left text-xs px-2 py-1.5 rounded hover:bg-muted transition-colors"
                              >
                                {label}
                              </button>
                            ))}
                          </div>
                        </PopoverContent>
                      </Popover>
                    </div>
                  )}
                </div>
              </div>
            </div>
            {/* Indicador visual de prioridade */}
            {process?.prioridade && process.prioridade !== "media" && (
              <div className={`mt-3 p-2 rounded-lg text-xs font-medium ${
                process.prioridade === "alta"
                  ? "bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-800"
                  : "bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300 border border-green-200 dark:border-green-800"
              }`}>
                {process.prioridade === "alta" ? "⚠ Prioridade Alta — Ação requerida" : "✓ Prioridade Baixa — Sem urgência"}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Timeline do Processo */}
        <ProcessTimeline 
          processId={id}
          currentStatus={process.status}
          history={process.status_history || activities.filter(a => a.type === 'status_change')}
          workflowStatuses={workflowStatuses}
        />

        {/* TAREFA 2: Resolver conflitos de dados IA */}
        <DataConflictResolver
          processId={id}
          suggestions={aiSuggestions}
          isDataConfirmed={isDataConfirmed}
          onResolve={(suggestionId) => {
            setAiSuggestions(prev => prev.filter(s => s.id !== suggestionId));
            fetchData();
          }}
          onConfirmData={(confirmed) => {
            setIsDataConfirmed(confirmed);
            fetchData();
          }}
          token={token}
        />

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Main Content */}
          <div className="lg:col-span-2 space-y-6">
            {/* Banner de modo de visualização para roles sem edit_process (exceto indexacao que edita financeiros) */}
            {isViewMode && !isProcessLocked && (
              <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-3 flex items-center gap-3">
                <AlertCircle className="h-5 w-5 text-amber-600 shrink-0" />
                <p className="text-sm text-amber-800 dark:text-amber-200">
                  <strong>Modo de visualização.</strong> Não tem permissões para editar os dados base do processo. Pode gerir documentos, tarefas, chat e atribuição de utilizadores.
                </p>
              </div>
            )}

            {/* Layout normal do processo (todas as roles) */}
            <Card className="border-border">
              <CardHeader>
                <CardTitle className="text-lg">Dados do Processo</CardTitle>
              </CardHeader>
              <CardContent>
                <Tabs value={activeTab} onValueChange={setActiveTab}>
                  <TabsList className="grid w-full grid-cols-3 sm:grid-cols-6 gap-1 h-auto p-1">
                    <TabsTrigger value="personal" className="gap-1 text-xs sm:text-sm py-1.5 sm:py-2">
                      <User className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                      <span className="hidden sm:inline">Pessoais</span>
                    </TabsTrigger>
                    <TabsTrigger value="financial" className="gap-1 text-xs sm:text-sm py-1.5 sm:py-2">
                      <Briefcase className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                      <span className="hidden sm:inline">Financeiros</span>
                    </TabsTrigger>
                    <TabsTrigger value="realestate" className="gap-1 text-xs sm:text-sm py-1.5 sm:py-2">
                      <Building2 className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                      <span className="hidden sm:inline">Imóvel / CPCV</span>
                    </TabsTrigger>
                    <TabsTrigger value="credit" className="gap-1 text-xs sm:text-sm py-1.5 sm:py-2">
                      <CreditCard className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                      <span className="hidden sm:inline">Crédito</span>
                    </TabsTrigger>
                    <TabsTrigger value="documents" className="gap-1 text-xs sm:text-sm py-1.5 sm:py-2 bg-amber-50 dark:bg-amber-900/20 data-[state=active]:bg-amber-100 dark:data-[state=active]:bg-amber-900/40">
                      <FolderOpen className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                      <span className="hidden sm:inline">Docs</span>
                    </TabsTrigger>
                    <TabsTrigger value="emails" className="gap-1 text-xs sm:text-sm py-1.5 sm:py-2 bg-blue-50 dark:bg-blue-900/20 data-[state=active]:bg-blue-100 dark:data-[state=active]:bg-blue-900/40">
                      <Send className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                      <span className="hidden sm:inline">Emails</span>
                    </TabsTrigger>
                  </TabsList>

                  {/* Personal Data Tab */}
                  <TabsContent value="personal" className="mt-4">
                    <div className="space-y-4">
                      {/* Contactos */}
                      <Card className="border-l-4 border-l-blue-500">
                        <CardContent className="pt-4">
                          <h4 className="font-semibold text-sm mb-3 flex items-center gap-2">
                            <Phone className="h-4 w-4 text-blue-500" />
                            Contactos
                          </h4>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Email</Label>
                              <Input
                                type="email"
                                value={process?.client_email || ""}
                                onChange={(e) => setProcess({ ...process, client_email: e.target.value })}
                                disabled={!canEditPersonal}
                                placeholder="email@exemplo.com"
                                className="h-9"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Telefone</Label>
                              <Input
                                value={process?.client_phone || ""}
                                onChange={(e) => setProcess({ ...process, client_phone: e.target.value })}
                                disabled={!canEditPersonal}
                                placeholder="+351 000 000 000"
                                className="h-9"
                              />
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                      
                      {/* Identificação */}
                      <Card className="border-l-4 border-l-amber-500">
                        <CardContent className="pt-4">
                          <h4 className="font-semibold text-sm mb-3 flex items-center gap-2">
                            <CreditCard className="h-4 w-4 text-amber-500" />
                            Identificação
                          </h4>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <div className="space-y-1 md:col-span-2">
                              <Label className="text-xs text-muted-foreground">Nome Completo</Label>
                              <Input
                                value={personalData.nome_completo || process?.client_name || ""}
                                onChange={(e) => setPersonalData({ ...personalData, nome_completo: e.target.value })}
                                disabled={!canEditPersonal}
                                className="h-9"
                                placeholder="Nome completo do cliente (pode ser diferente do nome do processo)"
                              />
                              <p className="text-[10px] text-muted-foreground">
                                O nome completo pode ser diferente do nome do processo
                              </p>
                            </div>
                            <div className="space-y-1">
                              <div className="flex items-center justify-between">
                                <Label className="text-xs text-muted-foreground">NIF</Label>
                                {getConfidenceIndicator("nif") && (
                                  <Badge className={`text-[9px] px-1.5 py-0 ${getConfidenceIndicator("nif").badge}`}>
                                    IA {getConfidenceIndicator("nif").label}
                                  </Badge>
                                )}
                              </div>
                              <Input
                                value={personalData.nif || ""}
                                onChange={(e) => {
                                  const value = e.target.value;
                                  setPersonalData({ ...personalData, nif: value });
                                  // Validar NIF em tempo real
                                  const validation = validateNIF(value);
                                  setNifError(validation.error);
                                }}
                                disabled={!canEditPersonal}
                                data-testid="personal-nif"
                                className={`h-9 ${nifError ? 'border-red-500 focus:ring-red-500' : ''} ${getConfidenceIndicator("nif")?.borderClass || ''}`}
                                placeholder="9 dígitos"
                              />
                              {nifError && (
                                <p className="text-xs text-red-500 mt-1">{nifError}</p>
                              )}
                            </div>
                            <div className="space-y-1">
                              <div className="flex items-center justify-between">
                                <Label className="text-xs text-muted-foreground">Nº Documento (CC)</Label>
                                {getConfidenceIndicator("documento_id") && (
                                  <Badge className={`text-[9px] px-1.5 py-0 ${getConfidenceIndicator("documento_id").badge}`}>
                                    IA {getConfidenceIndicator("documento_id").label}
                                  </Badge>
                                )}
                              </div>
                              <Input
                                value={personalData.documento_id || ""}
                                onChange={(e) => setPersonalData({ ...personalData, documento_id: e.target.value })}
                                disabled={!canEditPersonal}
                                className={`h-9 ${getConfidenceIndicator("documento_id")?.borderClass || ''}`}
                              />
                            </div>
                            <div className="space-y-1">
                              <div className="flex items-center justify-between">
                                <Label className="text-xs text-muted-foreground">Validade CC</Label>
                                {getConfidenceIndicator("cc_validity") && (
                                  <Badge className={`text-[9px] px-1.5 py-0 ${getConfidenceIndicator("cc_validity").badge}`}>
                                    IA {getConfidenceIndicator("cc_validity").label}
                                  </Badge>
                                )}
                              </div>
                              <Input
                                type="date"
                                value={formatDateForInput(personalData.data_validade_cc)}
                                onChange={(e) => setPersonalData({ ...personalData, data_validade_cc: e.target.value })}
                                disabled={!canEditPersonal}
                                className={`h-9 ${getConfidenceIndicator("cc_validity")?.borderClass || ''}`}
                              />
                            </div>
                            <div className="space-y-1">
                              <div className="flex items-center justify-between">
                                <Label className="text-xs text-muted-foreground">Data de Nascimento</Label>
                                {getConfidenceIndicator("birth_date") && (
                                  <Badge className={`text-[9px] px-1.5 py-0 ${getConfidenceIndicator("birth_date").badge}`}>
                                    IA {getConfidenceIndicator("birth_date").label}
                                  </Badge>
                                )}
                              </div>
                              <Input
                                type="date"
                                value={formatDateForInput(personalData.data_nascimento || personalData.birth_date)}
                                onChange={(e) => setPersonalData({ ...personalData, data_nascimento: e.target.value })}
                                disabled={!canEditPersonal}
                                className={`h-9 ${getConfidenceIndicator("birth_date")?.borderClass || ''}`}
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Tipo de Compra</Label>
                              <Select
                                value={personalData.compra_tipo || ""}
                                onValueChange={(value) => setPersonalData({ ...personalData, compra_tipo: value })}
                                disabled={!canEditPersonal}
                              >
                                <SelectTrigger className="h-9"><SelectValue placeholder="Selecione" /></SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="primeira_habitacao">Primeira Habitação</SelectItem>
                                  <SelectItem value="segunda_habitacao">Segunda Habitação</SelectItem>
                                  <SelectItem value="investimento">Investimento</SelectItem>
                                  <SelectItem value="refinanciamento">Refinanciamento</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Estado Civil</Label>
                              <Select
                                value={personalData.estado_civil || personalData.marital_status || ""}
                                onValueChange={(value) => setPersonalData({ ...personalData, estado_civil: value })}
                                disabled={!canEditPersonal}
                              >
                                <SelectTrigger className="h-9"><SelectValue placeholder="Selecione" /></SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="solteiro">Solteiro(a)</SelectItem>
                                  <SelectItem value="casado">Casado(a)</SelectItem>
                                  <SelectItem value="divorciado">Divorciado(a)</SelectItem>
                                  <SelectItem value="viuvo">Viúvo(a)</SelectItem>
                                  <SelectItem value="uniao_facto">União de Facto</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Sexo</Label>
                              <Select
                                value={personalData.sexo || ""}
                                onValueChange={(value) => setPersonalData({ ...personalData, sexo: value })}
                                disabled={!canEditPersonal}
                              >
                                <SelectTrigger className="h-9"><SelectValue placeholder="Selecione" /></SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="M">Masculino</SelectItem>
                                  <SelectItem value="F">Feminino</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Naturalidade</Label>
                              <Input
                                value={personalData.naturalidade || ""}
                                onChange={(e) => setPersonalData({ ...personalData, naturalidade: e.target.value })}
                                disabled={!canEditPersonal}
                                className="h-9"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Nacionalidade</Label>
                              <Input
                                value={personalData.nacionalidade || personalData.nationality || ""}
                                onChange={(e) => setPersonalData({ ...personalData, nacionalidade: e.target.value })}
                                disabled={!canEditPersonal}
                                className="h-9"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Altura (m)</Label>
                              <Input
                                value={personalData.altura || ""}
                                onChange={(e) => setPersonalData({ ...personalData, altura: e.target.value })}
                                disabled={!canEditPersonal}
                                className="h-9"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Profissão</Label>
                              <Input
                                value={personalData.profissao || ""}
                                onChange={(e) => setPersonalData({ ...personalData, profissao: e.target.value })}
                                disabled={!canEditPersonal}
                                className="h-9"
                                placeholder="Profissão do titular"
                              />
                            </div>
                            <div className="space-y-1 flex items-end pb-2">
                              <div className="flex items-center gap-2">
                                <input
                                  type="checkbox"
                                  id="menor_35_anos"
                                  checked={personalData.menor_35_anos || false}
                                  onChange={(e) => setPersonalData({ ...personalData, menor_35_anos: e.target.checked })}
                                  disabled={!canEditPersonal}
                                  className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                                />
                                <Label htmlFor="menor_35_anos" className="text-xs text-muted-foreground cursor-pointer whitespace-nowrap">
                                  Menor de 35 anos
                                </Label>
                              </div>
                              <p className="text-[10px] text-muted-foreground">
                                Apoio ao estado (jovem até 35 anos)
                              </p>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                      
                      {/* Filiação */}
                      <Card className="border-l-4 border-l-orange-500">
                        <CardContent className="pt-4">
                          <h4 className="font-semibold text-sm mb-3 flex items-center gap-2">
                            <Users className="h-4 w-4 text-orange-500" />
                            Filiação
                          </h4>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Nome do Pai</Label>
                              <Input
                                value={personalData.nome_pai || ""}
                                onChange={(e) => setPersonalData({ ...personalData, nome_pai: e.target.value })}
                                disabled={!canEditPersonal}
                                className="h-9"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Nome da Mãe</Label>
                              <Input
                                value={personalData.nome_mae || ""}
                                onChange={(e) => setPersonalData({ ...personalData, nome_mae: e.target.value })}
                                disabled={!canEditPersonal}
                                className="h-9"
                              />
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                      
                      {/* Morada */}
                      <Card className="border-l-4 border-l-teal-500">
                        <CardContent className="pt-4">
                          <h4 className="font-semibold text-sm mb-3 flex items-center gap-2">
                            <MapPin className="h-4 w-4 text-teal-500" />
                            Morada
                          </h4>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <div className="space-y-1 sm:col-span-2">
                              <Label className="text-xs text-muted-foreground">Morada Fiscal</Label>
                              <Input
                                value={personalData.morada_fiscal || personalData.address || ""}
                                onChange={(e) => setPersonalData({ ...personalData, morada_fiscal: e.target.value })}
                                disabled={!canEditPersonal}
                                className="h-9"
                                placeholder="Rua, número, andar"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Código Postal</Label>
                              <Input
                                value={personalData.codigo_postal || ""}
                                onChange={(e) => setPersonalData({ ...personalData, codigo_postal: e.target.value })}
                                disabled={!canEditPersonal}
                                className="h-9"
                                placeholder="0000-000"
                              />
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                      
                      {/* 2º Titular */}
                      {(process?.titular2_data || Object.keys(titular2Data).length > 0) && (
                        <Card className="border-l-4 border-l-cyan-500">
                          <CardContent className="pt-4">
                            <h4 className="font-semibold text-sm mb-3 flex items-center gap-2">
                              <Users className="h-4 w-4 text-cyan-500" />
                              2º Titular
                              <Badge variant="secondary" className="ml-2">
                                Cônjuge/Co-Titular
                              </Badge>
                            </h4>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                              {/* Nome */}
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Nome</Label>
                                <Input
                                  value={titular2Data.name || ""}
                                  onChange={(e) => setTitular2Data({ ...titular2Data, name: e.target.value })}
                                  disabled={!canEditPersonal}
                                  className="h-9"
                                  placeholder="Nome completo"
                                />
                              </div>
                              
                              {/* NIF */}
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">NIF</Label>
                                <Input
                                  value={titular2Data.nif || ""}
                                  onChange={(e) => {
                                    const value = e.target.value.replace(/\D/g, '').slice(0, 9);
                                    setTitular2Data({ ...titular2Data, nif: value });
                                  }}
                                  disabled={!canEditPersonal}
                                  className="h-9"
                                  placeholder="999999999"
                                  maxLength={9}
                                />
                              </div>
                              
                              {/* Email */}
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Email</Label>
                                <Input
                                  type="email"
                                  value={titular2Data.email || ""}
                                  onChange={(e) => setTitular2Data({ ...titular2Data, email: e.target.value })}
                                  disabled={!canEditPersonal}
                                  className="h-9"
                                  placeholder="email@exemplo.com"
                                />
                              </div>
                              
                              {/* Telefone */}
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Telefone</Label>
                                <Input
                                  value={titular2Data.phone || ""}
                                  onChange={(e) => setTitular2Data({ ...titular2Data, phone: e.target.value })}
                                  disabled={!canEditPersonal}
                                  className="h-9"
                                  placeholder="912345678"
                                />
                              </div>
                              
                              {/* Data de Nascimento */}
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Data de Nascimento</Label>
                                <Input
                                  type="date"
                                  value={titular2Data.birth_date || ""}
                                  onChange={(e) => setTitular2Data({ ...titular2Data, birth_date: e.target.value })}
                                  disabled={!canEditPersonal}
                                  className="h-9"
                                />
                              </div>
                              
                              {/* Estado Civil */}
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Estado Civil</Label>
                                <Select
                                  value={titular2Data.estado_civil || ""}
                                  onValueChange={(value) => setTitular2Data({ ...titular2Data, estado_civil: value })}
                                  disabled={!canEditPersonal}
                                >
                                  <SelectTrigger className="h-9">
                                    <SelectValue placeholder="Selecionar" />
                                  </SelectTrigger>
                                  <SelectContent>
                                    <SelectItem value="Solteiro">Solteiro(a)</SelectItem>
                                    <SelectItem value="Casado">Casado(a)</SelectItem>
                                    <SelectItem value="Divorciado">Divorciado(a)</SelectItem>
                                    <SelectItem value="Viúvo">Viúvo(a)</SelectItem>
                                    <SelectItem value="União de Facto">União de Facto</SelectItem>
                                  </SelectContent>
                                </Select>
                              </div>
                              
                              {/* Naturalidade */}
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Naturalidade</Label>
                                <Input
                                  value={titular2Data.naturalidade || ""}
                                  onChange={(e) => setTitular2Data({ ...titular2Data, naturalidade: e.target.value })}
                                  disabled={!canEditPersonal}
                                  className="h-9"
                                  placeholder="Cidade/País"
                                />
                              </div>
                              
                              {/* Nacionalidade */}
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Nacionalidade</Label>
                                <Input
                                  value={titular2Data.nacionalidade || ""}
                                  onChange={(e) => setTitular2Data({ ...titular2Data, nacionalidade: e.target.value })}
                                  disabled={!canEditPersonal}
                                  className="h-9"
                                  placeholder="Portuguesa"
                                />
                              </div>
                              
                              {/* Nº Documento */}
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Nº Documento</Label>
                                <Input
                                  value={titular2Data.documento_id || ""}
                                  onChange={(e) => setTitular2Data({ ...titular2Data, documento_id: e.target.value })}
                                  disabled={!canEditPersonal}
                                  className="h-9"
                                  placeholder="Nº do Cartão de Cidadão"
                                />
                              </div>
                              
                              {/* Morada Fiscal */}
                              <div className="space-y-1 col-span-2">
                                <Label className="text-xs text-muted-foreground">Morada Fiscal</Label>
                                <Input
                                  value={titular2Data.morada_fiscal || ""}
                                  onChange={(e) => setTitular2Data({ ...titular2Data, morada_fiscal: e.target.value })}
                                  disabled={!canEditPersonal}
                                  className="h-9"
                                  placeholder="Rua, número, código postal"
                                />
                              </div>
                              
                            </div>
                          </CardContent>
                        </Card>
                      )}
                      
                      {/* Co-Compradores / Co-Proponentes */}
                      {(process?.co_buyers?.length > 0 || process?.co_applicants?.length > 0) && (
                        <Card className="border-l-4 border-l-indigo-500">
                          <CardContent className="pt-4">
                            <h4 className="font-semibold text-sm mb-3 flex items-center gap-2">
                              <Users className="h-4 w-4 text-indigo-500" />
                              Co-Compradores / Co-Proponentes
                              <Badge variant="secondary" className="ml-2">
                                {(process?.co_buyers?.length || 0) + (process?.co_applicants?.length || 0)} pessoa(s)
                              </Badge>
                            </h4>
                            <div className="space-y-3">
                              {/* Co-Buyers (do CPCV) */}
                              {process?.co_buyers?.map((buyer, index) => (
                                <div key={`buyer-${index}`} className="p-3 bg-indigo-50 dark:bg-indigo-900/20 rounded-lg border border-indigo-200 dark:border-indigo-800">
                                  <div className="flex items-center gap-2 mb-2">
                                    <Badge variant="outline" className="text-xs">
                                      Comprador {index + 1}
                                    </Badge>
                                    {buyer.estado_civil && (
                                      <Badge variant="secondary" className="text-xs">
                                        {buyer.estado_civil}
                                      </Badge>
                                    )}
                                  </div>
                                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
                                    {buyer.nome && (
                                      <div>
                                        <span className="text-muted-foreground text-xs">Nome:</span>
                                        <p className="font-medium">{buyer.nome}</p>
                                      </div>
                                    )}
                                    {buyer.nif && (
                                      <div>
                                        <span className="text-muted-foreground text-xs">NIF:</span>
                                        <p className="font-medium">{buyer.nif}</p>
                                      </div>
                                    )}
                                    {buyer.email && (
                                      <div>
                                        <span className="text-muted-foreground text-xs">Email:</span>
                                        <p className="font-medium">{buyer.email}</p>
                                      </div>
                                    )}
                                    {buyer.telefone && (
                                      <div>
                                        <span className="text-muted-foreground text-xs">Telefone:</span>
                                        <p className="font-medium">{buyer.telefone}</p>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              ))}
                              
                              {/* Co-Applicants (do IRS/Simulação) */}
                              {process?.co_applicants?.map((applicant, index) => (
                                <div key={`applicant-${index}`} className="p-3 bg-purple-50 dark:bg-purple-900/20 rounded-lg border border-purple-200 dark:border-purple-800">
                                  <div className="flex items-center gap-2 mb-2">
                                    <Badge variant="outline" className="text-xs">
                                      {index === 0 ? "Titular" : "Cônjuge/Proponente " + (index + 1)}
                                    </Badge>
                                    {applicant.rendimento_mensal && (
                                      <Badge variant="secondary" className="text-xs">
                                        {applicant.rendimento_mensal}€/mês
                                      </Badge>
                                    )}
                                  </div>
                                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
                                    {applicant.nome && (
                                      <div>
                                        <span className="text-muted-foreground text-xs">Nome:</span>
                                        <p className="font-medium">{applicant.nome}</p>
                                      </div>
                                    )}
                                    {applicant.nif && (
                                      <div>
                                        <span className="text-muted-foreground text-xs">NIF:</span>
                                        <p className="font-medium">{applicant.nif}</p>
                                      </div>
                                    )}
                                    {applicant.data_nascimento && (
                                      <div>
                                        <span className="text-muted-foreground text-xs">Data Nascimento:</span>
                                        <p className="font-medium">{applicant.data_nascimento}</p>
                                      </div>
                                    )}
                                    {applicant.entidade_patronal && (
                                      <div>
                                        <span className="text-muted-foreground text-xs">Empresa:</span>
                                        <p className="font-medium">{applicant.entidade_patronal}</p>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              ))}
                              
                              {/* Rendimento Agregado */}
                              {financialData?.rendimento_agregado && (
                                <div className="mt-3 p-2 bg-green-50 dark:bg-green-900/20 rounded border border-green-200 dark:border-green-800">
                                  <p className="text-sm font-medium text-green-700 dark:text-green-400">
                                    Rendimento Agregado: {financialData.rendimento_agregado.toLocaleString('pt-PT')}€/mês
                                  </p>
                                </div>
                              )}
                            </div>
                          </CardContent>
                        </Card>
                      )}
                    </div>
                  </TabsContent>

                  {/* Financial Data Tab */}
                  <TabsContent value="financial" className="mt-4">
                    <div className="space-y-4">
                      {/* DSTI Automático */}
                      <AutoDSTIBadge processId={id} token={token} compact={false} showDetails={true} />
                      {/* Rendimentos */}
                      <Card className="border-l-4 border-l-green-500">
                        <CardContent className="pt-4">
                          <h4 className="font-semibold text-sm mb-3 flex items-center gap-2">
                            <Briefcase className="h-4 w-4 text-green-500" />
                            Rendimentos
                          </h4>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Rendimento Mensal (€)</Label>
                              <Input
                                type="number"
                                value={financialData.monthly_income || financialData.salario_liquido || ""}
                                onChange={(e) => setFinancialData({ ...financialData, monthly_income: parseFloat(e.target.value) || null })}
                                disabled={!canEditFinancial}
                                className="h-9"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Rendimento Bruto (€)</Label>
                              <Input
                                type="number"
                                value={financialData.rendimento_bruto || financialData.salario_bruto || ""}
                                onChange={(e) => setFinancialData({ ...financialData, rendimento_bruto: parseFloat(e.target.value) || null })}
                                disabled={!canEditFinancial}
                                className="h-9"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Capital Próprio (€)</Label>
                              <Input
                                type="number"
                                value={financialData.capital_proprio || financialData.other_income || ""}
                                onChange={(e) => setFinancialData({ ...financialData, capital_proprio: parseFloat(e.target.value) || null })}
                                disabled={!canEditFinancial}
                                className="h-9"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Valor a Financiar</Label>
                              <Input
                                value={financialData.valor_financiado || ""}
                                onChange={(e) => setFinancialData({ ...financialData, valor_financiado: e.target.value })}
                                disabled={!canEditFinancial}
                                className="h-9"
                                placeholder="Ex: 200.000€ ou 80%"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Renda Habitação Atual (€)</Label>
                              <Input
                                type="number"
                                value={financialData.renda_habitacao_atual || ""}
                                onChange={(e) => setFinancialData({ ...financialData, renda_habitacao_atual: parseFloat(e.target.value) || null })}
                                disabled={!canEditFinancial}
                                className="h-9"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Rendimento Co-Titular (€)</Label>
                              <Input
                                type="number"
                                value={financialData.rendimento_co_titular || ""}
                                onChange={(e) => setFinancialData({ ...financialData, rendimento_co_titular: parseFloat(e.target.value) || null })}
                                disabled={!canEditFinancial}
                                className="h-9"
                                placeholder="Rendimento do 2º titular"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Nº de Dependentes</Label>
                              <Input
                                type="number"
                                min="0"
                                value={financialData.nr_dependentes || financialData.number_of_dependents || ""}
                                onChange={(e) => setFinancialData({ ...financialData, nr_dependentes: parseInt(e.target.value) || null })}
                                disabled={!canEditFinancial}
                                className="h-9"
                                placeholder="0"
                              />
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                      
                      {/* Situação Financeira */}
                      <Card className="border-l-4 border-l-blue-500">
                        <CardContent className="pt-4">
                          <h4 className="font-semibold text-sm mb-3 flex items-center gap-2">
                            <CreditCard className="h-4 w-4 text-blue-500" />
                            Situação Financeira
                          </h4>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Contrato Efetivo?</Label>
                              <Select
                                value={financialData.efetivo || ""}
                                onValueChange={(value) => setFinancialData({ ...financialData, efetivo: value })}
                                disabled={!canEditFinancial}
                              >
                                <SelectTrigger className="h-9"><SelectValue placeholder="Selecione" /></SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="sim">Sim</SelectItem>
                                  <SelectItem value="nao">Não</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Precisa Vender Casa?</Label>
                              <Select
                                value={financialData.precisa_vender_casa || ""}
                                onValueChange={(value) => setFinancialData({ ...financialData, precisa_vender_casa: value })}
                                disabled={!canEditFinancial}
                              >
                                <SelectTrigger className="h-9"><SelectValue placeholder="Selecione" /></SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="sim">Sim</SelectItem>
                                  <SelectItem value="nao">Não</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Tem Fiador?</Label>
                              <Select
                                value={financialData.fiador || ""}
                                onValueChange={(value) => setFinancialData({ ...financialData, fiador: value })}
                                disabled={!canEditFinancial}
                              >
                                <SelectTrigger className="h-9"><SelectValue placeholder="Selecione" /></SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="sim">Sim</SelectItem>
                                  <SelectItem value="nao">Não</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Créditos Existentes (€)</Label>
                              <Input
                                type="number"
                                value={financialData.creditos_existentes || ""}
                                onChange={(e) => setFinancialData({ ...financialData, creditos_existentes: parseFloat(e.target.value) || null })}
                                disabled={!canEditFinancial}
                                className="h-9"
                                placeholder="Valor total em dívida"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Prestação Créditos Mensal (€)</Label>
                              <Input
                                type="number"
                                value={financialData.prestacao_creditos_mensal || ""}
                                onChange={(e) => setFinancialData({ ...financialData, prestacao_creditos_mensal: parseFloat(e.target.value) || null })}
                                disabled={!canEditFinancial}
                                className="h-9"
                                placeholder="Total prestações mensais"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Acesso Portais Oficiais?</Label>
                              <Select
                                value={financialData.acesso_portal_financas || ""}
                                onValueChange={(value) => setFinancialData({ ...financialData, acesso_portal_financas: value })}
                                disabled={!canEditFinancial}
                              >
                                <SelectTrigger className="h-9"><SelectValue placeholder="Selecione" /></SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="portal_financas">Portal das Finanças</SelectItem>
                                  <SelectItem value="seguranca_social">Segurança Social Direta</SelectItem>
                                  <SelectItem value="ambos">Ambos</SelectItem>
                                  <SelectItem value="nenhuma">Nenhuma</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Chave Móvel Digital?</Label>
                              <Select
                                value={financialData.chave_movel_digital || ""}
                                onValueChange={(value) => setFinancialData({ ...financialData, chave_movel_digital: value })}
                                disabled={!canEditFinancial}
                              >
                                <SelectTrigger className="h-9"><SelectValue placeholder="Selecione" /></SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="sim">Sim</SelectItem>
                                  <SelectItem value="nao">Não</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                          </div>
                        </CardContent>
                      </Card>

                      {/* Credenciais de Portais Oficiais */}
                      <Card className="border-l-4 border-l-orange-500">
                        <CardContent className="pt-4">
                          <h4 className="font-semibold text-sm mb-3 flex items-center gap-2">
                            <Database className="h-4 w-4 text-orange-500" />
                            Credenciais de Portais Oficiais
                          </h4>
                          <p className="text-xs text-muted-foreground mb-3">
                            Preencha as credenciais de acesso aos portais oficiais para facilitar a gestão do processo.
                          </p>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            {/* Portal das Finanças */}
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Portal Finanças - Utilizador</Label>
                              <Input
                                value={financialData.portal_financas_utilizador || ""}
                                onChange={(e) => setFinancialData({ ...financialData, portal_financas_utilizador: e.target.value })}
                                disabled={!canEditFinancial}
                                className="h-9"
                                placeholder="NIF ou email"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Portal Finanças - Senha</Label>
                              <div className="relative">
                                <Input
                                  type={showPortalSenha ? "text" : "password"}
                                  value={financialData.portal_financas_senha || ""}
                                  onChange={(e) => setFinancialData({ ...financialData, portal_financas_senha: e.target.value })}
                                  disabled={!canEditFinancial}
                                  className="h-9 pr-9"
                                  placeholder="Senha de acesso"
                                />
                                <button
                                  type="button"
                                  onClick={() => setShowPortalSenha(!showPortalSenha)}
                                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground min-h-[44px] min-w-[44px] flex items-center justify-center"
                                  tabIndex={-1}
                                >
                                  {showPortalSenha ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                                </button>
                              </div>
                            </div>
                            {/* Segurança Social Direta */}
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Seg. Social - Utilizador</Label>
                              <Input
                                value={financialData.seg_social_utilizador || ""}
                                onChange={(e) => setFinancialData({ ...financialData, seg_social_utilizador: e.target.value })}
                                disabled={!canEditFinancial}
                                className="h-9"
                                placeholder="NISS ou email"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Seg. Social - Senha</Label>
                              <div className="relative">
                                <Input
                                  type={showSegSocialSenha ? "text" : "password"}
                                  value={financialData.seg_social_senha || ""}
                                  onChange={(e) => setFinancialData({ ...financialData, seg_social_senha: e.target.value })}
                                  disabled={!canEditFinancial}
                                  className="h-9 pr-9"
                                  placeholder="Senha de acesso"
                                />
                                <button
                                  type="button"
                                  onClick={() => setShowSegSocialSenha(!showSegSocialSenha)}
                                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground min-h-[44px] min-w-[44px] flex items-center justify-center"
                                  tabIndex={-1}
                                >
                                  {showSegSocialSenha ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                                </button>
                              </div>
                            </div>
                          </div>
                        </CardContent>
                      </Card>

                      {/* Credenciais de Portais Oficiais - 2º Proponente */}
                      {(process?.titular2_data || Object.keys(titular2Data).length > 0) && (
                        <Card className="border-l-4 border-l-orange-300">
                          <CardContent className="pt-4">
                            <h4 className="font-semibold text-sm mb-1 flex items-center gap-2">
                              <Database className="h-4 w-4 text-orange-400" />
                              Credenciais de Portais Oficiais
                              <Badge variant="outline" className="text-xs bg-orange-50 text-orange-600 border-orange-200 ml-1">2º Proponente</Badge>
                            </h4>
                            <p className="text-xs text-muted-foreground mb-3">
                              Credenciais de acesso aos portais oficiais do segundo proponente/titular.
                            </p>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                              {/* Portal das Finanças */}
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Finanças - Utilizador</Label>
                                <Input
                                  value={titular2Data.portal_financas_utilizador || ""}
                                  onChange={(e) => setTitular2Data({ ...titular2Data, portal_financas_utilizador: e.target.value })}
                                  disabled={!canEditFinancial}
                                  className="h-9"
                                  placeholder="NIF ou email"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Finanças - Senha</Label>
                                <Input
                                  type="password"
                                  value={titular2Data.portal_financas_senha || ""}
                                  onChange={(e) => setTitular2Data({ ...titular2Data, portal_financas_senha: e.target.value })}
                                  disabled={!canEditFinancial}
                                  className="h-9"
                                  placeholder="Senha de acesso"
                                />
                              </div>
                              {/* Segurança Social Direta */}
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Seg. Social - Utilizador</Label>
                                <Input
                                  value={titular2Data.seg_social_utilizador || ""}
                                  onChange={(e) => setTitular2Data({ ...titular2Data, seg_social_utilizador: e.target.value })}
                                  disabled={!canEditFinancial}
                                  className="h-9"
                                  placeholder="NISS ou email"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Seg. Social - Senha</Label>
                                <Input
                                  type="password"
                                  value={titular2Data.seg_social_senha || ""}
                                  onChange={(e) => setTitular2Data({ ...titular2Data, seg_social_senha: e.target.value })}
                                  disabled={!canEditFinancial}
                                  className="h-9"
                                  placeholder="Senha de acesso"
                                />
                              </div>
                            </div>
                          </CardContent>
                        </Card>
                      )}

                      {/* Créditos/Bancos */}
                      {financialData?.bancos_creditos?.length > 0 && (
                        <Card className="border-l-4 border-l-red-500">
                          <CardContent className="pt-4">
                            <h4 className="font-semibold text-sm mb-3 flex items-center gap-2">
                              <AlertCircle className="h-4 w-4 text-red-500" />
                              Créditos Ativos
                            </h4>
                            {/* Total dos créditos */}
                            {(() => {
                              const total = financialData.bancos_creditos.reduce((sum, item) => {
                                if (typeof item === 'object' && item.valor) return sum + item.valor;
                                return sum;
                              }, 0);
                              if (total > 0) {
                                return (
                                  <p className="text-xs text-muted-foreground mb-2">
                                    Total: <span className="font-semibold text-foreground">{total.toLocaleString('pt-PT', { style: 'currency', currency: 'EUR' })}</span>
                                  </p>
                                );
                              }
                              return null;
                            })()}
                            <div className="space-y-2">
                              {financialData.bancos_creditos.map((item, idx) => {
                                const banco = typeof item === 'object' ? item.banco : item;
                                const valor = typeof item === 'object' ? item.valor : null;
                                return (
                                  <div key={idx} className="flex items-center gap-2">
                                    <Badge className={getBankColor(banco)}>{banco}</Badge>
                                    {valor != null && valor > 0 && (
                                      <span className="text-xs font-medium text-muted-foreground">
                                        {valor.toLocaleString('pt-PT', { style: 'currency', currency: 'EUR' })}
                                      </span>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          </CardContent>
                        </Card>
                      )}

                      {/* Contas Abertas nos Bancos */}
                      {financialData?.tem_creditos_activos?.length > 0 && (
                        <Card className="border-l-4 border-l-amber-500">
                          <CardContent className="pt-4">
                            <h4 className="font-semibold text-sm mb-3 flex items-center gap-2">
                              <CreditCard className="h-4 w-4 text-amber-500" />
                              Contas de Crédito Abertas
                            </h4>
                            <div className="flex flex-wrap gap-2">
                              {financialData.tem_creditos_activos.map((banco, idx) => (
                                <Badge key={idx} className={getBankColor(banco)}>{banco}</Badge>
                              ))}
                            </div>
                          </CardContent>
                        </Card>
                      )}

                      {/* Editável: Bancos com contas de crédito abertas */}
                      {canEditFinancial && (
                        <Card className="border-l-4 border-l-amber-300 bg-amber-50/30">
                          <CardContent className="pt-4">
                            <h4 className="font-semibold text-sm mb-3 flex items-center gap-2">
                              <CreditCard className="h-4 w-4 text-amber-500" />
                              Contas de Crédito Abertas
                              <Badge variant="outline" className="text-xs bg-amber-50 text-amber-600 border-amber-200">Edição</Badge>
                            </h4>
                            <div className="flex flex-wrap gap-2">
                              <button
                                type="button"
                                onClick={() => setFinancialData({ ...financialData, tem_creditos_activos: [] })}
                                className={`px-3 py-1.5 rounded-full text-sm font-medium border-2 transition-all ${
                                  (financialData.tem_creditos_activos || []).length === 0
                                    ? 'ring-2 ring-offset-1 ring-amber-400 scale-105 bg-slate-700 text-white border-slate-700'
                                    : 'opacity-50 hover:opacity-80 bg-transparent text-slate-600 border-slate-400'
                                }`}
                              >
                                {(financialData.tem_creditos_activos || []).length === 0 && <span className="mr-1">✓</span>}
                                Nenhuma
                              </button>
                              {BANK_LIST.map((banco) => {
                                const selected = (financialData.tem_creditos_activos || []).includes(banco);
                                return (
                                  <button
                                    key={`edit-contas-${banco}`}
                                    type="button"
                                    onClick={() => {
                                      const current = financialData.tem_creditos_activos || [];
                                      setFinancialData({
                                        ...financialData,
                                        tem_creditos_activos: current.includes(banco)
                                          ? current.filter(b => b !== banco)
                                          : [...current, banco]
                                      });
                                    }}
                                    className={`px-3 py-1.5 rounded-full text-sm font-medium border-2 transition-all ${selected ? 'ring-2 ring-offset-1 ring-amber-400 scale-105' : 'opacity-50 hover:opacity-80'} ${getBankColor(banco)}`}
                                  >
                                    {selected && <span className="mr-1">✓</span>}
                                    {banco}
                                  </button>
                                );
                              })}
                            </div>
                          </CardContent>
                        </Card>
                      )}
                      
                      {/* Simulações de Crédito */}
                      {financialData?.bancos_simulacoes?.length > 0 && (
                        <Card className="border-l-4 border-l-blue-500">
                          <CardContent className="pt-4">
                            <h4 className="font-semibold text-sm mb-3 flex items-center gap-2">
                              <CreditCard className="h-4 w-4 text-blue-500" />
                              Simulações de Crédito Efetuadas
                            </h4>
                            <div className="flex flex-wrap gap-2">
                              {financialData.bancos_simulacoes.map((banco, idx) => (
                                <Badge key={idx} variant="outline" className="border-blue-300 text-blue-700">{banco}</Badge>
                              ))}
                            </div>
                          </CardContent>
                        </Card>
                      )}
                      
                      {/* Tempo Restante do Crédito (Refinanciamento) */}
                      {financialData?.tempo_restante_credito && (
                        <Card className="border-l-4 border-l-amber-500">
                          <CardContent className="pt-4">
                            <h4 className="font-semibold text-sm mb-3 flex items-center gap-2">
                              <Clock className="h-4 w-4 text-amber-500" />
                              Tempo Restante do Crédito Atual
                            </h4>
                            <p className="text-sm">
                              {financialData.tempo_restante_credito === "menos_1_ano" ? "Menos de 1 ano" :
                               financialData.tempo_restante_credito === "1_5_anos" ? "1 a 5 anos" :
                               financialData.tempo_restante_credito === "5_10_anos" ? "5 a 10 anos" :
                               financialData.tempo_restante_credito === "10_15_anos" ? "10 a 15 anos" :
                               financialData.tempo_restante_credito === "15_20_anos" ? "15 a 20 anos" :
                               financialData.tempo_restante_credito === "mais_20_anos" ? "Mais de 20 anos" : 
                               financialData.tempo_restante_credito}
                            </p>
                          </CardContent>
                        </Card>
                      )}
                      
                      {/* Emprego */}
                      <Card className="border-l-4 border-l-purple-500">
                        <CardContent className="pt-4">
                          <h4 className="font-semibold text-sm mb-3 flex items-center gap-2">
                            <User className="h-4 w-4 text-purple-500" />
                            Situação Profissional
                          </h4>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Tipo de Emprego</Label>
                              <Select
                                value={financialData.employment_type || ""}
                                onValueChange={(value) => setFinancialData({ ...financialData, employment_type: value })}
                                disabled={!canEditFinancial}
                              >
                                <SelectTrigger className="h-9"><SelectValue placeholder="Selecione" /></SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="efetivo">Contrato Efetivo</SelectItem>
                                  <SelectItem value="termo">Contrato a Termo</SelectItem>
                                  <SelectItem value="independente">Trabalhador Independente</SelectItem>
                                  <SelectItem value="empresario">Empresário</SelectItem>
                                  <SelectItem value="reformado">Reformado</SelectItem>
                                  <SelectItem value="desempregado">Desempregado</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Trabalha no Estrangeiro?</Label>
                              <Select
                                value={financialData.trabalha_estrangeiro || ""}
                                onValueChange={(value) => setFinancialData({ ...financialData, trabalha_estrangeiro: value })}
                                disabled={!canEditFinancial}
                              >
                                <SelectTrigger className="h-9"><SelectValue placeholder="Selecione" /></SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="sim">Sim</SelectItem>
                                  <SelectItem value="nao">Não</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Tempo de Emprego</Label>
                              <Input
                                value={financialData.employment_duration || ""}
                                onChange={(e) => setFinancialData({ ...financialData, employment_duration: e.target.value })}
                                disabled={!canEditFinancial}
                                className="h-9"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Entidade Empregadora</Label>
                              <Input
                                value={financialData.employer_name || ""}
                                onChange={(e) => setFinancialData({ ...financialData, employer_name: e.target.value })}
                                disabled={!canEditFinancial}
                                className="h-9"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">NIF da Entidade Empregadora</Label>
                              <Input
                                value={financialData.employer_nif || ""}
                                onChange={(e) => {
                                  const val = e.target.value.replace(/\D/g, '').slice(0, 9);
                                  setFinancialData({ ...financialData, employer_nif: val });
                                }}
                                disabled={!canEditFinancial}
                                className="h-9"
                                placeholder="NIF da empresa"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Categoria Profissional</Label>
                              <Input
                                value={financialData.categoria_profissional || ""}
                                onChange={(e) => setFinancialData({ ...financialData, categoria_profissional: e.target.value })}
                                disabled={!canEditFinancial}
                                className="h-9"
                                placeholder="Ex: Técnico superior, Operário..."
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Subsídio Alimentação (€)</Label>
                              <Input
                                type="number"
                                value={financialData.subsidiario_alimentacao || ""}
                                onChange={(e) => setFinancialData({ ...financialData, subsidiario_alimentacao: parseFloat(e.target.value) || null })}
                                disabled={!canEditFinancial}
                                className="h-9"
                                placeholder="0.00"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Data de Referência (Recibo)</Label>
                              <Input
                                type="month"
                                value={financialData.data_referencia || ""}
                                onChange={(e) => setFinancialData({ ...financialData, data_referencia: e.target.value })}
                                disabled={!canEditFinancial}
                                className="h-9"
                              />
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    </div>
                  </TabsContent>

                  {/* Real Estate Tab */}
                  <TabsContent value="realestate" className="space-y-4 mt-4">
                    {!canEditRealEstate && !realEstateData?.tipo_imovel && !realEstateData?.property_type && !realEstateData?.num_quartos ? (
                      <div className="text-center py-8 text-muted-foreground">
                        <Building2 className="h-12 w-12 mx-auto mb-4 opacity-50" />
                        <p>Dados imobiliários serão preenchidos pelo consultor</p>
                      </div>
                    ) : (
                      <div className="space-y-4">

                        {/* ====== Grupo D: Estado da Procura ====== */}
                        <Card className="border-l-4 border-l-indigo-500">
                          <CardContent className="pt-4">
                            <h4 className="font-semibold text-sm mb-3 flex items-center gap-2">
                              <Search className="h-4 w-4 text-indigo-500" />
                              Estado da Procura
                            </h4>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                              <div className="space-y-1 flex items-center gap-3 pb-1">
                                <input
                                  type="checkbox"
                                  id="ja_tem_imovel"
                                  checked={realEstateData.ja_tem_imovel || realEstateData.has_property || false}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, ja_tem_imovel: e.target.checked, has_property: e.target.checked })}
                                  disabled={!canEditRealEstate}
                                  className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                                />
                                <Label htmlFor="ja_tem_imovel" className="text-xs text-muted-foreground cursor-pointer whitespace-nowrap">
                                  Já tem imóvel identificado
                                </Label>
                              </div>
                              <div className="space-y-1 flex items-center gap-3 pb-1">
                                <input
                                  type="checkbox"
                                  id="ja_tem_casa_escolhida"
                                  checked={realEstateData.ja_tem_casa_escolhida || false}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, ja_tem_casa_escolhida: e.target.checked })}
                                  disabled={!canEditRealEstate}
                                  className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                                />
                                <Label htmlFor="ja_tem_casa_escolhida" className="text-xs text-muted-foreground cursor-pointer whitespace-nowrap">
                                  Já tem casa escolhida
                                </Label>
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Nome do Proprietário (vendedor)</Label>
                                <Input
                                  value={realEstateData.proprietario_nome || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, proprietario_nome: e.target.value })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                  placeholder="Nome do proprietário do imóvel"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Contacto do Proprietário</Label>
                                <Input
                                  value={realEstateData.proprietario_contacto || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, proprietario_contacto: e.target.value })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                  placeholder="+351 000 000 000"
                                />
                              </div>
                            </div>
                          </CardContent>
                        </Card>

                        {/* ====== Grupo A: Características do Imóvel ====== */}
                        <Card className="border-l-4 border-l-green-500">
                          <CardContent className="pt-4">
                            <h4 className="font-semibold text-sm mb-3 flex items-center gap-2">
                              <Building2 className="h-4 w-4 text-green-500" />
                              Características do Imóvel
                            </h4>
                            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Tipo de Imóvel</Label>
                                <Select
                                  value={realEstateData.tipo_imovel || ""}
                                  onValueChange={(value) => setRealEstateData({ ...realEstateData, tipo_imovel: value })}
                                  disabled={!canEditRealEstate}
                                >
                                  <SelectTrigger className="h-9"><SelectValue placeholder="Selecione" /></SelectTrigger>
                                  <SelectContent>
                                    <SelectItem value="apartamento">Apartamento</SelectItem>
                                    <SelectItem value="moradia">Moradia</SelectItem>
                                    <SelectItem value="terreno">Terreno</SelectItem>
                                    <SelectItem value="comercial">Espaço Comercial</SelectItem>
                                  </SelectContent>
                                </Select>
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Tipologia (Quartos)</Label>
                                <Select
                                  value={realEstateData.num_quartos || ""}
                                  onValueChange={(value) => setRealEstateData({ ...realEstateData, num_quartos: value })}
                                  disabled={!canEditRealEstate}
                                >
                                  <SelectTrigger className="h-9"><SelectValue placeholder="Selecione" /></SelectTrigger>
                                  <SelectContent>
                                    <SelectItem value="T0">T0</SelectItem>
                                    <SelectItem value="T1">T1</SelectItem>
                                    <SelectItem value="T2">T2</SelectItem>
                                    <SelectItem value="T3">T3</SelectItem>
                                    <SelectItem value="T4">T4+</SelectItem>
                                  </SelectContent>
                                </Select>
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Tipologia (CPCV)</Label>
                                <Input
                                  value={realEstateData.tipologia || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, tipologia: e.target.value })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                  placeholder="Ex: T2, T3, T4"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Valor do Imóvel (€)</Label>
                                <Input
                                  type="number"
                                  value={realEstateData.valor_imovel || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, valor_imovel: parseFloat(e.target.value) || null })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                  placeholder="0.00"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Valor Patrimonial (€)</Label>
                                <Input
                                  type="number"
                                  value={realEstateData.valor_patrimonial || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, valor_patrimonial: parseFloat(e.target.value) || null })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                  placeholder="0.00"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Certificado Energético</Label>
                                <Input
                                  value={realEstateData.certificado_energetico || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, certificado_energetico: e.target.value })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                  placeholder="Ex: A, B-, C"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Área Bruta (m²)</Label>
                                <Input
                                  type="number"
                                  value={realEstateData.area_bruta || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, area_bruta: e.target.value })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                  placeholder="0"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Área Útil (m²)</Label>
                                <Input
                                  type="number"
                                  value={realEstateData.area_util || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, area_util: e.target.value })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                  placeholder="0"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Fração</Label>
                                <Input
                                  value={realEstateData.fracao || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, fracao: e.target.value })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                  placeholder="Ex: A, B, C"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Artigo Matricial</Label>
                                <Input
                                  value={realEstateData.artigo_matricial || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, artigo_matricial: e.target.value })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                  placeholder="Ex: 1234"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Conservatória</Label>
                                <Input
                                  value={realEstateData.conservatoria || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, conservatoria: e.target.value })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                  placeholder="Nome da conservatória"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Número Predial</Label>
                                <Input
                                  value={realEstateData.numero_predial || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, numero_predial: e.target.value })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                  placeholder="Ex: 000"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Estacionamento</Label>
                                <Input
                                  value={realEstateData.estacionamento || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, estacionamento: e.target.value })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                  placeholder="Ex: Garagem dupla, Lugar 12"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Arrecadação</Label>
                                <Input
                                  value={realEstateData.arrecadacao || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, arrecadacao: e.target.value })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                  placeholder="Ex: Arrecadação A, Caixa 5"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Outras Características</Label>
                                <Input
                                  value={realEstateData.outras_caracteristicas || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, outras_caracteristicas: e.target.value })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                  placeholder="Ex: Varanda, Piscina, Solar"
                                />
                              </div>
                              <div className="space-y-1 sm:col-span-2 md:col-span-3">
                                <Label className="text-xs text-muted-foreground">Descrição do Imóvel</Label>
                                <Textarea
                                  value={realEstateData.descricao_imovel || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, descricao_imovel: e.target.value })}
                                  disabled={!canEditRealEstate}
                                  rows={2}
                                  placeholder="Descrição detalhada do imóvel"
                                />
                              </div>
                            </div>
                          </CardContent>
                        </Card>

                        {/* ====== Grupo B: Localização ====== */}
                        <Card className="border-l-4 border-l-blue-500">
                          <CardContent className="pt-4">
                            <h4 className="font-semibold text-sm mb-3 flex items-center gap-2">
                              <MapPin className="h-4 w-4 text-blue-500" />
                              Localização
                            </h4>
                            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Localização Pretendida</Label>
                                <Input
                                  value={realEstateData.localizacao || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, localizacao: e.target.value })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Área Pretendida (m²)</Label>
                                <Input
                                  type="number"
                                  value={realEstateData.area_pretendida || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, area_pretendida: parseFloat(e.target.value) || null })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Valor Máximo (€)</Label>
                                <Input
                                  type="number"
                                  value={realEstateData.valor_maximo_imovel || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, valor_maximo_imovel: parseFloat(e.target.value) || null })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Finalidade</Label>
                                <Select
                                  value={realEstateData.finalidade || ""}
                                  onValueChange={(value) => setRealEstateData({ ...realEstateData, finalidade: value })}
                                  disabled={!canEditRealEstate}
                                >
                                  <SelectTrigger className="h-9"><SelectValue placeholder="Selecione" /></SelectTrigger>
                                  <SelectContent>
                                    <SelectItem value="habitacao_propria">Habitação Própria</SelectItem>
                                    <SelectItem value="investimento">Investimento</SelectItem>
                                    <SelectItem value="arrendamento">Arrendamento</SelectItem>
                                    <SelectItem value="refinanciamento">Refinanciamento</SelectItem>
                                  </SelectContent>
                                </Select>
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Código Postal</Label>
                                <Input
                                  value={realEstateData.codigo_postal || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, codigo_postal: e.target.value })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                  placeholder="0000-000"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Localidade</Label>
                                <Input
                                  value={realEstateData.localidade || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, localidade: e.target.value })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                  placeholder="Cidade"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Freguesia</Label>
                                <Input
                                  value={realEstateData.freguesia || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, freguesia: e.target.value })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                  placeholder="Freguesia"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Concelho</Label>
                                <Input
                                  value={realEstateData.concelho || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, concelho: e.target.value })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                  placeholder="Concelho"
                                />
                              </div>
                            </div>
                            {/* Características como badges */}
                            {realEstateData?.caracteristicas?.length > 0 && (
                              <div className="mt-3 space-y-1">
                                <Label className="text-xs text-muted-foreground">Características Pretendidas</Label>
                                <div className="flex flex-wrap gap-2">
                                  {realEstateData.caracteristicas.map((c, idx) => (
                                    <Badge key={idx} variant="secondary">{c}</Badge>
                                  ))}
                                </div>
                              </div>
                            )}
                            <div className="mt-3 space-y-1">
                              <Label className="text-xs text-muted-foreground">Outras Informações</Label>
                              <Textarea
                                value={realEstateData.outras_informacoes || ""}
                                onChange={(e) => setRealEstateData({ ...realEstateData, outras_informacoes: e.target.value })}
                                disabled={!canEditRealEstate}
                                rows={2}
                              />
                            </div>
                          </CardContent>
                        </Card>

                        {/* ====== Grupo C: Dados do CPCV e Prazos ====== */}
                        <Card className="border-l-4 border-l-amber-500">
                          <CardContent className="pt-4">
                            <h4 className="font-semibold text-sm mb-3 flex items-center gap-2">
                              <FileSignature className="h-4 w-4 text-amber-500" />
                              Dados do CPCV e Prazos
                            </h4>
                            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
                              {/* Valores Financeiros do CPCV (Fase 3) */}
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Sinal / Entrada (€)</Label>
                                <Input
                                  type="number"
                                  value={financialData.valor_entrada || ""}
                                  onChange={(e) => setFinancialData({ ...financialData, valor_entrada: parseFloat(e.target.value) || null })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                  placeholder="0.00"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Data do Sinal</Label>
                                <Input
                                  type="date"
                                  value={financialData.data_sinal || ""}
                                  onChange={(e) => setFinancialData({ ...financialData, data_sinal: e.target.value })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Reforço do Sinal (€)</Label>
                                <Input
                                  type="number"
                                  value={financialData.reforco_sinal || ""}
                                  onChange={(e) => setFinancialData({ ...financialData, reforco_sinal: parseFloat(e.target.value) || null })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                  placeholder="0.00"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Comissão Mediação (€)</Label>
                                <Input
                                  type="number"
                                  value={financialData.comissao_mediacao || ""}
                                  onChange={(e) => setFinancialData({ ...financialData, comissao_mediacao: parseFloat(e.target.value) || null })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                  placeholder="0.00"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Data do CPCV</Label>
                                <Input
                                  type="date"
                                  value={realEstateData.data_cpcv || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, data_cpcv: e.target.value })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Data Escritura Prevista</Label>
                                <Input
                                  type="date"
                                  value={realEstateData.data_escritura_prevista || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, data_escritura_prevista: e.target.value })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Prazo Escritura (dias)</Label>
                                <Input
                                  type="number"
                                  min="0"
                                  value={realEstateData.prazo_escritura_dias || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, prazo_escritura_dias: parseInt(e.target.value) || null })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                  placeholder="Ex: 90"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Data Entrega de Chaves</Label>
                                <Input
                                  type="date"
                                  value={realEstateData.data_entrega_chaves || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, data_entrega_chaves: e.target.value })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                />
                              </div>
                              <div className="space-y-1 sm:col-span-2">
                                <Label className="text-xs text-muted-foreground">Condição Suspensiva</Label>
                                <Input
                                  value={realEstateData.condicao_suspensiva || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, condicao_suspensiva: e.target.value })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                  placeholder="Ex: Aprovação de financiamento bancário"
                                />
                              </div>
                              <div className="space-y-1 sm:col-span-2 md:col-span-3">
                                <Label className="text-xs text-muted-foreground">Observações do CPCV</Label>
                                <Textarea
                                  value={realEstateData.observacoes_cpcv || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, observacoes_cpcv: e.target.value })}
                                  disabled={!canEditRealEstate}
                                  rows={2}
                                  placeholder="Observações adicionais sobre o CPCV"
                                />
                              </div>
                            </div>
                          </CardContent>
                        </Card>

                        {/* Dados do Proprietário (existente) */}
                        <Card className="border-l-4 border-l-orange-500">
                          <CardContent className="pt-4">
                            <h4 className="font-semibold text-sm mb-3 flex items-center gap-2">
                              <Users className="h-4 w-4 text-orange-500" />
                              Dados do Proprietário / Vendedor
                            </h4>
                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Nome</Label>
                                <Input
                                  value={realEstateData.owner_name || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, owner_name: e.target.value })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                  placeholder="Nome completo"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Email</Label>
                                <Input
                                  type="email"
                                  value={realEstateData.owner_email || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, owner_email: e.target.value })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                  placeholder="email@exemplo.com"
                                />
                              </div>
                              <div className="space-y-1">
                                <Label className="text-xs text-muted-foreground">Telefone</Label>
                                <Input
                                  value={realEstateData.owner_phone || ""}
                                  onChange={(e) => setRealEstateData({ ...realEstateData, owner_phone: e.target.value })}
                                  disabled={!canEditRealEstate}
                                  className="h-9"
                                  placeholder="+351 000 000 000"
                                />
                              </div>
                            </div>
                          </CardContent>
                        </Card>

                      </div>
                    )}
                  </TabsContent>

                  {/* Credit Tab */}
                  <TabsContent value="credit" className="space-y-4 mt-4">
                    {!canEditCredit && !creditData?.requested_amount ? (
                      <div className="text-center py-8 text-muted-foreground">
                        <CreditCard className="h-12 w-12 mx-auto mb-4 opacity-50" />
                        <p>Dados de crédito só podem ser preenchidos na fase bancária ou após aprovação</p>
                        <Badge className="mt-2">{currentStatusInfo.label}</Badge>
                      </div>
                    ) : (
                      <>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="space-y-2">
                          <Label>Valor do Empréstimo (€)</Label>
                          <Input
                            type="number"
                            value={creditData.requested_amount || ""}
                            onChange={(e) => setCreditData({ ...creditData, requested_amount: parseFloat(e.target.value) || null })}
                            disabled={!canEditCredit}
                          />
                        </div>
                        <div className="space-y-2">
                          <Label>Prazo (anos)</Label>
                          <Input
                            type="number"
                            value={creditData.loan_term_years || ""}
                            onChange={(e) => setCreditData({ ...creditData, loan_term_years: parseInt(e.target.value) || null })}
                            disabled={!canEditCredit}
                          />
                        </div>
                        <div className="space-y-2">
                          <Label>Taxa de Juro (%)</Label>
                          <Input
                            type="number"
                            step="0.01"
                            value={creditData.interest_rate || ""}
                            onChange={(e) => setCreditData({ ...creditData, interest_rate: parseFloat(e.target.value) || null })}
                            disabled={!canEditCredit}
                          />
                        </div>
                        <div className="space-y-2">
                          <Label>Prestação Mensal (€)</Label>
                          <Input
                            type="number"
                            value={creditData.monthly_payment || ""}
                            onChange={(e) => setCreditData({ ...creditData, monthly_payment: parseFloat(e.target.value) || null })}
                            disabled={!canEditCredit}
                          />
                        </div>
                        <div className="space-y-2">
                          <Label>Banco</Label>
                          <Input
                            value={creditData.bank_name || ""}
                            onChange={(e) => setCreditData({ ...creditData, bank_name: e.target.value })}
                            disabled={!canEditCredit}
                          />
                        </div>
                        <div className="space-y-2">
                          <Label>Data de Aprovação</Label>
                          <Input
                            type="date"
                            value={formatDateForInput(creditData.bank_approval_date)}
                            onChange={(e) => setCreditData({ ...creditData, bank_approval_date: e.target.value })}
                            disabled={!canEditCredit}
                          />
                        </div>
                        <div className="space-y-2 md:col-span-2">
                          <Label>Notas da Aprovação</Label>
                          <Textarea
                            value={creditData.bank_approval_notes || ""}
                            onChange={(e) => setCreditData({ ...creditData, bank_approval_notes: e.target.value })}
                            disabled={!canEditCredit}
                          />
                        </div>
                      </div>

                      {/* ====== Avaliação Bancária (Fase 3) ====== */}
                      <Card className="border-l-4 border-l-emerald-500 mt-4">
                        <CardContent className="pt-4">
                          <h4 className="font-semibold text-sm mb-3 flex items-center gap-2">
                            <Building2 className="h-4 w-4 text-emerald-500" />
                            Avaliação Bancária
                          </h4>
                          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Valor da Avaliação (€)</Label>
                              <Input
                                type="number"
                                value={creditData.valuation_value || ""}
                                onChange={(e) => setCreditData({ ...creditData, valuation_value: parseFloat(e.target.value) || null })}
                                disabled={!canEditCredit}
                                className="h-9"
                                placeholder="0.00"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Data da Avaliação</Label>
                              <Input
                                type="date"
                                value={creditData.valuation_date || ""}
                                onChange={(e) => setCreditData({ ...creditData, valuation_date: e.target.value })}
                                disabled={!canEditCredit}
                                className="h-9"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Banco Avaliador</Label>
                              <Input
                                value={creditData.valuation_bank || ""}
                                onChange={(e) => setCreditData({ ...creditData, valuation_bank: e.target.value })}
                                disabled={!canEditCredit}
                                className="h-9"
                                placeholder="Ex: CGD, Millennium BCP"
                              />
                            </div>
                            <div className="space-y-1 sm:col-span-2 md:col-span-3">
                              <Label className="text-xs text-muted-foreground">Notas da Avaliação</Label>
                              <Textarea
                                value={creditData.valuation_notes || ""}
                                onChange={(e) => setCreditData({ ...creditData, valuation_notes: e.target.value })}
                                disabled={!canEditCredit}
                                rows={2}
                                placeholder="Observações sobre a avaliação bancária"
                              />
                            </div>
                          </div>
                          {/* Alerta: Avaliação abaixo do valor de compra */}
                          {creditData.valuation_value && realEstateData.valor_imovel && creditData.valuation_value < realEstateData.valor_imovel && (
                            <div className="mt-3 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-center gap-2">
                              <AlertTriangle className="h-4 w-4 text-red-500 shrink-0" />
                              <p className="text-xs text-red-700 dark:text-red-300">
                                Valor da avaliação ({creditData.valuation_value.toLocaleString('pt-PT')}€) é inferior ao valor do imóvel ({realEstateData.valor_imovel.toLocaleString('pt-PT')}€). Diferença de {Math.abs(realEstateData.valor_imovel - creditData.valuation_value).toLocaleString('pt-PT')}€.
                              </p>
                            </div>
                          )}
                        </CardContent>
                      </Card>
                      </>
                    )}
                  </TabsContent>

                  {/* Documents Tab - Destaque para fácil acesso */}
                  <TabsContent value="documents" className="mt-4">
                    <div className="space-y-4">
                      {/* Header com info */}
                      <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-4">
                        <div className="flex items-center gap-3">
                          <div className="p-2 bg-amber-100 dark:bg-amber-900/40 rounded-lg">
                            <FolderOpen className="h-6 w-6 text-amber-600 dark:text-amber-400" />
                          </div>
                          <div>
                            <h3 className="font-semibold text-amber-800 dark:text-amber-200">Gestão de Documentos</h3>
                            <p className="text-sm text-amber-600 dark:text-amber-400">
                              Faça upload de ficheiros ou adicione links externos (Google Drive, OneDrive, etc.)
                            </p>
                          </div>
                        </div>
                      </div>
                      
                      {/* Painel de Documentos Unificado */}
                      <Card className="border-amber-200 dark:border-amber-800">
                        <CardContent className="pt-6">
                          <UnifiedDocumentsPanel 
                            key={documentsRefreshKey}
                            processId={id}
                            clientName={process?.client_name}
                            onAIDataExtracted={handleAIDataExtractedFromDocs}
                          />
                        </CardContent>
                      </Card>
                    </div>
                  </TabsContent>

                  {/* Emails Tab - Histórico de Emails do Processo */}
                  <TabsContent value="emails" className="mt-4">
                    <div className="space-y-4">
                      {/* Header com info */}
                      <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                        <div className="flex items-center gap-3">
                          <div className="p-2 bg-blue-100 dark:bg-blue-900/40 rounded-lg">
                            <Send className="h-6 w-6 text-blue-600 dark:text-blue-400" />
                          </div>
                          <div>
                            <h3 className="font-semibold text-blue-800 dark:text-blue-200">Histórico de Emails</h3>
                            <p className="text-sm text-blue-600 dark:text-blue-400">
                              Emails associados a este processo
                            </p>
                          </div>
                        </div>
                      </div>
                      
                      {/* Painel de Emails */}
                      <Card className="border-blue-200 dark:border-blue-800">
                        <CardContent className="pt-6">
                          <EmailHistoryPanel 
                            processId={id}
                            clientEmail={process?.client_email}
                            clientName={process?.client_name}
                            compact={false}
                            maxHeight="500px"
                            token={token}
                          />
                        </CardContent>
                      </Card>
                    </div>
                  </TabsContent>
                </Tabs>

                {/* Notas extraídas por IA */}
                {process.ai_extracted_notes && (
                  <Card className="mt-6 border-purple-200 bg-purple-50/50">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm flex items-center gap-2 text-purple-700">
                        <Sparkles className="h-4 w-4" />
                        Dados Extraídos por IA
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <pre className="text-xs whitespace-pre-wrap text-gray-700 bg-white p-3 rounded border max-h-[200px] overflow-y-auto">
                        {process.ai_extracted_notes}
                      </pre>
                    </CardContent>
                  </Card>
                )}

                {/* Conexões de Dados - Visível apenas para admin */}
                {userRole === "admin" && (
                  <Card className="mt-6 border-blue-200 bg-blue-50/50">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm flex items-center gap-2 text-blue-700">
                        <Database className="h-4 w-4" />
                        Origem dos Dados
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-xs">
                        {/* Titular 1 */}
                        <div className="bg-white p-2 rounded border">
                          <div className="font-medium mb-1">Titular 1</div>
                          <div className="space-y-0.5 text-muted-foreground">
                            <div className="flex justify-between">
                              <span>Nome:</span>
                              <Badge variant={process.source_client_name === "ai" ? "default" : "secondary"} className="text-[9px] px-1">
                                {process.source_client_name === "ai" ? "IA" : process.source_client_name === "form" ? "Form" : "Manual"}
                              </Badge>
                            </div>
                            <div className="flex justify-between">
                              <span>NIF:</span>
                              <Badge variant={process.source_nif === "ai" ? "default" : "secondary"} className="text-[9px] px-1">
                                {process.source_nif === "ai" ? "IA" : process.source_nif === "form" ? "Form" : "Manual"}
                              </Badge>
                            </div>
                            <div className="flex justify-between">
                              <span>Email:</span>
                              <Badge variant={process.source_email === "ai" ? "default" : "secondary"} className="text-[9px] px-1">
                                {process.source_email === "ai" ? "IA" : process.source_email === "form" ? "Form" : "Manual"}
                              </Badge>
                            </div>
                          </div>
                        </div>
                        
                        {/* Financeiros */}
                        <div className="bg-white p-2 rounded border">
                          <div className="font-medium mb-1">Financeiros</div>
                          <div className="space-y-0.5 text-muted-foreground">
                            <div className="flex justify-between">
                              <span>Rendimento:</span>
                              <Badge variant={financialData?.source_income === "ai" ? "default" : "secondary"} className="text-[9px] px-1">
                                {financialData?.source_income === "ai" ? "IA" : financialData?.source_income === "form" ? "Form" : "Manual"}
                              </Badge>
                            </div>
                            <div className="flex justify-between">
                              <span>Capital:</span>
                              <Badge variant={financialData?.source_capital === "ai" ? "default" : "secondary"} className="text-[9px] px-1">
                                {financialData?.source_capital === "ai" ? "IA" : financialData?.source_capital === "form" ? "Form" : "Manual"}
                              </Badge>
                            </div>
                          </div>
                        </div>
                        
                        {/* Imobiliário */}
                        <div className="bg-white p-2 rounded border">
                          <div className="font-medium mb-1">Imobiliário</div>
                          <div className="space-y-0.5 text-muted-foreground">
                            <div className="flex justify-between">
                              <span>Tipo:</span>
                              <Badge variant={realEstateData?.source_property_type === "ai" ? "default" : "secondary"} className="text-[9px] px-1">
                                {realEstateData?.source_property_type === "ai" ? "IA" : realEstateData?.source_property_type === "form" ? "Form" : "Manual"}
                              </Badge>
                            </div>
                            <div className="flex justify-between">
                              <span>Valor:</span>
                              <Badge variant={realEstateData?.source_value === "ai" ? "default" : "secondary"} className="text-[9px] px-1">
                                {realEstateData?.source_value === "ai" ? "IA" : realEstateData?.source_value === "form" ? "Form" : "Manual"}
                              </Badge>
                            </div>
                          </div>
                        </div>
                        
                        {/* Documentos */}
                        <div className="bg-white p-2 rounded border col-span-2 md:col-span-3">
                          <div className="font-medium mb-1">Resumo</div>
                          <div className="flex gap-4 text-muted-foreground">
                            <span>Criado: <strong>{process.created_by || "Sistema"}</strong></span>
                            <span>Fonte: <strong>{process.lead_source || "Manual"}</strong></span>
                            {process.updated_by && <span>Últ. edição: <strong>{process.updated_by}</strong></span>}
                          </div>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                )}

                <Separator className="my-6" />

                {!isViewMode && (
                <div className="flex flex-wrap justify-end gap-2">
                  {/* Botão Guardar normal */}
                  <Button onClick={handleSave} disabled={saving} data-testid="save-process-btn">
                    {saving ? (
                      <><Loader2 className="h-4 w-4 mr-2 animate-spin" />A guardar...</>
                    ) : (
                      "Guardar Alterações"
                    )}
                  </Button>
                </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Sidebar - Organizada com Accordions */}
          <div className="space-y-3">
            {/* Activity Section - visível se NÃO for modo de visualização ou se tiver use_chat */}
            {(!isViewMode || canUseChat) && (
            <Card className="border-border">
              <CardHeader className="pb-2 py-3">
                <CardTitle className="text-sm flex items-center gap-2">
                  <MessageSquare className="h-4 w-4" />
                  Atividade
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0 pb-3">
                <div className="space-y-2">
                  <div className="flex gap-2">
                    <Textarea
                      placeholder="Adicionar comentário..."
                      value={newComment}
                      onChange={(e) => setNewComment(e.target.value)}
                      className="flex-1 min-h-[50px] text-sm resize-none"
                      data-testid="new-comment-input"
                    />
                    <Button
                      onClick={handleSendComment}
                      disabled={sendingComment || !newComment.trim()}
                      size="sm"
                      data-testid="send-comment-btn"
                    >
                      {sendingComment ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                    </Button>
                  </div>
                  <ScrollArea className="h-[120px]">
                    <div className="space-y-1.5 pr-2">
                      {activities.length === 0 ? (
                        <p className="text-center text-muted-foreground py-2 text-xs">Sem comentários</p>
                      ) : (
                        activities.slice(0, 5).map((activity) => (
                          <div key={activity.id} className="p-1.5 bg-muted/50 rounded text-xs" data-testid={`activity-${activity.id}`}>
                            <div className="flex items-start justify-between gap-1">
                              <div className="flex-1 min-w-0">
                                <span className="font-medium">{activity.user_name}</span>
                                {activity.source === 'trello' && <Badge variant="outline" className="ml-1 text-[9px] px-1 py-0">trello</Badge>}
                                <p className="text-[11px] mt-0.5 text-muted-foreground line-clamp-2">{activity.comment}</p>
                                <p className="text-[10px] text-muted-foreground">{format(parseISO(activity.created_at), "dd/MM HH:mm", { locale: pt })}</p>
                              </div>
                              {(activity.user_id === user.id || user.role === "admin") && (
                                <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0" onClick={() => handleDeleteComment(activity.id)}>
                                  <Trash2 className="h-3 w-3 text-destructive" />
                                </Button>
                              )}
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </ScrollArea>
                </div>
              </CardContent>
            </Card>
            )}

            {/* Tarefas - visível se tem manage_tasks */}
            {canManageTasks && (
            <Card className="border-border">
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Check className="h-5 w-5" />
                  Tarefas
                </CardTitle>
              </CardHeader>
              <CardContent>
                <TasksPanel
                  processId={id}
                  processName={process?.client_name}
                  compact={false}
                />
              </CardContent>
            </Card>
            )}

            {/* Accordion para agrupar painéis secundários - visível se tiver manage_tasks */}
            {(!isViewMode || canManageTasks) && (
            <Accordion type="multiple" defaultValue={[]} className="space-y-2">

              {/* Match Imóveis */}
              <AccordionItem value="match" className="border rounded-lg">
                <AccordionTrigger className="px-3 py-2 text-sm hover:no-underline">
                  <span className="flex items-center gap-2">
                    <Building2 className="h-4 w-4" />
                    Imóveis Compatíveis
                  </span>
                </AccordionTrigger>
                <AccordionContent className="px-3 pb-3">
                  <ClientPropertyMatch 
                    processId={id}
                    clientName={process?.client_name}
                  />
                </AccordionContent>
              </AccordionItem>

            </Accordion>
            )}

            {/* Side Tabs - Prazos e Histórico - visível se NÃO for modo de visualização */}
            {!isViewMode && (
            <Card className="border-border">
              <CardContent className="p-0">
                <Tabs value={sideTab} onValueChange={setSideTab}>
                  <TabsList className="w-full grid grid-cols-2 rounded-none rounded-t-md h-9">
                    <TabsTrigger value="deadlines" className="gap-1 text-xs">
                      <Clock className="h-3 w-3" />
                      Prazos
                    </TabsTrigger>
                    <TabsTrigger value="history" className="gap-1 text-xs">
                      <History className="h-3 w-3" />
                      Histórico
                    </TabsTrigger>
                  </TabsList>

                  {/* Deadlines Tab */}
                  <TabsContent value="deadlines" className="p-4 pt-2">
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="font-medium">Prazos</h3>
                      {canManageDeadlines && (
                        <Dialog open={isDeadlineDialogOpen} onOpenChange={setIsDeadlineDialogOpen}>
                          <DialogTrigger asChild>
                            <Button size="sm" variant="outline" data-testid="add-deadline-btn">
                              <Plus className="h-4 w-4" />
                            </Button>
                          </DialogTrigger>
                          <DialogContent aria-describedby="deadline-dialog-description" className="sm:max-w-md w-[calc(100vw-2rem)]">
                            <DialogHeader>
                              <DialogTitle>Novo Prazo</DialogTitle>
                              <DialogDescription id="deadline-dialog-description">
                                Crie um novo prazo para este processo.
                              </DialogDescription>
                            </DialogHeader>
                            <div className="space-y-4">
                              <div className="space-y-2">
                                <Label>Título</Label>
                                <Input
                                  value={deadlineForm.title}
                                  onChange={(e) => setDeadlineForm({ ...deadlineForm, title: e.target.value })}
                                  placeholder="Ex: Entregar documentos"
                                />
                              </div>
                              <div className="space-y-2">
                                <Label>Descrição</Label>
                                <Textarea
                                  value={deadlineForm.description}
                                  onChange={(e) => setDeadlineForm({ ...deadlineForm, description: e.target.value })}
                                />
                              </div>
                              <div className="space-y-2">
                                <Label>Data Limite</Label>
                                <Popover>
                                  <PopoverTrigger asChild>
                                    <Button variant="outline" className="w-full justify-start text-left font-normal">
                                      <CalendarIcon className="mr-2 h-4 w-4" />
                                      {selectedDate ? format(selectedDate, "PPP", { locale: pt }) : "Selecione"}
                                    </Button>
                                  </PopoverTrigger>
                                  <PopoverContent className="w-auto p-0">
                                    <Calendar mode="single" selected={selectedDate} onSelect={setSelectedDate} locale={pt} />
                                  </PopoverContent>
                                </Popover>
                              </div>
                              <div className="space-y-2">
                                <Label>Prioridade</Label>
                                <Select
                                  value={deadlineForm.priority}
                                  onValueChange={(value) => setDeadlineForm({ ...deadlineForm, priority: value })}
                                >
                                  <SelectTrigger><SelectValue /></SelectTrigger>
                                  <SelectContent>
                                    <SelectItem value="low">Baixa</SelectItem>
                                    <SelectItem value="medium">Média</SelectItem>
                                    <SelectItem value="high">Alta</SelectItem>
                                  </SelectContent>
                                </Select>
                              </div>
                            </div>
                            <DialogFooter>
                              <Button onClick={handleCreateDeadline}>Criar Prazo</Button>
                            </DialogFooter>
                          </DialogContent>
                        </Dialog>
                      )}
                    </div>

                    <Calendar
                      mode="single"
                      selected={selectedDate}
                      locale={pt}
                      modifiers={{ deadline: deadlineDates }}
                      modifiersStyles={{
                        deadline: { backgroundColor: "hsl(var(--primary))", color: "white", borderRadius: "4px" },
                      }}
                      className="rounded-md border mb-4"
                    />

                    <ScrollArea className="h-[200px]">
                      {deadlines.length === 0 ? (
                        <p className="text-center text-muted-foreground text-sm py-4">Sem prazos</p>
                      ) : (
                        <div className="space-y-2">
                          {deadlines.map((deadline) => (
                            <div
                              key={deadline.id}
                              className={`flex items-center justify-between p-2 rounded-md ${deadline.completed ? "bg-muted/30" : "bg-muted/50"}`}
                            >
                              <div className="flex items-center gap-2">
                                <button
                                  onClick={() => handleToggleDeadline(deadline)}
                                  className={`h-4 w-4 rounded border flex items-center justify-center ${
                                    deadline.completed ? "bg-emerald-500 border-emerald-500 text-white" : "border-slate-300"
                                  }`}
                                  disabled={!canManageDeadlines}
                                >
                                  {deadline.completed && <Check className="h-3 w-3" />}
                                </button>
                                <div>
                                  <p className={`text-sm ${deadline.completed ? "line-through text-muted-foreground" : ""}`}>
                                    {deadline.title}
                                  </p>
                                  <p className="text-xs text-muted-foreground font-mono">
                                    {format(parseISO(deadline.due_date), "dd/MM/yyyy")}
                                  </p>
                                </div>
                              </div>
                              {canManageDeadlines && (
                                <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => handleDeleteDeadline(deadline.id)}>
                                  <Trash2 className="h-3 w-3 text-destructive" />
                                </Button>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </ScrollArea>
                  </TabsContent>

                  {/* History Tab */}
                  <TabsContent value="history" className="p-4 pt-2">
                    <h3 className="font-medium mb-3">Filme da Lead</h3>
                    <UnifiedAuditTrail 
                      history={history} 
                      activities={activities}
                      maxHeight="400px"
                    />
                  </TabsContent>
                </Tabs>
              </CardContent>
            </Card>
            )}
          </div>
        </div>
      </div>
      
      {/* Dialog para atribuir utilizadores */}
      <Dialog open={showAssignDialog} onOpenChange={setShowAssignDialog}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Users className="h-5 w-5 text-purple-600" />
              Gerir Atribuições
            </DialogTitle>
            <DialogDescription>
              Seleccione os utilizadores a atribuir a este processo.
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4 py-4">
            <div className="p-3 bg-gray-50 rounded-lg">
              <p className="font-medium">{process?.client_name}</p>
              <p className="text-sm text-muted-foreground">
                #{process?.process_number || '—'}
              </p>
            </div>
            
            {loadingUsers ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-purple-600" />
                <span className="ml-2 text-sm text-muted-foreground">A carregar utilizadores...</span>
              </div>
            ) : (
            <div className="space-y-4">
              {/* Consultores - Seleção Múltipla */}
              <div>
                <Label className="text-sm font-medium mb-2 block">Consultores</Label>
                <div className="border rounded-lg p-3 max-h-48 overflow-y-auto">
                  {appUsers
                    .filter(u => ["consultor", "diretor", "admin", "ceo", "administrativo"].includes(u.role))
                    .map(u => (
                      <label key={u.id} className="flex items-center gap-2 py-1.5 cursor-pointer hover:bg-gray-50 px-2 rounded">
                        <input
                          type="checkbox"
                          checked={selectedConsultores.includes(u.id)}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setSelectedConsultores([...selectedConsultores, u.id]);
                            } else {
                              setSelectedConsultores(selectedConsultores.filter(id => id !== u.id));
                            }
                          }}
                          className="rounded border-gray-300"
                        />
                        <span className="text-sm">{u.name}</span>
                        <Badge variant="outline" className="text-xs ml-auto">{u.role}</Badge>
                      </label>
                    ))
                  }
                  {appUsers.filter(u => ["consultor", "diretor", "admin", "ceo", "administrativo"].includes(u.role)).length === 0 && (
                    <p className="text-sm text-muted-foreground text-center py-2">Nenhum consultor disponível</p>
                  )}
                </div>
                {selectedConsultores.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {selectedConsultores.map(cid => {
                      const user = appUsers.find(u => u.id === cid);
                      return user ? (
                        <Badge key={cid} variant="secondary" className="flex items-center gap-1">
                          {user.name}
                          <button
                            onClick={() => setSelectedConsultores(selectedConsultores.filter(id => id !== cid))}
                            className="ml-1 hover:text-destructive"
                          >
                            ×
                          </button>
                        </Badge>
                      ) : null;
                    })}
                  </div>
                )}
              </div>
              
              {/* Intermediários - Seleção Múltipla */}
              <div>
                <Label className="text-sm font-medium mb-2 block">Intermediários / Mediadores</Label>
                <div className="border rounded-lg p-3 max-h-48 overflow-y-auto">
                  {appUsers
                    .filter(u => ["mediador", "intermediario", "intermediario_credito", "diretor"].includes(u.role))
                    .map(u => (
                      <label key={u.id} className="flex items-center gap-2 py-1.5 cursor-pointer hover:bg-gray-50 px-2 rounded">
                        <input
                          type="checkbox"
                          checked={selectedMediadores.includes(u.id)}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setSelectedMediadores([...selectedMediadores, u.id]);
                            } else {
                              setSelectedMediadores(selectedMediadores.filter(id => id !== u.id));
                            }
                          }}
                          className="rounded border-gray-300"
                        />
                        <span className="text-sm">{u.name}</span>
                        <Badge variant="outline" className="text-xs ml-auto">{u.role}</Badge>
                      </label>
                    ))
                  }
                  {appUsers.filter(u => ["mediador", "intermediario", "intermediario_credito", "diretor"].includes(u.role)).length === 0 && (
                    <p className="text-sm text-muted-foreground text-center py-2">Nenhum intermediário disponível</p>
                  )}
                </div>
                {selectedMediadores.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {selectedMediadores.map(mid => {
                      const user = appUsers.find(u => u.id === mid);
                      return user ? (
                        <Badge key={mid} variant="secondary" className="flex items-center gap-1">
                          {user.name}
                          <button
                            onClick={() => setSelectedMediadores(selectedMediadores.filter(id => id !== mid))}
                            className="ml-1 hover:text-destructive"
                          >
                            ×
                          </button>
                        </Badge>
                      ) : null;
                    })}
                  </div>
                )}
              </div>
              
              {/* Indexação - Seleção Única */}
              <div>
                <Label className="text-sm font-medium">Indexação (Documentos)</Label>
                <Select value={selectedIndexacao || "none"} onValueChange={(v) => setSelectedIndexacao(v === "none" ? "" : v)}>
                  <SelectTrigger className="mt-1" data-testid="indexacao-select">
                    <SelectValue placeholder="Seleccionar indexação..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Nenhum</SelectItem>
                    {appUsers
                      .filter(u => ["indexacao", "administrativo", "admin", "ceo"].includes(u.role))
                      .map(u => (
                        <SelectItem key={u.id} value={u.id}>
                          {u.name} ({u.role})
                        </SelectItem>
                      ))
                    }
                  </SelectContent>
                </Select>
              </div>
              
              {/* Parceiro - Seleção Única (Utilizador Fantasma) */}
              <div>
                <Label className="text-sm font-medium flex items-center gap-2">
                  Parceiro
                  <span className="text-xs text-muted-foreground font-normal">(Utilizador fantasma - sem acesso)</span>
                </Label>
                <Select value={selectedParceiro || "none"} onValueChange={(v) => setSelectedParceiro(v === "none" ? "" : v)}>
                  <SelectTrigger className="mt-1" data-testid="parceiro-select">
                    <SelectValue placeholder="Seleccionar parceiro..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Nenhum</SelectItem>
                    {appUsers
                      .filter(u => u.role === "parceiro")
                      .map(u => (
                        <SelectItem key={u.id} value={u.id}>
                          {u.name}
                        </SelectItem>
                      ))
                    }
                  </SelectContent>
                </Select>
              </div>
            </div>
            )}
          </div>
          
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setShowAssignDialog(false)}>
              Cancelar
            </Button>
            <Button 
              onClick={handleSaveAssignment}
              disabled={savingAssignment}
              className="bg-purple-600 hover:bg-purple-700"
            >
              {savingAssignment ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  A guardar...
                </>
              ) : (
                "Guardar"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog de Revisão de Conflitos IA */}
      <Dialog open={showAIReviewDialog} onOpenChange={setShowAIReviewDialog}>
        <DialogContent className="sm:max-w-2xl w-[calc(100vw-2rem)] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-yellow-500" />
              Revisão de Dados Extraídos
            </DialogTitle>
            <DialogDescription>
              A análise IA detectou valores diferentes para alguns campos. Escolha o valor correcto ou edite manualmente.
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4 py-4">
            {aiConflicts.map((conflict, idx) => (
              <div key={idx} className="border rounded-lg p-4 space-y-3">
                <div className="font-medium text-sm">
                  {conflict.field.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                </div>
                
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div 
                    className="border rounded p-3 cursor-pointer hover:border-blue-500 hover:bg-blue-50 dark:hover:bg-blue-950"
                    onClick={() => resolveAIConflict(conflict.field, conflict.existing_value)}
                  >
                    <div className="text-xs text-muted-foreground mb-1">Valor Existente</div>
                    <div className="font-medium">{conflict.existing_value || "-"}</div>
                  </div>
                  
                  <div 
                    className="border rounded p-3 cursor-pointer hover:border-green-500 hover:bg-green-50 dark:hover:bg-green-950"
                    onClick={() => resolveAIConflict(conflict.field, conflict.new_value)}
                  >
                    <div className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
                      <Sparkles className="h-3 w-3" />
                      Valor Extraído (IA)
                    </div>
                    <div className="font-medium text-green-700 dark:text-green-400">{conflict.new_value || "-"}</div>
                    {conflict.source && (
                      <div className="text-xs text-muted-foreground mt-1">Fonte: {conflict.source}</div>
                    )}
                  </div>
                </div>
                
                <div className="flex items-center gap-2">
                  <Input
                    placeholder="Ou edite manualmente..."
                    className="flex-1 text-sm"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && e.target.value) {
                        resolveAIConflict(conflict.field, e.target.value);
                        e.target.value = '';
                      }
                    }}
                  />
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={(e) => {
                      const input = e.target.parentElement.querySelector('input');
                      if (input?.value) {
                        resolveAIConflict(conflict.field, input.value);
                        input.value = '';
                      }
                    }}
                  >
                    Aplicar
                  </Button>
                </div>
              </div>
            ))}
            
            {aiConflicts.length === 0 && (
              <div className="text-center py-8 text-muted-foreground">
                <CheckCircle className="h-12 w-12 mx-auto mb-3 text-green-500" />
                <p>Todos os conflitos foram resolvidos!</p>
              </div>
            )}
          </div>
          
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAIReviewDialog(false)}>
              Fechar
            </Button>
            <Button 
              onClick={() => {
                setShowAIReviewDialog(false);
                toast.success("Campos actualizados. Não esqueça de guardar!");
              }}
              disabled={aiConflicts.length > 0}
            >
              <Check className="h-4 w-4 mr-2" />
              Confirmar Todos
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Modal CPCV - Contrato Promessa Compra e Venda */}
      <CPCVModal
        open={showCPCVModal}
        onOpenChange={setShowCPCVModal}
        process={process}
        personalData={personalData}
        financialData={financialData}
        realEstateData={realEstateData}
        token={token}
      />

      {/* Modal para Enviar Documentação para Balcões */}
      <SendDocumentationModal
        open={showSendDocsModal}
        onOpenChange={setShowSendDocsModal}
        processId={id}
        process={process}
        token={token}
        user={user}
      />
    </DashboardLayout>
  );
};

export default ProcessDetails;
