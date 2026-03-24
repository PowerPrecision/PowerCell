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
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "../components/ui/alert-dialog";
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
import ProcessAlerts from "../components/ProcessAlerts";
import TasksPanel from "../components/TasksPanel";
import ProcessSummaryCard from "../components/ProcessSummaryCard";
import EmailHistoryPanel from "../components/EmailHistoryPanel";
import UnifiedDocumentsPanel from "../components/UnifiedDocumentsPanel";
import ProcessTimeline from "../components/ProcessTimeline";
import ClientPropertyMatch from "../components/ClientPropertyMatch";
import DataConflictResolver from "../components/DataConflictResolver";
import CPCVModal from "../components/CPCVModal";
import ProcessStickyHeader from "../components/ProcessStickyHeader";
import DSTICalculator from "../components/DSTICalculator";
import RiskCalculator from "../components/RiskCalculator";
import TempLinkButton from "../components/TempLinkButton";
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
  Users,
  Sparkles,
  Phone,
  MapPin,
  FileSignature,
  AlertTriangle,
  CheckCircle,
  Database,
  Calculator,
  TrendingUp,
  Link2,
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

// Status relacionados com bancos - ao mudar para estes status, verificar créditos ativos
const BANK_RELATED_STATUSES = ["enviado_bruno", "enviado_luis", "enviado_bcp_rui", "fase_bancaria", "entradas_precision"];

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
  const [financialData, setFinancialData] = useState({});
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
  const [savingAssignment, setSavingAssignment] = useState(false);
  const [loadingUsers, setLoadingUsers] = useState(false);
  
  // Contador para forçar refresh dos documentos
  const [documentsRefreshKey, setDocumentsRefreshKey] = useState(0);
  
  // Estado do RGPD
  const [rgpdStatus, setRgpdStatus] = useState(null);
  const [rgpdLoading, setRgpdLoading] = useState(false);
  const [rgpdSending, setRgpdSending] = useState(false);
  
  // Estado para aviso de bancos com créditos ativos
  const [showBankWarning, setShowBankWarning] = useState(false);
  const [pendingStatusChange, setPendingStatusChange] = useState(null);
  
  // Estado para o modal CPCV
  const [showCPCVModal, setShowCPCVModal] = useState(false);
  
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
  const [aiConflicts, setAiConflicts] = useState([]);
  const [showAIReviewDialog, setShowAIReviewDialog] = useState(false);

  // Handler para dados extraídos pela IA dos documentos
  const handleAIDataExtractedFromDocs = ({ extractedData, conflicts, documentsProcessed, suggestions }) => {
    console.log("Dados extraídos pela IA:", { extractedData, conflicts, documentsProcessed });
    
    // Guardar dados e conflitos
    setAiExtractedData(extractedData);
    setAiConflicts(conflicts || []);
    
    // Pré-preencher campos nos formulários
    if (extractedData) {
      // Dados pessoais
      const newPersonalData = { ...personalData };
      if (extractedData.nif) newPersonalData.nif = extractedData.nif;
      if (extractedData.documento_id || extractedData.cc_number) newPersonalData.documento_id = extractedData.documento_id || extractedData.cc_number;
      if (extractedData.data_nascimento || extractedData.birth_date) newPersonalData.data_nascimento = extractedData.data_nascimento || extractedData.birth_date;
      if (extractedData.naturalidade) newPersonalData.naturalidade = extractedData.naturalidade;
      if (extractedData.nacionalidade || extractedData.nationality) newPersonalData.nacionalidade = extractedData.nacionalidade || extractedData.nationality;
      if (extractedData.estado_civil) newPersonalData.estado_civil = extractedData.estado_civil;
      if (extractedData.sexo || extractedData.gender) newPersonalData.sexo = extractedData.sexo || extractedData.gender;
      if (extractedData.morada || extractedData.address) newPersonalData.morada = extractedData.morada || extractedData.address;
      if (extractedData.morada_fiscal || extractedData.fiscal_address) newPersonalData.morada_fiscal = extractedData.morada_fiscal || extractedData.fiscal_address;
      setPersonalData(newPersonalData);
      
      // Dados financeiros
      const newFinancialData = { ...financialData };
      if (extractedData.rendimento_mensal || extractedData.salario_liquido) newFinancialData.rendimento_mensal = extractedData.rendimento_mensal || extractedData.salario_liquido;
      if (extractedData.rendimento_bruto || extractedData.salario_bruto) newFinancialData.rendimento_bruto = extractedData.rendimento_bruto || extractedData.salario_bruto;
      if (extractedData.empresa) newFinancialData.empresa = extractedData.empresa;
      if (extractedData.tipo_contrato) newFinancialData.tipo_contrato = extractedData.tipo_contrato;
      setFinancialData(newFinancialData);
      
      // Dados do imóvel
      const newRealEstateData = { ...realEstateData };
      if (extractedData.valor_imovel) newRealEstateData.valor_imovel = extractedData.valor_imovel;
      if (extractedData.localizacao) newRealEstateData.localizacao = extractedData.localizacao;
      if (extractedData.tipologia) newRealEstateData.tipologia = extractedData.tipologia;
      if (extractedData.area) newRealEstateData.area = extractedData.area;
      setRealEstateData(newRealEstateData);
      
      // Se há conflitos, mostrar dialog de revisão
      if (conflicts && conflicts.length > 0) {
        setShowAIReviewDialog(true);
        toast.info(`${conflicts.length} conflito(s) detectado(s). Reveja os valores.`);
      } else {
        toast.success(`Campos pré-preenchidos com dados de ${documentsProcessed} documento(s)`);
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
    const canChangeStatus = ["consultor", "mediador", "admin", "ceo", "diretor", "administrativo"].includes(user?.role);
    if (!canChangeStatus) {
      return;
    }

    // Debounce para evitar múltiplas gravações
    const timeoutId = setTimeout(() => {
      // Verificar se está a mudar para um status relacionado com bancos
      if (BANK_RELATED_STATUSES.includes(status)) {
        const activeBanks = getActiveBanks();
        if (activeBanks.length > 0) {
          // Mostrar aviso com os bancos onde o cliente tem créditos ativos
          setPendingStatusChange({ status, activeBanks });
          setShowBankWarning(true);
          return;
        }
      }

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
      setFinancialData(processData.financial_data || {});
      setRealEstateData(processData.real_estate_data || {});
      setCreditData(processData.credit_data || {});
      
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
      'seg_social_utilizador', 'seg_social_senha'
    ];
    
    const cleaned = {};
    for (const key of validFields) {
      if (data[key] !== undefined && data[key] !== null && data[key] !== '') {
        cleaned[key] = data[key];
      }
    }
    return cleaned;
  };

  // Função para obter bancos com créditos ativos do processo
  const getActiveBanks = () => {
    if (financialData?.bancos_creditos && Array.isArray(financialData.bancos_creditos)) {
      return financialData.bancos_creditos.filter(banco => banco && banco.trim() !== "");
    }
    return [];
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

      if (user.role === "cliente" || user.role === "admin") {
        updateData.personal_data = cleanedPersonalData;
        updateData.financial_data = cleanedFinancialData;
      }

      if (user.role === "consultor" || user.role === "admin") {
        updateData.personal_data = cleanedPersonalData;
        updateData.financial_data = cleanedFinancialData;
        updateData.real_estate_data = realEstateData;
      }

      if (user.role === "mediador" || user.role === "admin") {
        updateData.personal_data = cleanedPersonalData;
        updateData.financial_data = cleanedFinancialData;
        const allowedStatuses = workflowStatuses.filter(s => s.order >= 3).map(s => s.name);
        if (allowedStatuses.includes(process.status) || process.status === "ch_aprovado" || process.status === "fase_bancaria") {
          updateData.credit_data = creditData;
        }
      }

      if (user.role !== "cliente" && statusToSave !== process.status) {
        updateData.status = statusToSave;
      }

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
    // Validar NIF antes de guardar
    if (personalData.nif) {
      const validation = validateNIF(personalData.nif);
      if (!validation.valid) {
        toast.error(validation.error);
        setNifError(validation.error);
        return;
      }
    }
    
    // Verificar se está a mudar para um status relacionado com bancos
    if (user.role !== "cliente" && status !== process.status && BANK_RELATED_STATUSES.includes(status)) {
      const activeBanks = getActiveBanks();
      if (activeBanks.length > 0) {
        // Mostrar aviso com os bancos onde o cliente tem créditos ativos
        setPendingStatusChange({ status, activeBanks });
        setShowBankWarning(true);
        return;
      }
    }

    // Se não há créditos ativos ou não é status de banco, salvar diretamente
    await executeSave(status);
  };

  // Confirmar mudança de status após aviso de bancos
  const handleConfirmBankStatusChange = async () => {
    if (pendingStatusChange) {
      await executeSave(pendingStatusChange.status);
    }
    setShowBankWarning(false);
    setPendingStatusChange(null);
  };

  // Cancelar mudança de status
  const handleCancelBankStatusChange = () => {
    setShowBankWarning(false);
    setPendingStatusChange(null);
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

  const canEditPersonal = ["cliente", "consultor", "mediador", "admin", "ceo", "administrativo", "diretor"].includes(user?.role) && user?.role !== "indexacao";
  const canEditFinancial = ["cliente", "consultor", "mediador", "admin", "ceo", "administrativo", "diretor"].includes(user?.role) && user?.role !== "indexacao";
  const canEditRealEstate = ["consultor", "admin", "ceo", "administrativo", "diretor"].includes(user?.role) && user?.role !== "indexacao";
  const canEditCredit = ["mediador", "admin", "ceo", "administrativo", "diretor"].includes(user?.role) && user?.role !== "indexacao" && 
    (workflowStatuses.filter(s => s.order >= 3).map(s => s.name).includes(process?.status) || 
     process?.status === "ch_aprovado" || process?.status === "fase_bancaria");
  const canChangeStatus = ["consultor", "mediador", "admin", "ceo", "administrativo", "diretor"].includes(user?.role) && user?.role !== "indexacao";
  const canManageDeadlines = ["consultor", "mediador", "admin", "ceo", "administrativo", "diretor"].includes(user?.role) && user?.role !== "indexacao";
  const canDeleteClient = ["admin", "ceo", "diretor", "administrativo"].includes(user?.role);
  
  // Role INDEXACAO: só pode ver dados e gerir documentos (upload/delete)
  const isIndexacaoRole = user?.role === "indexacao";

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

  if (loading) {
    return (
      <DashboardLayout title="Detalhes do Processo">
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
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
          <div className="flex flex-wrap items-center gap-2 pl-0 sm:pl-12">
            {/* Botão para Gerir Atribuições - escondido para gestor_documentos */}
            {user?.role !== "gestor_documentos" && (
              <Button
                variant="outline"
                size="sm"
                className="text-purple-600 border-purple-200 hover:bg-purple-50"
                onClick={openAssignDialog}
                data-testid="assign-users-btn"
              >
                <Users className="h-4 w-4 mr-1" />
                Atribuições
              </Button>
            )}
            
            {/* Botão RGPD */}
            {user?.role !== "gestor_documentos" && user?.role !== "indexacao" && (
              <Button
                variant="outline"
                size="sm"
                className={`${
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
                  <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                ) : rgpdStatus?.status === 'signed' ? (
                  <CheckCircle className="h-4 w-4 mr-1" />
                ) : (
                  <FileSignature className="h-4 w-4 mr-1" />
                )}
                {rgpdStatus?.status === 'signed' 
                  ? 'RGPD Assinado' 
                  : rgpdStatus?.status === 'pending'
                  ? 'RGPD Pendente'
                  : 'Solicitar RGPD'}
              </Button>
            )}
            
            {/* Botão CPCV */}
            {user?.role !== "gestor_documentos" && user?.role !== "indexacao" && (
              <Button
                variant="outline"
                size="sm"
                className="text-indigo-600 border-indigo-200 hover:bg-indigo-50"
                onClick={() => setShowCPCVModal(true)}
                title="Gerar Contrato Promessa Compra e Venda"
              >
                <FileSignature className="h-4 w-4 mr-2" />
                CPCV
              </Button>
            )}

            {/* Calculadoras */}
            {user?.role !== "gestor_documentos" && user?.role !== "indexacao" && (
              <>
                <TempLinkButton
                  processId={id}
                  clientName={process?.client_name}
                  clientEmail={process?.client_email}
                />
                <DSTICalculator
                  trigger={
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-blue-600 border-blue-200 hover:bg-blue-50"
                      title="Calculadora DSTI - Taxa de Esforço"
                    >
                      <Calculator className="h-4 w-4 mr-2" />
                      DSTI
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
                      className="text-purple-600 border-purple-200 hover:bg-purple-50"
                      title="Calculadora de Risco de Crédito"
                    >
                      <TrendingUp className="h-4 w-4 mr-2" />
                      Risco
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
                <SelectTrigger className="w-44" data-testid="status-select">
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
                className="text-red-600 border-red-200 hover:bg-red-50"
                onClick={handleDeleteClient}
                data-testid="delete-client-btn"
              >
                <Trash2 className="h-4 w-4 mr-1" />
                Eliminar
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

        {/* Timeline do Processo */}
        <ProcessTimeline 
          processId={id}
          currentStatus={process.status}
          history={process.status_history || activities.filter(a => a.type === 'status_change')}
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
            {/* Para role INDEXACAO: mostrar apenas info básica e Documentos */}
            {isIndexacaoRole ? (
              <>
                {/* Info básica do cliente */}
                <Card className="border-border">
                  <CardHeader>
                    <CardTitle className="text-lg">Informação do Cliente</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label className="text-muted-foreground text-xs">Nome</Label>
                        <p className="font-medium">{process?.client_name || "-"}</p>
                      </div>
                      <div>
                        <Label className="text-muted-foreground text-xs">Email</Label>
                        <p className="font-medium">{personalData?.email || "-"}</p>
                      </div>
                      <div>
                        <Label className="text-muted-foreground text-xs">Telefone</Label>
                        <p className="font-medium">{personalData?.phone || "-"}</p>
                      </div>
                      <div>
                        <Label className="text-muted-foreground text-xs">NIF</Label>
                        <p className="font-medium">{personalData?.nif || "-"}</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
                
                {/* Documentos - acesso completo para upload/delete */}
                <Card className="border-border">
                  <CardHeader>
                    <CardTitle className="text-lg flex items-center gap-2">
                      <FolderOpen className="h-5 w-5" />
                      Documentos
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <UnifiedDocumentsPanel 
                      key={documentsRefreshKey}
                      processId={id}
                      clientName={process?.client_name}
                      onAIDataExtracted={handleAIDataExtractedFromDocs}
                    />
                  </CardContent>
                </Card>
              </>
            ) : (
              /* Layout normal para outras roles */
              <Card className="border-border">
              <CardHeader>
                <CardTitle className="text-lg">Dados do Processo</CardTitle>
              </CardHeader>
              <CardContent>
                <Tabs value={activeTab} onValueChange={setActiveTab}>
                  <TabsList className="grid w-full grid-cols-5">
                    <TabsTrigger value="personal" className="gap-2">
                      <User className="h-4 w-4" />
                      <span className="hidden sm:inline">Pessoais</span>
                    </TabsTrigger>
                    <TabsTrigger value="financial" className="gap-2">
                      <Briefcase className="h-4 w-4" />
                      <span className="hidden sm:inline">Financeiros</span>
                    </TabsTrigger>
                    <TabsTrigger value="realestate" className="gap-2">
                      <Building2 className="h-4 w-4" />
                      <span className="hidden sm:inline">Imobiliário</span>
                    </TabsTrigger>
                    <TabsTrigger value="credit" className="gap-2">
                      <CreditCard className="h-4 w-4" />
                      <span className="hidden sm:inline">Crédito</span>
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
                          <div className="grid grid-cols-2 gap-4">
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
                          <div className="grid grid-cols-2 gap-4">
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
                              <Label className="text-xs text-muted-foreground">NIF</Label>
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
                                className={`h-9 ${nifError ? 'border-red-500 focus:ring-red-500' : ''}`}
                                placeholder="9 dígitos"
                              />
                              {nifError && (
                                <p className="text-xs text-red-500 mt-1">{nifError}</p>
                              )}
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Nº Documento (CC)</Label>
                              <Input
                                value={personalData.documento_id || ""}
                                onChange={(e) => setPersonalData({ ...personalData, documento_id: e.target.value })}
                                disabled={!canEditPersonal}
                                className="h-9"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Data de Nascimento</Label>
                              <Input
                                type="date"
                                value={formatDateForInput(personalData.data_nascimento || personalData.birth_date)}
                                onChange={(e) => setPersonalData({ ...personalData, data_nascimento: e.target.value })}
                                disabled={!canEditPersonal}
                                className="h-9"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Validade CC</Label>
                              <Input
                                type="date"
                                value={formatDateForInput(personalData.data_validade_cc)}
                                onChange={(e) => setPersonalData({ ...personalData, data_validade_cc: e.target.value })}
                                disabled={!canEditPersonal}
                                className="h-9"
                              />
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
                              <Label className="text-xs text-muted-foreground">Altura (m)</Label>
                              <Input
                                value={personalData.altura || ""}
                                onChange={(e) => setPersonalData({ ...personalData, altura: e.target.value })}
                                disabled={!canEditPersonal}
                                className="h-9"
                              />
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
                          <div className="grid grid-cols-2 gap-4">
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
                          <div className="space-y-1">
                            <Label className="text-xs text-muted-foreground">Morada Fiscal</Label>
                            <Input
                              value={personalData.morada_fiscal || personalData.address || ""}
                              onChange={(e) => setPersonalData({ ...personalData, morada_fiscal: e.target.value })}
                              disabled={!canEditPersonal}
                              className="h-9"
                            />
                          </div>
                        </CardContent>
                      </Card>
                      
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
                                  <div className="grid grid-cols-2 gap-2 text-sm">
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
                                  <div className="grid grid-cols-2 gap-2 text-sm">
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
                      {/* Rendimentos */}
                      <Card className="border-l-4 border-l-green-500">
                        <CardContent className="pt-4">
                          <h4 className="font-semibold text-sm mb-3 flex items-center gap-2">
                            <Briefcase className="h-4 w-4 text-green-500" />
                            Rendimentos
                          </h4>
                          <div className="grid grid-cols-2 gap-4">
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
                          <div className="grid grid-cols-2 gap-4">
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
                          <div className="grid grid-cols-2 gap-4">
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
                              <Input
                                type="password"
                                value={financialData.portal_financas_senha || ""}
                                onChange={(e) => setFinancialData({ ...financialData, portal_financas_senha: e.target.value })}
                                disabled={!canEditFinancial}
                                className="h-9"
                                placeholder="Senha de acesso"
                              />
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
                              <Input
                                type="password"
                                value={financialData.seg_social_senha || ""}
                                onChange={(e) => setFinancialData({ ...financialData, seg_social_senha: e.target.value })}
                                disabled={!canEditFinancial}
                                className="h-9"
                                placeholder="Senha de acesso"
                              />
                            </div>
                          </div>
                        </CardContent>
                      </Card>

                      {/* Créditos/Bancos */}
                      {financialData?.bancos_creditos?.length > 0 && (
                        <Card className="border-l-4 border-l-red-500">
                          <CardContent className="pt-4">
                            <h4 className="font-semibold text-sm mb-3 flex items-center gap-2">
                              <AlertCircle className="h-4 w-4 text-red-500" />
                              Créditos Ativos
                            </h4>
                            <div className="flex flex-wrap gap-2">
                              {financialData.bancos_creditos.map((banco, idx) => (
                                <Badge key={idx} className={getBankColor(banco)}>{banco}</Badge>
                              ))}
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
                          <div className="grid grid-cols-2 gap-4">
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
                              <Label className="text-xs text-muted-foreground">Tempo de Emprego</Label>
                              <Input
                                value={financialData.employment_duration || ""}
                                onChange={(e) => setFinancialData({ ...financialData, employment_duration: e.target.value })}
                                disabled={!canEditFinancial}
                                className="h-9"
                              />
                            </div>
                            <div className="space-y-1 col-span-2">
                              <Label className="text-xs text-muted-foreground">Entidade Empregadora</Label>
                              <Input
                                value={financialData.employer_name || ""}
                                onChange={(e) => setFinancialData({ ...financialData, employer_name: e.target.value })}
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
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="space-y-2">
                          <Label>Tipo de Imóvel</Label>
                          <Select
                            value={realEstateData.tipo_imovel || realEstateData.property_type || ""}
                            onValueChange={(value) => setRealEstateData({ ...realEstateData, tipo_imovel: value })}
                            disabled={!canEditRealEstate}
                          >
                            <SelectTrigger><SelectValue placeholder="Selecione" /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="apartamento">Apartamento</SelectItem>
                              <SelectItem value="moradia">Moradia</SelectItem>
                              <SelectItem value="terreno">Terreno</SelectItem>
                              <SelectItem value="comercial">Espaço Comercial</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                        <div className="space-y-2">
                          <Label>Tipologia (Quartos)</Label>
                          <Select
                            value={realEstateData.num_quartos || ""}
                            onValueChange={(value) => setRealEstateData({ ...realEstateData, num_quartos: value })}
                            disabled={!canEditRealEstate}
                          >
                            <SelectTrigger><SelectValue placeholder="Selecione" /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="T0">T0</SelectItem>
                              <SelectItem value="T1">T1</SelectItem>
                              <SelectItem value="T2">T2</SelectItem>
                              <SelectItem value="T3">T3</SelectItem>
                              <SelectItem value="T4">T4+</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                        <div className="space-y-2">
                          <Label>Tipologia do Imóvel (CPCV)</Label>
                          <Input
                            value={realEstateData.tipologia || ""}
                            onChange={(e) => setRealEstateData({ ...realEstateData, tipologia: e.target.value })}
                            disabled={!canEditRealEstate}
                            placeholder="Ex: T2, T3, T4"
                          />
                        </div>
                        <div className="space-y-2">
                          <Label>Localização Pretendida</Label>
                          <Input
                            value={realEstateData.localizacao || realEstateData.property_zone || ""}
                            onChange={(e) => setRealEstateData({ ...realEstateData, localizacao: e.target.value })}
                            disabled={!canEditRealEstate}
                          />
                        </div>
                        <div className="space-y-2">
                          <Label>Área Pretendida (m²)</Label>
                          <Input
                            type="number"
                            value={realEstateData.area_pretendida || realEstateData.desired_area || ""}
                            onChange={(e) => setRealEstateData({ ...realEstateData, area_pretendida: parseFloat(e.target.value) || null })}
                            disabled={!canEditRealEstate}
                          />
                        </div>
                        <div className="space-y-2">
                          <Label>Valor Máximo (€)</Label>
                          <Input
                            type="number"
                            value={realEstateData.valor_maximo_imovel || realEstateData.max_budget || ""}
                            onChange={(e) => setRealEstateData({ ...realEstateData, valor_maximo_imovel: parseFloat(e.target.value) || null })}
                            disabled={!canEditRealEstate}
                          />
                        </div>
                        <div className="space-y-2">
                          <Label>Finalidade</Label>
                          <Select
                            value={realEstateData.finalidade || realEstateData.property_purpose || ""}
                            onValueChange={(value) => setRealEstateData({ ...realEstateData, finalidade: value })}
                            disabled={!canEditRealEstate}
                          >
                            <SelectTrigger><SelectValue placeholder="Selecione" /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="habitacao_propria">Habitação Própria</SelectItem>
                              <SelectItem value="investimento">Investimento</SelectItem>
                              <SelectItem value="arrendamento">Arrendamento</SelectItem>
                              <SelectItem value="refinanciamento">Refinanciamento</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                        {/* Características */}
                        {realEstateData?.caracteristicas?.length > 0 && (
                          <div className="space-y-2 md:col-span-2">
                            <Label>Características Pretendidas</Label>
                            <div className="flex flex-wrap gap-2">
                              {realEstateData.caracteristicas.map((c, idx) => (
                                <Badge key={idx} variant="secondary">{c}</Badge>
                              ))}
                            </div>
                          </div>
                        )}
                        <div className="space-y-2 md:col-span-2">
                          <Label>Outras Informações</Label>
                          <Textarea
                            value={realEstateData.outras_informacoes || realEstateData.notes || ""}
                            onChange={(e) => setRealEstateData({ ...realEstateData, outras_informacoes: e.target.value })}
                            disabled={!canEditRealEstate}
                          />
                        </div>
                        
                        {/* Dados do Proprietário */}
                        <div className="md:col-span-2 pt-4 border-t">
                          <h4 className="font-medium text-sm text-muted-foreground mb-4">Dados do Proprietário</h4>
                          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            <div className="space-y-2">
                              <Label>Nome do Proprietário</Label>
                              <Input
                                value={realEstateData.owner_name || ""}
                                onChange={(e) => setRealEstateData({ ...realEstateData, owner_name: e.target.value })}
                                disabled={!canEditRealEstate}
                                placeholder="Nome completo"
                              />
                            </div>
                            <div className="space-y-2">
                              <Label>Email do Proprietário</Label>
                              <Input
                                type="email"
                                value={realEstateData.owner_email || ""}
                                onChange={(e) => setRealEstateData({ ...realEstateData, owner_email: e.target.value })}
                                disabled={!canEditRealEstate}
                                placeholder="email@exemplo.com"
                              />
                            </div>
                            <div className="space-y-2">
                              <Label>Telefone do Proprietário</Label>
                              <Input
                                value={realEstateData.owner_phone || ""}
                                onChange={(e) => setRealEstateData({ ...realEstateData, owner_phone: e.target.value })}
                                disabled={!canEditRealEstate}
                                placeholder="+351 000 000 000"
                              />
                            </div>
                          </div>
                        </div>
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
                    )}
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

                {/* Conexões de Dados - Visível para todos exceto clientes e indexacao */}
                {user?.role !== "cliente" && user?.role !== "indexacao" && (
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

                <div className="flex justify-end">
                  <Button onClick={handleSave} disabled={saving} data-testid="save-process-btn">
                    {saving ? (
                      <><Loader2 className="h-4 w-4 mr-2 animate-spin" />A guardar...</>
                    ) : (
                      "Guardar Alterações"
                    )}
                  </Button>
                </div>
              </CardContent>
            </Card>
            )}
          </div>

          {/* Sidebar - Organizada com Accordions */}
          <div className="space-y-3">
            {/* Activity Section - escondido para INDEXACAO */}
            {!isIndexacaoRole && (
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
                                <Button variant="ghost" size="icon" className="h-5 w-5 shrink-0" onClick={() => handleDeleteComment(activity.id)}>
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

            {/* Accordion para agrupar painéis secundários - escondido para INDEXACAO */}
            {!isIndexacaoRole && (
            <Accordion type="multiple" defaultValue={["tasks"]} className="space-y-2">
              {/* Tarefas */}
              <AccordionItem value="tasks" className="border rounded-lg">
                <AccordionTrigger className="px-3 py-2 text-sm hover:no-underline">
                  <span className="flex items-center gap-2">
                    <Check className="h-4 w-4" />
                    Tarefas
                  </span>
                </AccordionTrigger>
                <AccordionContent className="px-3 pb-3">
                  <TasksPanel 
                    processId={id} 
                    processName={process.client_name}
                    compact={true}
                    maxHeight="150px"
                  />
                </AccordionContent>
              </AccordionItem>

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

              {/* Emails */}
              <AccordionItem value="emails" className="border rounded-lg">
                <AccordionTrigger className="px-3 py-2 text-sm hover:no-underline">
                  <span className="flex items-center gap-2">
                    <Send className="h-4 w-4" />
                    Histórico de Emails
                  </span>
                </AccordionTrigger>
                <AccordionContent className="px-3 pb-3">
                  <EmailHistoryPanel 
                    processId={id}
                    clientEmail={process?.client_email}
                    clientName={process?.client_name}
                    compact={true}
                    maxHeight="200px"
                    token={token}
                  />
                </AccordionContent>
              </AccordionItem>

              {/* Documentos Unificados - Ficheiros + Links Drive */}
              <AccordionItem value="docs" className="border rounded-lg">
                <AccordionTrigger className="px-3 py-2 text-sm hover:no-underline">
                  <span className="flex items-center gap-2">
                    <FolderOpen className="h-4 w-4" />
                    Documentos
                  </span>
                </AccordionTrigger>
                <AccordionContent className="px-3 pb-3 overflow-x-auto">
                  <UnifiedDocumentsPanel 
                    key={documentsRefreshKey}
                    processId={id}
                    clientName={process?.client_name}
                    onAIDataExtracted={handleAIDataExtractedFromDocs}
                  />
                </AccordionContent>
              </AccordionItem>
            </Accordion>
            )}

            {/* Side Tabs - Prazos e Histórico - escondido para INDEXACAO */}
            {!isIndexacaoRole && (
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
                          <DialogContent aria-describedby="deadline-dialog-description">
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
                                <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => handleDeleteDeadline(deadline.id)}>
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
                    <h3 className="font-medium mb-4">Histórico de Alterações</h3>
                    <ScrollArea className="h-[400px]">
                      {history.length === 0 ? (
                        <p className="text-center text-muted-foreground text-sm py-4">Sem histórico</p>
                      ) : (
                        <div className="space-y-3">
                          {history.map((entry) => (
                            <div key={entry.id} className="border-l-2 border-primary/30 pl-3 py-1">
                              <p className="text-sm font-medium">{entry.action}</p>
                              {entry.field && (
                                <p className="text-xs text-muted-foreground">
                                  {entry.field}: {entry.old_value || "vazio"} → {entry.new_value}
                                </p>
                              )}
                              <p className="text-xs text-muted-foreground">
                                {entry.user_name} • {format(parseISO(entry.created_at), "dd/MM HH:mm", { locale: pt })}
                              </p>
                            </div>
                          ))}
                        </div>
                      )}
                    </ScrollArea>
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
                      .filter(u => ["indexacao", "gestor_documentos", "administrativo", "admin", "ceo"].includes(u.role))
                      .map(u => (
                        <SelectItem key={u.id} value={u.id}>
                          {u.name} ({u.role})
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
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
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
                
                <div className="grid grid-cols-2 gap-3">
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

      {/* AlertDialog para aviso de bancos com créditos ativos */}
      <AlertDialog open={showBankWarning} onOpenChange={setShowBankWarning}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2 text-amber-600">
              <AlertCircle className="h-5 w-5" />
              Aviso: Créditos Ativos
            </AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-3">
                <p>
                  O cliente <strong>{process?.client_name}</strong> tem créditos ativos nos seguintes bancos:
                </p>
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
                  <div className="flex flex-wrap gap-2">
                    {pendingStatusChange?.activeBanks?.map((bank, index) => (
                      <Badge key={index} className={getBankColor(bank)}>{bank}</Badge>
                    ))}
                  </div>
                </div>
                <p className="text-sm text-muted-foreground">
                  Tem a certeza que deseja alterar o status para &quot;{workflowStatuses.find(s => s.name === pendingStatusChange?.status)?.label || pendingStatusChange?.status}&quot;?
                </p>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={handleCancelBankStatusChange}>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={handleConfirmBankStatusChange} className="bg-amber-600 hover:bg-amber-700">
              Confirmar Alteração
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

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
    </DashboardLayout>
  );
};

export default ProcessDetails;
