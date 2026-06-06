import React, { useState, useEffect, useRef, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Textarea } from "../components/ui/textarea";
import { Avatar, AvatarFallback } from "../components/ui/avatar";
import { ScrollArea } from "../components/ui/scroll-area";
import { Skeleton } from "../components/ui/skeleton";
import { Separator } from "../components/ui/separator";
import { Badge } from "../components/ui/badge";
import { useAuth } from "../contexts/AuthContext";
import { getAnnouncements, createAnnouncement } from "../services/api";
import { Megaphone, Send, Loader2, MessageSquare, AlertCircle } from "lucide-react";
import { isToday, isYesterday, format, parseISO } from "date-fns";
import { pt } from "date-fns/locale";
import { toast } from "sonner";
import { safeDateStr, safeParseISO } from "../lib/utils";

// ── Helper Functions ──────────────────────────────────────────────

const getInitials = (name) =>
  name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

const getAvatarColor = (name) => {
  const colors = [
    "bg-amber-500",
    "bg-emerald-500",
    "bg-rose-500",
    "bg-violet-500",
    "bg-cyan-500",
    "bg-orange-500",
    "bg-teal-500",
    "bg-pink-500",
  ];
  let hash = 0;
  for (let i = 0; i < name.length; i++)
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return colors[Math.abs(hash) % colors.length];
};

const formatDate = (dateStr) => {
  const date = safeParseISO(dateStr);
  if (!date || isNaN(date.getTime())) return "—";
  if (isToday(date)) return `Hoje às ${format(date, "HH:mm")}`;
  if (isYesterday(date)) return `Ontem às ${format(date, "HH:mm")}`;
  return format(date, "d MMM, HH:mm", { locale: pt });
};

const formatRole = (role) => {
  const map = {
    admin: "Admin",
    ceo: "CEO",
    diretor: "Diretor",
    consultor: "Consultor",
    intermediario: "Intermediário",
    indexacao: "Indexação",
    administrativo: "Administrativo",
    cliente: "Cliente",
  };
  return map[role] || role;
};

// ── Loading Skeleton ──────────────────────────────────────────────

const FeedSkeleton = () => (
  <div className="space-y-4 p-4">
    {Array.from({ length: 4 }).map((_, i) => (
      <div key={i} className="flex gap-3">
        <Skeleton className="h-9 w-9 rounded-full shrink-0" />
        <div className="flex-1 space-y-2">
          <div className="flex items-center gap-2">
            <Skeleton className="h-4 w-28" />
            <Skeleton className="h-3 w-16 rounded-full" />
          </div>
          <Skeleton className="h-3 w-20" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
        </div>
      </div>
    ))}
  </div>
);

// ── Main Component ────────────────────────────────────────────────

const TeamFeed = () => {
  const { user } = useAuth();
  const [announcements, setAnnouncements] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [content, setContent] = useState("");
  const [posting, setPosting] = useState(false);
  const scrollRef = useRef(null);
  const textareaRef = useRef(null);

  const MAX_CHARS = 2000;

  const fetchAnnouncements = useCallback(async () => {
    try {
      setLoading(true);
      setError(false);
      const res = await getAnnouncements();
      const data = res.data;
      setAnnouncements(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error("Erro ao carregar mural:", err);
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAnnouncements();
  }, [fetchAnnouncements]);

  // Scroll to bottom on load and new messages
  useEffect(() => {
    if (!loading && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [announcements, loading]);

  const handlePost = async () => {
    const trimmed = content.trim();
    if (!trimmed || trimmed.length === 0) return;
    if (trimmed.length > MAX_CHARS) return;

    try {
      setPosting(true);
      await createAnnouncement(trimmed);
      setContent("");
      await fetchAnnouncements();
      toast.success("Mensagem publicada no mural");
      textareaRef.current?.focus();
    } catch (err) {
      console.error("Erro ao publicar:", err);
      toast.error("Erro ao publicar mensagem");
    } finally {
      setPosting(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      handlePost();
    }
  };

  return (
    <Card className="h-full flex flex-col border-border">
      {/* ── Header ─────────────────────────────────────────── */}
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <Megaphone className="h-5 w-5 text-amber-600" />
          📢 Mural da Equipa
        </CardTitle>
        <p className="text-xs text-muted-foreground mt-0.5">
          Informações gerais para toda a equipa
        </p>
      </CardHeader>

      {/* ── Input Area ─────────────────────────────────────── */}
      <div className="px-4 pb-3">
        <div className="relative">
          <Textarea
            ref={textareaRef}
            rows={3}
            value={content}
            onChange={(e) => {
              if (e.target.value.length <= MAX_CHARS) setContent(e.target.value);
            }}
            onKeyDown={handleKeyDown}
            placeholder="Escreve uma mensagem para a equipa..."
            className="resize-none pr-12 text-sm"
            disabled={posting}
          />
          <Button
            size="icon"
            className="absolute bottom-2 right-2 h-8 w-8 rounded-full"
            onClick={handlePost}
            disabled={
              posting ||
              !content.trim() ||
              content.trim().length === 0
            }
            aria-label="Enviar mensagem"
          >
            {posting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>
        <div className="flex items-center justify-between mt-1.5">
          <span className="text-[11px] text-muted-foreground">
            Ctrl+Enter para enviar
          </span>
          <span
            className={`text-[11px] ${
              content.length > MAX_CHARS * 0.9
                ? "text-red-500 font-medium"
                : "text-muted-foreground"
            }`}
          >
            {content.length}/{MAX_CHARS}
          </span>
        </div>
      </div>

      <Separator />

      {/* ── Feed Area ──────────────────────────────────────── */}
      <div className="flex-1 min-h-0">
        {loading ? (
          <FeedSkeleton />
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-full py-12 px-4 text-center">
            <AlertCircle className="h-10 w-10 text-muted-foreground mb-3" />
            <p className="text-sm text-muted-foreground mb-3">
              Não foi possível carregar o mural.
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={fetchAnnouncements}
              className="gap-1.5"
            >
              <Loader2 className="h-3.5 w-3.5" />
              Tentar novamente
            </Button>
          </div>
        ) : announcements.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full py-12 px-4 text-center">
            <MessageSquare className="h-10 w-10 text-muted-foreground/50 mb-3" />
            <p className="text-sm text-muted-foreground">
              Nenhuma mensagem ainda.
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              Sê o primeiro a partilhar algo com a equipa!
            </p>
          </div>
        ) : (
          <ScrollArea className="max-h-[500px] overflow-y-auto" ref={scrollRef}>
            <div className="divide-y divide-border/50">
              {announcements.map((announcement) => {
                const isOwn =
                  user && user.id === announcement.author_id;
                return (
                  <div
                    key={announcement.id}
                    className={`p-4 transition-colors ${
                      isOwn
                        ? "bg-amber-50 dark:bg-amber-950/20"
                        : "hover:bg-muted/50"
                    }`}
                  >
                    <div className="flex gap-3">
                      {/* Avatar */}
                      <Avatar className="h-9 w-9 shrink-0">
                        <AvatarFallback
                          className={`${getAvatarColor(
                            announcement.author_name || "U"
                          )} text-white text-xs font-medium`}
                        >
                          {getInitials(announcement.author_name || "U")}
                        </AvatarFallback>
                      </Avatar>

                      {/* Content */}
                      <div className="flex-1 min-w-0">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="text-sm font-semibold text-foreground">
                            {announcement.author_name || "Utilizador"}
                          </span>
                          {isOwn && (
                            <Badge
                              variant="secondary"
                              className="text-[10px] px-1.5 py-0 h-4 font-medium bg-amber-200 text-amber-800 dark:bg-amber-800 dark:text-amber-200"
                            >
                              Tu
                            </Badge>
                          )}
                          {announcement.author_role && (
                            <Badge
                              variant="outline"
                              className="text-[10px] px-1.5 py-0 h-4 font-normal"
                            >
                              {formatRole(announcement.author_role)}
                            </Badge>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {formatDate(announcement.created_at)}
                        </p>
                        <p className="text-sm text-foreground/90 mt-1.5 whitespace-pre-wrap break-words leading-relaxed">
                          {announcement.content}
                        </p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </ScrollArea>
        )}
      </div>

      {/* ── Footer ─────────────────────────────────────────── */}
      {!loading && !error && announcements.length > 0 && (
        <>
          <Separator />
          <div className="px-4 py-2">
            <p className="text-[11px] text-muted-foreground text-center">
              {announcements.length} mensagem
              {announcements.length !== 1 ? "s" : ""} no mural
            </p>
          </div>
        </>
      )}
    </Card>
  );
};

export default TeamFeed;
