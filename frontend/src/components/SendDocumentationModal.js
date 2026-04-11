/**
 * SendDocumentationModal - Modal para enviar documentação para balcões/bancos
 * 
 * Funcionalidades:
 * - Seleção de documentos do processo
 * - Seleção de destinatários (BCC)
 * - Validação contra contas ativas e simulações do cliente
 * - Preview do email com template pré-preenchido
 * - Rich Text Editor (WYSIWYG) para edição do HTML pelo Admin/CEO
 * 
 * ATUALIZADO: Integração com RichTextEditor para edição visual de HTML
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
import { Badge } from "./ui/badge";
import { ScrollArea } from "./ui/scroll-area";
import { Separator } from "./ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
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
  Edit3,
  Code,
} from "lucide-react";
import { toast } from "sonner";
import RichTextEditor, { RichTextViewer } from "./ui/RichTextEditor";

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
  const [rgpdDocuments, setRgpdDocuments] = useState([]); // RGPD signed docs
  const [selectedDocs, setSelectedDocs] = useState([]);
  const [recipients, setRecipients] = useState([]);
  const [selectedRecipients, setSelectedRecipients] = useState([]);
  const [emailTemplate, setEmailTemplate] = useState("");
  const [ccEmails, setCcEmails] = useState("");
  const [config, setConfig] = useState(null);
  const [warnings, setWarnings] = useState([]);
  const [selectedToEmails, setSelectedToEmails] = useState([]);
  
  // NOVO: Estado para o HTML do email (preview e edição)
  const [emailHtml, setEmailHtml] = useState("");
  const [emailSubject, setEmailSubject] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("preview");

  // Carregar configuração e documentos
  useEffect(() => {
    if (open && processId) {
      loadData();
    }
  }, [open, processId]);

  // Carregar preview do HTML quando os documentos selecionados mudam
  useEffect(() => {
    if (open && processId && selectedDocs.length > 0 && canEditTemplate) {
      loadPreview();
    }
  }, [open, processId, selectedDocs]);

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
        // Pré-selecionar todos os TO emails por padrão
        setSelectedToEmails(configData.default_to_emails || []);
      }

      // Carregar documentos do processo
      const docsRes = await fetch(`${API_URL}/api/documents/process/${processId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      
      if (docsRes.ok) {
        const docsData = await docsRes.json();
        const allDocs = docsData.documents || docsData || [];
        setDocuments(allDocs);
        
        // Separar documentos RGPD assinados (categoria "RGPD") e pré-selecionar
        const rgpdDocs = allDocs.filter(d => d.category === "RGPD" || (d.original_name || "").toLowerCase().includes("rgpd"));
        setRgpdDocuments(rgpdDocs);
        if (rgpdDocs.length > 0) {
          // Pré-selecionar documentos RGPD assinados
          setSelectedDocs(rgpdDocs.map(d => d.id));
        }
      }
      
      // Carregar status do RGPD do processo
      try {
        const rgpdRes = await fetch(`${API_URL}/api/rgpd/status/${processId}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        // RGPD status loaded silently - used to decide pre-selection
      } catch { /* silent */ }
    } catch (error) {
      console.error("Erro ao carregar dados:", error);
      toast.error("Erro ao carregar dados");
    } finally {
      setLoading(false);
    }
  };

  // NOVO: Carregar preview do HTML do backend
  const loadPreview = async () => {
    setPreviewLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/emails/preview-documentation/${processId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      
      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          setEmailHtml(data.html);
          setEmailSubject(data.subject);
        }
      }
    } catch (error) {
      console.error("Erro ao carregar preview:", error);
    } finally {
      setPreviewLoading(false);
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

  // Toggle TO email
  const toggleToEmail = (email) => {
    setSelectedToEmails(prev =>
      prev.includes(email)
        ? prev.filter(e => e !== email)
        : [...prev, email]
    );
  };

  // Selecionar todos os TO emails
  const selectAllToEmails = () => {
    const allTo = config?.default_to_emails || [];
    if (selectedToEmails.length === allTo.length) {
      setSelectedToEmails([]);
    } else {
      setSelectedToEmails(allTo);
    }
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
      toast.error("Selecione pelo menos um destinatário BCC");
      return;
    }

    if (selectedToEmails.length === 0) {
      toast.error("Selecione pelo menos um destinatário TO");
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
      const requestBody = {
        document_ids: selectedDocs,
        s3_paths: selectedDocs.map(id => {
          const doc = documents.find(d => d.id === id);
          return doc?.s3_path;
        }).filter(Boolean),
        to_emails: selectedToEmails,
        bcc_recipients: selectedRecipients,
        cc_emails: ccEmails ? ccEmails.split(",").map(e => e.trim()) : [],
      };

      // NOVO: Enviar HTML customizado do editor se for admin/CEO
      if (canEditTemplate && emailHtml) {
        requestBody.custom_html_body = emailHtml;
      }

      const response = await fetch(`${API_URL}/api/emails/send-documentation/${processId}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(requestBody),
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
        setSelectedToEmails(config?.default_to_emails || []);
        setEmailHtml("");
        setEmailSubject("");
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
      <DialogContent className="max-w-5xl max-h-[90vh]">
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
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Coluna Esquerda: Documentos e Destinatários */}
            <div className="space-y-4">
              {/* Anexos Disponíveis: RGPD assinado */}
              {rgpdDocuments.length > 0 && (
                <div className="border rounded-lg p-3 bg-emerald-50 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-800">
                  <Label className="flex items-center gap-2 mb-2 text-emerald-800 dark:text-emerald-200">
                    <CheckCircle className="h-4 w-4" />
                    RGPD Assinado (pré-selecionado)
                  </Label>
                  <ScrollArea className="h-auto max-h-24">
                    <div className="space-y-1">
                      {rgpdDocuments.map((doc) => (
                        <label
                          key={doc.id}
                          className="flex items-center gap-2 p-2 rounded hover:bg-emerald-100 dark:hover:bg-emerald-900/30 cursor-pointer"
                        >
                          <Checkbox
                            checked={selectedDocs.includes(doc.id)}
                            onCheckedChange={() => toggleDocument(doc.id)}
                          />
                          <FileText className="h-4 w-4 text-emerald-600" />
                          <span className="text-sm truncate flex-1">
                            {doc.original_name || doc.filename || "RGPD"}
                          </span>
                          <Badge variant="outline" className="text-xs text-emerald-700 border-emerald-300">
                            Pré-selecionado
                          </Badge>
                        </label>
                      ))}
                    </div>
                  </ScrollArea>
                </div>
              )}

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
                <ScrollArea className="h-40">
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
                <ScrollArea className="h-40">
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

              {/* TO Emails */}
              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <Label className="text-xs text-muted-foreground">
                    TO (Destinatário Principal) — {selectedToEmails.length}/{(config?.default_to_emails || []).length}
                  </Label>
                  {(config?.default_to_emails || []).length > 1 && (
                    <Button variant="ghost" size="sm" className="h-5 text-xs" onClick={selectAllToEmails}>
                      {selectedToEmails.length === (config?.default_to_emails || []).length ? "Desmarcar todos" : "Selecionar todos"}
                    </Button>
                  )}
                </div>
                {config?.default_to_emails && config.default_to_emails.length > 0 ? (
                  <div className="border rounded-md p-1.5 bg-muted/30 space-y-0.5">
                    {config.default_to_emails.map((email, i) => (
                      <label
                        key={i}
                        className="flex items-center gap-2 p-1.5 rounded hover:bg-muted cursor-pointer"
                      >
                        <Checkbox
                          checked={selectedToEmails.includes(email)}
                          onCheckedChange={() => toggleToEmail(email)}
                        />
                        <Mail className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                        <span className="text-sm font-mono">{email}</span>
                      </label>
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
            </div>

            {/* Coluna Direita: Editor de Email */}
            <div className="lg:col-span-2 space-y-4">
              {/* Tabs: Preview vs Editor */}
              <Tabs value={activeTab} onValueChange={setActiveTab}>
                <div className="flex items-center justify-between">
                  <Label className="text-sm font-medium">
                    Corpo do Email
                    {canEditTemplate && (
                      <Badge variant="outline" className="ml-2 text-xs">
                        Editável (Admin/CEO)
                      </Badge>
                    )}
                  </Label>
                  <TabsList>
                    <TabsTrigger value="preview" className="text-xs">
                      <Eye className="h-3.5 w-3.5 mr-1" />
                      Preview
                    </TabsTrigger>
                    {canEditTemplate && (
                      <TabsTrigger value="edit" className="text-xs">
                        <Edit3 className="h-3.5 w-3.5 mr-1" />
                        Editar HTML
                      </TabsTrigger>
                    )}
                    {canEditTemplate && (
                      <TabsTrigger value="code" className="text-xs">
                        <Code className="h-3.5 w-3.5 mr-1" />
                        Código
                      </TabsTrigger>
                    )}
                  </TabsList>
                </div>

                <TabsContent value="preview" className="mt-2">
                  {previewLoading ? (
                    <div className="flex items-center justify-center py-12 border rounded-lg">
                      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                    </div>
                  ) : (
                    <div className="border rounded-lg overflow-hidden">
                      <RichTextViewer html={emailHtml} className="max-h-[400px] overflow-y-auto" />
                    </div>
                  )}
                </TabsContent>

                {canEditTemplate && (
                  <TabsContent value="edit" className="mt-2">
                    <RichTextEditor
                      value={emailHtml}
                      onChange={setEmailHtml}
                      placeholder="Edite o conteúdo do email..."
                      minHeight={300}
                      className="max-h-[400px] overflow-y-auto"
                    />
                  </TabsContent>
                )}

                {canEditTemplate && (
                  <TabsContent value="code" className="mt-2">
                    <div className="relative">
                      <pre className="bg-muted p-3 rounded-lg text-xs overflow-auto max-h-[400px] font-mono whitespace-pre-wrap border">
                        {emailHtml || "Nenhum HTML gerado"}
                      </pre>
                      <Button
                        size="sm"
                        variant="secondary"
                        className="absolute top-2 right-2"
                        onClick={() => {
                          navigator.clipboard.writeText(emailHtml);
                          toast.success("HTML copiado!");
                        }}
                      >
                        Copiar HTML
                      </Button>
                    </div>
                  </TabsContent>
                )}
              </Tabs>

              {/* Info sobre o email */}
              <div className="text-xs text-muted-foreground space-y-1">
                <p>
                  <strong>Assunto:</strong> {emailSubject || `Documentação - ${process?.client_name || "N/A"} (Processo #${process?.process_number || "N/A"})`}
                </p>
                <p>
                  <strong>Nota:</strong> O editor WYSIWYG permite adicionar notas, apagar texto, formatar tabelas, negritos, etc. O HTML é enviado diretamente no corpo do email.
                </p>
              </div>
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
            disabled={sending || selectedDocs.length === 0 || selectedRecipients.length === 0 || selectedToEmails.length === 0}
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
