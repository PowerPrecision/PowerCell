/**
 * ChatPanel - Painel de Chat Interno Completo
 * Sistema de mensagens entre utilizadores do CRM
 * 
 * Funcionalidades:
 * - Chat direto (1-para-1)
 * - Chat em grupo
 * - Anexos/ficheiros
 * - Typing indicators
 * - Reações a mensagens
 * - Pesquisa de mensagens
 * - Citação/resposta a mensagens
 */
import { useState, useEffect, useRef, useCallback } from "react";
import { useAuth } from "../contexts/AuthContext";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Badge } from "./ui/badge";
import { ScrollArea } from "./ui/scroll-area";
import { Avatar, AvatarFallback } from "./ui/avatar";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "./ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";
import { Textarea } from "./ui/textarea";
import { Label } from "./ui/label";
import {
  MessageSquare,
  Send,
  Search,
  X,
  ChevronLeft,
  Circle,
  Loader2,
  Users,
  Plus,
  Paperclip,
  Smile,
  MoreVertical,
  Reply,
  Trash2,
  Edit2,
  Search as SearchIcon,
  ArrowLeft,
  Check,
  FileText,
  Image as ImageIcon,
  File,
  Download,
} from "lucide-react";
import { toast } from "sonner";
import { format, parseISO, isToday, isYesterday } from "date-fns";
import { pt } from "date-fns/locale";
import EmojiPicker from "./EmojiPicker";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Emojis comuns para reações rápidas
const QUICK_REACTIONS = ["👍", "❤️", "😂", "😮", "😢", "🎉", "✅", "👎"];

const ChatPanel = ({ open, onOpenChange }) => {
  const { token, user } = useAuth();
  const [conversations, setConversations] = useState([]);
  const [selectedConversation, setSelectedConversation] = useState(null);
  const [messages, setMessages] = useState([]);
  const [newMessage, setNewMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [sendingMessage, setSendingMessage] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [allUsers, setAllUsers] = useState([]);
  const [showNewChat, setShowNewChat] = useState(false);
  const [showNewGroup, setShowNewGroup] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [unreadCount, setUnreadCount] = useState({ total: 0, direct: 0, group: 0 });
  const [typingUsers, setTypingUsers] = useState({});
  const [replyTo, setReplyTo] = useState(null);
  const [editingMessage, setEditingMessage] = useState(null);
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);
  const [showReactionsFor, setShowReactionsFor] = useState(null);
  const [groups, setGroups] = useState([]);
  const [newGroupName, setNewGroupName] = useState("");
  const [newGroupDescription, setNewGroupDescription] = useState("");
  const [selectedMembers, setSelectedMembers] = useState([]);
  const [uploadingFile, setUploadingFile] = useState(false);

  const messagesEndRef = useRef(null);
  const typingTimeoutRef = useRef(null);
  const fileInputRef = useRef(null);

  // Carregar conversas
  const fetchConversations = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/api/chat/conversations`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        setConversations(data.conversations || []);
      }
    } catch {
      // Error handled silently in production
    }
  }, [token]);

  // Carregar contagem de não lidas
  const fetchUnreadCount = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/api/chat/unread-count`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        setUnreadCount(data);
      }
    } catch {
      // Error handled silently in production
    }
  }, [token]);

  // Carregar grupos
  const fetchGroups = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/api/chat/groups`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        setGroups(data.groups || []);
      }
    } catch {
      // Error handled silently in production
    }
  }, [token]);

  // Carregar mensagens de uma conversa
  const fetchMessages = useCallback(async (conversationId, isGroup = false) => {
    setLoading(true);
    try {
      const response = await fetch(
        `${API_URL}/api/chat/messages/${conversationId}?is_group=${isGroup}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (response.ok) {
        const data = await response.json();
        setMessages(data.messages || []);
        setSelectedConversation({
          id: conversationId,
          isGroup,
          name: isGroup ? data.group?.name : data.other_user?.name,
          group: data.group,
          otherUser: data.other_user,
        });
        fetchConversations();
        fetchUnreadCount();
      }
    } catch {
      // Error handled silently in production
    } finally {
      setLoading(false);
    }
  }, [token, fetchConversations, fetchUnreadCount]);

  // Carregar utilizadores para nova conversa/grupo
  const fetchUsers = useCallback(async () => {
    try {
      const response = await fetch(
        `${API_URL}/api/chat/users${searchQuery ? `?search=${encodeURIComponent(searchQuery)}` : ""}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (response.ok) {
        const data = await response.json();
        setAllUsers(data.users || []);
      }
    } catch {
      // Error handled silently in production
    }
  }, [token, searchQuery]);

  // Enviar indicador de digitação
  const sendTypingIndicator = useCallback(async (isTyping) => {
    if (!selectedConversation) return;
    try {
      await fetch(`${API_URL}/api/chat/typing`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          receiver_id: selectedConversation.isGroup ? null : selectedConversation.id,
          group_id: selectedConversation.isGroup ? selectedConversation.id : null,
          is_typing: isTyping,
        }),
      });
    } catch {
      // Error handled silently in production
    }
  }, [token, selectedConversation]);

  // Handler de digitação
  const handleTyping = useCallback(() => {
    sendTypingIndicator(true);
    if (typingTimeoutRef.current) {
      clearTimeout(typingTimeoutRef.current);
    }
    typingTimeoutRef.current = setTimeout(() => {
      sendTypingIndicator(false);
    }, 2000);
  }, [sendTypingIndicator]);

  // Enviar mensagem
  const handleSendMessage = async (e) => {
    e?.preventDefault();
    if (!newMessage.trim() || !selectedConversation) return;

    setSendingMessage(true);
    try {
      const response = await fetch(`${API_URL}/api/chat/messages`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          receiver_id: selectedConversation.isGroup ? null : selectedConversation.id,
          group_id: selectedConversation.isGroup ? selectedConversation.id : null,
          content: newMessage.trim(),
          reply_to: replyTo?.id,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        setMessages((prev) => [...prev, data.message]);
        setNewMessage("");
        setReplyTo(null);
        fetchConversations();
        sendTypingIndicator(false);
      } else {
        toast.error("Erro ao enviar mensagem");
      }
    } catch {
      toast.error("Erro ao enviar mensagem");
    } finally {
      setSendingMessage(false);
    }
  };

  // Upload de ficheiro
  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file || !selectedConversation) return;

    if (file.size > 10 * 1024 * 1024) {
      toast.error("Ficheiro demasiado grande (máx 10MB)");
      return;
    }

    setUploadingFile(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("content", "");
      if (selectedConversation.isGroup) {
        formData.append("group_id", selectedConversation.id);
      } else {
        formData.append("receiver_id", selectedConversation.id);
      }

      const response = await fetch(`${API_URL}/api/chat/messages/upload`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (response.ok) {
        const data = await response.json();
        setMessages((prev) => [...prev, data.message]);
        fetchConversations();
        toast.success("Ficheiro enviado com sucesso");
      } else {
        toast.error("Erro ao enviar ficheiro");
      }
    } catch {
      toast.error("Erro ao enviar ficheiro");
    } finally {
      setUploadingFile(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  // Adicionar reação
  const handleReaction = async (messageId, reaction) => {
    try {
      const response = await fetch(`${API_URL}/api/chat/messages/react`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ message_id: messageId, reaction }),
      });

      if (response.ok) {
        const data = await response.json();
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === messageId ? { ...msg, reactions: data.reactions } : msg
          )
        );
      }
    } catch {
      // Error handled silently in production
    }
    setShowReactionsFor(null);
  };

  // Editar mensagem
  const handleEditMessage = async (messageId, newContent) => {
    try {
      const response = await fetch(`${API_URL}/api/chat/messages/edit`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ message_id: messageId, content: newContent }),
      });

      if (response.ok) {
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === messageId
              ? { ...msg, content: newContent, edited: true }
              : msg
          )
        );
        setEditingMessage(null);
        toast.success("Mensagem editada");
      }
    } catch {
      toast.error("Erro ao editar mensagem");
    }
  };

  // Apagar mensagem
  const handleDeleteMessage = async (messageId) => {
    if (!window.confirm("Tem a certeza que deseja apagar esta mensagem?")) return;

    try {
      const response = await fetch(`${API_URL}/api/chat/messages/${messageId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        setMessages((prev) => prev.filter((msg) => msg.id !== messageId));
        toast.success("Mensagem apagada");
      }
    } catch {
      toast.error("Erro ao apagar mensagem");
    }
  };

  // Criar grupo
  const handleCreateGroup = async () => {
    if (!newGroupName.trim()) {
      toast.error("Nome do grupo é obrigatório");
      return;
    }

    try {
      const response = await fetch(`${API_URL}/api/chat/groups`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: newGroupName,
          description: newGroupDescription,
          members: selectedMembers,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        toast.success("Grupo criado com sucesso");
        setShowNewGroup(false);
        setNewGroupName("");
        setNewGroupDescription("");
        setSelectedMembers([]);
        fetchGroups();
        fetchConversations();
        // Abrir o novo grupo
        fetchMessages(data.group.id, true);
      }
    } catch {
      toast.error("Erro ao criar grupo");
    }
  };

  // Pesquisar mensagens
  const handleSearch = async () => {
    if (!searchQuery.trim()) return;

    setSearching(true);
    try {
      const response = await fetch(`${API_URL}/api/chat/search`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ query: searchQuery, limit: 50 }),
      });

      if (response.ok) {
        const data = await response.json();
        setSearchResults(data.results || []);
      }
    } catch {
      toast.error("Erro ao pesquisar mensagens");
    } finally {
      setSearching(false);
    }
  };

  // Download de anexo
  const handleDownloadAttachment = (attachment) => {
    const link = document.createElement("a");
    link.href = `data:${attachment.content_type};base64,${attachment.data}`;
    link.download = attachment.filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Scroll para o fim das mensagens
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Carregar dados iniciais
  useEffect(() => {
    if (open) {
      fetchConversations();
      fetchUnreadCount();
      fetchGroups();
    }
  }, [open, fetchConversations, fetchUnreadCount, fetchGroups]);

  // Carregar utilizadores quando pesquisar
  useEffect(() => {
    if (showNewChat || showNewGroup) {
      fetchUsers();
    }
  }, [showNewChat, showNewGroup, fetchUsers]);

  // Limpar timeout de typing ao desmontar
  useEffect(() => {
    return () => {
      if (typingTimeoutRef.current) {
        clearTimeout(typingTimeoutRef.current);
      }
    };
  }, []);

  // Formatar data da mensagem
  const formatMessageDate = (dateStr) => {
    const date = parseISO(dateStr);
    if (isToday(date)) {
      return format(date, "HH:mm", { locale: pt });
    }
    if (isYesterday(date)) {
      return `Ontem ${format(date, "HH:mm", { locale: pt })}`;
    }
    return format(date, "d MMM HH:mm", { locale: pt });
  };

  // Obter iniciais do nome
  const getInitials = (name) => {
    return name
      ?.split(" ")
      .map((n) => n[0])
      .join("")
      .substring(0, 2)
      .toUpperCase() || "?";
  };

  // Obter ícone de ficheiro
  const getFileIcon = (contentType) => {
    if (contentType.startsWith("image/")) return ImageIcon;
    if (contentType === "application/pdf") return FileText;
    return File;
  };

  // Renderizar lista de conversas
  const renderConversationList = () => (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b flex items-center justify-between">
        <div className="flex items-center gap-2">
          <MessageSquare className="h-5 w-5 text-primary" />
          <h3 className="font-semibold">Chat Interno</h3>
          {unreadCount.total > 0 && (
            <Badge variant="destructive" className="h-5 px-1.5 text-xs">
              {unreadCount.total}
            </Badge>
          )}
        </div>
        <div className="flex gap-1">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setShowSearch(true)}
            title="Pesquisar mensagens"
          >
            <SearchIcon className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setShowNewGroup(true)}
            title="Criar grupo"
          >
            <Users className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowNewChat(true)}
          >
            <Plus className="h-4 w-4 mr-1" />
            Nova
          </Button>
        </div>
      </div>

      <ScrollArea className="flex-1">
        {conversations.length === 0 ? (
          <div className="p-8 text-center text-muted-foreground">
            <MessageSquare className="h-12 w-12 mx-auto mb-4 opacity-30" />
            <p>Sem conversas</p>
            <p className="text-sm mt-1">Clique em "Nova" para iniciar</p>
          </div>
        ) : (
          <div className="divide-y">
            {conversations.map((conv) => (
              <button
                type="button"
                key={conv.group_id || conv.user_id}
                className="w-full text-left p-3 hover:bg-accent/50 cursor-pointer transition-colors"
                onClick={() => fetchMessages(conv.group_id || conv.user_id, conv.is_group)}
              >
                <div className="flex items-center gap-3">
                  <div className="relative">
                    <Avatar className="h-10 w-10">
                      <AvatarFallback
                        className={`text-sm ${
                          conv.is_group
                            ? "bg-purple-100 text-purple-700"
                            : "bg-primary/10 text-primary"
                        }`}
                      >
                        {conv.is_group ? (
                          <Users className="h-5 w-5" />
                        ) : (
                          getInitials(conv.user_name)
                        )}
                      </AvatarFallback>
                    </Avatar>
                    {!conv.is_group && conv.is_online && (
                      <Circle className="absolute bottom-0 right-0 h-3 w-3 fill-green-500 text-green-500" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <p className="font-medium text-sm truncate">
                        {conv.is_group ? conv.group_name : conv.user_name}
                      </p>
                      <span className="text-xs text-muted-foreground">
                        {formatMessageDate(conv.last_message_time)}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <p className="text-xs text-muted-foreground truncate">
                        {conv.last_message}
                      </p>
                      {conv.unread_count > 0 && (
                        <Badge variant="destructive" className="h-4 px-1 text-[10px]">
                          {conv.unread_count}
                        </Badge>
                      )}
                    </div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}
      </ScrollArea>
    </div>
  );

  // Renderizar lista de utilizadores para nova conversa
  const renderUserList = () => (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b">
        <div className="flex items-center gap-2 mb-3">
          <Button variant="ghost" size="sm" onClick={() => setShowNewChat(false)}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <h3 className="font-semibold">Nova Conversa</h3>
        </div>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Pesquisar utilizador..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>

      <ScrollArea className="flex-1">
        <div className="divide-y">
          {allUsers.map((u) => (
            <button
              type="button"
              key={u.id}
              className="w-full text-left p-3 hover:bg-accent/50 cursor-pointer transition-colors"
              onClick={() => {
                setShowNewChat(false);
                setSearchQuery("");
                fetchMessages(u.id, false);
              }}
            >
              <div className="flex items-center gap-3">
                <div className="relative">
                  <Avatar className="h-10 w-10">
                    <AvatarFallback className="bg-primary/10 text-primary text-sm">
                      {getInitials(u.name)}
                    </AvatarFallback>
                  </Avatar>
                  {u.is_online && (
                    <Circle className="absolute bottom-0 right-0 h-3 w-3 fill-green-500 text-green-500" />
                  )}
                </div>
                <div>
                  <p className="font-medium text-sm">{u.name}</p>
                  <p className="text-xs text-muted-foreground">{u.role}</p>
                </div>
              </div>
            </button>
          ))}
        </div>
      </ScrollArea>
    </div>
  );

  // Renderizar criação de grupo
  const renderNewGroupForm = () => (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => {
            setShowNewGroup(false);
            setSelectedMembers([]);
            setNewGroupName("");
            setNewGroupDescription("");
          }}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <h3 className="font-semibold">Novo Grupo</h3>
        </div>
      </div>

      <ScrollArea className="flex-1 p-4 space-y-4">
        <div className="space-y-2">
          <Label>Nome do Grupo *</Label>
          <Input
            value={newGroupName}
            onChange={(e) => setNewGroupName(e.target.value)}
            placeholder="Nome do grupo..."
          />
        </div>

        <div className="space-y-2">
          <Label>Descrição</Label>
          <Textarea
            value={newGroupDescription}
            onChange={(e) => setNewGroupDescription(e.target.value)}
            placeholder="Descrição opcional..."
            rows={2}
          />
        </div>

        <div className="space-y-2">
          <Label>Membros ({selectedMembers.length} selecionados)</Label>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Pesquisar utilizador..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>
        </div>

        <div className="divide-y border rounded-lg">
          {allUsers
            .filter((u) => searchQuery || u.id !== user?.id)
            .map((u) => (
              <button
                type="button"
                key={u.id}
                className="w-full text-left p-3 hover:bg-accent/50 cursor-pointer transition-colors flex items-center gap-3"
                onClick={() => {
                  setSelectedMembers((prev) =>
                    prev.includes(u.id)
                      ? prev.filter((id) => id !== u.id)
                      : [...prev, u.id]
                  );
                }}
              >
                <div
                  className={`w-5 h-5 border rounded flex items-center justify-center ${
                    selectedMembers.includes(u.id)
                      ? "bg-primary border-primary text-primary-foreground"
                      : ""
                  }`}
                >
                  {selectedMembers.includes(u.id) && <Check className="h-3 w-3" />}
                </div>
                <Avatar className="h-8 w-8">
                  <AvatarFallback className="bg-primary/10 text-primary text-xs">
                    {getInitials(u.name)}
                  </AvatarFallback>
                </Avatar>
                <div>
                  <p className="text-sm font-medium">{u.name}</p>
                  <p className="text-xs text-muted-foreground">{u.role}</p>
                </div>
              </button>
            ))}
        </div>
      </ScrollArea>

      <div className="p-4 border-t">
        <Button
          className="w-full"
          onClick={handleCreateGroup}
          disabled={!newGroupName.trim()}
        >
          <Users className="h-4 w-4 mr-2" />
          Criar Grupo
        </Button>
      </div>
    </div>
  );

  // Renderizar pesquisa
  const renderSearch = () => (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b">
        <div className="flex items-center gap-2 mb-3">
          <Button variant="ghost" size="sm" onClick={() => {
            setShowSearch(false);
            setSearchResults([]);
            setSearchQuery("");
          }}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <h3 className="font-semibold">Pesquisar Mensagens</h3>
        </div>
        <div className="flex gap-2">
          <Input
            placeholder="Pesquisar..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          />
          <Button onClick={handleSearch} disabled={searching}>
            {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : <SearchIcon className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      <ScrollArea className="flex-1">
        {searchResults.length === 0 ? (
          <div className="p-8 text-center text-muted-foreground">
            <SearchIcon className="h-12 w-12 mx-auto mb-4 opacity-30" />
            <p>Pesquise mensagens por conteúdo</p>
          </div>
        ) : (
          <div className="divide-y">
            {searchResults.map((msg) => (
              <button
                type="button"
                key={msg.id}
                className="w-full text-left p-3 hover:bg-accent/50 cursor-pointer transition-colors"
                onClick={() => {
                  if (msg.group_id) {
                    fetchMessages(msg.group_id, true);
                  } else {
                    const otherId = msg.sender_id === user?.id ? msg.receiver_id : msg.sender_id;
                    fetchMessages(otherId, false);
                  }
                  setShowSearch(false);
                }}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-medium text-sm">{msg.sender_name}</span>
                  <span className="text-xs text-muted-foreground">
                    {formatMessageDate(msg.created_at)}
                  </span>
                  {msg.group_name && (
                    <Badge variant="outline" className="text-xs">
                      {msg.group_name}
                    </Badge>
                  )}
                </div>
                <p className="text-sm text-muted-foreground line-clamp-2">{msg.content}</p>
              </button>
            ))}
          </div>
        )}
      </ScrollArea>
    </div>
  );

  // Renderizar conversa
  const renderConversation = () => (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => {
            setSelectedConversation(null);
            setReplyTo(null);
            setMessages([]);
          }}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Avatar className="h-8 w-8">
            <AvatarFallback
              className={`text-xs ${
                selectedConversation?.isGroup
                  ? "bg-purple-100 text-purple-700"
                  : "bg-primary/10 text-primary"
              }`}
            >
              {selectedConversation?.isGroup ? (
                <Users className="h-4 w-4" />
              ) : (
                getInitials(selectedConversation?.name)
              )}
            </AvatarFallback>
          </Avatar>
          <div>
            <p className="font-medium text-sm">{selectedConversation?.name}</p>
            {selectedConversation?.isGroup && (
              <p className="text-xs text-muted-foreground">
                {selectedConversation.group?.members?.length || 0} membros
              </p>
            )}
            {typingUsers[selectedConversation?.id] && (
              <p className="text-xs text-primary animate-pulse">
                {typingUsers[selectedConversation.id]} a escrever...
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Messages */}
      <ScrollArea className="flex-1 p-4">
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="space-y-4">
            {messages.map((msg) => {
              const isOwn = msg.sender_id === user?.id;
              const reactions = msg.reactions || [];
              const hasAttachment = msg.attachments?.length > 0;

              return (
                <div key={msg.id} className={`flex ${isOwn ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[80%] ${isOwn ? "order-1" : "order-2"}`}>
                    {/* Reply to indicator */}
                    {msg.reply_to_data && (
                      <div
                        className={`text-xs p-2 rounded-t-lg border-b ${
                          isOwn
                            ? "bg-primary/80 text-primary-foreground/80 rounded-tl-lg"
                            : "bg-muted rounded-tr-lg"
                        }`}
                      >
                        <p className="font-medium">{msg.reply_to_data.sender_name}</p>
                        <p className="truncate opacity-70">{msg.reply_to_data.content}</p>
                      </div>
                    )}

                    {/* Message content */}
                    <div
                      className={`rounded-lg px-3 py-2 relative group ${
                        isOwn
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted"
                      } ${msg.reply_to_data ? (isOwn ? "rounded-tr-lg" : "rounded-tl-lg") : ""}`}
                    >
                      {/* Sender name for groups */}
                      {selectedConversation?.isGroup && !isOwn && (
                        <p className="text-xs font-medium text-primary mb-1">{msg.sender_name}</p>
                      )}

                      {/* Content */}
                      {editingMessage === msg.id ? (
                        <div className="flex gap-2">
                          <Input
                            value={editingMessage.content}
                            onChange={(e) =>
                              setEditingMessage({ ...editingMessage, content: e.target.value })
                            }
                            className="h-8 text-sm"
                          />
                          <Button
                            size="sm"
                            onClick={() => handleEditMessage(msg.id, editingMessage.content)}
                          >
                            <Check className="h-4 w-4" />
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setEditingMessage(null)}
                          >
                            <X className="h-4 w-4" />
                          </Button>
                        </div>
                      ) : (
                        <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                      )}

                      {/* Attachment */}
                      {hasAttachment && (
                        <div className="mt-2 space-y-2">
                          {msg.attachments.map((att, idx) => {
                            const FileIcon = getFileIcon(att.content_type);
                            return (
                              <div
                                key={idx}
                                className={`flex items-center gap-2 p-2 rounded ${
                                  isOwn ? "bg-primary-foreground/10" : "bg-background"
                                }`}
                              >
                                <FileIcon className="h-5 w-5" />
                                <span className="text-sm truncate flex-1">{att.filename}</span>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => handleDownloadAttachment(att)}
                                >
                                  <Download className="h-4 w-4" />
                                </Button>
                              </div>
                            );
                          })}
                        </div>
                      )}

                      {/* Edited indicator */}
                      {msg.edited && (
                        <span className="text-[10px] opacity-50 ml-2">(editado)</span>
                      )}

                      {/* Time */}
                      <p
                        className={`text-[10px] mt-1 ${
                          isOwn ? "text-primary-foreground/70" : "text-muted-foreground"
                        }`}
                      >
                        {formatMessageDate(msg.created_at)}
                      </p>

                      {/* Action buttons */}
                      <div
                        className={`absolute ${isOwn ? "left-0 -translate-x-full" : "right-0 translate-x-full"} top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity flex gap-1 px-1`}
                      >
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-6 w-6 p-0"
                          onClick={() => setReplyTo(msg)}
                        >
                          <Reply className="h-3 w-3" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-6 w-6 p-0"
                          onClick={() => setShowReactionsFor(msg.id)}
                        >
                          <Smile className="h-3 w-3" />
                        </Button>
                        {isOwn && (
                          <>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-6 w-6 p-0"
                              onClick={() => setEditingMessage({ id: msg.id, content: msg.content })}
                            >
                              <Edit2 className="h-3 w-3" />
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-6 w-6 p-0 text-destructive"
                              onClick={() => handleDeleteMessage(msg.id)}
                            >
                              <Trash2 className="h-3 w-3" />
                            </Button>
                          </>
                        )}
                      </div>

                      {/* Reactions popup */}
                      {showReactionsFor === msg.id && (
                        <div
                          className={`absolute ${isOwn ? "right-0" : "left-0"} bottom-full mb-1 bg-popover border rounded-lg p-1 flex gap-1 shadow-lg z-10`}
                        >
                          {QUICK_REACTIONS.map((emoji) => (
                            <button
                              type="button"
                              key={emoji}
                              className="hover:bg-accent rounded p-1 text-lg"
                              onClick={() => handleReaction(msg.id, emoji)}
                            >
                              {emoji}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Reactions display */}
                    {reactions.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1">
                        {Object.entries(
                          reactions.reduce((acc, r) => {
                            acc[r.reaction] = acc[r.reaction] || [];
                            acc[r.reaction].push(r);
                            return acc;
                          }, {})
                        ).map(([emoji, users]) => (
                          <button
                            type="button"
                            key={emoji}
                            className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-xs border ${
                              users.some((u) => u.user_id === user?.id)
                                ? "bg-primary/10 border-primary"
                                : "bg-muted border-transparent"
                            }`}
                            onClick={() => handleReaction(msg.id, emoji)}
                            title={users.map((u) => u.user_name).join(", ")}
                          >
                            <span>{emoji}</span>
                            <span>{users.length}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
            <div ref={messagesEndRef} />
          </div>
        )}
      </ScrollArea>

      {/* Reply to indicator */}
      {replyTo && (
        <div className="px-4 py-2 bg-muted/50 border-t flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm">
            <Reply className="h-4 w-4" />
            <span className="font-medium">{replyTo.sender_name}</span>
            <span className="text-muted-foreground truncate max-w-[200px]">
              {replyTo.content}
            </span>
          </div>
          <Button variant="ghost" size="sm" onClick={() => setReplyTo(null)}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      )}

      {/* Input */}
      <form onSubmit={handleSendMessage} className="p-4 border-t flex gap-2">
        <input
          type="file"
          ref={fileInputRef}
          className="hidden"
          onChange={handleFileUpload}
          accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.txt,.csv"
        />
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={() => fileInputRef.current?.click()}
          disabled={uploadingFile}
        >
          {uploadingFile ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Paperclip className="h-4 w-4" />
          )}
        </Button>
        <Input
          placeholder="Escrever mensagem..."
          value={newMessage}
          onChange={(e) => {
            setNewMessage(e.target.value);
            handleTyping();
          }}
          disabled={sendingMessage}
        />
        <Button
          type="submit"
          size="icon"
          disabled={!newMessage.trim() || sendingMessage}
        >
          {sendingMessage ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </Button>
      </form>
    </div>
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md h-[700px] p-0 flex flex-col">
        {showSearch ? (
          renderSearch()
        ) : showNewGroup ? (
          renderNewGroupForm()
        ) : showNewChat ? (
          renderUserList()
        ) : selectedConversation ? (
          renderConversation()
        ) : (
          renderConversationList()
        )}
      </DialogContent>
    </Dialog>
  );
};

export default ChatPanel;
