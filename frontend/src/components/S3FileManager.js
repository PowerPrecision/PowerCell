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
 * @context {AuthContext} — Consome token, user para autenticação e permissões de role
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
import React, { useState, useEffect, useCallback, useRef } from "react";
import { useAuth } from "../contexts/AuthContext";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "./ui/card";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
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
import PDFAnnotationViewer from "./PDFAnnotationViewer";
import { hasRole } from "../utils/roleUtils";
import {
  FileText,
  Upload,
  Loader2,
  Download,
  Trash2,
  FolderOpen,
  RefreshCw,
  User,
  Briefcase,
  Building2,
  CreditCard,
  MoreVertical,
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
  CheckSquare,
  Square,
  Link,
  Settings2,
  ChevronDown,
  ChevronUp,
  ChevronRight,
  Save,
  LayoutGrid,
  List,
  HardDrive,
  Eye,
  ExternalLink,
  ZoomIn,
  ZoomOut,
  Pencil,
  FolderSync,
  MessageSquare,
} from "lucide-react";
import { Input } from "./ui/input";
import { format } from "date-fns";
import { pt } from "date-fns/locale";
import { safeDateStr } from "../lib/utils";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Calcula cor de texto com contraste adequado para a cor de fundo
const getContrastColor = (bgColor) => {
  if (!bgColor) return '#ffffff';
  const namedColors = {
    yellow: '#EAB308', orange: '#F97316', blue: '#3B82F6',
    green: '#22C55E', red: '#EF4444', purple: '#A855F7', gray: '#6B7280',
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
  { id: "Outros", label: "Outros", icon: FolderOpen, color: "gray" },
];

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

const S3FileManager = ({ processId, clientName, onAIDataExtracted }) => {
  const { token, user } = useAuth();
  const [files, setFiles] = useState({});
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
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
  const [moving, setMoving] = useState(false);
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
  
  // Função para ordenar ficheiros
  const sortFiles = (filesList) => {
    return [...filesList].sort((a, b) => {
      let comparison = 0;
      
      if (sortBy === "date") {
        const dateA = new Date(a.last_modified ? safeDateStr(a.last_modified) : 0);
        const dateB = new Date(b.last_modified ? safeDateStr(b.last_modified) : 0);
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
      const response = await fetch(
        `${API_URL}/api/documents/client/${processId}/files`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (response.ok) {
        const data = await response.json();
        setFiles(data.files || {});
        setStats(data.stats || null);
      } else {
        const error = await response.json();
        if (error.detail !== "S3 não configurado") {
          toast.error(error.detail || "Erro ao carregar ficheiros");
        }
      }
    } catch (error) {
      console.error("Erro ao carregar ficheiros:", error);
    } finally {
      setLoading(false);
    }
  }, [processId, token]);

  useEffect(() => {
    fetchFiles();
  }, [fetchFiles]);

  // Carregar mapeamento S3 actual e pastas disponíveis
  const loadS3MappingData = async () => {
    if (!canMapS3) return;
    
    setLoadingS3Folders(true);
    try {
      // Buscar dados do mapeamento
      const response = await fetch(
        `${API_URL}/api/admin/client-s3-mappings?search=${encodeURIComponent(clientName || '')}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      
      if (response.ok) {
        const data = await response.json();
        setS3Folders(data.available_folders || []);
        
        // Encontrar mapeamento actual deste processo
        const currentProcess = data.processes?.find(p => p.id === processId);
        if (currentProcess) {
          // Backend retorna 's3_folder', não 's3_folder_mapping'
          setCurrentS3Mapping(currentProcess.s3_folder || null);
          setSelectedS3Folder(currentProcess.s3_folder || "");
        }
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
      const url = selectedS3Folder
        ? `${API_URL}/api/admin/client-s3-mappings?process_id=${processId}&s3_folder=${encodeURIComponent(selectedS3Folder)}`
        : `${API_URL}/api/admin/client-s3-mappings?process_id=${processId}`;
      
      const response = await fetch(url, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      
      if (response.ok) {
        const data = await response.json();
        toast.success(data.message || "Mapeamento guardado");
        setCurrentS3Mapping(selectedS3Folder);
        setS3MappingOpen(false);
        // Recarregar ficheiros para mostrar os da nova pasta
        fetchFiles();
      } else {
        const error = await response.json();
        toast.error(error.detail || "Erro ao guardar mapeamento");
      }
    } catch (error) {
      console.error("Erro ao guardar mapeamento:", error);
      toast.error("Erro ao guardar mapeamento");
    } finally {
      setSavingS3Mapping(false);
    }
  };

  // Inicializar pastas
  const initializeFolders = async () => {
    try {
      const response = await fetch(
        `${API_URL}/api/documents/client/${processId}/init-folders`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (response.ok) {
        toast.success("Estrutura de pastas criada");
        fetchFiles();
      }
    } catch (error) {
      console.error("Erro ao criar pastas:", error);
    }
  };

  // Verificar NIF da empresa
  const checkEmpresaNif = async (nif) => {
    try {
      const response = await fetch(
        `${API_URL}/api/documents/check-employer-nif/${nif}`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      
      if (response.ok) {
        return await response.json();
      }
      return null;
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
        const response = await fetch(
          `${API_URL}/api/documents/client/${processId}/upload`,
          {
            method: "POST",
            headers: { Authorization: `Bearer ${token}` },
            body: formData,
          }
        );

        if (response.ok) {
          successCount++;
        } else if (response.status === 429) {
          // Rate limiting - esperar e tentar novamente
          const retryAfter = response.headers.get("Retry-After") || 60;
          toast.warning(`Aguardar ${retryAfter} segundos antes de continuar...`);
          // Esperar e tentar novamente o mesmo ficheiro
          await new Promise(resolve => setTimeout(resolve, parseInt(retryAfter) * 1000));
          i--; // Tentar novamente o mesmo ficheiro
          continue;
        } else {
          const error = await response.json();
          // Mensagem de erro mais amigável
          const errorMsg = error.detail || `Erro ${response.status}`;
          toast.error(`${file.name}: ${errorMsg}`);
          errorCount++;
        }
      } catch (error) {
        toast.error(`Erro de conexão ao enviar ${file.name}`);
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
      const response = await fetch(
        `${API_URL}/api/documents/check-upload-conflict`,
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            process_id: processId,
            filenames: filenames,
            category: category
          })
        }
      );
      
      if (response.ok) {
        return await response.json();
      }
      return { has_conflicts: false, conflicts: [] };
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
        const response = await fetch(
          `${API_URL}/api/documents/client/${processId}/upload`,
          {
            method: "POST",
            headers: { Authorization: `Bearer ${token}` },
            body: formData,
          }
        );

        if (response.ok) {
          successCount++;
        } else if (response.status === 429) {
          const retryAfter = response.headers.get("Retry-After") || 60;
          toast.warning(`Aguardar ${retryAfter} segundos antes de continuar...`);
          await new Promise(resolve => setTimeout(resolve, parseInt(retryAfter) * 1000));
          i--;
          continue;
        } else {
          const error = await response.json();
          const errorMsg = error.detail || `Erro ${response.status}`;
          toast.error(`${file.name}: ${errorMsg}`);
          errorCount++;
        }
      } catch (error) {
        toast.error(`Erro de conexão ao enviar ${file.name}`);
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
      const response = await fetch(
        `${API_URL}/api/documents/proxy/${encodeURIComponent(file.path)}`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (response.ok) {
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = file.name || 'download';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      } else {
        const error = await response.json();
        toast.error(error.detail || "Erro ao fazer download");
      }
    } catch (error) {
      console.error("Erro ao fazer download:", error);
      toast.error("Erro ao fazer download");
    }
  };

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
      const response = await fetch(
        `${API_URL}/api/documents/client/${processId}/file?file_path=${encodeURIComponent(deleteDialog.file.path)}`,
        {
          method: "DELETE",
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (response.ok) {
        toast.success("Ficheiro eliminado");
        fetchFiles();
      } else {
        const error = await response.json().catch(() => ({}));
        toast.error(error.detail || "Erro ao eliminar ficheiro");
      }
    } catch (error) {
      toast.error("Erro ao eliminar ficheiro");
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
      const response = await fetch(
        `${API_URL}/api/documents/client/${processId}/bulk-delete`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            file_paths: selectedFilesForAI.map((f) => f.path),
          }),
        }
      );

      if (response.ok) {
        const data = await response.json();
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
      } else {
        const error = await response.json().catch(() => ({}));
        toast.error(error.detail || "Erro ao eliminar ficheiros");
      }
    } catch (error) {
      console.error("Erro ao eliminar ficheiros em massa:", error);
      toast.error("Erro ao eliminar ficheiros");
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
      const response = await fetch(
        `${API_URL}/api/templates/process/${processId}/generate/${selectedTemplate}/download`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (response.ok) {
        // Download do ficheiro
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        
        // Obter nome do ficheiro do header ou usar default
        const disposition = response.headers.get('Content-Disposition');
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
      } else {
        const error = await response.json();
        // Se for erro de validação (campos em falta)
        if (error.detail?.missing_fields) {
          setTemplateError({
            message: error.detail.message || "Dados incompletos",
            missingFields: error.detail.missing_fields
          });
        } else {
          toast.error(error.detail?.message || error.detail || "Erro ao gerar minuta");
        }
      }
    } catch (error) {
      console.error("Erro ao gerar template:", error);
      toast.error("Erro ao gerar minuta");
    } finally {
      setGeneratingTemplate(false);
    }
  };

  // Formatar data - dd/mm/AA hh:mm
  const formatDate = (dateStr) => {
    try {
      return format(new Date(safeDateStr(dateStr)), "dd/MM/yy HH:mm", { locale: pt });
    } catch {
      return dateStr;
    }
  };

  // Contar ficheiros por categoria
  const getCategoryCount = (categoryId) => {
    return files[categoryId]?.length || 0;
  };

  // Obter todos os ficheiros (todas as categorias)
  const getAllFiles = () => {
    const allFiles = [];
    Object.values(files).forEach(categoryFiles => {
      if (Array.isArray(categoryFiles)) {
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
      const response = await fetch(
        `${API_URL}/api/documents/proxy/${encodeURIComponent(file.path)}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      
      if (response.ok) {
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        setPreviewUrl(url);
      } else {
        const error = await response.json();
        toast.error(error.detail || "Erro ao carregar preview");
        setPreviewFile(null);
      }
    } catch (error) {
      console.error("Erro ao carregar preview:", error);
      toast.error("Erro ao carregar preview");
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

  // Análise IA dos documentos
  const handleAIAnalysis = async () => {
    const filesToAnalyze = selectedFilesForAI.length > 0 ? selectedFilesForAI : getAllFiles();
    
    if (filesToAnalyze.length === 0) {
      toast.error("Não há ficheiros para analisar");
      return;
    }

    setAiAnalyzing(true);
    toast.info(`A analisar ${filesToAnalyze.length} documento(s) com IA...`);

    try {
      // Criar FormData com os ficheiros
      const formData = new FormData();
      
      // Obter o conteúdo dos ficheiros via proxy endpoint (evita CORS do S3)
      for (const file of filesToAnalyze) {
        try {
          // Usar proxy endpoint que faz streaming através do backend (evita CORS)
          const proxyResponse = await fetch(
            `${API_URL}/api/documents/proxy/${encodeURIComponent(file.path)}`,
            { headers: { Authorization: `Bearer ${token}` } }
          );
          
          if (proxyResponse.ok) {
            const blob = await proxyResponse.blob();
            formData.append('files', blob, file.name);
          } else {
            console.warn(`Erro ao obter ficheiro ${file.name} via proxy: ${proxyResponse.status}`);
            continue;
          }
        } catch (e) {
          console.error(`Erro ao obter ficheiro ${file.name}:`, e);
        }
      }

      // Enviar para análise
      const response = await fetch(
        `${API_URL}/api/documents/ai-analyze/${processId}`,
        {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
          body: formData,
        }
      );

      if (response.ok) {
        const result = await response.json();
        
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
              await fetch(`${API_URL}/api/documents/organize/${processId}`, {
                method: 'POST',
                headers: { 
                  Authorization: `Bearer ${token}`,
                  'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                  documents: docsToOrganize,
                  create_folders: true
                })
              });
            }
          } catch (orgError) {
            console.warn("Erro ao organizar documentos:", orgError);
          }
          
          // Passar dados extraídos para o componente pai
          onAIDataExtracted({
            extractedData: result.extracted_data,
            fieldConfidence: result.field_confidence || {},
            conflicts: result.conflicts || [],
            documentsProcessed: result.documents_count,
            suggestions: result.suggestions || []
          });
          
          toast.success(`Análise completa! ${result.documents_count} documento(s) processado(s). Verifique os campos pré-preenchidos.`);
          
          // Não mostrar popup se temos callback
          setSelectedFilesForAI([]);
        } else {
          // Fallback: mostrar popup com resultados
          setAiDialog({ open: true, results: result });
          toast.success(`Análise completa: ${result.documents_count} documento(s) processado(s)`);
        }
        
        // Recarregar ficheiros para ver nova organização
        fetchFiles();
      } else {
        const error = await response.json();
        toast.error(error.detail || "Erro na análise IA");
      }
    } catch (error) {
      console.error("Erro na análise IA:", error);
      toast.error("Erro ao analisar documentos");
    } finally {
      setAiAnalyzing(false);
      setSelectedFilesForAI([]);
    }
  };

  // Aplicar sugestões da análise IA
  const handleApplyAISuggestions = async (suggestions) => {
    if (!suggestions || Object.keys(suggestions).length === 0) {
      toast.info("Nenhuma sugestão para aplicar");
      return;
    }

    setApplyingChanges(true);
    try {
      const response = await fetch(
        `${API_URL}/api/documents/ai-apply-suggestions/${processId}`,
        {
          method: 'POST',
          headers: { 
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(suggestions),
        }
      );

      if (response.ok) {
        const result = await response.json();
        toast.success(`${result.updated_fields} campo(s) actualizado(s)`);
        setAiDialog({ open: false, results: null });
      } else {
        const error = await response.json();
        toast.error(error.detail || "Erro ao aplicar sugestões");
      }
    } catch (error) {
      console.error("Erro ao aplicar sugestões:", error);
      toast.error("Erro ao aplicar alterações");
    } finally {
      setApplyingChanges(false);
    }
  };

  // Renomeação inteligente de documentos com IA
  const handleSmartRename = async () => {
    const allFiles = getAllFiles();
    if (allFiles.length === 0) {
      toast.error("Não há ficheiros para renomear");
      return;
    }

    setRenaming(true);
    toast.info("A renomear documentos com nomes inteligentes...");

    try {
      const response = await fetch(
        `${API_URL}/api/documents/rename-all-smart/${processId}`,
        {
          method: 'POST',
          headers: { 
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      );

      if (response.ok) {
        const result = await response.json();
        
        if (result.renamed > 0) {
          toast.success(`${result.renamed} documento(s) renomeado(s) com sucesso!`);
          // Recarregar ficheiros para mostrar novos nomes
          fetchFiles();
        } else if (result.skipped > 0 && result.renamed === 0) {
          toast.info("Todos os documentos já têm nomes correctos ou não estão categorizados");
        }
        
        // Mostrar diálogo com detalhes se houver resultados
        if (result.details && result.details.length > 0) {
          setRenameDialog({ open: true, results: result });
        }
      } else {
        const error = await response.json();
        if (error.detail?.includes("categorizado")) {
          toast.warning("Execute primeiro a análise IA para categorizar os documentos");
        } else {
          toast.error(error.detail || "Erro ao renomear documentos");
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
      const response = await fetch(
        `${API_URL}/api/documents/rename-smart/${processId}`,
        {
          method: 'POST',
          headers: { 
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            s3_path: file.path,
            apply_ai_name: false,
            novo_nome: newName.trim()
          })
        }
      );

      if (response.ok) {
        const result = await response.json();
        toast.success(`Ficheiro renomeado para "${result.new_name}"`);
        setManualRenameDialog({ open: false, file: null, newName: "" });
        fetchFiles(); // Recarregar lista
      } else {
        const error = await response.json();
        toast.error(error.detail || "Erro ao renomear ficheiro");
      }
    } catch (error) {
      console.error("Erro ao renomear ficheiro:", error);
      toast.error("Erro ao renomear ficheiro");
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
          const proxyResponse = await fetch(
            `${API_URL}/api/documents/proxy/${encodeURIComponent(file.path)}`,
            { headers: { Authorization: `Bearer ${token}` } }
          );
          
          if (proxyResponse.ok) {
            const blob = await proxyResponse.blob();
            formData.append('files', blob, file.name);
          }
        } catch (e) {
          console.error(`Erro ao obter ficheiro ${file.name}:`, e);
        }
      }

      // Análise IA
      const analyzeResponse = await fetch(
        `${API_URL}/api/documents/ai-analyze/${processId}`,
        {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
          body: formData,
        }
      );

      if (!analyzeResponse.ok) {
        const error = await analyzeResponse.json();
        throw new Error(error.detail || "Erro na análise IA");
      }

      const analyzeResult = await analyzeResponse.json();

      // Passo 2: Organizar documentos nas pastas
      // Juntar source_path dos ficheiros originais com resultados da IA
      const docsToOrganize = (analyzeResult.documents || []).map(doc => {
        const originalFile = allFiles.find(f => f.name === doc.file_name);
        return {
          ...doc,
          source_path: originalFile?.path || null
        };
      }).filter(doc => doc.source_path);

      const organizeResponse = await fetch(
        `${API_URL}/api/documents/organize/${processId}`,
        {
          method: 'POST',
          headers: { 
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            documents: docsToOrganize,
            create_folders: true
          })
        }
      );

      if (organizeResponse.ok) {
        const organizeResult = await organizeResponse.json();
        
        setOrganizeResults({
          analyzed: analyzeResult.documents_count || allFiles.length,
          organized: organizeResult.organized_count || organizeResult.organized?.length || 0,
          categories: analyzeResult.categories_found || [],
          details: organizeResult.organized || []
        });

        toast.success(`Organização completa! ${organizeResult.organized_count || 0} documento(s) organizado(s).`);
        fetchFiles(); // Recarregar lista
      } else {
        const error = await organizeResponse.json();
        throw new Error(error.detail || "Erro ao organizar documentos");
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

  const handleDragLeave = (e, category) => {
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
        const response = await fetch(
          `${API_URL}/api/documents/check-move-conflict`,
          {
            method: 'POST',
            headers: { 
              Authorization: `Bearer ${token}`,
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({
              process_id: processId,
              source_path: file.path,
              target_category: targetCategory
            })
          }
        );
        
        if (response.ok) {
          const data = await response.json();
          if (data.has_conflict) {
            conflicts.push({
              file,
              conflictPath: data.conflict_path,
              conflictFilename: data.conflict_filename,
              suggestedNames: data.suggested_names
            });
          }
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
    
    const response = await fetch(
      `${API_URL}/api/documents/move-file/${processId}`,
      {
        method: 'POST',
        headers: { 
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(body)
      }
    );
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail?.message || errorData.detail || 'Erro ao mover ficheiro');
    }
    
    return response.json();
  };

  const handleDrop = async (e, targetCategory) => {
    e.preventDefault();
    const previousDropTarget = dropTarget;
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
                <span className="hidden sm:inline">Analisar</span> IA
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={handleSmartRename}
                disabled={renaming || getAllFiles().length === 0}
                data-testid="smart-rename-btn"
                title="Renomear documentos com nomes inteligentes baseados na análise IA"
                className="bg-amber-50 hover:bg-amber-100 border-amber-200 dark:bg-amber-950/50 dark:border-amber-800 dark:hover:bg-amber-900/50 whitespace-nowrap h-8 px-2 sm:px-3"
              >
                {renaming ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-amber-600 sm:mr-1" />
                ) : (
                  <Sparkles className="h-3.5 w-3.5 text-amber-600 sm:mr-1" />
                )}
                <span className="hidden md:inline">Renomear</span> IA
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={handleQuickOrganize}
                disabled={organizing || aiAnalyzing || getAllFiles().length === 0}
                data-testid="quick-organize-btn"
                title="Analisar e organizar documentos automaticamente nas pastas corretas"
                className="bg-teal-50 hover:bg-teal-100 border-teal-200 dark:bg-teal-950/50 dark:border-teal-800 dark:hover:bg-teal-900/50 whitespace-nowrap h-8 px-2 sm:px-3"
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
                  {CATEGORIES.map((cat) => {
                    const Icon = cat.icon;
                    const count = getCategoryCount(cat.id);
                    const colorMap = {
                      blue: "text-blue-500",
                      green: "text-green-500",
                      purple: "text-purple-500",
                      orange: "text-orange-500",
                      gray: "text-gray-500",
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
                            const response = await fetch(`${API_URL}/api/documents/bulk-download`, {
                              method: 'POST',
                              headers: {
                                Authorization: `Bearer ${token}`,
                                'Content-Type': 'application/json'
                              },
                              body: JSON.stringify({
                                document_ids: selectedFilesForAI.map(f => f.path),
                                process_id: processId
                              })
                            });
                            
                            if (response.ok) {
                              const blob = await response.blob();
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
                            } else {
                              const error = await response.json();
                              toast.error(error.detail || "Erro ao descarregar documentos");
                            }
                          } catch (error) {
                            console.error("Erro no download em massa:", error);
                            toast.error("Erro ao descarregar documentos");
                          }
                        }}
                      >
                        <Download className="h-3 w-3 mr-1" />
                        Download
                      </Button>
                      {/* Botão Análise IA */}
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
              <AlertDialog open={bulkDeleteDialog.open} onOpenChange={(open) => { if (!bulkDeleting) setBulkDeleteDialog({ open }); }}>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Eliminar {selectedFilesForAI.length} ficheiro(s)</AlertDialogTitle>
                    <AlertDialogDescription>
                      Tem a certeza que pretende eliminar {selectedFilesForAI.length} ficheiro(s) selecionado(s)? 
                      Esta ação não pode ser revertida. Os ficheiros serão removidos permanentemente do armazenamento.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel disabled={bulkDeleting}>Cancelar</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={(e) => {
                        e.preventDefault();
                        handleBulkDelete();
                      }}
                      disabled={bulkDeleting}
                      className="bg-red-600 text-white hover:bg-red-700 focus-visible:ring-red-300"
                    >
                      {bulkDeleting ? (
                        <>
                          <Loader2 className="h-4 w-4 animate-spin mr-1" />
                          A eliminar...
                        </>
                      ) : (
                        <>
                          <Trash2 className="h-4 w-4 mr-1" />
                          Eliminar {selectedFilesForAI.length} ficheiro(s)
                        </>
                      )}
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>

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
                {CATEGORIES.map((cat) => {
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

              {CATEGORIES.map((cat) => (
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
      <AlertDialog open={deleteDialog.open} onOpenChange={(open) => setDeleteDialog({ open, file: null })}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Eliminar ficheiro?</AlertDialogTitle>
            <AlertDialogDescription>
              Tem a certeza que deseja eliminar "{deleteDialog.file?.name}"?
              Esta ação não pode ser revertida.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              disabled={deleting}
              className="bg-red-500 hover:bg-red-600"
            >
              {deleting ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Trash2 className="h-4 w-4 mr-2" />
              )}
              Eliminar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Dialog para conflito de nomes ao mover/renomear */}
      <Dialog open={conflictDialog.open} onOpenChange={(open) => {
        if (!open) {
          setConflictDialog({ open: false, files: [], targetCategory: null, currentIndex: 0, conflicts: [] });
          setDraggedFile(null);
          setDraggedFiles([]);
        }
      }}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-amber-600">
              <AlertTriangle className="h-5 w-5" />
              Ficheiro com Nome Duplicado
            </DialogTitle>
            <DialogDescription>
              Já existe um ficheiro com o mesmo nome na pasta de destino.
            </DialogDescription>
          </DialogHeader>
          
          {conflictDialog.conflicts?.length > 0 && (
            <div className="space-y-4 py-4">
              {/* Info do ficheiro em conflito */}
              <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-4">
                <div className="flex items-center gap-3">
                  <FileText className="h-8 w-8 text-amber-600" />
                  <div>
                    <p className="font-medium text-amber-800 dark:text-amber-200">
                      {conflictDialog.conflicts[0]?.conflictFilename || conflictDialog.conflicts[0]?.file?.name}
                    </p>
                    <p className="text-sm text-amber-600 dark:text-amber-400">
                      Destino: {conflictDialog.targetCategory}
                    </p>
                  </div>
                </div>
              </div>
              
              {/* Mostrar mais ficheiros se houver múltiplos conflitos */}
              {conflictDialog.conflicts.length > 1 && (
                <p className="text-sm text-muted-foreground">
                  +{conflictDialog.conflicts.length - 1} outro(s) ficheiro(s) com conflito
                </p>
              )}
              
              {/* Opções de resolução */}
              <div className="space-y-2">
                <p className="text-sm font-medium">O que deseja fazer?</p>
                
                {/* Sugestões de nomes alternativos */}
                {conflictDialog.conflicts[0]?.suggestedNames?.length > 0 && (
                  <div className="bg-muted/50 rounded-lg p-3 mb-3">
                    <p className="text-xs text-muted-foreground mb-2">Nomes sugeridos:</p>
                    <div className="flex flex-wrap gap-2">
                      {conflictDialog.conflicts[0].suggestedNames.slice(0, 3).map((suggestion, idx) => (
                        <Button
                          key={idx}
                          variant="outline"
                          size="sm"
                          onClick={() => handleConflictDecision('custom', suggestion.filename)}
                          className="text-xs"
                        >
                          <Save className="h-3 w-3 mr-1" />
                          {suggestion.filename || suggestion}
                        </Button>
                      ))}
                    </div>
                  </div>
                )}
                
                <div className="grid grid-cols-2 gap-2">
                  <Button
                    variant="outline"
                    onClick={() => handleConflictDecision('rename')}
                    className="w-full"
                  >
                    <Pencil className="h-4 w-4 mr-2" />
                    Renomear Automaticamente
                  </Button>
                  <Button
                    variant="destructive"
                    onClick={() => handleConflictDecision('overwrite')}
                    className="w-full"
                  >
                    <Trash2 className="h-4 w-4 mr-2" />
                    Substituir Existente
                  </Button>
                </div>
                
                <div className="grid grid-cols-2 gap-2">
                  <Button
                    variant="ghost"
                    onClick={() => handleConflictDecision('skip')}
                    className="w-full"
                  >
                    <X className="h-4 w-4 mr-2" />
                    Ignorar Este
                  </Button>
                  {conflictDialog.conflicts?.length > 1 && (
                    <Button
                      variant="ghost"
                      onClick={() => handleConflictDecisionForAll('rename')}
                      className="w-full text-amber-600 hover:text-amber-700"
                    >
                      <FolderSync className="h-4 w-4 mr-2" />
                      Renomear Todos
                    </Button>
                  )}
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Dialog para geração de minutas */}
      <Dialog open={templateDialog.open} onOpenChange={(open) => {
        setTemplateDialog({ open });
        if (!open) {
          setTemplateError(null);
          setSelectedTemplate("");
        }
      }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileDown className="h-5 w-5 text-emerald-600" />
              Gerar Minuta
            </DialogTitle>
            <DialogDescription>
              Selecione o tipo de documento para gerar automaticamente com os dados do cliente.
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Tipo de Documento</label>
              <Select
                value={selectedTemplate}
                onValueChange={(value) => {
                  setSelectedTemplate(value);
                  setTemplateError(null);
                }}
              >
                <SelectTrigger data-testid="template-select">
                  <SelectValue placeholder="Selecione o tipo de documento..." />
                </SelectTrigger>
                <SelectContent>
                  {TEMPLATES.map((t) => (
                    <SelectItem key={t.value} value={t.value}>
                      {t.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Erro de validação - campos em falta */}
            {templateError && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950/30">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="font-medium text-amber-800 dark:text-amber-200">
                      Não é possível gerar a minuta
                    </p>
                    <p className="text-sm text-amber-700 dark:text-amber-300 mt-1">
                      {templateError.message}
                    </p>
                    {templateError.missingFields?.length > 0 && (
                      <div className="mt-2">
                        <p className="text-sm font-medium text-amber-800 dark:text-amber-200">
                          Campos em falta:
                        </p>
                        <ul className="mt-1 text-sm text-amber-700 dark:text-amber-300 list-disc list-inside">
                          {templateError.missingFields.map((field, idx) => (
                            <li key={idx}>{field}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    <p className="text-xs text-amber-600 dark:text-amber-400 mt-2">
                      Preencha os dados em falta na ficha do cliente antes de gerar o documento.
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>

          <DialogFooter className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => setTemplateDialog({ open: false })}
              disabled={generatingTemplate}
            >
              Cancelar
            </Button>
            <Button
              onClick={handleGenerateTemplate}
              disabled={!selectedTemplate || generatingTemplate}
              className="bg-emerald-600 hover:bg-emerald-700"
            >
              {generatingTemplate ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <FileDown className="h-4 w-4 mr-2" />
              )}
              Gerar e Descarregar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog de Resultados da Análise IA */}
      <Dialog open={aiDialog.open} onOpenChange={(open) => setAiDialog({ open, results: open ? aiDialog.results : null })}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Brain className="h-5 w-5 text-purple-600" />
              Resultados da Análise IA
            </DialogTitle>
            <DialogDescription>
              Dados extraídos dos documentos de {clientName || "cliente"}
            </DialogDescription>
          </DialogHeader>

          <div className="flex-1 overflow-y-auto py-4 space-y-4">
            {aiDialog.results?.analysis && (
              <>
                {/* Documentos Analisados */}
                <div className="space-y-2">
                  <h4 className="font-medium text-sm flex items-center gap-2">
                    <FileText className="h-4 w-4" />
                    Documentos Processados ({aiDialog.results.analysis.documents_analyzed?.length || 0})
                  </h4>
                  <div className="grid gap-2">
                    {aiDialog.results.analysis.documents_analyzed?.map((doc, idx) => (
                      <div key={idx} className="p-2 rounded border bg-muted/30">
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-medium">{doc.file_name}</span>
                          <Badge variant="outline" className="text-xs">
                            {doc.tipo_documento || "outro"}
                          </Badge>
                        </div>
                        <div className="text-xs text-muted-foreground mt-1">
                          Confiança: {Math.round((doc.confianca || 0) * 100)}%
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Campos Vazios (Podem ser Preenchidos) */}
                {aiDialog.results.analysis.comparison?.empty_fields?.length > 0 && (
                  <div className="space-y-2">
                    <h4 className="font-medium text-sm flex items-center gap-2 text-green-600">
                      <CheckCircle className="h-4 w-4" />
                      Campos a Preencher ({aiDialog.results.analysis.comparison.empty_fields.length})
                    </h4>
                    <div className="grid gap-2">
                      {aiDialog.results.analysis.comparison.empty_fields.map((field, idx) => {
                        // Obter confiança do campo via auto_fill_suggestions
                        const suggestion = aiDialog.results.analysis.auto_fill_suggestions?.[field.field];
                        const conf = suggestion?.confidence;
                        const pct = Math.round((conf || 0) * 100);
                        const confBadge = conf >= 0.8
                          ? "bg-green-100 text-green-700"
                          : conf >= 0.6
                            ? "bg-amber-100 text-amber-700"
                            : "bg-red-100 text-red-700";
                        return (
                          <div key={idx} className={`p-2 rounded border ${conf < 0.8 ? 'border-amber-300 bg-amber-50 dark:bg-amber-950/30' : 'bg-green-50 dark:bg-green-950/30'}`}>
                            <div className="flex items-center justify-between">
                              <span className="text-sm font-medium">{field.field}</span>
                              <div className="flex gap-1">
                                <Badge className="bg-green-100 text-green-700">Novo</Badge>
                                {conf !== undefined && (
                                  <Badge className={`text-[10px] ${confBadge}`}>
                                    {pct}%
                                  </Badge>
                                )}
                              </div>
                            </div>
                            <p className={`text-sm mt-1 ${conf < 0.8 ? 'text-amber-700 dark:text-amber-300' : 'text-green-700 dark:text-green-300'}`}>
                              {field.suggested_value}
                            </p>
                            {conf < 0.8 && conf !== undefined && (
                              <p className="text-[10px] text-amber-600 mt-1">⚠️ Baixa confiança — verifique manualmente</p>
                            )}
                            <p className="text-xs text-muted-foreground">
                              Fonte: {field.source}
                            </p>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Campos com Diferenças */}
                {aiDialog.results.analysis.comparison?.different?.length > 0 && (
                  <div className="space-y-2">
                    <h4 className="font-medium text-sm flex items-center gap-2 text-amber-600">
                      <AlertCircle className="h-4 w-4" />
                      Dados Divergentes ({aiDialog.results.analysis.comparison.different.length})
                    </h4>
                    <div className="grid gap-2">
                      {aiDialog.results.analysis.comparison.different.map((field, idx) => (
                        <div key={idx} className="p-2 rounded border bg-amber-50 dark:bg-amber-950/30">
                          <div className="text-sm font-medium">{field.field}</div>
                          <div className="grid grid-cols-2 gap-2 mt-1">
                            <div className="text-xs">
                              <span className="text-muted-foreground">Actual:</span>
                              <p className="font-medium">{field.current_value}</p>
                            </div>
                            <div className="text-xs">
                              <span className="text-muted-foreground">Documento:</span>
                              <p className="font-medium text-amber-700">{field.document_value}</p>
                            </div>
                          </div>
                          <Button
                            size="sm"
                            variant="outline"
                            className="mt-2 text-xs bg-amber-100 hover:bg-amber-200 border-amber-300"
                            onClick={() => handleApplyAISuggestions({ [field.field]: field.document_value })}
                            disabled={applyingChanges}
                          >
                            {applyingChanges ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <CheckCircle className="h-3 w-3 mr-1" />}
                            Usar valor do documento
                          </Button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Campos Coincidentes */}
                {aiDialog.results.analysis.comparison?.matching?.length > 0 && (
                  <div className="space-y-2">
                    <h4 className="font-medium text-sm flex items-center gap-2 text-muted-foreground">
                      <CheckCircle className="h-4 w-4" />
                      Dados Confirmados ({aiDialog.results.analysis.comparison.matching.length})
                    </h4>
                    <div className="flex flex-wrap gap-1">
                      {aiDialog.results.analysis.comparison.matching.map((field, idx) => (
                        <Badge key={idx} variant="outline" className="text-xs">
                          {field.field}: {field.value?.toString().substring(0, 20)}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>

          <DialogFooter className="flex gap-2 pt-4 border-t">
            <Button
              variant="outline"
              onClick={() => setAiDialog({ open: false, results: null })}
            >
              Fechar
            </Button>
            {aiDialog.results?.analysis?.auto_fill_suggestions && 
              Object.keys(aiDialog.results.analysis.auto_fill_suggestions).length > 0 && (
              <Button
                onClick={() => handleApplyAISuggestions(
                  Object.fromEntries(
                    Object.entries(aiDialog.results.analysis.auto_fill_suggestions)
                      .map(([k, v]) => [k, v.value])
                  )
                )}
                disabled={applyingChanges}
                className="bg-purple-600 hover:bg-purple-700"
              >
                {applyingChanges ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                ) : (
                  <Sparkles className="h-4 w-4 mr-2" />
                )}
                Aplicar Sugestões
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Diálogo de resultados de renomeação inteligente */}
      <Dialog open={renameDialog.open} onOpenChange={(open) => setRenameDialog({ open, results: open ? renameDialog.results : null })}>
        <DialogContent className="max-w-lg max-h-[80vh] overflow-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-amber-600" />
              Renomeação Inteligente
            </DialogTitle>
            <DialogDescription>
              Resultado da renomeação automática dos documentos
            </DialogDescription>
          </DialogHeader>
          
          {renameDialog.results && (
            <div className="space-y-4 py-4">
              {/* Estatísticas resumidas */}
              <div className="grid grid-cols-4 gap-2">
                <div className="text-center p-2 bg-muted rounded-lg">
                  <p className="text-2xl font-bold">{renameDialog.results.total}</p>
                  <p className="text-xs text-muted-foreground">Total</p>
                </div>
                <div className="text-center p-2 bg-green-50 dark:bg-green-950/30 rounded-lg">
                  <p className="text-2xl font-bold text-green-600">{renameDialog.results.renamed}</p>
                  <p className="text-xs text-green-600">Renomeados</p>
                </div>
                <div className="text-center p-2 bg-amber-50 dark:bg-amber-950/30 rounded-lg">
                  <p className="text-2xl font-bold text-amber-600">{renameDialog.results.skipped}</p>
                  <p className="text-xs text-amber-600">Ignorados</p>
                </div>
                <div className="text-center p-2 bg-red-50 dark:bg-red-950/30 rounded-lg">
                  <p className="text-2xl font-bold text-red-600">{renameDialog.results.errors}</p>
                  <p className="text-xs text-red-600">Erros</p>
                </div>
              </div>
              
              {/* Lista detalhada */}
              {renameDialog.results.details && renameDialog.results.details.length > 0 && (
                <div className="border rounded-lg divide-y max-h-60 overflow-auto">
                  {renameDialog.results.details.map((item, idx) => (
                    <div key={idx} className="p-2 flex items-center gap-2 text-sm">
                      {item.status === "renamed" ? (
                        <CheckCircle className="h-4 w-4 text-green-500 flex-shrink-0" />
                      ) : item.status === "skipped" ? (
                        <AlertCircle className="h-4 w-4 text-amber-500 flex-shrink-0" />
                      ) : (
                        <X className="h-4 w-4 text-red-500 flex-shrink-0" />
                      )}
                      <div className="flex-1 min-w-0">
                        <p className="truncate font-medium">{item.file}</p>
                        {item.new_name && (
                          <p className="text-xs text-green-600 truncate">→ {item.new_name}</p>
                        )}
                        {item.reason && (
                          <p className="text-xs text-muted-foreground">{item.reason}</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          
          <DialogFooter>
            <Button onClick={() => setRenameDialog({ open: false, results: null })}>
              Fechar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog para NIF da Empresa (obrigatório para indexacao) */}
      <Dialog open={empresaNifDialog.open} onOpenChange={(open) => {
        if (!open) {
          setEmpresaNifDialog({ open: false, files: [], empresaNif: "", checking: false, existingProcesses: null });
          setPendingFiles(null);
          if (fileInputRef.current) {
            fileInputRef.current.value = "";
          }
        }
      }}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Building2 className="h-5 w-5 text-blue-600" />
              NIF da Empresa
            </DialogTitle>
            <DialogDescription>
              Para concluir o upload, é obrigatório indicar o NIF da empresa onde o cliente trabalha.
              <br />
              <span className="text-sm text-muted-foreground mt-1 block">
                {empresaNifDialog.files?.length || 0} ficheiro(s) selecionado(s) para upload.
              </span>
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">NIF da Empresa (9 dígitos)</label>
              <div className="flex gap-2">
                <Input
                  placeholder="Ex: 509123456"
                  value={empresaNifDialog.empresaNif}
                  onChange={(e) => setEmpresaNifDialog(prev => ({
                    ...prev,
                    empresaNif: e.target.value.replace(/\D/g, '').slice(0, 9)
                  }))}
                  maxLength={9}
                  className="flex-1"
                />
                <Button
                  variant="outline"
                  onClick={handleVerifyEmpresaNif}
                  disabled={empresaNifDialog.empresaNif.length !== 9 || empresaNifDialog.checking}
                >
                  {empresaNifDialog.checking ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Search className="h-4 w-4" />
                  )}
                  Verificar
                </Button>
              </div>
            </div>

            {/* Resultado da verificação */}
            {empresaNifDialog.existingProcesses && (
              <div className={`rounded-lg border p-4 ${
                empresaNifDialog.existingProcesses.exists 
                  ? 'bg-amber-50 border-amber-200 dark:bg-amber-950/30 dark:border-amber-800' 
                  : 'bg-green-50 border-green-200 dark:bg-green-950/30 dark:border-green-800'
              }`}>
                {empresaNifDialog.existingProcesses.exists ? (
                  <>
                    <div className="flex items-start gap-3">
                      <AlertTriangle className="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" />
                      <div>
                        <p className="font-medium text-amber-800 dark:text-amber-200">
                          Este NIF já foi utilizado em {empresaNifDialog.existingProcesses.total_count} processo(s)
                        </p>
                        <p className="text-sm text-amber-700 dark:text-amber-300 mt-1">
                          Documentos desta empresa já foram enviados para os seguintes balcões:
                        </p>
                      </div>
                    </div>
                    
                    <div className="mt-3 max-h-40 overflow-y-auto space-y-2">
                      {empresaNifDialog.existingProcesses.processes.map((proc, idx) => (
                        <div 
                          key={idx}
                          className="flex items-center justify-between p-2 rounded bg-white/50 dark:bg-black/20 border border-amber-100 dark:border-amber-900"
                        >
                          <div>
                            <p className="font-medium text-sm">{proc.client_name}</p>
                            {proc.employer_name && (
                              <p className="text-xs text-muted-foreground">{proc.employer_name}</p>
                            )}
                          </div>
                          <div className="text-right">
                            <Badge 
                              style={{ 
                                backgroundColor: proc.status_color || '#6B7280',
                                color: getContrastColor(proc.status_color),
                                fontSize: '10px'
                              }}
                            >
                              {proc.status_label}
                            </Badge>
                            {(proc.consultor_name || proc.mediador_name) && (
                              <p className="text-xs text-muted-foreground mt-1">
                                {proc.consultor_name || proc.mediador_name}
                              </p>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                    
                    <p className="text-xs text-amber-600 dark:text-amber-400 mt-3">
                      Pode prosseguir com o upload mesmo assim. Este aviso é apenas informativo.
                    </p>
                  </>
                ) : (
                  <div className="flex items-center gap-3">
                    <CheckCircle className="h-5 w-5 text-green-600" />
                    <div>
                      <p className="font-medium text-green-800 dark:text-green-200">
                        NIF não registado anteriormente
                      </p>
                      <p className="text-sm text-green-700 dark:text-green-300">
                        Este NIF de empresa ainda não foi utilizado em nenhum processo.
                      </p>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          <DialogFooter className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => {
                setEmpresaNifDialog({ open: false, files: [], empresaNif: "", checking: false, existingProcesses: null });
                setPendingFiles(null);
                if (fileInputRef.current) {
                  fileInputRef.current.value = "";
                }
              }}
            >
              Cancelar
            </Button>
            <Button
              onClick={handleConfirmUploadWithNif}
              disabled={empresaNifDialog.empresaNif.length !== 9}
              className="bg-teal-600 hover:bg-teal-700"
            >
              <Upload className="h-4 w-4 mr-2" />
              Confirmar Upload
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Diálogo de renomeação manual */}
      <Dialog open={manualRenameDialog.open} onOpenChange={(open) => {
        if (!open) {
          setManualRenameDialog({ open: false, file: null, newName: "" });
        }
      }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Pencil className="h-5 w-5 text-blue-600" />
              Renomear Ficheiro
            </DialogTitle>
            <DialogDescription>
              Introduza o novo nome para "{manualRenameDialog.file?.name}".
              <br />
              <span className="text-xs text-muted-foreground">
                A extensão será mantida automaticamente.
              </span>
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Novo nome</label>
              <Input
                placeholder="Introduza o novo nome..."
                value={manualRenameDialog.newName}
                onChange={(e) => setManualRenameDialog(prev => ({
                  ...prev,
                  newName: e.target.value
                }))}
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && manualRenameDialog.newName.trim()) {
                    handleManualRename();
                  }
                }}
              />
            </div>
          </div>

          <DialogFooter className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => setManualRenameDialog({ open: false, file: null, newName: "" })}
              disabled={manualRenaming}
            >
              Cancelar
            </Button>
            <Button
              onClick={handleManualRename}
              disabled={!manualRenameDialog.newName.trim() || manualRenaming}
              className="bg-blue-600 hover:bg-blue-700"
            >
              {manualRenaming ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Pencil className="h-4 w-4 mr-2" />
              )}
              Renomear
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Diálogo de resultados da organização */}
      <Dialog open={!!organizeResults} onOpenChange={(open) => !open && setOrganizeResults(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FolderSync className="h-5 w-5 text-teal-600" />
              Organização Completa
            </DialogTitle>
            <DialogDescription>
              Os documentos foram analisados e organizados automaticamente.
            </DialogDescription>
          </DialogHeader>
          
          {organizeResults && (
            <div className="space-y-4 py-4">
              {/* Resumo */}
              <div className="grid grid-cols-2 gap-3">
                <div className="text-center p-3 bg-muted rounded-lg">
                  <p className="text-2xl font-bold text-blue-600">{organizeResults.analyzed}</p>
                  <p className="text-xs text-muted-foreground">Analisados</p>
                </div>
                <div className="text-center p-3 bg-teal-50 dark:bg-teal-950/30 rounded-lg">
                  <p className="text-2xl font-bold text-teal-600">{organizeResults.organized}</p>
                  <p className="text-xs text-teal-600">Organizados</p>
                </div>
              </div>

              {/* Categorias encontradas */}
              {organizeResults.categories?.length > 0 && (
                <div className="space-y-2">
                  <p className="text-sm font-medium">Categorias identificadas:</p>
                  <div className="flex flex-wrap gap-1">
                    {organizeResults.categories.map((cat, idx) => (
                      <Badge key={idx} variant="outline" className="text-xs">
                        {cat}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              {/* Detalhes */}
              {organizeResults.details?.length > 0 && (
                <div className="border rounded-lg max-h-40 overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead className="bg-muted sticky top-0">
                      <tr>
                        <th className="text-left p-2">Ficheiro</th>
                        <th className="text-left p-2">Pasta</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {organizeResults.details.slice(0, 10).map((item, idx) => (
                        <tr key={idx}>
                          <td className="p-2 truncate max-w-[150px]">{item.filename || item.file_name}</td>
                          <td className="p-2">{item.target_folder || item.category}</td>
                        </tr>
                      ))}
                      {organizeResults.details.length > 10 && (
                        <tr>
                          <td colSpan={2} className="p-2 text-center text-muted-foreground">
                            +{organizeResults.details.length - 10} mais...
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          <DialogFooter>
            <Button onClick={() => setOrganizeResults(null)} className="bg-teal-600 hover:bg-teal-700">
              Fechar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Diálogo de conflitos de upload (ficheiros duplicados) */}
      <Dialog open={uploadConflictDialog.open} onOpenChange={(open) => {
        if (!open) handleCancelUpload();
      }}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-amber-600">
              <AlertTriangle className="h-5 w-5" />
              Ficheiro Duplicado Detetado
            </DialogTitle>
            <DialogDescription>
              Já existe um ficheiro com o mesmo nome no destino.
              Escolha como pretende resolver este conflito.
            </DialogDescription>
          </DialogHeader>

          {uploadConflictDialog.conflicts.length > 0 && (
            <>
              {/* Indicador de progresso */}
              {uploadConflictDialog.conflicts.length > 1 && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground mb-2">
                  <span>
                    Conflito {uploadConflictDialog.currentConflictIndex + 1} de {uploadConflictDialog.conflicts.length}
                  </span>
                  <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-amber-500 transition-all"
                      style={{ 
                        width: `${((uploadConflictDialog.currentConflictIndex + 1) / uploadConflictDialog.conflicts.length) * 100}%` 
                      }}
                    />
                  </div>
                </div>
              )}

              {/* Conflito atual */}
              {(() => {
                const conflict = uploadConflictDialog.conflicts[uploadConflictDialog.currentConflictIndex];
                const resolution = uploadConflictDialog.resolutions?.[uploadConflictDialog.currentConflictIndex];
                
                if (!conflict) return null;
                
                return (
                  <div className="space-y-4 py-4">
                    {/* Info do ficheiro */}
                    <div className="p-4 bg-amber-50 dark:bg-amber-950/30 rounded-lg border border-amber-200 dark:border-amber-800">
                      <div className="flex items-start gap-3">
                        <FileText className="h-8 w-8 text-amber-600 flex-shrink-0" />
                        <div className="flex-1 min-w-0">
                          <p className="font-medium text-amber-800 dark:text-amber-200 truncate">
                            {conflict.original_filename}
                          </p>
                          <p className="text-sm text-amber-700 dark:text-amber-300">
                            Já existe um ficheiro com este nome na categoria "{uploadConflictDialog.category}"
                          </p>
                        </div>
                      </div>
                    </div>

                    {/* Opções de resolução */}
                    <div className="space-y-3">
                      <p className="text-sm font-medium">Escolha uma ação:</p>
                      
                      {/* Opção: Substituir */}
                      <label className={`
                        flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-all
                        ${resolution?.action === 'overwrite' 
                          ? 'border-red-500 bg-red-50 dark:bg-red-950/30' 
                          : 'border-gray-200 hover:border-gray-300 dark:border-gray-700'
                        }
                      `}>
                        <input
                          type="radio"
                          name="conflict-action"
                          checked={resolution?.action === 'overwrite'}
                          onChange={() => handleConflictResolution('overwrite')}
                          className="mt-1"
                        />
                        <div>
                          <p className="font-medium text-red-700 dark:text-red-300">
                            Substituir ficheiro existente
                          </p>
                          <p className="text-sm text-muted-foreground">
                            O ficheiro atual será eliminado e substituído pelo novo
                          </p>
                        </div>
                      </label>

                      {/* Opção: Renomear */}
                      <label className={`
                        flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-all
                        ${resolution?.action === 'rename' 
                          ? 'border-blue-500 bg-blue-50 dark:bg-blue-950/30' 
                          : 'border-gray-200 hover:border-gray-300 dark:border-gray-700'
                        }
                      `}>
                        <input
                          type="radio"
                          name="conflict-action"
                          checked={resolution?.action === 'rename'}
                          onChange={() => {
                            // Selecionar o primeiro nome sugerido automaticamente
                            const suggested = conflict.suggested_names?.[0]?.filename;
                            handleConflictResolution('rename', suggested || null);
                          }}
                          className="mt-1"
                        />
                        <div className="flex-1">
                          <p className="font-medium text-blue-700 dark:text-blue-300">
                            Guardar com nome diferente
                          </p>
                          <p className="text-sm text-muted-foreground mb-2">
                            O ficheiro será guardado com um novo nome
                          </p>
                          
                          {/* Seleção de nome */}
                          {resolution?.action === 'rename' && conflict.suggested_names?.length > 0 && (
                            <select
                              value={resolution.customName || ''}
                              onChange={(e) => handleConflictResolution('rename', e.target.value)}
                              className="w-full text-sm p-2 border rounded bg-white dark:bg-gray-800"
                            >
                              {conflict.suggested_names.map((s, idx) => (
                                <option key={idx} value={s.filename}>{s.filename}</option>
                              ))}
                            </select>
                          )}
                        </div>
                      </label>

                      {/* Opção: Ignorar */}
                      <label className={`
                        flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-all
                        ${resolution?.action === 'skip' 
                          ? 'border-gray-500 bg-gray-50 dark:bg-gray-800' 
                          : 'border-gray-200 hover:border-gray-300 dark:border-gray-700'
                        }
                      `}>
                        <input
                          type="radio"
                          name="conflict-action"
                          checked={resolution?.action === 'skip'}
                          onChange={() => handleConflictResolution('skip')}
                          className="mt-1"
                        />
                        <div>
                          <p className="font-medium text-gray-700 dark:text-gray-300">
                            Ignorar este ficheiro
                          </p>
                          <p className="text-sm text-muted-foreground">
                            O ficheiro não será enviado e o existente será mantido
                          </p>
                        </div>
                      </label>
                    </div>
                  </div>
                );
              })()}
            </>
          )}

          <DialogFooter className="flex gap-2">
            <Button
              variant="outline"
              onClick={handleCancelUpload}
            >
              Cancelar Tudo
            </Button>
            <Button
              onClick={handleNextConflict}
              disabled={!uploadConflictDialog.resolutions?.[uploadConflictDialog.currentConflictIndex]?.action}
              className="bg-amber-600 hover:bg-amber-700"
            >
              {uploadConflictDialog.currentConflictIndex < uploadConflictDialog.conflicts.length - 1 
                ? 'Próximo' 
                : 'Continuar Upload'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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
    </>
  );
};

export default S3FileManager;
