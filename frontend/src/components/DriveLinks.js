/**
 * DriveLinks - Componente para gestão de links de armazenamento externo
 * Suporta: S3, Google Drive, OneDrive, Dropbox (configurável pelo admin)
 * 
 * Cenário A (Upload Massivo): Nome da pasta = Nome do cliente
 * Cenário B (Página do Cliente): Usa force_client_id, ignora nome da pasta
 */
import { useState, useEffect } from "react";
import { Card, CardContent } from "./ui/card";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Badge } from "./ui/badge";
import { ScrollArea } from "./ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "./ui/dialog";
import { FolderOpen, Plus, Trash2, ExternalLink, Loader2, Link as LinkIcon, Save, Cloud, HardDrive } from "lucide-react";
import { toast } from "sonner";
import { getProcessOneDriveLinks, addProcessOneDriveLink, deleteProcessOneDriveLink } from "../services/api";

const API_URL = process.env.REACT_APP_BACKEND_URL || "";

const DriveLinks = ({ processId, clientName }) => {
  const [links, setLinks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [storageInfo, setStorageInfo] = useState(null);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [mainFolderUrl, setMainFolderUrl] = useState(null);
  const [savedFolderUrl, setSavedFolderUrl] = useState(null);
  const [loadingFolder, setLoadingFolder] = useState(false);
  const [formData, setFormData] = useState({
    name: "",
    url: "",
    description: ""
  });

  useEffect(() => {
    fetchStorageInfo();
    fetchLinks();
    fetchFolderUrl();
  }, [processId]);

  // Buscar informação do storage configurado
  const fetchStorageInfo = async () => {
    try {
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_URL}/api/system-config/storage-info`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setStorageInfo(data);
      }
    } catch (error) {
      console.error("Error fetching storage info:", error);
    }
  };

  const fetchLinks = async () => {
    try {
      const response = await getProcessOneDriveLinks(processId);
      setLinks(response.data);
    } catch (error) {
      console.error("Error fetching links:", error);
    } finally {
      setLoading(false);
    }
  };

  // Buscar URL da pasta do Drive (usa storage configurado)
  const fetchFolderUrl = async () => {
    // Se não há storage configurado ou é S3, não precisamos de folder URL externo
    if (storageInfo && storageInfo.provider === "s3") {
      // S3 não tem pasta externa - os ficheiros são acedidos via API
      setMainFolderUrl(null);
      return;
    }
    
    try {
      const token = localStorage.getItem("token");
      // Tentar endpoint genérico primeiro
      const response = await fetch(`${API_URL}/api/storage/process/${processId}/folder-url`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setMainFolderUrl(data.url);
        if (data.type === "saved") {
          setSavedFolderUrl(data.url);
        }
      } else if (response.status === 400 || response.status === 404) {
        // Storage não configurado ou não suporta folder URLs - é OK
        setMainFolderUrl(null);
      }
    } catch (error) {
      // Silently ignore - storage pode não estar configurado
      console.debug("Storage folder URL not available:", error);
    }
  };

  // Abrir pasta do cliente no Drive
  const handleOpenFolder = () => {
    if (savedFolderUrl) {
      window.open(savedFolderUrl, "_blank");
    } else if (mainFolderUrl) {
      window.open(mainFolderUrl, "_blank");
      toast.info(`Procure pela pasta "${clientName}"`, { duration: 5000 });
    } else if (storageInfo?.base_url) {
      window.open(storageInfo.base_url, "_blank");
      toast.info(`Procure pela pasta "${clientName}" no ${storageInfo.provider_label}`, { duration: 5000 });
    } else {
      toast.error("Armazenamento não configurado. Contacte o administrador.");
    }
  };

  // Guardar link da pasta específica do cliente
  const handleSaveFolderUrl = async () => {
    const placeholder = storageInfo?.provider === "aws_s3" 
      ? "s3://bucket/pasta/cliente/"
      : "https://...";
    
    const url = prompt(
      `Cole aqui o link da pasta específica do cliente:\n\nFormato: ${placeholder}`,
      ""
    );
    if (!url) return;

    setLoadingFolder(true);
    try {
      const token = localStorage.getItem("token");
      const response = await fetch(
        `${API_URL}/api/storage/process/${processId}/folder-url?folder_url=${encodeURIComponent(url)}`,
        {
          method: "PUT",
          headers: { Authorization: `Bearer ${token}` }
        }
      );
      if (response.ok) {
        toast.success("Link da pasta guardado com sucesso!");
        setSavedFolderUrl(url);
      } else {
        const data = await response.json();
        toast.error(data.detail || "Erro ao guardar link");
      }
    } catch (error) {
      toast.error("Erro ao guardar link da pasta");
    } finally {
      setLoadingFolder(false);
    }
  };

  // Remover link da pasta
  const handleRemoveFolderUrl = async () => {
    if (!window.confirm("Tem a certeza que deseja remover o link da pasta?")) return;

    try {
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_URL}/api/storage/process/${processId}/folder-url`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` }
      });
      if (response.ok) {
        toast.success("Link removido");
        setSavedFolderUrl(null);
      }
    } catch (error) {
      toast.error("Erro ao remover link");
    }
  };

  const handleAddLink = async (e) => {
    e.preventDefault();
    if (!formData.name || !formData.url) {
      toast.error("Nome e URL são obrigatórios");
      return;
    }

    setSaving(true);
    try {
      await addProcessOneDriveLink(processId, formData);
      toast.success("Link adicionado com sucesso");
      setIsDialogOpen(false);
      setFormData({ name: "", url: "", description: "" });
      fetchLinks();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Erro ao adicionar link");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteLink = async (linkId) => {
    if (!window.confirm("Tem a certeza que deseja eliminar este link?")) return;

    try {
      await deleteProcessOneDriveLink(processId, linkId);
      toast.success("Link eliminado");
      fetchLinks();
    } catch (error) {
      toast.error("Erro ao eliminar link");
    }
  };

  // Obter ícone baseado no tipo de storage
  const getStorageIcon = () => {
    if (storageInfo?.provider === "aws_s3") return <HardDrive className="h-4 w-4" />;
    return <Cloud className="h-4 w-4" />;
  };

  // Obter label do storage
  const getStorageLabel = () => {
    return storageInfo?.provider_label || "Armazenamento";
  };

  if (loading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin" />
        </CardContent>
      </Card>
    );
  }

  // Se storage não está configurado
  const isStorageConfigured = storageInfo?.configured || mainFolderUrl;

  return (
    <div className="space-y-4" data-testid="drive-links-container">
      {/* Header com info do storage */}
      {isStorageConfigured && (
        <div className="p-4 bg-blue-50 dark:bg-blue-900/30 rounded-lg border border-blue-200 dark:border-blue-700">
          <div className="flex items-center justify-between gap-4">
            <div className="flex-1 min-w-0">
              <h4 className="font-medium text-sm flex items-center gap-2 dark:text-blue-200">
                {getStorageIcon()}
                <span className="text-blue-600 dark:text-blue-400">{getStorageLabel()}</span>
                <span className="text-muted-foreground">•</span>
                <span>{clientName}</span>
              </h4>
              <p className="text-xs text-muted-foreground mt-1">
                {savedFolderUrl ? "Link específico guardado" : "Pasta principal configurada"}
              </p>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <Button
                onClick={handleOpenFolder}
                size="sm"
                className="bg-blue-600 hover:bg-blue-700"
                data-testid="open-storage-btn"
              >
                <ExternalLink className="h-4 w-4 mr-1" />
                Abrir
              </Button>
              {!savedFolderUrl ? (
                <Button
                  onClick={handleSaveFolderUrl}
                  size="sm"
                  variant="outline"
                  disabled={loadingFolder}
                  title="Guardar link específico desta pasta"
                  data-testid="save-folder-btn"
                >
                  {loadingFolder ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                </Button>
              ) : (
                <Button
                  onClick={handleRemoveFolderUrl}
                  size="sm"
                  variant="outline"
                  className="text-red-600 hover:text-red-700"
                  title="Remover link guardado"
                  data-testid="remove-folder-btn"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Lista de Links Externos */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-medium flex items-center gap-2">
            <LinkIcon className="h-4 w-4 text-muted-foreground" />
            Links Externos
            {links.length > 0 && (
              <Badge variant="secondary" className="text-xs">{links.length}</Badge>
            )}
          </h4>
          <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
            <DialogTrigger asChild>
              <Button size="sm" variant="outline" data-testid="add-link-btn">
                <Plus className="h-4 w-4 mr-1" />
                Adicionar
              </Button>
            </DialogTrigger>
            <DialogContent aria-describedby="add-link-description">
              <DialogHeader>
                <DialogTitle>Adicionar Link Externo</DialogTitle>
                <DialogDescription id="add-link-description">
                  Adicione um link para documentos externos como OneDrive, Google Drive ou S3.
                </DialogDescription>
              </DialogHeader>
              <form onSubmit={handleAddLink} className="space-y-4">
                <div>
                  <Label>Nome *</Label>
                  <Input
                    value={formData.name}
                    onChange={(e) => setFormData({...formData, name: e.target.value})}
                    placeholder="Ex: Contrato de Compra"
                    data-testid="link-name-input"
                  />
                </div>
                <div>
                  <Label>URL *</Label>
                  <Input
                    value={formData.url}
                    onChange={(e) => setFormData({...formData, url: e.target.value})}
                    placeholder="https://... ou s3://..."
                    data-testid="link-url-input"
                  />
                </div>
                <div>
                  <Label>Descrição</Label>
                  <Input
                    value={formData.description}
                    onChange={(e) => setFormData({...formData, description: e.target.value})}
                    placeholder="Opcional"
                    data-testid="link-description-input"
                  />
                </div>
                <DialogFooter>
                  <Button type="button" variant="outline" onClick={() => setIsDialogOpen(false)}>
                    Cancelar
                  </Button>
                  <Button type="submit" disabled={saving} data-testid="save-link-btn">
                    {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
                    Guardar
                  </Button>
                </DialogFooter>
              </form>
            </DialogContent>
          </Dialog>
        </div>

        {links.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4 text-center">
            Nenhum link externo adicionado
          </p>
        ) : (
          <ScrollArea className="max-h-[200px]">
            <div className="space-y-2">
              {links.map((link) => (
                <div 
                  key={link.id} 
                  className="flex items-center justify-between p-3 bg-muted/50 rounded-lg"
                  data-testid={`link-item-${link.id}`}
                >
                  <div className="flex-1 min-w-0 mr-3">
                    <p className="font-medium text-sm truncate">{link.name}</p>
                    {link.description && (
                      <p className="text-xs text-muted-foreground truncate">{link.description}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => window.open(link.url, "_blank")}
                      title="Abrir link"
                    >
                      <ExternalLink className="h-4 w-4" />
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-red-600 hover:text-red-700"
                      onClick={() => handleDeleteLink(link.id)}
                      title="Eliminar link"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>
        )}
      </div>

      {/* Mensagem quando não há storage configurado - mas permite adicionar links externos */}
      {!isStorageConfigured && links.length === 0 && (
        <div className="p-3 bg-muted/50 rounded-lg text-sm text-center">
          <p className="text-muted-foreground">
            Adicione links para documentos externos deste cliente
          </p>
        </div>
      )}
    </div>
  );
};

export default DriveLinks;
