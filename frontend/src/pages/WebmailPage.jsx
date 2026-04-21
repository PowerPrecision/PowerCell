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
  Image,
  FileSpreadsheet,
  File,
  Tag,
  CheckSquare,
  Square,
  Upload,
  Download,
  Trash2,
  FolderPlus,
  FolderOpen,
  Folder,
  FolderInput,
  Pencil,
  MoreVertical,
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

// Formatar tamanho de ficheiro
const formatFileSize = (bytes) => {
  if (!bytes) return '';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
};

// Ícone por tipo de ficheiro
const getAttachmentIcon = (filename) => {
  if (!filename) return File;
  const lower = filename.toLowerCase();
  if (/\.(jpg|jpeg|png|gif|bmp|webp|svg|ico|tiff?)$/i.test(lower)) return Image;
  if (/\.(xls|xlsx|csv|ods)$/i.test(lower)) return FileSpreadsheet;
  if (/\.(doc|docx|pdf|txt|rtf|odt)$/i.test(lower)) return FileText;
  return File;
};

const WebmailPage = () => {
  const { token, user } = useAuth();
  const navigate = useNavigate();

  // Auto-select account based on user email domain
  const userDomain = (user?.email || "").split("@")[1]?.toLowerCase() || "";
  const defaultAccount = userDomain.includes("power") ? "power"
    : userDomain.includes("precision") ? "precision"
    : "power";

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
  const [account, setAccount] = useState(defaultAccount);

  // Tab-based mailbox state
  const [activeBox, setActiveBox] = useState(null); // "personal", "general", or "shared_indexacao"
  const [unreadByBox, setUnreadByBox] = useState({ personal: 0, general: 0 });

  // Composer state
  const [composerOpen, setComposerOpen] = useState(false);
  const [composerData, setComposerData] = useState({
    to_emails: "",
    cc_emails: "",
    subject: "",
    body: "",
    account: defaultAccount,
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

  // Labels state
  const [labels, setLabels] = useState([]);
  const [selectedLabel, setSelectedLabel] = useState(null);
  const [labelsLoading, setLabelsLoading] = useState(false);

  // Multi-select state
  const [selectedEmails, setSelectedEmails] = useState(new Set());
  const [multiSelectMode, setMultiSelectMode] = useState(false);
  const [labelDropdownOpen, setLabelDropdownOpen] = useState(false);

  // Upload attachments state (composer)
  const [uploadAttachments, setUploadAttachments] = useState([]);
  const [uploadingFiles, setUploadingFiles] = useState(false);
  const fileInputRef = useRef(null);

  // Custom folders state
  const [customFolders, setCustomFolders] = useState([]);
  const [activeCustomFolder, setActiveCustomFolder] = useState(null);
  const [folderDialogOpen, setFolderDialogOpen] = useState(false);
  const [folderDialogMode, setFolderDialogMode] = useState("create"); // "create" | "edit"
  const [folderDialogData, setFolderDialogData] = useState({ name: "", color: "#6b7280" });
  const [folderDialogSaving, setFolderDialogSaving] = useState(false);
  const [moveFolderOpen, setMoveFolderOpen] = useState(false);
  const [contextMenuPosition, setContextMenuPosition] = useState(null);
  const [contextMenuFolder, setContextMenuFolder] = useState(null);

  // Debounce search
  const searchTimeoutRef = useRef(null);

  // ============================================================
  // ROLE-BASED TABS: Initialize activeBox
  // ============================================================
  useEffect(() => {
    const role = user?.role;
    if (role === 'consultor') setActiveBox('personal');
    else if (role === 'indexacao') setActiveBox('shared_indexacao');
    else setActiveBox('personal'); // admin/ceo/diretor/administrativo default to personal
  }, [user?.role]);

  // Derived UI state
  const showTabs = ['admin', 'ceo', 'diretor', 'administrativo'].includes(user?.role);
  const showAccountSelector = showTabs && activeBox === 'personal';
  const pageSubtitle = !showTabs
    ? (user?.role === 'indexacao' ? 'Caixa de Indexação (Partilhada)' : 'A Minha Caixa de Entrada')
    : null;

  // ============================================================
  // FETCH LABELS
  // ============================================================
  const fetchLabels = useCallback(async () => {
    if (!token) return;
    setLabelsLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/emails/labels`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setLabels(Array.isArray(data) ? data : data.labels || []);
      }
    } catch {
      // Silently fail — labels are non-critical
    } finally {
      setLabelsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchLabels();
  }, [fetchLabels]);

  // ============================================================
  // FETCH CUSTOM FOLDERS
  // ============================================================
  const fetchCustomFolders = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API_URL}/api/emails/folders`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setCustomFolders(Array.isArray(data.folders) ? data.folders : []);
      }
    } catch (error) {
      console.error("Erro ao carregar pastas personalizadas:", error);
    }
  }, [token]);

  useEffect(() => {
    fetchCustomFolders();
  }, [fetchCustomFolders]);

  // ============================================================
  // FETCH UNREAD COUNTS (for tab badges)
  // ============================================================
  const fetchUnreadCounts = useCallback(async () => {
    if (!token) return;
    const role = user?.role;
    if (!role) return;

    if (['admin', 'ceo', 'diretor', 'administrativo'].includes(role)) {
      // Fetch both personal and general unread counts
      try {
        const [personalRes, generalRes] = await Promise.all([
          fetch(`${API_URL}/api/emails/webmail-stats?box=personal`, { headers: { Authorization: `Bearer ${token}` } }),
          fetch(`${API_URL}/api/emails/webmail-stats?box=general`, { headers: { Authorization: `Bearer ${token}` } }),
        ]);
        const pData = personalRes.ok ? await personalRes.json() : {};
        const gData = generalRes.ok ? await generalRes.json() : {};
        setUnreadByBox({ personal: pData.unread_count || 0, general: gData.unread_count || 0 });
      } catch {
        // Silently fail
      }
    } else if (role === 'indexacao') {
      try {
        const res = await fetch(`${API_URL}/api/emails/webmail-stats?box=shared_indexacao`, { headers: { Authorization: `Bearer ${token}` } });
        if (res.ok) {
          const data = await res.json();
          setUnreadByBox({ personal: 0, general: 0, shared_indexacao: data.unread_count || 0 });
        }
      } catch {
        // Silently fail
      }
    }
    // For consultor, the regular unreadCount from fetchEmails is sufficient
  }, [token, user?.role]);

  useEffect(() => {
    fetchUnreadCounts();
    const interval = setInterval(fetchUnreadCounts, 60000);
    return () => clearInterval(interval);
  }, [fetchUnreadCounts]);

  // ============================================================
  // FETCH EMAILS
  // ============================================================
  const fetchEmails = useCallback(async (folder, page, search, label, customFolderId) => {
    if (!token) return;
    setLoading(true);
    try {
      const actualFolder = customFolderId ? "custom" : (folder || activeFolder);
      const params = new URLSearchParams({
        folder: actualFolder,
        page: String(page || 1),
        limit: "30",
        account: account,
      });
      if (search && search.trim()) {
        params.append("search", search.trim());
      }
      if (label) {
        params.append("label", label);
      }
      if (customFolderId) {
        params.append("custom_folder", customFolderId);
      }
      // Always enforce box=shared_indexacao for indexacao role
      const effectiveBox = user?.role === 'indexacao' ? 'shared_indexacao' : activeBox;
      if (effectiveBox) {
        params.append("box", effectiveBox);
      }

      const response = await fetch(
        `${API_URL}/api/emails/webmail?${params.toString()}`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Erro ${response.status} ao carregar emails`);
      }
      const data = await response.json();

      console.debug("[Webmail] folder=%s, account=%s, total=%d", actualFolder, account, data?.total || 0);

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
  }, [token, activeFolder, account, activeBox, user?.role]);

  // Carregar emails quando muda pasta, página ou label
  useEffect(() => {
    if (activeCustomFolder) {
      fetchEmails("custom", currentPage, "", null, activeCustomFolder);
    } else {
      fetchEmails(activeFolder, currentPage, "", selectedLabel);
    }
    setSelectedEmail(null);
    setEmailDetail(null);
    setShowMobileReading(false);
    setSelectedEmails(new Set());
  }, [activeFolder, currentPage, selectedLabel, activeCustomFolder, activeBox, fetchEmails]);

  // Debounced search
  const handleSearchChange = useCallback((value) => {
    setSearchQuery(value);
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }
    searchTimeoutRef.current = setTimeout(() => {
      setCurrentPage(1);
      if (activeCustomFolder) {
        fetchEmails("custom", 1, value, null, activeCustomFolder);
      } else {
        fetchEmails(activeFolder, 1, value, selectedLabel);
      }
    }, 400);
  }, [activeFolder, fetchEmails, selectedLabel, activeCustomFolder]);

  // Refresh
  const handleRefresh = useCallback(() => {
    if (activeCustomFolder) {
      fetchEmails("custom", currentPage, searchQuery, null, activeCustomFolder);
    } else {
      fetchEmails(activeFolder, currentPage, searchQuery, selectedLabel);
    }
  }, [activeFolder, currentPage, searchQuery, fetchEmails, selectedLabel, activeCustomFolder]);

  // ============================================================
  // SYNC EMAILS (IMAP → DB)
  // ============================================================
  const handleSyncEmails = useCallback(async () => {
    if (!token || syncing) return;
    setSyncing(true);
    try {
      // Determine sync endpoint based on role and active box
      const isGeneralSync = activeBox === 'general' && showTabs;
      const syncEndpoint = isGeneralSync
        ? `${API_URL}/api/emails/webmail/sync`
        : `${API_URL}/api/emails/webmail/sync-user`;

      const params = new URLSearchParams({ days: "7" });
      if (account && !isGeneralSync) {
        params.append("account", account);
      }
      const response = await fetch(
        `${syncEndpoint}?${params.toString()}`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        toast.error(data.detail || "Erro na sincronização");
        return;
      }

      if (data.success === false) {
        toast.error(data.error || "Erro na sincronização");
        return;
      }

      // Background sync started — show info toast
      toast.info("Sincronização iniciada em background. Pode acompanhar o progresso em Tarefas em Background.");
      setLastSyncTime(new Date());

      // Auto-refresh after a delay to pick up synced emails
      setTimeout(() => {
        handleRefresh();
      }, 5000);
    } catch (error) {
      console.error("Erro ao sincronizar emails:", error);
      toast.error("Erro de ligação ao servidor");
    } finally {
      setSyncing(false);
    }
  }, [token, account, syncing, handleRefresh, activeBox, showTabs]);

  // ============================================================
  // SELECT EMAIL & MARK AS READ
  // ============================================================
  const handleSelectEmail = useCallback(async (email) => {
    if (multiSelectMode) {
      // Toggle checkbox in multi-select mode
      setSelectedEmails((prev) => {
        const next = new Set(prev);
        if (next.has(email.id)) {
          next.delete(email.id);
        } else {
          next.add(email.id);
        }
        return next;
      });
      return;
    }

    setSelectedEmail(email);
    setShowMobileReading(true);

    // Carregar detalhe completo
    setDetailLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/emails/${email.id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `Erro ${response.status} ao carregar email`);
      }
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
  }, [token, multiSelectMode]);

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
    setUploadAttachments([]);
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

      const bodyPayload = {
        to_emails: toList,
        subject: composerData.subject,
        body: composerData.body,
        body_html: "",
        cc_emails: ccList,
        process_id: composerData.process_id,
        from_box: activeBox,
      };

      // Include attachment_ids if any uploads
      if (uploadAttachments.length > 0) {
        bodyPayload.attachment_ids = uploadAttachments.map((a) => a.id);
      }

      const response = await fetch(
        `${API_URL}/api/emails/send?account=${composerData.account}`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify(bodyPayload),
        }
      );

      if (!response.ok) throw new Error("Erro ao enviar email");
      toast.success("Email enviado com sucesso");
      setComposerOpen(false);
      setUploadAttachments([]);
      handleRefresh();
    } catch (error) {
      console.error("Erro ao enviar:", error);
      toast.error("Erro ao enviar email");
    } finally {
      setComposerSending(false);
    }
  }, [composerData, token, handleRefresh, uploadAttachments, activeBox]);

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
          `${API_URL}/api/processes?search=${encodeURIComponent(query.trim())}&size=10`,
          {
            headers: { Authorization: `Bearer ${token}` },
          }
        );
        if (!response.ok) throw new Error("Erro na pesquisa");
        const data = await response.json();
        const items = data.items || data || [];
        setLinkSearchResults(items.map(p => ({
          id: p.id,
          name: p.client_name,
          email: p.client_email,
          number: p.process_number,
        })));
      } catch {
        toast.error("Erro ao pesquisar processos");
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
  // MULTI-SELECT HANDLERS
  // ============================================================
  const handleToggleMultiSelect = useCallback(() => {
    setMultiSelectMode((prev) => {
      if (prev) {
        setSelectedEmails(new Set());
        setLabelDropdownOpen(false);
      }
      return !prev;
    });
  }, []);

  const handleSelectAll = useCallback(() => {
    if (selectedEmails.size === emails.length) {
      setSelectedEmails(new Set());
    } else {
      setSelectedEmails(new Set(emails.map((e) => e.id)));
    }
  }, [emails, selectedEmails.size]);

  const handleApplyLabelToSelected = useCallback(async (labelId) => {
    if (selectedEmails.size === 0 || !labelId) return;
    try {
      const response = await fetch(`${API_URL}/api/emails/labels/apply`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email_ids: Array.from(selectedEmails),
          label_id: labelId,
        }),
      });
      if (response.ok) {
        toast.success("Marcador aplicado com sucesso");
        setLabelDropdownOpen(false);
        setSelectedEmails(new Set());
        setMultiSelectMode(false);
        handleRefresh();
        fetchLabels();
      } else {
        toast.error("Erro ao aplicar marcador");
      }
    } catch {
      toast.error("Erro ao aplicar marcador");
    }
  }, [selectedEmails, token, handleRefresh, fetchLabels]);

  const handleDeleteSelected = useCallback(async () => {
    if (selectedEmails.size === 0) return;
    try {
      const ids = Array.from(selectedEmails);
      await Promise.all(
        ids.map((id) =>
          fetch(`${API_URL}/api/emails/${id}`, {
            method: "DELETE",
            headers: { Authorization: `Bearer ${token}` },
          })
        )
      );
      toast.success(`${ids.length} email${ids.length !== 1 ? "s" : ""} eliminado${ids.length !== 1 ? "s" : ""}`);
      setSelectedEmails(new Set());
      setMultiSelectMode(false);
      if (selectedEmail && ids.includes(selectedEmail.id)) {
        setSelectedEmail(null);
        setEmailDetail(null);
      }
      handleRefresh();
    } catch {
      toast.error("Erro ao eliminar emails");
    }
  }, [selectedEmails, token, selectedEmail, handleRefresh]);

  const handleDeleteSingle = useCallback(async () => {
    if (!selectedEmail) return;
    if (!confirm("Tem a certeza que deseja eliminar este email?")) return;
    try {
      const response = await fetch(`${API_URL}/api/emails/${selectedEmail.id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error("Erro ao eliminar");
      toast.success("Email eliminado");
      setSelectedEmail(null);
      setEmailDetail(null);
      setShowMobileReading(false);
      handleRefresh();
    } catch {
      toast.error("Erro ao eliminar email");
    }
  }, [selectedEmail, token, handleRefresh]);

  // ============================================================
  // FILE UPLOAD (Composer)
  // ============================================================
  const uploadFiles = useCallback(async (files) => {
    if (!files || files.length === 0) return;
    setUploadingFiles(true);
    for (const file of files) {
      const formData = new FormData();
      formData.append("files", file);
      try {
        const res = await fetch(`${API_URL}/api/emails/attachments/upload`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: formData,
        });
        if (res.ok) {
          const data = await res.json();
          const uploaded = data.files || [data];
          setUploadAttachments((prev) => [...prev, ...uploaded]);
        } else {
          toast.error(`Erro ao carregar ${file.name}`);
        }
      } catch {
        toast.error(`Erro ao carregar ${file.name}`);
      }
    }
    setUploadingFiles(false);
  }, [token]);

  const handleDropZoneClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileInputChange = useCallback((e) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      uploadFiles(Array.from(files));
    }
    // Reset input so same file can be selected again
    if (e.target) e.target.value = "";
  }, [uploadFiles]);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    const files = e.dataTransfer?.files;
    if (files && files.length > 0) {
      uploadFiles(Array.from(files));
    }
  }, [uploadFiles]);

  const handleRemoveUpload = useCallback((fileId) => {
    setUploadAttachments((prev) => prev.filter((a) => a.id !== fileId));
  }, []);

  // ============================================================
  // FOLDER CRUD HANDLERS
  // ============================================================
  const handleOpenFolderDialog = useCallback((mode = "create", folder = null) => {
    setFolderDialogMode(mode);
    if (mode === "edit" && folder) {
      setFolderDialogData({ name: folder.name, color: folder.color });
    } else {
      setFolderDialogData({ name: "", color: "#6b7280" });
    }
    setFolderDialogOpen(true);
  }, []);

  const handleSaveFolder = useCallback(async () => {
    if (!folderDialogData.name.trim()) {
      toast.error("Nome da pasta é obrigatório");
      return;
    }
    setFolderDialogSaving(true);
    try {
      const url = folderDialogMode === "create"
        ? `${API_URL}/api/emails/folders`
        : `${API_URL}/api/emails/folders/${contextMenuFolder?.id}`;
      const method = folderDialogMode === "create" ? "POST" : "PUT";
      
      const res = await fetch(url, {
        method,
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: folderDialogData.name.trim(),
          color: folderDialogData.color,
        }),
      });

      if (res.ok) {
        toast.success(folderDialogMode === "create" ? "Pasta criada" : "Pasta atualizada");
        setFolderDialogOpen(false);
        fetchCustomFolders();
      } else {
        const data = await res.json().catch(() => ({}));
        toast.error(data.detail || "Erro ao guardar pasta");
      }
    } catch {
      toast.error("Erro de ligação ao servidor");
    } finally {
      setFolderDialogSaving(false);
    }
  }, [folderDialogData, folderDialogMode, contextMenuFolder, token, fetchCustomFolders]);

  const handleDeleteFolder = useCallback(async (folder) => {
    if (!folder) return;
    try {
      const res = await fetch(`${API_URL}/api/emails/folders/${folder.id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        toast.success(`Pasta "${folder.name}" eliminada`);
        if (activeCustomFolder === folder.id) {
          setActiveCustomFolder(null);
          setActiveFolder("inbox");
        }
        fetchCustomFolders();
      } else {
        toast.error("Erro ao eliminar pasta");
      }
    } catch {
      toast.error("Erro ao eliminar pasta");
    }
    setContextMenuPosition(null);
  }, [token, activeCustomFolder, fetchCustomFolders]);

  const handleMoveToFolder = useCallback(async (folderId) => {
    const emailIds = selectedEmails.size > 0
      ? Array.from(selectedEmails)
      : selectedEmail ? [selectedEmail.id] : [];
    
    if (emailIds.length === 0) return;

    try {
      const res = await fetch(`${API_URL}/api/emails/emails/move-to-folder`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email_ids: emailIds,
          folder_id: folderId || null,
        }),
      });

      if (res.ok) {
        const folderName = folderId
          ? customFolders.find(f => f.id === folderId)?.name || "Pasta"
          : "Caixa de Entrada";
        toast.success(`${emailIds.length} email${emailIds.length !== 1 ? "s" : ""} movido${emailIds.length !== 1 ? "s" : ""} para "${folderName}"`);
        setMoveFolderOpen(false);
        setSelectedEmails(new Set());
        setMultiSelectMode(false);
        handleRefresh();
        fetchCustomFolders();
      } else {
        toast.error("Erro ao mover emails");
      }
    } catch {
      toast.error("Erro ao mover emails");
    }
  }, [selectedEmails, selectedEmail, token, customFolders, handleRefresh, fetchCustomFolders]);

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
          {showAccountSelector && (
          <Select value={account} onValueChange={setAccount}>
            <SelectTrigger className="w-[160px] h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="precision">Precision Crédito</SelectItem>
              <SelectItem value="power">Power Real Estate</SelectItem>
            </SelectContent>
          </Select>
          )}

          {/* Select (multi-select toggle) */}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant={multiSelectMode ? "default" : "ghost"}
                size="icon"
                className="h-8 w-8"
                onClick={handleToggleMultiSelect}
              >
                {multiSelectMode ? (
                  <CheckSquare className="h-4 w-4" />
                ) : (
                  <Square className="h-4 w-4" />
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent>Selecionar</TooltipContent>
          </Tooltip>

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

          {/* Move to Folder (visible in multi-select mode) */}
          {(multiSelectMode && selectedEmails.size > 0) && (
            <Button
              variant="ghost"
              size="sm"
              className="h-8 gap-1.5 text-xs"
              onClick={() => setMoveFolderOpen(true)}
            >
              <FolderInput className="h-4 w-4" />
              Mover
              {selectedEmails.size > 0 && (
                <Badge variant="secondary" className="h-5 text-[10px] px-1.5">
                  {selectedEmails.size}
                </Badge>
              )}
            </Button>
          )}
        </div>

        {/* ===== TAB BAR (role-based) ===== */}
        {showTabs && (
          <div className="flex items-center gap-1 px-4 py-2 border-b bg-muted/20 shrink-0">
            <button
              onClick={() => { setActiveBox('personal'); setCurrentPage(1); }}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                activeBox === 'personal'
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-accent hover:text-foreground'
              }`}
            >
              Caixa Pessoal
              {unreadByBox.personal > 0 && (
                <Badge variant="secondary" className="ml-2 h-5 text-[10px] px-1.5">
                  {unreadByBox.personal}
                </Badge>
              )}
            </button>
            <button
              onClick={() => { setActiveBox('general'); setCurrentPage(1); }}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                activeBox === 'general'
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-accent hover:text-foreground'
              }`}
            >
              Caixa Geral
              {unreadByBox.general > 0 && (
                <Badge variant="secondary" className="ml-2 h-5 text-[10px] px-1.5">
                  {unreadByBox.general}
                </Badge>
              )}
            </button>
          </div>
        )}

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
            <nav className="p-2 space-y-0.5">
              {FOLDERS.map((folder) => {
                const Icon = folder.icon;
                const isActive = activeFolder === folder.id && !selectedLabel && !activeCustomFolder;
                // Show role-specific label for inbox on non-tab roles
                const folderLabel = (folder.id === 'inbox' && pageSubtitle) ? pageSubtitle : folder.label;
                return (
                  <button
                    key={folder.id}
                    onClick={() => {
                      setActiveFolder(folder.id);
                      setCurrentPage(1);
                      setSelectedLabel(null);
                      setActiveCustomFolder(null);
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
                    <span className="flex-1 truncate">{folderLabel}</span>
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

            {/* Marcadores (Labels) */}
            {labels.length > 0 && (
              <>
                <Separator />
                <div className="px-2 pt-2 pb-1">
                  <div className="flex items-center gap-2 px-3 py-1.5">
                    <Tag className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                      Marcadores
                    </span>
                  </div>
                  <div className="space-y-0.5">
                    {labels.map((label) => {
                      const isLabelActive = selectedLabel === label.name;
                      return (
                        <button
                          key={label.id}
                          onClick={() => {
                            setSelectedLabel(isLabelActive ? null : label.name);
                            setCurrentPage(1);
                            setActiveFolder("inbox");
                          }}
                          className={`
                            w-full flex items-center gap-3 px-3 py-1.5 rounded-md text-sm
                            transition-colors text-left
                            ${
                              isLabelActive
                                ? "bg-accent text-accent-foreground font-medium"
                                : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
                            }
                          `}
                        >
                          <span
                            className="w-3 h-3 rounded-full shrink-0 border border-black/10"
                            style={{ backgroundColor: label.color || "#6b7280" }}
                          />
                          <span className="flex-1 truncate">{label.name}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              </>
            )}

            {/* Pastas Personalizadas */}
            <div className="px-2 pt-1 pb-1">
              <div className="flex items-center justify-between px-3 py-1.5">
                <div className="flex items-center gap-2">
                  <Folder className="h-3.5 w-3.5 text-muted-foreground" />
                  <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    Pastas
                  </span>
                </div>
                <button
                  onClick={() => { setContextMenuFolder(null); handleOpenFolderDialog("create"); }}
                  className="p-0.5 rounded hover:bg-accent/50 text-muted-foreground hover:text-foreground transition-colors"
                  title="Nova pasta"
                >
                  <FolderPlus className="h-3.5 w-3.5" />
                </button>
              </div>
              <div className="space-y-0.5">
                {customFolders.map((folder) => {
                  const isFolderActive = activeCustomFolder === folder.id;
                  return (
                    <div key={folder.id} className="relative group">
                      <button
                        onClick={() => {
                          setActiveCustomFolder(isFolderActive ? null : folder.id);
                          setActiveFolder("inbox");
                          setCurrentPage(1);
                          setSelectedLabel(null);
                        }}
                        className={`
                          w-full flex items-center gap-3 px-3 py-1.5 rounded-md text-sm
                          transition-colors text-left
                          ${
                            isFolderActive
                              ? "bg-accent text-accent-foreground font-medium"
                              : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
                          }
                        `}
                      >
                        <FolderOpen className={`h-4 w-4 shrink-0 ${isFolderActive ? "text-foreground" : ""}`}
                          style={isFolderActive ? { color: folder.color } : {}}
                        />
                        <span className="flex-1 truncate">{folder.name}</span>
                        {folder.email_count > 0 && (
                          <Badge
                            variant="secondary"
                            className="h-5 min-w-[20px] flex items-center justify-center text-[10px] px-1.5"
                          >
                            {folder.email_count}
                          </Badge>
                        )}
                        {/* Context menu trigger - only visible on hover */}
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setContextMenuFolder(folder);
                            const rect = e.currentTarget.getBoundingClientRect();
                            setContextMenuPosition({ x: rect.left, y: rect.bottom });
                          }}
                          className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-accent/70 transition-opacity"
                        >
                          <MoreVertical className="h-3 w-3" />
                        </button>
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Footer info */}
            <div className="mt-auto p-3 border-t space-y-1">
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
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold">
                  {activeCustomFolder
                    ? customFolders.find((f) => f.id === activeCustomFolder)?.name || "Pasta"
                    : selectedLabel
                    ? labels.find((l) => l.id === selectedLabel)?.name || "Marcador"
                    : FOLDERS.find((f) => f.id === activeFolder)?.label}
                </h2>
                {activeCustomFolder && (
                  <button
                    onClick={() => setActiveCustomFolder(null)}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    <X className="h-3 w-3" />
                  </button>
                )}
                {selectedLabel && (
                  <button
                    onClick={() => setSelectedLabel(null)}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    <X className="h-3 w-3" />
                  </button>
                )}
              </div>
              <div className="flex items-center gap-2">
                {multiSelectMode && (
                  <button
                    onClick={handleSelectAll}
                    className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                  >
                    {selectedEmails.size === emails.length && emails.length > 0
                      ? "Desselecionar"
                      : "Selecionar tudo"}
                  </button>
                )}
                {totalPages > 1 && (
                  <span className="text-xs text-muted-foreground">
                    Página {currentPage} de {totalPages}
                  </span>
                )}
              </div>
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
                      : selectedLabel
                      ? "Sem emails com este marcador"
                      : "Sem emails nesta pasta"}
                  </p>
                </div>
              ) : (
                // Email items
                <div className="divide-y">
                  {emails.map((email) => {
                    const isSelected = selectedEmail?.id === email.id;
                    const isChecked = selectedEmails.has(email.id);
                    return (
                      <button
                        key={email.id}
                        onClick={() => handleSelectEmail(email)}
                        className={`
                          w-full text-left p-3 transition-colors hover:bg-accent/50
                          ${isSelected && !multiSelectMode ? "bg-accent" : ""}
                        `}
                      >
                        <div className="flex items-start gap-2">
                          {/* Multi-select checkbox */}
                          {multiSelectMode && (
                            <span className="mt-1 shrink-0">
                              {isChecked ? (
                                <CheckSquare className="h-4 w-4 text-primary" />
                              ) : (
                                <Square className="h-4 w-4 text-muted-foreground" />
                              )}
                            </span>
                          )}

                          {/* Unread dot */}
                          {!multiSelectMode && !email.is_read && (
                            <span className="bg-blue-500 w-2 h-2 rounded-full mt-1.5 shrink-0" />
                          )}
                          {!multiSelectMode && email.is_read && <span className="w-2 shrink-0" />}

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
                            <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                              <p className="text-xs text-muted-foreground truncate flex-1 min-w-0">
                                {email.preview || ""}
                              </p>
                              {/* Label badges */}
                              {email.labels?.length > 0 && (
                                <span className="flex items-center gap-1 shrink-0">
                                  {email.labels.slice(0, 2).map((lbl) => (
                                    <span
                                      key={lbl.id || lbl.name}
                                      className="rounded-full px-1.5 py-0.5 text-white leading-none"
                                      style={{
                                        backgroundColor: lbl.color || "#6b7280",
                                        fontSize: "10px",
                                      }}
                                    >
                                      {lbl.name}
                                    </span>
                                  ))}
                                  {email.labels.length > 2 && (
                                    <span
                                      className="rounded-full px-1.5 py-0.5 text-muted-foreground leading-none border"
                                      style={{ fontSize: "10px" }}
                                    >
                                      +{email.labels.length - 2}
                                    </span>
                                  )}
                                </span>
                              )}
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
                    {/* Label badges on detail */}
                    {emailDetail.labels?.length > 0 && (
                      <div className="flex items-center gap-1.5 flex-wrap pt-1">
                        {emailDetail.labels.map((lbl) => (
                          <span
                            key={lbl.id || lbl.name}
                            className="rounded-full px-2 py-0.5 text-white leading-none"
                            style={{
                              backgroundColor: lbl.color || "#6b7280",
                              fontSize: "11px",
                            }}
                          >
                            {lbl.name}
                          </span>
                        ))}
                      </div>
                    )}
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
                    {emailDetail.process_id ? (
                      <Badge
                        variant="secondary"
                        className="h-8 text-xs gap-1.5 cursor-pointer hover:bg-accent"
                        onClick={() => navigate(`/processo/${emailDetail.process_id}`)}
                      >
                        <Link2 className="h-3.5 w-3.5" />
                        {emailDetail.process_id} Associado
                      </Badge>
                    ) : (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-8 text-xs gap-1.5"
                            onClick={handleOpenLinkDialog}
                          >
                            <Link2 className="h-3.5 w-3.5" />
                            Ligar a Processo
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Ligar a Processo</TooltipContent>
                      </Tooltip>
                    )}
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <button
                          onClick={() => setMoveFolderOpen(true)}
                          className="p-1.5 rounded-md hover:bg-accent/50 text-muted-foreground hover:text-foreground transition-colors"
                          title="Mover para pasta"
                        >
                          <FolderInput className="h-4 w-4" />
                        </button>
                      </TooltipTrigger>
                      <TooltipContent>Mover para pasta</TooltipContent>
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
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-8 w-8 p-0 text-destructive hover:text-destructive hover:bg-destructive/10"
                          onClick={handleDeleteSingle}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>Eliminar email</TooltipContent>
                    </Tooltip>
                  </div>
                </div>

                {/* Body */}
                <ScrollArea className="flex-1">
                  <div className="p-5">
                    {sanitizedBodyHtml ? (
                      <iframe
                        srcDoc={sanitizedBodyHtml}
                        className="w-full border-0 rounded-md"
                        style={{ minHeight: "200px", maxHeight: "600px" }}
                        title="Email content"
                        sandbox="allow-same-origin"
                        onLoad={(e) => {
                          const doc = e.target.contentDocument;
                          if (doc) {
                            const h = doc.body?.scrollHeight || 200;
                            e.target.style.height = Math.min(h + 20, 600) + "px";
                          }
                        }}
                      />
                    ) : (
                      <pre className="whitespace-pre-wrap font-sans text-sm">
                        {emailDetail.body || ""}
                      </pre>
                    )}

                    {/* Attachments - Visual Cards */}
                    {emailDetail.attachments?.length > 0 && (
                      <div className="mt-6 pt-4 border-t">
                        <h4 className="font-medium text-sm flex items-center gap-2 mb-3">
                          <Paperclip className="h-4 w-4" />
                          Anexos ({emailDetail.attachments.length})
                        </h4>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                          {emailDetail.attachments.map((attachment, idx) => {
                            const AttIcon = getAttachmentIcon(attachment.filename);
                            return (
                              <div
                                key={attachment.id || idx}
                                className="flex items-center gap-3 p-3 rounded-lg border bg-muted/20 hover:bg-muted/40 transition-colors group"
                              >
                                <div className="h-9 w-9 rounded-md bg-muted flex items-center justify-center shrink-0">
                                  <AttIcon className="h-4 w-4 text-muted-foreground" />
                                </div>
                                <div className="flex-1 min-w-0">
                                  <p className="text-sm font-medium truncate">
                                    {attachment.filename || `Anexo ${idx + 1}`}
                                  </p>
                                  {attachment.size && (
                                    <p className="text-xs text-muted-foreground mt-0.5">
                                      {formatFileSize(attachment.size)}
                                    </p>
                                  )}
                                </div>
                                {attachment.url && (
                                  <Tooltip>
                                    <TooltipTrigger asChild>
                                      <a
                                        href={attachment.url}
                                        download={attachment.filename || `Anexo ${idx + 1}`}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="h-8 w-8 rounded-md border flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-accent transition-colors shrink-0"
                                        onClick={(e) => e.stopPropagation()}
                                      >
                                        <Download className="h-3.5 w-3.5" />
                                      </a>
                                    </TooltipTrigger>
                                    <TooltipContent>Descarregar</TooltipContent>
                                  </Tooltip>
                                )}
                              </div>
                            );
                          })}
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

        {/* ===== MULTI-SELECT FLOATING ACTION BAR ===== */}
        {multiSelectMode && selectedEmails.size > 0 && (
          <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 bg-background border shadow-lg rounded-xl px-4 py-2.5 flex items-center gap-3">
            <span className="text-sm font-medium">
              {selectedEmails.size} selecionado{selectedEmails.size !== 1 ? "s" : ""}
            </span>
            <Separator orientation="vertical" className="h-5" />
            {/* Apply Label button + dropdown */}
            <div className="relative">
              <Button
                variant="outline"
                size="sm"
                className="h-8 text-xs gap-1.5"
                onClick={() => setLabelDropdownOpen((prev) => !prev)}
                disabled={labels.length === 0}
              >
                <Tag className="h-3.5 w-3.5" />
                Aplicar Marcador
              </Button>
              {labelDropdownOpen && labels.length > 0 && (
                <div className="absolute bottom-full left-0 mb-1 bg-background border rounded-md shadow-md py-1 min-w-[160px] z-50">
                  {labels.map((label) => (
                    <button
                      key={label.id}
                      onClick={() => handleApplyLabelToSelected(label.id)}
                      className="w-full flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent transition-colors text-left"
                    >
                      <span
                        className="w-3 h-3 rounded-full shrink-0"
                        style={{ backgroundColor: label.color || "#6b7280" }}
                      />
                      <span className="truncate">{label.name}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <Button
              variant="destructive"
              size="sm"
              className="h-8 text-xs gap-1.5"
              onClick={handleDeleteSelected}
            >
              <Trash2 className="h-3.5 w-3.5" />
              Eliminar
            </Button>
          </div>
        )}

        {/* ===== EMAIL COMPOSER DIALOG ===== */}
        <Dialog open={composerOpen} onOpenChange={(open) => {
          if (!open) {
            setUploadAttachments([]);
            setUploadingFiles(false);
          }
          setComposerOpen(open);
        }}>
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

              {/* Drag & Drop upload zone */}
              <div
                onClick={handleDropZoneClick}
                onDragOver={handleDragOver}
                onDrop={handleDrop}
                className={`
                  border-2 border-dashed rounded-lg p-4 text-center cursor-pointer
                  transition-colors
                  ${uploadingFiles
                    ? "border-primary/50 bg-primary/5"
                    : "border-muted-foreground/25 hover:border-muted-foreground/50 hover:bg-muted/30"
                  }
                `}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  className="hidden"
                  onChange={handleFileInputChange}
                />
                {uploadingFiles ? (
                  <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    A carregar ficheiro(s)...
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-1.5">
                    <Upload className="h-5 w-5 text-muted-foreground" />
                    <p className="text-sm text-muted-foreground">
                      Arraste ficheiros aqui ou clique para selecionar
                    </p>
                  </div>
                )}
              </div>

              {/* Uploaded files list */}
              {uploadAttachments.length > 0 && (
                <div className="space-y-1.5">
                  {uploadAttachments.map((file) => {
                    const UpIcon = getAttachmentIcon(file.filename);
                    return (
                      <div
                        key={file.id}
                        className="flex items-center gap-2 p-2 rounded-md border bg-muted/20"
                      >
                        <UpIcon className="h-4 w-4 text-muted-foreground shrink-0" />
                        <span className="flex-1 text-sm truncate">
                          {file.filename || "Ficheiro"}
                        </span>
                        {file.size && (
                          <span className="text-xs text-muted-foreground shrink-0">
                            {formatFileSize(file.size)}
                          </span>
                        )}
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleRemoveUpload(file.id);
                          }}
                          className="h-5 w-5 rounded-full hover:bg-accent flex items-center justify-center text-muted-foreground hover:text-foreground shrink-0 transition-colors"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}

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
                  placeholder="Pesquisar por nome do cliente ou processo..."
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
                          {client.name}{client.number ? ` (${client.number})` : ""}
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
                    Nenhum processo encontrado
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

        {/* ===== FOLDER CONTEXT MENU ===== */}
        {contextMenuPosition && contextMenuFolder && (
          <>
            <div
              className="fixed inset-0 z-40"
              onClick={() => setContextMenuPosition(null)}
            />
            <div
              className="absolute z-50 bg-popover border rounded-md shadow-lg py-1 min-w-[140px]"
              style={{
                left: `${contextMenuPosition.x}px`,
                top: `${contextMenuPosition.y}px`,
              }}
            >
              <button
                onClick={() => {
                  setContextMenuPosition(null);
                  handleOpenFolderDialog("edit", contextMenuFolder);
                }}
                className="w-full flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent/50 text-left"
              >
                <Pencil className="h-3.5 w-3.5" />
                Renomear
              </button>
              <button
                onClick={() => {
                  setContextMenuPosition(null);
                  if (window.confirm(`Eliminar pasta "${contextMenuFolder.name}"? Os emails serão movidos para a Caixa de Entrada.`)) {
                    handleDeleteFolder(contextMenuFolder);
                  }
                }}
                className="w-full flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent/50 text-left text-destructive"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Eliminar
              </button>
            </div>
          </>
        )}

        {/* ===== FOLDER CREATE/EDIT DIALOG ===== */}
        <Dialog open={folderDialogOpen} onOpenChange={setFolderDialogOpen}>
          <DialogContent className="sm:max-w-[400px]">
            <DialogHeader>
              <DialogTitle>
                {folderDialogMode === "create" ? "Nova Pasta" : "Editar Pasta"}
              </DialogTitle>
              <DialogDescription>
                {folderDialogMode === "create"
                  ? "Crie uma pasta para organizar os seus emails"
                  : "Altere o nome ou cor da pasta"}
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-2">
              <div className="space-y-2">
                <label className="text-sm font-medium">Nome da pasta</label>
                <Input
                  placeholder="Ex: Clientes VIP, Documentação..."
                  value={folderDialogData.name}
                  onChange={(e) =>
                    setFolderDialogData((prev) => ({ ...prev, name: e.target.value }))
                  }
                  maxLength={40}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleSaveFolder();
                  }}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Cor</label>
                <div className="flex flex-wrap gap-2">
                  {[
                    "#6b7280", "#ef4444", "#f59e0b", "#22c55e", "#3b82f6",
                    "#8b5cf6", "#ec4899", "#14b8a6", "#f97316", "#6366f1",
                  ].map((color) => (
                    <button
                      key={color}
                      onClick={() =>
                        setFolderDialogData((prev) => ({ ...prev, color }))
                      }
                      className={`w-7 h-7 rounded-full border-2 transition-transform ${
                        folderDialogData.color === color
                          ? "border-foreground scale-110"
                          : "border-transparent hover:scale-105"
                      }`}
                      style={{ backgroundColor: color }}
                    />
                  ))}
                </div>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setFolderDialogOpen(false)}>
                Cancelar
              </Button>
              <Button onClick={handleSaveFolder} disabled={folderDialogSaving}>
                {folderDialogSaving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                {folderDialogMode === "create" ? "Criar Pasta" : "Guardar"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* ===== MOVE TO FOLDER DIALOG ===== */}
        <Dialog open={moveFolderOpen} onOpenChange={setMoveFolderOpen}>
          <DialogContent className="sm:max-w-[350px]">
            <DialogHeader>
              <DialogTitle>Mover para pasta</DialogTitle>
              <DialogDescription>
                Selecione a pasta de destino ou "Caixa de Entrada" para remover da pasta atual
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-1 py-2 max-h-60 overflow-y-auto">
              <button
                onClick={() => handleMoveToFolder(null)}
                className="w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm hover:bg-accent/50 text-left"
              >
                <Inbox className="h-4 w-4 text-muted-foreground" />
                <span>Caixa de Entrada</span>
              </button>
              {customFolders.map((folder) => (
                <button
                  key={folder.id}
                  onClick={() => handleMoveToFolder(folder.id)}
                  className="w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm hover:bg-accent/50 text-left"
                >
                  <FolderOpen className="h-4 w-4" style={{ color: folder.color }} />
                  <span className="flex-1 truncate">{folder.name}</span>
                  {folder.email_count > 0 && (
                    <span className="text-xs text-muted-foreground">{folder.email_count}</span>
                  )}
                </button>
              ))}
              {customFolders.length === 0 && (
                <p className="text-sm text-muted-foreground text-center py-4">
                  Sem pastas personalizadas
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
