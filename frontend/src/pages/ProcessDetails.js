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
import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { safeLabel, safeNumber } from "../components/dashboard/DashboardShared";
import { buildStatusOptions, formatStatusLabel } from "../utils/workflowStatuses";
import DashboardLayout from "../layouts/DashboardLayout";
import useWebSocket, { WSEventType } from "../hooks/useWebSocket";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Switch } from "../components/ui/switch";
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../components/ui/dropdown-menu";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "../components/ui/accordion";
import {
  getProcess,
  updateProcess,
  getClient,
  updateClient,
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
  deleteProcess,
  generateMagicLink,
  sendMagicLinkEmail,
  impersonateClient,
  impersonateClientPortal,
} from "../services/api";
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
import { AIBadge, getFieldMeta, buildManualMetadata } from "../components/ui/AIBadge";
import TempLinkButton from "../components/TempLinkButton";
import SendDocumentationModal from "../components/SendDocumentationModal";
import PortalDocumentRequests from "../components/PortalDocumentRequests";
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
  ChevronDown,
  ChevronUp,
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
  Pencil,
  Database,
  Calculator,
  TrendingUp,
  Lock,
  Eye,
  EyeOff,
  X,
  Search,
  RefreshCw,
  BrainCircuit,
  Home,
  Shield,
} from "lucide-react";
import { toast } from "sonner";
import { format, parseISO, isAfter, isValid } from "date-fns";
import { pt } from "date-fns/locale";
import { hasRole, hasAnyRole, filterByAnyRole, filterByRole, excludeRoles, ROLE_LABELS } from "../utils/roleUtils";
import { safeCopyToClipboard } from "../utils/clipboard";
import { safeString, safeStringArray } from "../utils/safeString";
import { extractErrorMessage } from "../utils/extractErrorMessage";
import { safeDateStr, safeParseISO, safeFormat, safeDate } from "../lib/utils";

import {
  statusColors,
  BANK_LIST,
  getBankColor,
  typeLabels,
} from "./processDetails/processDetailsConstants";
import {
  formatDateForInput,
  cleanPersonalDataForSubmit,
  cleanTitular2DataForSubmit,
  cleanRealEstateDataForSubmit,
  cleanCreditDataForSubmit,
  cleanFinancialDataForSubmit,
} from "./processDetails/processFormCleaners";
import { validateNIF } from "../utils/validateNIF";
import VisitasTab from "../components/processDetails/VisitasTab";
import ProcessPortalMessagesTab from "../components/processDetails/ProcessPortalMessagesTab";
import CardHeaderWithEditBase from "../components/processDetails/CardHeaderWithEdit";
import { useProcessPortalMessages } from "../hooks/useProcessPortalMessages";
import { useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "../lib/queryClient";
import { deriveProcessDetailsViewModel } from "./processDetails/processDetailsHydration";
import ProcessPersonalTab from "../components/processDetails/ProcessPersonalTab";
import ProcessFinancialTab from "../components/processDetails/ProcessFinancialTab";
import ProcessRealEstateTab from "../components/processDetails/ProcessRealEstateTab";
import ProcessCreditTab from "../components/processDetails/ProcessCreditTab";

// eslint-disable-next-line no-undef
const API_URL = process.env.REACT_APP_BACKEND_URL || "";

// Constantes/helpers: processDetailsConstants, processFormCleaners, validateNIF, VisitasTab

const ProcessDetails = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user, token } = useAuth();
  const queryClient = useQueryClient();
  
  // ── WebSocket: juntar-se à room do processo para mensagens em tempo real ──
  // portalRefreshRef aponta para o refresh do hook useProcessPortalMessages
  // (definido mais abaixo) — evita TDZ e mantém o callback WS estável.
  const portalRefreshRef = useRef(() => {});
  const { joinProcessRoom, leaveProcessRoom } = useWebSocket({
    onPortalMessage: (data) => {
      // Quando chega uma nova mensagem do portal, refrescar a lista SEMPRE
      // (independentemente do tab ativo, para que o unread count e as mensagens
      // estejam atualizados quando o utilizador mudar de tab)
      if (data?.process_id === id) {
        portalRefreshRef.current();
      }
    },
  });
  const [process, setProcess] = useState(null);
  // ── Fase 3: Estado separado do Cliente (entidade independente) ──
  const [clientData, setClientData] = useState(null);   // Dados completos do cliente (GET /clients/{id})
  const [clientId, setClientId] = useState(null);       // FK para a coleção clients
  // Guardar os dados originais do processo (da BD) para componentes
  // que precisam dos valores guardados (ex: email para notificações)
  const savedProcessRef = useRef(null);
  // Refs para os triggers das calculadoras (desacopladas do Dropdown — Pacote AF)
  const dstiRef = useRef(null);
  const riskRef = useRef(null);
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

  // Mensagens do Portal — estado/polling vivem no hook (badge do tab precisa de unread)
  const portal = useProcessPortalMessages(id, { isActive: activeTab === "mensagens" });
  portalRefreshRef.current = portal.refresh;


  const [accessDenied, setAccessDenied] = useState(false);
  const [notFound, setNotFound] = useState(false);
  
  // Estado de erro de validação do NIF
  const [nifError, setNifError] = useState(null);

  // TAREFA 2: Estado para conflitos de dados IA
  const [aiSuggestions, setAiSuggestions] = useState([]);
  const [isDataConfirmed, setIsDataConfirmed] = useState(false);

  // AI Executive Summary
  const [aiSummary, setAiSummary] = useState(null);
  const [aiAnalysisDate, setAiAnalysisDate] = useState(null);
  const [aiAnalysisLoading, setAiAnalysisLoading] = useState(false);

  // Form states
  const [personalData, setPersonalData] = useState({});
  const [titular2Data, setTitular2Data] = useState({});  // Estado para 2º titular
  const [financialData, setFinancialData] = useState({});
  const [editingCreditField, setEditingCreditField] = useState(null); // 'creditos' | 'contas' | 'simulacoes' | null
  // Per-card editing states (default: read-only). Null = no card in edit mode.
  const [editingCardId, setEditingCardId] = useState(null); // unique card ID (e.g. 'personal_contactos', 'financial_rendimentos') or null
  // Pacote AC: cartão Compliance minimizado por defeito (collapsedCards[cardId] = true)
  const [collapsedCards, setCollapsedCards] = useState({ credit_compliance: true }); // { cardId: boolean } — empty cards auto-collapse
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
  const [rgpdDialogOpen, setRgpdDialogOpen] = useState(false);
  const [rgpdCustomMessage, setRgpdCustomMessage] = useState("");
  
  // Estado para o modal CPCV
  const [showCPCVModal, setShowCPCVModal] = useState(false);

  // Estado para o modal de envio de documentação
  const [showSendDocsModal, setShowSendDocsModal] = useState(false);

  // Estado para etiquetas (Fase 3)
  const [newLabel, setNewLabel] = useState("");

  // Buscar utilizadores
  const fetchUsers = async () => {
    setLoadingUsers(true);
    try {
      const response = await fetch(`${API_URL}/api/admin/users`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        const users = await response.json();
        // Filtrar: ativos, não admin, não ceo — garantir que é array
        const usersArray = Array.isArray(users) ? users : [];
        const activeUsers = excludeRoles(usersArray.filter(u => u.is_active !== false), ["admin", "ceo"]);
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
      // RGPD status check failed silently — not critical
    } finally {
      setRgpdLoading(false);
    }
  };

  // Solicitar RGPD - abre o dialog
  const handleRequestRgpd = () => {
    // Verifica também o nome e o email vindo do cliente (caso ainda não tenha
    // sido sincronizado com o processo) — evita 422 ao submeter.
    const clientName = (process?.client_name || clientData?.nome || "").trim();
    const clientEmail = (process?.client_email || clientData?.contacto?.email || "").trim();
    if (!clientName) {
      toast.error("O cliente não tem nome definido — atualize a ficha do cliente.");
      return;
    }
    if (!clientEmail) {
      toast.error("O cliente não tem email definido");
      return;
    }
    setRgpdCustomMessage("");
    setRgpdDialogOpen(true);
  };

  // Helper: formata erros Pydantic (FastAPI 422) num único texto legível
  // O backend pode devolver `detail` como string OU como lista
  // [{type, loc, msg, input}, ...] (Pydantic ValidationError). Sem isto,
  // passar o array directamente ao toast/JSX provoca o erro React #31.
  const formatApiError = (data, fallback = "Erro inesperado") => {
    if (!data) return fallback;
    const detail = data.detail ?? data.message ?? data.error;
    if (!detail) return fallback;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d) => {
          if (typeof d === "string") return d;
          if (d && typeof d === "object") {
            const field = Array.isArray(d.loc) ? d.loc.filter((p) => p !== "body").join(".") : "";
            const msg = d.msg || d.message || JSON.stringify(d);
            return field ? `${field}: ${msg}` : msg;
          }
          return String(d);
        })
        .join(" • ");
    }
    if (typeof detail === "object") return detail.msg || JSON.stringify(detail);
    return String(detail);
  };

  // Confirmar envio de RGPD com mensagem customizada
  const handleConfirmRgpd = async () => {
    setRgpdDialogOpen(false);
    setRgpdSending(true);
    try {
      // Garantir que os campos obrigatórios estão presentes antes de enviar
      // (evita 422 silenciosos quando o processo ainda não tem client_name)
      const clientName = (process?.client_name || clientData?.nome || "").trim();
      const clientEmail = (process?.client_email || clientData?.contacto?.email || "").trim();
      if (!clientName) {
        toast.error("O cliente não tem nome definido — não é possível enviar o pedido RGPD.");
        return;
      }
      if (!clientEmail) {
        toast.error("O cliente não tem email definido.");
        return;
      }

      const response = await fetch(`${API_URL}/api/rgpd/request`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          process_id: id,
          client_name: clientName,
          client_email: clientEmail,
          custom_message: rgpdCustomMessage || undefined,
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
        toast.error(formatApiError(data, "Erro ao enviar RGPD"));
      }
    } catch (error) {
      console.error("Erro ao enviar RGPD:", error);
      toast.error("Erro ao enviar RGPD");
    } finally {
      setRgpdSending(false);
    }
  };

  // Abrir dialog de atribuição
  const openAssignDialog = async () => {
    if (process) {
      // Suporte a múltiplos consultores - converter para array
      const rawConsultorIds = process.assigned_consultor_ids || 
        (process.assigned_consultor_id ? [process.assigned_consultor_id] : []);
      setSelectedConsultores(Array.isArray(rawConsultorIds) ? rawConsultorIds : []);
      
      // Suporte a múltiplos intermediários - converter para array
      const rawMediadorIds = process.assigned_mediador_ids || 
        (process.assigned_mediador_id ? [process.assigned_mediador_id] : []);
      setSelectedMediadores(Array.isArray(rawMediadorIds) ? rawMediadorIds : []);
      
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
        toast.error(extractErrorMessage(data.detail, "Erro ao actualizar atribuições"));
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

  // AI Executive Summary — generate or refresh
  const handleAiAnalysis = async (force = false) => {
    setAiAnalysisLoading(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_URL}/api/processes/${id}/analyze${force ? '?force=true' : ''}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        if (res.status === 409) {
          toast.warning("Já existe uma análise em curso. Aguarde.");
        } else if (res.status === 503) {
          toast.error("Serviço de IA não configurado. Contacte o administrador.");
        } else {
          toast.error(extractErrorMessage(errData.detail, "Erro ao gerar análise IA"));
        }
        return;
      }
      const data = await res.json();
      setAiSummary(data.ai_executive_summary);
      setAiAnalysisDate(data.ai_analysis_date);
      if (data.cached) {
        toast.info("Análise anterior carregada. Clique em 'Actualizar' para gerar nova análise.");
      } else {
        toast.success("Análise IA gerada com sucesso!");
      }
    } catch (err) {
      console.error("Erro na análise IA:", err);
      toast.error("Erro de ligação ao servidor.");
    } finally {
      setAiAnalysisLoading(false);
    }
  };

  // Render Markdown summary as HTML (simple: just handle headings, bold, lists, blockquotes)
  const renderAiSummary = (markdown) => {
    if (!markdown) return null;
    return markdown.split('\n').map((line, i) => {
      // Headings
      if (line.startsWith('### ')) {
        const isAlert = line.toLowerCase().includes('alerta') || line.toLowerCase().includes('diverg');
        return <h4 key={i} className={`font-semibold text-sm mt-4 mb-2 ${isAlert ? 'text-red-600 flex items-center gap-1.5' : 'text-foreground flex items-center gap-1.5'}`}>{line.replace('### ', '')}</h4>;
      }
      if (line.startsWith('## ')) return <h3 key={i} className="font-semibold text-base mt-5 mb-2">{line.replace('## ', '')}</h3>;
      if (line.startsWith('# ')) return <h2 key={i} className="font-bold text-lg mt-5 mb-2">{line.replace('# ', '')}</h2>;
      // Blockquote
      if (line.startsWith('> ')) return <blockquote key={i} className="border-l-4 border-green-400 pl-3 my-2 text-sm text-muted-foreground italic">{line.replace('> ', '')}</blockquote>;
      // Horizontal rule
      if (line.trim() === '---') return <hr key={i} className="my-3 border-muted" />;
      // List items
      if (line.startsWith('- ') || line.startsWith('* ')) return <li key={i} className="ml-4 text-sm list-disc">{renderInlineFormatting(line.replace(/^[-*]\s/, ''))}</li>;
      // Empty line
      if (line.trim() === '') return <div key={i} className="h-1" />;
      // Bold line (alerts)
      if (line.startsWith('**') && line.endsWith('**')) return <p key={i} className="text-sm font-semibold mt-1">{line.replace(/\*\*/g, '')}</p>;
      // Normal paragraph
      return <p key={i} className="text-sm leading-relaxed">{renderInlineFormatting(line)}</p>;
    });
  };

  const renderInlineFormatting = (text) => {
    // Simple bold **text** → <strong>
    const parts = text.split(/(\*\*[^*]+\*\*)/g);
    return parts.map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={i} className="font-semibold">{part.replace(/\*\*/g, '')}</strong>;
      }
      return part;
    });
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
    const canChangeStatus = ["consultor", "intermediario", "admin", "ceo", "diretor", "administrativo"].includes(user?.role?.toLowerCase());
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

  // ── WebSocket Room: juntar-se à room do processo para mensagens em tempo real ──
  useEffect(() => {
    if (id) {
      joinProcessRoom(id);
    }
    return () => {
      if (id) {
        leaveProcessRoom(id);
      }
    };
  }, [id, joinProcessRoom, leaveProcessRoom]);

  const fetchData = async () => {
    try {
      // TanStack Query cache (same keys as useProcessQuery / useProcessFullData)
      const [processData, deadlinesData, activitiesData, historyData, statusesData] = await Promise.all([
        queryClient.fetchQuery({
          queryKey: queryKeys.processes.detail(id),
          queryFn: async () => {
            const response = await getProcess(id);
            return response.data;
          },
        }),
        queryClient.fetchQuery({
          queryKey: queryKeys.deadlines.byProcess(id),
          queryFn: async () => {
            try {
              const response = await getDeadlines(id);
              return Array.isArray(response.data) ? response.data : [];
            } catch {
              return [];
            }
          },
        }),
        queryClient.fetchQuery({
          queryKey: queryKeys.activities.byProcess(id),
          queryFn: async () => {
            try {
              const response = await getActivities(id);
              return Array.isArray(response.data) ? response.data : [];
            } catch {
              return [];
            }
          },
        }),
        queryClient.fetchQuery({
          queryKey: queryKeys.history.byProcess(id),
          queryFn: async () => {
            try {
              const response = await getHistory(id);
              return Array.isArray(response.data) ? response.data : [];
            } catch {
              return [];
            }
          },
        }),
        queryClient.fetchQuery({
          queryKey: queryKeys.workflowStatuses.list(),
          queryFn: async () => {
            try {
              const response = await getWorkflowStatuses();
              return Array.isArray(response.data) ? response.data : [];
            } catch {
              return [];
            }
          },
        }),
      ]);

      setDeadlines(deadlinesData);
      setActivities(activitiesData);
      setHistory(historyData);
      setWorkflowStatuses(statusesData);

      let clientData = null;
      if (processData.client_id) {
        setClientId(processData.client_id);
        try {
          const clientRes = await getClient(processData.client_id);
          clientData = clientRes.data;
        } catch (clientErr) {
          console.warn("Não foi possível carregar dados do cliente via client_id:", clientErr);
        }
      }

      const vm = deriveProcessDetailsViewModel(processData, clientData);
      setProcess(vm.process);
      savedProcessRef.current = vm.process;
      setClientId(vm.clientId);
      setClientData(vm.clientData);
      setPersonalData(vm.personalData);
      setTitular2Data(vm.titular2Data);
      setFinancialData(vm.financialData);
      setRealEstateData(vm.realEstateData);
      setCreditData(vm.creditData);
      setStatus(vm.status);
      setAiSummary(vm.aiSummary);
      setAiAnalysisDate(vm.aiAnalysisDate);
      setAiSuggestions(vm.aiSuggestions);
      setIsDataConfirmed(vm.isDataConfirmed);
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
  };

  const handleDownloadFile = async (filePath) => {
    try {
      const res = await getS3DownloadUrl(id, filePath);
      window.open(res.data.url, "_blank");
    } catch (e) {
      toast.error("Erro ao obter link de download");
    }
  };

  // Função para executar o save após confirmação
  // FASE 3: Gravação separada — dados pessoais vão para /clients/{id}, dados de negócio para /processes/{id}
  // Função para executar o save após confirmação
  const executeSave = async (statusToSave) => {
    setSaving(true);
    try {
      const processUpdateData = {};
      const clientUpdateData = {};
      
      // ── Sincronização Inteligente: Créditos Ativos → Contas Bancárias ──
      // Quando o utilizador preenche "Créditos Ativos" (bancos_creditos),
      // os bancos indicados são adicionados automaticamente a "Contas de
      // Crédito Abertas" (tem_creditos_activos) se ainda não existirem.
      if (Array.isArray(financialData.bancos_creditos) && financialData.bancos_creditos.length > 0) {
        const creditBanks = financialData.bancos_creditos.map(item =>
          typeof item === 'object' ? item.banco : item
        ).filter(b => b); // extrair nomes dos bancos, ignorar vazios
        
        const existingAccounts = financialData.tem_creditos_activos || [];
        const newAccounts = [...existingAccounts];
        
        for (const bank of creditBanks) {
          if (!newAccounts.includes(bank)) {
            newAccounts.push(bank);
          }
        }
        
        if (newAccounts.length !== existingAccounts.length) {
          financialData.tem_creditos_activos = newAccounts;
          setFinancialData({ ...financialData, tem_creditos_activos: newAccounts });
        }
      }
      
      // 1. LIMPAR DADOS
      const cleanedPersonalData = cleanPersonalDataForSubmit(personalData);
      const cleanedFinancialData = cleanFinancialDataForSubmit(financialData);

      // 2. PREPARAR DADOS DO CLIENTE (mapear para o schema ClientUpdate do backend)
      // O backend espera: { nome, contacto: { email, telefone }, dados_pessoais: {...} }
      if (cleanedPersonalData.nome_completo) clientUpdateData.nome = cleanedPersonalData.nome_completo;
      
      // Mapear email e telefone para o objecto aninhado 'contacto'
      // IMPORTANTE: Só incluímos os campos quando têm valor não-vazio.
      // Enviar strings vazias faria com que o backend sobrescrevesse os
      // contactos existentes do Cliente (merge {**existing, **incoming}),
      // apagando dados válidos quando o utilizador apenas alterou outros
      // campos do formulário.
      const contactoData = {};
      const emailVal = (process?.client_email || '').trim();
      const phoneVal = (process?.client_phone || '').trim();
      if (emailVal) {
        contactoData.email = emailVal;
      }
      if (phoneVal) {
        contactoData.telefone = phoneVal;
      }
      if (Object.keys(contactoData).length > 0) {
        clientUpdateData.contacto = contactoData;
      }
      
      // Mapear dados pessoais — o backend espera 'dados_pessoais', não 'personal_data'
      if (cleanedPersonalData && Object.keys(cleanedPersonalData).length > 0) {
        clientUpdateData.dados_pessoais = cleanedPersonalData;
      }

      // 3. PREPARAR DADOS DO PROCESSO (inclui dados pessoais e titular2 que vivem no processo)
      processUpdateData.personal_data = cleanedPersonalData;
      processUpdateData.financial_data = cleanedFinancialData;
      processUpdateData.titular2_data = cleanTitular2DataForSubmit(titular2Data);

      if (hasAnyRole(user, ["consultor", "admin"])) {
        processUpdateData.real_estate_data = cleanRealEstateDataForSubmit(realEstateData);
      }

      processUpdateData.credit_data = cleanCreditDataForSubmit(creditData);

      if (!hasRole(user, "cliente") && statusToSave !== process.status) {
        processUpdateData.status = statusToSave;
      }

      if (process.vendedor) processUpdateData.vendedor = process.vendedor;
      if (process.mediador) processUpdateData.mediador = process.mediador;
      if (process.monitored_emails && process.monitored_emails.length > 0) {
        processUpdateData.monitored_emails = process.monitored_emails;
      }
      if (process.notes !== undefined) processUpdateData.notes = process.notes;
      if (process.prioridade) processUpdateData.prioridade = process.prioridade;
      if (process.labels !== undefined) processUpdateData.labels = process.labels;

      // ── Pacote CT (Data Provenance UI): marcar proveniência "manual" ──
      // Quando o Consultor guarda um cartão, todos os campos desse cartão
      // passam a ser de origem manual (o humano sobrepôs/revisou o dado).
      // O backend (Pacote CS) faz merge seguro — preserva metadata de outros
      // campos não incluídos neste request.
      // O mapeamento editingCardId → field paths cobre apenas os cartões
      // com campos "importantes" badgados; outros cartões (ex: notas,
      // prazos) não geram field_metadata.
      const MANUAL_FIELDS_BY_CARD = {
        personal_identificacao: [
          "dados_pessoais.nif", "dados_pessoais.documento_id",
          "dados_pessoais.data_validade_cc", "dados_pessoais.data_nascimento",
          "dados_pessoais.niss",
        ],
        personal_morada: ["dados_pessoais.morada_fiscal"],
        financial_rendimentos: [
          "financial_data.monthly_income", "financial_data.rendimento_bruto",
          "financial_data.valor_financiado", "financial_data.capital_proprio",
          "financial_data.renda_habitacao_atual",
          "financial_data.rendimento_co_titular", "financial_data.rendimento_anual",
        ],
        realestate_caracteristicas: [
          "real_estate_data.valor_imovel", "real_estate_data.valor_patrimonial",
        ],
        credit_dados: [
          "credit_data.requested_amount", "credit_data.loan_term_years",
          "credit_data.interest_rate", "credit_data.monthly_payment",
          "credit_data.bank_name",
        ],
      };
      const _manualFields = editingCardId ? MANUAL_FIELDS_BY_CARD[editingCardId] : null;
      const _manualMeta = buildManualMetadata(_manualFields);
      if (_manualMeta) {
        // dados_pessoais.* / contacto.* / nome vivem no client; os restantes no process
        const _clientMeta = {};
        const _processMeta = {};
        for (const [k, v] of Object.entries(_manualMeta)) {
          if (k.startsWith("dados_pessoais.") || k.startsWith("contacto.") || k === "nome") {
            _clientMeta[k] = v;
          } else {
            _processMeta[k] = v;
          }
        }
        if (Object.keys(_processMeta).length > 0) {
          processUpdateData.field_metadata = _processMeta;
        }
        if (Object.keys(_clientMeta).length > 0) {
          clientUpdateData.field_metadata = _clientMeta;
        }
      }

      // 4. DISPARAR OS DOIS REQUESTS EM SIMULTÂNEO (PROMISE.ALL)
      const promises = [];

      // Update do Processo — incluir client_email/client_phone no body
      // (o backend lê do raw_body para sincronizar com o cliente)
      // Só incluímos se tiverem valor: evita sobrescrever campos válidos
      // do processo com strings vazias.
      if (emailVal) processUpdateData.client_email = emailVal;
      if (phoneVal) processUpdateData.client_phone = phoneVal;
      promises.push(updateProcess(id, processUpdateData));
      
      // Update do Cliente (apenas se houver client_id e não for role de indexação)
      if (process.client_id && !hasRole(user, "indexacao")) {
        promises.push(updateClient(process.client_id, clientUpdateData));
      }
      
      await Promise.all(promises);

      toast.success("Processo e Cliente atualizados com sucesso!");
      setEditingCardId(null); // Exit editing mode after save
      fetchData();
    } catch (error) {
      console.error("Error saving:", error);
      toast.error(error.message || "Erro ao guardar alterações");
    } finally {
      setSaving(false);
    }
  };

  // Guardar apenas os dados da Organização do Processo (notas, prioridade, etiquetas)
  const [savingOrg, setSavingOrg] = useState(false);
  const handleSaveOrganization = async () => {
    if (isProcessLocked) {
      toast.error("Não é possível editar um processo eliminado, desistido ou concluído.");
      return;
    }
    // Admin/CEO podem editar processos concluídos — isProcessLocked já exclui estes roles
    setSavingOrg(true);
    try {
      const orgData = {
        notes: process?.notes || "",
        prioridade: process?.prioridade || "media",
        labels: Array.isArray(process?.labels) ? process.labels : [],
      };
      await updateProcess(id, orgData);
      toast.success("Organização do processo guardada com sucesso!");
      fetchData();
    } catch (error) {
      console.error("Error saving organization:", error);
      const detail = error.response?.data?.detail;
      const errorMessage = typeof detail === 'string' ? detail : "Erro ao guardar organização do processo";
      toast.error(errorMessage);
    } finally {
      setSavingOrg(false);
    }
  };

  // Função principal de save que verifica créditos ativos
  const handleSave = async () => {
    // Bloquear guarda se o processo está em status terminal
    // Admin/CEO estão isentos (isProcessLocked já exclui estes roles)
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
      setActivities(Array.isArray(activitiesRes.data) ? activitiesRes.data : []);
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
      setActivities(Array.isArray(activitiesRes.data) ? activitiesRes.data : []);
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
        due_date: selectedDate && isValid(selectedDate) ? format(selectedDate, "yyyy-MM-dd") : null,
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
    return statusInfo || { label: formatStatusLabel(statusName), color: "blue" };
  };

  // ── Derived: opções do Select com baseline estático + fallback ─────
  // A dropdown de estado NUNCA deve ficar em branco. buildStatusOptions:
  //   1) usa workflowStatuses (API /admin/workflow-statuses) se existirem;
  //   2) senão, recorre ao baseline estático KNOWN_PROCESS_STATUSES (16 canónicos
  //      do enum ProcessStatus + legacy: triagem, fase_documental, etc.);
  //   3) se o `status` actual (process.status) não estiver na base escolhida,
  //      injeta-o como opção extra (label formatada, _isFallback=true).
  // Isto corrige o bug em que a dropdown aparecia vazia quando a API devolvia []
  // ou falhava (antes havia um `return []` prematuro que ignorava o fallback).
  const safeStatusOptions = useMemo(
    () => buildStatusOptions(workflowStatuses, status),
    [workflowStatuses, status]
  );

  // Normalizar role para comparação case-insensitive
  const userRole = user?.role?.toLowerCase() || "";
  const roleLabels = ROLE_LABELS; // Rótulos legíveis para exibição no banner retroativo
  const userPermissions = user?.permissions || {};
  const userPages = userPermissions?.pages || [];
  const userActions = userPermissions?.actions || [];
  
  // Permissões baseadas em actions (se disponíveis) ou fallback para role
  const hasEditProcess = userActions.length > 0 
    ? userActions.includes("edit_process") 
    : ["cliente", "consultor", "intermediario", "admin", "ceo", "administrativo", "diretor"].includes(userRole);
  
  const canEditPersonal = hasEditProcess;
  const canEditFinancial = hasEditProcess || (userActions.includes("view_financials") && userRole === "indexacao");
  const canEditRealEstate = hasEditProcess && 
    (userActions.length > 0 ? true : ["consultor", "admin", "ceo", "administrativo", "diretor"].includes(userRole));
  const canEditCredit = hasEditProcess && 
    (userActions.length > 0 ? true : ["intermediario", "admin", "ceo", "administrativo", "diretor", "consultor"].includes(userRole));
  const canChangeStatus = hasEditProcess && 
    (userActions.length > 0 ? true : ["consultor", "intermediario", "admin", "ceo", "administrativo", "diretor"].includes(userRole));
  const canManageDeadlines = hasEditProcess && 
    (userActions.length > 0 ? true : ["consultor", "intermediario", "admin", "ceo", "administrativo", "diretor"].includes(userRole));
  const canDeleteClient = ["admin", "ceo", "diretor", "administrativo"].includes(userRole);
  
  // Permissões específicas por action
  const canManageTasks = userActions.length > 0 
    ? userActions.includes("manage_tasks") 
    : ["admin", "ceo", "consultor", "intermediario", "diretor", "administrativo"].includes(userRole);
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
  // EXCEPÇÃO: admin e CEO NUNCA sofrem lock — podem editar processos concluídos retroativamente
  const BLOCKED_STATUSES = ["eliminados", "desistencias", "concluidos"];
  const isProcessLocked = process && BLOCKED_STATUSES.includes(process.status) && !['admin', 'ceo'].includes(userRole);
  const isViewMode = (!hasEditProcess && !(userActions.includes("view_financials") && userRole === "indexacao")) || isProcessLocked;

  // Função para eliminar o PROCESSO (soft-delete). O cliente NÃO é tocado —
  // para eliminar um cliente há-de usar-se a página de detalhe do cliente.
  // O backend (DELETE /processes/{id}) faz cascade de documentos/tarefas.
  const handleDeleteProcess = async () => {
    if (!id) {
      toast.error("Não foi possível identificar este processo.");
      return;
    }
    if (!window.confirm(
      `Tem a certeza que deseja eliminar o processo "${process?.ref || process?.process_ref || ""}" de ${process?.client_name || "cliente"}?\n\n` +
      `Esta ação é irreversível. O cliente NÃO será eliminado — apenas este processo, os seus documentos e tarefas associadas.`
    )) {
      return;
    }

    try {
      await deleteProcess(id);
      toast.success("Processo eliminado com sucesso");
      navigate("/processos");
    } catch (error) {
      toast.error(extractErrorMessage(error.response?.data?.detail, "Erro ao eliminar processo"));
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

  // ── Helper: detect if a card has no meaningful data ────────────
  // Helper: proveniência do dado (Data Provenance — Pacote CS/CT).
  // Lê do field_metadata do processo e, em fallback, do cliente.
  // Retorna {source, updated_at, confidence} ou null.
  const getFieldMetaFor = (fieldPath) =>
    getFieldMeta(fieldPath, process?.field_metadata, clientData?.field_metadata);

  // ── Helper: detect if a card has no meaningful data ────────────
  const isCardEmpty = (cardId) => {
    switch (cardId) {
      case 'financial_rendimentos':
        return !financialData?.monthly_income && !financialData?.salario_liquido &&
               !financialData?.rendimento_bruto && !financialData?.capital_proprio &&
               !financialData?.outras_rendas && !(financialData?.bancos_creditos?.length > 0) &&
               !financialData?.situacao_financeira && !financialData?.emprego_atual;
      case 'realestate_procura':
        return !realEstateData?.tipo_imovel && !realEstateData?.property_type &&
               !realEstateData?.num_quartos && !realEstateData?.ja_tem_imovel &&
               !realEstateData?.morada && !realEstateData?.localidade;
      case 'credit_dados':
        return !creditData?.requested_amount && !creditData?.bank_name &&
               !creditData?.loan_term_years && !creditData?.interest_rate;
      case 'credit_compliance':
        // Pacote AC: cartão Compliance & Perfil de Risco — colapsa quando vazio
        return !creditData?.admission_year &&
               creditData?.is_ppe == null &&
               creditData?.is_fpe == null &&
               !creditData?.credit_incidents;
      case 'financial_credenciais':
        // Credenciais de Portais Oficiais (1º proponente) — colapsa quando
        // não há nenhum utilizador/senha preenchido em nenhum portal.
        return !financialData?.portal_financas_utilizador && !financialData?.portal_financas_senha &&
               !financialData?.seg_social_utilizador && !financialData?.seg_social_senha;
      case 'financial_credenciais_2':
        // Credenciais de Portais Oficiais (2º proponente) — mesma lógica.
        return !titular2Data?.portal_financas_utilizador && !titular2Data?.portal_financas_senha &&
               !titular2Data?.seg_social_utilizador && !titular2Data?.seg_social_senha;
      default:
        return false;
    }
  };

  // ── Helper: toggle card collapse ───────────────────────────────
  const toggleCardCollapse = (cardId) => {
    setCollapsedCards(prev => ({ ...prev, [cardId]: !prev[cardId] }));
  };

  // ── Helper: should a card be collapsed? ────────────────────────
  // Auto-collapse empty cards (unless user is editing them or manually expanded)
  const shouldCardBeCollapsed = (cardId) => {
    if (editingCardId === cardId) return false; // Never collapse while editing
    if (collapsedCards[cardId] === false) return false; // User explicitly expanded
    if (collapsedCards[cardId] === true) return true;   // User explicitly collapsed
    return isCardEmpty(cardId); // Auto-collapse if empty (default)
  };

  // Thin wrapper: liga o CardHeaderWithEdit extraído ao estado local do processo
  const CardHeaderWithEdit = ({ title, cardKey, icon, canEdit, collapsible }) => (
    <CardHeaderWithEditBase
      title={title}
      cardKey={cardKey}
      icon={icon}
      canEdit={canEdit}
      collapsible={collapsible}
      collapsed={collapsible && shouldCardBeCollapsed(cardKey)}
      empty={collapsible && isCardEmpty(cardKey)}
      isEditing={editingCardId === cardKey}
      isProcessLocked={isProcessLocked}
      saving={saving}
      onToggleCollapse={toggleCardCollapse}
      onStartEdit={setEditingCardId}
      onCancelEdit={() => setEditingCardId(null)}
      onSave={handleSave}
    />
  );

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

  const deadlineDates = deadlines.map((d) => safeParseISO(d.due_date)).filter(Boolean);
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
        {/* Aviso de processo bloqueado ou em modo retroativo */}
        {isProcessLocked && (
          <div className="flex items-center gap-2 p-3 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-lg text-amber-800 dark:text-amber-200 text-sm">
            <Lock className="h-4 w-4 shrink-0" />
            <span>
              Este processo encontra-se em estado terminal (<strong>{safeLabel(currentStatusInfo.label)}</strong>). 
              A edição de dados está bloqueada para todos os utilizadores.
            </span>
          </div>
        )}
        {!isProcessLocked && ['admin', 'ceo'].includes(userRole) && process && BLOCKED_STATUSES.includes(process.status) && (
          <div className="flex items-center gap-2 p-3 bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 rounded-lg text-blue-800 dark:text-blue-200 text-sm">
            <Shield className="h-4 w-4 shrink-0" />
            <span>
              Este processo está em estado terminal (<strong>{safeLabel(currentStatusInfo.label)}</strong>), 
              mas como <strong>{roleLabels[userRole] || userRole}</strong> pode editar valores retroativamente. 
              As alterações serão sincronizadas com o snapshot financeiro.
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
                <h2 className="text-xl font-semibold truncate">
                  Processo #{safeString(process?.process_number || '')} — {safeString(clientData?.nome || process?.client_name || personalData?.nome_completo || personalData?.nome) || 'Cliente'}
                </h2>
                <Badge className={`${statusColors[currentStatusInfo.color]} border shrink-0`}>
                  {safeLabel(currentStatusInfo.label)}
                </Badge>
              </div>
              <p className="text-sm text-muted-foreground">
                {typeLabels[safeString(process.process_type)] || safeString(process.process_type)}
                {process?.process_number && (
                  <span className="ml-2 text-xs bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded font-mono">
                    Nº {safeString(process.process_number)}
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
            
            {/* Dialog RGPD */}
            <Dialog open={rgpdDialogOpen} onOpenChange={setRgpdDialogOpen}>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Solicitar Consentimento RGPD</DialogTitle>
                  <DialogDescription>
                    Envie um pedido de consentimento RGPD para <strong>{safeString(process?.client_name)}</strong> ({safeString(process?.client_email)}).
                  </DialogDescription>
                </DialogHeader>
                <div className="py-4">
                  <label className="text-sm font-medium text-foreground mb-2 block">
                    Mensagem personalizada <span className="text-muted-foreground font-normal">(opcional)</span>
                  </label>
                  <Textarea
                    placeholder="Adicione uma mensagem personalizada para o cliente..."
                    value={rgpdCustomMessage}
                    onChange={(e) => setRgpdCustomMessage(e.target.value)}
                    rows={3}
                  />
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setRgpdDialogOpen(false)}>
                    Cancelar
                  </Button>
                  <Button onClick={handleConfirmRgpd} disabled={rgpdSending}>
                    {rgpdSending ? (
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    ) : null}
                    Solicitar RGPD
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>

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
                  clientName={savedProcessRef.current?.client_name || process?.client_name}
                  clientEmail={savedProcessRef.current?.client_email || process?.client_email}
                />
                {/* Portal do Cliente — DropdownMenu unificado.
                    A ação principal abre as opções do portal (Copiar Link /
                    Enviar por Email) e, na lista suspensa, o item
                    👁️ Ver como Cliente abre o Portal do Cliente deste
                    processo num novo separador (impersonate / suporte).
                    O backend regista no audit_trail + history a mensagem
                    "O utilizador X assumiu a identidade do cliente no processo Y". */}
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-teal-600 border-teal-200 hover:bg-teal-50 h-8 px-2 sm:px-3"
                      title="Portal do Cliente"
                    >
                      <ExternalLink className="h-3.5 w-3.5 sm:mr-1" />
                      <span className="hidden sm:inline">Portal do Cliente</span>
                      <ChevronDown className="h-3.5 w-3.5 sm:ml-1" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start" className="w-60">
                    <DropdownMenuLabel>Portal do Cliente</DropdownMenuLabel>
                    <p className="text-xs text-muted-foreground px-2 pb-1">
                      Gerar link mágico de acesso ao portal.
                    </p>
                    <DropdownMenuItem
                      className="gap-2 cursor-pointer"
                      onClick={async () => {
                        try {
                          const res = await generateMagicLink(id);
                          const link = res.data?.magic_link || res.data?.link || res.data?.url;
                          if (link) {
                            await safeCopyToClipboard(link);
                          } else {
                            toast.error("Não foi possível gerar o link");
                          }
                        } catch (error) {
                          // O interceptor global do api.js é silencioso para 404
                          // (só faz console.warn). Para o utilizador ver a causa
                          // real ("processo eliminado", "processo não encontrado",
                          // etc.), extraímos o detail do backend e mostramos aqui.
                          // Outros status (400/500/...) já são tratados pelo interceptor.
                          if (error?.response?.status === 404) {
                            toast.error(error?.response?.data?.detail || "Processo não encontrado");
                          }
                        }
                      }}
                    >
                      <LinkIcon className="h-4 w-4" />
                      Copiar Link
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      className="gap-2 cursor-pointer"
                      onClick={async () => {
                        try {
                          await sendMagicLinkEmail(id);
                          toast.success("Email enviado com o link do portal!");
                        } catch (error) {
                          // Mesma lógica do Copiar Link: o interceptor é
                          // silencioso para 404, por isso mostramos o detail
                          // do backend (ex.: "processo eliminado") aqui.
                          if (error?.response?.status === 404) {
                            toast.error(error?.response?.data?.detail || "Processo não encontrado");
                          }
                        }
                      }}
                    >
                      <Mail className="h-4 w-4" />
                      Enviar por Email
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      className="gap-2 cursor-pointer text-amber-700 focus:text-amber-800"
                      onClick={async () => {
                        try {
                          const res = await impersonateClientPortal(id);
                          // CORREÇÃO (Pacote AD-fix): extração robusta do link.
                          // O backend devolve { url, short_id, process_id, ... } mas
                          // diferentes versões/estados podem usar chaves distintas.
                          // Tentamos todas as chaves possíveis antes de falhar.
                          const data = res?.data || res || {};
                          const url = data.url || data.magic_link || data.portal_url || data.link || data.access_url;
                          if (!url) {
                            toast.error(
                              extractErrorMessage(data) ||
                              "Não foi possível gerar o link de impersonate (resposta inválida do servidor)."
                            );
                            return;
                          }
                          // Abrir num novo separador. window.open devolve null
                          // quando o browser bloqueia popups; nesse caso, avisamos
                          // o utilizador e damos a opção de copiar o link.
                          const win = window.open(url, "_blank", "noopener,noreferrer");
                          if (!win) {
                            try {
                              await safeCopyToClipboard(url);
                              toast.info(
                                "Popup bloqueado pelo browser. Link copiado — cole num novo separador."
                              );
                            } catch {
                              toast.error("Popup bloqueado pelo browser. Tente permitir popups para este site.");
                            }
                          } else {
                            toast.success("Portal do Cliente aberto num novo separador (modo Visualização)");
                          }
                        } catch (error) {
                          // Tratamento de erro robusto: extrair a mensagem do servidor.
                          // O interceptor global do api.js é silencioso em alguns 4xx.
                          const detail =
                            error?.response?.data?.detail ||
                            error?.response?.data?.message ||
                            error?.message ||
                            "Erro ao gerar link de acesso.";
                          toast.error(detail);
                        }
                      }}
                    >
                      <Eye className="h-4 w-4" />
                      Ver como Cliente
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>

                {/* Simulações agrupadas num Dropdown (Pacote AC)
                    CORREÇÃO (Pacote AF): desacopladas do Dropdown para evitar
                    que o menu fique preso aberto. As calculadoras ficam fora
                    (div hidden) com refs aos botões de trigger; os itens do
                    menu chamam ref.current?.click() para abrir o modal,
                    permitindo ao Radix fechar o menu naturalmente. */}
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-amber-700 border-amber-200 hover:bg-amber-50 h-8 px-2 sm:px-3"
                      title="Simulações"
                    >
                      <Sparkles className="h-3.5 w-3.5 sm:mr-1" />
                      <span className="hidden sm:inline">Simulações</span>
                      <ChevronDown className="h-3.5 w-3.5 sm:ml-1" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-52">
                    <DropdownMenuItem
                      className="cursor-pointer gap-2 text-blue-600"
                      onSelect={() => dstiRef.current?.click()}
                    >
                      <Calculator className="h-4 w-4" />
                      Calculadora DSTI
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      className="cursor-pointer gap-2 text-purple-600"
                      onSelect={() => riskRef.current?.click()}
                    >
                      <TrendingUp className="h-4 w-4" />
                      Calculadora de Risco
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>

                {/* Calculadoras desacopladas — invisíveis mas funcionais.
                    Os botões reais de trigger estão aqui (hidden) e são
                    clicados programaticamente pelos itens do Dropdown. */}
                <div className="hidden" aria-hidden="true">
                  <DSTICalculator
                    trigger={<button ref={dstiRef} type="button" title="Calculadora DSTI" />}
                    clientData={{
                      rendimento_bruto: financialData?.rendimento_bruto,
                      rendimento_mensal: financialData?.monthly_income || financialData?.salario_liquido,
                      salario_liquido: financialData?.salario_liquido,
                      renda_habitacao_atual: financialData?.renda_habitacao_atual,
                      rendimento_co_titular: financialData?.rendimento_co_titular,
                    }}
                  />
                  <RiskCalculator
                    trigger={<button ref={riskRef} type="button" title="Calculadora de Risco" />}
                    clientData={{
                      rendimento_mensal: financialData?.monthly_income || financialData?.salario_liquido,
                      valor_imovel: realEstateData?.valor_imovel || realEstateData?.valor,
                      valor_entrada: financialData?.valor_entrada || financialData?.capital_proprio,
                      capital_proprio: financialData?.capital_proprio,
                      idade: personalData?.idade,
                      data_nascimento: personalData?.data_nascimento || personalData?.birth_date,
                    }}
                  />
                </div>
              </>
            )}
            
            {canChangeStatus && (
              <Select value={status} onValueChange={setStatus}>
                <SelectTrigger className="w-36 sm:w-44 h-8 text-xs sm:text-sm" data-testid="status-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {safeStatusOptions.map((s) => (
                    <SelectItem key={s.id} value={s.name}>
                      {s._isFallback
                        ? `⚠ ${safeLabel(s.label)} (não configurado)`
                        : safeLabel(s.label)
                      }
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            
            {/* Botão Eliminar Processo - apenas para Admin/CEO/Diretor/Administrativo.
                Elimina o PROCESSO (soft-delete + cascade docs/tarefas). O cliente
                NÃO é tocado — para eliminar o cliente usar a página do cliente. */}
            {canDeleteClient && (
              <Button
                variant="outline"
                size="sm"
                className="text-red-600 border-red-200 hover:bg-red-50 h-8 px-2 sm:px-3"
                onClick={handleDeleteProcess}
                data-testid="delete-process-btn"
                title="Eliminar este processo (o cliente não é eliminado)"
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
          consultorNames={safeStringArray(process.consultor_names)}
          mediadorNames={safeStringArray(process.mediador_names)}
          consultorName={process.consultor_name || process.assigned_consultor_name}
          mediadorName={process.mediador_name || process.assigned_mediador_name}
        />

        {/* ═══════ PACOTE BC: Layout reestruturado ═══════
            Ordem visual exata:
            1. Timeline (full width)
            2. Cartão meta-dados: Etiquetas + Prioridade (full width)
            3. Grid 2 colunas: Input (esquerda) + Atividades Recentes (direita) */}

        {/* ── 1. Timeline (full width) ── */}
        <ProcessTimeline
          processId={id}
          currentStatus={process.status}
          history={history}
          workflowStatuses={workflowStatuses}
        />

        {/* ── 2. Cartão meta-dados: Etiquetas + Prioridade (full width) ── */}
        <Card>
          <CardContent className="pt-4 pb-4">
            <div className="flex flex-wrap items-center gap-4">
              {/* Prioridade */}
              <div className="flex items-center gap-2">
                <Label className="text-xs text-muted-foreground">Prioridade</Label>
                <Select
                  value={process?.prioridade || "media"}
                  onValueChange={(value) => {
                    setProcess(prev => ({ ...prev, prioridade: value }));
                    if (canEditPersonal && !isProcessLocked) handleSaveOrganization();
                  }}
                  disabled={!canEditPersonal || isProcessLocked}
                >
                  <SelectTrigger className="h-8 w-28 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="baixa"><span className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-green-500" />Baixa</span></SelectItem>
                    <SelectItem value="media"><span className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-amber-500" />Média</span></SelectItem>
                    <SelectItem value="alta"><span className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-red-500" />Alta</span></SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {/* Etiquetas */}
              <div className="flex items-center gap-1.5 flex-wrap">
                <Label className="text-xs text-muted-foreground">Etiquetas</Label>
                {(Array.isArray(process?.labels) ? process.labels : []).map((label, idx) => (
                  <Badge key={idx} variant="secondary" className="text-xs gap-1 pr-1">
                    {safeString(label)}
                    {canEditPersonal && (
                      <button
                        onClick={() => setProcess(prev => ({ ...prev, labels: (prev.labels || []).filter((_, i) => i !== idx) }))}
                        className="ml-0.5 hover:text-destructive"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    )}
                  </Badge>
                ))}
                {canEditPersonal && (
                  <Input
                    value={newLabel}
                    onChange={(e) => setNewLabel(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && newLabel.trim()) {
                        e.preventDefault();
                        setProcess(prev => ({ ...prev, labels: [...(prev.labels || []), newLabel.trim()] }));
                        setNewLabel("");
                        if (!isProcessLocked) handleSaveOrganization();
                      }
                    }}
                    className="h-7 w-28 text-xs"
                    placeholder="Nova etiqueta"
                  />
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* ── 3. Grid 2 colunas: Input (esquerda) + Atividades (direita) ── */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Lado Esquerdo: Registar Atividade / Nota */}
          {!isProcessLocked && (
            <Card className="border-violet-200 dark:border-violet-900">
              <CardHeader className="pb-2 py-3">
                <CardTitle className="text-sm flex items-center gap-2">
                  <MessageSquare className="h-4 w-4 text-violet-600" />
                  Registar Atividade / Nota
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0 pb-3">
                <div className="flex gap-2">
                  <Textarea
                    placeholder="Escreva uma nota ou registo de atividade para este processo..."
                    value={newComment}
                    onChange={(e) => setNewComment(e.target.value)}
                    className="flex-1 min-h-[60px] text-sm resize-none"
                    data-testid="quick-note-input"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                        e.preventDefault();
                        handleSendComment();
                      }
                    }}
                  />
                  <Button
                    onClick={handleSendComment}
                    disabled={sendingComment || !newComment.trim()}
                    size="sm"
                    data-testid="quick-note-submit"
                    className="bg-violet-600 hover:bg-violet-700"
                  >
                    {sendingComment ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  </Button>
                </div>
                <p className="text-[10px] text-muted-foreground mt-1.5">Cmd/Ctrl+Enter para enviar rápido</p>
              </CardContent>
            </Card>
          )}

          {/* Lado Direito: Atividades Recentes / Histórico */}
          <Card>
            <CardHeader className="pb-2 py-3">
              <CardTitle className="text-sm flex items-center gap-2">
                <Clock className="h-4 w-4 text-muted-foreground" />
                Atividades Recentes
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0 pb-3">
              <ScrollArea className="h-[300px]">
                <div className="space-y-2 pr-2">
                  {activities.length === 0 ? (
                    <p className="text-center text-muted-foreground py-4 text-xs">Sem registos. Adicione a primeira nota à esquerda.</p>
                  ) : (
                    /* PACOTE BH: Ordenação descendente por data (mais recentes primeiro).
                       Antes usava-se apenas .reverse() que inverte a ordem do array tal como
                       vem do backend — frágil e incorreto se a ordem de origem mudar.
                       Agora ordena-se por created_at (fallback timestamp) de forma descendente,
                       com tratamento defensivo de datas inválidas (items sem data vão para o fim). */
                    [...activities].sort((a, b) => {
                      const dateA = safeDate(a.created_at || a.timestamp);
                      const dateB = safeDate(b.created_at || b.timestamp);
                      if (!dateA && !dateB) return 0;
                      if (!dateA) return 1;  // items sem data ficam no fim
                      if (!dateB) return -1;
                      return dateB - dateA;  // descendente — mais recentes primeiro
                    }).map((activity) => (
                      <div key={activity.id} className="p-2 bg-muted/50 rounded text-xs" data-testid={`activity-${activity.id}`}>
                        <div className="flex items-start justify-between gap-1">
                          <div className="flex-1 min-w-0">
                            <span className="font-medium">{safeString(activity.user_name)}</span>
                            <p className="text-xs mt-0.5 text-muted-foreground whitespace-pre-wrap">{safeString(activity.comment)}</p>
                            <p className="text-[10px] text-muted-foreground">{safeFormat(activity.created_at, "dd/MM HH:mm", { locale: pt })}</p>
                          </div>
                          {(activity.user_id === user.id || hasRole(user, "admin")) && (
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
            </CardContent>
          </Card>
        </div>

        {/* PACOTE BC: Cartão "Organização do Processo" removido. */}

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
                <Tabs value={activeTab} onValueChange={(v) => { setEditingCardId(null); setActiveTab(v); }}>
                  <TabsList className="grid w-full grid-cols-3 sm:grid-cols-9 gap-1 h-auto p-1">
                    {/* ── DADOS DO CLIENTE ── */}
                    <TabsTrigger value="personal" className="gap-1 text-xs sm:text-sm py-1.5 sm:py-2 bg-teal-50 dark:bg-teal-900/20 data-[state=active]:bg-teal-100 dark:data-[state=active]:bg-teal-900/40">
                      <User className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                      <span className="hidden sm:inline">Cliente</span>
                    </TabsTrigger>
                    {/* ── DADOS DO PROCESSO/NEGÓCIO ── */}
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
                    <TabsTrigger value="visitas" className="gap-1 text-xs sm:text-sm py-1.5 sm:py-2 bg-emerald-50 dark:bg-emerald-900/20 data-[state=active]:bg-emerald-100 dark:data-[state=active]:bg-emerald-900/40">
                      <Home className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                      <span className="hidden sm:inline">Visitas</span>
                    </TabsTrigger>
                    <TabsTrigger value="mensagens" className="gap-1 text-xs sm:text-sm py-1.5 sm:py-2 bg-violet-50 dark:bg-violet-900/20 data-[state=active]:bg-violet-100 dark:data-[state=active]:bg-violet-900/40 relative">
                      <MessageSquare className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                      <span className="hidden sm:inline">Mensagens</span>
                      {portal.unreadCount > 0 && (
                        <span className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 text-white text-[9px] font-bold rounded-full flex items-center justify-center">
                          {portal.unreadCount > 9 ? '9+' : portal.unreadCount}
                        </span>
                      )}
                    </TabsTrigger>
                  </TabsList>

                  {/* ── FASE 3: Tab Dados do Cliente ── */}
                  <TabsContent value="personal" className="mt-4">
                    <ProcessPersonalTab
                      personalData={personalData}
                      setPersonalData={setPersonalData}
                      process={process}
                      setProcess={setProcess}
                      clientId={clientId}
                      nifError={nifError}
                      setNifError={setNifError}
                      editingCardId={editingCardId}
                      canEditPersonal={canEditPersonal}
                      CardHeaderWithEdit={CardHeaderWithEdit}
                      getConfidenceIndicator={getConfidenceIndicator}
                      getFieldMetaFor={getFieldMetaFor}
                      fetchData={fetchData}
                      financialData={financialData}
                    />
                  </TabsContent>

                  {/* Financial Data Tab */}
                  <TabsContent value="financial" className="mt-4">
                    <ProcessFinancialTab
                      titular2Data={titular2Data}
                      setTitular2Data={setTitular2Data}
                      financialData={financialData}
                      setFinancialData={setFinancialData}
                      process={process}
                      editingCardId={editingCardId}
                      editingCreditField={editingCreditField}
                      setEditingCreditField={setEditingCreditField}
                      showPortalSenha={showPortalSenha}
                      setShowPortalSenha={setShowPortalSenha}
                      showSegSocialSenha={showSegSocialSenha}
                      setShowSegSocialSenha={setShowSegSocialSenha}
                      canEditFinancial={canEditFinancial}
                      CardHeaderWithEdit={CardHeaderWithEdit}
                      getFieldMetaFor={getFieldMetaFor}
                      token={token}
                      id={id}
                      shouldCardBeCollapsed={shouldCardBeCollapsed}
                    />
                  </TabsContent>

                  {/* Real Estate Tab */}
                  <TabsContent value="realestate" className="space-y-4 mt-4">
                    <ProcessRealEstateTab
                      financialData={financialData}
                      setFinancialData={setFinancialData}
                      realEstateData={realEstateData}
                      setRealEstateData={setRealEstateData}
                      editingCardId={editingCardId}
                      canEditRealEstate={canEditRealEstate}
                      CardHeaderWithEdit={CardHeaderWithEdit}
                      getFieldMetaFor={getFieldMetaFor}
                      shouldCardBeCollapsed={shouldCardBeCollapsed}
                    />
                  </TabsContent>

                  {/* Credit Tab */}
                  <TabsContent value="credit" className="space-y-4 mt-4">
                    <ProcessCreditTab
                      realEstateData={realEstateData}
                      creditData={creditData}
                      setCreditData={setCreditData}
                      editingCardId={editingCardId}
                      canEditCredit={canEditCredit}
                      CardHeaderWithEdit={CardHeaderWithEdit}
                      getFieldMetaFor={getFieldMetaFor}
                      shouldCardBeCollapsed={shouldCardBeCollapsed}
                      collapsedCards={collapsedCards}
                    />
                  </TabsContent>

                  {/* Documents Tab - Destaque para fácil acesso */}
                  <TabsContent value="documents" className="mt-4">
                    <div className="space-y-4">
                      {/* Header com info — só visível para admin e CEO */}
                      {hasAnyRole(user, ["admin", "ceo"]) && (
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
                      )}

                      {/* PACOTE DB — AI Executive Summary temporariamente oculto (display: none).
                          O Card é mantido para reativação futura — não apagar.
                          Originalmente: só visível para admin e CEO. */}
                      {/* eslint-disable-next-line no-constant-binary-expression -- feature flag off until AI summary is re-enabled */}
                      {hasAnyRole(user, ["admin", "ceo"]) && false && (
                      <Card className="border-indigo-200 dark:border-indigo-800 bg-gradient-to-r from-indigo-50/50 to-purple-50/50 dark:from-indigo-900/10 dark:to-purple-900/10" style={{ display: 'none' }}>
                        <CardContent className="pt-4">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                              <div className="p-2 bg-indigo-100 dark:bg-indigo-900/40 rounded-lg">
                                <BrainCircuit className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
                              </div>
                              <div>
                                <h3 className="font-semibold text-sm text-indigo-800 dark:text-indigo-200">Resumo Executivo IA</h3>
                                <p className="text-xs text-indigo-600 dark:text-indigo-400">
                                  Auditoria cruzada entre dados declarados e documentos
                                </p>
                              </div>
                            </div>
                            <div className="flex items-center gap-2">
                              {aiAnalysisDate && (
                                <span className="text-xs text-muted-foreground hidden sm:inline">
                                  {safeFormat(aiAnalysisDate, "dd/MM/yyyy HH:mm", { locale: pt })}
                                </span>
                              )}
                              {aiSummary && !aiAnalysisLoading ? (
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() => handleAiAnalysis(true)}
                                  className="border-indigo-300 text-indigo-700 hover:bg-indigo-100 dark:border-indigo-700 dark:text-indigo-300"
                                >
                                  <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
                                  Atualizar
                                </Button>
                              ) : (
                                <Button
                                  size="sm"
                                  onClick={() => handleAiAnalysis(true)}
                                  disabled={aiAnalysisLoading}
                                  className="bg-indigo-600 hover:bg-indigo-700 text-white"
                                >
                                  {aiAnalysisLoading ? (
                                    <>
                                      <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                                      A cruzar dados e a ler documentos...
                                    </>
                                  ) : (
                                    <>
                                      <Sparkles className="h-3.5 w-3.5 mr-1.5" />
                                      {aiSummary ? "Atualizar Análise IA" : "Analisar IA (Auditoria)"}
                                    </>
                                  )}
                                </Button>
                              )}
                            </div>
                          </div>

                          {/* Loading state */}
                          {aiAnalysisLoading && (
                            <div className="mt-4 flex items-center gap-3 p-4 bg-indigo-50 dark:bg-indigo-900/20 rounded-lg">
                              <div className="flex gap-1">
                                <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                                <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                                <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                              </div>
                              <p className="text-sm text-indigo-700 dark:text-indigo-300">
                                A IA está a cruzar os dados do formulário com os documentos extraídos...
                              </p>
                            </div>
                          )}

                          {/* Summary result */}
                          {aiSummary && !aiAnalysisLoading && (
                            <div className="mt-4 p-4 bg-white dark:bg-gray-900 border rounded-lg max-h-[600px] overflow-y-auto">
                              <div className="prose prose-sm dark:prose-invert max-w-none">
                                {renderAiSummary(aiSummary)}
                              </div>
                            </div>
                          )}
                        </CardContent>
                      </Card>
                      )}

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

                      {/* Pedidos de Documentos do Portal */}
                      <PortalDocumentRequests
                        processId={id}
                        onDocumentsChange={() => setDocumentsRefreshKey(k => k + 1)}
                      />
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
                            clientEmail={savedProcessRef.current?.client_email || process?.client_email}
                            clientName={savedProcessRef.current?.client_name || process?.client_name}
                            compact={false}
                            maxHeight="500px"
                            token={token}
                          />
                        </CardContent>
                      </Card>
                    </div>
                  </TabsContent>

                  {/* Visitas / Imóveis Tab */}
                  <TabsContent value="visitas" className="mt-4">
                    <VisitasTab processId={id} />
                  </TabsContent>

                  {/* Mensagens do Portal Tab */}
                  <TabsContent value="mensagens" className="mt-4">
                    <ProcessPortalMessagesTab
                      messages={portal.messages}
                      loading={portal.loading}
                      newMessage={portal.newMessage}
                      setNewMessage={portal.setNewMessage}
                      sending={portal.sending}
                      onRefresh={portal.fetchMessages}
                      onSend={portal.sendMessage}
                    />
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
                        {typeof process.ai_extracted_notes === 'string'
                          ? process.ai_extracted_notes
                          : JSON.stringify(process.ai_extracted_notes, null, 2)}
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
                            <span>Criado: <strong>{safeString(process?.created_by, "Sistema")}</strong></span>
                            <span>Fonte: <strong>{safeString(process?.lead_source, "Manual")}</strong></span>
                            {process.updated_by && <span>Últ. edição: <strong>{safeString(process?.updated_by)}</strong></span>}
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
            {/* PACOTE AQ: Cartão "Atividade" movido para o topo do layout
                (agora integrado no cartão "Atividade & Notas" com a Timeline). */}

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
                                      {selectedDate && isValid(selectedDate) ? format(selectedDate, "PPP", { locale: pt }) : "Selecione"}
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
                                    {safeString(deadline.title)}
                                  </p>
                                  <p className="text-xs text-muted-foreground font-mono">
                                    {safeFormat(deadline.due_date, "dd/MM/yyyy")}
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
              <p className="font-medium">{safeString(clientData?.nome || process?.client_name || personalData?.nome_completo) || 'Cliente'}</p>
              <p className="text-sm text-muted-foreground">
                #{safeString(process?.process_number, '—')}
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
                  {filterByAnyRole(appUsers, ["consultor", "diretor", "admin", "ceo", "administrativo"])
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
                  {filterByAnyRole(appUsers, ["consultor", "diretor", "admin", "ceo", "administrativo"]).length === 0 && (
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
                  {filterByAnyRole(appUsers, ["intermediario", "intermediario", "intermediario_credito", "diretor"])
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
                  {filterByAnyRole(appUsers, ["intermediario", "intermediario", "intermediario_credito", "diretor"]).length === 0 && (
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
                    {filterByAnyRole(appUsers, ["indexacao", "administrativo", "admin", "ceo"])
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
                    {filterByRole(appUsers, "parceiro")
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
                    <div className="font-medium">{safeString(conflict.existing_value, "-")}</div>
                  </div>
                  
                  <div 
                    className="border rounded p-3 cursor-pointer hover:border-green-500 hover:bg-green-50 dark:hover:bg-green-950"
                    onClick={() => resolveAIConflict(conflict.field, conflict.new_value)}
                  >
                    <div className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
                      <Sparkles className="h-3 w-3" />
                      Valor Extraído (IA)
                    </div>
                    <div className="font-medium text-green-700 dark:text-green-400">{safeString(conflict.new_value, "-")}</div>
                    {conflict.source && (
                      <div className="text-xs text-muted-foreground mt-1">Fonte: {safeString(conflict.source)}</div>
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
