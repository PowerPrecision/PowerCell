/**
 * SendDocumentationModal - Modal para enviar documentação para balcões/bancos
 * 
 * Funcionalidades:
 * - Seleção de documentos do processo
 * - Seleção de destinatários (BCC)
 * - Validação contra contas ativas e simulações do cliente
 * - Preview do email com template pré-preenchido
 * - Admin/CEO podem editar o texto do email
 */
import React, { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { Checkbox } from "./ui/checkbox";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Textarea } from "./ui/textarea";
import { Badge } from "./ui/badge";
import { ScrollArea } from "./ui/scroll-area";
import { Separator } from "./ui/separator";
import {
  AlertCircle,
  CheckCircle,
  FileText,
  Mail,
  Send,
  Loader2,
  Users,
  AlertTriangle,
  Building2,
  Eye,
} from "lucide-react";
import { toast } from "sonner";

const API_URL = process.env.REACT_APP_BACKEND_URL || "";

const SendDocumentationModal = ({
  open,
  onOpenChange,
  processId,
  process,
  token,
  user,
}) => {
  // Estado
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [documents, setDocuments] = useState([]);
  const [selectedDocs, setSelectedDocs] = useState([]);
  const [recipients, setRecipients] = useState([]);
  const [selectedRecipients, setSelectedRecipients] = useState([]);
  const [emailTemplate, setEmailTemplate] = useState("");
  const [customMessage, setCustomMessage] = useState("");
  const [ccEmails, setCcEmails] = useState("");
  const [config, setConfig] = useState(null);
  const [warnings, setWarnings] = useState([]);

  // Carregar configuração e documentos
  useEffect(() => {
    if (open && processId) {
      loadData();
    }
  }, [open, processId]);

  const loadData = async () => {
    setLoading(true);
    try {
      // Carregar configuração de destinatários
      const configRes = await fetch(`${API_URL}/api/emails/document-recipients`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      
      if (configRes.ok) {
        const configData = await configRes.json();
        setConfig(configData);
        setRecipients(configData.recipients || []);
        setEmailTemplate(configData.email_template || "");
      }

      // Carregar documentos do processo
      const docsRes = await fetch(`${API_URL}/api/documents/process/${processId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      
      if (docsRes.ok) {
        const docsData = await docsRes.json();
        setDocuments(docsData.documents || docsData || []);
      }
    } catch (error) {
      console.error("Erro ao carregar dados:", error);
      toast.error("Erro ao carregar dados");
    } finally {
      setLoading(false);
    }
  };

  // Verificar se destinatário está bloqueado (cliente tem conta ativa ou simulação)
  const isRecipientBlocked = (recipient) => {
    if (!process?.financial_data) return false;
    
    const financialData = process.financial_data;
    const bancosCreditos = financialData.bancos_creditos || [];
    const bancosSimulacoes = financialData.bancos_simulacoes || [];
    const blockedBanks = [...bancosCreditos, ...bancosSimulacoes].map(b => 
      (b || "").toLowerCase().trim()
    );
    
    const recipientName = (recipient.name || "").toLowerCase().trim();
    
    return blockedBanks.some(blocked => 
      recipientName.includes(blocked) || blocked.includes(recipientName)
    );
  };

  // Toggle documento
  const toggleDocument = (docId) => {
    setSelectedDocs(prev => 
      prev.includes(docId) 
        ? prev.filter(id => id !== docId)
        : [...prev, docId]
    );
  };

  // Toggle destinatário
  const toggleRecipient = (email) => {
    setSelectedRecipients(prev =>
      prev.includes(email)
        ? prev.filter(e => e !== email)
        : [...prev, email]
    );
  };

  // Selecionar todos os documentos
  const selectAllDocs = () => {
    if (selectedDocs.length === documents.length) {
      setSelectedDocs([]);
    } else {
      setSelectedDocs(documents.map(d => d.id));
    }
  };

  // Enviar documentação
  const handleSend = async () => {
    // Validações
    if (selectedDocs.length === 0) {
      toast.error("Selecione pelo menos um documento");
      return;
    }
    
    if (selectedRecipients.length === 0) {
      toast.error("Selecione pelo menos um destinatário");
      return;
    }

    // Verificar destinatários bloqueados
    const blockedRecipients = selectedRecipients.filter(email => {
      const recipient = recipients.find(r => r.email === email);
      return recipient && isRecipientBlocked(recipient);
    });

    if (blockedRecipients.length > 0 && !user?.role?.match(/admin|ceo/i)) {
      toast.error(
        <div>
          <strong>Destinatários bloqueados:</strong>
          <p>Alguns destinatários não podem receber documentação porque o cliente tem conta ativa ou simulação nesses bancos.</p>
        </div>
      );
      return;
    }

    setSending(true);
    try {
      const response = await fetch(`${API_URL}/api/emails/send-documentation/${processId}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          document_ids: selectedDocs,
          bcc_recipients: selectedRecipients,
          cc_emails: ccEmails ? ccEmails.split(",").map(e => e.trim()) : [],
          custom_message: user?.role?.match(/admin|ceo/i) ? customMessage : undefined,
        }),
      });

      const data = await response.json();

      if (response.ok) {
        toast.success(data.message);
        if (data.warnings && data.warnings.length > 0) {
          setWarnings(data.warnings);
          setTimeout(() => setWarnings([]), 5000);
        }
        onOpenChange(false);
        // Reset state
        setSelectedDocs([]);
        setSelectedRecipients([]);
        setCustomMessage("");
        setCcEmails("");
      } else {
        if (response.status === 404) {
          toast.error(data.detail || "Processo ou documento não encontrado.", { duration: 6000 });
        } else {
          toast.error(data.detail || "Erro ao enviar documentação");
        }
      }
    } catch (error) {
      console.error("Erro ao enviar:", error);
      toast.error("Erro ao enviar documentação");
    } finally {
      setSending(false);
    }
  };

  // Preview do email
  const previewEmail = () => {
    const clientName = process?.client_name || "N/A";
    const clientNif = process?.personal_data?.nif || process?.client_nif || "N/A";
    const processNumber = process?.process_number || "N/A";
    const docsList = documents
      .filter(d => selectedDocs.includes(d.id))
      .map(d => `- ${d.original_name || d.filename || "Documento"}`)
      .join("\n");

    let body = customMessage || emailTemplate || "Template não configurado";
    
    body = body
      .replace(/{client_name}/g, clientName)
      .replace(/{client_nif}/g, clientNif)
      .replace(/{process_number}/g, processNumber)
      .replace(/{documents_list}/g, docsList)
      .replace(/{sender_name}/g, user?.name || "")
      .replace(/{sender_email}/g, user?.email || "");

    return body;
  };

  // Verificar permissões
  const canEditTemplate = user?.role?.match(/admin|ceo/i);

  if (!config?.enabled) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertCircle className="h-5 w-5 text-amber-500" />
              Funcionalidade Desactivada
            </DialogTitle>
            <DialogDescription>
              O envio de documentação para balcões não está activado.
              Contacte o administrador para activar esta funcionalidade nas configurações do sistema.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Fechar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Mail className="h-5 w-5 text-primary" />
            Enviar Documentação para Balcões
          </DialogTitle>
          <DialogDescription>
            Envie a documentação do cliente para os balcões/bancos selecionados.
            {process && (
              <span className="block mt-1 font-medium text-foreground">
                Cliente: {process.client_name} • Processo #{process.process_number || "N/A"}
              </span>
            )}
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Coluna Esquerda: Documentos e Destinatários */}
            <div className="space-y-4">
              {/* Documentos */}
              <div className="border rounded-lg p-3">
                <div className="flex items-center justify-between mb-2">
                  <Label className="flex items-center gap-2">
                    <FileText className="h-4 w-4" />
                    Documentos ({selectedDocs.length}/{documents.length})
                  </Label>
                  <Button variant="ghost" size="sm" onClick={selectAllDocs}>
                    {selectedDocs.length === documents.length ? "Desmarcar todos" : "Selecionar todos"}
                  </Button>
                </div>
                <ScrollArea className="h-48">
                  <div className="space-y-1">
                    {documents.map((doc) => (
                      <label
                        key={doc.id}
                        className="flex items-center gap-2 p-2 rounded hover:bg-muted cursor-pointer"
                      >
                        <Checkbox
                          checked={selectedDocs.includes(doc.id)}
                          onCheckedChange={() => toggleDocument(doc.id)}
                        />
                        <FileText className="h-4 w-4 text-muted-foreground" />
                        <span className="text-sm truncate flex-1">
                          {doc.original_name || doc.filename || "Documento"}
                        </span>
                        {doc.size && (
                          <span className="text-xs text-muted-foreground">
                            {(doc.size / 1024).toFixed(1)}KB
                          </span>
                        )}
                      </label>
                    ))}
                    {documents.length === 0 && (
                      <p className="text-sm text-muted-foreground text-center py-4">
                        Nenhum documento disponível
                      </p>
                    )}
                  </div>
                </ScrollArea>
              </div>

              {/* Destinatários */}
              <div className="border rounded-lg p-3">
                <Label className="flex items-center gap-2 mb-2">
                  <Building2 className="h-4 w-4" />
                  Destinatários (BCC) - {selectedRecipients.length} seleccionado(s)
                </Label>
                <ScrollArea className="h-48">
                  <div className="space-y-1">
                    {recipients.map((recipient) => {
                      const isBlocked = isRecipientBlocked(recipient);
                      return (
                        <label
                          key={recipient.email}
                          className={`flex items-center gap-2 p-2 rounded cursor-pointer ${
                            isBlocked 
                              ? "bg-red-50 dark:bg-red-950/20 opacity-75" 
                              : "hover:bg-muted"
                          }`}
                        >
                          <Checkbox
                            checked={selectedRecipients.includes(recipient.email)}
                            onCheckedChange={() => toggleRecipient(recipient.email)}
                            disabled={isBlocked && !canEditTemplate}
                          />
                          <div className="flex-1">
                            <span className="text-sm font-medium">{recipient.name}</span>
                            <span className="text-xs text-muted-foreground block">
                              {recipient.email}
                            </span>
                          </div>
                          {isBlocked && (
                            <Badge variant="outline" className="text-red-600 border-red-300">
                              <AlertTriangle className="h-3 w-3 mr-1" />
                              Bloqueado
                            </Badge>
                          )}
                        </label>
                      );
                    })}
                    {recipients.length === 0 && (
                      <p className="text-sm text-muted-foreground text-center py-4">
                        Nenhum destinatário configurado
                      </p>
                    )}
                  </div>
                </ScrollArea>
              </div>
            </div>

            {/* Coluna Direita: Email */}
            <div className="space-y-4">
              {/* TO — Múltiplos emails */}
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">TO (Destinatário Principal)</Label>
                {config?.default_to_emails && config.default_to_emails.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5 p-2 bg-muted rounded-md min-h-[38px]">
                    {config.default_to_emails.map((email, i) => (
                      <Badge key={i} variant="secondary" className="text-xs font-mono">
                        <Mail className="h-3 w-3 mr-1" />
                        {email}
                      </Badge>
                    ))}
                  </div>
                ) : (
                  <Input
                    value={config?.default_to || ""}
                    disabled
                    className="bg-muted"
                  />
                )}
              </div>

              {/* CC */}
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">CC (opcional, separar por vírgula)</Label>
                <Input
                  placeholder="email1@exemplo.pt, email2@exemplo.pt"
                  value={ccEmails}
                  onChange={(e) => setCcEmails(e.target.value)}
                />
              </div>

              {/* Mensagem */}
              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <Label className="text-xs text-muted-foreground">
                    Mensagem do Email
                    {canEditTemplate && (
                      <Badge variant="outline" className="ml-2 text-xs">
                        Editável (Admin/CEO)
                      </Badge>
                    )}
                  </Label>
                </div>
                {canEditTemplate ? (
                  <Textarea
                    placeholder="Personalize a mensagem do email..."
                    value={customMessage || emailTemplate}
                    onChange={(e) => setCustomMessage(e.target.value)}
                    className="min-h-[200px] font-mono text-sm"
                  />
                ) : (
                  <ScrollArea className="h-48 border rounded-lg p-2 bg-muted">
                    <pre className="text-xs whitespace-pre-wrap font-sans">
                      {previewEmail()}
                    </pre>
                  </ScrollArea>
                )}
                <p className="text-xs text-muted-foreground">
                  Variáveis: {"{client_name}"}, {"{client_nif}"}, {"{process_number}"}, {"{documents_list}"}, {"{sender_name}"}, {"{sender_email}"}
                </p>
              </div>

              {/* Preview */}
              <details className="border rounded-lg">
                <summary className="p-2 cursor-pointer text-sm font-medium flex items-center gap-2">
                  <Eye className="h-4 w-4" />
                  Preview do Email
                </summary>
                <ScrollArea className="h-40 p-2 bg-muted rounded-b-lg">
                  <pre className="text-xs whitespace-pre-wrap font-sans">
                    {previewEmail()}
                  </pre>
                </ScrollArea>
              </details>
            </div>
          </div>
        )}

        {/* Warnings */}
        {warnings.length > 0 && (
          <div className="bg-amber-50 dark:bg-amber-950/20 border border-amber-200 rounded-lg p-3">
            <div className="flex items-start gap-2">
              <AlertTriangle className="h-5 w-5 text-amber-500 mt-0.5" />
              <div>
                <p className="font-medium text-amber-800 dark:text-amber-200">Avisos</p>
                <ul className="text-sm text-amber-700 dark:text-amber-300 list-disc list-inside">
                  {warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button
            onClick={handleSend}
            disabled={sending || selectedDocs.length === 0 || selectedRecipients.length === 0}
          >
            {sending ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                A enviar...
              </>
            ) : (
              <>
                <Send className="h-4 w-4 mr-2" />
                Enviar Documentação ({selectedRecipients.length} destinatário{selectedRecipients.length !== 1 ? "s" : ""})
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default SendDocumentationModal;
