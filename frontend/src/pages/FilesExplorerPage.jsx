/**
 * FilesExplorerPage — Explorador de Ficheiros (File Explorer).
 *
 * Página de ecrã inteiro para navegar, pesquisar e gerir ficheiros
 * armazenados no S3. Substitui a antiga DocumentsPage que era apenas
 * um placeholder sem funcionalidade.
 *
 * INTEGRAÇÃO:
 * - Usa o endpoint /api/admin/s3-folder-contents para listar pastas e ficheiros.
 * - Breadcrumb de navegação hierárquica (duplo clique em pastas).
 * - Upload, download, rename e delete de ficheiros.
 * - Barra de pesquisa em tempo real.
 * - Vista de tabela com colunas: Ícone, Nome, Tamanho, Data, Ações.
 *
 * ACESSO:
 * - Todos os utilizadores autenticados podem aceder ao explorador S3.
 * - Consultores/Intermediários têm acesso de leitura e download.
 * - Admin/CEO/Diretor/Administrativo têm acesso total (upload, rename, delete).
 */
import React, { useState, useCallback, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { useAuth } from "../contexts/AuthContext";
import { hasAnyRole } from "../utils/roleUtils";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Badge } from "../components/ui/badge";
import { Skeleton } from "../components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../components/ui/table";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "../components/ui/breadcrumb";
import {
  Upload,
  Search,
  RefreshCw,
  Folder,
  FolderOpen,
  FileText,
  FileImage,
  FileSpreadsheet,
  File,
  Download,
  Pencil,
  Trash2,
  MoreVertical,
  ChevronRight,
  HardDrive,
  FolderPlus,
  AlertCircle,
  Loader2,
  Home,
  ArrowUp,
  Settings,
  CloudOff,
} from "lucide-react";
import { toast } from "sonner";
import { format, parseISO } from "date-fns";
import { pt } from "date-fns/locale";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// ── Helpers ────────────────────────────────────────────────────────────────

const formatFileSize = (bytes) => {
  if (!bytes || bytes === 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
};

const formatDate = (dateStr) => {
  if (!dateStr) return "—";
  try {
    return format(parseISO(dateStr), "dd/MM/yyyy HH:mm", { locale: pt });
  } catch {
    return dateStr;
  }
};

const FileIcon = ({ filename, isFolder }) => {
  if (isFolder) return <Folder className="h-5 w-5 text-amber-500" />;
  const ext = filename?.split(".").pop()?.toLowerCase();
  if (["jpg", "jpeg", "png", "gif", "webp", "svg", "bmp", "heic"].includes(ext)) {
    return <FileImage className="h-5 w-5 text-pink-500" />;
  }
  if (["xls", "xlsx", "csv"].includes(ext)) {
    return <FileSpreadsheet className="h-5 w-5 text-emerald-600" />;
  }
  if (["pdf"].includes(ext)) {
    return <FileText className="h-5 w-5 text-red-500" />;
  }
  if (["doc", "docx", "txt", "rtf"].includes(ext)) {
    return <FileText className="h-5 w-5 text-blue-500" />;
  }
  return <File className="h-5 w-5 text-muted-foreground" />;
};

// ── Component ──────────────────────────────────────────────────────────────

const FilesExplorerPage = () => {
  const { token, user } = useAuth();
  const navigate = useNavigate();

  const isFullAccess = hasAnyRole(user, ["admin", "ceo", "diretor", "administrativo"]);
  const canViewExplorer = hasAnyRole(user, ["admin", "ceo", "diretor", "administrativo", "consultor", "intermediario", "consultor_intermediario", "indexacao"]);

  // ── State ──────────────────────────────────────────────────────────────────
  const [currentPath, setCurrentPath] = useState("");
  const [breadcrumb, setBreadcrumb] = useState([{ label: "Raiz", path: "" }]);
  const [folders, setFolders] = useState([]);
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

  // Rename dialog
  const [renameDialog, setRenameDialog] = useState({ open: false, item: null, newName: "" });
  const [renaming, setRenaming] = useState(false);

  // Delete dialog
  const [deleteDialog, setDeleteDialog] = useState({ open: false, item: null });
  const [deleting, setDeleting] = useState(false);

  // New folder dialog
  const [newFolderDialog, setNewFolderDialog] = useState({ open: false, name: "" });
  const [creatingFolder, setCreatingFolder] = useState(false);

  // S3 configuration state
  const [s3Configured, setS3Configured] = useState(null); // null = loading, true/false
  const [configDialog, setConfigDialog] = useState({ open: false });
  const [configLoading, setConfigLoading] = useState(false);

  const fileInputRef = useRef(null);
  const searchTimeoutRef = useRef(null);

  // ── Fetch folder contents ─────────────────────────────────────────────────
  const fetchContents = useCallback(async (path) => {
    if (!token) return;
    setLoading(true);
    try {
      const res = await fetch(
        `${API_URL}/api/admin/s3-folder-contents?folder_path=${encodeURIComponent(path || "")}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (res.ok) {
        const data = await res.json();
        console.log("Arquivos carregados:", data);
        setS3Configured(true);
        setFolders(data.subfolders || []);
        setFiles(data.files || []);
      } else {
        const err = await res.json().catch(() => ({}));
        console.error("Erro ao carregar ficheiros:", res.status, err);
        if (res.status === 403) {
          toast.error("Sem permissões para aceder ao explorador de ficheiros.");
        } else if (res.status === 503) {
          setS3Configured(false);
        } else {
          toast.error(err.detail || "Erro ao carregar ficheiros");
        }
      }
    } catch (err) {
      console.error("Erro fetchContents:", err);
      toast.error("Erro de ligação ao servidor");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchContents(currentPath);
  }, [currentPath, fetchContents]);

  // ── Navigation ───────────────────────────────────────────────────────────
  const navigateToFolder = (folderPath) => {
    const parts = folderPath.split("/");
    const newBreadcrumb = parts.map((part, idx) => ({
      label: part,
      path: parts.slice(0, idx + 1).join("/"),
    }));
    // Add root if not already there
    if (newBreadcrumb.length === 0 || newBreadcrumb[0].path !== "") {
      newBreadcrumb.unshift({ label: "Raiz", path: "" });
    }
    setBreadcrumb(newBreadcrumb);
    setCurrentPath(folderPath);
    setSearchQuery("");
  };

  const navigateToBreadcrumb = (crumb) => {
    if (crumb.path === "") {
      setBreadcrumb([{ label: "Raiz", path: "" }]);
      setCurrentPath("");
    } else {
      // Rebuild breadcrumb up to this level
      const newBreadcrumb = [{ label: "Raiz", path: "" }];
      const parts = crumb.path.split("/");
      parts.forEach((part, idx) => {
        newBreadcrumb.push({
          label: part,
          path: parts.slice(0, idx + 1).join("/"),
        });
      });
      setBreadcrumb(newBreadcrumb);
      setCurrentPath(crumb.path);
    }
    setSearchQuery("");
  };

  const navigateUp = () => {
    if (currentPath === "") return;
    const parentParts = currentPath.split("/").slice(0, -1);
    const parentPath = parentParts.join("/");
    navigateToBreadcrumb({ label: parentParts[parentParts.length - 1] || "Raiz", path: parentPath });
  };

  // ── Upload ────────────────────────────────────────────────────────────────
  const handleUpload = async (e) => {
    const selectedFiles = Array.from(e.target.files || []);
    if (selectedFiles.length === 0) return;
    setUploading(true);
    setUploadProgress(0);

    let successCount = 0;
    let errorCount = 0;

    for (let i = 0; i < selectedFiles.length; i++) {
      const file = selectedFiles[i];
      const formData = new FormData();
      formData.append("file", file);
      formData.append("folder_path", currentPath);

      try {
        const res = await fetch(
          `${API_URL}/api/admin/s3-upload`,
          {
            method: "POST",
            headers: { Authorization: `Bearer ${token}` },
            body: formData,
          }
        );

        if (res.ok) {
          successCount++;
        } else {
          const err = await res.json().catch(() => ({}));
          toast.error(`${file.name}: ${err.detail || "Erro"}`);
          errorCount++;
        }
      } catch (err) {
        toast.error(`Erro ao enviar ${file.name}`);
        errorCount++;
      }

      setUploadProgress(Math.round(((i + 1) / selectedFiles.length) * 100));
    }

    if (successCount > 0) {
      toast.success(`${successCount} ficheiro(s) enviado(s)`);
      fetchContents(currentPath);
    }
    if (errorCount > 0) {
      toast.error(`${errorCount} ficheiro(s) com erro`);
    }

    setUploading(false);
    setUploadProgress(0);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  // ── Download ─────────────────────────────────────────────────────────────
  const handleDownload = async (file) => {
    try {
      const res = await fetch(
        `${API_URL}/api/admin/s3-download?path=${encodeURIComponent(file.path)}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = file.name || "download";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || "Erro ao fazer download");
      }
    } catch (err) {
      toast.error("Erro ao fazer download");
    }
  };

  // ── Rename ────────────────────────────────────────────────────────────────
  const openRenameDialog = (item) => {
    setRenameDialog({ open: true, item, newName: item.name });
  };

  const handleRename = async () => {
    if (!renameDialog.item || !renameDialog.newName.trim()) return;
    setRenaming(true);
    try {
      // S3 rename = copy + delete (or use rename API if exists)
      const res = await fetch(
        `${API_URL}/api/admin/s3-rename`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            old_path: renameDialog.item.path || `${renameDialog.item.path}/`,
            new_name: renameDialog.newName.trim(),
            is_folder: !!renameDialog.item.isFolder,
          }),
        }
      );
      if (res.ok) {
        toast.success("Renomeado com sucesso");
        fetchContents(currentPath);
        setRenameDialog({ open: false, item: null, newName: "" });
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || "Erro ao renomear");
      }
    } catch {
      toast.error("Erro ao renomear");
    } finally {
      setRenaming(false);
    }
  };

  // ── Delete ────────────────────────────────────────────────────────────────
  const openDeleteDialog = (item) => {
    setDeleteDialog({ open: true, item });
  };

  const handleDelete = async () => {
    if (!deleteDialog.item) return;
    setDeleting(true);
    try {
      const res = await fetch(
        `${API_URL}/api/admin/s3-delete`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            path: deleteDialog.item.path,
            is_folder: !!deleteDialog.item.isFolder,
          }),
        }
      );
      if (res.ok) {
        toast.success(deleteDialog.item.isFolder ? "Pasta eliminada" : "Ficheiro eliminado");
        fetchContents(currentPath);
        setDeleteDialog({ open: false, item: null });
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || "Erro ao eliminar");
      }
    } catch {
      toast.error("Erro ao eliminar");
    } finally {
      setDeleting(false);
    }
  };

  // ── New Folder ─────────────────────────────────────────────────────────────
  const handleCreateFolder = async () => {
    if (!newFolderDialog.name.trim()) return;
    setCreatingFolder(true);
    try {
      const folderPath = currentPath
        ? `${currentPath}/${newFolderDialog.name.trim()}/`
        : `${newFolderDialog.name.trim()}/`;
      const res = await fetch(
        `${API_URL}/api/admin/s3-create-folder`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ folder_path: folderPath }),
        }
      );
      if (res.ok) {
        toast.success("Pasta criada com sucesso");
        fetchContents(currentPath);
        setNewFolderDialog({ open: false, name: "" });
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || "Erro ao criar pasta");
      }
    } catch {
      toast.error("Erro ao criar pasta");
    } finally {
      setCreatingFolder(false);
    }
  };

  // ── Save S3 Configuration ─────────────────────────────────────────────
  const handleSaveConfig = async (settings) => {
    setConfigLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/admin/settings`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          s3_bucket: settings.bucket,
          s3_region: settings.region,
          s3_access_key: settings.accessKey,
          s3_secret_key: settings.secretKey,
        }),
      });
      if (res.ok) {
        toast.success("Configuração S3 guardada com sucesso");
        setConfigDialog({ open: false });
        setS3Configured(null);
        fetchContents(currentPath);
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || "Erro ao guardar configuração");
      }
    } catch {
      toast.error("Erro de ligação ao servidor");
    } finally {
      setConfigLoading(false);
    }
  };

  // ── Search ────────────────────────────────────────────────────────────────
  const handleSearch = (value) => {
    setSearchQuery(value);
    if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current);
    searchTimeoutRef.current = setTimeout(() => {
      // Search is client-side filtering for now
    }, 300);
  };

  const filteredFolders = searchQuery.trim()
    ? folders.filter((f) => f.name.toLowerCase().includes(searchQuery.toLowerCase()))
    : folders;
  const filteredFiles = searchQuery.trim()
    ? files.filter((f) => f.name.toLowerCase().includes(searchQuery.toLowerCase()))
    : files;

  // ── Sort: folders first, then files alphabetically ───────────────────────
  const sortedFolders = [...filteredFolders].sort((a, b) => a.name.localeCompare(b.name));
  const sortedFiles = [...filteredFiles].sort((a, b) => a.name.localeCompare(b.name));

  // ── S3 Not Configured Banner ─────────────────────────────────────────
  const S3NotConfiguredBanner = () => (
    <Card className="border-amber-300 bg-amber-50 dark:bg-amber-950/20">
      <CardContent className="py-6">
        <div className="flex flex-col items-center justify-center text-center space-y-4">
          <div className="h-16 w-16 rounded-full bg-amber-100 dark:bg-amber-900/40 flex items-center justify-center">
            <CloudOff className="h-8 w-8 text-amber-600 dark:text-amber-400" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-amber-800 dark:text-amber-200">
              Armazenamento S3 Não Configurado
            </h3>
            <p className="text-sm text-amber-700 dark:text-amber-300 mt-1 max-w-md">
              O Explorador de Ficheiros necessita de credenciais S3 (Amazon S3, MinIO ou compatível) para funcionar.
              Configure o acesso nas Definições Gerais do sistema.
            </p>
          </div>
          <div className="flex items-center gap-3">
            {isFullAccess && (
              <Button
                variant="outline"
                onClick={() => setConfigDialog({ open: true })}
                className="gap-2"
              >
                <Settings className="h-4 w-4" />
                Configurar Agora
              </Button>
            )}
            <Button
              variant="ghost"
              onClick={() => navigate(isFullAccess ? "/configuracoes" : "/definicoes")}
              className="gap-2"
            >
              Ir para Configurações
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );

  // ── Restricted access for non-staff ─────────────────────────────────────
  if (!canViewExplorer) {
    return (
      <DashboardLayout title="Ficheiros">
        <div className="space-y-6 max-w-lg">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <HardDrive className="h-6 w-6 text-primary" />
              Explorador de Ficheiros
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Gestão global de ficheiros armazenados no sistema.
            </p>
          </div>

          <Card>
            <CardContent className="pt-6">
              <div className="flex items-start gap-4 p-4 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded-lg">
                <AlertCircle className="h-5 w-5 text-amber-600 mt-0.5 shrink-0" />
                <div className="space-y-1">
                  <p className="text-sm font-medium text-amber-800 dark:text-amber-200">
                    Acesso Restrito
                  </p>
                  <p className="text-sm text-amber-700 dark:text-amber-300">
                    Não tem permissões para aceder ao Explorador de Ficheiros.
                    Para gerir os ficheiros dos seus processos, aceda à página de detalhes do processo.
                  </p>
                  <Button
                    variant="outline"
                    size="sm"
                    className="mt-2"
                    onClick={() => navigate("/processos")}
                  >
                    Ir para Processos
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </DashboardLayout>
    );
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <DashboardLayout title="Ficheiros">
      <div className="space-y-4">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <HardDrive className="h-6 w-6 text-primary" />
              Explorador de Ficheiros
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Navegue e gere os ficheiros armazenados no S3.
            </p>
          </div>
          <div className="flex items-center gap-2">
            {isFullAccess && (
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={() => setConfigDialog({ open: true })}
              >
                <Settings className="h-4 w-4" />
                <span className="hidden sm:inline">Configuração</span>
              </Button>
            )}
          </div>
        </div>

        {/* Breadcrumb */}
        <Breadcrumb>
          <BreadcrumbList>
            {breadcrumb.map((crumb, idx) => {
              const isLast = idx === breadcrumb.length - 1;
              return (
                <React.Fragment key={crumb.path}>
                  {idx > 0 && <BreadcrumbSeparator />}
                  <BreadcrumbItem>
                    {isLast ? (
                      <BreadcrumbPage className="font-medium">{crumb.label}</BreadcrumbPage>
                    ) : (
                      <button
                        onClick={() => navigateToBreadcrumb(crumb)}
                        className="text-muted-foreground hover:text-foreground transition-colors text-sm"
                      >
                        {crumb.label}
                      </button>
                    )}
                  </BreadcrumbItem>
                </React.Fragment>
              );
            })}
          </BreadcrumbList>
        </Breadcrumb>

        {/* Action Bar */}
        <Card>
          <CardContent className="py-3">
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
              {/* Search */}
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Pesquisar ficheiros e pastas..."
                  className="pl-9 h-9"
                  value={searchQuery}
                  onChange={(e) => handleSearch(e.target.value)}
                />
              </div>

              {/* Actions */}
              <div className="flex items-center gap-2">
                {isFullAccess && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-1.5"
                    onClick={() => setNewFolderDialog({ open: true, name: "" })}
                  >
                    <FolderPlus className="h-4 w-4" />
                    <span className="hidden sm:inline">Nova Pasta</span>
                  </Button>
                )}
                {isFullAccess && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-1.5"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploading}
                  >
                    {uploading ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Upload className="h-4 w-4" />
                    )}
                    <span className="hidden sm:inline">{uploading ? "A enviar..." : "Upload"}</span>
                  </Button>
                )}
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-9 w-9"
                  onClick={() => fetchContents(currentPath)}
                  disabled={loading}
                >
                  <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
                </Button>
                {currentPath && (
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-9 w-9"
                    onClick={navigateUp}
                    title="Pasta superior"
                  >
                    <ArrowUp className="h-4 w-4" />
                  </Button>
                )}
              </div>
            </div>

            {/* Upload progress bar */}
            {uploading && (
              <div className="mt-2">
                <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
                  <div
                    className="h-full bg-primary transition-all duration-300"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
                <p className="text-xs text-muted-foreground mt-1">{uploadProgress}% concluído</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* S3 Not Configured Fallback */}
        {s3Configured === false && <S3NotConfiguredBanner />}

        {/* Empty State with helpful message */}
        {!loading && s3Configured !== false && sortedFolders.length === 0 && sortedFiles.length === 0 && (
          <Card className="border-dashed">
            <CardContent className="py-12">
              <div className="flex flex-col items-center justify-center text-center space-y-3">
                <div className="h-14 w-14 rounded-full bg-muted/50 flex items-center justify-center">
                  <Folder className="h-7 w-7 text-muted-foreground/40" />
                </div>
                <div>
                  <p className="font-medium text-muted-foreground">Nenhum ficheiro encontrado</p>
                  <p className="text-sm text-muted-foreground/70 mt-1">
                    Verifique as configurações de armazenamento nas Definições Gerais.<br />
                    {!currentPath && "Certifique-se de que o caminho base (Base Path) está correto."}
                  </p>
                </div>
                <div className="flex items-center gap-2 mt-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => fetchContents(currentPath)}
                    disabled={loading}
                    className="gap-1.5"
                  >
                    <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
                    Tentar Novamente
                  </Button>
                  {isFullAccess && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setConfigDialog({ open: true })}
                      className="gap-1.5"
                    >
                      <Settings className="h-3.5 w-3.5" />
                      Verificar Configuração
                    </Button>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* File Table — hidden when S3 not configured or empty (fallback shown above) */}
        {s3Configured !== false && (sortedFolders.length > 0 || sortedFiles.length > 0 || loading) && (
        <Card>
          <CardContent className="p-0">
            <div className="rounded-md border overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="bg-muted/50 hover:bg-muted/50">
                    <TableHead className="w-10" />
                    <TableHead>Nome</TableHead>
                    <TableHead className="w-24 hidden sm:table-cell">Tamanho</TableHead>
                    <TableHead className="w-40 hidden md:table-cell">Data de Modificação</TableHead>
                    <TableHead className="w-12" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {loading ? (
                    <>
                      <TableRow><TableCell colSpan={5}><Skeleton className="h-10" /></TableCell></TableRow>
                      <TableRow><TableCell colSpan={5}><Skeleton className="h-10" /></TableCell></TableRow>
                      <TableRow><TableCell colSpan={5}><Skeleton className="h-10" /></TableCell></TableRow>
                      <TableRow><TableCell colSpan={5}><Skeleton className="h-10" /></TableCell></TableRow>
                      <TableRow><TableCell colSpan={5}><Skeleton className="h-10" /></TableCell></TableRow>
                    </>
                  ) : sortedFolders.length === 0 && sortedFiles.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5}>
                        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
                          <Folder className="h-12 w-12 mb-3 opacity-30" />
                          <p className="text-sm font-medium">
                            {searchQuery ? "Nenhum resultado encontrado" : "Pasta vazia"}
                          </p>
                          <p className="text-xs mt-1">
                            {searchQuery
                              ? `Nenhum ficheiro ou pasta corresponde a "${searchQuery}"`
                              : "Envie ficheiros ou crie uma pasta para começar"}
                          </p>
                        </div>
                      </TableCell>
                    </TableRow>
                  ) : (
                    <>
                      {/* Folders */}
                      {sortedFolders.map((folder) => (
                        <TableRow
                          key={`folder-${folder.path}`}
                          className="cursor-pointer hover:bg-muted/50 transition-colors"
                          onDoubleClick={() => navigateToFolder(folder.path)}
                        >
                          <TableCell className="w-10 pl-3">
                            <Folder className="h-5 w-5 text-amber-500" />
                          </TableCell>
                          <TableCell>
                            <div className="flex items-center gap-2">
                              <span className="font-medium text-sm">{folder.name}</span>
                              <Badge variant="secondary" className="text-[10px] px-1.5 hidden sm:inline-flex">
                                Pasta
                              </Badge>
                            </div>
                          </TableCell>
                          <TableCell className="text-sm text-muted-foreground hidden sm:table-cell">—</TableCell>
                          <TableCell className="text-sm text-muted-foreground hidden md:table-cell">—</TableCell>
                          <TableCell className="text-right pr-3">
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <Button variant="ghost" size="icon" className="h-8 w-8">
                                  <MoreVertical className="h-4 w-4" />
                                </Button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="end">
                                <DropdownMenuItem onClick={() => navigateToFolder(folder.path)}>
                                  <ChevronRight className="h-4 w-4 mr-2" />
                                  Abrir
                                </DropdownMenuItem>
                                {isFullAccess && (
                                  <>
                                    <DropdownMenuSeparator />
                                    <DropdownMenuItem
                                      onClick={() => openRenameDialog({ ...folder, isFolder: true })}
                                    >
                                      <Pencil className="h-4 w-4 mr-2" />
                                      Renomear
                                    </DropdownMenuItem>
                                    <DropdownMenuItem
                                      onClick={() => openDeleteDialog({ ...folder, isFolder: true })}
                                      className="text-destructive"
                                    >
                                      <Trash2 className="h-4 w-4 mr-2" />
                                      Eliminar
                                    </DropdownMenuItem>
                                  </>
                                )}
                              </DropdownMenuContent>
                            </DropdownMenu>
                          </TableCell>
                        </TableRow>
                      ))}

                      {/* Files */}
                      {sortedFiles.map((file) => (
                        <TableRow
                          key={`file-${file.path}`}
                          className="hover:bg-muted/50 transition-colors"
                        >
                          <TableCell className="w-10 pl-3">
                            <FileIcon filename={file.name} />
                          </TableCell>
                          <TableCell>
                            <span className="text-sm">{file.name}</span>
                          </TableCell>
                          <TableCell className="text-sm text-muted-foreground hidden sm:table-cell">
                            {formatFileSize(file.size)}
                          </TableCell>
                          <TableCell className="text-sm text-muted-foreground hidden md:table-cell">
                            {formatDate(file.last_modified)}
                          </TableCell>
                          <TableCell className="text-right pr-3">
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <Button variant="ghost" size="icon" className="h-8 w-8">
                                  <MoreVertical className="h-4 w-4" />
                                </Button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="end">
                                <DropdownMenuItem onClick={() => handleDownload(file)}>
                                  <Download className="h-4 w-4 mr-2" />
                                  Download
                                </DropdownMenuItem>
                                {isFullAccess && (
                                  <>
                                    <DropdownMenuSeparator />
                                    <DropdownMenuItem onClick={() => openRenameDialog(file)}>
                                      <Pencil className="h-4 w-4 mr-2" />
                                      Renomear
                                    </DropdownMenuItem>
                                    <DropdownMenuItem
                                      onClick={() => openDeleteDialog(file)}
                                      className="text-destructive"
                                    >
                                      <Trash2 className="h-4 w-4 mr-2" />
                                      Eliminar
                                    </DropdownMenuItem>
                                  </>
                                )}
                              </DropdownMenuContent>
                            </DropdownMenu>
                          </TableCell>
                        </TableRow>
                      ))}
                    </>
                  )}
                </TableBody>
              </Table>
            </div>

            {/* Footer info */}
            {!loading && (sortedFolders.length > 0 || sortedFiles.length > 0) && (
              <div className="flex items-center justify-between px-4 py-2 border-t text-xs text-muted-foreground">
                <span>
                  {sortedFolders.length} pasta{sortedFolders.length !== 1 ? "s" : ""}, {sortedFiles.length} ficheiro{sortedFiles.length !== 1 ? "s" : ""}
                  {searchQuery && ` (filtrados por "${searchQuery}")`}
                </span>
                <span>
                  {folders.length + files.length} item{folders.length + files.length !== 1 ? "s" : ""} no total
                </span>
              </div>
            )}
          </CardContent>
        </Card>
        )}
      </div>

      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={handleUpload}
      />

      {/* Rename Dialog */}
      <Dialog open={renameDialog.open} onOpenChange={(open) => !open && setRenameDialog({ open: false, item: null, newName: "" })}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Renomear</DialogTitle>
            <DialogDescription>
              {renameDialog.item?.isFolder ? "Introduza o novo nome da pasta." : "Introduza o novo nome do ficheiro."}
            </DialogDescription>
          </DialogHeader>
          <Input
            value={renameDialog.newName}
            onChange={(e) => setRenameDialog((prev) => ({ ...prev, newName: e.target.value }))}
            placeholder="Novo nome"
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter") handleRename();
            }}
          />
          <DialogFooter className="mt-4">
            <Button variant="outline" onClick={() => setRenameDialog({ open: false, item: null, newName: "" })}>
              Cancelar
            </Button>
            <Button onClick={handleRename} disabled={renaming || !renameDialog.newName.trim()}>
              {renaming ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
              Guardar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialog.open} onOpenChange={(open) => !open && setDeleteDialog({ open: false, item: null })}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Confirmar Eliminação</DialogTitle>
            <DialogDescription>
              Tem a certeza que deseja eliminar{" "}
              <strong>{deleteDialog.item?.isFolder ? `a pasta "${deleteDialog.item?.name}"` : `o ficheiro "${deleteDialog.item?.name}"}`}</strong>?
              Esta ação não pode ser desfeita.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="mt-4">
            <Button variant="outline" onClick={() => setDeleteDialog({ open: false, item: null })}>
              Cancelar
            </Button>
            <Button variant="destructive" onClick={handleDelete} disabled={deleting}>
              {deleting ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
              Eliminar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* S3 Configuration Dialog */}
      <Dialog open={configDialog.open} onOpenChange={(open) => setConfigDialog({ open })}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Settings className="h-5 w-5" />
              Configuração do Armazenamento
            </DialogTitle>
            <DialogDescription>
              Configure as credenciais S3 para ativar o Explorador de Ficheiros.
              Pode usar Amazon S3, MinIO ou qualquer serviço compatível com S3.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="p-3 bg-muted/50 rounded-lg">
              <p className="text-sm text-muted-foreground">
                As credenciais S3 também podem ser configuradas na página de{" "}
                <button
                  onClick={() => { setConfigDialog({ open: false }); navigate("/configuracoes"); }}
                  className="text-primary underline hover:no-underline"
                >
                  Definições Gerais
                </button>.
              </p>
            </div>
            <div className="space-y-3">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Bucket</label>
                  <Input placeholder="nome-do-bucket" />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Região</label>
                  <Input placeholder="eu-west-1" />
                </div>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Access Key ID</label>
                <Input placeholder="AKIAIOSFODNN7EXAMPLE" type="password" />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Secret Access Key</label>
                <Input placeholder="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY" type="password" />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfigDialog({ open: false })}>
              Cancelar
            </Button>
            <Button onClick={() => navigate("/configuracoes")} className="gap-2">
              <Settings className="h-4 w-4" />
              Ir para Definições Gerais
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* New Folder Dialog */}
      <Dialog open={newFolderDialog.open} onOpenChange={(open) => !open && setNewFolderDialog({ open: false, name: "" })}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Nova Pasta</DialogTitle>
            <DialogDescription>
              Introduza o nome da nova pasta em{" "}
              <strong className="text-foreground">{currentPath ? `"${currentPath}/"` : "raiz"}</strong>.
            </DialogDescription>
          </DialogHeader>
          <Input
            value={newFolderDialog.name}
            onChange={(e) => setNewFolderDialog((prev) => ({ ...prev, name: e.target.value }))}
            placeholder="Nome da pasta"
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter") handleCreateFolder();
            }}
          />
          <DialogFooter className="mt-4">
            <Button variant="outline" onClick={() => setNewFolderDialog({ open: false, name: "" })}>
              Cancelar
            </Button>
            <Button onClick={handleCreateFolder} disabled={creatingFolder || !newFolderDialog.name.trim()}>
              {creatingFolder ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
              Criar Pasta
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </DashboardLayout>
  );
};

export default FilesExplorerPage;
