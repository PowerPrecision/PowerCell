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
import { Link, useParams, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { safeLabel } from "../components/dashboard/DashboardShared";
import { buildStatusOptions, formatStatusLabel } from "../utils/workflowStatuses";
import DashboardLayout from "../layouts/DashboardLayout";
import useWebSocket from "../hooks/useWebSocket";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Input } from "../components/ui/input";
// PACOTE DD — Label deixou de ser usado após remover o cartão de Etiquetas (badges compactos no PageHeader)
// PACOTE 9 — Label reactivado para o Toggle "Indexado" no header
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
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
} from "../components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Separator } from "../components/ui/separator";
// PACOTE 9 — Toggle "Indexado" (Switch shadcn) no header do processo
import { Switch } from "../components/ui/switch";
// PACOTE DD — ScrollArea para limitar altura do painel de Tarefas
import { ScrollArea } from "../components/ui/scroll-area";
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
  deleteProcess,
  generateMagicLink,
  sendMagicLinkEmail,
  impersonateClientPortal,
  // PACOTE DE — Download RGPD pré-preenchido (PDF para assinatura manual)
  downloadRGPDF,
  getStaffUsers,
  getUsers,
  addProcessObservationNote,
  // PACOTE 9 — Toggle "Indexado" no header (set-indexed true/false)
  setProcessIndexed,
  // PACOTE 11 (Eixo 4) — restauro rápido do processo eliminado (banner)
  restoreProcess,
  // ÉPICO 7 — nota de voz do consultor
  uploadVoiceNote,
  // Ponto 15 — catálogo de etiquetas para as sugestões do editor
  getProcessLabels,
} from "../services/api";
import ProcessDomainTabsList from "../components/processDetails/ProcessDomainTabsList";
import AIReviewDialog from "../components/processDetails/dialogs/AIReviewDialog";
import {
  aplicarDecisaoNaRevisao,
  prepararRevisaoDaExtraccao,
} from "../utils/documentExtraction";
import { resumirAnaliseEmLote } from "../utils/analiseEmLoteFeedback";
import RGPDRequestDialog from "../components/processDetails/dialogs/RGPDRequestDialog";
import TitularChoiceDialog from "../components/processDetails/dialogs/TitularChoiceDialog";
import useTaskEvents from "../hooks/useTaskEvents";
import {
  eNotaDeVozDoProcesso,
  mensagemDeConclusao,
} from "../utils/voiceNote";
import { useProcessMutations } from "../hooks/mutations/useProcessMutations";
import { sanitizeProcessUpdatePayload } from "./processDetails/processUpdatePayload";
import ProcessAlerts from "../components/ProcessAlerts";
import TasksPanel from "../components/TasksPanel";
import ClientPropertyMatch from "../components/ClientPropertyMatch";
import ProcessAssignDialog from "../components/processDetails/ProcessAssignDialog";
import ClientContextCard from "../components/processDetails/ClientContextCard";
import AssignmentContextCard from "../components/processDetails/AssignmentContextCard";
import DataConflictResolver from "../components/DataConflictResolver";
import CPCVModal from "../components/CPCVModal";
import AutoDSTIBadge from "../components/AutoDSTIBadge";
import { getFieldMeta, buildManualMetadata } from "../components/ui/AIBadge";
import TempLinkButton from "../components/TempLinkButton";
import SendDocumentationModal from "../components/SendDocumentationModal";
import {
  ArrowLeft,
  User,
  Briefcase,
  Building2,
  CreditCard,
  CalendarClock,
  ClipboardList,
  Check,
  Trash2,
  RotateCcw,
  Loader2,
  AlertCircle,
  MessageSquare,
  History,
  Send,
  FolderOpen,
  ChevronDown,
  ExternalLink,
  Link as LinkIcon,
  Sparkles,
  Mail,
  Phone,
  FileSignature,
  FileDown,
  AlertTriangle,
  CheckCircle,
  Database,
  Lock,
  Eye,
  X,
  Home,
  Shield,
} from "lucide-react";
import { toast } from "sonner";
import { format, isValid } from "date-fns";
import { hasRole, hasAnyRole, ROLE_LABELS } from "../utils/roleUtils";
import { safeCopyToClipboard } from "../utils/clipboard";
import { safeString, safeStringArray } from "../utils/safeString";
import { extractErrorMessage } from "../utils/extractErrorMessage";
import { safeParseISO } from "../lib/utils";
import { applyProcessDelta } from "../utils/processDelta";
import { notifyFinancialEngine } from "../utils/financialEngineFeedback";

import {
  cleanPersonalDataForSubmit,
  cleanTitular2DataForSubmit,
  cleanRealEstateDataForSubmit,
  cleanCreditDataForSubmit,
  cleanFinancialDataForSubmit,
} from "./processDetails/processFormCleaners";
import { validateNIF } from "../utils/validateNIF";
import CardHeaderWithEditBase from "../components/processDetails/CardHeaderWithEdit";
import { useProcessPortalMessages } from "../hooks/useProcessPortalMessages";
import { useQueryClient } from "@tanstack/react-query";
import { invalidateProcessDetailsQueries } from "../lib/queryClient";
import { useProcessFullData } from "../hooks/queries/useProcessQuery";
import { deriveProcessDetailsViewModel, resolveAssignedNames } from "./processDetails/processDetailsHydration";
// Sub-componentes das abas — cada um é responsável apenas pelo seu domínio
// (SRP); ProcessDetails.js fica como orquestrador do layout + estado.
import PersonalInfoTab from "../components/processDetails/tabs/PersonalInfoTab";
import FinancialTab from "../components/processDetails/tabs/FinancialTab";
import RealEstateTab from "../components/processDetails/tabs/RealEstateTab";
import CreditTab from "../components/processDetails/tabs/CreditTab";
import DocumentsTab from "../components/processDetails/tabs/DocumentsTab";
import EmailsTab from "../components/processDetails/tabs/EmailsTab";
import VisitasTab from "../components/processDetails/tabs/VisitasTab";
import PortalMessagesTab from "../components/processDetails/tabs/PortalMessagesTab";
import DeadlinesTab from "../components/processDetails/tabs/DeadlinesTab";
import HistoryTab from "../components/processDetails/tabs/HistoryTab";
import ProcessObservationsCard from "../components/processDetails/ProcessObservationsCard";
import ProcessLabelsEditor from "../components/processDetails/ProcessLabelsEditor";
import ProcessSummaryTimeline from "../components/processDetails/ProcessSummaryTimeline";
import { PageHeader } from "../components/shared/PageHeader";
// Ponto 17 — Navegação Contígua. O hook resolve os vizinhos a partir do
// contexto que a listagem trouxe (zero pedidos) e só pergunta ao
// servidor na fronteira da página.
import ProcessNavigator from "../components/processDetails/ProcessNavigator";
import { useProcessNeighbours } from "../hooks/useProcessNeighbours";
import { StatusBadge } from "../components/shared/StatusBadge";
import { resolveProcessTabsFromQuery } from "../utils/processDeepLink";

const API_URL = process.env.REACT_APP_BACKEND_URL || "";

// Constantes/helpers: processDetailsConstants, processFormCleaners, validateNIF

const ProcessDetails = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user, token, effectiveRole } = useAuth();
  const queryClient = useQueryClient();

  // Ponto 17 — vizinhos na listagem de origem.
  const vizinhos = useProcessNeighbours(id);
  const irParaProcesso = useCallback((destinoId) => {
    // O contexto viaja com a seta: sem isto, o primeiro clique
    // consumia-o e o segundo já não teria vizinhança nenhuma.
    navigate(`/process/${destinoId}`, {
      state: { contextoDeNavegacao: vizinhos.contexto },
    });
  }, [navigate, vizinhos.contexto]);

  // Live TanStack queries (process + client + side panels)
  const processBundle = useProcessFullData(id);
  // Side panels consomem a query directamente — sem copiar para useState.
  const deadlines = processBundle.deadlines;
  const activities = processBundle.activities;
  const history = processBundle.history;
  const workflowStatuses = processBundle.workflowStatuses;

  // Mutations TanStack (silent — toasts ficam na página; payload sanitizado no hook)
  const processMutations = useProcessMutations(id, {
    silent: true,
    clientId: processBundle.process?.client_id,
  });
  
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
    // BUGFIX (reatividade do cartão de Atribuição) — reagir ao delta de
    // processo. Quem clica em "Indexado" já vê o cartão actualizado pelo
    // refetch, mas OUTRO operador com o mesmo processo aberto não via nada:
    // esta página não escutava `process_updated`. A auto-atribuição
    // pós-indexação difunde agora um delta com os nomes/ids já resolvidos,
    // que aqui é fundido no estado local (sem refetch).
    onProcessUpdate: (_type, data) => {
      setProcess((prev) => applyProcessDelta(prev, data, id));
    },
  });
  const [process, setProcess] = useState(null);
  // ── Fase 3: Estado separado do Cliente (entidade independente) ──
  const [clientData, setClientData] = useState(null);   // Dados completos do cliente (GET /clients/{id})
  const [clientId, setClientId] = useState(null);       // FK para a coleção clients
  // Guardar os dados originais do processo (da BD) para componentes
  // que precisam dos valores guardados (ex: email para notificações)
  const savedProcessRef = useRef(null);
  const lastHydratedAtRef = useRef(0);
  const wasEditingRef = useRef(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingObservations, setSavingObservations] = useState(false);
  const initialTabs = resolveProcessTabsFromQuery(searchParams.get("tab"));
  const [activeTab, setActiveTab] = useState(initialTabs.activeTab);
  // Separadores de topo (Progressive Disclosure): Resumo / Documentos / Histórico
  const [mainTab, setMainTab] = useState(initialTabs.mainTab);

  // Mensagens do Portal — estado/polling vivem no hook (badge do tab precisa de unread)
  // Declarados ANTES do hook do portal de propósito: o `if (notFound) return`
  // da página é um early return no RENDER, e os hooks correm antes dele. Sem
  // isto, a página mostrava "Processo não encontrado" enquanto continuava a
  // interrogar o servidor sobre o processo eliminado, de 30 em 30 segundos.
  const [notFound, setNotFound] = useState(false);
  const [accessDenied, setAccessDenied] = useState(false);

  const portal = useProcessPortalMessages(id, {
    isActive: activeTab === "mensagens",
    enabled: !notFound && !accessDenied,
  });
  portalRefreshRef.current = portal.refresh;

  const tabQuery = searchParams.get("tab");
  useEffect(() => {
    const next = resolveProcessTabsFromQuery(tabQuery);
    setMainTab(next.mainTab);
    setActiveTab(next.activeTab);
  }, [tabQuery]);

  const writeTabQuery = (main, inner) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      let tab = "";
      if (main && main !== "resumo") tab = main;
      else if (inner === "mensagens") tab = "portal";
      else if (inner && inner !== "personal") tab = inner;
      if (tab) next.set("tab", tab);
      else next.delete("tab");
      return next;
    }, { replace: true });
  };


  
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
  // ── Nota de voz (Épico 7) ────────────────────────────────────────
  // Declarado JUNTO DO RESTANTE ESTADO, e não ao pé dos handlers: um
  // `const` usado por um `useCallback` declarado antes dele fica na zona
  // morta temporal e rebenta no primeiro render (regressão do Épico 6).
  // Processo actualmente hidratado — distingue a montagem de uma mudança
  // de processo no efeito de reset (ver o BUGFIX do Épico 8 abaixo).
  const processoAnteriorRef = useRef(null);
  const [voiceNoteOpen, setVoiceNoteOpen] = useState(false);
  const [aEnviarNotaDeVoz, setAEnviarNotaDeVoz] = useState(false);
  const [notaDeVozEmCurso, setNotaDeVozEmCurso] = useState(null);

  // Deadline dialog
  const [isDeadlineDialogOpen, setIsDeadlineDialogOpen] = useState(false);
  const [deadlineForm, setDeadlineForm] = useState({
    title: "",
    description: "",
    due_date: "",
    priority: "medium",
    // PACOTE DH — Agenda evolution: type / reminder_time / visible_to_client
    type: "deadline",
    reminder_time: null,
    visible_to_client: false,
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

  // PACOTE DD — newLabel removido (edição inline de etiquetas movida para um Dialog
  // accionado pelo botão "+" ao lado dos badges no PageHeader; estado agora local ao Dialog)
  // const [newLabel, setNewLabel] = useState("");

  // Buscar utilizadores
  const fetchUsers = async () => {
    setLoadingUsers(true);
    try {
      const [staffRes, idxRes, partnerRes] = await Promise.all([
        getStaffUsers().catch(() => ({ data: [] })),
        getUsers("indexacao").catch(() => ({ data: [] })),
        getUsers("parceiro").catch(() => ({ data: [] })),
      ]);
      const merged = [
        ...(Array.isArray(staffRes?.data) ? staffRes.data : []),
        ...(Array.isArray(idxRes?.data) ? idxRes.data : []),
        ...(Array.isArray(partnerRes?.data) ? partnerRes.data : []),
      ].filter((u) => u && u.is_active !== false);
      const byId = new Map();
      merged.forEach((u) => {
        if (u.id) byId.set(u.id, u);
      });
      const activeUsers = [...byId.values()];
      setAppUsers(activeUsers);
      return activeUsers;
    } catch (error) {
      console.error("Erro ao buscar utilizadores:", error);
      toast.error("Erro ao carregar utilizadores");
    } finally {
      setLoadingUsers(false);
    }
    return [];
  };

  // Buscar estado do RGPD
  // PACOTE 12 (Eixo 1) — aceita um AbortSignal: o effect de [id] aborta o
  // pedido quando o processo muda ou o ecrã desmonta, evitando setStates
  // tardios em componente desmontado e respostas obsoletas (do processo
  // anterior) a sobrescreverem o estado do processo novo.
  const fetchRgpdStatus = async (signal) => {
    if (!id) return;
    setRgpdLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/rgpd/status/${id}`, {
        headers: { Authorization: `Bearer ${token}` },
        signal,
      });
      if (response.ok) {
        const data = await response.json();
        if (!signal?.aborted) setRgpdStatus(data);
      } else if (response.status === 404) {
        // Processo sem pedido RGPD ainda — estado neutro, sem erro na UI.
        if (!signal?.aborted) setRgpdStatus(null);
      }
    } catch {
      // RGPD status check failed silently — not critical
      // (o aborto do cleanup do effect também cai aqui e é ignorado)
      if (signal?.aborted) return;
      setRgpdStatus(null);
    } finally {
      if (!signal?.aborted) setRgpdLoading(false);
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

  // PACOTE DE — Download RGPD PDF pré-preenchido (assinatura manual)
  // Chama GET /api/rgpd/pdf/{process_id} (backend já implementa) e descarrega
  // o PDF com nome seguro baseado no nome do cliente (sem acentos/espaços).
  // PACOTE 5 — `titular` define o titular alvo ("first" | "second"): o PDF
  // do 2º titular é preenchido exclusivamente com os dados dessa pessoa.
  const handleDownloadRgpdPdf = async (titular = "first") => {
    try {
      const res = await downloadRGPDF(id, titular);
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement("a");
      link.href = url;
      const baseName =
        titular === "second"
          ? (titular2Data?.nome || titular2Data?.name || process?.second_client_data?.nome || "2o_Titular")
          : (process?.client_name || "cliente");
      const safeName = (baseName)
        .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
        .replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 50);
      const suffix = titular === "second" ? "_2o_Titular" : "";
      link.setAttribute("download", `RGPD_${safeName}${suffix}.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      toast.success(
        titular === "second"
          ? "RGPD pré-preenchido do 2º titular descarregado."
          : "RGPD pré-preenchido descarregado."
      );
    } catch (error) {
      // O endpoint devolve JSON de erro (não blob) quando falha — tentamos ler
      // como texto e fazer parse do detail. Se falhar o parse, fallback p/ message.
      let detail = error?.message || "Erro ao gerar PDF do RGPD.";
      try {
        const raw = error?.response?.data;
        if (raw instanceof Blob) {
          const txt = await raw.text();
          try { detail = JSON.parse(txt)?.detail || detail; } catch { detail = txt || detail; }
        } else if (raw?.detail) {
          detail = raw.detail;
        }
      } catch {
        // mantém o detail default
      }
      toast.error(detail);
    }
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
          // PACOTE 5 — feedback do 2º envio independente (quando o processo
          // tem 2º titular com nome e email válidos, o backend dispara 2
          // emails, um por titular, cada um com o seu link de assinatura).
          if (data.second_titular_name) {
            if (data.second_email_sent) {
              toast.success(
                `Emails de RGPD enviados para o 1º titular e para ${data.second_titular_name} (2º titular) — cada um com o seu link de assinatura.`
              );
            } else {
              toast.success("Email de RGPD enviado para o cliente!");
              toast.warning(
                `Não foi possível enviar o email para o 2º titular (${data.second_titular_name}). Verifique o email dele na ficha do processo.`
              );
            }
          } else {
            toast.success("Email de RGPD enviado para o cliente!");
          }
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
      await processMutations.assignProcess.mutateAsync({
        consultorIds: selectedConsultores.filter(Boolean),
        mediadorIds: selectedMediadores.filter(Boolean),
        indexacaoId: selectedIndexacao || "",
        parceiroId: selectedParceiro || "",
      });
      toast.success("Atribuições actualizadas com sucesso");
      setShowAssignDialog(false);
      await fetchData();
    } catch (error) {
      console.error("Erro ao guardar atribuições:", error);
      toast.error(extractErrorMessage(error.response?.data?.detail, "Erro ao guardar atribuições"));
    } finally {
      setSavingAssignment(false);
    }
  };

  // Estado para dados extraídos pela IA com conflitos
  const [aiExtractedData, setAiExtractedData] = useState(null);
  const [aiFieldConfidence, setAiFieldConfidence] = useState({});
  const [aiConflicts, setAiConflicts] = useState([]);
  const [showAIReviewDialog, setShowAIReviewDialog] = useState(false);
  // Épico 9 — extracção por ficheiro à espera de confirmação.
  // Enquanto isto não for `null`, NADA foi escrito: nem no formulário, nem
  // na base de dados. É o que separa este caminho do da análise em lote.
  const [revisaoPendente, setRevisaoPendente] = useState(null);
  const [titularChoiceDialog, setTitularChoiceDialog] = useState({
    open: false,
    items: [],
    pendingPayload: null,
  });

  const applySharedExtractedFields = (extractedData) => {
    if (!extractedData) return;
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

    const newCreditData = { ...creditData };
    if (extractedData.valuation_value || extractedData.valor_avaliacao) newCreditData.valuation_value = extractedData.valuation_value || extractedData.valor_avaliacao;
    if (extractedData.valuation_date || extractedData.data_avaliacao) newCreditData.valuation_date = extractedData.valuation_date || extractedData.data_avaliacao;
    if (extractedData.valuation_bank || extractedData.banco_avaliacao) newCreditData.valuation_bank = extractedData.valuation_bank || extractedData.banco_avaliacao;
    if (extractedData.valuation_notes || extractedData.notas_avaliacao) newCreditData.valuation_notes = extractedData.valuation_notes || extractedData.notas_avaliacao;
    setCreditData(newCreditData);
  };

  const applyPersonalAndFinancialToTitular = (extractedData, targetTitular) => {
    if (!extractedData || targetTitular === "ignore") return;

    const personalPatch = {};
    if (extractedData.nif) personalPatch.nif = extractedData.nif;
    if (extractedData.documento_id || extractedData.cc_number) personalPatch.documento_id = extractedData.documento_id || extractedData.cc_number;
    if (extractedData.data_nascimento || extractedData.birth_date) personalPatch.data_nascimento = extractedData.data_nascimento || extractedData.birth_date;
    if (extractedData.cc_validity || extractedData.data_validade_cc) personalPatch.data_validade_cc = extractedData.cc_validity || extractedData.data_validade_cc;
    if (extractedData.naturalidade) personalPatch.naturalidade = extractedData.naturalidade;
    if (extractedData.nacionalidade || extractedData.nationality) personalPatch.nacionalidade = extractedData.nacionalidade || extractedData.nationality;
    if (extractedData.estado_civil) personalPatch.estado_civil = extractedData.estado_civil;
    if (extractedData.sexo || extractedData.gender) personalPatch.sexo = extractedData.sexo || extractedData.gender;
    if (extractedData.profissao || extractedData.profession) personalPatch.profissao = extractedData.profissao || extractedData.profession;
    const addr = extractedData.morada_fiscal || extractedData.fiscal_address || extractedData.morada || extractedData.address || "";
    if (addr) personalPatch.morada_fiscal = addr;
    if (extractedData.codigo_postal || extractedData.postal_code) personalPatch.codigo_postal = extractedData.codigo_postal || extractedData.postal_code;
    if (extractedData.email) personalPatch.email = extractedData.email;
    if (extractedData.phone || extractedData.telefone) personalPatch.phone = extractedData.phone || extractedData.telefone;
    if (extractedData.nome || extractedData.name || extractedData.client_name) {
      personalPatch.name = extractedData.nome || extractedData.name || extractedData.client_name;
      personalPatch.nome = personalPatch.name;
    }

    const financialPatch = {};
    const liq = extractedData.monthly_income || extractedData.rendimento_mensal || extractedData.salario_liquido;
    if (liq) financialPatch.monthly_income = liq;
    const brut = extractedData.rendimento_bruto || extractedData.salario_bruto;
    if (brut) financialPatch.rendimento_bruto = brut;
    if (extractedData.employer_name || extractedData.empresa || extractedData.entidade_patronal) {
      financialPatch.employer_name = extractedData.employer_name || extractedData.empresa || extractedData.entidade_patronal;
    }
    if (extractedData.employment_type || extractedData.tipo_contrato) {
      financialPatch.tipo_contrato = extractedData.employment_type || extractedData.tipo_contrato;
    }
    if (extractedData.categoria_profissional) financialPatch.categoria_profissional = extractedData.categoria_profissional;
    if (extractedData.subsidiario_alimentacao) financialPatch.subsidiario_alimentacao = extractedData.subsidiario_alimentacao;
    if (extractedData.data_referencia || extractedData.reference_date) {
      financialPatch.data_referencia = extractedData.data_referencia || extractedData.reference_date;
    }
    if (extractedData.employer_nif || extractedData.nif_entidade) {
      financialPatch.employer_nif = extractedData.employer_nif || extractedData.nif_entidade;
    }

    if (targetTitular === "titular2") {
      setTitular2Data((prev) => ({ ...prev, ...personalPatch, ...financialPatch }));
    } else {
      setPersonalData((prev) => ({ ...prev, ...personalPatch }));
      setFinancialData((prev) => ({ ...prev, ...financialPatch }));
    }
  };

  const persistAISuggestions = async (extractedData, documentsProcessed, targetTitular) => {
    try {
      const token = localStorage.getItem("token");
      const applyRes = await fetch(`${API_URL}/api/documents/ai-apply-suggestions/${id}`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          ...extractedData,
          target_titular: targetTitular || "titular1",
        }),
      });
      if (applyRes.ok) {
        const who = targetTitular === "titular2" ? "2º titular" : "titular 1";
        toast.success(`Campos pré-preenchidos (${who}) e guardados com dados de ${documentsProcessed} documento(s)`);
      } else {
        toast.success(`Campos pré-preenchidos com dados de ${documentsProcessed} documento(s). Guarde manualmente.`);
      }
    } catch (applyErr) {
      console.warn("Erro ao aplicar sugestões IA:", applyErr);
      toast.success(`Campos pré-preenchidos com dados de ${documentsProcessed} documento(s). Guarde manualmente.`);
    }
  };

  /**
   * Entrega a extracção em LOTE ao diálogo de revisão.
   *
   * REGRA DE OURO, SEM EXCEPÇÃO: nada é escrito na ficha antes de o
   * consultor confirmar. Este caminho fazia-o — abria o diálogo quando
   * havia conflitos e, quando não havia, gravava directamente em
   * `/ai-apply-suggestions`.
   *
   * E "sem conflitos" não era o caso benigno: um conflito só existe
   * quando a ficha JÁ TEM outro valor. Ficha vazia = zero conflitos =
   * tudo o que a IA leu entrava de uma vez, sem ninguém ver.
   *
   * O diálogo abre agora sempre, e mostra os dois grupos: o que colide
   * (a decidir) e o que vai preencher campos vazios (a confirmar).
   */
  const commitAIExtractedData = async (payload, targetTitular) => {
    const {
      extractedData,
      fieldConfidence,
      conflicts,
      documentsProcessed,
      documentsSucceeded,
      documentsFailed,
    } = payload;

    // "VLM no Escuro" (Lote 5, P0): aqui havia um `return` mudo. Com a
    // chave da OpenAI em falta a resposta chegava com `extracted_data`
    // vazio, este `if` disparava e a UI ficava sem nada — depois de um
    // toast VERDE dado pelo `S3FileManager`. Um desfecho sem palavra
    // nenhuma é indistinguível de a aplicação estar avariada.
    const dizerODesfecho = (temRevisao) => {
      const { tipo, texto } = resumirAnaliseEmLote({
        documentsCount: documentsProcessed,
        documentsSucceeded,
        documentsFailed,
        temRevisao,
      });
      if (tipo === "erro") toast.error(texto);
      else if (tipo === "aviso") toast.warning(texto);
      else toast.success(texto);
    };

    if (!extractedData || Object.keys(extractedData).length === 0) {
      dizerODesfecho(false);
      return;
    }

    if (targetTitular === "ignore") {
      // Só os campos partilhados (imóvel) — nada de identidade nem de
      // rendimentos, que é o que o "ignorar" quer dizer.
      applySharedExtractedFields(extractedData);
    } else {
      const revisao = prepararRevisaoDaExtraccao({
        extractedData,
        conflicts,
        sourceDocument:
          documentsProcessed > 1
            ? `${documentsProcessed} documentos analisados`
            : "1 documento analisado",
        targetTitular,
        documentsProcessed,
      });

      // O segundo `return` mudo vivia aqui: sem `else`, um `revisao`
      // nulo (a IA leu mas não reconheceu campo nenhum) não abria o
      // diálogo nem dizia porquê.
      dizerODesfecho(!!revisao);

      if (revisao) {
        setAiConflicts(revisao.conflicts);
        setRevisaoPendente(revisao);
        setShowAIReviewDialog(true);
        if (revisao.conflicts.length > 0) {
          toast.info(
            `${revisao.conflicts.length} conflito(s) detectado(s). Reveja os valores.`,
          );
        }
      } else {
        return;
      }
    }

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

    setActiveTab("personal");
  };

  /**
   * Épico 9 — dados lidos de UM documento, à espera de revisão.
   *
   * REGRA DE OURO: ao contrário da análise em lote (que pré-preenche o
   * formulário e, quando não há conflitos, chega a gravar sozinha em
   * `/ai-apply-suggestions`), aqui não se toca em nada antes do "Confirmar".
   * São dados pessoais e financeiros lidos por um modelo de visão: uma
   * alucinação sobre um NIF ou um vencimento não pode entrar na ficha sem
   * um humano a validar.
   *
   * O diálogo abre SEMPRE, mesmo sem conflitos — sem conflitos é
   * precisamente o caso em que a ficha está vazia e tudo o que a IA leu
   * vai entrar de novo.
   */
  const handleDocumentDataExtracted = ({
    extractedData,
    conflicts,
    sourceDocument,
    titularMatches,
  }) => {
    const revisao = prepararRevisaoDaExtraccao({
      extractedData,
      conflicts,
      sourceDocument,
      titularMatches,
    });
    if (!revisao) {
      toast.warning("A IA não devolveu dados deste documento.");
      return;
    }

    setAiConflicts(revisao.conflicts);
    setRevisaoPendente(revisao);
    setShowAIReviewDialog(true);
  };

  // Handler para dados extraídos pela IA dos documentos
  const handleAIDataExtractedFromDocs = async ({
    extractedData,
    fieldConfidence,
    conflicts,
    documentsProcessed,
    suggestions,
    titularMatches,
    needsTitularChoice,
  }) => {
    setAiExtractedData(extractedData);
    setAiFieldConfidence(fieldConfidence || {});
    setAiConflicts(conflicts || []);

    const matches = titularMatches || [];
    const aggregate = matches.find((m) => m.scope === "process_aggregate");
    const docsNeedingChoice = matches.filter(
      (m) => m.scope === "document" && m.needs_user_choice && m.has_second_titular
    );

    if (needsTitularChoice && (docsNeedingChoice.length > 0 || aggregate?.needs_user_choice)) {
      const items =
        docsNeedingChoice.length > 0
          ? docsNeedingChoice.map((m) => ({
              key: m.file_name || `doc-${m.match}`,
              file_name: m.file_name || "Documento",
              titular1_name: m.titular1_name || "Titular 1",
              titular2_name: m.titular2_name || "Titular 2",
              choice:
                m.match === "titular2" ? "titular2" : m.match === "titular1" ? "titular1" : null,
            }))
          : [
              {
                key: "aggregate",
                file_name: "Dados extraídos (agregado)",
                titular1_name: aggregate?.titular1_name || "Titular 1",
                titular2_name: aggregate?.titular2_name || "Titular 2",
                choice: null,
              },
            ];
      applySharedExtractedFields(extractedData);
      setTitularChoiceDialog({
        open: true,
        items,
        pendingPayload: {
          extractedData,
          fieldConfidence,
          conflicts,
          documentsProcessed,
          suggestions,
        },
      });
      toast.info("Há documentos ambíguos — indique se são do titular 1 ou 2.");
      return;
    }

    const target = aggregate?.match === "titular2" ? "titular2" : "titular1";
    await commitAIExtractedData(
      { extractedData, fieldConfidence, conflicts, documentsProcessed, suggestions },
      target
    );
  };

  const confirmTitularChoices = async () => {
    const { items, pendingPayload } = titularChoiceDialog;
    if (!pendingPayload) {
      setTitularChoiceDialog({ open: false, items: [], pendingPayload: null });
      return;
    }
    const choices = items.map((i) => i.choice).filter((c) => c && c !== "ignore");
    const t2 = choices.filter((c) => c === "titular2").length;
    const t1 = choices.filter((c) => c === "titular1").length;
    let target = "titular1";
    if (choices.length === 0) target = "ignore";
    else if (t2 > t1) target = "titular2";
    else target = "titular1";

    setTitularChoiceDialog({ open: false, items: [], pendingPayload: null });
    if (target === "ignore") {
      toast.info("Dados de identidade ignorados. Campos do imóvel (se houver) já foram aplicados.");
      return;
    }
    await commitAIExtractedData(pendingPayload, target);
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

    // Épico 9 — a decisão tem de ficar registada nos dados que a
    // confirmação vai gravar. Sem isto, escolher "fica o valor existente"
    // limpava o conflito do ecrã e o `Confirmar` escrevia o valor da IA na
    // mesma: a interface dizia uma coisa e a ficha ficava com outra.
    setRevisaoPendente((anterior) =>
      aplicarDecisaoNaRevisao(anterior, field, chosenValue),
    );

    toast.success(`Campo "${field}" actualizado`);
  };

  // PACOTE 12 (Eixo 1) — AbortController: cancela o pedido do estado RGPD
  // quando o id muda ou o componente desmonta (cleanup), para que respostas
  // obsoletas nunca cheguem ao setState.
  useEffect(() => {
    const controller = new AbortController();
    fetchRgpdStatus(controller.signal);
    return () => controller.abort();
  }, [id]);

  // Side panels: consume TanStack query directly (no local copy)

  // Loading / error from live process query
  useEffect(() => {
    if (processBundle.isLoading) {
      setLoading(true);
      return;
    }
    if (processBundle.isError) {
      const statusCode = processBundle.error?.response?.status;
      if (statusCode === 404) {
        setNotFound(true);
      } else if (statusCode === 403) {
        setAccessDenied(true);
        toast.error("Não tem permissão para aceder a este processo");
      } else if (statusCode) {
        toast.error("Erro ao carregar dados do processo");
        navigate(-1);
      }
      setLoading(false);
    }
  }, [processBundle.isLoading, processBundle.isError, processBundle.error, navigate]);

  // Hydrate editable form state from query data (skip while a card is being edited)
  useEffect(() => {
    if (editingCardId) {
      wasEditingRef.current = true;
      return;
    }
    if (wasEditingRef.current) {
      wasEditingRef.current = false;
      lastHydratedAtRef.current = 0; // force re-apply server VM after cancel/exit edit
    }

    const processData = processBundle.process;
    if (!processData) return;

    const updatedAt = processBundle.processQuery?.dataUpdatedAt
      || processBundle.clientQuery?.dataUpdatedAt
      || 0;
    // Guard against re-entry: only hydrate when TanStack reports a new data timestamp
    if (!updatedAt || updatedAt === lastHydratedAtRef.current) return;

    lastHydratedAtRef.current = updatedAt;
    const vm = deriveProcessDetailsViewModel(processData, processBundle.client);
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
    setLoading(false);
    setNotFound(false);
    setAccessDenied(false);
  }, [
    processBundle.process,
    processBundle.client,
    processBundle.processQuery?.dataUpdatedAt,
    processBundle.clientQuery?.dataUpdatedAt,
    editingCardId,
  ]);

  // Auto-save quando o status muda (deps mínimas — evitar loop com `process`/`loading`)
  useEffect(() => {
    if (loading || !process || !status || status === process.status) {
      return;
    }

    const canChangeStatus = ["consultor", "intermediario", "admin", "ceo", "diretor", "administrativo"].includes(user?.role?.toLowerCase());
    if (!canChangeStatus) {
      return;
    }

    const previousStatus = process.status;
    const timeoutId = setTimeout(() => {
      const saveStatusOnly = async () => {
        try {
          await processMutations.updateProcess.mutateAsync({ status });
          toast.success("Estado atualizado");
        } catch (error) {
          console.error("Erro ao atualizar estado:", error);
          toast.error("Erro ao atualizar estado");
          setStatus(previousStatus);
        }
      };
      saveStatusOnly();
    }, 500);

    return () => clearTimeout(timeoutId);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: only react to status changes
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

  const fetchData = useCallback(async () => {
    const cid = clientId || processBundle.process?.client_id;
    await invalidateProcessDetailsQueries(queryClient, id, { clientId: cid });
    await processBundle.refetchAll();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- refetchAll is stable enough per id
  }, [queryClient, id, clientId, processBundle.process?.client_id, processBundle.refetchAll]);

  // Reset hydration when navigating to another process
  //
  // BUGFIX (Épico 8): este efeito é declarado DEPOIS do de hidratação, pelo
  // que na montagem corriam os dois pela mesma ordem — hidratar e logo a
  // seguir desfazer. Na primeira visita isso passava despercebido: a query
  // ainda não tinha resolvido, `dataUpdatedAt` mudava a seguir e a
  // hidratação voltava a correr. Numa REVISITA dentro do `staleTime` (60 s)
  // o TanStack serve a cache logo no primeiro render, `dataUpdatedAt` nunca
  // muda, a hidratação não volta a correr — e a página ficava presa no
  // esqueleto de carregamento, para sempre.
  //
  // Na montagem não há nada a limpar: o estado acabou de nascer. Só uma
  // MUDANÇA de processo justifica o reset, que é o que o nome do efeito
  // sempre disse.
  useEffect(() => {
    if (processoAnteriorRef.current === id) return;
    const eraMontagem = processoAnteriorRef.current === null;
    processoAnteriorRef.current = id;
    if (eraMontagem) return;

    lastHydratedAtRef.current = 0;
    setLoading(true);
    setProcess(null);
    setClientData(null);
    setClientId(null);
    setNotFound(false);
    setAccessDenied(false);
    // Não remover a cache no unmount — gcTime (5 min) trata da GC.
    // removeQueries aqui anulava staleTime e forçava refetch em cada visita.
  }, [id]);

  // Legacy OneDrive functions - kept for compatibility but use S3FileManager instead


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
      if (process.observations !== undefined) processUpdateData.observations = process.observations;
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

      // 4. DISPARAR OS DOIS REQUESTS EM SIMULTÂNEO (mutations TanStack)
      // Sanitize explícito aqui + de novo no hook (defense in depth contra
      // documents/onedrive_links/arrays vazios a esmagarem o backend).
      const safeProcessPayload = sanitizeProcessUpdatePayload(processUpdateData);
      if (emailVal) safeProcessPayload.client_email = emailVal;
      if (phoneVal) safeProcessPayload.client_phone = phoneVal;

      const promises = [
        processMutations.updateProcess.mutateAsync(safeProcessPayload),
      ];

      if (process.client_id && !hasRole(user, "indexacao")) {
        promises.push(
          processMutations.updateClient.mutateAsync({
            clientId: process.client_id,
            data: clientUpdateData,
          })
        );
      }

      await Promise.all(promises);

      toast.success("Processo e Cliente atualizados com sucesso!");
      setEditingCardId(null); // Exit editing mode after save
      await fetchData();
    } catch (error) {
      console.error("Error saving:", error);
      toast.error(error.message || "Erro ao guardar alterações");
    } finally {
      setSaving(false);
    }
  };

  // Guardar apenas os dados da Organização do Processo (notas, prioridade, etiquetas)
  const [, setSavingOrg] = useState(false);
  // `overrides` permite passar o valor recém-alterado explicitamente em vez de
  // depender de `process` (a closure desta função fica "presa" ao valor de
  // `process` do render em que foi definida — chamar handleSaveOrganization()
  // logo após um setProcess() no mesmo handler enviaria o valor ANTIGO, já
  // que o setState ainda não tinha sido aplicado nesse render).
  const handleSaveOrganization = async (overrides = {}) => {
    if (isProcessLocked) {
      toast.error("Não é possível editar um processo eliminado, desistido ou concluído.");
      return;
    }
    // Admin/CEO podem editar processos concluídos — isProcessLocked já exclui estes roles
    setSavingOrg(true);
    try {
      const orgData = {
        notes: process?.notes || "",
        observations: process?.observations ?? process?.notes ?? "",
        prioridade: process?.prioridade || "media",
        labels: Array.isArray(process?.labels) ? process.labels : [],
        ...overrides,
      };
      // labels:[] é intencional (limpar etiquetas) — allowEmptyArrays
      await processMutations.updateProcess.mutateAsync({
        payload: orgData,
        allowEmptyArrays: ["labels"],
      });
      toast.success("Organização do processo guardada com sucesso!");
      await fetchData();
    } catch (error) {
      console.error("Error saving organization:", error);
      const detail = error.response?.data?.detail;
      const errorMessage = typeof detail === 'string' ? detail : "Erro ao guardar organização do processo";
      toast.error(errorMessage);
    } finally {
      setSavingOrg(false);
    }
  };

  const handleAddObservationNote = async (text) => {
    if (isProcessLocked) {
      toast.error("Não é possível editar um processo eliminado, desistido ou concluído.");
      throw new Error("process_locked");
    }
    setSavingObservations(true);
    try {
      const res = await addProcessObservationNote(id, text);
      const updated = res?.data;
      if (updated) {
        setProcess((prev) => (prev ? { ...prev, ...updated } : updated));
      }
      toast.success("Nota adicionada");
      await fetchData();
    } catch (error) {
      const detail = error.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "Erro ao adicionar nota");
      throw error;
    } finally {
      setSavingObservations(false);
    }
  };

  // ── Etiquetas (ponto 15) ───────────────────────────────────────────
  // O catálogo alimenta as sugestões do editor. Falhar a lê-lo não é
  // motivo para bloquear nada: sem sugestões continua a poder escrever-se
  // a etiqueta à mão.
  const [sugestoesDeEtiquetas, setSugestoesDeEtiquetas] = useState([]);
  const [aGravarEtiquetas, setAGravarEtiquetas] = useState(false);

  useEffect(() => {
    let cancelado = false;
    getProcessLabels()
      .then((res) => {
        if (!cancelado) setSugestoesDeEtiquetas(res?.data?.labels || []);
      })
      .catch(() => {
        if (!cancelado) setSugestoesDeEtiquetas([]);
      });
    return () => {
      cancelado = true;
    };
  }, []);

  const handleGuardarEtiquetas = async (etiquetas) => {
    setAGravarEtiquetas(true);
    try {
      // `handleSaveOrganization` já trata do `allowEmptyArrays: ["labels"]`
      // — limpar todas as etiquetas tem de chegar ao servidor como [].
      setProcess((anterior) => (anterior ? { ...anterior, labels: etiquetas } : anterior));
      await handleSaveOrganization({ labels: etiquetas });
    } finally {
      setAGravarEtiquetas(false);
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
      await processMutations.addActivity.mutateAsync({ comment: newComment });
      setNewComment("");
      toast.success("Comentário adicionado");
    } catch {
      toast.error("Erro ao adicionar comentário");
    } finally {
      setSendingComment(false);
    }
  };

  // ── Nota de voz (Épico 7) ────────────────────────────────────────
  // O upload devolve de imediato; o trabalho pesado (transcrição, IA,
  // escrita na timeline, criação de tarefas) corre em background no
  // servidor e volta pelos eventos `task_*` do Épico 4.
  const handleEnviarNotaDeVoz = useCallback(
    async (ficheiro) => {
      setAEnviarNotaDeVoz(true);
      try {
        const { data } = await uploadVoiceNote(id, ficheiro);
        setNotaDeVozEmCurso(data?.task_id || null);
        setVoiceNoteOpen(false);
        toast.info("Nota enviada. A transcrever e a analisar...");
      } catch (erro) {
        toast.error(
          erro?.response?.data?.detail || "Não foi possível enviar a nota de voz.",
        );
      } finally {
        setAEnviarNotaDeVoz(false);
      }
    },
    [id],
  );

  // A nota só aparece no ecrã sem refresh porque este handler invalida as
  // queries do processo quando o evento terminal chega. Sem o filtro por
  // tipo e processo, QUALQUER tarefa de fundo do CRM (importações, análises
  // em massa) recarregaria esta página.
  useTaskEvents(
    useCallback(
      (payload, tipoDeEvento) => {
        if (!eNotaDeVozDoProcesso(payload, id)) return;

        if (tipoDeEvento === "task_completed") {
          setNotaDeVozEmCurso(null);
          fetchData();
          toast.success(mensagemDeConclusao(payload?.result));
        } else if (tipoDeEvento === "task_failed") {
          setNotaDeVozEmCurso(null);
          toast.error(payload?.error || "A nota de voz não pôde ser processada.");
        }
      },
      [id, fetchData],
    ),
  );

  // O diálogo de revisão não anuncia nada: diz que o utilizador confirmou
  // e o contentor é que sabe que isso implica fechar e avisar para guardar.
  const handleConfirmAIReview = useCallback(async () => {
    setShowAIReviewDialog(false);

    // Caminho do Épico 9: nada foi aplicado ainda. A confirmação do
    // consultor é o que autoriza escrever no formulário e na ficha.
    if (revisaoPendente) {
      const { extractedData, targetTitular, documentsProcessed } =
        revisaoPendente;
      setRevisaoPendente(null);
      applySharedExtractedFields(extractedData);
      applyPersonalAndFinancialToTitular(extractedData, targetTitular);
      await persistAISuggestions(
        extractedData,
        documentsProcessed || 1,
        targetTitular,
      );
      setActiveTab("personal");
      return;
    }

    // Caminho da análise em lote: os campos já tinham sido pré-preenchidos
    // antes de o diálogo abrir; só falta avisar que é preciso guardar.
    toast.success("Campos actualizados. Não esqueça de guardar!");
  }, [revisaoPendente]);

  // Fechar o diálogo sem confirmar DESCARTA a extracção pendente. Guardá-la
  // seria pior do que inútil: a próxima confirmação escreveria dados de um
  // documento que o consultor já tinha rejeitado.
  const handleAIReviewOpenChange = useCallback((aberto) => {
    setShowAIReviewDialog(aberto);
    if (!aberto) setRevisaoPendente(null);
  }, []);

  // ── Escolha de titular para documentos ambíguos (Épico 8) ────────
  // O diálogo é de apresentação: diz qual foi a escolha, o contentor é que
  // sabe que isso significa reconstruir a lista de itens.
  const handleTitularChoice = useCallback((indice, escolha) => {
    setTitularChoiceDialog((anterior) => ({
      ...anterior,
      items: anterior.items.map((item, i) =>
        i === indice ? { ...item, choice: escolha } : item,
      ),
    }));
  }, []);

  const handleTitularDialogOpenChange = useCallback((aberto) => {
    if (!aberto) {
      setTitularChoiceDialog({ open: false, items: [], pendingPayload: null });
    }
  }, []);

  const handleDeleteComment = async (activityId) => {
    try {
      await processMutations.deleteActivity.mutateAsync(activityId);
      toast.success("Comentário eliminado");
    } catch {
      toast.error("Erro ao eliminar comentário");
    }
  };

  const handleCreateDeadline = async () => {
    if (!deadlineForm.title || !selectedDate) {
      toast.error("Preencha o título e a data");
      return;
    }

    try {
      await processMutations.deadlines.create.mutateAsync({
        title: deadlineForm.title,
        description: deadlineForm.description,
        due_date: selectedDate && isValid(selectedDate) ? format(selectedDate, "yyyy-MM-dd") : null,
        priority: deadlineForm.priority,
        // PACOTE DH — Agenda evolution: novos campos persistidos no backend
        type: deadlineForm.type || "deadline",
        reminder_time: deadlineForm.reminder_time ?? null,
        visible_to_client: !!deadlineForm.visible_to_client,
      });
      toast.success("Prazo criado com sucesso!");
      setIsDeadlineDialogOpen(false);
      // PACOTE DH — reset inclui os novos campos do formulário Agenda
      setDeadlineForm({
        title: "",
        description: "",
        due_date: "",
        priority: "medium",
        type: "deadline",
        reminder_time: null,
        visible_to_client: false,
      });
      setSelectedDate(null);
    } catch {
      toast.error("Erro ao criar prazo");
    }
  };

  const handleToggleDeadline = async (deadline) => {
    try {
      await processMutations.deadlines.update.mutateAsync({
        deadlineId: deadline.id,
        data: { completed: !deadline.completed },
      });
    } catch {
      toast.error("Erro ao atualizar prazo");
    }
  };

  const handleDeleteDeadline = async (deadlineId) => {
    if (!confirm("Tem certeza que deseja eliminar este prazo?")) return;

    try {
      await processMutations.deadlines.remove.mutateAsync(deadlineId);
      toast.success("Prazo eliminado!");
    } catch {
      toast.error("Erro ao eliminar prazo");
    }
  };

  const getStatusInfo = (statusName) => {
    const statusInfo = workflowStatuses.find(s => s.name === statusName);
    return statusInfo || { label: formatStatusLabel(statusName), color: "blue" };
  };

  // ── Derived: opções do Select 100% dinâmicas + fallback do status ──
  // A dropdown de estado nunca inventa fases em código (PACOTE 11 —
  // Eixo 1, Strict No-Hardcoding). buildStatusOptions:
  //   1) usa workflowStatuses (API /admin/workflow-statuses, colecção
  //      `workflow_statuses` configurável pelo admin) como base ÚNICA;
  //   2) se o `status` actual (process.status) não estiver na lista
  //      dinâmica (API falhou / fase removida), injecta-o como opção
  //      extra com label formatada (_isFallback=true) — a dropdown nunca
  //      fica em branco, mas também nunca mostra fases cravadas.
  const safeStatusOptions = useMemo(
    () => buildStatusOptions(workflowStatuses, status),
    [workflowStatuses, status]
  );

  // PACOTE FQ-2 — lookup id → utilizador para resolver nomes de atribuição
  // quando só existem IDs (assigned_consultor_ids / assigned_mediador_ids)
  // sem os arrays de nomes correspondentes ainda carregados.
  const appUsersById = useMemo(() => {
    const map = new Map();
    appUsers.forEach((u) => {
      if (u?.id) map.set(u.id, u);
    });
    return map;
  }, [appUsers]);

  // Normalizar role para comparação case-insensitive
  const userRole = user?.role?.toLowerCase() || "";
  const roleLabels = ROLE_LABELS; // Rótulos legíveis para exibição no banner retroativo
  const userPermissions = user?.permissions || {};
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
  
  // PACOTE 9 — Toggle "Indexado" no header: visível apenas para perfis de
  // gestão/indexação (mesma regra do backend assert_mark_indexed_permission:
  // indexacao/admin/ceo). Usa o perfil ACTIVO (effectiveRole) e, em fallback,
  // hasAnyRole — o padrão já usado no Kanban para multi-perfis.
  const INDEX_TOGGLE_ROLES = ["indexacao", "admin", "ceo"];
  const canMarkIndexed =
    INDEX_TOGGLE_ROLES.includes((effectiveRole || userRole || "").toLowerCase()) ||
    hasAnyRole(user, INDEX_TOGGLE_ROLES);
  const [indexToggleBusy, setIndexToggleBusy] = useState(false);
  const handleToggleIndexed = async (checked) => {
    if (!id || indexToggleBusy) return;
    const previous = process?.is_indexed;
    // Optimistic update + rollback em erro (o bundle TanStack refresca depois)
    setProcess((prev) => (prev ? { ...prev, is_indexed: checked } : prev));
    setIndexToggleBusy(true);
    try {
      const res = await setProcessIndexed(id, checked);
      const nextValue =
        res?.data && typeof res.data.is_indexed === "boolean"
          ? res.data.is_indexed
          : checked;
      setProcess((prev) => (prev ? { ...prev, is_indexed: nextValue } : prev));
      toast.success(
        nextValue
          ? "Indexação concluída! A equipa foi notificada."
          : "Indexação revertida — o processo voltou a 'não indexado'."
      );
      // ÉPICO Motor de Simulação Financeira (Eixo 4) — quando a validação
      // da indexação dispara o cálculo automático dos cenários de crédito,
      // o backend devolve `financial_engine.triggered`. Toast informativo
      // secundário para o utilizador saber que há trabalho em background
      // (o progresso até ao PDF é acompanhado pelo painel de Tarefas).
      notifyFinancialEngine(res?.data, toast.info);
      await fetchData();
    } catch (error) {
      setProcess((prev) => (prev ? { ...prev, is_indexed: previous } : prev));
      toast.error(
        extractErrorMessage(
          error?.response?.data?.detail,
          "Erro ao actualizar o estado de indexação"
        )
      );
    } finally {
      setIndexToggleBusy(false);
    }
  };
  
  // Permissões específicas por action
  const canManageTasks = userActions.length > 0 
    ? userActions.includes("manage_tasks") 
    : ["admin", "ceo", "consultor", "intermediario", "diretor", "administrativo"].includes(userRole);
  // Modo de visualização (read-only) quando não tem edit_process
  // OU quando o processo está em status terminal (eliminados, desistências, concluídos)
  // EXCEPÇÃO: admin e CEO NUNCA sofrem lock — podem editar processos concluídos retroativamente
  const BLOCKED_STATUSES = ["eliminados", "desistencias", "concluidos"];
  const isProcessLocked = process && BLOCKED_STATUSES.includes(process.status) && !['admin', 'ceo'].includes(userRole);

  // PACOTE 11 (Eixo 4) — Proteção Soft-Delete: quando o processo está
  // eliminado (is_deleted OU status 'eliminado'), TODOS os inputs e botões
  // de edição ficam desactivados (read-only forçado, sem excepção de role)
  // para impedir falsas mensagens de sucesso. O banner de restauro (topo
  // da página) é a única acção disponível.
  const isDeletedProcess = !!(
    process?.is_deleted ||
    process?.deleted ||
    process?.status === "eliminado" ||
    process?.status === "eliminados"
  );
  // PACOTE 12 (Eixo 1) — mesmo guard para o CLIENTE do processo (dados do
  // bundle GET /clients/{id}): quando o cliente está eliminado, a edição
  // fica bloqueada mesmo com o processo activo — os PUTs de cliente não
  // podem gravar num registo inactivo. Sem banner adicional: o restauro do
  // cliente faz-se na sua ficha (ClientDetailPage).
  const isDeletedClient = !!(
    clientData?.is_deleted ||
    clientData?.deleted ||
    clientData?.status === "eliminado" ||
    clientData?.status === "eliminados"
  );
  const isViewMode =
    (!hasEditProcess && !(userActions.includes("view_financials") && userRole === "indexacao")) ||
    isProcessLocked ||
    isDeletedProcess ||
    isDeletedClient;

  // Processos Inativos (Read-Only): estados finais onde as ações principais
  // (RGPD, CPCV, Enviar Balcões, Portal do Cliente, Eliminar) devem ficar
  // visíveis mas desabilitadas — o workflow já terminou, pelo que estas ações
  // deixam de fazer sentido independentemente do role de quem vê o ecrã.
  // Inclui "eliminado" (singular, valor real gravado pelo soft-delete do
  // processo — ver backend/services/process_delete.py) e as suas variantes
  // legacy/plural para cobrir dados antigos.
  const INACTIVE_PROCESS_STATUSES = [
    "concluido", "concluidos",
    "desistencias", "desistido",
    "cancelado",
    "eliminado", "eliminados",
    "perdido", "arquivo",
  ];
  const isInactiveProcess = !!(
    (process && (INACTIVE_PROCESS_STATUSES.includes(process.status) || process.is_deleted)) ||
    isDeletedClient
  );

  // PACOTE 11 (Eixo 4) — Restauro Rápido: reactiva o processo eliminado
  // via POST /processes/{id}/restore e refresca os dados da página.
  const [restoringProcess, setRestoringProcess] = useState(false);
  const handleRestoreProcess = async () => {
    if (!id || restoringProcess) return;
    setRestoringProcess(true);
    try {
      await restoreProcess(id);
      toast.success("Processo restaurado com sucesso");
      await fetchData();
    } catch (err) {
      toast.error(
        extractErrorMessage(err?.response?.data?.detail, "Não foi possível restaurar o processo")
      );
    } finally {
      setRestoringProcess(false);
    }
  };

  // PACOTE 5 (RGPD por titular) — True quando o processo tem 2º titular
  // identificado (cliente ligado via second_client_id ou titular2_data com
  // nome). Habilita o download do PDF do 2º titular no menu RGPD; o backend
  // dispara também o pedido + email independentes dele na solicitação.
  const hasSecondTitular = !!(
    process?.second_client_id ||
    process?.second_client_data?.nome ||
    titular2Data?.nome ||
    titular2Data?.name
  );

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
      // PACOTE DH — novos casos: cartões que antes eram sempre expandidos
      // (mesmo vazios). Agora colapsam automaticamente quando não têm dados.
      case 'financial_situacao':
        return !financialData?.efetivo && !financialData?.precisa_vender_casa &&
               !financialData?.fiador && !financialData?.creditos_existentes &&
               !financialData?.prestacao_creditos_mensal &&
               !financialData?.acesso_portal_financas && !financialData?.chave_movel_digital;
      case 'financial_profissional':
        return !financialData?.employment_type && !financialData?.trabalha_estrangeiro &&
               !financialData?.employment_duration && !financialData?.employer_name &&
               !financialData?.employer_nif && !financialData?.categoria_profissional &&
               !financialData?.subsidiario_alimentacao && !financialData?.data_referencia;
      case 'realestate_caracteristicas':
        return !realEstateData?.tipo_imovel && !realEstateData?.num_quartos &&
               !realEstateData?.tipologia && !realEstateData?.valor_imovel &&
               !realEstateData?.valor_patrimonial && !realEstateData?.certificado_energetico &&
               !realEstateData?.area_bruta && !realEstateData?.area_util &&
               !realEstateData?.fracao && !realEstateData?.artigo_matricial;
      case 'realestate_localizacao':
        return !realEstateData?.localizacao && !realEstateData?.area_pretendida &&
               !realEstateData?.valor_maximo_imovel && !realEstateData?.finalidade &&
               !realEstateData?.codigo_postal && !realEstateData?.localidade &&
               !realEstateData?.freguesia && !realEstateData?.concelho &&
               !(Array.isArray(realEstateData?.caracteristicas) && realEstateData.caracteristicas.length > 0);
      case 'realestate_cpcv':
        return !financialData?.valor_entrada && !realEstateData?.data_sinal &&
               !realEstateData?.data_escritura && !realEstateData?.data_balcao;
      case 'realestate_vendedor':
        return !realEstateData?.vendedor_nome && !realEstateData?.vendedor_nif &&
               !realEstateData?.vendedor_contacto && !realEstateData?.vendedor_email;
      case 'credit_avaliacao':
        return !creditData?.valuation_value && !creditData?.valuation_date &&
               !creditData?.valuation_bank && !creditData?.valuation_notes;
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
  const headerClientName = safeString(
    clientData?.nome || process?.client_name || personalData?.nome_completo || personalData?.nome,
  );
  // PACOTE 11 (Eixo 3) — ID do cliente para o Link da ficha (header + card
  // lateral). Ordem: cliente carregado do bundle → FK do processo.
  const headerClientId = safeString(
    clientData?.id || clientData?._id || clientId || process?.client_id,
  );
  const headerPhone = safeString(
    process?.client_phone || personalData?.telefone || clientData?.contacto?.telefone,
  );
  const headerEmail = safeString(
    process?.client_email || personalData?.email || clientData?.contacto?.email,
  );
  const headerConsultor =
    safeStringArray(process.consultor_names).join(", ") ||
    safeString(process.consultor_name || process.assigned_consultor_name);

  return (
    <DashboardLayout title="Detalhes do Processo">
      <div className="space-y-6">
        {/* PACOTE 11 (Eixo 4) — Banner de processo eliminado + Restauro Rápido:
            todos os inputs/botões de edição ficam desactivados (ver
            isDeletedProcess acima) e o botão restaura via API. */}
        {isDeletedProcess && (
          <div
            className="flex flex-col sm:flex-row sm:items-center gap-3 p-3 rounded-lg border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/30"
            role="alert"
          >
            <div className="flex items-center gap-2.5 flex-1 min-w-0">
              <Trash2 className="h-4 w-4 text-red-600 dark:text-red-400 shrink-0" aria-hidden="true" />
              <div className="min-w-0">
                <p className="font-medium text-red-800 dark:text-red-200 text-sm">
                  Este processo encontra-se eliminado
                </p>
                <p className="text-xs text-red-700 dark:text-red-300 mt-0.5">
                  A edição está bloqueada para todos os utilizadores. Restaure o processo para
                  retomar o trabalho (documentos, tarefas e pedidos RGPD são restaurados em cascata).
                </p>
              </div>
            </div>
            <Button
              onClick={handleRestoreProcess}
              disabled={restoringProcess}
              className="gap-2 bg-red-600 hover:bg-red-700 text-white shrink-0 h-8"
              aria-label="Restaurar processo eliminado"
            >
              {restoringProcess ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RotateCcw className="h-4 w-4" />
              )}
              Restaurar
            </Button>
          </div>
        )}
        {/* Aviso de processo bloqueado ou em modo retroativo
            (oculto quando já está visível o banner de eliminado) */}
        {isProcessLocked && !isDeletedProcess && (
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

        {/* Header (Progressive Disclosure): PageHeader partilhado + StatusBadge
            junto ao título; ações principais alinhadas à direita. A gestão de
            atribuições passou para o Cartão de Atribuição (coluna direita) —
            fica junto da informação que edita, em vez de solta no cabeçalho. */}
        <div className="flex items-start gap-2">
          <Button variant="ghost" size="icon" onClick={() => navigate(-1)} aria-label="Voltar" className="mt-0.5 shrink-0">
            <ArrowLeft className="h-5 w-5" />
          </Button>
          {/* Ponto 17 — setas Anterior/Seguinte. Só aparecem quando há
              mesmo uma listagem de origem: um processo aberto por
              pesquisa global ou por link não tem vizinhos, e uma seta a
              apontar para os vizinhos de outra lista seria pior do que
              seta nenhuma. */}
          {vizinhos.disponivel && (
            <div className="mt-0.5">
              <ProcessNavigator
                anteriorId={vizinhos.anteriorId}
                seguinteId={vizinhos.seguinteId}
                posicao={vizinhos.posicao}
                total={vizinhos.total}
                aCarregar={vizinhos.aCarregar}
                onNavegar={irParaProcesso}
              />
            </div>
          )}
          <div className="flex-1 min-w-0">
            <PageHeader
              title={`Processo #${safeString(process?.process_number || "")}`}
              titleBadge={
                <StatusBadge status={process.status} workflowStatuses={safeStatusOptions} showOrder={false} />
              }
              description={
                <span className="flex items-center gap-x-3 gap-y-1 flex-wrap text-sm text-muted-foreground">
                  {/* PACOTE 11 (Eixo 3) — nome do cliente clicável: navega
                      para a ficha do cliente (/cliente/:id). */}
                  {headerClientName ? (
                    headerClientId ? (
                      <Link
                        to={`/cliente/${headerClientId}`}
                        className="font-medium hover:text-foreground hover:underline underline-offset-2 transition-colors"
                        title="Abrir ficha do cliente"
                      >
                        {headerClientName}
                      </Link>
                    ) : (
                      <span>{headerClientName}</span>
                    )
                  ) : null}
                  {headerPhone ? (
                    <a href={`tel:${headerPhone}`} className="inline-flex items-center gap-1 hover:text-foreground">
                      <Phone className="h-3 w-3" aria-hidden="true" />
                      {headerPhone}
                    </a>
                  ) : null}
                  {headerEmail ? (
                    <a href={`mailto:${headerEmail}`} className="inline-flex items-center gap-1 hover:text-foreground truncate max-w-[220px]">
                      <Mail className="h-3 w-3 shrink-0" aria-hidden="true" />
                      {headerEmail}
                    </a>
                  ) : null}
                  {headerConsultor ? <span>Consultor: {headerConsultor}</span> : null}
                  {/* Ponto 15 — as etiquetas deixam de ser só crachás.
                      O PACOTE DD removeu o cartão de Etiquetas e prometeu
                      um Dialog no botão "+" que nunca foi construído: o
                      campo ficou só acessível pela API. É este. */}
                  <ProcessLabelsEditor
                    labels={process?.labels}
                    sugestoes={sugestoesDeEtiquetas}
                    disabled={isViewMode || isProcessLocked}
                    saving={aGravarEtiquetas}
                    onChange={handleGuardarEtiquetas}
                  />
                </span>
              }
              actions={
                <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
            {/* Dialog RGPD */}
            <RGPDRequestDialog
              open={rgpdDialogOpen}
              onOpenChange={setRgpdDialogOpen}
              clientName={process?.client_name}
              clientEmail={process?.client_email}
              message={rgpdCustomMessage}
              onMessageChange={setRgpdCustomMessage}
              onConfirm={handleConfirmRgpd}
              sending={rgpdSending}
            />

            {/* PACOTE DE — RGPD DropdownMenu: Solicitar + Download PDF (Assinatura Manual) */}
            {userRole !== "indexacao" && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
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
                    disabled={rgpdSending || rgpdLoading || isInactiveProcess}
                    title="RGPD"
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
                    <ChevronDown className="h-3.5 w-3.5 sm:ml-1" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="w-60">
                  <DropdownMenuLabel>RGPD</DropdownMenuLabel>
                  <DropdownMenuItem
                    className="gap-2 cursor-pointer"
                    onClick={handleRequestRgpd}
                  >
                    <Mail className="h-4 w-4" />
                    Solicitar Consentimento
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    className="gap-2 cursor-pointer"
                    onClick={() => handleDownloadRgpdPdf("first")}
                  >
                    <FileDown className="h-4 w-4" />
                    Descarregar PDF (Assinatura Manual)
                  </DropdownMenuItem>
                  {/* PACOTE 5 — PDF do 2º titular: documento independente,
                      preenchido exclusivamente com os dados dessa pessoa. */}
                  {hasSecondTitular && (
                    <DropdownMenuItem
                      className="gap-2 cursor-pointer"
                      onClick={() => handleDownloadRgpdPdf("second")}
                    >
                      <FileDown className="h-4 w-4" />
                      Descarregar PDF — 2º Titular
                    </DropdownMenuItem>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            )}
            
            {/* Botão CPCV */}
            {userRole !== "indexacao" && (
              <Button
                variant="outline"
                size="sm"
                className="text-indigo-600 border-indigo-200 hover:bg-indigo-50 h-8 px-2 sm:px-3"
                onClick={() => setShowCPCVModal(true)}
                disabled={isInactiveProcess}
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
                disabled={isInactiveProcess}
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
                      disabled={isInactiveProcess}
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
              </>
            )}
            
            {/* PACOTE 9 — Toggle "Indexado": liga/desliga is_indexed directamente
                via POST /processes/{id}/set-indexed. Visível apenas para perfis
                de gestão/indexação (canMarkIndexed). ON delega no fluxo canónico
                do mark-indexed (notificações + salto de workflow); OFF reverte o
                flag sem mexer na fase (histórico INDEXACAO_REVERTIDA no backend). */}
            {canMarkIndexed && (
              <div
                className="flex items-center gap-1.5 h-8 px-2 sm:px-3 rounded-md border bg-background"
                title={
                  process?.is_indexed
                    ? "Processo indexado — clique para reverter (voltar a 'não indexado')"
                    : "Marcar este processo como indexado (conclui a fase de indexação)"
                }
                data-testid="indexed-toggle"
              >
                <Switch
                  id="process-indexed-toggle"
                  checked={!!process?.is_indexed}
                  onCheckedChange={handleToggleIndexed}
                  disabled={indexToggleBusy || !process}
                  aria-label="Indexado"
                />
                <Label
                  htmlFor="process-indexed-toggle"
                  className="text-xs sm:text-sm font-medium cursor-pointer select-none"
                >
                  {indexToggleBusy ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin inline" />
                  ) : (
                    "Indexado"
                  )}
                </Label>
              </div>
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
                disabled={isInactiveProcess}
                data-testid="delete-process-btn"
                title={isInactiveProcess ? "Processo em estado terminal — ação desativada" : "Eliminar este processo (o cliente não é eliminado)"}
              >
                <Trash2 className="h-3.5 w-3.5 sm:mr-1" />
                <span className="hidden sm:inline">Eliminar</span>
              </Button>
            )}
                </div>
              }
            />
          </div>
        </div>

        {/* Alertas do Processo — sempre visível, independente do separador ativo */}
        <ProcessAlerts processId={id} className="mb-2" />

        {/* ═══════ Layout Progressive Disclosure ═══════
            Esquerda (2/3): Tabs Resumo / Documentos / Histórico — esconde a
            complexidade em separadores por tarefa.
            Direita (1/3): Contexto fixo — Cliente + Atribuição sempre visíveis,
            independentemente do separador ativo à esquerda. */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* ── Coluna Esquerda: Ação & Exploração (2/3) ── */}
          <div className="lg:col-span-2 space-y-6">
            <Tabs value={mainTab} onValueChange={(v) => {
              setMainTab(v);
              writeTabQuery(v, activeTab);
            }}>
              <TabsList className="grid w-full grid-cols-3">
                <TabsTrigger value="resumo" className="gap-1.5">
                  <ClipboardList className="h-4 w-4" />
                  Resumo
                </TabsTrigger>
                <TabsTrigger value="documentos" className="gap-1.5">
                  <FolderOpen className="h-4 w-4" />
                  Documentos
                </TabsTrigger>
                <TabsTrigger value="historico" className="gap-1.5">
                  <History className="h-4 w-4" />
                  Histórico
                </TabsTrigger>
              </TabsList>

              {/* ── Separador: Resumo — formulários principais + dados críticos ── */}
              <TabsContent value="resumo" className="space-y-6 mt-4">
                {/* Banner de modo de visualização para roles sem edit_process (exceto indexacao que edita financeiros) */}
                {isViewMode && !isProcessLocked && (
                  <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-3 flex items-center gap-3">
                    <AlertCircle className="h-5 w-5 text-amber-600 shrink-0" />
                    <p className="text-sm text-amber-800 dark:text-amber-200">
                      <strong>Modo de visualização.</strong> Não tem permissões para editar os dados base do processo. Pode gerir documentos, tarefas, chat e atribuição de utilizadores.
                    </p>
                  </div>
                )}

                {/* PACOTE DO.1 / DP — Observações + Timeline compacta no Resumo */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
                  <ProcessObservationsCard
                    process={process}
                    onAdd={handleAddObservationNote}
                    disabled={isViewMode || isProcessLocked}
                    saving={savingObservations}
                  />
                  <ProcessSummaryTimeline
                    process={process}
                    history={history}
                    onOpenFullHistory={() => setMainTab("historico")}
                  />
                </div>

                {/* PACOTE DD — cartão de Etiquetas removido (movido para PageHeader) */}

                {/* Resolver conflitos de dados IA */}
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

                {/* Formulários principais do processo, organizados por domínio */}
                <Card className="border-border">
                  <CardHeader>
                    <CardTitle className="text-lg">Dados do Processo</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <Tabs value={activeTab} onValueChange={(v) => {
                      setEditingCardId(null);
                      setActiveTab(v);
                      writeTabQuery(mainTab, v);
                    }}>
                      <ProcessDomainTabsList unreadMessagesCount={portal.unreadCount} />

                  {/* ── FASE 3: Tab Dados do Cliente ── */}
                  <TabsContent value="personal" className="mt-4">
                    <PersonalInfoTab
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
                    <FinancialTab
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
                    <RealEstateTab
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
                    <CreditTab
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

                  {/* Prazos Tab — calendário e lista de prazos críticos do processo */}
                  <TabsContent value="prazos" className="mt-4">
                    <DeadlinesTab
                      canManageDeadlines={canManageDeadlines}
                      isDeadlineDialogOpen={isDeadlineDialogOpen}
                      setIsDeadlineDialogOpen={setIsDeadlineDialogOpen}
                      deadlineForm={deadlineForm}
                      setDeadlineForm={setDeadlineForm}
                      selectedDate={selectedDate}
                      setSelectedDate={setSelectedDate}
                      handleCreateDeadline={handleCreateDeadline}
                      deadlineDates={deadlineDates}
                      deadlines={deadlines}
                      handleToggleDeadline={handleToggleDeadline}
                      handleDeleteDeadline={handleDeleteDeadline}
                    />
                  </TabsContent>

                  {/* Emails Tab - Histórico de Emails do Processo */}
                  <TabsContent value="emails" className="mt-4">
                    <EmailsTab id={id} savedProcessRef={savedProcessRef} process={process} token={token} />
                  </TabsContent>

                  {/* Visitas / Imóveis Tab */}
                  <TabsContent value="visitas" className="mt-4">
                    <VisitasTab processId={id} />
                  </TabsContent>

                  {/* Mensagens do Portal Tab */}
                  <TabsContent value="mensagens" className="mt-4">
                    <PortalMessagesTab
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
              </TabsContent>

              {/* ── Separador: Documentos — gestor de ficheiros S3 do cliente ── */}
              <TabsContent value="documentos" className="mt-4">
                <DocumentsTab
                  hasAnyRole={hasAnyRole}
                  user={user}
                  aiSummary={aiSummary}
                  aiAnalysisLoading={aiAnalysisLoading}
                  aiAnalysisDate={aiAnalysisDate}
                  handleAiAnalysis={handleAiAnalysis}
                  renderAiSummary={renderAiSummary}
                  documentsRefreshKey={documentsRefreshKey}
                  id={id}
                  process={process}
                  handleAIDataExtractedFromDocs={handleAIDataExtractedFromDocs}
                  handleDocumentDataExtracted={handleDocumentDataExtracted}
                  setDocumentsRefreshKey={setDocumentsRefreshKey}
                />
              </TabsContent>

              {/* ── Separador: Histórico — changelog, notas e cronologia de atividades ── */}
              <TabsContent value="historico" className="mt-4">
                <HistoryTab
                  processId={id}
                  process={process}
                  history={history}
                  workflowStatuses={workflowStatuses}
                  activities={activities}
                  newComment={newComment}
                  setNewComment={setNewComment}
                  sendingComment={sendingComment}
                  handleSendComment={handleSendComment}
                  handleDeleteComment={handleDeleteComment}
                  user={user}
                  isProcessLocked={isProcessLocked}
                  voiceNoteOpen={voiceNoteOpen}
                  onVoiceNoteOpenChange={setVoiceNoteOpen}
                  onEnviarNotaDeVoz={handleEnviarNotaDeVoz}
                  aEnviarNotaDeVoz={aEnviarNotaDeVoz}
                  aProcessarNotaDeVoz={Boolean(notaDeVozEmCurso)}
                />
              </TabsContent>
            </Tabs>
          </div>

          {/* ── Coluna Direita: Contexto Fixo (1/3) — Cliente + Atribuição sempre visíveis ── */}
          <div className="space-y-4">
            {/* PACOTE 11 (Eixo 3) — clientId para o nome do titular ser
                clicável (navega para a ficha do cliente). */}
            <ClientContextCard
              process={process}
              personalData={personalData}
              clientData={clientData}
              clientId={headerClientId || null}
            />

            <AssignmentContextCard
              process={process}
              consultorNames={resolveAssignedNames(
                process.consultor_names,
                process.assigned_consultor_ids?.length ? process.assigned_consultor_ids : process.assigned_consultor_id,
                appUsersById,
              )}
              mediadorNames={resolveAssignedNames(
                process.mediador_names,
                process.assigned_mediador_ids?.length ? process.assigned_mediador_ids : process.assigned_mediador_id,
                appUsersById,
              )}
              deadlines={deadlines}
              onManageAssignment={openAssignDialog}
              canManageAssignment={userRole !== "cliente"}
              priority={process?.prioridade || "media"}
              onPriorityChange={(value) => {
                setProcess(prev => ({ ...prev, prioridade: value }));
                if (canEditPersonal && !isProcessLocked) handleSaveOrganization({ prioridade: value });
              }}
              canEditPriority={canEditPersonal && !isProcessLocked}
            />

            {/* Tarefas - visível se tem manage_tasks.
                Lote 4, ponto 13: o TasksPanel JÁ É um cartão completo com
                cabeçalho, contagem e área de scroll próprios. Havia aqui
                um segundo Card, um segundo título "Tarefas" e um segundo
                ScrollArea por cima dos dele — e `compact={false}` desligava
                o modo compacto que o componente já tinha. Um cartão só,
                desenhado por quem sabe o que tem dentro. */}
            {canManageTasks && (
              <TasksPanel
                processId={id}
                processName={process?.client_name}
                compact
                maxHeight="320px"
              />
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
          </div>
        </div>
      </div>
      
      {/* Dialog para atribuir utilizadores */}
      <ProcessAssignDialog
        open={showAssignDialog}
        onOpenChange={setShowAssignDialog}
        clientName={clientData?.nome || process?.client_name || personalData?.nome_completo}
        processNumber={process?.process_number}
        loadingUsers={loadingUsers}
        appUsers={appUsers}
        selectedConsultores={selectedConsultores}
        setSelectedConsultores={setSelectedConsultores}
        selectedMediadores={selectedMediadores}
        setSelectedMediadores={setSelectedMediadores}
        selectedIndexacao={selectedIndexacao}
        setSelectedIndexacao={setSelectedIndexacao}
        selectedParceiro={selectedParceiro}
        setSelectedParceiro={setSelectedParceiro}
        savingAssignment={savingAssignment}
        onSave={handleSaveAssignment}
      />

      {/* Dialog de Revisão de Conflitos IA */}
      <AIReviewDialog
        open={showAIReviewDialog}
        conflicts={aiConflicts}
        newValues={revisaoPendente?.newValues || []}
        sourceDocument={revisaoPendente?.sourceDocument || ""}
        onOpenChange={handleAIReviewOpenChange}
        onResolve={resolveAIConflict}
        onConfirmAll={handleConfirmAIReview}
      />

      {/* Dialog: documento ambíguo → Titular 1 / Titular 2 / Ignorar */}
      <TitularChoiceDialog
        open={titularChoiceDialog.open}
        items={titularChoiceDialog.items}
        onOpenChange={handleTitularDialogOpenChange}
        onChoose={handleTitularChoice}
        onConfirm={confirmTitularChoices}
      />

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
