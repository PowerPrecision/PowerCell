/**
 * EmailHistoryPanel - Painel de Histórico de Emails
 * Componente para visualizar e registar emails na ficha do cliente
 */
import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Textarea } from "./ui/textarea";
import { Badge } from "./ui/badge";
import { Label } from "./ui/label";
import { ScrollArea } from "./ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
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
import { 
  Mail, Send, Inbox, Plus, Loader2, Clock, User, 
  Paperclip, MoreVertical, Trash2, Eye, ChevronDown, ChevronUp, RefreshCw,
  Settings, X, AtSign, Maximize2, ExternalLink, Link, Search
} from "lucide-react";
import { toast } from "sonner";
import { format, parseISO } from "date-fns";
import { pt } from "date-fns/locale";
import { getProcessEmails, getEmailStats, createEmail, deleteEmail, syncProcessEmails, getMonitoredEmails, addMonitoredEmail, removeMonitoredEmail } from "../services/api";
import EmailViewerModal from "./EmailViewerModal";

const API_URL = process.env.REACT_APP_BACKEND_URL;

const EmailHistoryPanel = ({ 
  processId, 
  clientEmail,
  clientName,
  compact = false,
  maxHeight = "400px",
  token
}) => {
  const [emails, setEmails] = useState([]);
  const [stats, setStats] = useState({ total: 0, sent: 0, received: 0 });
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [filter, setFilter] = useState("all"); // all, sent, received
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [expandedEmail, setExpandedEmail] = useState(null);
  
  // Modal de visualização
  const [isViewerOpen, setIsViewerOpen] = useState(false);
  const [selectedEmailId, setSelectedEmailId] = useState(null);
  
  // Emails monitorizados
  const [monitoredEmails, setMonitoredEmails] = useState([]);
  const [newMonitoredEmail, setNewMonitoredEmail] = useState("");
  const [addingEmail, setAddingEmail] = useState(false);
  
  // TAREFA 1: Associação manual de emails
  const [isAssociateDialogOpen, setIsAssociateDialogOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [associating, setAssociating] = useState(null);
  
  // Pesquisa local no histórico
  const [localSearchTerm, setLocalSearchTerm] = useState("");
  
  // URLs dos webmails
  const WEBMAIL_URLS = {
    precision: "http://webmail.precisioncredito.pt/",
    power: "https://webmail2.hcpro.pt/Mondo/lang/sys/login.aspx"
  };
  
  // Form state
  const [newEmail, setNewEmail] = useState({
    direction: "sent",
    from_email: "",
    to_emails: "",
    subject: "",
    body: "",
    notes: ""
  });
  
  const openWebmail = (webmail) => {
    window.open(WEBMAIL_URLS[webmail], '_blank');
  };
  
  const openEmailViewer = (emailId) => {
    setSelectedEmailId(emailId);
    setIsViewerOpen(true);
  };

  useEffect(() => {
    if (processId) {
      fetchData();
      fetchMonitoredEmails();
    }
  }, [processId, filter]);

  const fetchMonitoredEmails = async () => {
    try {
      const response = await getMonitoredEmails(processId);
      setMonitoredEmails(response.data.monitored_emails || []);
    } catch (error) {
      console.error("Erro ao carregar emails monitorizados:", error);
    }
  };

  const handleAddMonitoredEmail = async () => {
    if (!newMonitoredEmail.trim() || !newMonitoredEmail.includes("@")) {
      toast.error("Introduza um email válido");
      return;
    }
    try {
      setAddingEmail(true);
      await addMonitoredEmail(processId, newMonitoredEmail.trim());
      toast.success("Email adicionado à monitorização");
      setNewMonitoredEmail("");
      fetchMonitoredEmails();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Erro ao adicionar email");
    } finally {
      setAddingEmail(false);
    }
  };

  const handleRemoveMonitoredEmail = async (email) => {
    try {
      await removeMonitoredEmail(processId, email);
      toast.success("Email removido da monitorização");
      fetchMonitoredEmails();
    } catch (error) {
      toast.error("Erro ao remover email");
    }
  };

  // TAREFA 1: Pesquisar emails para associação
  const handleSearchEmails = async () => {
    if (!searchQuery.trim() || searchQuery.length < 3) {
      toast.error("Introduza pelo menos 3 caracteres para pesquisar");
      return;
    }
    try {
      setSearching(true);
      const response = await fetch(
        `${API_URL}/api/emails/search?q=${encodeURIComponent(searchQuery)}&limit=20`,
        {
          headers: { Authorization: `Bearer ${token}` }
        }
      );
      if (!response.ok) throw new Error("Erro na pesquisa");
      const data = await response.json();
      setSearchResults(data.emails || []);
    } catch (error) {
      toast.error("Erro ao pesquisar emails");
    } finally {
      setSearching(false);
    }
  };

  // TAREFA 1: Associar email ao cliente
  const handleAssociateEmail = async (emailId) => {
    try {
      setAssociating(emailId);
      const response = await fetch(`${API_URL}/api/emails/associate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({
          email_id: emailId,
          process_id: processId
        })
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Erro ao associar email");
      }
      const result = await response.json();
      toast.success(result.message);
      setIsAssociateDialogOpen(false);
      setSearchQuery("");
      setSearchResults([]);
      fetchData();
    } catch (error) {
      toast.error(error.message);
    } finally {
      setAssociating(null);
    }
  };

  const fetchData = async () => {
    try {
      setLoading(true);
      const [emailsRes, statsRes] = await Promise.all([
        getProcessEmails(processId, filter === "all" ? null : filter),
        getEmailStats(processId)
      ]);
      setEmails(emailsRes.data);
      setStats(statsRes.data);
    } catch (error) {
      console.error("Erro ao carregar emails:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleSyncEmails = async () => {
    if (!clientEmail && monitoredEmails.length === 0) {
      toast.error("Adicione pelo menos um email para monitorizar antes de sincronizar");
      return;
    }

    try {
      setSyncing(true);
      toast.info("A iniciar sincronização de emails em background...");
      
      const response = await syncProcessEmails(processId, 60);
      
      // Verificar se a sincronização foi iniciada em background
      if (response.data.status === "started") {
        toast.success("Sincronização iniciada! Os emails serão importados em alguns minutos.");
        // Polling para verificar o status
        const checkStatus = async () => {
          try {
            const statusResponse = await fetch(
              `${process.env.REACT_APP_BACKEND_URL}/api/emails/sync-status/${processId}`,
              { headers: { Authorization: `Bearer ${token}` } }
            );
            const status = await statusResponse.json();
            
            if (status.status === "completed") {
              toast.success(`Sincronização concluída: ${status.result?.new_imported || 0} novos emails importados`);
              fetchData();
              setSyncing(false);
            } else if (status.status === "error") {
              toast.error(`Erro na sincronização: ${status.error}`);
              setSyncing(false);
            } else if (status.status === "running") {
              // Continuar polling
              setTimeout(checkStatus, 5000);
            } else {
              setSyncing(false);
            }
          } catch (e) {
            console.error("Erro ao verificar status:", e);
            setSyncing(false);
          }
        };
        // Iniciar polling após 3 segundos
        setTimeout(checkStatus, 3000);
      } else if (response.data.success) {
        // Resposta síncrona (modo blocking)
        toast.success(`Sincronização concluída: ${response.data.new_imported} novos emails importados`);
        fetchData();
        setSyncing(false);
      } else {
        const errorMsg = response.data.error || "";
        if (errorMsg.includes("não configurada") || errorMsg.includes("not configured")) {
          toast.error("Conta de email não configurada. Contacte o administrador.");
        } else {
          toast.error(errorMsg || "Erro na sincronização");
        }
        setSyncing(false);
      }
    } catch (error) {
      console.error("Erro ao sincronizar:", error);
      const detail = error.response?.data?.detail || "";
      if (detail.includes("não configurada") || detail.includes("not configured") || detail.includes("IMAP")) {
        toast.error("Conta de email não configurada pelo administrador. A sincronização não está disponível.");
      } else {
        toast.error(detail || "Erro ao sincronizar emails");
      }
      setSyncing(false);
    }
  };

  const handleCreateEmail = async () => {
    if (!newEmail.subject.trim() || !newEmail.body.trim()) {
      toast.error("Assunto e corpo são obrigatórios");
      return;
    }
    if (!newEmail.to_emails.trim()) {
      toast.error("Destinatário é obrigatório");
      return;
    }

    try {
      setCreating(true);
      
      // Preparar dados
      const toEmails = newEmail.to_emails.split(",").map(e => e.trim()).filter(e => e);
      
      await createEmail({
        process_id: processId,
        direction: newEmail.direction,
        from_email: newEmail.from_email || (newEmail.direction === "sent" ? "sistema@precisioncredito.pt" : clientEmail),
        to_emails: toEmails,
        subject: newEmail.subject,
        body: newEmail.body,
        notes: newEmail.notes,
        status: "sent"
      });
      
      toast.success("Email registado com sucesso");
      setIsCreateDialogOpen(false);
      setNewEmail({
        direction: "sent",
        from_email: "",
        to_emails: "",
        subject: "",
        body: "",
        notes: ""
      });
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Erro ao registar email");
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteEmail = async (emailId) => {
    if (!window.confirm("Tem a certeza que deseja eliminar este registo de email?")) return;
    try {
      await deleteEmail(emailId);
      toast.success("Email eliminado");
      fetchData();
    } catch (error) {
      toast.error("Erro ao eliminar email");
    }
  };

  const openCreateDialog = (direction = "sent") => {
    setNewEmail({
      direction,
      from_email: direction === "sent" ? "" : clientEmail || "",
      to_emails: direction === "sent" ? clientEmail || "" : "",
      subject: "",
      body: "",
      notes: ""
    });
    setIsCreateDialogOpen(true);
  };

  const toggleExpandEmail = (emailId) => {
    setExpandedEmail(expandedEmail === emailId ? null : emailId);
  };

  if (loading && emails.length === 0) {
    return (
      <Card className="border-border">
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin" />
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card className="border-border">
        <CardHeader className={compact ? "pb-2" : ""}>
          <div className="space-y-3">
            {/* Título */}
            <div className="flex items-center justify-between">
              <CardTitle className={`flex items-center gap-2 ${compact ? "text-base" : "text-lg"}`}>
                <Mail className="h-5 w-5" />
                Histórico de Emails
                {stats.total > 0 && (
                  <Badge variant="secondary" className="ml-2">{stats.total}</Badge>
                )}
              </CardTitle>
            </div>
            
            {/* Botões de acção - numa linha separada */}
            <div className="flex flex-wrap items-center gap-2">
              <Button 
                size="sm" 
                variant="outline"
                onClick={() => openWebmail('precision')}
                title="Abrir Webmail Precision"
                data-testid="email-webmail-precision-btn"
              >
                <Mail className="h-4 w-4 mr-1" />
                <span className="text-xs">Precision</span>
                <ExternalLink className="h-3 w-3 ml-1" />
              </Button>
              <Button 
                size="sm" 
                variant="outline"
                onClick={() => openWebmail('power')}
                title="Abrir Webmail Power"
                data-testid="email-webmail-power-btn"
              >
                <Mail className="h-4 w-4 mr-1" />
                <span className="text-xs">Power</span>
                <ExternalLink className="h-3 w-3 ml-1" />
              </Button>
              <Button 
                size="sm" 
                variant="outline"
                onClick={() => setIsAssociateDialogOpen(true)}
                title="Associar email manualmente"
                data-testid="email-associate-btn"
                className="bg-blue-50 hover:bg-blue-100 border-blue-200 dark:bg-blue-950 dark:border-blue-800"
              >
                <Link className="h-4 w-4 mr-1" />
                <span className="text-xs">Associar</span>
              </Button>
              <Button 
                size="sm" 
                variant="outline"
                onClick={() => setIsSettingsOpen(true)}
                title="Configurar emails monitorizados"
                data-testid="email-settings-btn"
                className="bg-amber-50 hover:bg-amber-100 border-amber-200"
              >
                <Settings className="h-4 w-4 mr-1" />
                <span className="text-xs">Emails</span>
              </Button>
              <Button 
                size="sm" 
                variant="outline"
                onClick={handleSyncEmails}
                disabled={syncing || (!clientEmail && monitoredEmails.length === 0)}
                title="Sincronizar emails do servidor"
                data-testid="email-sync-btn"
              >
                {syncing ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="h-4 w-4" />
                )}
                <span className="text-xs ml-1">Sync</span>
              </Button>
            </div>
            
            {!compact && (
              <CardDescription className="text-xs">
                {stats.sent} enviado(s) • {stats.received} recebido(s)
                {monitoredEmails.length > 0 && ` • ${monitoredEmails.length + 1} email(s) monitorizados`}
              </CardDescription>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {/* Campo de Pesquisa */}
          <div className="relative mb-3">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Pesquisar emails por assunto, remetente..."
              value={localSearchTerm}
              onChange={(e) => setLocalSearchTerm(e.target.value)}
              className="pl-9 h-9 text-sm"
              data-testid="email-search-input"
            />
            {localSearchTerm && (
              <Button
                variant="ghost"
                size="sm"
                className="absolute right-1 top-1/2 -translate-y-1/2 h-7 w-7 p-0"
                onClick={() => setLocalSearchTerm("")}
              >
                <X className="h-3 w-3" />
              </Button>
            )}
          </div>

          {/* Filtros */}
          <Tabs value={filter} onValueChange={setFilter} className="mb-4">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="all" className="text-xs">
                Todos ({stats.total})
              </TabsTrigger>
              <TabsTrigger value="sent" className="text-xs">
                <Send className="h-3 w-3 mr-1" />
                Enviados ({stats.sent})
              </TabsTrigger>
              <TabsTrigger value="received" className="text-xs">
                <Inbox className="h-3 w-3 mr-1" />
                Recebidos ({stats.received})
              </TabsTrigger>
            </TabsList>
          </Tabs>

          {/* Lista de emails - Layout compacto com scroll horizontal no assunto */}
          {(() => {
            // Filtrar emails pela pesquisa local
            const filteredEmails = localSearchTerm.trim() 
              ? emails.filter(email => 
                  (email.subject && email.subject.toLowerCase().includes(localSearchTerm.toLowerCase())) ||
                  (email.from_email && email.from_email.toLowerCase().includes(localSearchTerm.toLowerCase())) ||
                  (email.to_email && email.to_email.toLowerCase().includes(localSearchTerm.toLowerCase())) ||
                  (email.body_preview && email.body_preview.toLowerCase().includes(localSearchTerm.toLowerCase()))
                )
              : emails;
            
            if (emails.length === 0) {
              return (
                <div className="text-center py-8 text-muted-foreground">
                  <Mail className="h-12 w-12 mx-auto mb-2 opacity-20" />
                  <p>Nenhum email registado</p>
                  <Button 
                    variant="outline" 
                    className="mt-4"
                    onClick={() => openCreateDialog("sent")}
                  >
                    <Plus className="h-4 w-4 mr-2" />
                    Registar Email
                  </Button>
                </div>
              );
            }
            
            if (filteredEmails.length === 0 && localSearchTerm) {
              return (
                <div className="text-center py-8 text-muted-foreground">
                  <Search className="h-12 w-12 mx-auto mb-2 opacity-20" />
                  <p>Nenhum email encontrado para "{localSearchTerm}"</p>
                  <Button 
                    variant="outline" 
                    className="mt-4"
                    onClick={() => setLocalSearchTerm("")}
                  >
                    <X className="h-4 w-4 mr-2" />
                    Limpar pesquisa
                  </Button>
                </div>
              );
            }
            
            return (
              <ScrollArea className="pr-1" style={{ height: maxHeight }}>
                <div className="space-y-1">
                  {filteredEmails.map((email) => (
                  <div
                    key={email.id}
                    className={`flex items-center gap-2 p-2 rounded-lg border cursor-pointer hover:bg-muted/50 transition-colors ${
                      email.direction === "sent" 
                        ? "bg-blue-50/30 dark:bg-blue-950/10 border-blue-200/50 dark:border-blue-800/50" 
                        : "bg-emerald-50/30 dark:bg-emerald-950/10 border-emerald-200/50 dark:border-emerald-800/50"
                    }`}
                    onClick={() => openEmailViewer(email.id)}
                  >
                    {/* Ícone de direção */}
                    <div className={`p-1.5 rounded shrink-0 ${
                      email.direction === "sent" 
                        ? "bg-blue-100 dark:bg-blue-900/50 text-blue-600 dark:text-blue-300" 
                        : "bg-emerald-100 dark:bg-emerald-900/50 text-emerald-600 dark:text-emerald-300"
                    }`}>
                      {email.direction === "sent" ? (
                        <Send className="h-3 w-3" />
                      ) : (
                        <Inbox className="h-3 w-3" />
                      )}
                    </div>

                    {/* Conteúdo com scroll horizontal */}
                    <div className="flex-1 min-w-0 overflow-hidden">
                      <div className="overflow-x-auto scrollbar-thin scrollbar-thumb-muted">
                        <p className="font-medium text-sm whitespace-nowrap pr-2" title={email.subject}>
                          {email.subject}
                        </p>
                      </div>
                      <p className="text-xs text-muted-foreground truncate">
                        {email.direction === "sent" ? "Para: " : "De: "}
                        {email.direction === "sent" 
                          ? email.to_emails?.join(", ")
                          : email.from_email
                        }
                      </p>
                      {/* Mostrar CC se existir - destacado */}
                      {email.cc_emails?.length > 0 && (
                        <p className="text-xs text-amber-600 dark:text-amber-400 font-medium flex items-center gap-1">
                          <span className="text-[10px] bg-amber-100 dark:bg-amber-900/50 px-1 rounded">CC</span>
                          <span className="truncate">{email.cc_emails.join(", ")}</span>
                        </p>
                      )}
                    </div>

                    {/* Data e botão */}
                    <div className="flex items-center gap-2 shrink-0">
                      <span className="text-[10px] text-muted-foreground whitespace-nowrap">
                        {email.sent_at 
                          ? format(parseISO(email.sent_at), "dd/MM/yy", { locale: pt })
                          : "-"
                        }
                      </span>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        onClick={(e) => {
                          e.stopPropagation();
                          openEmailViewer(email.id);
                        }}
                        title="Ver email completo"
                      >
                        <Maximize2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
            );
          })()}
        </CardContent>
      </Card>

      {/* Modal para visualização de email */}
      <EmailViewerModal
        isOpen={isViewerOpen}
        onClose={() => setIsViewerOpen(false)}
        emails={emails}
        selectedEmailId={selectedEmailId}
        onSelectEmail={setSelectedEmailId}
      />

      {/* Dialog para registar email */}
      <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
        <DialogContent className="sm:max-w-[600px]">
          <DialogHeader>
            <DialogTitle>
              {newEmail.direction === "sent" ? "Registar Email Enviado" : "Registar Email Recebido"}
            </DialogTitle>
            <DialogDescription>
              {newEmail.direction === "sent" 
                ? "Registe um email que foi enviado ao cliente"
                : "Registe um email que foi recebido do cliente"
              }
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4 py-4">
            {/* Direção */}
            <div className="space-y-2">
              <Label>Tipo</Label>
              <Select 
                value={newEmail.direction} 
                onValueChange={(v) => setNewEmail(prev => ({ 
                  ...prev, 
                  direction: v,
                  from_email: v === "sent" ? "" : clientEmail || "",
                  to_emails: v === "sent" ? clientEmail || "" : ""
                }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="sent">
                    <div className="flex items-center gap-2">
                      <Send className="h-4 w-4" />
                      Email Enviado
                    </div>
                  </SelectItem>
                  <SelectItem value="received">
                    <div className="flex items-center gap-2">
                      <Inbox className="h-4 w-4" />
                      Email Recebido
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>De</Label>
                <Input
                  placeholder="email@exemplo.pt"
                  value={newEmail.from_email}
                  onChange={(e) => setNewEmail(prev => ({ ...prev, from_email: e.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label>Para *</Label>
                <Input
                  placeholder="email@exemplo.pt (separar com vírgula)"
                  value={newEmail.to_emails}
                  onChange={(e) => setNewEmail(prev => ({ ...prev, to_emails: e.target.value }))}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label>Assunto *</Label>
              <Input
                placeholder="Assunto do email"
                value={newEmail.subject}
                onChange={(e) => setNewEmail(prev => ({ ...prev, subject: e.target.value }))}
              />
            </div>
            
            <div className="space-y-2">
              <Label>Corpo do Email *</Label>
              <Textarea
                placeholder="Conteúdo do email..."
                value={newEmail.body}
                onChange={(e) => setNewEmail(prev => ({ ...prev, body: e.target.value }))}
                rows={6}
              />
            </div>

            <div className="space-y-2">
              <Label>Notas (opcional)</Label>
              <Input
                placeholder="Notas internas sobre este email"
                value={newEmail.notes}
                onChange={(e) => setNewEmail(prev => ({ ...prev, notes: e.target.value }))}
              />
            </div>
          </div>
          
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsCreateDialogOpen(false)}>
              Cancelar
            </Button>
            <Button 
              onClick={handleCreateEmail} 
              disabled={creating}
              className="bg-teal-600 hover:bg-teal-700"
            >
              {creating ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Plus className="h-4 w-4 mr-2" />}
              Registar Email
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog de Configurações de Emails Monitorizados */}
      <Dialog open={isSettingsOpen} onOpenChange={setIsSettingsOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AtSign className="h-5 w-5" />
              Emails Monitorizados
            </DialogTitle>
            <DialogDescription>
              Configure os emails que serão sincronizados para este processo.
              Os emails de geral@powerealestate.pt e geral@precisioncredito.pt são verificados automaticamente.
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4 py-4">
            {/* Email principal do cliente */}
            <div>
              <Label className="text-sm font-medium">Email Principal do Cliente</Label>
              <div className="flex items-center gap-2 mt-1 p-2 bg-muted rounded-md">
                <Mail className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm">{clientEmail || "Não definido"}</span>
                <Badge variant="outline" className="ml-auto text-xs">Principal</Badge>
              </div>
            </div>

            {/* Emails adicionais */}
            <div>
              <Label className="text-sm font-medium">Emails Adicionais</Label>
              <p className="text-xs text-muted-foreground mb-2">
                Adicione outros emails relacionados com este processo (bancos, intermediários, etc.)
              </p>
              
              {/* Lista de emails monitorizados */}
              {monitoredEmails.length > 0 ? (
                <div className="space-y-2 mb-3">
                  {monitoredEmails.map((email) => (
                    <div key={email} className="flex items-center gap-2 p-2 bg-muted/50 rounded-md">
                      <AtSign className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm flex-1">{email}</span>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 w-6 p-0 text-destructive hover:text-destructive"
                        onClick={() => handleRemoveMonitoredEmail(email)}
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground italic mb-3">
                  Nenhum email adicional configurado
                </p>
              )}

              {/* Adicionar novo email */}
              <div className="flex gap-2">
                <Input
                  placeholder="email@exemplo.pt"
                  value={newMonitoredEmail}
                  onChange={(e) => setNewMonitoredEmail(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleAddMonitoredEmail()}
                />
                <Button 
                  onClick={handleAddMonitoredEmail}
                  disabled={addingEmail}
                  size="sm"
                >
                  {addingEmail ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Plus className="h-4 w-4" />
                  )}
                </Button>
              </div>
            </div>

            {/* Contas de email da empresa */}
            <div className="pt-2 border-t">
              <Label className="text-sm font-medium">Contas da Empresa</Label>
              <p className="text-xs text-muted-foreground mb-2">
                Emails da empresa onde os emails são sincronizados
              </p>
              <div className="space-y-1">
                <div className="flex items-center gap-2 text-sm">
                  <Badge variant="outline" className="text-xs">Precision</Badge>
                  geral@precisioncredito.pt
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <Badge variant="outline" className="text-xs">Power</Badge>
                  geral@powerealestate.pt
                </div>
              </div>
            </div>
          </div>
          
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsSettingsOpen(false)}>
              Fechar
            </Button>
            <Button 
              onClick={() => {
                setIsSettingsOpen(false);
                handleSyncEmails();
              }}
              className="bg-teal-600 hover:bg-teal-700"
            >
              <RefreshCw className="h-4 w-4 mr-2" />
              Sincronizar Agora
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* TAREFA 1: Dialog para Associar Email Manualmente */}
      <Dialog open={isAssociateDialogOpen} onOpenChange={setIsAssociateDialogOpen}>
        <DialogContent className="sm:max-w-[600px]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Link className="h-5 w-5" />
              Associar Email ao Cliente
            </DialogTitle>
            <DialogDescription>
              Pesquise um email existente pelo assunto ou remetente para associar a este cliente.
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4 py-4">
            {/* Pesquisa */}
            <div className="flex gap-2">
              <Input
                placeholder="Pesquisar por assunto ou remetente..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearchEmails()}
              />
              <Button onClick={handleSearchEmails} disabled={searching}>
                {searching ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Search className="h-4 w-4" />
                )}
              </Button>
            </div>

            {/* Resultados */}
            <ScrollArea className="h-[300px] border rounded-md p-2">
              {searchResults.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  <Search className="h-8 w-8 mx-auto mb-2 opacity-30" />
                  <p className="text-sm">
                    {searchQuery.length > 0 ? "Nenhum resultado encontrado" : "Pesquise para ver resultados"}
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  {searchResults.map((email) => (
                    <div 
                      key={email.id}
                      className="p-3 border rounded-lg hover:bg-muted/50 cursor-pointer"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <p className="font-medium text-sm truncate">{email.subject}</p>
                          <p className="text-xs text-muted-foreground truncate">
                            De: {email.from_email}
                          </p>
                          <div className="flex items-center gap-2 mt-1">
                            <span className="text-xs text-muted-foreground">
                              {email.sent_at && format(parseISO(email.sent_at), "dd/MM/yyyy", { locale: pt })}
                            </span>
                            {email.client_name && (
                              <Badge variant="outline" className="text-xs">
                                Já associado: {email.client_name}
                              </Badge>
                            )}
                          </div>
                        </div>
                        <Button
                          size="sm"
                          onClick={() => handleAssociateEmail(email.id)}
                          disabled={associating === email.id || email.process_id === processId}
                          className="shrink-0"
                        >
                          {associating === email.id ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : email.process_id === processId ? (
                            "Já associado"
                          ) : (
                            <>
                              <Link className="h-4 w-4 mr-1" />
                              Associar
                            </>
                          )}
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </ScrollArea>
          </div>
          
          <DialogFooter>
            <Button variant="outline" onClick={() => {
              setIsAssociateDialogOpen(false);
              setSearchQuery("");
              setSearchResults([]);
            }}>
              Fechar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default EmailHistoryPanel;
