/**
 * S3FileManager — Gestor de documentos AWS S3 com capacidades de IA e anotações.
 *
 * PORQUÊ: O PowerCell migrou do OneDrive para AWS S3 para armazenamento de documentos
 * dos clientes. Este componente é a interface central para upload, organização,
 * visualização e análise de documentos (PDF, imagens, etc.). A integração com IA permite
 * extrair automaticamente dados de documentos (NIF, morada, salário, etc.) e
 * pré-preencher fichas de processo, reduzindo trabalho manual da equipa de indexação.
 *
 * DECISÕES ARQUITECTURAIS:
 * - Categorias de documentos (Pessoais, Financeiros, Imóvel, Bancários, Outros)
 *   para organização automática por IA.
 * - Download via proxy backend para evitar problemas de CORS do S3 directo.
 * - Upload com detecção de conflitos (ficheiros duplicados) e diálogo de resolução.
 * - Drag-and-drop para mover ficheiros entre categorias.
 * - Renomeação inteligente por IA para nomes descritivos em português.
 * - Anotações em PDF via PDFAnnotationViewer para marcação de campos relevantes.
 * - Geração de minutas/templates (CPCV, contrato mediação, etc.) com dados do processo.
 * - Para utilizadores de indexação, é obrigatório fornecer o NIF da empresa no upload.
 * - Mapeamento S3 individual disponível apenas para admins.
 *
 * @param {Object} props
 * @param {string} props.processId — ID do processo para gerir documentos
 * @param {string} [props.clientName] — Nome do cliente (para mapeamento S3)
 * @param {Function} [props.onAIDataExtracted] — Callback quando a IA extrai dados dos documentos
 *
 * @context {AuthContext} — Consome token, user e effectiveRole para permissões de role.
 *   Os pedidos vão pelo cliente Axios (`services/api`), que injecta
 *   `Authorization`, `X-Company-Id` e `X-Active-Role` — um `fetch` cru só
 *   levaria o que lhe escrevessem à mão (ver AGENTS.md).
 *
 * @example
 * <S3FileManager
 *   processId="proc-123"
 *   clientName="João Silva"
 *   onAIDataExtracted={(data) => {
 *     setPersonalData(prev => ({ ...prev, ...data.extractedData }));
 *   }}
 * />
 */
import { useState, useEffect, useCallback, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "../lib/queryClient";
import { useAuth } from "../contexts/AuthContext";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "./ui/card";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import AIResultsDialog from "./storage/dialogs/AIResultsDialog";
import EmpresaNifDialog from "./storage/dialogs/EmpresaNifDialog";
import MoveConflictDialog from "./storage/dialogs/MoveConflictDialog";
import DeleteFileDialog from "./storage/dialogs/DeleteFileDialog";
import BulkDeleteDialog from "./storage/dialogs/BulkDeleteDialog";
import ManualRenameDialog from "./storage/dialogs/ManualRenameDialog";
import SmartRenameResultsDialog from "./storage/dialogs/SmartRenameResultsDialog";
import OrganizeResultsDialog from "./storage/dialogs/OrganizeResultsDialog";
import GenerateTemplateDialog from "./storage/dialogs/GenerateTemplateDialog";
import UploadConflictDialog from "./storage/dialogs/UploadConflictDialog";
import { ScrollArea } from "./ui/scroll-area";
import { Progress } from "./ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "./ui/alert-dialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import { toast } from "sonner";
import { extractErrorMessage } from "../utils/extractErrorMessage";
import PDFAnnotationViewer from "./PDFAnnotationViewer";
// PACOTE DJ — Modal de revisão Human-in-the-Loop de sugestões IA por documento
import DocumentReviewModal from "./DocumentReviewModal";
import { hasRole, MANAGEMENT_ROLES, canAccessByEffectiveRole } from "../utils/roleUtils";
import {
  FileText,
  ScanText,
  Upload,
  Loader2,
  Download,
  Trash2,
  FolderOpen,
  RefreshCw,
  ShieldAlert,
  User,
  Briefcase,
  Building2,
  CreditCard,
  FileImage,
  FileSpreadsheet,
  File,
  CheckCircle,
  AlertCircle,
  Cloud,
  FileDown,
  AlertTriangle,
  Search,
  X,
  Sparkles,
  Brain,
  BrainCircuit, // PACOTE DJ — trigger IA per-document (HITL)
  CheckCircle2, // PACOTE DJ — badge "approved"
  CheckSquare,
  Square,
  Link,
  Settings2,
  ChevronDown,
  ChevronUp,
  Save,
  LayoutGrid,
  List,
  HardDrive,
  Eye,
  ExternalLink,
  Pencil,
  FolderSync,
  MessageSquare,
} from "lucide-react";
import { Input } from "./ui/input";
import { pt } from "date-fns/locale";
import { safeDate, safeFormat } from "../lib/utils";
// PACOTE DJ — helper api.js para o novo endpoint de revisão HITL
import {
  aiAnalyzeS3Documents,
  aiApplyS3Suggestions,
  analyzeDocumentForReview,
  extractDocumentData,
  bulkDeleteProcessS3Files,
  bulkDownloadS3Files,
  categorizeAllS3Documents,
  checkEmployerNif,
  checkS3MoveConflict,
  checkS3UploadConflict,
  deleteProcessS3File,
  generateProcessTemplate,
  getClientS3Mappings,
  getProcessS3Files,
  getS3FileContent,
  moveS3File,
  organizeS3Documents,
  renameAllS3DocumentsSmart,
  readBlobErrorBody,
  renameS3DocumentSmart,
  saveClientS3Mapping,
  uploadProcessS3File,
} from "../services/api";


// Calcula cor de texto com contraste adequado para a cor de fundo
const getContrastColor = (bgColor) => {
  if (!bgColor) return '#ffffff';
  const namedColors = {
    yellow: '#EAB308', orange: '#F97316', blue: '#3B82F6',
    green: '#22C55E', red: '#EF4444', purple: '#A855F7', gray: '#6B7280', teal: '#14B8A6',
  };
  let hex = namedColors[bgColor?.toLowerCase()] || bgColor;
  if (!hex.startsWith('#')) return '#ffffff';
  const clean = hex.replace('#', '');
  const r = parseInt(clean.substring(0, 2), 16);
  const g = parseInt(clean.substring(2, 4), 16);
  const b = parseInt(clean.substring(4, 6), 16);
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance > 0.55 ? '#1a1a1a' : '#ffffff';
};

// Categorias com ícones e cores
const CATEGORIES = [
  { id: "Documentos Pessoais", label: "Pessoais", icon: User, color: "blue" },
  { id: "Financeiros", label: "Financeiros", icon: Briefcase, color: "green" },
  { id: "Imóvel", label: "Imóvel", icon: Building2, color: "purple" },
  { id: "Bancários", label: "Bancários", icon: CreditCard, color: "orange" },
  { id: "Index", label: "Index", icon: FileText, color: "teal" },
  { id: "Outros", label: "Outros", icon: FolderOpen, color: "gray" },
];

// ====================================================================
// PACOTE BL — CATEGORIA INDEX FORÇADA E PRIVADA (BLOQUEIO DE SEGURANÇA)
// ====================================================================
// A categoria "Index" é a "pasta cofre" onde vão parar todos os
// documentos enviados diretamente pelo cliente através do Portal.
// Esta categoria é tratada EXCLUSIVAMENTE pela equipa de Indexação
// (e gestão: admin/CEO/diretor). Os restantes roles (consultor,
// intermediário, administrativo, etc.) NÃO a veem no painel de
// documentos — o filtro abaixo remove-a da UI para esses roles.
// ====================================================================
const INDEX_CATEGORY_ID = "Index";
const INDEX_CATEGORY_ALLOWED_ROLES = ["admin", "ceo", "diretor", "indexacao"];

// Ícone baseado na extensão do ficheiro
const FileIcon = ({ filename }) => {
  const ext = filename?.split('.').pop()?.toLowerCase();
  
  if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg'].includes(ext)) {
    return <FileImage className="h-4 w-4 text-pink-500" />;
  }
  if (['xls', 'xlsx', 'csv'].includes(ext)) {
    return <FileSpreadsheet className="h-4 w-4 text-green-500" />;
  }
  if (['pdf'].includes(ext)) {
    return <FileText className="h-4 w-4 text-red-500" />;
  }
  return <File className="h-4 w-4 text-gray-500" />;
};

const S3FileManager = ({ processId, clientName, onAIDataExtracted, onDocumentDataExtracted }) => {
  const { token, user, effectiveRole } = useAuth();
  const queryClient = useQueryClient();
  const [files, setFiles] = useState({});
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  // PACOTE 11 (Eixo 3 — Privacy Warning localizado): quando o utilizador
  // não tem permissão para ver os documentos do processo (403 do backend,
  // guard `assert_can_view_process_documents`), o aviso passa a ser
  // renderizado DENTRO desta tab (em vez de toast genérico + painel vazio).
  // O S3FileManager só é renderizado na tab Documentos — a restante vista
  // do processo continua acessível.
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [activeTab, setActiveTab] = useState("all"); // "all" para mostrar todos, ou categoria específica
  const [deleteDialog, setDeleteDialog] = useState({ open: false, file: null });
  const [deleting, setDeleting] = useState(false);
  const [bulkDeleteDialog, setBulkDeleteDialog] = useState({ open: false });
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const fileInputRef = useRef(null);

  // Estado para geração de minutas
  const [templateDialog, setTemplateDialog] = useState({ open: false });
  const [selectedTemplate, setSelectedTemplate] = useState("");
  const [generatingTemplate, setGeneratingTemplate] = useState(false);
  const [templateError, setTemplateError] = useState(null);
  
  // Estado para análise IA
  const [aiAnalyzing, setAiAnalyzing] = useState(false);
  const [aiDialog, setAiDialog] = useState({ open: false, results: null });
  const [selectedFilesForAI, setSelectedFilesForAI] = useState([]);
  const [applyingChanges, setApplyingChanges] = useState(false);

  // PACOTE DJ — Revisão Human-in-the-Loop de sugestões IA por documento.
  // `analyzingDocIds` guarda os docIds em análise (mostra badge "A analisar..."
  // por ficheiro enquanto o endpoint /ai-analyze-review corre). `reviewModal`
  // controla a abertura do DocumentReviewModal com o doc a rever.
  const [analyzingDocIds, setAnalyzingDocIds] = useState(new Set());
  // Épico 9 — extracção de dados por ficheiro. Indexado pelo CAMINHO S3
  // (e não pelo doc_id): ficheiros ainda sem `document_metadata` também
  // podem ser lidos, e o caminho existe sempre na listagem.
  const [extractingPaths, setExtractingPaths] = useState(new Set());
  const [reviewModal, setReviewModal] = useState({ open: false, doc: null });

  
  // Estado para mapeamento S3 individual
  const [s3MappingOpen, setS3MappingOpen] = useState(false);
  const [s3Folders, setS3Folders] = useState([]);
  const [currentS3Mapping, setCurrentS3Mapping] = useState(null);
  const [selectedS3Folder, setSelectedS3Folder] = useState("");
  const [savingS3Mapping, setSavingS3Mapping] = useState(false);
  const [loadingS3Folders, setLoadingS3Folders] = useState(false);
  
  // Estado para renomeação inteligente (IA)
  const [renaming, setRenaming] = useState(false);
  const [renameDialog, setRenameDialog] = useState({ open: false, results: null });
  
  // Estado para renomeação manual (por ficheiro individual)
  const [manualRenameDialog, setManualRenameDialog] = useState({ open: false, file: null, newName: "" });
  const [manualRenaming, setManualRenaming] = useState(false);
  
  // Estado para organização rápida de documentos
  const [organizing, setOrganizing] = useState(false);
  const [organizeResults, setOrganizeResults] = useState(null);
  
  // Estado para drag and drop
  const [draggedFile, setDraggedFile] = useState(null);
  const [draggedFiles, setDraggedFiles] = useState([]); // Múltiplos ficheiros selecionados
  const [dropTarget, setDropTarget] = useState(null);
  const [, setMoving] = useState(false);
  const [dragCounter, setDragCounter] = useState(0); // Contador para drag enter/leave correto
  
  // Estado para conflito de nomes ao mover/renomear
  const [conflictDialog, setConflictDialog] = useState({ 
    open: false, 
    files: [], 
    targetCategory: null,
    currentIndex: 0,
    conflicts: []
  });
  
  // Estado para ordenação de ficheiros
  const [sortBy, setSortBy] = useState("date"); // "date", "name", "size", "category"
  const [sortOrder, setSortOrder] = useState("desc"); // "asc", "desc"
  
  // Estado para modo de visualização (lista ou grelha)
  const [viewMode, setViewMode] = useState("list"); // "list" | "grid"
  
  // Estado para categoria seleccionada na sidebar
  const [selectedCategory, setSelectedCategory] = useState(null); // null = todos
  
  // Estado para preview do documento
  const [previewFile, setPreviewFile] = useState(null); // ficheiro em preview
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewUrl, setPreviewUrl] = useState(null);
  
  // Estado para o visualizador de anotações
  const [annotationViewer, setAnnotationViewer] = useState(null); // { path, name }
  
  // Estado para NIF da empresa (obrigatório para indexacao)
  const [empresaNifDialog, setEmpresaNifDialog] = useState({ open: false, files: [], empresaNif: "", checking: false, existingProcesses: null });
  const [pendingFiles, setPendingFiles] = useState(null);
  
  // Estado para conflitos de upload (ficheiros duplicados)
  const [uploadConflictDialog, setUploadConflictDialog] = useState({
    open: false,
    conflicts: [],
    files: [],
    empresaNif: null,
    currentConflictIndex: 0,
    selectedAction: null, // 'overwrite' | 'rename' | 'skip'
    selectedRename: null
  });
  
  // Verificar se o utilizador pode mapear S3 (apenas admin)
  const canMapS3 = hasRole(user, "admin");

  // Verificar se o utilizador é de indexacao (precisa de NIF da empresa)
  const isIndexacao = hasRole(user, "indexacao");

  // Analisar / Renomear com IA — apenas cargos superiores (admin, CEO, diretor/"gestor")
  // Usa effectiveRole (perfil activo), não hasRole, para multi-perfil.
  const canUseAIDocumentTools = MANAGEMENT_ROLES.includes(effectiveRole);

  // PACOTE BL — Bloqueio de segurança: categoria "Index" (pasta cofre)
  // Apenas admin/CEO/diretor/indexacao vêem documentos da categoria "Index".
  // Os restantes roles (consultor, intermediário, administrativo, etc.) não
  // veem estes documentos na UI — são filtrados em getAllFiles(),
  // getFilteredCategoryFiles() e na lista de categorias da sidebar.
  // Pacote FO — usa o cargo efetivo (effectiveRole / perfil ativo do UCR),
  // não hasAnyRole(user, ...) que lê role/additional_roles em bruto do
  // JWT e ignoraria a troca de perfil multi-empresa.
  const canSeeIndexCategory = canAccessByEffectiveRole(effectiveRole, INDEX_CATEGORY_ALLOWED_ROLES);

  // PACOTE BL — Lista de categorias visíveis na sidebar (exclui "Index" para
  // roles não autorizados). Usada em todos os CATEGORIES.map da UI.
  const visibleCategories = canSeeIndexCategory
    ? CATEGORIES
    : CATEGORIES.filter(cat => cat.id !== INDEX_CATEGORY_ID);

  // PACOTE BL — Guard: se selectedCategory for "Index" e o utilizador não
  // tem permissão (ex: impersonate terminou, mudança de role), volta para
  // "all" (todos). Evita mostrar um TabsContent vazio sem explicação.
  useEffect(() => {
    if (selectedCategory === INDEX_CATEGORY_ID && !canSeeIndexCategory) {
      setSelectedCategory(null);
    }
  }, [selectedCategory, canSeeIndexCategory]);
  
  // Função para ordenar ficheiros
  const sortFiles = (filesList) => {
    return [...filesList].sort((a, b) => {
      let comparison = 0;
      
      if (sortBy === "date") {
        const dateA = safeDate(a.last_modified);
        const dateB = safeDate(b.last_modified);
        // Push items without dates to the end
        if (!dateA && !dateB) return 0;
        if (!dateA) return 1;
        if (!dateB) return -1;
        comparison = dateA - dateB;
      } else if (sortBy === "name") {
        comparison = (a.name || "").localeCompare(b.name || "");
      } else if (sortBy === "size") {
        comparison = (a.size || 0) - (b.size || 0);
      } else if (sortBy === "category") {
        comparison = (a.category || "").localeCompare(b.category || "");
      }
      
      return sortOrder === "desc" ? -comparison : comparison;
    });
  };
  
  // Toggle ordenação
  const toggleSort = (field) => {
    if (sortBy === field) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    } else {
      setSortBy(field);
      setSortOrder("desc");
    }
  };
  
  // Lista de templates disponíveis
  const TEMPLATES = [
    { value: "cpcv", label: "CPCV - Contrato Promessa Compra e Venda" },
    { value: "contrato_mediacao", label: "Contrato de Mediação Imobiliária" },
    { value: "ficha_visita", label: "Ficha de Visita ao Imóvel" },
    { value: "valuation_appeal", label: "Apelação de Avaliação Bancária" },
    { value: "deed_reminder", label: "Lembrete de Escritura" },
  ];

  // Carregar ficheiros
  const fetchFiles = useCallback(async () => {
    if (!processId) return;

    try {
      const { data } = await getProcessS3Files(processId);
      setFiles(data.files || {});
      setStats(data.stats || null);
      setPermissionDenied(false);
    } catch (error) {
      const status = error?.response?.status;
      if (status === 403) {
        // PACOTE 11 — permissão insuficiente: aviso LOCALIZADO à tab (sem
        // toast global), o utilizador continua a navegar no resto do processo.
        // O `skipErrorToast` da função de API é o que impede o interceptor
        // de sobrepor aqui o toast genérico "Acesso Negado".
        setPermissionDenied(true);
        setFiles({});
        setStats(null);
      } else if (status) {
        const detalhe = error?.response?.data?.detail;
        if (detalhe !== "S3 não configurado") {
          toast.error(extractErrorMessage(detalhe, "Erro ao carregar ficheiros"));
        }
      } else {
        console.error("Erro ao carregar ficheiros:", error);
      }
    } finally {
      setLoading(false);
    }
  }, [processId]);

  useEffect(() => {
    fetchFiles();
  }, [fetchFiles]);

  // Carregar mapeamento S3 actual e pastas disponíveis
  const loadS3MappingData = async () => {
    if (!canMapS3) return;
    
    setLoadingS3Folders(true);
    try {
      // Buscar dados do mapeamento
      const { data } = await getClientS3Mappings(clientName || "");
      setS3Folders(data.available_folders || []);

      // Encontrar mapeamento actual deste processo
      const currentProcess = data.processes?.find(p => p.id === processId);
      if (currentProcess) {
        // Backend retorna 's3_folder', não 's3_folder_mapping'
        setCurrentS3Mapping(currentProcess.s3_folder || null);
        setSelectedS3Folder(currentProcess.s3_folder || "");
      }
    } catch (error) {
      console.error("Erro ao carregar mapeamento S3:", error);
    } finally {
      setLoadingS3Folders(false);
    }
  };

  // Guardar mapeamento S3
  const saveS3Mapping = async () => {
    if (!canMapS3) return;
    
    setSavingS3Mapping(true);
    try {
      const { data } = await saveClientS3Mapping(processId, selectedS3Folder);
      toast.success(data.message || "Mapeamento guardado");
      setCurrentS3Mapping(selectedS3Folder);
      setS3MappingOpen(false);
      // Recarregar ficheiros para mostrar os da nova pasta
      fetchFiles();
    } catch (error) {
      console.error("Erro ao guardar mapeamento:", error);
      toast.error(
        extractErrorMessage(
          error?.response?.data?.detail,
          "Erro ao guardar mapeamento",
        ),
      );
    } finally {
      setSavingS3Mapping(false);
    }
  };

  // Inicializar pastas

  // Verificar NIF da empresa
  const checkEmpresaNif = async (nif) => {
    try {
      const { data } = await checkEmployerNif(nif);
      return data;
    } catch (error) {
      console.error("Erro ao verificar NIF:", error);
      return null;
    }
  };

  // Handle do botão de verificar NIF
  const handleVerifyEmpresaNif = async () => {
    const nif = empresaNifDialog.empresaNif.trim();
    
    // Validar NIF (9 dígitos)
    if (!/^\d{9}$/.test(nif)) {
      toast.error("NIF inválido. Deve conter exatamente 9 dígitos.");
      return;
    }
    
    setEmpresaNifDialog(prev => ({ ...prev, checking: true }));
    
    const result = await checkEmpresaNif(nif);
    
    setEmpresaNifDialog(prev => ({
      ...prev,
      checking: false,
      existingProcesses: result
    }));
  };

  // Confirmar upload com NIF da empresa
  const handleConfirmUploadWithNif = async () => {
    const nif = empresaNifDialog.empresaNif.trim();
    
    if (!/^\d{9}$/.test(nif)) {
      toast.error("NIF inválido. Deve conter exatamente 9 dígitos.");
      return;
    }
    
    setEmpresaNifDialog(prev => ({ ...prev, open: false }));
    
    // Prosseguir com o upload usando o NIF
    if (pendingFiles) {
      await executeUpload(pendingFiles, nif);
      setPendingFiles(null);
    }
  };

  // Executar upload dos ficheiros
  const executeUpload = async (files, empresaNif = null) => {
    setUploading(true);
    setUploadProgress(0);

    let successCount = 0;
    let errorCount = 0;
    const totalFiles = files.length;

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const formData = new FormData();
      formData.append("file", file);
      // Quando está no tab "all", usar "Outros" como categoria default
      formData.append("category", activeTab === "all" ? "Outros" : activeTab);
      
      // Adicionar NIF da empresa se fornecido
      if (empresaNif) {
        formData.append("empresa_nif", empresaNif);
      }

      try {
        await uploadProcessS3File(processId, formData);
        successCount++;
      } catch (error) {
        const status = error?.response?.status;
        if (status === 429) {
          // Rate limiting. O interceptor do Axios já tentou de novo (3x com
          // recuo exponencial) antes de chegar aqui; esta espera é a última
          // linha, mantida do comportamento anterior para que um lote
          // grande acabe por passar em vez de perder ficheiros.
          const retryAfter = error?.response?.headers?.["retry-after"] || 60;
          toast.warning(`Aguardar ${retryAfter} segundos antes de continuar...`);
          await new Promise(resolve => setTimeout(resolve, parseInt(retryAfter) * 1000));
          i--; // Tentar novamente o mesmo ficheiro
          continue;
        }
        if (status) {
          const errorMsg = extractErrorMessage(
            error?.response?.data?.detail,
            `Erro ${status}`,
          );
          toast.error(`${file.name}: ${errorMsg}`);
        } else {
          toast.error(`Erro de conexão ao enviar ${file.name}`);
        }
        errorCount++;
      }

      setUploadProgress(((i + 1) / totalFiles) * 100);
      
      // Pequeno delay entre uploads para evitar rate limiting
      if (i < files.length - 1) {
        await new Promise(resolve => setTimeout(resolve, 200));
      }
    }

    if (successCount > 0) {
      toast.success(
        successCount === totalFiles
          ? `${successCount} ficheiro(s) enviado(s) com sucesso`
          : `${successCount}/${totalFiles} ficheiros enviados`
      );
      fetchFiles();
      // Reatividade: um upload interno pode ter sido auto-associado a um
      // pedido pendente do Portal do Cliente (_auto_fulfill_portal_request
      // no backend). Invalidar a query garante que o consultor vê o
      // estado "Recebido" no PortalDocumentRequests sem refresh manual.
      queryClient.invalidateQueries({ queryKey: queryKeys.portalRequests.byProcess(processId) });
    }
    
    if (errorCount > 0 && successCount === 0) {
      toast.error(`Falha no upload de ${errorCount} ficheiro(s). Verifique o formato dos ficheiros (PDF, JPEG, PNG, HEIC).`);
    }

    setUploading(false);
    setUploadProgress(0);
    
    // Limpar input
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  // Verificar conflitos de upload antes de enviar
  const checkUploadConflicts = async (filenames, category) => {
    try {
      const { data } = await checkS3UploadConflict({
        process_id: processId,
        filenames: filenames,
        category: category,
      });
      return data;
    } catch (error) {
      console.error("Erro ao verificar conflitos:", error);
      return { has_conflicts: false, conflicts: [] };
    }
  };

  // Upload de ficheiro
  const handleUpload = async (e) => {
    const selectedFiles = Array.from(e.target.files || []);
    if (selectedFiles.length === 0) return;

    // Determinar categoria (quando está no tab "all", usar "Outros")
    const category = activeTab === "all" ? "Outros" : activeTab;

    // Verificar conflitos antes de fazer upload
    const filenames = selectedFiles.map(f => f.name);
    const conflictCheck = await checkUploadConflicts(filenames, category);
    
    if (conflictCheck.has_conflicts) {
      // Há conflitos - mostrar diálogo
      setUploadConflictDialog({
        open: true,
        conflicts: conflictCheck.conflicts,
        files: selectedFiles,
        empresaNif: null,
        currentConflictIndex: 0,
        category: category,
        // Para cada conflito, guardar a ação escolhida
        resolutions: conflictCheck.conflicts.map(() => ({ action: null, customName: null }))
      });
      return;
    }

    // Se o utilizador é "indexacao", pedir NIF da empresa
    if (isIndexacao) {
      setPendingFiles(selectedFiles);
      setEmpresaNifDialog({
        open: true,
        files: selectedFiles,
        empresaNif: "",
        checking: false,
        existingProcesses: null
      });
      return;
    }

    // Upload normal para outros utilizadores
    await executeUpload(selectedFiles);
  };
  
  // Resolver conflito individual
  const handleConflictResolution = (action, customName = null) => {
    const { currentConflictIndex, resolutions } = uploadConflictDialog;
    const newResolutions = [...resolutions];
    newResolutions[currentConflictIndex] = { action, customName };
    
    setUploadConflictDialog(prev => ({
      ...prev,
      resolutions: newResolutions
    }));
  };
  
  // Avançar para próximo conflito ou iniciar upload
  const handleNextConflict = async () => {
    const { currentConflictIndex, conflicts, resolutions, files, empresaNif, category } = uploadConflictDialog;
    
    // Verificar se ação foi selecionada
    if (!resolutions[currentConflictIndex]?.action) {
      toast.error("Por favor, selecione uma ação para o conflito");
      return;
    }
    
    // Se há mais conflitos, mostrar o próximo
    if (currentConflictIndex < conflicts.length - 1) {
      setUploadConflictDialog(prev => ({
        ...prev,
        currentConflictIndex: prev.currentConflictIndex + 1
      }));
      return;
    }
    
    // Todos os conflitos foram resolvidos - iniciar upload
    setUploadConflictDialog(prev => ({ ...prev, open: false }));
    
    // Executar upload com resoluções
    await executeUploadWithResolutions(files, conflicts, resolutions, empresaNif, category);
  };
  
  // Cancelar todo o upload
  const handleCancelUpload = () => {
    setUploadConflictDialog({
      open: false,
      conflicts: [],
      files: [],
      empresaNif: null,
      currentConflictIndex: 0,
      resolutions: []
    });
    // Limpar input
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    toast.info("Upload cancelado");
  };
  
  // Executar upload com resoluções de conflitos
  const executeUploadWithResolutions = async (files, conflicts, resolutions, empresaNif, category) => {
    setUploading(true);
    setUploadProgress(0);

    let successCount = 0;
    let errorCount = 0;
    const totalFiles = files.length;

    // Criar mapa de resoluções por nome original
    const resolutionMap = new Map();
    conflicts.forEach((conflict, idx) => {
      resolutionMap.set(conflict.original_filename, resolutions[idx]);
    });

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const formData = new FormData();
      formData.append("file", file);
      formData.append("category", category);
      
      // Adicionar NIF da empresa se fornecido
      if (empresaNif) {
        formData.append("empresa_nif", empresaNif);
      }
      
      // Verificar se há resolução para este ficheiro
      const resolution = resolutionMap.get(file.name);
      if (resolution) {
        if (resolution.action === 'rename' && resolution.customName) {
          formData.append("custom_filename", resolution.customName);
        } else if (resolution.action === 'skip') {
          // Saltar este ficheiro
          continue;
        }
        // Se action === 'overwrite', não enviar custom_filename (S3 sobrepõe por defeito)
      }

      try {
        await uploadProcessS3File(processId, formData);
        successCount++;
      } catch (error) {
        const status = error?.response?.status;
        if (status === 429) {
          const retryAfter = error?.response?.headers?.["retry-after"] || 60;
          toast.warning(`Aguardar ${retryAfter} segundos antes de continuar...`);
          await new Promise(resolve => setTimeout(resolve, parseInt(retryAfter) * 1000));
          i--;
          continue;
        }
        if (status) {
          const errorMsg = extractErrorMessage(
            error?.response?.data?.detail,
            `Erro ${status}`,
          );
          toast.error(`${file.name}: ${errorMsg}`);
        } else {
          toast.error(`Erro de conexão ao enviar ${file.name}`);
        }
        errorCount++;
      }

      setUploadProgress(((i + 1) / totalFiles) * 100);
      
      if (i < files.length - 1) {
        await new Promise(resolve => setTimeout(resolve, 200));
      }
    }

    if (successCount > 0) {
      const skipped = resolutions.filter(r => r.action === 'skip').length;
      const message = skipped > 0
        ? `${successCount} ficheiro(s) enviado(s), ${skipped} ignorado(s)`
        : `${successCount} ficheiro(s) enviado(s) com sucesso`;
      toast.success(message);
      fetchFiles();
      // Reatividade: ver comentário equivalente em executeUpload().
      queryClient.invalidateQueries({ queryKey: queryKeys.portalRequests.byProcess(processId) });
    }
    
    if (errorCount > 0 && successCount === 0) {
      toast.error(`Falha no upload de ${errorCount} ficheiro(s).`);
    }

    setUploading(false);
    setUploadProgress(0);
    
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  // Download de ficheiro - usa proxy para evitar CORS
  const handleDownload = async (file) => {
    try {
      // Usar proxy endpoint para evitar CORS do S3
      const { data: blob } = await getS3FileContent(file.path);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = file.name || 'download';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Erro ao fazer download:", error);
      toast.error(
        extractErrorMessage(
          error?.response?.data?.detail,
          "Erro ao fazer download",
        ),
      );
    }
  };

  // ── Fechos e edições dos diálogos extraídos (Épico 8) ────────────
  // Cancelar o NIF limpa também o `input` de ficheiro: sem isso, escolher
  // o MESMO ficheiro outra vez não dispara `change` e o upload não arranca.
  const handleCancelEmpresaNif = useCallback(() => {
    setEmpresaNifDialog({ open: false, files: [], empresaNif: "", checking: false, existingProcesses: null });
    setPendingFiles(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }, []);

  const handleEmpresaNifChange = useCallback((nif) => {
    setEmpresaNifDialog((anterior) => ({ ...anterior, empresaNif: nif }));
  }, []);

  // Cancelar o conflito de movimentação limpa também o estado de
  // arrastamento — senão o próximo "largar" herdaria os ficheiros antigos.
  const handleCancelMoveConflict = useCallback(() => {
    setConflictDialog({ open: false, files: [], targetCategory: null, currentIndex: 0, conflicts: [] });
    setDraggedFile(null);
    setDraggedFiles([]);
  }, []);

  // Os diálogos são de apresentação: devolvem a intenção, e é aqui que se
  // decide o que ela implica ao estado.
  const handleDeleteDialogOpenChange = useCallback((aberto) => {
    setDeleteDialog({ open: aberto, file: null });
  }, []);

  const handleManualRenameOpenChange = useCallback((aberto) => {
    if (!aberto) setManualRenameDialog({ open: false, file: null, newName: "" });
  }, []);

  const handleManualRenameNameChange = useCallback((nome) => {
    setManualRenameDialog((anterior) => ({ ...anterior, newName: nome }));
  }, []);

  // Fechar preserva os resultados enquanto o diálogo estiver aberto, tal
  // como antes; ao fechar de vez, limpa-os.
  const handleRenameDialogOpenChange = useCallback((aberto) => {
    setRenameDialog((anterior) => ({
      open: aberto,
      results: aberto ? anterior.results : null,
    }));
  }, []);

  const handleCloseOrganizeResults = useCallback(() => setOrganizeResults(null), []);

  // Fechar o diálogo de minutas limpa a escolha e o erro de validação —
  // reabrir traz uma folha em branco, como antes.
  const handleTemplateDialogOpenChange = useCallback((aberto) => {
    setTemplateDialog({ open: aberto });
    if (!aberto) {
      setTemplateError(null);
      setSelectedTemplate("");
    }
  }, []);

  // Escolher um tipo novo limpa o erro do tipo anterior.
  const handleTemplateChange = useCallback((id) => {
    setSelectedTemplate(id);
    setTemplateError(null);
  }, []);

  // Eliminar ficheiro
  const handleDelete = async () => {
    if (!deleteDialog.file) return;

    // Impedir eliminação de pastas (paths que terminam com /)
    if (deleteDialog.file.path?.endsWith('/')) {
      toast.error("Não é possível eliminar pastas. Selecione um ficheiro específico.");
      setDeleteDialog({ open: false, file: null });
      return;
    }

    setDeleting(true);
    try {
      await deleteProcessS3File(processId, deleteDialog.file.path);
      toast.success("Ficheiro eliminado");
      fetchFiles();
    } catch (error) {
      toast.error(
        extractErrorMessage(
          error?.response?.data?.detail,
          "Erro ao eliminar ficheiro",
        ),
      );
    } finally {
      setDeleting(false);
      setDeleteDialog({ open: false, file: null });
    }
  };

  // Eliminar ficheiros selecionados em massa
  const handleBulkDelete = async () => {
    if (selectedFilesForAI.length === 0) return;

    setBulkDeleting(true);
    try {
      const { data } = await bulkDeleteProcessS3Files(
        processId,
        selectedFilesForAI.map((f) => f.path),
      );
      const deleted = data.deleted_count || 0;
      const failed = data.failed_count || 0;
      if (failed > 0) {
        toast.warning(
          `${deleted} ficheiro(s) eliminado(s), ${failed} falhou(aram)`
        );
      } else {
        toast.success(`${deleted} ficheiro(s) eliminado(s) com sucesso`);
      }
      setSelectedFilesForAI([]);
      setBulkDeleteDialog({ open: false });
      fetchFiles();
    } catch (error) {
      console.error("Erro ao eliminar ficheiros em massa:", error);
      toast.error(
        extractErrorMessage(
          error?.response?.data?.detail,
          "Erro ao eliminar ficheiros",
        ),
      );
    } finally {
      setBulkDeleting(false);
    }
  };

  // Gerar minuta/template
  const handleGenerateTemplate = async () => {
    if (!selectedTemplate) {
      toast.error("Selecione um tipo de documento");
      return;
    }

    setGeneratingTemplate(true);
    setTemplateError(null);

    try {
      const resposta = await generateProcessTemplate(processId, selectedTemplate);
      const url = window.URL.createObjectURL(resposta.data);
      const a = document.createElement('a');
      a.href = url;

      // Obter nome do ficheiro do header ou usar default
      const disposition = resposta.headers?.["content-disposition"];
      let filename = `minuta_${selectedTemplate}.txt`;
      if (disposition) {
        const match = disposition.match(/filename="(.+)"/);
        if (match) filename = match[1];
      }

      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      toast.success("Minuta gerada com sucesso!");
      setTemplateDialog({ open: false });
      setSelectedTemplate("");
    } catch (error) {
      console.error("Erro ao gerar template:", error);
      // Com `responseType: "blob"` o corpo de ERRO também vem como Blob:
      // sem o ler como texto, a lista de campos em falta desaparecia e o
      // utilizador via só "Erro ao gerar minuta".
      const corpo = await readBlobErrorBody(error);
      if (corpo.detail?.missing_fields) {
        setTemplateError({
          message: corpo.detail.message || "Dados incompletos",
          missingFields: corpo.detail.missing_fields,
        });
      } else {
        toast.error(
          extractErrorMessage(
            corpo.detail?.message || corpo.detail,
            "Erro ao gerar minuta",
          ),
        );
      }
    } finally {
      setGeneratingTemplate(false);
    }
  };

  // Formatar data - dd/mm/AA hh:mm (protecção defensiva contra datas inválidas / Safari)
  const formatDate = (dateStr) => {
    if (!dateStr) return "-";
    return safeFormat(dateStr, "dd/MM/yy HH:mm", { locale: pt });
  };

  // Contar ficheiros por categoria
  const getCategoryCount = (categoryId) => {
    // PACOTE BL: ocultar contagem da categoria "Index" para roles não autorizados
    if (categoryId === INDEX_CATEGORY_ID && !canSeeIndexCategory) {
      return 0;
    }
    return files[categoryId]?.length || 0;
  };

  // Obter todos os ficheiros (todas as categorias)
  const getAllFiles = () => {
    const allFiles = [];
    Object.entries(files).forEach(([categoryKey, categoryFiles]) => {
      if (Array.isArray(categoryFiles)) {
        // PACOTE BL: excluir ficheiros da categoria "Index" (pasta cofre)
        // para utilizadores sem permissão (não admin/CEO/diretor/indexacao).
        if (categoryKey === INDEX_CATEGORY_ID && !canSeeIndexCategory) {
          return; // skip esta categoria
        }
        allFiles.push(...categoryFiles);
      }
    });
    return allFiles;
  };

  // Filtrar ficheiros por pesquisa
  const filterFilesBySearch = (fileList) => {
    if (!searchQuery.trim()) return fileList;
    const query = searchQuery.toLowerCase();
    return fileList.filter(file =>
      file.name.toLowerCase().includes(query) ||
      file.category?.toLowerCase().includes(query)
    );
  };

  // Ficheiros filtrados (todos ou por categoria)
  const filteredFiles = sortFiles(filterFilesBySearch(getAllFiles()));

  // Ficheiros filtrados por categoria específica
  const getFilteredCategoryFiles = (categoryId) => {
    // PACOTE BL: bloquear acesso à categoria "Index" para roles não autorizados.
    // Mesmo que o selectedCategory seja "Index" por algum motivo (ex: URL
    // manipulada, state legacy), retornamos array vazio.
    if (categoryId === INDEX_CATEGORY_ID && !canSeeIndexCategory) {
      return [];
    }
    return sortFiles(filterFilesBySearch(files[categoryId] || []));
  };

  // Toggle seleção de ficheiro para análise IA
  const toggleFileSelection = (file) => {
    setSelectedFilesForAI(prev => {
      const isSelected = prev.some(f => f.path === file.path);
      if (isSelected) {
        return prev.filter(f => f.path !== file.path);
      } else {
        return [...prev, file];
      }
    });
  };
  
  // Selecionar/deselecionar todos os ficheiros visíveis
  const toggleSelectAll = (filesList) => {
    if (selectedFilesForAI.length === filesList.length && filesList.length > 0) {
      // Desselecionar todos
      setSelectedFilesForAI([]);
    } else {
      // Selecionar todos
      setSelectedFilesForAI([...filesList]);
    }
  };
  
  // Obter ficheiros filtrados para a vista atual
  const getDisplayFiles = () => {
    if (selectedCategory) {
      return getFilteredCategoryFiles(selectedCategory);
    }
    return filteredFiles;
  };
  
  // Abrir preview do documento
  const handlePreview = async (file) => {
    setPreviewFile(file);
    setPreviewLoading(true);
    
    try {
      // Usar proxy endpoint para evitar CORS do S3
      const { data: blob } = await getS3FileContent(file.path);
      setPreviewUrl(URL.createObjectURL(blob));
    } catch (error) {
      console.error("Erro ao carregar preview:", error);
      const corpo = await readBlobErrorBody(error);
      toast.error(extractErrorMessage(corpo.detail, "Erro ao carregar preview"));
      setPreviewFile(null);
    } finally {
      setPreviewLoading(false);
    }
  };
  
  // Fechar preview
  const closePreview = () => {
    setPreviewFile(null);
    setPreviewUrl(null);
  };
  
  // Verificar se ficheiro é previewable (PDF ou imagem)
  const isPreviewable = (filename) => {
    const ext = filename?.split('.').pop()?.toLowerCase();
    return ['pdf', 'jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext);
  };
  
  // Épico 9 — o motor de visão só lê imagens e PDF. Um .docx seguiria para
  // uma chamada PAGA e voltaria vazio; mais vale não oferecer o botão.
  const podeExtrairDados = (filename) => {
    const ext = filename?.split('.').pop()?.toLowerCase();
    return ['pdf', 'jpg', 'jpeg', 'png', 'webp'].includes(ext);
  };

  // Verificar se ficheiro é PDF (para anotações)
  const isPdfFile = (filename) => {
    const ext = filename?.split('.').pop()?.toLowerCase();
    return ext === 'pdf';
  };
  
  // Abrir visualizador de anotações
  const handleOpenAnnotations = (file) => {
    setAnnotationViewer({ path: file.path, name: file.name });
  };
  
  // Fechar visualizador de anotações
  const handleCloseAnnotations = () => {
    setAnnotationViewer(null);
  };

  // Análise IA dos documentos (salta docs já marcados com ai_analyzed)
  const handleAIAnalysis = async () => {
    if (!canUseAIDocumentTools) {
      toast.error("Sem permissão para analisar documentos com IA");
      return;
    }

    const candidates = selectedFilesForAI.length > 0 ? selectedFilesForAI : getAllFiles();
    const alreadyAnalyzed = candidates.filter((f) => f.ai_analyzed);
    const filesToAnalyze = candidates.filter((f) => !f.ai_analyzed && !f.path?.endsWith('/'));

    if (candidates.length === 0) {
      toast.error("Não há ficheiros para analisar");
      return;
    }
    if (filesToAnalyze.length === 0) {
      toast.info(
        alreadyAnalyzed.length > 0
          ? "Todos os documentos seleccionados já foram analisados pela IA"
          : "Não há ficheiros para analisar"
      );
      return;
    }
    if (alreadyAnalyzed.length > 0) {
      toast.info(`${alreadyAnalyzed.length} documento(s) já analisado(s) — a saltar`);
    }

    setAiAnalyzing(true);
    toast.info(`A analisar ${filesToAnalyze.length} documento(s) com IA...`);

    try {
      // Criar FormData com os ficheiros + paths S3 (para marcar / saltar no backend)
      const formData = new FormData();
      const uploadedPaths = [];

      // Obter o conteúdo dos ficheiros via proxy endpoint (evita CORS do S3)
      for (const file of filesToAnalyze) {
        try {
          // Usar proxy endpoint que faz streaming através do backend (evita CORS)
          const { data: blob } = await getS3FileContent(file.path);
          formData.append('files', blob, file.name);
          uploadedPaths.push(file.path);
        } catch (e) {
          console.error(`Erro ao obter ficheiro ${file.name}:`, e);
        }
      }

      if (uploadedPaths.length === 0) {
        toast.error("Não foi possível obter ficheiros para análise");
        return;
      }
      formData.append('file_paths', JSON.stringify(uploadedPaths));

      // Enviar para análise
      // O `X-Active-Role` deixa de ser escrito à mão: o interceptor do
      // Axios injecta-o (e o `X-Company-Id`, que aqui nunca seguia).
      let result;
      try {
        ({ data: result } = await aiAnalyzeS3Documents(processId, formData));
      } catch (erroAnalise) {
        const corpo = erroAnalise?.response?.data || {};
        toast.error(extractErrorMessage(corpo.detail, "Erro na análise IA"));
        return;
      }
      {

        if ((result.documents_count || 0) === 0 && (result.skipped_already_analyzed || 0) > 0) {
          toast.info(result.message || "Documentos já analisados pela IA");
          fetchFiles();
          return;
        }
        
        // Se temos callback, passar os dados para pré-preencher a ficha
        if (onAIDataExtracted && result.extracted_data) {
          // Organizar documentos em pastas (mover ficheiros no S3)
          try {
            // Juntar source_path (S3 path) dos ficheiros originais com os resultados da IA
            const docsToOrganize = (result.documents || []).map(doc => {
              const originalFile = filesToAnalyze.find(f => f.name === doc.file_name);
              return {
                ...doc,
                source_path: originalFile?.path || null
              };
            }).filter(doc => doc.source_path);

            if (docsToOrganize.length > 0) {
              await organizeS3Documents(processId, {
                documents: docsToOrganize,
                create_folders: true,
              });
            }
          } catch (orgError) {
            console.warn("Erro ao organizar documentos:", orgError);
          }
          
          // Passar dados extraídos para o componente pai (inclui match titular 1/2)
          onAIDataExtracted({
            extractedData: result.extracted_data,
            fieldConfidence: result.field_confidence || {},
            conflicts: result.conflicts || [],
            documentsProcessed: result.documents_count,
            suggestions: result.suggestions || [],
            titularMatches: result.titular_matches || [],
            needsTitularChoice: !!result.needs_titular_choice,
          });
          
          toast.success(`Análise completa! ${result.documents_count} documento(s) processado(s). Verifique os campos pré-preenchidos.`);
          
          // Não mostrar popup se temos callback
          setSelectedFilesForAI([]);
        } else {
          // Fallback: mostrar popup com resultados
          setAiDialog({ open: true, results: result });
          toast.success(`Análise completa: ${result.documents_count} documento(s) processado(s)`);
        }
        
        // Recarregar ficheiros para ver nova organização + badges "Analisado"
        fetchFiles();
      }
    } catch (error) {
      console.error("Erro na análise IA:", error);
      toast.error("Erro ao analisar documentos");
    } finally {
      setAiAnalyzing(false);
      setSelectedFilesForAI([]);
    }
  };

  // PACOTE DJ — Analisar documento individual para revisão HITL.
  // Diferente do `handleAIAnalysis` (que analisa vários ficheiros via endpoint
  // antigo e auto-aplica), este handler chama o NOVO endpoint
  // `POST /documents/{doc_id}/ai-analyze-review` que:
  //   1. Persiste sugestões em `suggested_*` (NÃO toca em `ai_*`).
  //   2. Marca `ai_review_status='pending'`.
  //   3. Devolve `{ suggestions, current, ai_review_status }` para o modal.
  // Depois de receber a resposta, abre o DocumentReviewModal para o consultor
  // aprovar/rejeitar explicitamente cada campo.
  const handleAnalyzeDocForReview = async (file) => {
    if (!canUseAIDocumentTools) {
      toast.error("Sem permissão para analisar documentos com IA");
      return;
    }
    // O listing de ficheiros (`GET /client/{process_id}/files`) expõe o ID do
    // document_metadata em `file.doc_id`. Fallback para `file.id` se o backend
    // usar esse nome alternativo noutros contextos.
    const docId = file?.doc_id || file?.id;
    if (!docId) {
      toast.error("Não foi possível identificar o documento (doc_id em falta).");
      return;
    }

    setAnalyzingDocIds((prev) => new Set([...prev, docId]));
    try {
      const res = await analyzeDocumentForReview(docId);
      toast.success("Análise IA concluída. Revise as sugestões.");
      // Refresca a lista para mostrar o badge "Sugestões IA" (pending).
      await fetchFiles();
      // Abre o modal de revisão com os dados frescos (suggestions + current).
      // Merge do `file` (com campos `suggested_*` actualizados pelo fetchFiles)
      // com a resposta do endpoint para garantir que temos tudo disponível.
      setReviewModal({
        open: true,
        doc: { ...file, ...(res?.data || {}) },
      });
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Erro ao analisar documento.");
    } finally {
      setAnalyzingDocIds((prev) => {
        const next = new Set(prev);
        next.delete(docId);
        return next;
      });
    }
  };

  /**
   * Épico 9 — lê UM ficheiro com IA e entrega os dados ao contentor.
   *
   * REGRA DE OURO: isto não grava nada. O endpoint é de leitura e o que
   * volta vai para o diálogo de revisão, onde o consultor confirma. Uma
   * alucinação sobre um NIF ou um vencimento não entra na base de dados
   * sem um humano pelo meio.
   */
  const handleExtractDocData = async (file) => {
    if (!canUseAIDocumentTools) {
      toast.error("Sem permissão para extrair dados com IA");
      return;
    }
    const caminho = file?.path;
    if (!caminho) {
      toast.error("Não foi possível identificar o ficheiro (caminho em falta).");
      return;
    }
    if (!podeExtrairDados(file?.name)) {
      toast.error("Formato não suportado. A extracção aceita imagens e PDF.");
      return;
    }

    setExtractingPaths((prev) => new Set([...prev, caminho]));
    try {
      const { data: resultado } = await extractDocumentData(processId, caminho);
      const extraidos = resultado?.extracted_data || {};
      if (Object.keys(extraidos).length === 0) {
        toast.warning("A IA não conseguiu ler dados deste documento.");
        return;
      }
      if (!onDocumentDataExtracted) {
        // Sem contentor a ouvir não há onde rever; melhor dizê-lo do que
        // deixar o consultor à espera de um diálogo que nunca abre.
        toast.info("Dados extraídos, mas não há ecrã de revisão disponível.");
        return;
      }
      onDocumentDataExtracted({
        extractedData: extraidos,
        fieldConfidence: resultado?.field_confidence || {},
        conflicts: resultado?.conflicts || [],
        sourceDocument: resultado?.source_document?.name || file?.name || "",
        titularMatches: resultado?.titular_matches || [],
        needsTitularChoice: !!resultado?.needs_titular_choice,
      });
    } catch (err) {
      toast.error(
        extractErrorMessage(
          err?.response?.data?.detail,
          "Erro ao extrair dados do documento.",
        ),
      );
    } finally {
      setExtractingPaths((prev) => {
        const next = new Set(prev);
        next.delete(caminho);
        return next;
      });
    }
  };

  // PACOTE DJ — Abrir o modal de revisão para um ficheiro que já tem
  // `ai_review_status='pending'` (sugestões gravadas, à espera de decisão).
  // Não chama o endpoint de análise; apenas abre o modal com os dados que
  // já vieram no listing (`suggested_*` + `ai_*`/`current`).
  const handleOpenReviewModal = (file) => {
    if (!file) return;
    setReviewModal({ open: true, doc: file });
  };

  // Fechar o diálogo de resultados. Reabrir sem resultados limpava-os; o
  // comportamento anterior preservava-os enquanto o diálogo estivesse
  // aberto, e é isso que se mantém.
  const handleAIDialogOpenChange = useCallback((aberto) => {
    setAiDialog((anterior) => ({
      open: aberto,
      results: aberto ? anterior.results : null,
    }));
  }, []);

  // Aplicar sugestões da análise IA
  const handleApplyAISuggestions = async (suggestions) => {
    if (!suggestions || Object.keys(suggestions).length === 0) {
      toast.info("Nenhuma sugestão para aplicar");
      return;
    }

    setApplyingChanges(true);
    try {
      const { data: result } = await aiApplyS3Suggestions(processId, suggestions);
      toast.success(`${result.updated_fields} campo(s) actualizado(s)`);
      setAiDialog({ open: false, results: null });
    } catch (error) {
      console.error("Erro ao aplicar sugestões:", error);
      toast.error(
        extractErrorMessage(
          error?.response?.data?.detail,
          "Erro ao aplicar alterações",
        ),
      );
    } finally {
      setApplyingChanges(false);
    }
  };

  // Renomeação inteligente: categoriza com IA (se necessário) e aplica nomes legíveis
  const handleSmartRename = async () => {
    if (!canUseAIDocumentTools) {
      toast.error("Sem permissão para renomear documentos com IA");
      return;
    }

    const allFiles = getAllFiles().filter((f) => !f.path?.endsWith('/'));
    if (allFiles.length === 0) {
      toast.error("Não há ficheiros para renomear");
      return;
    }

    setRenaming(true);
    toast.info("A analisar e renomear documentos com nomes legíveis...");

    try {
      // 1) Categorizar docs ainda sem categoria (necessário para gerar nomes inteligentes)
      try {
        await categorizeAllS3Documents(processId);
      } catch (catErr) {
        console.warn("Categorização prévia falhou (a tentar renomear na mesma):", catErr);
      }

      // 2) Renomear com nomes inteligentes baseados na categoria IA
      let result;
      try {
        ({ data: result } = await renameAllS3DocumentsSmart(processId));
      } catch (erroRename) {
        const detalhe = erroRename?.response?.data?.detail;
        if (typeof detalhe === "string" && detalhe.includes("categorizado")) {
          toast.warning("Execute primeiro a análise IA para categorizar os documentos");
        } else {
          toast.error(extractErrorMessage(detalhe, "Erro ao renomear documentos"));
        }
        return;
      }

      {
        if (result.renamed > 0) {
          toast.success(`${result.renamed} documento(s) renomeado(s) com sucesso!`);
          // Recarregar ficheiros para mostrar novos nomes
          fetchFiles();
        } else if (result.skipped > 0 && result.renamed === 0) {
          toast.info("Todos os documentos já têm nomes correctos ou não estão categorizados");
        } else if ((result.total || 0) === 0) {
          toast.warning("Nenhum documento categorizado para renomear. Tente Analisar IA primeiro.");
        }
        
        // Mostrar diálogo com detalhes se houver resultados
        if (result.details && result.details.length > 0) {
          setRenameDialog({ open: true, results: result });
        }
      }
    } catch (error) {
      console.error("Erro ao renomear documentos:", error);
      toast.error("Erro ao renomear documentos");
    } finally {
      setRenaming(false);
    }
  };

  // Abrir diálogo de renomeação manual
  const openManualRename = (file) => {
    // Extrair nome sem extensão para facilitar edição
    const filename = file.name || file.path?.split('/').pop() || "";
    const lastDot = filename.lastIndexOf('.');
    const nameWithoutExt = lastDot > 0 ? filename.substring(0, lastDot) : filename;
    
    setManualRenameDialog({
      open: true,
      file: file,
      newName: nameWithoutExt
    });
  };

  // Renomear ficheiro individual manualmente
  const handleManualRename = async () => {
    const { file, newName } = manualRenameDialog;
    
    if (!file || !newName.trim()) {
      toast.error("Nome inválido");
      return;
    }

    setManualRenaming(true);
    
    try {
      const { data: result } = await renameS3DocumentSmart(processId, {
        s3_path: file.path,
        apply_ai_name: false,
        novo_nome: newName.trim(),
      });
      toast.success(`Ficheiro renomeado para "${result.new_name}"`);
      setManualRenameDialog({ open: false, file: null, newName: "" });
      fetchFiles(); // Recarregar lista
    } catch (error) {
      console.error("Erro ao renomear ficheiro:", error);
      toast.error(
        extractErrorMessage(
          error?.response?.data?.detail,
          "Erro ao renomear ficheiro",
        ),
      );
    } finally {
      setManualRenaming(false);
    }
  };

  // Organização rápida de documentos
  const handleQuickOrganize = async () => {
    const allFiles = getAllFiles();
    
    if (allFiles.length === 0) {
      toast.error("Não há ficheiros para organizar");
      return;
    }

    setOrganizing(true);
    setOrganizeResults(null);
    toast.info(`A organizar ${allFiles.length} documento(s)...`);

    try {
      // Passo 1: Analisar documentos com IA
      const formData = new FormData();
      
      for (const file of allFiles) {
        try {
          const { data: blob } = await getS3FileContent(file.path);
          formData.append('files', blob, file.name);
        } catch (e) {
          console.error(`Erro ao obter ficheiro ${file.name}:`, e);
        }
      }

      // Análise IA
      let analyzeResult;
      try {
        ({ data: analyzeResult } = await aiAnalyzeS3Documents(processId, formData));
      } catch (erroAnalise) {
        throw new Error(
          extractErrorMessage(
            erroAnalise?.response?.data?.detail,
            "Erro na análise IA",
          ),
        );
      }

      // Passo 2: Organizar documentos nas pastas
      // Juntar source_path dos ficheiros originais com resultados da IA
      const docsToOrganize = (analyzeResult.documents || []).map(doc => {
        const originalFile = allFiles.find(f => f.name === doc.file_name);
        return {
          ...doc,
          source_path: originalFile?.path || null
        };
      }).filter(doc => doc.source_path);

      let organizeResult;
      try {
        ({ data: organizeResult } = await organizeS3Documents(processId, {
          documents: docsToOrganize,
          create_folders: true,
        }));
      } catch (erroOrganize) {
        throw new Error(
          extractErrorMessage(
            erroOrganize?.response?.data?.detail,
            "Erro ao organizar documentos",
          ),
        );
      }

      {
        setOrganizeResults({
          analyzed: analyzeResult.documents_count || allFiles.length,
          organized: organizeResult.organized_count || organizeResult.organized?.length || 0,
          categories: analyzeResult.categories_found || [],
          details: organizeResult.organized || []
        });

        toast.success(`Organização completa! ${organizeResult.organized_count || 0} documento(s) organizado(s).`);
        fetchFiles(); // Recarregar lista
      }

    } catch (error) {
      console.error("Erro na organização:", error);
      toast.error(error.message || "Erro ao organizar documentos");
    } finally {
      setOrganizing(false);
    }
  };

  // Drag and Drop handlers
  const handleDragStart = (e, file) => {
    // Se o ficheiro arrastado está entre os selecionados, arrastar todos os selecionados
    // Caso contrário, arrastar apenas este ficheiro
    const isSelected = selectedFilesForAI.some(f => f.path === file.path);
    
    if (isSelected && selectedFilesForAI.length > 1) {
      // Arrastar múltiplos ficheiros selecionados
      setDraggedFiles(selectedFilesForAI);
      setDraggedFile(null);
      e.dataTransfer.setData("text/plain", `${selectedFilesForAI.length} ficheiros`);
    } else {
      // Arrastar apenas este ficheiro
      setDraggedFile(file);
      setDraggedFiles([]);
      e.dataTransfer.setData("text/plain", file.path);
    }
    
    e.dataTransfer.effectAllowed = "move";
  };

  const handleDragEnd = () => {
    setDraggedFile(null);
    setDraggedFiles([]);
    setDropTarget(null);
    setDragCounter(0);
  };

  const handleDragOver = (e, category) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    setDropTarget(category);
  };

  const handleDragEnter = (e, category) => {
    e.preventDefault();
    setDragCounter(prev => prev + 1);
    setDropTarget(category);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setDragCounter(prev => prev - 1);
    // Só limpar o dropTarget quando sairmos completamente
    if (dragCounter <= 1) {
      setDropTarget(null);
    }
  };

  // Função para verificar conflitos antes de mover
  const checkMoveConflicts = async (filesToMove, targetCategory) => {
    const conflicts = [];
    
    for (const file of filesToMove) {
      try {
        const { data } = await checkS3MoveConflict({
          process_id: processId,
          source_path: file.path,
          target_category: targetCategory,
        });
        if (data.has_conflict) {
          conflicts.push({
            file,
            conflictPath: data.conflict_path,
            conflictFilename: data.conflict_filename,
            suggestedNames: data.suggested_names,
          });
        }
      } catch (err) {
        console.error(`Erro ao verificar conflito para ${file.name}:`, err);
      }
    }
    
    return conflicts;
  };

  // Função para mover um ficheiro com opções de conflito
  const moveFileWithConflictHandling = async (file, targetCategory, action = 'rename', customName = null) => {
    const body = {
      source_path: file.path,
      target_category: targetCategory
    };
    
    if (action === 'overwrite') {
      body.overwrite = true;
    } else if (action === 'rename') {
      body.auto_rename = true;
    } else if (action === 'custom' && customName) {
      body.target_filename = customName;
      body.auto_rename = true;
    }
    
    try {
      const { data } = await moveS3File(processId, body);
      return data;
    } catch (error) {
      const detalhe = error?.response?.data?.detail;
      throw new Error(detalhe?.message || detalhe || 'Erro ao mover ficheiro');
    }
  };

  const handleDrop = async (e, targetCategory) => {
    e.preventDefault();
    setDropTarget(null);
    setDragCounter(0);
    
    // Determinar quais ficheiros mover
    const filesToMove = draggedFiles.length > 0 ? draggedFiles : (draggedFile ? [draggedFile] : []);
    
    if (filesToMove.length === 0) return;
    
    // Filtrar ficheiros que já estão na categoria destino
    const filesToActuallyMove = filesToMove.filter(file => {
      const currentCategory = file.category || "Outros";
      return currentCategory !== targetCategory;
    });
    
    if (filesToActuallyMove.length === 0) {
      toast.info(filesToMove.length === 1 
        ? "Ficheiro já está nesta categoria" 
        : "Todos os ficheiros já estão nesta categoria");
      setDraggedFile(null);
      setDraggedFiles([]);
      return;
    }

    setMoving(true);
    toast.info(`A verificar conflitos...`);

    try {
      // Verificar conflitos antes de mover
      const conflicts = await checkMoveConflicts(filesToActuallyMove, targetCategory);
      
      if (conflicts.length > 0) {
        // Existem conflitos - mostrar diálogo de confirmação
        setConflictDialog({
          open: true,
          files: filesToActuallyMove,
          targetCategory,
          currentIndex: 0,
          conflicts,
          totalFiles: filesToActuallyMove.length
        });
        setMoving(false);
        return;
      }
      
      // Sem conflitos - mover diretamente
      await executeMoveFiles(filesToActuallyMove, targetCategory);
      
    } catch (error) {
      console.error("Erro ao mover ficheiros:", error);
      toast.error("Erro ao mover ficheiros");
      setMoving(false);
    }
  };

  // Função para executar a movimentação dos ficheiros
  const executeMoveFiles = async (filesToMove, targetCategory, conflictAction = 'rename') => {
    setMoving(true);
    let successCount = 0;
    let errorCount = 0;

    try {
      for (const file of filesToMove) {
        try {
          await moveFileWithConflictHandling(file, targetCategory, conflictAction);
          successCount++;
        } catch (err) {
          errorCount++;
          console.error(`Erro ao mover ${file.name}:`, err);
        }
      }

      // Mostrar resultado
      if (successCount > 0) {
        toast.success(`${successCount} ficheiro${successCount > 1 ? 's' : ''} movido${successCount > 1 ? 's' : ''} para ${targetCategory}`);
        fetchFiles(); // Recarregar lista
        setSelectedFilesForAI([]); // Limpar seleção
      }
      
      if (errorCount > 0) {
        toast.error(`${errorCount} ficheiro${errorCount > 1 ? 's' : ''} não foram movidos`);
      }
    } catch (error) {
      console.error("Erro ao mover ficheiros:", error);
      toast.error("Erro ao mover ficheiros");
    } finally {
      setMoving(false);
      setDraggedFile(null);
      setDraggedFiles([]);
    }
  };

  // Função para lidar com a decisão do utilizador no diálogo de conflito
  const handleConflictDecision = async (decision, customName = null) => {
    const { files, targetCategory, currentIndex, conflicts } = conflictDialog;
    const currentConflict = conflicts.find(c => c.file === files[currentIndex]);
    
    if (decision === 'skip') {
      // Pular este ficheiro
      if (currentIndex < files.length - 1) {
        setConflictDialog(prev => ({ ...prev, currentIndex: currentIndex + 1 }));
        return;
      }
    } else {
      // Mover o ficheiro atual com a decisão tomada
      try {
        if (currentConflict) {
          await moveFileWithConflictHandling(
            currentConflict.file, 
            targetCategory, 
            decision,
            customName
          );
          toast.success(`${currentConflict.file.name} movido com sucesso`);
        }
      } catch (err) {
        toast.error(`Erro ao mover ${currentConflict?.file?.name || 'ficheiro'}: ${err.message}`);
      }
    }
    
    // Passar ao próximo ficheiro ou fechar diálogo
    if (currentIndex < files.length - 1) {
      // Verificar se há mais conflitos
      const nextFiles = files.slice(currentIndex + 1);
      const remainingConflicts = conflicts.filter(c => nextFiles.includes(c.file));
      
      if (remainingConflicts.length > 0) {
        setConflictDialog(prev => ({ 
          ...prev, 
          currentIndex: currentIndex + 1,
          conflicts: remainingConflicts
        }));
        return;
      } else {
        // Mover os restantes sem conflito
        await executeMoveFiles(nextFiles, targetCategory);
      }
    }
    
    // Fechar diálogo e limpar
    setConflictDialog({ open: false, files: [], targetCategory: null, currentIndex: 0, conflicts: [] });
    setDraggedFile(null);
    setDraggedFiles([]);
    fetchFiles();
  };

  // Função para aplicar decisão a todos os conflitos restantes
  const handleConflictDecisionForAll = async (decision) => {
    const { files, targetCategory, currentIndex } = conflictDialog;
    const remainingFiles = files.slice(currentIndex);
    
    setConflictDialog(prev => ({ ...prev, open: false }));
    
    // Mover todos os ficheiros restantes com a ação escolhida
    await executeMoveFiles(remainingFiles, targetCategory, decision);
    
    setDraggedFile(null);
    setDraggedFiles([]);
  };

  if (loading) {
    return (
      <Card data-testid="s3-file-manager">
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  // PACOTE 11 (Eixo 3 — Privacy Warning localizado): o backend respondeu
  // 403 ao carregar os ficheiros (guard `assert_can_view_process_documents`
  // — processo não indexado visível apenas a indexação/admin/utilizadores
  // atribuídos). O aviso vive DENTRO da tab Documentos (este componente só
  // é renderizado aqui) — a restante vista do processo permanece acessível.
  if (permissionDenied) {
    return (
      <Card data-testid="s3-file-manager-permission-denied" className="border-amber-200 dark:border-amber-800">
        <CardContent className="py-10 flex flex-col items-center justify-center text-center">
          <div className="p-4 bg-amber-100 dark:bg-amber-900/40 rounded-full mb-4">
            <ShieldAlert className="h-8 w-8 text-amber-600 dark:text-amber-400" aria-hidden="true" />
          </div>
          <h3 className="text-lg font-semibold text-amber-800 dark:text-amber-200">
            Documentos não disponíveis
          </h3>
          <p className="text-sm text-muted-foreground max-w-md mt-2 leading-relaxed">
            Não tem permissão para ver os documentos deste processo. Os documentos de
            processos ainda não indexados são visíveis apenas para a equipa de indexação,
            administração e utilizadores atribuídos ao processo.
          </p>
          <p className="text-xs text-muted-foreground/70 mt-3">
            Os restantes separadores do processo (Resumo, Histórico, Tarefas) continuam
            disponíveis. Contacte o administrador se precisar de acesso à documentação.
          </p>
          <Button
            variant="outline"
            size="sm"
            className="mt-5 gap-2"
            onClick={() => {
              setLoading(true);
              fetchFiles();
            }}
          >
            <RefreshCw className="h-4 w-4" />
            Tentar novamente
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card data-testid="s3-file-manager" className="h-full">
        {/* Mapeamento S3 (apenas para admin) */}
        {canMapS3 && (
          <div className="border-b">
            <button
              className="w-full px-4 py-2 flex items-center justify-between text-sm hover:bg-muted/50 transition-colors"
              onClick={() => {
                setS3MappingOpen(!s3MappingOpen);
                if (!s3MappingOpen && s3Folders.length === 0) {
                  loadS3MappingData();
                }
              }}
              data-testid="s3-mapping-toggle"
            >
              <div className="flex items-center gap-2">
                <Settings2 className="h-4 w-4 text-muted-foreground" />
                <span className="font-medium">Mapeamento S3</span>
                {currentS3Mapping && (
                  <span className="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded">
                    {currentS3Mapping.split('/').pop()}
                  </span>
                )}
              </div>
              {s3MappingOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
            
            {s3MappingOpen && (
              <div className="px-4 pb-4 pt-2 border-t bg-muted/30">
                <div className="space-y-3">
                  <div className="text-xs text-muted-foreground">
                    Associe este cliente/processo a uma pasta específica no S3 para organizar os documentos.
                  </div>
                  
                  {loadingS3Folders ? (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      A carregar pastas...
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <Select value={selectedS3Folder || "__none__"} onValueChange={(val) => setSelectedS3Folder(val === "__none__" ? "" : val)}>
                        <SelectTrigger className="flex-1" data-testid="s3-folder-select">
                          <SelectValue placeholder="Seleccione uma pasta S3..." />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__none__">-- Sem mapeamento --</SelectItem>
                          {s3Folders.map((folder) => (
                            <SelectItem key={folder.path} value={folder.path}>
                              {folder.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Button
                        size="sm"
                        onClick={saveS3Mapping}
                        disabled={savingS3Mapping || selectedS3Folder === currentS3Mapping}
                        data-testid="save-s3-mapping-btn"
                      >
                        {savingS3Mapping ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Save className="h-4 w-4" />
                        )}
                      </Button>
                    </div>
                  )}
                  
                  {currentS3Mapping && (
                    <div className="flex items-center gap-2 text-xs">
                      <Link className="h-3 w-3 text-green-600" />
                      <span className="text-green-700 dark:text-green-400">
                        Mapeado para: <strong>{currentS3Mapping}</strong>
                      </span>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
        
        <CardHeader className="pb-3">
          <div className="flex flex-col gap-3">
            {/* Linha 1: Título e contador */}
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Cloud className="h-5 w-5 text-blue-500" />
                  Documentos
                </CardTitle>
                <CardDescription>
                  {stats ? (
                    <span>{stats.total_files} ficheiros ({stats.total_size_formatted})</span>
                  ) : (
                    <span>Gestão de documentos do cliente</span>
                  )}
                </CardDescription>
              </div>
              {/* Botão refresh no canto */}
              <Button
                variant="ghost"
                size="sm"
                onClick={fetchFiles}
                disabled={loading}
                data-testid="refresh-files-btn"
                className="h-8 w-8 p-0"
              >
                <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              </Button>
            </div>
            
            {/* Linha 2: Botões de acção */}
            <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setTemplateError(null);
                  setSelectedTemplate("");
                  setTemplateDialog({ open: true });
                }}
                data-testid="generate-template-btn"
                className="bg-emerald-50 hover:bg-emerald-100 border-emerald-200 dark:bg-emerald-950/50 dark:border-emerald-800 dark:hover:bg-emerald-900/50 whitespace-nowrap h-8 px-2 sm:px-3"
              >
                <FileDown className="h-3.5 w-3.5 text-emerald-600 sm:mr-1" />
                <span className="hidden sm:inline">Gerar</span> Minuta
              </Button>
              {/* INDEXAÇÃO READ-ONLY: Ocultar botão de upload */}
              {!isIndexacao && (
                <Button
                  size="sm"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading}
                  data-testid="upload-file-btn"
                  className="whitespace-nowrap h-8 px-2 sm:px-3"
                >
                  {uploading ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin sm:mr-1" />
                  ) : (
                    <Upload className="h-3.5 w-3.5 sm:mr-1" />
                  )}
                  <span className="hidden xs:inline">Upload</span>
                </Button>
              )}
              {/* Analisar / Renomear IA — apenas admin, CEO, diretor (gestão) */}
              {canUseAIDocumentTools && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleAIAnalysis}
                  disabled={aiAnalyzing || getAllFiles().length === 0}
                  data-testid="ai-analyze-btn"
                  className="bg-purple-50 hover:bg-purple-100 border-purple-200 dark:bg-purple-950/50 dark:border-purple-800 dark:hover:bg-purple-900/50 whitespace-nowrap h-8 px-2 sm:px-3"
                >
                  {aiAnalyzing ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-purple-600 sm:mr-1" />
                  ) : (
                    <Brain className="h-3.5 w-3.5 text-purple-600 sm:mr-1" />
                  )}
                  {/* PACOTE DJ — Sistema Híbrido. Botão global de análise em lote. */}
                  <span className="hidden sm:inline">🧠 Analisar Documentos</span>
                  <span className="sm:hidden">🧠 Analisar</span>
                </Button>
              )}
              {canUseAIDocumentTools && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleSmartRename}
                  disabled={renaming || getAllFiles().length === 0}
                  data-testid="smart-rename-btn"
                  title="Analisar e renomear documentos com nomes legíveis baseados na IA"
                  className="bg-amber-50 hover:bg-amber-100 border-amber-200 dark:bg-amber-950/50 dark:border-amber-800 dark:hover:bg-amber-900/50 whitespace-nowrap h-8 px-2 sm:px-3"
                >
                  {renaming ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-amber-600 sm:mr-1" />
                  ) : (
                    <Sparkles className="h-3.5 w-3.5 text-amber-600 sm:mr-1" />
                  )}
                  <span className="hidden md:inline">Renomear</span> IA
                </Button>
              )}
              {/* PACOTE DB — Botão "Organizar" temporariamente oculto (display: none).
                  Mantido para reativação futura — não apagar. */}
              <Button
                size="sm"
                variant="outline"
                onClick={handleQuickOrganize}
                disabled={organizing || aiAnalyzing || getAllFiles().length === 0}
                data-testid="quick-organize-btn"
                title="Analisar e organizar documentos automaticamente nas pastas corretas"
                className="bg-teal-50 hover:bg-teal-100 border-teal-200 dark:bg-teal-950/50 dark:border-teal-800 dark:hover:bg-teal-900/50 whitespace-nowrap h-8 px-2 sm:px-3"
                style={{ display: 'none' }}
              >
                {organizing ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-teal-600 sm:mr-1" />
                ) : (
                  <FolderSync className="h-3.5 w-3.5 text-teal-600 sm:mr-1" />
                )}
                <span className="hidden sm:inline">Organizar</span>
              </Button>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                onChange={handleUpload}
                className="hidden"
                accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png,.gif,.webp"
              />
            </div>
          </div>

          {/* Barra de progresso do upload */}
          {uploading && (
            <div className="mt-3">
              <Progress value={uploadProgress} className="h-2" />
              <p className="text-xs text-muted-foreground mt-1">
                A enviar... {Math.round(uploadProgress)}%
              </p>
            </div>
          )}

          {/* Pesquisa de ficheiros, toggle de vista e ordenação */}
          <div className="mt-3 flex flex-col sm:flex-row gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                type="text"
                placeholder="Pesquisar documentos..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9 h-9 text-sm"
                data-testid="search-documents-input"
              />
              {searchQuery && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="absolute right-1 top-1/2 transform -translate-y-1/2 h-7 w-7 p-0"
                  onClick={() => setSearchQuery("")}
                >
                  <X className="h-3 w-3" />
                </Button>
              )}
            </div>
            {/* Toggle de vista e ordenação */}
            <div className="flex gap-1 justify-end items-center">
              {/* Toggle Lista/Grelha */}
              <div className="flex border rounded-md p-0.5 mr-1">
                <Button
                  variant={viewMode === "list" ? "secondary" : "ghost"}
                  size="sm"
                  onClick={() => setViewMode("list")}
                  className="h-7 w-7 p-0"
                  title="Vista de lista"
                  data-testid="view-list-btn"
                >
                  <List className="h-4 w-4" />
                </Button>
                <Button
                  variant={viewMode === "grid" ? "secondary" : "ghost"}
                  size="sm"
                  onClick={() => setViewMode("grid")}
                  className="h-7 w-7 p-0"
                  title="Vista de grelha"
                  data-testid="view-grid-btn"
                >
                  <LayoutGrid className="h-4 w-4" />
                </Button>
              </div>
              {/* Botões de ordenação - apenas na vista de lista */}
              {viewMode === "list" && (
                <>
                  <Button
                    variant={sortBy === "date" ? "secondary" : "ghost"}
                    size="sm"
                    onClick={() => toggleSort("date")}
                    className="h-7 px-2 text-xs"
                    title="Ordenar por data"
                  >
                    {sortBy === "date" && sortOrder === "desc" ? <ChevronDown className="h-3 w-3 mr-0.5" /> : sortBy === "date" ? <ChevronUp className="h-3 w-3 mr-0.5" /> : null}
                    Data
                  </Button>
                  <Button
                    variant={sortBy === "name" ? "secondary" : "ghost"}
                    size="sm"
                    onClick={() => toggleSort("name")}
                    className="h-7 px-2 text-xs"
                    title="Ordenar por nome"
                  >
                    {sortBy === "name" && sortOrder === "desc" ? <ChevronDown className="h-3 w-3 mr-0.5" /> : sortBy === "name" ? <ChevronUp className="h-3 w-3 mr-0.5" /> : null}
                    Nome
                  </Button>
                </>
              )}
            </div>
          </div>
        </CardHeader>

        <CardContent className="pt-0">
          {/* ========================================= */}
          {/* VISTA DE LISTA - Explorador de Ficheiros */}
          {/* ========================================= */}
          {viewMode === "list" && (
            <div className="flex flex-col sm:flex-row gap-2 mt-3 h-[300px] sm:h-[450px]">
              {/* Sidebar - Categorias (apenas ícones) */}
              <div className="w-10 flex-shrink-0 border rounded-lg overflow-hidden flex flex-col">
                <div className="bg-muted/50 px-1 py-1.5 text-[10px] font-medium border-b flex items-center justify-center">
                  <HardDrive className="h-3.5 w-3.5" />
                </div>
                <ScrollArea className="flex-1">
                  {/* Pasta "Todos" */}
                  <button
                    onClick={() => setSelectedCategory(null)}
                    className={`w-full px-1 py-2 text-xs flex items-center justify-center hover:bg-accent/50 transition-colors ${!selectedCategory ? "bg-accent" : ""}`}
                    data-testid="folder-all"
                    title={`Todos (${stats?.total_files || 0})`}
                  >
                    <FolderOpen className={`h-4 w-4 ${!selectedCategory ? "text-blue-600" : "text-blue-500"}`} />
                  </button>
                  
                  {/* Pastas por Categoria - apenas ícones */}
                  {visibleCategories.map((cat) => {
                    const Icon = cat.icon;
                    const count = getCategoryCount(cat.id);
                    const colorMap = {
                      blue: "text-blue-500",
                      green: "text-green-500",
                      purple: "text-purple-500",
                      orange: "text-orange-500",
                      gray: "text-gray-500",
                      teal: "text-teal-500",
                    };
                    const isDropTarget = dropTarget === cat.id;
                    const isDraggingMultiple = draggedFiles.length > 1;
                    return (
                      <div
                        key={cat.id}
                        onDragOver={(e) => handleDragOver(e, cat.id)}
                        onDragEnter={(e) => handleDragEnter(e, cat.id)}
                        onDragLeave={(e) => handleDragLeave(e, cat.id)}
                        onDrop={(e) => handleDrop(e, cat.id)}
                        className={`relative ${isDropTarget ? "ring-2 ring-teal-500 ring-inset bg-teal-50 dark:bg-teal-950/30 rounded" : ""}`}
                      >
                        <button
                          onClick={() => setSelectedCategory(cat.id)}
                          className={`w-full px-1 py-2 text-xs flex items-center justify-center hover:bg-accent/50 transition-colors ${selectedCategory === cat.id ? "bg-accent" : ""}`}
                          data-testid={`folder-${cat.id.toLowerCase().replace(/\s/g, '-')}`}
                          title={`${cat.label} (${count}) - Arraste ficheiros para mover`}
                        >
                          <Icon className={`h-4 w-4 ${isDropTarget ? "text-teal-600" : selectedCategory === cat.id ? "text-primary font-bold" : colorMap[cat.color] || "text-gray-500"}`} />
                        </button>
                        {isDropTarget && (
                          <div className="absolute inset-0 flex items-center justify-center pointer-events-none bg-teal-100/80 dark:bg-teal-900/80 rounded">
                            <div className="flex flex-col items-center">
                              {isDraggingMultiple ? (
                                <>
                                  <span className="text-[10px] text-teal-700 dark:text-teal-300 font-bold">{draggedFiles.length}</span>
                                  <span className="text-[8px] text-teal-600 dark:text-teal-400">soltar</span>
                                </>
                              ) : (
                                <span className="text-[8px] text-teal-600 dark:text-teal-400 font-medium">soltar</span>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </ScrollArea>
              </div>

              {/* Área Principal - Tabela de Ficheiros */}
              <div className={`${previewFile ? 'flex-1' : 'flex-1'} border rounded-lg overflow-hidden flex flex-col min-w-0`}>
                {/* Header da tabela - clicável para ordenar */}
                <div className="grid grid-cols-[28px_1fr_90px_100px_70px] gap-2 bg-muted/50 px-2 py-1.5 text-[10px] font-medium text-muted-foreground border-b items-center">
                  <div className="w-7 flex justify-center">
                    <button
                      onClick={() => toggleSelectAll(getDisplayFiles())}
                      className="hover:bg-accent rounded p-0.5"
                      title={selectedFilesForAI.length === getDisplayFiles().length && getDisplayFiles().length > 0 ? "Desselecionar todos" : "Selecionar todos"}
                    >
                      {selectedFilesForAI.length === getDisplayFiles().length && getDisplayFiles().length > 0 ? (
                        <CheckSquare className="h-3.5 w-3.5 text-blue-600" />
                      ) : (
                        <Square className="h-3.5 w-3.5" />
                      )}
                    </button>
                  </div>
                  <button 
                    onClick={() => toggleSort("name")} 
                    className="flex items-center gap-1 hover:text-foreground text-left"
                  >
                    Nome 
                    {sortBy === "name" && (
                      sortOrder === "asc" ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />
                    )}
                  </button>
                  <button 
                    onClick={() => toggleSort("category")} 
                    className="text-left"
                  >
                    Cat.
                    {sortBy === "category" && (
                      sortOrder === "asc" ? <ChevronUp className="h-2.5 w-2.5 inline ml-0.5" /> : <ChevronDown className="h-2.5 w-2.5 inline ml-0.5" />
                    )}
                  </button>
                  <button 
                    onClick={() => toggleSort("date")} 
                    className="text-left"
                  >
                    Data
                    {sortBy === "date" && (
                      sortOrder === "asc" ? <ChevronUp className="h-2.5 w-2.5 inline ml-0.5" /> : <ChevronDown className="h-2.5 w-2.5 inline ml-0.5" />
                    )}
                  </button>
                  <div className="text-center">Ações</div>
                </div>

                {/* Linhas dos ficheiros */}
                <ScrollArea className="flex-1">
                  {getDisplayFiles().length > 0 ? (
                    getDisplayFiles().map((file, idx) => {
                      const isSelected = selectedFilesForAI.some(f => f.path === file.path);
                      const isPreviewing = previewFile?.path === file.path;
                      const isDragging = draggedFile?.path === file.path || draggedFiles.some(f => f.path === file.path);
                      const isMultiDrag = draggedFiles.length > 1 && isSelected;
                      const isFolder = file.path?.endsWith('/');
                      return (
                        <div
                          key={`${file.path}-${idx}`}
                          draggable
                          onDragStart={(e) => handleDragStart(e, file)}
                          onDragEnd={handleDragEnd}
                          className={`grid grid-cols-[28px_1fr_80px_90px_auto] gap-2 px-2 py-1.5 text-xs items-center hover:bg-accent/50 cursor-pointer border-b last:border-b-0 transition-colors select-none ${isSelected ? "bg-blue-50 dark:bg-blue-950/30" : ""} ${isPreviewing ? "bg-accent" : ""} ${isDragging ? "opacity-40 bg-teal-50 dark:bg-teal-950/50 ring-1 ring-teal-400 ring-inset" : ""}`}
                          onClick={() => { toggleFileSelection(file); handlePreview(file); }}
                          data-testid={`file-row-${idx}`}
                        >
                          {/* Checkbox / Drag handle */}
                          <div className="w-7 flex justify-center cursor-grab active:cursor-grabbing relative">
                            {isMultiDrag ? (
                              <div className="relative">
                                <CheckSquare className="h-3.5 w-3.5 text-teal-600" />
                                <span className="absolute -top-1 -right-1 bg-teal-500 text-white text-[8px] rounded-full w-3 h-3 flex items-center justify-center font-bold">
                                  {draggedFiles.length}
                                </span>
                              </div>
                            ) : isSelected ? (
                              <CheckSquare className="h-3.5 w-3.5 text-blue-600" />
                            ) : (
                              <Square className="h-3.5 w-3.5 text-muted-foreground" />
                            )}
                          </div>

                          {/* Nome + Ícone */}
                          <div className="flex items-center gap-2 min-w-0">
                            <FileIcon filename={file.name} />
                            <span 
                              className="truncate font-medium"
                              title={file.name}
                            >
                              {file.name}
                            </span>
                            {/* PACOTE DJ — Sistema Híbrido. Badges de estado de revisão IA.
                                Estados: auto_approved (≥85% confiança, IA auto-aplicou),
                                pending_review (<85%, à espera de revisão humana),
                                approved/rejected/edited (decisão humana já registada). */}
                            {analyzingDocIds.has(file.doc_id || file.id) && (
                              <Badge
                                variant="outline"
                                className="text-[9px] py-0 h-4 px-1 bg-primary/10 text-primary border-primary/20 shrink-0"
                                title="A análise IA está em curso..."
                              >
                                <Loader2 className="h-2.5 w-2.5 mr-0.5 animate-spin" />
                                A analisar...
                              </Badge>
                            )}
                            {file.ai_review_status === "auto_approved" && (
                              <Badge
                                variant="secondary"
                                className="text-[9px] py-0 h-4 px-1 bg-primary/10 text-primary border-primary/20 shrink-0"
                                title="Confiança ≥85% — sugestões IA aplicadas automaticamente"
                              >
                                <Sparkles className="h-2.5 w-2.5 mr-0.5" />
                                ✨ Auto-Aprovado
                              </Badge>
                            )}
                            {file.ai_review_status === "pending_review" && (
                              <Badge
                                variant="outline"
                                className="text-[9px] py-0 h-4 px-1 bg-accent/15 text-accent-foreground border-accent/30 shrink-0 cursor-pointer"
                                title="Confiança <85% — clique para rever as sugestões da IA"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleOpenReviewModal(file);
                                }}
                              >
                                <AlertTriangle className="h-2.5 w-2.5 mr-0.5" />
                                ⚠️ Revisão Necessária
                              </Badge>
                            )}
                            {file.ai_review_status === "approved" && (
                              <Badge
                                variant="secondary"
                                className="text-[9px] py-0 h-4 px-1 shrink-0"
                                title="Sugestões IA aprovadas"
                              >
                                <CheckCircle2 className="h-2.5 w-2.5 mr-0.5" />
                                Aprovado
                              </Badge>
                            )}
                            {file.ai_review_status === "rejected" && (
                              <Badge
                                variant="outline"
                                className="text-[9px] py-0 h-4 px-1 text-muted-foreground shrink-0"
                                title="Sugestões IA rejeitadas"
                              >
                                Rejeitado
                              </Badge>
                            )}
                            {file.ai_review_status === "edited" && (
                              <Badge
                                variant="outline"
                                className="text-[9px] py-0 h-4 px-1 bg-primary/15 text-primary border-primary/30 shrink-0"
                                title="Sugestões IA aplicadas com edições manuais"
                              >
                                <Pencil className="h-2.5 w-2.5 mr-0.5" />
                                Editado
                              </Badge>
                            )}
                            {file.ai_analyzed && (
                              <Badge
                                variant="outline"
                                className="text-[9px] py-0 h-4 px-1 bg-purple-50 text-purple-700 border-purple-200 shrink-0"
                                title={file.ai_analyzed_at ? `Analisado pela IA em ${file.ai_analyzed_at}` : "Já analisado pela IA"}
                              >
                                <Brain className="h-2.5 w-2.5 mr-0.5" />
                                IA
                              </Badge>
                            )}
                          </div>

                          {/* Categoria */}
                          <Badge variant="outline" className="text-[10px] justify-center py-0 h-4 truncate">
                            {file.category || "Outros"}
                          </Badge>

                          {/* Data - mais pequena */}
                          <span className="text-[10px] text-muted-foreground truncate">
                            {formatDate(file.last_modified)}
                          </span>

                          {/* Ações */}
                          <div className="flex items-center justify-end gap-0.5 min-w-[80px]">
                            {/* PACOTE DJ — Botão "Analisar com IA" (HITL) por documento.
                                Chama o endpoint /ai-analyze-review que persiste sugestões
                                em suggested_* (não aplica) e abre o DocumentReviewModal.
                                Gate: apenas gestão (canUseAIDocumentTools). */}
                            {canUseAIDocumentTools && !isFolder && (
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-5 w-5 flex-shrink-0 text-primary hover:text-primary"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleAnalyzeDocForReview(file);
                                }}
                                disabled={analyzingDocIds.has(file.doc_id || file.id)}
                                title="Analisar com IA"
                                data-testid={`dj-analyze-btn-${idx}`}
                              >
                                {analyzingDocIds.has(file.doc_id || file.id) ? (
                                  <Loader2 className="h-3 w-3 animate-spin" />
                                ) : (
                                  <BrainCircuit className="h-3 w-3" />
                                )}
                              </Button>
                            )}
                            {canUseAIDocumentTools && !isFolder && podeExtrairDados(file?.name) && (
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-5 w-5 flex-shrink-0 text-primary hover:text-primary"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleExtractDocData(file);
                                }}
                                disabled={extractingPaths.has(file.path)}
                                title="Extrair Dados com IA"
                                aria-label={`Extrair dados de ${file.name}`}
                                data-testid={`vlm-extract-btn-${idx}`}
                              >
                                {extractingPaths.has(file.path) ? (
                                  <Loader2 className="h-3 w-3 animate-spin" />
                                ) : (
                                  <ScanText className="h-3 w-3" />
                                )}
                              </Button>
                            )}
                            {isPreviewable(file.name) && (
                              <Button 
                                variant="ghost" 
                                size="icon" 
                                className="h-5 w-5 flex-shrink-0" 
                                onClick={(e) => { e.stopPropagation(); handlePreview(file); }}
                                title="Preview"
                              >
                                <Eye className="h-3 w-3" />
                              </Button>
                            )}
                            {isPdfFile(file.name) && (
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-5 w-5 flex-shrink-0 text-amber-500 hover:text-amber-600"
                                onClick={(e) => { e.stopPropagation(); handleOpenAnnotations(file); }}
                                title="Anotações"
                              >
                                <MessageSquare className="h-3 w-3" />
                              </Button>
                            )}
                            <Button 
                              variant="ghost" 
                              size="icon" 
                              className="h-5 w-5 flex-shrink-0" 
                              onClick={(e) => { e.stopPropagation(); handleDownload(file); }}
                              title="Download"
                              >
                              <Download className="h-3 w-3" />
                            </Button>
                            <Button 
                              variant="ghost" 
                              size="icon" 
                              className="h-5 w-5 flex-shrink-0 text-blue-500 hover:text-blue-600" 
                              onClick={(e) => { e.stopPropagation(); openManualRename(file); }}
                              title="Renomear"
                            >
                              <Pencil className="h-3 w-3" />
                            </Button>
                            {/* INDEXAÇÃO READ-ONLY: Ocultar botão de eliminar; também ocultar para pastas */}
                            {!isIndexacao && !isFolder && (
                              <Button 
                                variant="ghost" 
                                size="icon" 
                                className="h-5 w-5 flex-shrink-0 text-red-500 hover:text-red-600" 
                                onClick={(e) => { e.stopPropagation(); setDeleteDialog({ open: true, file }); }}
                                title="Eliminar"
                              >
                                <Trash2 className="h-3 w-3" />
                              </Button>
                            )}
                          </div>
                        </div>
                      );
                    })
                  ) : (
                    <div className="text-center py-12 text-muted-foreground">
                      <FolderOpen className="h-12 w-12 mx-auto mb-3 opacity-40" />
                      <p className="text-sm font-medium">
                        {searchQuery ? "Nenhum ficheiro encontrado" : "Nenhum ficheiro"}
                      </p>
                      <p className="text-xs mt-1">
                        {searchQuery ? `Pesquisa: "${searchQuery}"` : selectedCategory ? `Categoria vazia` : "Faça upload de documentos"}
                      </p>
                    </div>
                  )}
                </ScrollArea>
                
                {/* Footer com contador de seleção */}
                {selectedFilesForAI.length > 0 && (
                  <div className="bg-blue-50 dark:bg-blue-950/50 px-2 py-1.5 text-[10px] text-blue-700 dark:text-blue-300 flex items-center justify-between border-t">
                    <span>{selectedFilesForAI.length} ficheiro(s) selecionado(s)</span>
                    <div className="flex gap-1">
                      {/* Botão Download em Massa */}
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-5 text-[10px] bg-emerald-50 hover:bg-emerald-100 border-emerald-200 px-2"
                        onClick={async () => {
                          try {
                            const { data: blob } = await bulkDownloadS3Files({
                              document_ids: selectedFilesForAI.map(f => f.path),
                              process_id: processId,
                            });
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = `documentos_${new Date().toISOString().slice(0,10)}.zip`;
                            document.body.appendChild(a);
                            a.click();
                            document.body.removeChild(a);
                            URL.revokeObjectURL(url);
                            toast.success(`${selectedFilesForAI.length} documento(s) descarregado(s)`);
                            setSelectedFilesForAI([]);
                          } catch (error) {
                            console.error("Erro no download em massa:", error);
                            const corpo = await readBlobErrorBody(error);
                            toast.error(
                              extractErrorMessage(corpo.detail, "Erro ao descarregar documentos"),
                            );
                          }
                        }}
                      >
                        <Download className="h-3 w-3 mr-1" />
                        Download
                      </Button>
                      {/* Botão Análise IA — apenas gestão */}
                      {canUseAIDocumentTools && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-5 text-[10px] bg-purple-50 hover:bg-purple-100 border-purple-200 px-2"
                          onClick={handleAIAnalysis}
                          disabled={aiAnalyzing}
                        >
                          {aiAnalyzing ? (
                            <Loader2 className="h-3 w-3 animate-spin mr-1" />
                          ) : (
                            <Brain className="h-3 w-3 mr-1" />
                          )}
                          Analisar
                        </Button>
                      )}
                      {/* Botão Eliminar Selecionados */}
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-5 text-[10px] bg-red-50 hover:bg-red-100 border-red-200 text-red-700 hover:text-red-800 px-2"
                        onClick={() => setBulkDeleteDialog({ open: true })}
                        disabled={bulkDeleting}
                      >
                        <Trash2 className="h-3 w-3 mr-1" />
                        Eliminar
                      </Button>
                    </div>
                  </div>
                )}
              </div>

              {/* Diálogo de confirmação para eliminar selecionados */}
              <BulkDeleteDialog
                open={bulkDeleteDialog.open}
                count={selectedFilesForAI.length}
                deleting={bulkDeleting}
                onOpenChange={(aberto) => setBulkDeleteDialog({ open: aberto })}
                onConfirm={handleBulkDelete}
              />

              {/* Painel de Preview Lateral */}
              {previewFile && (
                <div className="w-80 flex-shrink-0 border rounded-lg overflow-hidden flex flex-col bg-muted/30">
                  {/* Header do Preview - nome visível */}
                  <div className="bg-muted/50 px-2 py-2 border-b">
                    <div className="flex items-center gap-2">
                      <Eye className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
                      <span className="text-xs font-medium truncate flex-1" title={previewFile.name || previewFile.filename}>
                        {previewFile.name || previewFile.filename || "Documento"}
                      </span>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-5 w-5 flex-shrink-0"
                        onClick={closePreview}
                      >
                        <X className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>
                  
                  {/* Área de Preview */}
                  <div className="flex-1 flex items-center justify-center p-2 overflow-hidden">
                    {previewLoading ? (
                      <div className="flex flex-col items-center gap-2 text-muted-foreground">
                        <Loader2 className="h-6 w-6 animate-spin" />
                        <span className="text-xs">A carregar...</span>
                      </div>
                    ) : previewUrl ? (
                      previewFile.name?.toLowerCase().endsWith('.pdf') ? (
                        <iframe
                          src={previewUrl}
                          className="w-full h-full border-0 rounded"
                          title={`Preview de ${previewFile.name}`}
                        />
                      ) : (
                        <img
                          src={previewUrl}
                          alt={previewFile.name}
                          className="max-w-full max-h-full object-contain rounded"
                        />
                      )
                    ) : (
                      <div className="flex flex-col items-center gap-2 text-muted-foreground">
                        <File className="h-10 w-10 opacity-40" />
                        <span className="text-xs">Preview não disponível</span>
                      </div>
                    )}
                  </div>
                  
                  {/* Footer do Preview */}
                  <div className="border-t p-2 space-y-1">
                    <div className="flex items-center justify-between text-[10px]">
                      <span className="text-muted-foreground">Categoria:</span>
                      <Badge variant="outline" className="text-[10px] h-4">
                        {previewFile.category || "Outros"}
                      </Badge>
                    </div>
                    <div className="flex items-center justify-between text-[10px]">
                      <span className="text-muted-foreground">Tamanho:</span>
                      <span>{previewFile.size_formatted}</span>
                    </div>
                    <div className="flex gap-1 mt-2">
                      <Button
                        size="sm"
                        variant="outline"
                        className="flex-1 h-6 text-[10px]"
                        onClick={() => handleDownload(previewFile)}
                      >
                        <Download className="h-3 w-3 mr-1" />
                        Download
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-6 w-6 p-0"
                        onClick={() => window.open(previewUrl, '_blank')}
                        title="Abrir em nova aba"
                      >
                        <ExternalLink className="h-3 w-3" />
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-6 w-6 p-0 text-blue-500 hover:text-blue-600"
                        onClick={() => openManualRename(previewFile)}
                        title="Renomear"
                      >
                        <Pencil className="h-3 w-3" />
                      </Button>
                      {/* INDEXAÇÃO READ-ONLY: Ocultar botão de eliminar; também ocultar para pastas */}
                      {!isIndexacao && !previewFile?.path?.endsWith('/') && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-6 w-6 p-0 text-red-500 hover:text-red-600"
                          onClick={() => setDeleteDialog({ open: true, file: previewFile })}
                          title="Eliminar"
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ========================================= */}
          {/* VISTA DE GRELHA - Cards Horizontais      */}
          {/* ========================================= */}
          {viewMode === "grid" && (
            <Tabs value={activeTab} onValueChange={setActiveTab}>
              <TabsList className="w-full flex flex-wrap h-auto gap-0.5 sm:gap-1 p-1">
                {/* Tab "Todos" primeiro */}
                <TabsTrigger
                  value="all"
                  className="min-w-[40px] sm:min-w-[60px] sm:flex-1 gap-1 text-[10px] sm:text-xs py-1.5 px-1.5 sm:px-2"
                  data-testid="tab-all"
                >
                  <FolderOpen className="h-3 w-3" />
                  <span className="hidden sm:inline">Todos</span>
                  {stats?.total_files > 0 && (
                    <Badge variant="secondary" className="ml-0.5 sm:ml-1 h-4 px-1 text-[10px]">
                      {stats.total_files}
                    </Badge>
                  )}
                </TabsTrigger>
                {visibleCategories.map((cat) => {
                  const Icon = cat.icon;
                  const count = getCategoryCount(cat.id);
                  const isDropTarget = dropTarget === cat.id;
                  const isDraggingMultiple = draggedFiles.length > 1;
                  return (
                    <div
                      key={cat.id}
                      className="relative"
                      onDragOver={(e) => handleDragOver(e, cat.id)}
                      onDragEnter={(e) => handleDragEnter(e, cat.id)}
                      onDragLeave={(e) => handleDragLeave(e, cat.id)}
                      onDrop={(e) => handleDrop(e, cat.id)}
                    >
                      <TabsTrigger
                        value={cat.id}
                        className={`min-w-[40px] sm:min-w-[60px] sm:flex-1 gap-1 text-[10px] sm:text-xs py-1.5 px-1.5 sm:px-2 ${isDropTarget ? "ring-2 ring-teal-500 bg-teal-50 dark:bg-teal-950/50" : ""}`}
                        data-testid={`tab-${cat.id.toLowerCase().replace(/\s/g, '-')}`}
                      >
                        <Icon className="h-3 w-3" />
                        <span className="hidden sm:inline">{cat.label}</span>
                        {count > 0 && (
                          <Badge variant="secondary" className="ml-0.5 sm:ml-1 h-4 px-1 text-[10px]">
                            {count}
                          </Badge>
                        )}
                      </TabsTrigger>
                      {isDropTarget && (
                        <div className="absolute inset-0 flex items-center justify-center pointer-events-none bg-teal-100/90 dark:bg-teal-900/90 rounded-md">
                          <div className="flex flex-col items-center">
                            {isDraggingMultiple ? (
                              <>
                                <span className="text-xs text-teal-700 dark:text-teal-300 font-bold">{draggedFiles.length}</span>
                                <span className="text-[10px] text-teal-600 dark:text-teal-400">soltar aqui</span>
                              </>
                            ) : (
                              <span className="text-[10px] text-teal-600 dark:text-teal-400 font-medium">soltar aqui</span>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </TabsList>

              {/* Tab "Todos" - mostra todos os ficheiros */}
              <TabsContent value="all" className="mt-3">
                {filteredFiles.length > 0 ? (
                  <div className="overflow-x-auto pb-2 -mx-2 px-2">
                    <div className="flex gap-3 min-w-max">
                      {filteredFiles.map((file, idx) => {
                        const isDragging = draggedFile?.path === file.path || draggedFiles.some(f => f.path === file.path);
                        const isFolder = file.path?.endsWith('/');
                        return (
                          <div
                            key={`${file.path}-${idx}`}
                            draggable
                            onDragStart={(e) => handleDragStart(e, file)}
                            onDragEnd={handleDragEnd}
                            className={`flex flex-col w-[140px] sm:w-[180px] md:w-[200px] p-3 rounded-lg border bg-card hover:bg-accent/50 transition-colors group cursor-grab active:cursor-grabbing ${isDragging ? "opacity-40 ring-2 ring-teal-400" : ""}`}
                          >
                            {/* Icon and actions row */}
                            <div className="flex items-center justify-between mb-2">
                              <FileIcon filename={file.name} />
                              <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                                {/* PACOTE DJ — Botão "Analisar com IA" (HITL) por documento (vista grelha - Todos). */}
                                {canUseAIDocumentTools && !isFolder && (
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-6 w-6 text-primary hover:text-primary"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleAnalyzeDocForReview(file);
                                    }}
                                    disabled={analyzingDocIds.has(file.doc_id || file.id)}
                                    title="Analisar com IA"
                                    data-testid={`dj-analyze-btn-all-${idx}`}
                                  >
                                    {analyzingDocIds.has(file.doc_id || file.id) ? (
                                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                    ) : (
                                      <BrainCircuit className="h-3.5 w-3.5" />
                                    )}
                                  </Button>
                                )}
                                {canUseAIDocumentTools && !isFolder && podeExtrairDados(file?.name) && (
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-6 w-6 text-primary hover:text-primary"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleExtractDocData(file);
                                    }}
                                    disabled={extractingPaths.has(file.path)}
                                    title="Extrair Dados com IA"
                                    aria-label={`Extrair dados de ${file.name}`}
                                    data-testid={`vlm-extract-btn-all-${idx}`}
                                  >
                                    {extractingPaths.has(file.path) ? (
                                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                    ) : (
                                      <ScanText className="h-3.5 w-3.5" />
                                    )}
                                  </Button>
                                )}
                                {isPdfFile(file.name) && (
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-6 w-6 text-amber-500 hover:text-amber-600"
                                    onClick={(e) => { e.stopPropagation(); handleOpenAnnotations(file); }}
                                    title="Anotações"
                                  >
                                    <MessageSquare className="h-3.5 w-3.5" />
                                  </Button>
                                )}
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  className="h-6 w-6"
                                  onClick={(e) => { e.stopPropagation(); handleDownload(file); }}
                                  title="Download"
                                >
                                  <Download className="h-3.5 w-3.5" />
                                </Button>
                                {/* INDEXAÇÃO READ-ONLY: Ocultar botão de eliminar; também ocultar para pastas */}
                                {!isIndexacao && !isFolder && (
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-6 w-6 text-red-500 hover:text-red-600"
                                    onClick={(e) => { e.stopPropagation(); setDeleteDialog({ open: true, file }); }}
                                    title="Eliminar"
                                  >
                                    <Trash2 className="h-3.5 w-3.5" />
                                  </Button>
                                )}
                              </div>
                            </div>
                            {/* Clickable file name - duas linhas com letra pequena */}
                            <button
                              onClick={(e) => { e.stopPropagation(); handleDownload(file); }}
                              className="text-left text-[10px] sm:text-xs font-medium line-clamp-2 hover:text-blue-600 hover:underline cursor-pointer mb-1 min-h-[2rem] leading-tight"
                              title={`Clique para descarregar: ${file.name}`}
                            >
                              {file.name}
                            </button>
                            {/* Meta info */}
                            <div className="flex flex-wrap items-center gap-1">
                              <Badge variant="outline" className="text-[10px] py-0 h-4">
                                {file.category}
                              </Badge>
                              {/* PACOTE DJ — Sistema Híbrido. Badges de estado de revisão IA (grelha - Todos). */}
                              {analyzingDocIds.has(file.doc_id || file.id) && (
                                <Badge
                                  variant="outline"
                                  className="text-[9px] py-0 h-4 px-1 bg-primary/10 text-primary border-primary/20"
                                  title="A análise IA está em curso..."
                                >
                                  <Loader2 className="h-2.5 w-2.5 mr-0.5 animate-spin" />
                                  A analisar...
                                </Badge>
                              )}
                              {file.ai_review_status === "auto_approved" && (
                                <Badge
                                  variant="secondary"
                                  className="text-[9px] py-0 h-4 px-1 bg-primary/10 text-primary border-primary/20"
                                  title="Confiança ≥85% — sugestões IA aplicadas automaticamente"
                                >
                                  <Sparkles className="h-2.5 w-2.5 mr-0.5" />
                                  ✨ Auto-Aprovado
                                </Badge>
                              )}
                              {file.ai_review_status === "pending_review" && (
                                <Badge
                                  variant="outline"
                                  className="text-[9px] py-0 h-4 px-1 bg-accent/15 text-accent-foreground border-accent/30 cursor-pointer"
                                  title="Confiança <85% — clique para rever as sugestões da IA"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleOpenReviewModal(file);
                                  }}
                                >
                                  <AlertTriangle className="h-2.5 w-2.5 mr-0.5" />
                                  ⚠️ Revisão Necessária
                                </Badge>
                              )}
                              {file.ai_review_status === "approved" && (
                                <Badge
                                  variant="secondary"
                                  className="text-[9px] py-0 h-4 px-1"
                                  title="Sugestões IA aprovadas"
                                >
                                  <CheckCircle2 className="h-2.5 w-2.5 mr-0.5" />
                                  Aprovado
                                </Badge>
                              )}
                              {file.ai_review_status === "rejected" && (
                                <Badge
                                  variant="outline"
                                  className="text-[9px] py-0 h-4 px-1 text-muted-foreground"
                                  title="Sugestões IA rejeitadas"
                                >
                                  Rejeitado
                                </Badge>
                              )}
                              {file.ai_review_status === "edited" && (
                                <Badge
                                  variant="outline"
                                  className="text-[9px] py-0 h-4 px-1 bg-primary/15 text-primary border-primary/30"
                                  title="Sugestões IA aplicadas com edições manuais"
                                >
                                  <Pencil className="h-2.5 w-2.5 mr-0.5" />
                                  Editado
                                </Badge>
                              )}
                              {file.ai_analyzed && (
                                <Badge
                                  variant="outline"
                                  className="text-[9px] py-0 h-4 px-1 bg-purple-50 text-purple-700 border-purple-200"
                                  title="Já analisado pela IA"
                                >
                                  <Brain className="h-2.5 w-2.5 mr-0.5" />
                                  IA
                                </Badge>
                              )}
                              <span className="text-[10px] text-muted-foreground">
                                {file.size_formatted}
                              </span>
                            </div>
                            <span className="text-[10px] text-muted-foreground mt-1">
                              {formatDate(file.last_modified)}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    <FolderOpen className="h-10 w-10 mx-auto mb-3 opacity-50" />
                    <p className="text-sm">
                      {searchQuery ? "Nenhum ficheiro encontrado" : "Nenhum ficheiro"}
                    </p>
                    <p className="text-xs mt-1">
                      {searchQuery ? `Pesquisa: "${searchQuery}"` : "Faça upload de documentos"}
                    </p>
                  </div>
                )}
              </TabsContent>

              {visibleCategories.map((cat) => (
                <TabsContent key={cat.id} value={cat.id} className="mt-3">
                  {getFilteredCategoryFiles(cat.id).length > 0 ? (
                    <div className="overflow-x-auto pb-2 -mx-2 px-2">
                      <div className="flex gap-3 min-w-max">
                        {getFilteredCategoryFiles(cat.id).map((file, idx) => {
                          const isDragging = draggedFile?.path === file.path || draggedFiles.some(f => f.path === file.path);
                          return (
                            <div
                              key={`${file.path}-${idx}`}
                              draggable
                              onDragStart={(e) => handleDragStart(e, file)}
                              onDragEnd={handleDragEnd}
                              className={`flex flex-col w-[140px] sm:w-[180px] md:w-[200px] p-3 rounded-lg border bg-card hover:bg-accent/50 transition-colors group cursor-grab active:cursor-grabbing ${isDragging ? "opacity-40 ring-2 ring-teal-400" : ""}`}
                              data-testid={`file-item-${idx}`}
                            >
                              {/* Icon and actions row */}
                              <div className="flex items-center justify-between mb-2">
                                <FileIcon filename={file.name} />
                                <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                                  {/* PACOTE DJ — Botão "Analisar com IA" (HITL) por documento (vista grelha - por categoria). */}
                                  {canUseAIDocumentTools && !file?.path?.endsWith('/') && (
                                    <Button
                                      variant="ghost"
                                      size="icon"
                                      className="h-6 w-6 text-primary hover:text-primary"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        handleAnalyzeDocForReview(file);
                                      }}
                                      disabled={analyzingDocIds.has(file.doc_id || file.id)}
                                      title="Analisar com IA"
                                      data-testid={`dj-analyze-btn-cat-${idx}`}
                                    >
                                      {analyzingDocIds.has(file.doc_id || file.id) ? (
                                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                      ) : (
                                        <BrainCircuit className="h-3.5 w-3.5" />
                                      )}
                                    </Button>
                                  )}
                                  {canUseAIDocumentTools && !file?.path?.endsWith('/') && podeExtrairDados(file?.name) && (
                                    <Button
                                      variant="ghost"
                                      size="icon"
                                      className="h-6 w-6 text-primary hover:text-primary"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        handleExtractDocData(file);
                                      }}
                                      disabled={extractingPaths.has(file.path)}
                                      title="Extrair Dados com IA"
                                      aria-label={`Extrair dados de ${file.name}`}
                                      data-testid={`vlm-extract-btn-cat-${idx}`}
                                    >
                                      {extractingPaths.has(file.path) ? (
                                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                      ) : (
                                        <ScanText className="h-3.5 w-3.5" />
                                      )}
                                    </Button>
                                  )}
                                  {isPdfFile(file.name) && (
                                    <Button
                                      variant="ghost"
                                      size="icon"
                                      className="h-6 w-6 text-amber-500 hover:text-amber-600"
                                      onClick={(e) => { e.stopPropagation(); handleOpenAnnotations(file); }}
                                      title="Anotações"
                                    >
                                      <MessageSquare className="h-3.5 w-3.5" />
                                    </Button>
                                  )}
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-6 w-6"
                                    onClick={(e) => { e.stopPropagation(); handleDownload(file); }}
                                    title="Download"
                                    data-testid={`download-btn-${idx}`}
                                  >
                                    <Download className="h-3.5 w-3.5" />
                                  </Button>
                                  {/* INDEXAÇÃO READ-ONLY: Ocultar botão de eliminar; também ocultar para pastas */}
                                  {!isIndexacao && !previewFile?.path?.endsWith('/') && (
                                    <Button
                                      variant="ghost"
                                      size="icon"
                                      className="h-6 w-6 text-red-500 hover:text-red-600"
                                      onClick={(e) => { e.stopPropagation(); setDeleteDialog({ open: true, file }); }}
                                      title="Eliminar"
                                      data-testid={`delete-btn-${idx}`}
                                    >
                                      <Trash2 className="h-3.5 w-3.5" />
                                    </Button>
                                  )}
                                </div>
                              </div>
                              {/* Clickable file name - duas linhas com letra pequena */}
                              <button
                                onClick={(e) => { e.stopPropagation(); handleDownload(file); }}
                                className="text-left text-[10px] sm:text-xs font-medium line-clamp-2 hover:text-blue-600 hover:underline cursor-pointer mb-1 min-h-[2rem] leading-tight"
                                title={`Clique para descarregar: ${file.name}`}
                              >
                                {file.name}
                              </button>
                              {/* Meta info */}
                              <div className="flex flex-wrap items-center gap-1">
                                {/* PACOTE DJ — Sistema Híbrido. Badges de estado de revisão IA (grelha - por categoria). */}
                                {analyzingDocIds.has(file.doc_id || file.id) && (
                                  <Badge
                                    variant="outline"
                                    className="text-[9px] py-0 h-4 px-1 bg-primary/10 text-primary border-primary/20"
                                    title="A análise IA está em curso..."
                                  >
                                    <Loader2 className="h-2.5 w-2.5 mr-0.5 animate-spin" />
                                    A analisar...
                                  </Badge>
                                )}
                                {file.ai_review_status === "auto_approved" && (
                                  <Badge
                                    variant="secondary"
                                    className="text-[9px] py-0 h-4 px-1 bg-primary/10 text-primary border-primary/20"
                                    title="Confiança ≥85% — sugestões IA aplicadas automaticamente"
                                  >
                                    <Sparkles className="h-2.5 w-2.5 mr-0.5" />
                                    ✨ Auto-Aprovado
                                  </Badge>
                                )}
                                {file.ai_review_status === "pending_review" && (
                                  <Badge
                                    variant="outline"
                                    className="text-[9px] py-0 h-4 px-1 bg-accent/15 text-accent-foreground border-accent/30 cursor-pointer"
                                    title="Confiança <85% — clique para rever as sugestões da IA"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleOpenReviewModal(file);
                                    }}
                                  >
                                    <AlertTriangle className="h-2.5 w-2.5 mr-0.5" />
                                    ⚠️ Revisão Necessária
                                  </Badge>
                                )}
                                {file.ai_review_status === "approved" && (
                                  <Badge
                                    variant="secondary"
                                    className="text-[9px] py-0 h-4 px-1"
                                    title="Sugestões IA aprovadas"
                                  >
                                    <CheckCircle2 className="h-2.5 w-2.5 mr-0.5" />
                                    Aprovado
                                  </Badge>
                                )}
                                {file.ai_review_status === "rejected" && (
                                  <Badge
                                    variant="outline"
                                    className="text-[9px] py-0 h-4 px-1 text-muted-foreground"
                                    title="Sugestões IA rejeitadas"
                                  >
                                    Rejeitado
                                  </Badge>
                                )}
                                {file.ai_review_status === "edited" && (
                                  <Badge
                                    variant="outline"
                                    className="text-[9px] py-0 h-4 px-1 bg-primary/15 text-primary border-primary/30"
                                    title="Sugestões IA aplicadas com edições manuais"
                                  >
                                    <Pencil className="h-2.5 w-2.5 mr-0.5" />
                                    Editado
                                  </Badge>
                                )}
                                {file.ai_analyzed && (
                                  <Badge
                                    variant="outline"
                                    className="text-[9px] py-0 h-4 px-1 bg-purple-50 text-purple-700 border-purple-200"
                                    title="Já analisado pela IA"
                                  >
                                    <Brain className="h-2.5 w-2.5 mr-0.5" />
                                    IA
                                  </Badge>
                                )}
                                <span className="text-[10px] text-muted-foreground">
                                  {file.size_formatted}
                                </span>
                              </div>
                              <span className="text-[10px] text-muted-foreground mt-1">
                                {formatDate(file.last_modified)}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ) : (
                    <div className="text-center py-8 text-muted-foreground">
                      <FolderOpen className="h-10 w-10 mx-auto mb-3 opacity-50" />
                      <p className="text-sm">Nenhum ficheiro em {cat.label}</p>
                      <p className="text-xs mt-1">
                        Clique em "Upload" para adicionar documentos
                      </p>
                    </div>
                  )}
                </TabsContent>
              ))}
            </Tabs>
          )}
        </CardContent>
      </Card>

      {/* Dialog de confirmação de eliminação */}
      <DeleteFileDialog
        open={deleteDialog.open}
        fileName={deleteDialog.file?.name}
        deleting={deleting}
        onOpenChange={handleDeleteDialogOpenChange}
        onConfirm={handleDelete}
      />

      {/* Dialog para conflito de nomes ao mover/renomear */}
      <MoveConflictDialog
        open={conflictDialog.open}
        conflicts={conflictDialog.conflicts}
        targetCategory={conflictDialog.targetCategory}
        onDecide={handleConflictDecision}
        onDecideForAll={handleConflictDecisionForAll}
        onCancel={handleCancelMoveConflict}
      />

      {/* Dialog para geração de minutas */}
      <GenerateTemplateDialog
        open={templateDialog.open}
        templates={TEMPLATES}
        selectedTemplate={selectedTemplate}
        error={templateError}
        generating={generatingTemplate}
        onOpenChange={handleTemplateDialogOpenChange}
        onTemplateChange={handleTemplateChange}
        onGenerate={handleGenerateTemplate}
      />

      {/* Dialog de Resultados da Análise IA */}
      <AIResultsDialog
        open={aiDialog.open}
        results={aiDialog.results}
        clientName={clientName}
        applying={applyingChanges}
        onOpenChange={handleAIDialogOpenChange}
        onApplySuggestions={handleApplyAISuggestions}
      />

      {/* Diálogo de resultados de renomeação inteligente */}
      <SmartRenameResultsDialog
        open={renameDialog.open}
        results={renameDialog.results}
        onOpenChange={handleRenameDialogOpenChange}
      />

      {/* Dialog para NIF da Empresa (obrigatório para indexacao) */}
      <EmpresaNifDialog
        open={empresaNifDialog.open}
        files={empresaNifDialog.files}
        nif={empresaNifDialog.empresaNif}
        checking={empresaNifDialog.checking}
        existingProcesses={empresaNifDialog.existingProcesses}
        contrastColorOf={getContrastColor}
        onNifChange={handleEmpresaNifChange}
        onVerify={handleVerifyEmpresaNif}
        onConfirm={handleConfirmUploadWithNif}
        onCancel={handleCancelEmpresaNif}
      />

      {/* Diálogo de renomeação manual */}
      <ManualRenameDialog
        open={manualRenameDialog.open}
        fileName={manualRenameDialog.file?.name}
        newName={manualRenameDialog.newName}
        renaming={manualRenaming}
        onOpenChange={handleManualRenameOpenChange}
        onNameChange={handleManualRenameNameChange}
        onConfirm={handleManualRename}
      />

      {/* Diálogo de resultados da organização */}
      <OrganizeResultsDialog
        results={organizeResults}
        onClose={handleCloseOrganizeResults}
      />

      {/* Diálogo de conflitos de upload (ficheiros duplicados) */}
      <UploadConflictDialog
        open={uploadConflictDialog.open}
        conflicts={uploadConflictDialog.conflicts}
        currentIndex={uploadConflictDialog.currentConflictIndex}
        resolutions={uploadConflictDialog.resolutions}
        category={uploadConflictDialog.category}
        onResolve={handleConflictResolution}
        onNext={handleNextConflict}
        onCancel={handleCancelUpload}
      />

      {/* Visualizador de Anotações Contextuais */}
      {annotationViewer && (
        <PDFAnnotationViewer
          processId={processId}
          document={annotationViewer}
          token={token}
          onClose={handleCloseAnnotations}
          user={{ id: user?.id, name: user?.name || user?.email, role: user?.role }}
        />
      )}

      {/* PACOTE DJ — Modal de Revisão de Sugestões IA (Human-in-the-Loop).
          Aberto quando o consultor clica no botão "Analisar com IA" por
          documento (BrainCircuit) ou no badge "Sugestões IA" (pending).
          Permite aprovar/rejeitar cada campo sugerido pela IA antes de
          aplicar — ver DocumentReviewModal.jsx. */}
      <DocumentReviewModal
        open={reviewModal.open}
        onOpenChange={(open) => setReviewModal((prev) => ({ ...prev, open }))}
        doc={reviewModal.doc}
        onResolved={fetchFiles}
      />
    </>
  );
};

export default S3FileManager;
