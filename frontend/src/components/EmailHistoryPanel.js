/**
 * EmailHistoryPanel - Painel de Histórico de Emails
 * Componente para visualizar e registar emails na ficha do cliente
 * 
 * MELHORIAS:
 * - Visualização de anexos (preview, download)
 * - Filtros avançados (por data, por conta, por tipo)
 * - Marcação de emails (importante, lido, etc.)
 * - Templates de resposta rápida
 * - Timeline de emails no processo
 */
import { useState, useEffect, useMemo } from "react";
import { extractErrorMessage } from "../utils/extractErrorMessage";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Badge } from "./ui/badge";
import { Label } from "./ui/label";
import { ScrollArea } from "./ui/scroll-area";
import { Tabs, TabsList, TabsTrigger } from "./ui/tabs";
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
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "./ui/popover";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";
import { Checkbox } from "./ui/checkbox";
import { 
  Mail, Send, Inbox, Plus, Loader2, Clock, 
  Paperclip, MoreVertical, Trash2, Eye, RefreshCw,
  Settings, X, AtSign, ExternalLink, Unlink, Search,
  Star, StarOff,
  Filter, Calendar, FileText, Download,
  AlertCircle, CheckCircle, Copy,
  EyeOff
} from "lucide-react";
import { toast } from "sonner";
import { isAfter, isBefore, startOfDay, endOfDay } from "date-fns";
import { pt } from "date-fns/locale";
import {
  getProcessEmails, deleteEmail, syncProcessEmails, getMonitoredEmails,
  addMonitoredEmail, removeMonitoredEmail, getEmailStats,
  markEmail as markEmailRequest, unmarkEmail as unmarkEmailRequest,
  disassociateEmailFromProcess, getProcessEmailSyncStatus,
  downloadWebmailAttachment, readBlobErrorBody,
} from "../services/api";
import EmailViewerModal from "./EmailViewerModal";
import { safeFormat, safeParseISO } from "../lib/utils";


// Tamanhos de arquivo

// Ícone por tipo de anexo

const EmailHistoryPanel = ({ 
  processId, 
  clientEmail,
  clientName,
  compact = false,
  maxHeight = "400px",
  token
}) => {
  const [emails, setEmails] = useState([]);
  const [stats, setStats] = useState({ total: 0, sent: 0, received: 0, unread: 0, important: 0, starred: 0 });
  const [loading, setLoading] = useState(true);
  // O servidor recusou a lista (403/404): di-lo, em vez de parecer «sem emails».
  const [acessoNegado, setAcessoNegado] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [filter, setFilter] = useState("all"); // all, sent, received
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  
  // Modal de visualização
  const [isViewerOpen, setIsViewerOpen] = useState(false);
  const [selectedEmailId, setSelectedEmailId] = useState(null);
  
  // Emails monitorizados
  const [monitoredEmails, setMonitoredEmails] = useState([]);
  const [newMonitoredEmail, setNewMonitoredEmail] = useState("");
  const [addingEmail, setAddingEmail] = useState(false);
  
  // Associação manual
  
  // Pesquisa local
  const [localSearchTerm, setLocalSearchTerm] = useState("");
  
  // Filtros avançados
  const [advancedFilters, setAdvancedFilters] = useState({
    account: "all",
    dateFrom: "",
    dateTo: "",
    hasAttachments: "all",
    isImportant: false,
    isUnread: false,
    isStarred: false
  });
  
  // Anexos
  const [attachmentPreview, setAttachmentPreview] = useState(null);
  
  // Timeline mode
  const [timelineMode, setTimelineMode] = useState(false);
  const [emailTimeline, setEmailTimeline] = useState([]);
  
  // URLs dos webmails
  const WEBMAIL_URLS = {
    precision: "http://webmail.precisioncredito.pt/",
    power: "https://webmail2.hcpro.pt/Mondo/lang/sys/login.aspx"
  };
  
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
  }, [processId, filter, advancedFilters]);

  const fetchMonitoredEmails = async () => {
    try {
      const response = await getMonitoredEmails(processId);
      setMonitoredEmails(response.data.monitored_emails || []);
    } catch (error) {
      console.error("Erro ao carregar emails monitorizados:", error);
    }
  };

  // Filtros avançados aplicados
  const filteredEmails = useMemo(() => {
    let filtered = [...emails];
    
    // Pesquisa local
    if (localSearchTerm.trim()) {
      const term = localSearchTerm.toLowerCase();
      filtered = filtered.filter(email => 
        (email.subject && email.subject.toLowerCase().includes(term)) ||
        (email.from_email && email.from_email.toLowerCase().includes(term)) ||
        (email.to_emails && email.to_emails.some(e => e.toLowerCase().includes(term))) ||
        (email.body && email.body.toLowerCase().includes(term))
      );
    }
    
    // Filtro por conta
    if (advancedFilters.account !== "all") {
      filtered = filtered.filter(e => e.account === advancedFilters.account);
    }
    
    // Filtro por data (protecção defensiva: safeParseISO pode retornar null)
    if (advancedFilters.dateFrom) {
      const fromParsed = safeParseISO(advancedFilters.dateFrom);
      if (fromParsed) {
        const fromDate = startOfDay(fromParsed);
        filtered = filtered.filter(e => {
          if (!e.sent_at) return false;
          const sentParsed = safeParseISO(e.sent_at);
          return sentParsed ? isAfter(sentParsed, fromDate) : false;
        });
      }
    }
    if (advancedFilters.dateTo) {
      const toParsed = safeParseISO(advancedFilters.dateTo);
      if (toParsed) {
        const toDate = endOfDay(toParsed);
        filtered = filtered.filter(e => {
          if (!e.sent_at) return false;
          const sentParsed = safeParseISO(e.sent_at);
          return sentParsed ? isBefore(sentParsed, toDate) : false;
        });
      }
    }
    
    // Filtro por anexos
    if (advancedFilters.hasAttachments === "yes") {
      filtered = filtered.filter(e => e.attachments && e.attachments.length > 0);
    } else if (advancedFilters.hasAttachments === "no") {
      filtered = filtered.filter(e => !e.attachments || e.attachments.length === 0);
    }
    
    // Filtro por marcações
    if (advancedFilters.isImportant) {
      filtered = filtered.filter(e => e.is_important);
    }
    if (advancedFilters.isUnread) {
      filtered = filtered.filter(e => !e.is_read);
    }
    if (advancedFilters.isStarred) {
      filtered = filtered.filter(e => e.is_starred);
    }
    
    return filtered;
  }, [emails, localSearchTerm, advancedFilters]);

  // Agrupar emails por data para timeline
  useEffect(() => {
    if (timelineMode && emails.length > 0) {
      const grouped = {};
      emails.forEach(email => {
        if (email.sent_at) {
          const dateKey = email.sent_at.substring(0, 10);
          if (!grouped[dateKey]) {
            grouped[dateKey] = {
              date: dateKey,
              emails: [],
              stats: { sent: 0, received: 0 }
            };
          }
          grouped[dateKey].emails.push(email);
          if (email.direction === "sent") {
            grouped[dateKey].stats.sent++;
          } else {
            grouped[dateKey].stats.received++;
          }
        }
      });
      setEmailTimeline(Object.values(grouped).sort((a, b) => b.date.localeCompare(a.date)));
    }
  }, [timelineMode, emails]);

  // Marcação de emails
  const markEmail = async (emailId, markType) => {
    try {
      await markEmailRequest(emailId, { mark_type: markType });
      
      // Actualizar local
      setEmails(prev => prev.map(e => {
        if (e.id === emailId) {
          const updated = { ...e };
          if (markType === "important") updated.is_important = true;
          if (markType === "read") updated.is_read = true;
          if (markType === "unread") updated.is_read = false;
          if (markType === "starred") updated.is_starred = true;
          if (markType === "archived") updated.is_archived = true;
          return updated;
        }
        return e;
      }));
      
      toast.success(`Email marcado como ${markType}`);
    } catch {
      toast.error("Erro ao marcar email");
    }
  };

  const unmarkEmail = async (emailId, markType) => {
    try {
      await unmarkEmailRequest(emailId, markType);
      
      // Actualizar local
      setEmails(prev => prev.map(e => {
        if (e.id === emailId) {
          const updated = { ...e };
          if (markType === "important") updated.is_important = false;
          if (markType === "starred") updated.is_starred = false;
          if (markType === "archived") updated.is_archived = false;
          return updated;
        }
        return e;
      }));
      
      toast.success("Marcação removida");
    } catch {
      toast.error("Erro ao remover marcação");
    }
  };

  // Download de anexo
  const downloadAttachment = async (emailId, attachment) => {
    try {
      if (attachment.url) {
        window.open(attachment.url, '_blank');
        return;
      }
      
      // O endpoint de streaming do Webmail (S3 → base de dados → IMAP) e não
      // o legado `/emails/{id}/attachments/{id}`, que devolvia JSON para os
      // anexos guardados no S3 — e o ficheiro descarregado era esse JSON.
      let blob;
      try {
        ({ data: blob } = await downloadWebmailAttachment(attachment.id, { email_id: emailId }));
      } catch (erro) {
        const corpo = await readBlobErrorBody(erro);
        throw new Error(corpo.detail || "Anexo não encontrado");
      }
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = attachment.filename;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (erro) {
      toast.error(erro?.message || "Erro ao descarregar anexo");
    }
  };

  // Preview de anexo

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
      toast.error(extractErrorMessage(error.response?.data?.detail, "Erro ao adicionar email"));
    } finally {
      setAddingEmail(false);
    }
  };

  const handleRemoveMonitoredEmail = async (email) => {
    try {
      await removeMonitoredEmail(processId, email);
      toast.success("Email removido da monitorização");
      fetchMonitoredEmails();
    } catch {
      toast.error("Erro ao remover email");
    }
  };

  // Desassociar: retira o email deste processo (fica no Webmail). Só tira a ligação, não apaga nada.
  const handleDisassociateEmail = async (emailId) => {
    try {
      await disassociateEmailFromProcess(emailId);
      toast.success("Email desassociado do processo");
      if (selectedEmailId === emailId) setIsViewerOpen(false);
      fetchData();
    } catch (error) {
      const detalhe = error?.response?.data?.detail;
      toast.error(typeof detalhe === "string" ? detalhe : "Erro ao desassociar o email");
    }
  };

  const fetchData = async () => {
    try {
      setLoading(true);
      setAcessoNegado(false);
      // Os emails são o essencial; as estatísticas são um extra (uma falha
      // delas não pode esvaziar a lista).
      const [emailsRes, statsRes] = await Promise.allSettled([
        getProcessEmails(processId, filter === "all" ? null : filter, { skipErrorToast: true }),
        getEmailStats(processId, { skipErrorToast: true }),
      ]);
      if (emailsRes.status === "rejected") throw emailsRes.reason;
      setEmails(Array.isArray(emailsRes.value.data) ? emailsRes.value.data : []);
      if (statsRes.status === "fulfilled" && statsRes.value.data && typeof statsRes.value.data === "object") {
        setStats(statsRes.value.data);
      }
    } catch (error) {
      // 403/404 do servidor (processo fora do âmbito ou sem visibilidade):
      // dizer-se, em vez de mostrar uma lista vazia que parece «sem emails».
      const estado = error?.response?.status;
      if (estado === 403 || estado === 404) setAcessoNegado(true);
      console.error("Erro ao carregar emails:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleSyncEmails = async () => {
    if (!clientEmail && monitoredEmails.length === 0) {
      toast.error("Adicione pelo menos um email para monitorizar");
      return;
    }

    try {
      setSyncing(true);
      toast.info("A iniciar sincronização...");
      
      const response = await syncProcessEmails(processId, 60);
      
      if (response.data.status === "started") {
        toast.success("Sincronização iniciada em background");
        const checkStatus = async () => {
          try {
            const { data: status } = await getProcessEmailSyncStatus(processId);
            
            if (status.status === "completed") {
              toast.success(`Sincronização concluída: ${status.result?.new_imported || 0} novos emails`);
              fetchData();
              setSyncing(false);
            } else if (status.status === "error") {
              toast.error(`Erro: ${status.error}`);
              setSyncing(false);
            } else if (status.status === "running") {
              setTimeout(checkStatus, 5000);
            } else {
              setSyncing(false);
            }
          } catch {
            setSyncing(false);
          }
        };
        setTimeout(checkStatus, 3000);
      } else {
        toast.success(`Sincronização concluída: ${response.data.new_imported} novos emails`);
        fetchData();
        setSyncing(false);
      }
    } catch {
      toast.error("Erro ao sincronizar emails");
      setSyncing(false);
    }
  };

  const handleDeleteEmail = async (emailId) => {
    if (!window.confirm("Tem a certeza que deseja eliminar este email?")) return;
    try {
      await deleteEmail(emailId);
      toast.success("Email eliminado");
      fetchData();
    } catch {
      toast.error("Erro ao eliminar email");
    }
  };

  const clearFilters = () => {
    setAdvancedFilters({
      account: "all",
      dateFrom: "",
      dateTo: "",
      hasAttachments: "all",
      isImportant: false,
      isUnread: false,
      isStarred: false
    });
    setLocalSearchTerm("");
  };

  const hasActiveFilters = () => {
    return advancedFilters.account !== "all" ||
           advancedFilters.dateFrom ||
           advancedFilters.dateTo ||
           advancedFilters.hasAttachments !== "all" ||
           advancedFilters.isImportant ||
           advancedFilters.isUnread ||
           advancedFilters.isStarred ||
           localSearchTerm;
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
                {stats.unread > 0 && (
                  <Badge variant="destructive" className="ml-1">{stats.unread} não lidos</Badge>
                )}
              </CardTitle>
              
              {/* Toggle Timeline */}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setTimelineMode(!timelineMode)}
                className={timelineMode ? "bg-amber-100 text-amber-700" : ""}
              >
                <Clock className="h-4 w-4" />
              </Button>
            </div>
            
            {/* Botões de acção - responsivo */}
            <div className="flex flex-wrap items-center gap-1 sm:gap-2">
              <Button 
                size="sm" 
                variant="outline"
                onClick={() => openWebmail('precision')}
                title="Abrir Webmail Precision"
                className="px-2 sm:px-3"
              >
                <Mail className="h-4 w-4 sm:mr-1" />
                <span className="text-xs hidden sm:inline">Precision</span>
                <ExternalLink className="h-3 w-3 ml-1 hidden sm:inline" />
              </Button>
              <Button 
                size="sm" 
                variant="outline"
                onClick={() => openWebmail('power')}
                title="Abrir Webmail Power"
                className="px-2 sm:px-3"
              >
                <Mail className="h-4 w-4 sm:mr-1" />
                <span className="text-xs hidden sm:inline">Power</span>
                <ExternalLink className="h-3 w-3 ml-1 hidden sm:inline" />
              </Button>
              
              <Button 
                size="sm" 
                variant="outline"
                onClick={() => setIsSettingsOpen(true)}
                title="Configurações de emails"
                className="bg-amber-50 hover:bg-amber-100 border-amber-200 px-2 sm:px-3"
              >
                <Settings className="h-4 w-4 sm:mr-1" />
                <span className="text-xs hidden sm:inline">Emails</span>
              </Button>
              
              <Button 
                size="sm" 
                variant="outline"
                onClick={handleSyncEmails}
                disabled={syncing || (!clientEmail && monitoredEmails.length === 0)}
                title="Sincronizar emails"
                className="px-2 sm:px-3"
              >
                {syncing ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="h-4 w-4" />
                )}
                <span className="text-xs ml-1 hidden sm:inline">Sync</span>
              </Button>
              
            </div>
            
            {!compact && (
              <CardDescription className="text-xs">
                {stats.sent} enviado(s) • {stats.received} recebido(s)
                {stats.important > 0 && ` • ${stats.important} importante(s)`}
                {stats.starred > 0 && ` • ${stats.starred} estrela(s)`}
              </CardDescription>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {/* Campo de Pesquisa e Filtros */}
          <div className="flex gap-2 mb-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Pesquisar emails..."
                value={localSearchTerm}
                onChange={(e) => setLocalSearchTerm(e.target.value)}
                className="pl-9 h-9 text-sm"
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
            
            {/* Filtros Avançados */}
            <Popover open={isFilterOpen} onOpenChange={setIsFilterOpen}>
              <PopoverTrigger asChild>
                <Button 
                  variant="outline" 
                  size="sm"
                  className={hasActiveFilters() ? "bg-amber-100 border-amber-300" : ""}
                >
                  <Filter className="h-4 w-4" />
                  {hasActiveFilters() && (
                    <Badge variant="secondary" className="ml-1 h-5 w-5 p-0 text-xs">
                      !
                    </Badge>
                  )}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-80" align="end">
                <div className="space-y-4">
                  <h4 className="font-medium text-sm">Filtros Avançados</h4>
                  
                  {/* Conta */}
                  <div className="space-y-2">
                    <Label className="text-xs">Conta</Label>
                    <Select 
                      value={advancedFilters.account}
                      onValueChange={(v) => setAdvancedFilters(prev => ({ ...prev, account: v }))}
                    >
                      <SelectTrigger className="h-8">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">Todas</SelectItem>
                        <SelectItem value="precision">Precision</SelectItem>
                        <SelectItem value="power">Power</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  
                  {/* Data */}
                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1">
                      <Label className="text-xs">De</Label>
                      <Input
                        type="date"
                        value={advancedFilters.dateFrom}
                        onChange={(e) => setAdvancedFilters(prev => ({ ...prev, dateFrom: e.target.value }))}
                        className="h-8"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs">Até</Label>
                      <Input
                        type="date"
                        value={advancedFilters.dateTo}
                        onChange={(e) => setAdvancedFilters(prev => ({ ...prev, dateTo: e.target.value }))}
                        className="h-8"
                      />
                    </div>
                  </div>
                  
                  {/* Anexos */}
                  <div className="space-y-2">
                    <Label className="text-xs">Anexos</Label>
                    <Select 
                      value={advancedFilters.hasAttachments}
                      onValueChange={(v) => setAdvancedFilters(prev => ({ ...prev, hasAttachments: v }))}
                    >
                      <SelectTrigger className="h-8">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">Todos</SelectItem>
                        <SelectItem value="yes">Com anexos</SelectItem>
                        <SelectItem value="no">Sem anexos</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  
                  {/* Marcações */}
                  <div className="space-y-2">
                    <Label className="text-xs">Marcações</Label>
                    <div className="flex flex-wrap gap-2">
                      <label className="flex items-center gap-1 text-xs">
                        <Checkbox
                          checked={advancedFilters.isImportant}
                          onCheckedChange={(v) => setAdvancedFilters(prev => ({ ...prev, isImportant: v }))}
                        />
                        Importante
                      </label>
                      <label className="flex items-center gap-1 text-xs">
                        <Checkbox
                          checked={advancedFilters.isUnread}
                          onCheckedChange={(v) => setAdvancedFilters(prev => ({ ...prev, isUnread: v }))}
                        />
                        Não lido
                      </label>
                      <label className="flex items-center gap-1 text-xs">
                        <Checkbox
                          checked={advancedFilters.isStarred}
                          onCheckedChange={(v) => setAdvancedFilters(prev => ({ ...prev, isStarred: v }))}
                        />
                        Estrela
                      </label>
                    </div>
                  </div>
                  
                  <div className="flex justify-between pt-2">
                    <Button variant="ghost" size="sm" onClick={clearFilters}>
                      Limpar filtros
                    </Button>
                    <Button size="sm" onClick={() => setIsFilterOpen(false)}>
                      Aplicar
                    </Button>
                  </div>
                </div>
              </PopoverContent>
            </Popover>
          </div>

          {/* Tabs de Filtros */}
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

          {/* Timeline Mode */}
          {timelineMode ? (
            <ScrollArea style={{ height: maxHeight }}>
              <div className="space-y-4">
                {emailTimeline.map((day) => (
                  <div key={day.date}>
                    <div className="flex items-center gap-2 mb-2 sticky top-0 bg-background py-1">
                      <Calendar className="h-4 w-4 text-muted-foreground" />
                      <span className="font-medium text-sm">
                        {safeFormat(day.date, "EEEE, dd 'de' MMMM", { locale: pt })}
                      </span>
                      <Badge variant="outline" className="text-xs">
                        {day.stats.sent} env • {day.stats.received} rec
                      </Badge>
                    </div>
                    <div className="space-y-1 pl-6 border-l-2 border-muted">
                      {day.emails.map((email) => (
                        <div
                          key={email.id}
                          className={`flex items-center gap-2 p-2 rounded border cursor-pointer hover:bg-muted/50 ${
                            email.direction === "sent" 
                              ? "bg-blue-50/30 border-blue-200/50" 
                              : "bg-emerald-50/30 border-emerald-200/50"
                          }`}
                          onClick={() => openEmailViewer(email.id)}
                        >
                          <div className={`p-1 rounded ${
                            email.direction === "sent" 
                              ? "bg-blue-100 text-blue-600" 
                              : "bg-emerald-100 text-emerald-600"
                          }`}>
                            {email.direction === "sent" ? <Send className="h-3 w-3" /> : <Inbox className="h-3 w-3" />}
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium truncate">{email.subject}</p>
                            <p className="text-xs text-muted-foreground">
                              {email.direction === "sent" ? "Para: " : "De: "}
                              {email.direction === "sent" ? email.to_emails?.[0] : email.from_email}
                            </p>
                          </div>
                          <div className="flex items-center gap-1">
                            {email.is_important && <AlertCircle className="h-3 w-3 text-amber-500" />}
                            {email.is_starred && <Star className="h-3 w-3 text-amber-500 fill-amber-500" />}
                            {!email.is_read && <div className="h-2 w-2 rounded-full bg-amber-500" />}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          ) : (
            /* Lista Normal */
            <ScrollArea style={{ height: maxHeight }}>
              {acessoNegado ? (
                <div role="alert" data-testid="emails-acesso-negado" className="text-center py-8 text-muted-foreground">
                  <p className="font-medium">Não tem permissão para ver os emails deste processo.</p>
                  <p className="text-xs mt-1">
                    Os processos de outra rede, ou ainda por indexar, só são visíveis a quem lhes está atribuído.
                  </p>
                </div>
              ) : filteredEmails.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  <Mail className="h-12 w-12 mx-auto mb-2 opacity-20" />
                  <p>Nenhum email encontrado</p>
                  {hasActiveFilters() && (
                    <Button variant="outline" className="mt-2" size="sm" onClick={clearFilters}>
                      Limpar filtros
                    </Button>
                  )}
                </div>
              ) : (
                <div className="space-y-1">
                  {filteredEmails.map((email) => (
                    <div
                      key={email.id}
                      className={`flex items-center gap-2 p-2 rounded-lg border cursor-pointer hover:bg-muted/50 transition-colors ${
                        email.direction === "sent" 
                          ? "bg-blue-50/30 dark:bg-blue-950/10 border-blue-200/50 dark:border-blue-800/50" 
                          : "bg-emerald-50/30 dark:bg-emerald-950/10 border-emerald-200/50 dark:border-emerald-800/50"
                      } ${!email.is_read ? "border-l-4 border-l-amber-500" : ""}`}
                      onClick={() => openEmailViewer(email.id)}
                    >
                      {/* Ícone de direção */}
                      <div className={`p-1.5 rounded shrink-0 ${
                        email.direction === "sent" 
                          ? "bg-blue-100 dark:bg-blue-900/50 text-blue-600 dark:text-blue-300" 
                          : "bg-emerald-100 dark:bg-emerald-900/50 text-emerald-600 dark:text-emerald-300"
                      }`}>
                        {email.direction === "sent" ? <Send className="h-3 w-3" /> : <Inbox className="h-3 w-3" />}
                      </div>

                      {/* Conteúdo */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className={`font-medium text-sm truncate ${!email.is_read ? "font-semibold" : ""}`}>
                            {email.subject}
                          </p>
                          {/* Marcações */}
                          <div className="flex items-center gap-1 shrink-0">
                            {email.is_important && <AlertCircle className="h-3 w-3 text-amber-500" />}
                            {email.is_starred && <Star className="h-3 w-3 text-amber-500 fill-amber-500" />}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <p className="text-xs text-muted-foreground truncate">
                            {email.direction === "sent" ? "Para: " : "De: "}
                            {email.direction === "sent" ? email.to_emails?.[0] : email.from_email}
                          </p>
                          {email.attachments?.length > 0 && (
                            <div className="flex items-center gap-1 text-xs text-muted-foreground">
                              <Paperclip className="h-3 w-3" />
                              {email.attachments.length}
                            </div>
                          )}
                        </div>
                        {/* CC */}
                        {email.cc_emails?.length > 0 && (
                          <p className="text-xs text-amber-600 dark:text-amber-400 font-medium flex items-center gap-1">
                            <span className="text-[10px] bg-amber-100 dark:bg-amber-900/50 px-1 rounded">CC</span>
                            <span className="truncate">{email.cc_emails.join(", ")}</span>
                          </p>
                        )}
                      </div>

                      {/* Data e ações */}
                      <div className="flex items-center gap-1 shrink-0">
                        <span className="text-[10px] text-muted-foreground whitespace-nowrap">
                          {email.sent_at ? safeFormat(email.sent_at, "dd/MM/yy") : "-"}
                        </span>
                        
                        {/* Dropdown de ações */}
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Acções do email" onClick={(e) => e.stopPropagation()}>
                              <MoreVertical className="h-3.5 w-3.5" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end" className="w-44">
                            <DropdownMenuItem onClick={(e) => { e.stopPropagation(); openEmailViewer(email.id); }}>
                              <Eye className="h-4 w-4 mr-2" /> Ver completo
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            {!email.is_read ? (
                              <DropdownMenuItem onClick={(e) => { e.stopPropagation(); markEmail(email.id, "read"); }}>
                                <CheckCircle className="h-4 w-4 mr-2" /> Marcar lido
                              </DropdownMenuItem>
                            ) : (
                              <DropdownMenuItem onClick={(e) => { e.stopPropagation(); markEmail(email.id, "unread"); }}>
                                <EyeOff className="h-4 w-4 mr-2" /> Marcar não lido
                              </DropdownMenuItem>
                            )}
                            {!email.is_important ? (
                              <DropdownMenuItem onClick={(e) => { e.stopPropagation(); markEmail(email.id, "important"); }}>
                                <AlertCircle className="h-4 w-4 mr-2 text-amber-500" /> Importante
                              </DropdownMenuItem>
                            ) : (
                              <DropdownMenuItem onClick={(e) => { e.stopPropagation(); unmarkEmail(email.id, "important"); }}>
                                <AlertCircle className="h-4 w-4 mr-2" /> Não importante
                              </DropdownMenuItem>
                            )}
                            {!email.is_starred ? (
                              <DropdownMenuItem onClick={(e) => { e.stopPropagation(); markEmail(email.id, "starred"); }}>
                                <Star className="h-4 w-4 mr-2 text-amber-500" /> Estrela
                              </DropdownMenuItem>
                            ) : (
                              <DropdownMenuItem onClick={(e) => { e.stopPropagation(); unmarkEmail(email.id, "starred"); }}>
                                <StarOff className="h-4 w-4 mr-2" /> Tirar estrela
                              </DropdownMenuItem>
                            )}
                            <DropdownMenuSeparator />
                            <DropdownMenuItem onClick={(e) => { e.stopPropagation(); handleDisassociateEmail(email.id); }}>
                              <Unlink className="h-4 w-4 mr-2" /> Desassociar
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={(e) => { e.stopPropagation(); handleDeleteEmail(email.id); }} className="text-red-600">
                              <Trash2 className="h-4 w-4 mr-2" /> Eliminar
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </ScrollArea>
          )}
        </CardContent>
      </Card>

      {/* Modal de visualização */}
      <EmailViewerModal
        isOpen={isViewerOpen}
        onClose={() => setIsViewerOpen(false)}
        emails={filteredEmails}
        selectedEmailId={selectedEmailId}
        onSelectEmail={setSelectedEmailId}
        onMarkEmail={markEmail}
        onUnmarkEmail={unmarkEmail}
        token={token}
        clientName={clientName}
        processId={processId}
      />

      {/* Modal de Configurações */}
      <Dialog open={isSettingsOpen} onOpenChange={setIsSettingsOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AtSign className="h-5 w-5" />
              Emails Monitorizados
            </DialogTitle>
            <DialogDescription>
              Configure os emails que serão sincronizados para este processo.
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4 py-4">
            <div>
              <Label className="text-sm font-medium">Email Principal do Cliente</Label>
              <div className="flex items-center gap-2 mt-1 p-2 bg-muted rounded-md">
                <Mail className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm">{clientEmail || "Não definido"}</span>
                <Badge variant="outline" className="ml-auto text-xs">Principal</Badge>
              </div>
            </div>

            <div>
              <Label className="text-sm font-medium">Emails Adicionais</Label>
              <p className="text-xs text-muted-foreground mb-2">
                Adicione outros emails relacionados (bancos, intermediários, etc.)
              </p>
              
              {monitoredEmails.length > 0 ? (
                <div className="space-y-2 mb-3">
                  {monitoredEmails.map((email) => (
                    <div key={email} className="flex items-center gap-2 p-2 bg-muted/50 rounded-md">
                      <AtSign className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm flex-1">{email}</span>
                      <Button variant="ghost" size="sm" className="h-6 w-6 p-0 text-destructive" onClick={() => handleRemoveMonitoredEmail(email)}>
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

              <div className="flex gap-2">
                <Input
                  placeholder="email@exemplo.pt"
                  value={newMonitoredEmail}
                  onChange={(e) => setNewMonitoredEmail(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleAddMonitoredEmail()}
                />
                <Button onClick={handleAddMonitoredEmail} disabled={addingEmail} size="sm">
                  {addingEmail ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                </Button>
              </div>
            </div>

            <div className="pt-2 border-t">
              <Label className="text-sm font-medium">Contas da Empresa</Label>
              <div className="space-y-1 mt-2">
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
            <Button onClick={() => { setIsSettingsOpen(false); handleSyncEmails(); }} className="bg-teal-600 hover:bg-teal-700">
              <RefreshCw className="h-4 w-4 mr-2" />
              Sincronizar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Preview de Anexo */}
      {attachmentPreview && (
        <Dialog open={!!attachmentPreview} onOpenChange={() => setAttachmentPreview(null)}>
          <DialogContent className="sm:max-w-[800px]">
            <DialogHeader>
              <DialogTitle>{attachmentPreview.filename}</DialogTitle>
            </DialogHeader>
            <div className="flex items-center justify-center min-h-[400px] bg-muted/50 rounded-lg">
              {attachmentPreview.previewUrl ? (
                <img 
                  src={attachmentPreview.previewUrl} 
                  alt={attachmentPreview.filename}
                  className="max-w-full max-h-[500px] object-contain"
                />
              ) : (
                <div className="text-center">
                  <FileText className="h-16 w-16 mx-auto mb-2 text-muted-foreground" />
                  <p>Preview não disponível</p>
                  <Button 
                    className="mt-4"
                    onClick={() => downloadAttachment(selectedEmailId, attachmentPreview)}
                  >
                    <Download className="h-4 w-4 mr-2" />
                    Download
                  </Button>
                </div>
              )}
            </div>
          </DialogContent>
        </Dialog>
      )}
    </>
  );
};

export default EmailHistoryPanel;
