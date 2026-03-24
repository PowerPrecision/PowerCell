/**
 * ====================================================================
 * BOTÃO DE LINKS TEMPORÁRIOS - POWERCELL
 * ====================================================================
 * Botão simplificado para criar links temporários
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

const TempLinkButton = ({ processId, clientName, clientEmail }) => {
  const { token } = useAuth();
  const [showDialog, setShowDialog] = useState(false);
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

  // Load files when dialog opens and type is download
  useEffect(() => {
    if (showDialog && linkType === "download") {
      loadAvailableFiles();
    }
  }, [showDialog, linkType]);

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
      formData.append("notify_email", notifyEmail);
      
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
      
      toast.success(
        linkType === "upload" 
          ? "Link de upload criado! O cliente receberá um email."
          : "Link de download criado! O cliente receberá um email."
      );
      
      setShowDialog(false);
      resetForm();
    } catch (error) {
      toast.error(error.message || "Erro ao criar link");
    } finally {
      setCreating(false);
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

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        className="text-teal-600 border-teal-200 hover:bg-teal-50"
        onClick={() => setShowDialog(true)}
        title="Criar link temporário para o cliente"
      >
        <Link2 className="h-4 w-4 mr-2" />
        Link
      </Button>

      {/* Create Link Dialog */}
      <Dialog open={showDialog} onOpenChange={(open) => {
        setShowDialog(open);
        if (!open) resetForm();
      }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Criar Link Temporário</DialogTitle>
            <DialogDescription>
              Crie um link para {clientName || "o cliente"} carregar ou descarregar documentação.
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
            <Button variant="outline" onClick={() => setShowDialog(false)}>
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
    </>
  );
};

export default TempLinkButton;
