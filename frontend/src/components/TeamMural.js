/**
 * TeamMural — Componente Mural da Equipa (Feed Interno)
 *
 * PORQUÊ: Permite comunicação assíncrona entre membros da equipa.
 * Qualquer utilizador autenticado pode publicar mensagens visíveis a toda a equipa.
 *
 * FUNCIONALIDADES:
 * - Publicar mensagens com auto-refetch
 * - Dar "Gosto" (Like) com toggle (coração vermelho quando ativo)
 * - Indicador de leitura com tooltip de nomes
 * - Auto-read: após 2s de visibilidade, marca como lido automaticamente
 * - Destaque visual para mensagens não lidas (borda azul + ponto)
 * - Diferenciação visual entre mensagens próprias e dos outros
 */
import React, { useState, useEffect, useRef, useCallback } from "react";
import { useAuth } from "../contexts/AuthContext";
import {
  getAnnouncements,
  createAnnouncement,
  deleteAnnouncement,
  toggleAnnouncementLike,
  markAnnouncementRead,
  getAnnouncementReaders,
} from "../services/api";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Textarea } from "../components/ui/textarea";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../components/ui/tooltip";
import { Loader2, Send, Heart, Eye, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { formatDistanceToNow, parseISO } from "date-fns";
import { pt } from "date-fns/locale";

// ============== HOOK: useIntersectionObserver (Auto-Read) ==============
/**
 * Hook que detecta quando um elemento é visível no viewport.
 * Retorna uma ref para attaching ao elemento e o estado de visibilidade.
 * Após 2 segundos consecutivos de visibilidade, executa o callback.
 */
function useAutoRead(onRead) {
  const elementRef = useRef(null);
  const timerRef = useRef(null);
  const hasRead = useRef(false);

  useEffect(() => {
    const element = elementRef.current;
    if (!element || hasRead.current) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          // Elemento visível — iniciar timer de 2s
          if (!timerRef.current) {
            timerRef.current = setTimeout(() => {
              if (!hasRead.current) {
                hasRead.current = true;
                onRead();
              }
              timerRef.current = null;
              observer.unobserve(element);
            }, 2000);
          }
        } else {
          // Elemento saiu do viewport — cancelar timer
          if (timerRef.current) {
            clearTimeout(timerRef.current);
            timerRef.current = null;
          }
        }
      },
      { threshold: 0.3 } // 30% do elemento deve estar visível
    );

    observer.observe(element);
    return () => {
      observer.disconnect();
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, [onRead]);

  return elementRef;
}

// ============== COMPONENTE: AnnouncementItem ==============
/**
 * Renderiza uma mensagem individual do mural com:
 * - Conteúdo com preservação de line breaks
 * - Nome do autor em bold, data formatada
 * - Botão de like (coração toggle)
 * - Indicador de leitura com tooltip
 * - Destaque visual para não lidas
 * - Botão de eliminar (apenas para autor ou admin)
 */
const AnnouncementItem = React.memo(({ announcement, currentUser, onLike, onDelete }) => {
  const isOwn = currentUser?.id === announcement.author_id;
  const hasLiked = announcement.likes?.includes(currentUser?.id) || false;
  const isUnread = !announcement.read_by?.includes(currentUser?.id);
  const likeCount = announcement.likes?.length || 0;
  const readCount = announcement.read_by?.length || 0;

  const [readers, setReaders] = useState([]);
  const [loadingReaders, setLoadingReaders] = useState(false);

  // Auto-read: marca como lido após 2s de visibilidade
  const handleAutoRead = useCallback(() => {
    if (isUnread) {
      markAnnouncementRead(announcement.id).catch(() => {});
    }
  }, [announcement.id, isUnread]);

  const readRef = useAutoRead(handleAutoRead);

  // Carregar nomes dos leitores ao hover
  const handleMouseEnterReaders = async () => {
    if (readCount === 0 || readers.length > 0) return;
    setLoadingReaders(true);
    try {
      const res = await getAnnouncementReaders(announcement.id);
      setReaders(res.data.readers || []);
    } catch {
      // Silencioso
    } finally {
      setLoadingReaders(false);
    }
  };

  const handleLike = (e) => {
    e.stopPropagation();
    onLike(announcement.id);
  };

  const handleDelete = (e) => {
    e.stopPropagation();
    if (window.confirm("Eliminar esta mensagem?")) {
      onDelete(announcement.id);
    }
  };

  const formattedDate = (() => {
    try {
      return formatDistanceToNow(parseISO(announcement.created_at), {
        addSuffix: true,
        locale: pt,
      });
    } catch {
      return "";
    }
  })();

  return (
    <div
      ref={readRef}
      className={`group relative rounded-lg p-4 transition-all ${
        isOwn
          ? "bg-blue-50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-800"
          : "bg-muted/30 border border-border"
      } ${isUnread ? "ring-2 ring-blue-400 dark:ring-blue-500 ring-offset-1" : ""}`}
    >
      {/* Indicador de não lido - ponto azul */}
      {isUnread && (
        <div className="absolute -top-1 -left-1 w-2.5 h-2.5 bg-blue-500 rounded-full animate-pulse" />
      )}

      {/* Header: Autor + Data + Acções */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <div
            className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${
              isOwn
                ? "bg-blue-600 text-white"
                : "bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-200"
            }`}
          >
            {announcement.author_name?.charAt(0)?.toUpperCase() || "?"}
          </div>
          <div className="min-w-0">
            <span className="font-semibold text-sm">{announcement.author_name}</span>
            {isOwn && (
              <span className="ml-2 text-xs text-muted-foreground">(eu)</span>
            )}
            <span className="ml-2 text-xs text-muted-foreground">{formattedDate}</span>
          </div>
        </div>

        {/* Botão eliminar (apenas autor ou admin) */}
        {(isOwn || currentUser?.role === "admin") && (
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-red-500"
            onClick={handleDelete}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>

      {/* Conteúdo da mensagem */}
      <div className="text-sm whitespace-pre-wrap break-words leading-relaxed ml-9">
        {announcement.content}
      </div>

      {/* Barra de ferramentas: Likes + Leituras */}
      <div className="flex items-center gap-4 mt-3 ml-9">
        {/* Botão Like */}
        <button
          onClick={handleLike}
          className={`flex items-center gap-1.5 text-xs transition-colors ${
            hasLiked
              ? "text-red-500 hover:text-red-600"
              : "text-muted-foreground hover:text-red-400"
          }`}
        >
          <Heart
            className={`h-4 w-4 ${hasLiked ? "fill-current" : ""}`}
          />
          {likeCount > 0 && <span>{likeCount}</span>}
        </button>

        {/* Indicador de leitura */}
        <TooltipProvider delayDuration={300}>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onMouseEnter={handleMouseEnterReaders}
                className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-green-500 transition-colors"
              >
                <Eye className="h-4 w-4" />
                {readCount > 0 && <span>{readCount}</span>}
              </button>
            </TooltipTrigger>
            <TooltipContent side="top" className="max-w-[250px]">
              {loadingReaders ? (
                <span className="text-xs">A carregar...</span>
              ) : readers.length > 0 ? (
                <div className="text-xs">
                  <p className="font-semibold mb-1">Lido por:</p>
                  <ul className="space-y-0.5 max-h-40 overflow-y-auto">
                    {readers.map((name, i) => (
                      <li key={i}>{name}</li>
                    ))}
                  </ul>
                </div>
              ) : (
                <span className="text-xs">Ainda ninguém leu</span>
              )}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>
    </div>
  );
});

AnnouncementItem.displayName = "AnnouncementItem";

// ============== COMPONENTE PRINCIPAL: TeamMural ==============
const TeamMural = () => {
  const { user } = useAuth();
  const [announcements, setAnnouncements] = useState([]);
  const [loading, setLoading] = useState(true);
  const [publishing, setPublishing] = useState(false);
  const [newMessage, setNewMessage] = useState("");
  const textareaRef = useRef(null);
  const feedRef = useRef(null);

  // Carregar anúncios
  const fetchAnnouncements = useCallback(async () => {
    try {
      setLoading(true);
      const res = await getAnnouncements(50);
      setAnnouncements(res.data || []);
    } catch (error) {
      console.error("Error fetching announcements:", error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAnnouncements();
  }, [fetchAnnouncements]);

  // Publicar nova mensagem
  const handlePublish = async () => {
    const content = newMessage.trim();
    if (!content) return;

    setPublishing(true);
    try {
      await createAnnouncement({ content });
      setNewMessage("");
      toast.success("Mensagem publicada!");
      fetchAnnouncements();
    } catch (error) {
      toast.error("Erro ao publicar mensagem");
    } finally {
      setPublishing(false);
      if (textareaRef.current) {
        textareaRef.current.focus();
      }
    }
  };

  // Toggle like
  const handleLike = async (announcementId) => {
    try {
      const res = await toggleAnnouncementLike(announcementId);
      // Atualizar estado local optimistically
      setAnnouncements((prev) =>
        prev.map((a) => (a.id === announcementId ? res.data : a))
      );
    } catch {
      toast.error("Erro ao dar gosto");
    }
  };

  // Eliminar mensagem
  const handleDelete = async (announcementId) => {
    try {
      await deleteAnnouncement(announcementId);
      setAnnouncements((prev) => prev.filter((a) => a.id !== announcementId));
      toast.success("Mensagem eliminada");
    } catch {
      toast.error("Erro ao eliminar mensagem");
    }
  };

  // Ctrl+Enter para publicar
  const handleKeyDown = (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      handlePublish();
    }
  };

  return (
    <Card className="border-border">
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <span className="text-lg">📢</span>
          Mural da Equipa
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Formulário de publicação */}
        <div className="space-y-2">
          <Textarea
            ref={textareaRef}
            value={newMessage}
            onChange={(e) => setNewMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Escreva uma mensagem para a equipa..."
            className="min-h-[80px] resize-none"
            maxLength={2000}
          />
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">
              {newMessage.length}/2000 · Ctrl+Enter para publicar
            </span>
            <Button
              size="sm"
              onClick={handlePublish}
              disabled={publishing || !newMessage.trim()}
              className="bg-teal-600 hover:bg-teal-700"
            >
              {publishing ? (
                <Loader2 className="h-4 w-4 animate-spin mr-1" />
              ) : (
                <Send className="h-4 w-4 mr-1" />
              )}
              Publicar
            </Button>
          </div>
        </div>

        {/* Separador */}
        <div className="border-t" />

        {/* Feed de mensagens */}
        <div ref={feedRef} className="space-y-3 max-h-[500px] overflow-y-auto pr-1 custom-scrollbar">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : announcements.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <span className="text-3xl mb-3 block">📋</span>
              <p className="text-sm">Nenhuma mensagem ainda.</p>
              <p className="text-xs mt-1">Seja o primeiro a publicar!</p>
            </div>
          ) : (
            announcements.map((announcement) => (
              <AnnouncementItem
                key={announcement.id}
                announcement={announcement}
                currentUser={user}
                onLike={handleLike}
                onDelete={handleDelete}
              />
            ))
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default TeamMural;
