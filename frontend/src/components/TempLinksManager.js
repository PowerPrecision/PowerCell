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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Badge } from "../components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../components/ui/table";
import {
  Upload,
  Download,
  Link2,
  Copy,
  Trash2,
  Clock,
  CheckCircle,
  XCircle,
  Loader2,
  Mail,
  ExternalLink,
} from "lucide-react";
import { toast } from "sonner";
import {
  createTempLink,
  getProcessTempLinks,
  cancelTempLink,
  deleteTempLink,
} from "../services/api";

const TempLinksManager = ({ processId, clientName, clientEmail }) => {
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

  // Load existing links
  useEffect(() => {
    loadLinks();
  }, [processId]);

  const loadLinks = async () => {
    try {
      setLoading(true);
      const response = await getProcessTempLinks(processId);
      setLinks(response.data.links || []);
    } catch (error) {
      console.error("Erro ao carregar links:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateLink = async () => {
    setCreating(true);
    try {
      const formData = new FormData();
      formData.append("process_id", processId);
      formData.append("link_type", linkType);
      formData.append("expires_in_hours", parseInt(expiresIn));
      formData.append("max_uses", parseInt(maxUses));
      formData.append("description", description);
      formData.append("notify_email", notifyEmail);

      await createTempLink(formData);
      
      toast.success(
        linkType === "upload" 
          ? "Link de upload criado! O cliente receberá um email."
          : "Link de download criado! O cliente receberá um email."
      );
      
      setShowCreateDialog(false);
      resetForm();
      loadLinks();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Erro ao criar link");
    } finally {
      setCreating(false);
    }
  };

  const handleCopyLink = (url) => {
    navigator.clipboard.writeText(url);
    toast.success("Link copiado para o clipboard!");
  };

  const handleCancelLink = async (linkId) => {
    if (!window.confirm("Tem a certeza que deseja cancelar este link?")) return;
    
    try {
      await cancelTempLink(linkId);
      toast.success("Link cancelado");
      loadLinks();
    } catch (error) {
      toast.error("Erro ao cancelar link");
    }
  };

  const handleDeleteLink = async (linkId) => {
    if (!window.confirm("Eliminar este link permanentemente?")) return;
    
    try {
      await deleteTempLink(linkId);
      toast.success("Link eliminado");
      loadLinks();
    } catch (error) {
      toast.error("Erro ao eliminar link");
    }
  };

  const resetForm = () => {
    setLinkType("upload");
    setExpiresIn("72");
    setMaxUses("1");
    setDescription("");
    setNotifyEmail(true);
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
        <div className="border rounded-lg overflow-hidden">
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
                      {new Date(link.expires_at).toLocaleDateString("pt-PT", {
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
                        onClick={() => handleCopyLink(link.url)}
                        title="Copiar link"
                      >
                        <Copy className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => window.open(link.url, "_blank")}
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
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent>
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
                <input
                  type="checkbox"
                  id="notify-email"
                  checked={notifyEmail}
                  onChange={(e) => setNotifyEmail(e.target.checked)}
                  className="rounded"
                />
                <Label htmlFor="notify-email" className="text-sm">
                  Enviar email para {clientEmail}
                </Label>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreateDialog(false)}>
              Cancelar
            </Button>
            <Button onClick={handleCreateLink} disabled={creating}>
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
