/**
 * DocumentRecipientsManager - Gestão visual de destinatários de documentação
 * 
 * Permite adicionar, editar, remover e activar/desactivar destinatários
 * de forma fácil sem precisar de editar JSON.
 */
import React, { useState, useEffect } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "./ui/card";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Badge } from "./ui/badge";
import { Switch } from "./ui/switch";
import { Textarea } from "./ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
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
import { ScrollArea } from "./ui/scroll-area";
import { Separator } from "./ui/separator";
import {
  Plus,
  Pencil,
  Trash2,
  Building2,
  Mail,
  Check,
  X,
  Save,
  Loader2,
  GripVertical,
  Eye,
  AlertCircle,
} from "lucide-react";
import { toast } from "sonner";

const API_URL = process.env.REACT_APP_BACKEND_URL || "";

const DocumentRecipientsManager = ({ token, user }) => {
  // Estado
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [recipients, setRecipients] = useState([]);
  const [enabled, setEnabled] = useState(false);
  const [emailTemplate, setEmailTemplate] = useState("");
  const [defaultTo, setDefaultTo] = useState("");
  const [defaultToName, setDefaultToName] = useState("");
  const [hasChanges, setHasChanges] = useState(false);

  // Dialog states
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [editingRecipient, setEditingRecipient] = useState(null);
  const [deletingRecipient, setDeletingRecipient] = useState(null);

  // Form state
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    active: true,
  });

  // Carregar dados
  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/emails/document-recipients`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        const data = await response.json();
        setEnabled(data.enabled || false);
        setRecipients(data.recipients || []);
        setEmailTemplate(data.email_template || "");
        setDefaultTo(data.default_to || "");
        setDefaultTo(data.default_to || "geral@powerealestate.pt");
        setDefaultToName(data.default_to_name || "Power Real Estate");
      }
    } catch (error) {
      console.error("Erro ao carregar configuração:", error);
      toast.error("Erro ao carregar configuração");
    } finally {
      setLoading(false);
    }
  };

  // Guardar configuração
  const saveConfig = async () => {
    setSaving(true);
    try {
      const response = await fetch(`${API_URL}/api/system-config/document_recipients`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          enabled,
          recipients: JSON.stringify(recipients),
          email_template: emailTemplate,
          default_to: defaultTo,
          default_to_name: defaultToName,
        }),
      });

      if (response.ok) {
        toast.success("Configuração guardada com sucesso");
        setHasChanges(false);
      } else {
        const data = await response.json();
        toast.error(data.detail || "Erro ao guardar configuração");
      }
    } catch (error) {
      console.error("Erro ao guardar:", error);
      toast.error("Erro ao guardar configuração");
    } finally {
      setSaving(false);
    }
  };

  // Adicionar/Editar destinatário
  const openAddDialog = () => {
    setFormData({ name: "", email: "", active: true });
    setEditingRecipient(null);
    setShowEditDialog(true);
  };

  const openEditDialog = (recipient, index) => {
    setFormData({ ...recipient });
    setEditingRecipient({ ...recipient, index });
    setShowEditDialog(true);
  };

  const handleSaveRecipient = () => {
    // Validações
    if (!formData.name.trim()) {
      toast.error("Nome é obrigatório");
      return;
    }
    if (!formData.email.trim()) {
      toast.error("Email é obrigatório");
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      toast.error("Email inválido");
      return;
    }

    let newRecipients;
    if (editingRecipient) {
      // Editar existente
      newRecipients = recipients.map((r, i) =>
        i === editingRecipient.index ? { ...formData } : r
      );
      toast.success("Destinatário actualizado");
    } else {
      // Adicionar novo
      newRecipients = [...recipients, { ...formData }];
      toast.success("Destinatário adicionado");
    }

    setRecipients(newRecipients);
    setHasChanges(true);
    setShowEditDialog(false);
  };

  // Remover destinatário
  const openDeleteDialog = (recipient, index) => {
    setDeletingRecipient({ ...recipient, index });
    setShowDeleteDialog(true);
  };

  const handleDeleteRecipient = () => {
    const newRecipients = recipients.filter((_, i) => i !== deletingRecipient.index);
    setRecipients(newRecipients);
    setHasChanges(true);
    setShowDeleteDialog(false);
    toast.success("Destinatário removido");
  };

  // Toggle activo
  const toggleActive = (index) => {
    const newRecipients = recipients.map((r, i) =>
      i === index ? { ...r, active: !r.active } : r
    );
    setRecipients(newRecipients);
    setHasChanges(true);
  };

  // Template padrão
  const defaultTemplate = `Prezados,

Segue em anexo a documentação do cliente:

**Cliente:** {client_name}
**NIF:** {client_nif}
**Processo:** #{process_number}

**Documentos enviados:**
{documents_list}

Esta documentação foi enviada através do sistema PowerCell.

Com os melhores cumprimentos,
{sender_name}
{sender_email}`;

  // Verificar permissões
  const canEdit = user?.role?.match(/admin|ceo/i);

  if (loading) {
    return (
      <Card>
        <CardContent className="py-12 flex items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  if (!canEdit) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Building2 className="h-5 w-5" />
            Destinatários de Documentação
          </CardTitle>
          <CardDescription>
            Apenas administradores podem configurar destinatários.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Building2 className="h-5 w-5 text-primary" />
              Destinatários de Documentação
            </CardTitle>
            <CardDescription>
              Configure os balcões/bancos para envio de documentação de clientes
            </CardDescription>
          </div>
          {hasChanges && (
            <Badge variant="outline" className="bg-yellow-50 text-yellow-700">
              Alterações por guardar
            </Badge>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-6">
        {/* Activar/Desactivar */}
        <div className="flex items-center justify-between p-4 border rounded-lg">
          <div>
            <Label className="font-medium">Activar Envio de Documentação</Label>
            <p className="text-sm text-muted-foreground">
              Permite o envio de documentação para balcões directamente a partir dos processos
            </p>
          </div>
          <Switch
            checked={enabled}
            onCheckedChange={(v) => {
              setEnabled(v);
              setHasChanges(true);
            }}
          />
        </div>

        {enabled && (
          <>
            {/* Configuração do Email Principal */}
            <div className="space-y-4">
              <h4 className="font-medium flex items-center gap-2">
                <Mail className="h-4 w-4" />
                Email Principal (TO)
              </h4>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Email</Label>
                  <Input
                    placeholder="geral@powerealestate.pt"
                    value={defaultTo}
                    onChange={(e) => {
                      setDefaultTo(e.target.value);
                      setHasChanges(true);
                    }}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Nome</Label>
                  <Input
                    placeholder="Power Real Estate"
                    value={defaultToName}
                    onChange={(e) => {
                      setDefaultToName(e.target.value);
                      setHasChanges(true);
                    }}
                  />
                </div>
              </div>
            </div>

            <Separator />

            {/* Lista de Destinatários */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="font-medium">Destinatários (BCC)</h4>
                  <p className="text-sm text-muted-foreground">
                    Balcões/bancos que receberão a documentação em BCC (cópia oculta)
                  </p>
                </div>
                <Button onClick={openAddDialog} size="sm">
                  <Plus className="h-4 w-4 mr-2" />
                  Adicionar Destinatário
                </Button>
              </div>

              {recipients.length === 0 ? (
                <div className="text-center py-8 border-2 border-dashed rounded-lg">
                  <Building2 className="h-12 w-12 mx-auto text-muted-foreground opacity-50" />
                  <p className="mt-2 text-muted-foreground">
                    Nenhum destinatário configurado
                  </p>
                  <p className="text-sm text-muted-foreground">
                    Clique em "Adicionar Destinatário" para começar
                  </p>
                </div>
              ) : (
                <ScrollArea className="h-64">
                  <div className="space-y-2">
                    {recipients.map((recipient, index) => (
                      <div
                        key={index}
                        className={`flex items-center gap-3 p-3 border rounded-lg ${
                          !recipient.active ? "opacity-50 bg-muted" : ""
                        }`}
                      >
                        <Building2 className="h-5 w-5 text-muted-foreground" />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-medium truncate">
                              {recipient.name}
                            </span>
                            {!recipient.active && (
                              <Badge variant="outline" className="text-xs">
                                Inactivo
                              </Badge>
                            )}
                          </div>
                          <span className="text-sm text-muted-foreground truncate block">
                            {recipient.email}
                          </span>
                        </div>
                        <div className="flex items-center gap-1">
                          <Switch
                            checked={recipient.active}
                            onCheckedChange={() => toggleActive(index)}
                          />
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => openEditDialog(recipient, index)}
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => openDeleteDialog(recipient, index)}
                          >
                            <Trash2 className="h-4 w-4 text-red-500" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              )}
            </div>

            <Separator />

            {/* Template do Email */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div>
                  <Label className="font-medium">Template do Email</Label>
                  <p className="text-sm text-muted-foreground">
                    Personalize a mensagem que será enviada
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setEmailTemplate(defaultTemplate);
                    setHasChanges(true);
                  }}
                >
                  Restaurar Predefinição
                </Button>
              </div>
              <Textarea
                value={emailTemplate}
                onChange={(e) => {
                  setEmailTemplate(e.target.value);
                  setHasChanges(true);
                }}
                placeholder={defaultTemplate}
                className="min-h-[200px] font-mono text-sm"
              />
              <div className="bg-muted p-3 rounded-lg">
                <p className="text-xs font-medium mb-2">Variáveis disponíveis:</p>
                <div className="flex flex-wrap gap-2">
                  {[
                    "{client_name}",
                    "{client_nif}",
                    "{process_number}",
                    "{documents_list}",
                    "{sender_name}",
                    "{sender_email}",
                  ].map((v) => (
                    <Badge key={v} variant="outline" className="font-mono text-xs">
                      {v}
                    </Badge>
                  ))}
                </div>
              </div>
            </div>
          </>
        )}

        {/* Botões de Acção */}
        <div className="flex items-center justify-end gap-2 pt-4 border-t">
          <Button variant="outline" onClick={loadConfig} disabled={saving}>
            Cancelar
          </Button>
          <Button onClick={saveConfig} disabled={saving || !hasChanges}>
            {saving ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                A guardar...
              </>
            ) : (
              <>
                <Save className="h-4 w-4 mr-2" />
                Guardar Configuração
              </>
            )}
          </Button>
        </div>
      </CardContent>

      {/* Dialog Adicionar/Editar Destinatário */}
      <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {editingRecipient ? "Editar Destinatário" : "Adicionar Destinatário"}
            </DialogTitle>
            <DialogDescription>
              Configure o balcão/banco que receberá a documentação
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="name">Nome do Balcão/Banco *</Label>
              <Input
                id="name"
                placeholder="Ex: Millennium BCP, Santander, CGD..."
                value={formData.name}
                onChange={(e) =>
                  setFormData({ ...formData, name: e.target.value })
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">Email *</Label>
              <Input
                id="email"
                type="email"
                placeholder="balcao@banco.pt"
                value={formData.email}
                onChange={(e) =>
                  setFormData({ ...formData, email: e.target.value })
                }
              />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <Label>Activo</Label>
                <p className="text-sm text-muted-foreground">
                  Destinatários inactivos não aparecem na lista de envio
                </p>
              </div>
              <Switch
                checked={formData.active}
                onCheckedChange={(v) => setFormData({ ...formData, active: v })}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowEditDialog(false)}>
              Cancelar
            </Button>
            <Button onClick={handleSaveRecipient}>
              {editingRecipient ? "Guardar Alterações" : "Adicionar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog Confirmar Remoção */}
      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remover Destinatário</AlertDialogTitle>
            <AlertDialogDescription>
              Tem a certeza que deseja remover <strong>{deletingRecipient?.name}</strong>?
              <br />
              Esta ação não pode ser desfeita.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteRecipient} className="bg-red-600 hover:bg-red-700">
              Remover
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
};

export default DocumentRecipientsManager;
