/**
 * SendDocumentationModal — Modal para envio de documentação de clientes para balcões/bancos.
 *
 * PORQUÊ: No setor de crédito habitação em Portugal, a intermediação com balcões
 * bancários é uma operação crítica e frequente. Este modal centraliza o envio de
 * documentos, eliminando o processo manual de compor emails, anexar ficheiros
 * e gerir múltiplos destinatários. Inclui validação contra conflitos de interesse
 * (bloqueia envio para bancos onde o cliente já tem conta activa ou simulação)
 * e suporta edição visual do email pelo Admin/CEO via SmartRichEditor.
 *
 * DECISÕES ARQUITECTURAIS:
 * - Pré-seleção automática de documentos RGPD assinados (categoria "RGPD").
 * - Validação de destinatários bloqueados: compara o nome do balcão com a lista
 *   de bancos_creditos e bancos_simulacoes do cliente (case-insensitive).
 * - TO/BCC/CC separados para controlo de visibilidade (BCC protege a privacidade).
 * - Preview do HTML gerado pelo backend antes do envio.
 * - SmartRichEditor disponível para todos os utilizadores (edição visual ou HTML bruto).
 *
 * @param {Object} props
 * @param {boolean} props.open — Controla se o modal está visível
 * @param {Function} props.onOpenChange — Callback quando o estado de abertura muda
 * @param {string} props.processId — ID do processo para carregar documentos
 * @param {Object} props.process — Dados completos do processo (para validação de bancos)
 * @param {string} props.token — Token JWT de autenticação
 * @param {Object} props.user — Utilizador autenticado ({ role, … })
 *
 * @example
 * <SendDocumentationModal
 *   open={isModalOpen}
 *   onOpenChange={setIsModalOpen}
 *   processId="proc-123"
 *   process={currentProcess}
 *   token={jwtToken}
 *   user={currentUser}
 * />
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
  Tag,
  Copy,
  ChevronDown,
  ChevronUp,
  Euro,
} from "lucide-react";
import { toast } from "sonner";
import { RichTextViewer } from "./ui/RichTextEditor";
import SmartRichEditor from "./ui/SmartRichEditor";
import { safeString } from "../utils/safeString";

const API_URL = process.env.REACT_APP_BACKEND_URL || "";

/**
 * Tags Disponíveis para templates de email bancário.
 * Organizadas por categoria para facilitar a consulta.
 * As tags financeiras (5 novas) estão destacadas com flag `financial: true`.
 * Formato de uso nos templates: [NOME_DA_TAG]
 */
const TEMPLATE_TAG_CATEGORIES = [
  {
    label: "Dados Básicos",
    tags: [
      { key: "client_name", label: "Nome do Cliente" },
      { key: "client_nif", label: "NIF do Cliente" },
      { key: "process_number", label: "Nº do Processo" },
      { key: "documents_list", label: "Lista de Documentos" },
    ],
  },
  {
    label: "1º Proponente",
    tags: [
      { key: "p1_nome", label: "Nome" },
      { key: "p1_email", label: "Email" },
      { key: "p1_telefone", label: "Telefone" },
      { key: "p1_nif", label: "NIF" },
      { key: "p1_data_nascimento", label: "Data de Nascimento" },
      { key: "p1_tipo_doc", label: "Doc. Identificação" },
      { key: "p1_estado_civil", label: "Estado Civil" },
      { key: "p1_regime_casamento", label: "Regime de Casamento" },
      { key: "p1_profissao", label: "Profissão" },
      { key: "p1_vinculo", label: "Vínculo Laboral" },
      { key: "p1_salario", label: "Salário Líquido" },
      { key: "p1_dependentes", label: "Dependentes" },
      { key: "p1_despesas", label: "Despesas Mensais" },
      { key: "p1_situacao_bancaria", label: "Situação Bancária" },
    ],
  },
  {
    label: "2º Proponente",
    tags: [
      { key: "p2_nome", label: "Nome" },
      { key: "p2_email", label: "Email" },
      { key: "p2_telefone", label: "Telefone" },
    ],
  },
  {
    label: "Crédito Atual",
    tags: [
      { key: "banco_atual", label: "Banco Atual" },
      { key: "num_titulares", label: "Nº Titulares" },
      { key: "contrato_mais_2_anos", label: "Contrato > 2 Anos" },
      { key: "valor_aquisicao", label: "Valor Aquisição" },
      { key: "montante_divida", label: "Montante em Dívida" },
    ],
  },
  {
    label: "Transferência",
    tags: [
      { key: "valor_extra", label: "Valor Multiopções" },
      { key: "localidade_imovel", label: "Localidade do Imóvel" },
      { key: "possibilidade_fiador", label: "Possibilidade Fiador" },
    ],
  },
  {
    label: "💰 Financeiras",
    tags: [
      { key: "CAPITAIS_PROPRIOS", label: "Capitais Próprios", financial: true },
      { key: "VALOR_IMOVEL", label: "Valor do Imóvel", financial: true },
      { key: "VALOR_FINANCIAMENTO", label: "Valor Financiamento", financial: true },
      { key: "PRAZO_FINANCIAMENTO", label: "Prazo Financiamento", financial: true },
      { key: "COMPRA_SOZINHO", label: "Compra Sozinho", financial: true },
    ],
  },
  {
    label: "Remetente",
    tags: [
      { key: "sender_name", label: "Nome do Consultor" },
      { key: "sender_email", label: "Email do Consultor" },
      { key: "sender_phone", label: "Telefone do Consultor" },
    ],
  },
];

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
  const [activeTab, setActiveTab] = useState("preview"); // "preview" | "edit"
  const [tagsExpanded, setTagsExpanded] = useState(false);
  const [copiedTag, setCopiedTag] = useState(null);

  // Carregar configuração e documentos
  useEffect(() => {
    if (open && processId) {
      loadData();
    }
  }, [open, processId]);

  // Carregar preview do HTML ao abrir o modal e quando os documentos selecionados mudam
  // O preview deve carregar para TODOS os utilizadores (não só admin/CEO)
  useEffect(() => {
    if (open && processId) {
      loadPreview();
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

    if (blockedRecipients.length > 0 && !isAdminOrCEO) {
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

      // Enviar HTML customizado do editor (disponível para todos os utilizadores)
      if (emailHtml) {
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

  // Verificar permissões — Admin/CEO podem contornar destinatários bloqueados
  const canEditTemplate = true; // Todos os utilizadores podem editar o corpo do email
  const isAdminOrCEO = user?.role?.match(/admin|ceo/i);

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
                Cliente: {safeString(process.client_name)} • Processo #{safeString(process.process_number) || "N/A"}
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
                            disabled={isBlocked && !isAdminOrCEO}
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
                  <p className="text-xs text-muted-foreground italic p-2 bg-muted/50 rounded">
                    Sem destinatários TO configurados. Configure em Definições do Sistema → Documentação.
                  </p>
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
                    <Badge variant="outline" className="ml-2 text-xs">
                      Editável
                    </Badge>
                  </Label>
                  <TabsList>
                    <TabsTrigger value="preview" className="text-xs">
                      <Eye className="h-3.5 w-3.5 mr-1" />
                      Preview
                    </TabsTrigger>
                    <TabsTrigger value="edit" className="text-xs">
                      <Edit3 className="h-3.5 w-3.5 mr-1" />
                      Editar
                    </TabsTrigger>
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

                <TabsContent value="edit" className="mt-2">
                  {previewLoading ? (
                    <div className="flex items-center justify-center py-12 border rounded-lg">
                      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                    </div>
                  ) : (
                    <SmartRichEditor
                      key={emailHtml ? 'preview-loaded' : 'preview-empty'}
                      value={emailHtml}
                      onChange={setEmailHtml}
                      placeholder="Edite o conteúdo do email..."
                      minHeight={300}
                      advanced
                    />
                  )}
                </TabsContent>
              </Tabs>

              {/* Tags Disponíveis para Templates */}
              <div className="border rounded-lg overflow-hidden">
                <button
                  type="button"
                  className="w-full flex items-center justify-between p-2.5 hover:bg-muted/50 transition-colors"
                  onClick={() => setTagsExpanded(!tagsExpanded)}
                >
                  <span className="flex items-center gap-2 text-sm font-medium">
                    <Tag className="h-4 w-4 text-muted-foreground" />
                    Tags Disponíveis
                    <Badge variant="secondary" className="text-xs">
                      {TEMPLATE_TAG_CATEGORIES.reduce((sum, cat) => sum + cat.tags.length, 0)} variáveis
                    </Badge>
                  </span>
                  {tagsExpanded
                    ? <ChevronUp className="h-4 w-4 text-muted-foreground" />
                    : <ChevronDown className="h-4 w-4 text-muted-foreground" />
                  }
                </button>

                {tagsExpanded && (
                  <div className="border-t px-2.5 pb-2.5 pt-2 space-y-3 max-h-72 overflow-y-auto">
                    <p className="text-xs text-muted-foreground">
                      Clique numa tag para copiar <code className="bg-muted px-1 rounded">[TAG]</code> para a área de transferência.
                      Use no template de email do sistema (Configurações → Documentação).
                    </p>
                    {TEMPLATE_TAG_CATEGORIES.map((category) => (
                      <div key={category.label}>
                        <p className="text-xs font-semibold text-muted-foreground mb-1.5 uppercase tracking-wide">
                          {category.label}
                        </p>
                        <div className="flex flex-wrap gap-1.5">
                          {category.tags.map((tag) => (
                            <button
                              key={tag.key}
                              type="button"
                              title={`${tag.label} — clica para copiar [${tag.key}]`}
                              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-mono transition-all cursor-pointer border ${
                                tag.financial
                                  ? "bg-amber-50 dark:bg-amber-950/30 border-amber-300 dark:border-amber-700 text-amber-800 dark:text-amber-200 hover:bg-amber-100 dark:hover:bg-amber-900/40"
                                  : copiedTag === tag.key
                                    ? "bg-emerald-100 dark:bg-emerald-900/30 border-emerald-300 text-emerald-800 dark:text-emerald-200"
                                    : "bg-muted/50 border-border hover:bg-muted text-foreground"
                              }`}
                              onClick={() => {
                                const tagText = `[${tag.key}]`;
                                navigator.clipboard.writeText(tagText).then(() => {
                                  setCopiedTag(tag.key);
                                  toast.success(`Tag ${tagText} copiada!`, { duration: 1500 });
                                  setTimeout(() => setCopiedTag(null), 1500);
                                });
                              }}
                            >
                              {tag.financial && <Euro className="h-3 w-3" />}
                              {copiedTag === tag.key
                                ? <><Copy className="h-3 w-3" /> Copiado</>
                                : <>{tag.key}</>
                              }
                            </button>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Info sobre o email */}
              <div className="text-xs text-muted-foreground space-y-1">
                <p>
                  <strong>Assunto:</strong> {emailSubject || `Documentação - ${safeString(process?.client_name) || "N/A"} (Processo #${safeString(process?.process_number) || "N/A"})`}
                </p>
                <p>
                  <strong>Nota:</strong> Pode editar o conteúdo visualmente no separador "Editar" ou alternar para o modo HTML no botão {'</>'} Editar HTML.
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
