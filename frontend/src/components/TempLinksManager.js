/**
 * ====================================================================
 * GESTOR DE LINKS TEMPORÁRIOS - POWERCELL
 * ====================================================================
 * Permite criar e gerir links temporários para:
 * - Upload de documentação pelo cliente
 * - Download de documentação pelo cliente
 * ====================================================================
 */
import { useState, useEffect } from "react";
import { useAuth } from "../contexts/AuthContext";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Badge } from "./ui/badge";
import { Checkbox } from "./ui/checkbox";
import { ScrollArea } from "./ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "./ui/table";
import {
  Upload,
  Download,
  Link2,
  Copy,
  Clock,
  XCircle,
  Loader2,
  ExternalLink,
  FileText,
  FileImage,
  File,
  Check,
} from "lucide-react";
import { toast } from "sonner";
import { safeCopyToClipboard } from "../utils/clipboard";
import { safeDateStr } from "../lib/utils";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Ícone baseado na extensão do ficheiro
const FileIcon = ({ filename }) => {
  const ext = filename?.split('.').pop()?.toLowerCase();
  
  if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg'].includes(ext)) {
    return <FileImage className="h-4 w-4 text-pink-500" />;
  }
  if (['pdf'].includes(ext)) {
    return <FileText className="h-4 w-4 text-red-500" />;
  }
  return <File className="h-4 w-4 text-gray-500" />;
};

const TempLinksManager = ({ processId, clientName, clientEmail }) => {
  const { token } = useAuth();
  const [links, setLinks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [creating, setCreating] = useState(false);
  
  // Form state
  const [linkType, setLinkType] = useState("upload");
  const [expiresIn, setExpiresIn] = useState("72");
  const [maxUses, setMaxUses] = useState("1");
  const [description, setDescription] = useState("");
  const [notifyEmail, setNotifyEmail] = useState(true);
  
  // Files state for download links
  const [availableFiles, setAvailableFiles] = useState([]);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [loadingFiles, setLoadingFiles] = useState(false);

  // Load existing links
  useEffect(() => {
    loadLinks();
  }, [processId]);

  // Load files when dialog opens and type is download
  useEffect(() => {
    if (showCreateDialog && linkType === "download") {
      loadAvailableFiles();
    }
  }, [showCreateDialog, linkType]);

  const loadLinks = async () => {
    try {
      setLoading(true);
      const response = await fetch(
        `${API_URL}/api/temp-links/process/${processId}`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      
      if (response.ok) {
        const data = await response.json();
        setLinks(data.links || []);
      }
    } catch (error) {
      console.error("Erro ao carregar links:", error);
    } finally {
      setLoading(false);
    }
  };

  const loadAvailableFiles = async () => {
    setLoadingFiles(true);
    try {
      const response = await fetch(
        `${API_URL}/api/documents/client/${processId}/files`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      
      if (response.ok) {
        const data = await response.json();
        // Flatten all files from all categories
        const allFiles = [];
        if (data.files) {
          Object.entries(data.files).forEach(([category, files]) => {
            files.forEach(file => {
              allFiles.push({
                ...file,
                category
              });
            });
          });
        }
        setAvailableFiles(allFiles);
      }
    } catch (error) {
      console.error("Erro ao carregar ficheiros:", error);
      toast.error("Erro ao carregar lista de ficheiros");
    } finally {
      setLoadingFiles(false);
    }
  };

  const handleCreateLink = async () => {
    // Validação para links de download
    if (linkType === "download" && selectedFiles.length === 0) {
      toast.error("Selecione pelo menos um ficheiro para download");
      return;
    }

    setCreating(true);
    try {
      const formData = new FormData();
      formData.append("process_id", processId);
      formData.append("link_type", linkType);
      formData.append("expires_in_hours", parseInt(expiresIn));
      formData.append("max_uses", parseInt(maxUses));
      formData.append("description", description);
      formData.append("notify_email", notifyEmail ? "true" : "false");
      formData.append("base_url", window.location.origin);
      
      // Adicionar ficheiros selecionados para download
      if (linkType === "download" && selectedFiles.length > 0) {
        formData.append("file_paths", selectedFiles.join(","));
      }

      const response = await fetch(
        `${API_URL}/api/temp-links/create`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: formData,
        }
      );
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Erro ao criar link");
      }
      
      const linkData = await response.json();
      
      // Construir URL com o domínio atual (não o do backend que pode estar errado)
      const linkToken = linkData.token;
      const path = linkData.link_type === "upload" ? "upload" : "download";
      const correctUrl = `${window.location.origin}/${path}/${linkToken}`;
      
      // Copiar URL para a área de transferência
      await safeCopyToClipboard(
        correctUrl,
        linkType === "upload"
          ? "Link de upload criado e copiado!"
          : "Link de download criado e copiado!"
      );
      
      setShowCreateDialog(false);
      resetForm();
      loadLinks();
    } catch (error) {
      toast.error(error.message || "Erro ao criar link");
    } finally {
      setCreating(false);
    }
  };

  const handleCopyLink = async (url, token, linkType) => {
    const path = linkType === "upload" ? "upload" : "download";
    const correctUrl = `${window.location.origin}/${path}/${token}`;
    await safeCopyToClipboard(correctUrl);
  };

  const handleCancelLink = async (linkId) => {
    if (!window.confirm("Tem a certeza que deseja cancelar este link?")) return;
    
    try {
      const response = await fetch(
        `${API_URL}/api/temp-links/${linkId}/cancel`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      
      if (response.ok) {
        toast.success("Link cancelado");
        loadLinks();
      }
    } catch (error) {
      toast.error("Erro ao cancelar link");
    }
  };

  const toggleFileSelection = (filePath) => {
    setSelectedFiles(prev => {
      if (prev.includes(filePath)) {
        return prev.filter(p => p !== filePath);
      }
      return [...prev, filePath];
    });
  };

  const toggleSelectAll = () => {
    if (selectedFiles.length === availableFiles.length) {
      setSelectedFiles([]);
    } else {
      setSelectedFiles(availableFiles.map(f => f.path));
    }
  };

  const resetForm = () => {
    setLinkType("upload");
    setExpiresIn("72");
    setMaxUses("1");
    setDescription("");
    setNotifyEmail(true);
    setSelectedFiles([]);
    setAvailableFiles([]);
  };

  const formatFileSize = (bytes) => {
    if (!bytes) return "";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  };

  const getStatusBadge = (link) => {
    switch (link.status) {
      case "pending":
        return <Badge className="bg-blue-100 text-blue-800">Pendente</Badge>;
      case "used":
        return <Badge className="bg-green-100 text-green-800">Utilizado</Badge>;
      case "expired":
        return <Badge className="bg-gray-100 text-gray-800">Expirado</Badge>;
      case "cancelled":
        return <Badge className="bg-red-100 text-red-800">Cancelado</Badge>;
      default:
        return <Badge>{link.status}</Badge>;
    }
  };

  const getTypeIcon = (type) => {
    return type === "upload" ? (
      <Upload className="h-4 w-4 text-green-600" />
    ) : (
      <Download className="h-4 w-4 text-blue-600" />
    );
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">Links Temporários</h3>
        <Button
          size="sm"
          onClick={() => setShowCreateDialog(true)}
          className="bg-teal-600 hover:bg-teal-700"
        >
          <Link2 className="h-4 w-4 mr-2" />
          Criar Link
        </Button>
      </div>

      {/* Links List */}
      {loading ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
        </div>
      ) : links.length === 0 ? (
        <div className="text-center py-8 text-gray-500 text-sm">
          Nenhum link temporário criado
        </div>
      ) : (
        <div className="border rounded-lg overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10"></TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead>Utilizações</TableHead>
                <TableHead>Expira</TableHead>
                <TableHead className="text-right">Ações</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {links.map((link) => (
                <TableRow key={link.id}>
                  <TableCell>
                    {getTypeIcon(link.link_type)}
                  </TableCell>
                  <TableCell>
                    <div>
                      <p className="font-medium capitalize">
                        {link.link_type === "upload" ? "Upload" : "Download"}
                      </p>
                      {link.description && (
                        <p className="text-xs text-gray-500">{link.description}</p>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>{getStatusBadge(link)}</TableCell>
                  <TableCell>
                    <span className="text-sm">
                      {link.current_uses} / {link.max_uses}
                    </span>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1 text-sm text-gray-600">
                      <Clock className="h-3 w-3" />
                      {new Date(safeDateStr(link.expires_at)).toLocaleDateString("pt-PT", {
                        day: "2-digit",
                        month: "2-digit",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </div>
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleCopyLink(link.url, link.token, link.link_type)}
                        title="Copiar link"
                      >
                        <Copy className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => window.open(`${window.location.origin}/${link.link_type}/${link.token}`, "_blank")}
                        title="Abrir link"
                      >
                        <ExternalLink className="h-4 w-4" />
                      </Button>
                      {link.status === "pending" && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleCancelLink(link.id)}
                          className="text-orange-600 hover:text-orange-700"
                          title="Cancelar link"
                        >
                          <XCircle className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Create Link Dialog */}
      <Dialog open={showCreateDialog} onOpenChange={(open) => {
        setShowCreateDialog(open);
        if (!open) resetForm();
      }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Criar Link Temporário</DialogTitle>
            <DialogDescription>
              Crie um link para {clientName} carregar ou descarregar documentação.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            {/* Link Type */}
            <div className="space-y-2">
              <Label>Tipo de Link</Label>
              <Select value={linkType} onValueChange={setLinkType}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="upload">
                    <div className="flex items-center gap-2">
                      <Upload className="h-4 w-4 text-green-600" />
                      Upload - Cliente carrega documentos
                    </div>
                  </SelectItem>
                  <SelectItem value="download">
                    <div className="flex items-center gap-2">
                      <Download className="h-4 w-4 text-blue-600" />
                      Download - Cliente descarrega documentos
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* File Selection for Download */}
            {linkType === "download" && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label>Ficheiros para Download</Label>
                  {availableFiles.length > 0 && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={toggleSelectAll}
                      className="text-xs"
                    >
                      {selectedFiles.length === availableFiles.length ? "Desmarcar todos" : "Selecionar todos"}
                    </Button>
                  )}
                </div>
                
                {loadingFiles ? (
                  <div className="flex items-center justify-center py-8 border rounded-lg">
                    <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
                  </div>
                ) : availableFiles.length === 0 ? (
                  <div className="text-center py-8 text-gray-500 text-sm border rounded-lg">
                    <File className="h-8 w-8 mx-auto mb-2 opacity-50" />
                    Nenhum ficheiro disponível
                  </div>
                ) : (
                  <ScrollArea className="h-64 border rounded-lg">
                    <div className="p-2 space-y-1">
                      {availableFiles.map((file, index) => (
                        <div
                          key={`${file.path}-${index}`}
                          className={`flex items-center gap-3 p-2 rounded-lg cursor-pointer transition-colors ${
                            selectedFiles.includes(file.path)
                              ? "bg-teal-50 border border-teal-200"
                              : "hover:bg-gray-50 border border-transparent"
                          }`}
                          onClick={() => toggleFileSelection(file.path)}
                        >
                          <Checkbox
                            checked={selectedFiles.includes(file.path)}
                            onCheckedChange={() => toggleFileSelection(file.path)}
                          />
                          <FileIcon filename={file.name} />
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium truncate">{file.name}</p>
                            <p className="text-xs text-gray-500">
                              {file.category} • {formatFileSize(file.size)}
                            </p>
                          </div>
                          {selectedFiles.includes(file.path) && (
                            <Check className="h-4 w-4 text-teal-600" />
                          )}
                        </div>
                      ))}
                    </div>
                  </ScrollArea>
                )}
                
                {selectedFiles.length > 0 && (
                  <p className="text-sm text-teal-600">
                    {selectedFiles.length} ficheiro(s) selecionado(s)
                  </p>
                )}
              </div>
            )}

            {/* Expiration */}
            <div className="space-y-2">
              <Label>Expira em</Label>
              <Select value={expiresIn} onValueChange={setExpiresIn}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="24">24 horas</SelectItem>
                  <SelectItem value="48">48 horas</SelectItem>
                  <SelectItem value="72">3 dias</SelectItem>
                  <SelectItem value="168">7 dias</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Max Uses */}
            <div className="space-y-2">
              <Label>Máximo de utilizações</Label>
              <Select value={maxUses} onValueChange={setMaxUses}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1">1 vez</SelectItem>
                  <SelectItem value="2">2 vezes</SelectItem>
                  <SelectItem value="5">5 vezes</SelectItem>
                  <SelectItem value="10">10 vezes</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Description */}
            <div className="space-y-2">
              <Label>Descrição (opcional)</Label>
              <Input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Ex: Documentos para aprovação do crédito"
              />
            </div>

            {/* Notify Email */}
            {clientEmail && (
              <div className="flex items-center gap-2">
                <Checkbox
                  id="notify-email"
                  checked={notifyEmail}
                  onCheckedChange={setNotifyEmail}
                />
                <Label htmlFor="notify-email" className="text-sm cursor-pointer">
                  Enviar email para {clientEmail}
                </Label>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreateDialog(false)}>
              Cancelar
            </Button>
            <Button 
              onClick={handleCreateLink} 
              disabled={creating || (linkType === "download" && selectedFiles.length === 0)}
              className="bg-teal-600 hover:bg-teal-700"
            >
              {creating ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  A criar...
                </>
              ) : (
                <>
                  <Link2 className="h-4 w-4 mr-2" />
                  Criar Link
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default TempLinksManager;
