/**
 * WebmailPage - Webmail de três painéis (estilo Outlook)
 * 
 * Permite gerir emails (recebidos, enviados, rascunhos, destacados, lixo)
 * com visualização em painel de leitura, composição de emails e
 * associação a processos.
 */
import { useState, useCallback, useEffect, useMemo, useRef } from "react";
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Textarea } from "../components/ui/textarea";
import { Badge } from "../components/ui/badge";
import { ScrollArea } from "../components/ui/scroll-area";
import { Separator } from "../components/ui/separator";
import { Skeleton } from "../components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../components/ui/tooltip";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "../components/ui/collapsible";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "../components/ui/dialog";
import {
  Inbox,
  Send,
  Star,
  FileText,
  Archive,
  Plus,
  Search,
  RefreshCw,
  Mail,
  MailOpen,
  Paperclip,
  Reply,
  Forward,
  Link2,
  ChevronDown,
  ChevronRight,
  X,
  Loader2,
  ArrowLeft,
  AtSign,
} from "lucide-react";
import { toast } from "sonner";
import { format, parseISO, isToday, isYesterday } from "date-fns";
import { pt } from "date-fns/locale";
import { useNavigate } from "react-router-dom";
import { sanitizeEmailHtml } from "../utils/sanitize";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Configuração das pastas
const FOLDERS = [
  { id: "inbox", label: "Caixa de Entrada", icon: Inbox },
  { id: "sent", label: "Enviados", icon: Send },
  { id: "starred", label: "Destacados", icon: Star },
  { id: "drafts", label: "Rascunhos", icon: FileText },
  { id: "trash", label: "Lixo", icon: Archive },
];

// Formatar data relativa ou absoluta
const formatEmailDate = (dateStr) => {
  if (!dateStr) return "";
  try {
    const date = parseISO(dateStr);
    if (isToday(date)) {
      return format(date, "HH:mm", { locale: pt });
    }
    if (isYesterday(date)) {
      return "ontem";
    }
    return format(date, "dd/MM/yyyy", { locale: pt });
  } catch {
    return dateStr;
  }
};

// Formatar data completa
const formatFullDate = (dateStr) => {
  if (!dateStr) return "-";
  try {
    return format(parseISO(dateStr), "dd 'de' MMMM 'de' yyyy 'às' HH:mm", { locale: pt });
  } catch {
    return dateStr;
  }
};

const WebmailPage = () => {
  const { token, user } = useAuth();
  const navigate = useNavigate();

  // Estado principal
  const [activeFolder, setActiveFolder] = useState("inbox");
  const [emails, setEmails] = useState([]);
  const [totalEmails, setTotalEmails] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [unreadCount, setUnreadCount] = useState(0);
  const [selectedEmail, setSelectedEmail] = useState(null);
  const [emailDetail, setEmailDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [account, setAccount] = useState("precision");

  // Composer state
  const [composerOpen, setComposerOpen] = useState(false);
  const [composerData, setComposerData] = useState({
    to_emails: "",
    cc_emails: "",
    subject: "",
    body: "",
    account: "precision",
    process_id: null,
  });
  const [composerSending, setComposerSending] = useState(false);
  const [ccExpanded, setCcExpanded] = useState(false);

  // Link to process dialog
  const [linkDialogOpen, setLinkDialogOpen] = useState(false);
  const [linkSearchQuery, setLinkSearchQuery] = useState("");
  const [linkSearchResults, setLinkSearchResults] = useState([]);
  const [linkSearchLoading, setLinkSearchLoading] = useState(false);
  const [linkSaving, setLinkSaving] = useState(false);

  // Mobile reading pane
  const [showMobileReading, setShowMobileReading] = useState(false);

  // Sync state
  const [syncing, setSyncing] = useState(false);
  const [lastSyncTime, setLastSyncTime] = useState(null);

  // Debounce search
  const searchTimeoutRef = useRef(null);

  // ============================================================
  // FETCH EMAILS
  // ============================================================
  const fetchEmails = useCallback(async (folder, page, search) => {
    if (!token) return;
    setLoading(true);
    try {
      const params = new URLSearchParams({
        folder: folder || activeFolder,
        page: String(page || 1),
        limit: "30",
      });
      if (search && search.trim()) {
        params.append("search", search.trim());
      }

      const response = await fetch(
        `${API_URL}/api/emails/webmail?${params.toString()}`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (!response.ok) throw new Error("Erro ao carregar emails");
      const data = await response.json();

      setEmails(data.emails || []);
      setTotalEmails(data.total || 0);
      setCurrentPage(data.page || 1);
      setTotalPages(data.pages || 1);
      setUnreadCount(data.unread_count || 0);
    } catch (error) {
      console.error("Erro ao carregar emails:", error);
      toast.error("Erro ao carregar emails");
    } finally {
      setLoading(false);
    }
  }, [token, activeFolder]);

  // Carregar emails quando muda pasta ou página
  useEffect(() => {
    fetchEmails(activeFolder, currentPage, "");
    setSelectedEmail(null);
    setEmailDetail(null);
    setShowMobileReading(false);
  }, [activeFolder, currentPage, fetchEmails]);

  // Debounced search
  const handleSearchChange = useCallback((value) => {
    setSearchQuery(value);
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }
    searchTimeoutRef.current = setTimeout(() => {
      setCurrentPage(1);
      fetchEmails(activeFolder, 1, value);
    }, 400);
  }, [activeFolder, fetchEmails]);

  // Refresh
  const handleRefresh = useCallback(() => {
    fetchEmails(activeFolder, currentPage, searchQuery);
  }, [activeFolder, currentPage, searchQuery, fetchEmails]);

  // ============================================================
  // SYNC EMAILS (IMAP → DB)
  // ============================================================
  const handleSyncEmails = useCallback(async () => {
    if (!token || syncing) return;
    setSyncing(true);
    try {
      const params = new URLSearchParams({
        days: "7",
      });
      // Não enviar account param vazio — sync todas as contas por defeito
      if (account) {
        params.append("account", account);
      }
      const response = await fetch(
        `${API_URL}/api/emails/webmail/sync?${params.toString()}`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      const data = await response.json().catch(() => ({}));

      // Erro HTTP (500, etc)
      if (!response.ok) {
        toast.error(data.detail || "Erro na sincronização");
        return;
      }

      // Erro de negócio (success: false mas 200 OK)
      if (data.success === false) {
        toast.error(data.error || "Erro na sincronização");
        return;
      }

      const synced = data.total_synced || 0;
      const dups = data.total_duplicates || 0;
      const errs = data.total_errors || 0;
      if (synced > 0) {
        toast.success(`${synced} novo${synced !== 1 ? "s" : ""} email${synced !== 1 ? "s" : ""} sincronizado${synced !== 1 ? "s" : ""}${dups > 0 ? ` (${dups} duplicado${dups !== 1 ? "s" : ""})` : ""}${errs > 0 ? ` | ${errs} erro${errs !== 1 ? "s" : ""}` : ""}`);
      } else if (dups > 0) {
        toast.info(`${dups} email${dups !== 1 ? "s" : ""} já sincronizado${dups !== 1 ? "s" : ""}. Tudo em dia!`);
      } else if (errs > 0) {
        toast.error(`${errs} erro${errs !== 1 ? "s" : ""} na sincronização. Verifique as configurações de email.`);
      } else {
        toast.info("Nenhum email novo para sincronizar");
      }
      setLastSyncTime(new Date());
      // Refresh the list
      fetchEmails(activeFolder, currentPage, searchQuery);
    } catch (error) {
      console.error("Erro ao sincronizar emails:", error);
      toast.error("Erro de ligação ao servidor");
    } finally {
      setSyncing(false);
    }
  }, [token, account, syncing, activeFolder, currentPage, searchQuery, fetchEmails]);

  // ============================================================
  // SELECT EMAIL & MARK AS READ
  // ============================================================
  const handleSelectEmail = useCallback(async (email) => {
    setSelectedEmail(email);
    setShowMobileReading(true);

    // Carregar detalhe completo
    setDetailLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/emails/${email.id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error("Erro ao carregar email");
      const data = await response.json();
      setEmailDetail(data);

      // Marcar como lido se necessário
      if (!email.is_read) {
        try {
          await fetch(`${API_URL}/api/emails/${email.id}/mark`, {
            method: "POST",
            headers: {
              Authorization: `Bearer ${token}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ type: "read" }),
          });
          // Atualizar lista local
          setEmails((prev) =>
            prev.map((e) => (e.id === email.id ? { ...e, is_read: true } : e))
          );
          setUnreadCount((prev) => Math.max(0, prev - 1));
        } catch {
          // Falha silenciosa - não é crítica
        }
      }
    } catch (error) {
      console.error("Erro ao carregar detalhe:", error);
      toast.error("Erro ao carregar email");
    } finally {
      setDetailLoading(false);
    }
  }, [token]);

  // ============================================================
  // TOGGLE STAR
  // ============================================================
  const handleToggleStar = useCallback(async (email, e) => {
    e?.stopPropagation();
    try {
      const newStarred = !email.is_starred;
      await fetch(`${API_URL}/api/emails/${email.id}/mark`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ type: "starred" }),
      });

      // Atualizar lista local
      setEmails((prev) =>
        prev.map((em) =>
          em.id === email.id ? { ...em, is_starred: newStarred } : em
        )
      );
      if (emailDetail?.id === email.id) {
        setEmailDetail((prev) => prev ? { ...prev, is_starred: newStarred } : prev);
      }
      toast.success(newStarred ? "Email destacado" : "Destaque removido");
    } catch {
      toast.error("Erro ao alterar destaque");
    }
  }, [token, emailDetail]);

  // ============================================================
  // COMPOSER
  // ============================================================
  const openComposer = useCallback((mode, email = null) => {
    if (mode === "reply" && email) {
      const senderEmail = email.direction === "sent"
        ? email.to_emails?.[0] || ""
        : email.from_email || "";
      setComposerData({
        to_emails: senderEmail,
        cc_emails: "",
        subject: email.subject ? `Re: ${email.subject}` : "",
        body: `\n\n---------- Mensagem original ----------\nDe: ${email.from_email}\nData: ${formatFullDate(email.sent_at)}\nAssunto: ${email.subject || ""}\n\n${email.body || ""}`,
        account: email.account || "precision",
        process_id: email.process_id || null,
      });
    } else if (mode === "forward" && email) {
      setComposerData({
        to_emails: "",
        cc_emails: "",
        subject: email.subject ? `Fwd: ${email.subject}` : "",
        body: `\n\n---------- Mensagem encaminhada ----------\nDe: ${email.from_email}\nData: ${formatFullDate(email.sent_at)}\nAssunto: ${email.subject || ""}\n\n${email.body || ""}`,
        account: email.account || "precision",
        process_id: null,
      });
    } else {
      setComposerData({
        to_emails: "",
        cc_emails: "",
        subject: "",
        body: "",
        account: account,
        process_id: null,
      });
    }
    setCcExpanded(mode === "forward" || false);
    setComposerOpen(true);
  }, [account]);

  const handleSendEmail = useCallback(async () => {
    if (!composerData.to_emails.trim()) {
      toast.error("Introduza pelo menos um destinatário");
      return;
    }
    if (!composerData.subject.trim()) {
      toast.error("Introduza o assunto do email");
      return;
    }

    setComposerSending(true);
    try {
      const toList = composerData.to_emails
        .split(/[;,]/)
        .map((e) => e.trim())
        .filter(Boolean);
      const ccList = composerData.cc_emails
        .split(/[;,]/)
        .map((e) => e.trim())
        .filter(Boolean);

      const response = await fetch(
        `${API_URL}/api/emails/send?account=${composerData.account}`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            to_emails: toList,
            subject: composerData.subject,
            body: composerData.body,
            body_html: "",
            cc_emails: ccList,
            process_id: composerData.process_id,
          }),
        }
      );

      if (!response.ok) throw new Error("Erro ao enviar email");
      toast.success("Email enviado com sucesso");
      setComposerOpen(false);
      handleRefresh();
    } catch (error) {
      console.error("Erro ao enviar:", error);
      toast.error("Erro ao enviar email");
    } finally {
      setComposerSending(false);
    }
  }, [composerData, token, handleRefresh]);

  // ============================================================
  // LINK TO PROCESS
  // ============================================================
  const handleOpenLinkDialog = useCallback(() => {
    if (!selectedEmail) return;
    setLinkSearchQuery("");
    setLinkSearchResults([]);
    setLinkDialogOpen(true);
  }, [selectedEmail]);

  const handleSearchClients = useCallback(
    async (query) => {
      setLinkSearchQuery(query);
      if (!query.trim() || query.trim().length < 2) {
        setLinkSearchResults([]);
        return;
      }
      setLinkSearchLoading(true);
      try {
        const response = await fetch(
          `${API_URL}/api/clients/search?q=${encodeURIComponent(query.trim())}`,
          {
            headers: { Authorization: `Bearer ${token}` },
          }
        );
        if (!response.ok) throw new Error("Erro na pesquisa");
        const data = await response.json();
        setLinkSearchResults(data.clients || []);
      } catch {
        toast.error("Erro ao pesquisar clientes");
      } finally {
        setLinkSearchLoading(false);
      }
    },
    [token]
  );

  const handleLinkProcess = useCallback(
    async (processId) => {
      if (!selectedEmail || !processId) return;
      setLinkSaving(true);
      try {
        const response = await fetch(`${API_URL}/api/emails/associate`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            email_id: selectedEmail.id,
            process_id: processId,
          }),
        });
        if (!response.ok) throw new Error("Erro ao associar");
        toast.success("Email associado ao processo com sucesso");
        setLinkDialogOpen(false);
        // Atualizar email detalhe e lista
        setEmailDetail((prev) =>
          prev ? { ...prev, process_id: processId } : prev
        );
        setEmails((prev) =>
          prev.map((e) =>
            e.id === selectedEmail.id ? { ...e, process_id: processId } : e
          )
        );
      } catch {
        toast.error("Erro ao associar email ao processo");
      } finally {
        setLinkSaving(false);
      }
    },
    [token, selectedEmail]
  );

  // ============================================================
  // FOLDER COUNTS (derived from email list data)
  // ============================================================
  const folderCounts = useMemo(() => {
    const counts = { inbox: 0, sent: 0, starred: 0, drafts: 0, trash: 0 };
    // unreadCount vem da API para inbox
    counts.inbox = unreadCount;
    // Contar starred localmente (approx)
    return counts;
  }, [unreadCount]);

  // Sanitized HTML body
  const sanitizedBodyHtml = useMemo(() => {
    if (emailDetail?.body_html) {
      return sanitizeEmailHtml(emailDetail.body_html);
    }
    return "";
  }, [emailDetail?.body_html]);

  // ============================================================
  // RENDER
  // ============================================================
  return (
    <DashboardLayout title="Email">
      <TooltipProvider delayDuration={300}>
        <div className="flex flex-col h-[calc(100vh-64px)] -mx-6 -mt-6">
        {/* ===== TOP BAR ===== */}
        <div className="flex items-center gap-3 px-4 py-2.5 border-b bg-background shrink-0">
          {/* Mobile back button */}
          {showMobileReading && (
            <Button
              variant="ghost"
              size="icon"
              className="md:hidden shrink-0"
              onClick={() => setShowMobileReading(false)}
            >
              <ArrowLeft className="h-4 w-4" />
            </Button>
          )}

          {/* Search */}
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Pesquisar emails..."
              value={searchQuery}
              onChange={(e) => handleSearchChange(e.target.value)}
              className="pl-9 h-8"
            />
          </div>

          {/* Account selector */}
          <Select value={account} onValueChange={setAccount}>
            <SelectTrigger className="w-[160px] h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="precision">Precision Crédito</SelectItem>
              <SelectItem value="power">Power Real Estate</SelectItem>
            </SelectContent>
          </Select>

          {/* Refresh */}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={handleRefresh}
                disabled={loading}
              >
                <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Atualizar</TooltipContent>
          </Tooltip>
        </div>

        {/* ===== THREE PANE LAYOUT ===== */}
        <div className="flex flex-1 overflow-hidden">
          {/* ========== COLUMN 1: SIDEBAR ========== */}
          <div className={`
            w-56 flex-shrink-0 border-r bg-muted/30 flex flex-col
            ${showMobileReading ? "hidden md:flex" : "flex"}
          `}>
            {/* Nova Mensagem */}
            <div className="p-3 space-y-2">
              <Button
                className="w-full gap-2"
                onClick={() => openComposer("new")}
              >
                <Plus className="h-4 w-4" />
                Nova Mensagem
              </Button>
              <Button
                variant="outline"
                className="w-full gap-2"
                onClick={handleSyncEmails}
                disabled={syncing}
              >
                <RefreshCw className={`h-4 w-4 ${syncing ? "animate-spin" : ""}`} />
                {syncing ? "A sincronizar..." : "Sincronizar"}
              </Button>
            </div>

            <Separator />

            {/* Folders */}
            <nav className="flex-1 p-2 space-y-0.5">
              {FOLDERS.map((folder) => {
                const Icon = folder.icon;
                const isActive = activeFolder === folder.id;
                return (
                  <button
                    key={folder.id}
                    onClick={() => {
                      setActiveFolder(folder.id);
                      setCurrentPage(1);
                    }}
                    className={`
                      w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm
                      transition-colors text-left
                      ${
                        isActive
                          ? "bg-accent text-accent-foreground font-medium"
                          : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
                      }
                    `}
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    <span className="flex-1 truncate">{folder.label}</span>
                    {folder.id === "inbox" && unreadCount > 0 && (
                      <Badge
                        variant="secondary"
                        className="h-5 min-w-[20px] flex items-center justify-center text-[10px] px-1.5"
                      >
                        {unreadCount}
                      </Badge>
                    )}
                  </button>
                );
              })}
            </nav>

            {/* Footer info */}
            <div className="p-3 border-t space-y-1">
              <p className="text-[10px] text-muted-foreground">
                {totalEmails} email{totalEmails !== 1 ? "s" : ""}
              </p>
              {lastSyncTime && (
                <p className="text-[10px] text-muted-foreground">
                  Última sinc: {format(lastSyncTime, "HH:mm:ss")}
                </p>
              )}
            </div>
          </div>

          {/* ========== COLUMN 2: EMAIL LIST ========== */}
          <div className={`
            w-80 flex-shrink-0 border-r flex flex-col bg-background
            ${showMobileReading ? "hidden md:flex" : "flex"}
          `}>
            {/* List header */}
            <div className="flex items-center justify-between px-3 py-2 border-b shrink-0">
              <h2 className="text-sm font-semibold">
                {FOLDERS.find((f) => f.id === activeFolder)?.label}
              </h2>
              {totalPages > 1 && (
                <span className="text-xs text-muted-foreground">
                  Página {currentPage} de {totalPages}
                </span>
              )}
            </div>

            {/* Email list */}
            <div className="flex-1 overflow-y-auto">
              {loading ? (
                // Skeleton loading
                <div className="divide-y">
                  {Array.from({ length: 8 }).map((_, i) => (
                    <div key={i} className="p-3 space-y-2">
                      <div className="flex items-center gap-2">
                        <Skeleton className="h-3 w-3 rounded-full" />
                        <Skeleton className="h-4 w-[140px]" />
                        <Skeleton className="h-3 w-[40px] ml-auto" />
                      </div>
                      <Skeleton className="h-3.5 w-full" />
                      <Skeleton className="h-3 w-[70%]" />
                    </div>
                  ))}
                </div>
              ) : emails.length === 0 ? (
                // Empty state
                <div className="flex flex-col items-center justify-center h-full text-center p-6">
                  <MailOpen className="h-10 w-10 text-muted-foreground opacity-40 mb-3" />
                  <p className="text-sm text-muted-foreground">
                    {searchQuery
                      ? "Nenhum email encontrado"
                      : "Sem emails nesta pasta"}
                  </p>
                </div>
              ) : (
                // Email items
                <div className="divide-y">
                  {emails.map((email) => {
                    const isSelected = selectedEmail?.id === email.id;
                    return (
                      <button
                        key={email.id}
                        onClick={() => handleSelectEmail(email)}
                        className={`
                          w-full text-left p-3 transition-colors hover:bg-accent/50
                          ${isSelected ? "bg-accent" : ""}
                        `}
                      >
                        <div className="flex items-start gap-2">
                          {/* Unread dot */}
                          {!email.is_read && (
                            <span className="bg-blue-500 w-2 h-2 rounded-full mt-1.5 shrink-0" />
                          )}
                          {email.is_read && <span className="w-2 shrink-0" />}

                          {/* Content */}
                          <div className="flex-1 min-w-0">
                            {/* Top row: sender + date + indicators */}
                            <div className="flex items-center gap-1.5">
                              <span
                                className={`text-sm truncate flex-1 ${
                                  !email.is_read
                                    ? "font-semibold text-foreground"
                                    : "text-muted-foreground"
                                }`}
                              >
                                {email.direction === "sent"
                                  ? email.to_emails?.[0] || "Destinatário"
                                  : email.client_name || email.from_email || "Remetente"}
                              </span>
                              <span className="text-[11px] text-muted-foreground whitespace-nowrap shrink-0">
                                {formatEmailDate(email.sent_at)}
                              </span>
                            </div>

                            {/* Subject */}
                            <p
                              className={`text-sm truncate mt-0.5 ${
                                !email.is_read ? "font-medium" : ""
                              }`}
                            >
                              {email.subject || "(Sem assunto)"}
                            </p>

                            {/* Preview + indicators */}
                            <div className="flex items-center gap-1.5 mt-0.5">
                              <p className="text-xs text-muted-foreground truncate flex-1">
                                {email.preview || ""}
                              </p>
                              {/* Star */}
                              {email.is_starred && (
                                <Star className="h-3 w-3 text-amber-500 fill-amber-500 shrink-0" />
                              )}
                              {/* Attachment */}
                              {email.attachments?.length > 0 && (
                                <Paperclip className="h-3 w-3 text-muted-foreground shrink-0" />
                              )}
                              {/* Process badge */}
                              {email.process_id && (
                                <Badge
                                  variant="outline"
                                  className="h-4 text-[9px] px-1 py-0 shrink-0"
                                >
                                  Proc.
                                </Badge>
                              )}
                            </div>
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between px-3 py-2 border-t shrink-0">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 px-2 text-xs"
                  disabled={currentPage <= 1}
                  onClick={() => setCurrentPage((p) => p - 1)}
                >
                  Anterior
                </Button>
                <span className="text-xs text-muted-foreground">
                  {currentPage} / {totalPages}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 px-2 text-xs"
                  disabled={currentPage >= totalPages}
                  onClick={() => setCurrentPage((p) => p + 1)}
                >
                  Seguinte
                </Button>
              </div>
            )}
          </div>

          {/* ========== COLUMN 3: READING PANE ========== */}
          <div
            className={`
              flex-1 flex flex-col bg-background overflow-hidden
              ${!showMobileReading ? "hidden md:flex" : "flex"}
            `}
          >
            {detailLoading ? (
              // Loading skeleton
              <div className="flex-1 p-5 space-y-4">
                <Skeleton className="h-7 w-[70%]" />
                <div className="space-y-2">
                  <Skeleton className="h-4 w-[200px]" />
                  <Skeleton className="h-4 w-[250px]" />
                  <Skeleton className="h-4 w-[150px]" />
                </div>
                <Separator />
                <div className="space-y-3">
                  {Array.from({ length: 6 }).map((_, i) => (
                    <Skeleton key={i} className="h-4 w-full" />
                  ))}
                  <Skeleton className="h-4 w-[80%]" />
                  <Skeleton className="h-4 w-[60%]" />
                </div>
              </div>
            ) : selectedEmail && emailDetail ? (
              /* ===== EMAIL DETAIL ===== */
              <div className="flex-1 flex flex-col overflow-hidden">
                {/* Header */}
                <div className="px-5 py-4 border-b shrink-0">
                  {/* Subject */}
                  <h2 className="text-lg font-semibold leading-snug break-words">
                    {emailDetail.subject || "(Sem assunto)"}
                  </h2>

                  {/* Meta info */}
                  <div className="mt-2 space-y-1.5 text-sm">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-muted-foreground shrink-0">De:</span>
                      <span className="font-medium truncate">
                        {emailDetail.from_email || "-"}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-muted-foreground shrink-0">Para:</span>
                      <span className="truncate">
                        {emailDetail.to_emails?.join(", ") || "-"}
                      </span>
                    </div>
                    {emailDetail.cc_emails?.length > 0 && (
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="text-muted-foreground shrink-0">CC:</span>
                        <span className="truncate">
                          {emailDetail.cc_emails.join(", ")}
                        </span>
                      </div>
                    )}
                    <div className="flex items-center gap-2 text-muted-foreground">
                      <span>Data:</span>
                      <span>{formatFullDate(emailDetail.sent_at)}</span>
                    </div>
                  </div>

                  {/* Action buttons */}
                  <div className="flex items-center gap-1.5 mt-3 flex-wrap">
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-8 text-xs gap-1.5"
                      onClick={() => openComposer("reply", emailDetail)}
                    >
                      <Reply className="h-3.5 w-3.5" />
                      Responder
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-8 text-xs gap-1.5"
                      onClick={() => openComposer("forward", emailDetail)}
                    >
                      <Forward className="h-3.5 w-3.5" />
                      Encaminhar
                    </Button>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="outline"
                          size="sm"
                          className={`h-8 w-8 p-0 ${
                            emailDetail.is_starred
                              ? "text-amber-500"
                              : "text-muted-foreground"
                          }`}
                          onClick={(e) => handleToggleStar(emailDetail, e)}
                        >
                          <Star
                            className={`h-3.5 w-3.5 ${
                              emailDetail.is_starred ? "fill-amber-500" : ""
                            }`}
                          />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>
                        {emailDetail.is_starred ? "Remover destaque" : "Destacar"}
                      </TooltipContent>
                    </Tooltip>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-8 text-xs gap-1.5"
                          onClick={handleOpenLinkDialog}
                          disabled={!!emailDetail.process_id}
                        >
                          <Link2 className="h-3.5 w-3.5" />
                          {emailDetail.process_id ? "Associado" : "Associar"}
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>
                        {emailDetail.process_id
                          ? "Já associado a um processo"
                          : "Associar a processo"}
                      </TooltipContent>
                    </Tooltip>
                    {emailDetail.process_id && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-8 text-xs gap-1.5"
                        onClick={() => navigate(`/processo/${emailDetail.process_id}`)}
                      >
                        <FileText className="h-3.5 w-3.5" />
                        Ver Processo
                      </Button>
                    )}
                  </div>
                </div>

                {/* Body */}
                <ScrollArea className="flex-1">
                  <div className="p-5">
                    <div className="prose prose-sm max-w-none dark:prose-invert email-content">
                      {sanitizedBodyHtml ? (
                        <div
                          dangerouslySetInnerHTML={{ __html: sanitizedBodyHtml }}
                        />
                      ) : (
                        <pre className="whitespace-pre-wrap font-sans text-sm">
                          {emailDetail.body || ""}
                        </pre>
                      )}
                    </div>

                    {/* Attachments */}
                    {emailDetail.attachments?.length > 0 && (
                      <div className="mt-6 pt-4 border-t">
                        <h4 className="font-medium text-sm flex items-center gap-2 mb-3">
                          <Paperclip className="h-4 w-4" />
                          Anexos ({emailDetail.attachments.length})
                        </h4>
                        <div className="space-y-1.5">
                          {emailDetail.attachments.map((attachment, idx) => (
                            <div
                              key={attachment.id || idx}
                              className="flex items-center gap-2 p-2 rounded-md border bg-muted/30 text-sm"
                            >
                              <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                              <span className="flex-1 truncate">
                                {attachment.filename || `Anexo ${idx + 1}`}
                              </span>
                              {attachment.size && (
                                <span className="text-xs text-muted-foreground">
                                  {(attachment.size / 1024).toFixed(0)} KB
                                </span>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </ScrollArea>
              </div>
            ) : (
              /* ===== EMPTY STATE ===== */
              <div className="flex-1 flex flex-col items-center justify-center text-center p-6">
                <Mail className="h-14 w-14 text-muted-foreground opacity-30 mb-4" />
                <p className="text-muted-foreground text-sm">
                  Selecione um email para visualizar
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  Clique num email da lista à esquerda
                </p>
              </div>
            )}
          </div>
        </div>

        {/* ===== EMAIL COMPOSER DIALOG ===== */}
        <Dialog open={composerOpen} onOpenChange={setComposerOpen}>
          <DialogContent className="max-w-2xl max-h-[90vh] flex flex-col gap-0 p-0 overflow-hidden">
            <DialogHeader className="px-6 pt-5 pb-3">
              <DialogTitle>
                Nova Mensagem
              </DialogTitle>
              <DialogDescription>
                Componha e envie um email
              </DialogDescription>
            </DialogHeader>

            <div className="flex-1 overflow-y-auto px-6 space-y-3 pb-4">
              {/* To */}
              <div className="flex items-center gap-2">
                <label className="text-sm font-medium w-12 shrink-0">Para:</label>
                <Input
                  placeholder="email@exemplo.com"
                  value={composerData.to_emails}
                  onChange={(e) =>
                    setComposerData((d) => ({ ...d, to_emails: e.target.value }))
                  }
                  className="flex-1"
                />
              </div>

              {/* CC (collapsible) */}
              <Collapsible open={ccExpanded} onOpenChange={setCcExpanded}>
                <CollapsibleTrigger asChild>
                  <button className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors">
                    {ccExpanded ? (
                      <ChevronDown className="h-3 w-3" />
                    ) : (
                      <ChevronRight className="h-3 w-3" />
                    )}
                    {ccExpanded ? "Ocultar CC" : "Mostrar CC"}
                  </button>
                </CollapsibleTrigger>
                <CollapsibleContent className="mt-2">
                  <div className="flex items-center gap-2">
                    <label className="text-sm font-medium w-12 shrink-0">CC:</label>
                    <Input
                      placeholder="email@exemplo.com (separar por vírgulas)"
                      value={composerData.cc_emails}
                      onChange={(e) =>
                        setComposerData((d) => ({ ...d, cc_emails: e.target.value }))
                      }
                      className="flex-1"
                    />
                  </div>
                </CollapsibleContent>
              </Collapsible>

              {/* Subject */}
              <div className="flex items-center gap-2">
                <label className="text-sm font-medium w-12 shrink-0">
                  Assunto:
                </label>
                <Input
                  placeholder="Assunto do email"
                  value={composerData.subject}
                  onChange={(e) =>
                    setComposerData((d) => ({ ...d, subject: e.target.value }))
                  }
                  className="flex-1"
                />
              </div>

              {/* Account */}
              <div className="flex items-center gap-2">
                <label className="text-sm font-medium w-12 shrink-0">Conta:</label>
                <Select
                  value={composerData.account}
                  onValueChange={(v) =>
                    setComposerData((d) => ({ ...d, account: v }))
                  }
                >
                  <SelectTrigger className="flex-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="precision">Precision Crédito</SelectItem>
                    <SelectItem value="power">Power Real Estate</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Body */}
              <div>
                <Textarea
                  placeholder="Escreva a sua mensagem..."
                  value={composerData.body}
                  onChange={(e) =>
                    setComposerData((d) => ({ ...d, body: e.target.value }))
                  }
                  className="min-h-[200px] resize-y"
                  rows={12}
                />
              </div>
            </div>

            <DialogFooter className="px-6 py-3 border-t shrink-0">
              <Button
                variant="ghost"
                onClick={() => setComposerOpen(false)}
                disabled={composerSending}
              >
                Cancelar
              </Button>
              <Button onClick={handleSendEmail} disabled={composerSending}>
                {composerSending ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    A enviar...
                  </>
                ) : (
                  <>
                    <Send className="h-4 w-4 mr-2" />
                    Enviar
                  </>
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* ===== LINK TO PROCESS DIALOG ===== */}
        <Dialog open={linkDialogOpen} onOpenChange={setLinkDialogOpen}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>Associar a Processo</DialogTitle>
              <DialogDescription>
                Pesquise um cliente para associar este email ao respetivo processo
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-3">
              {/* Search input */}
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Pesquisar por nome do cliente..."
                  value={linkSearchQuery}
                  onChange={(e) => handleSearchClients(e.target.value)}
                  className="pl-9"
                  autoFocus
                />
              </div>

              {/* Results */}
              {linkSearchLoading && (
                <div className="space-y-2 py-2">
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-10 w-full" />
                </div>
              )}

              {!linkSearchLoading && linkSearchResults.length > 0 && (
                <div className="border rounded-md max-h-[250px] overflow-y-auto divide-y">
                  {linkSearchResults.map((client) => (
                    <button
                      key={client.id}
                      onClick={() => handleLinkProcess(client.id)}
                      disabled={linkSaving}
                      className="w-full flex items-center gap-3 px-3 py-2.5 text-left hover:bg-accent transition-colors disabled:opacity-50"
                    >
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">
                          {client.nome}
                        </p>
                        {client.email && (
                          <p className="text-xs text-muted-foreground truncate">
                            {client.email}
                          </p>
                        )}
                      </div>
                      {linkSaving ? (
                        <Loader2 className="h-4 w-4 animate-spin shrink-0" />
                      ) : (
                        <Link2 className="h-4 w-4 text-muted-foreground shrink-0" />
                      )}
                    </button>
                  ))}
                </div>
              )}

              {!linkSearchLoading &&
                linkSearchQuery.trim().length >= 2 &&
                linkSearchResults.length === 0 && (
                  <p className="text-sm text-muted-foreground text-center py-4">
                    Nenhum cliente encontrado
                  </p>
                )}

              {!linkSearchLoading && linkSearchQuery.trim().length < 2 && (
                <p className="text-sm text-muted-foreground text-center py-4">
                  Introduza pelo menos 2 caracteres para pesquisar
                </p>
              )}
            </div>
          </DialogContent>
        </Dialog>
        </div>
      </TooltipProvider>
    </DashboardLayout>
  );
};

export default WebmailPage;
