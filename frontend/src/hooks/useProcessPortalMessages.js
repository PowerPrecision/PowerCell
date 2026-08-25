/**
 * Hook de mensagens do Portal (cliente ↔ staff) para um processo.
 *
 * Mantém polling de unread e lista de mensagens ao nível da página
 * (o badge do tab precisa de unread mesmo com o tab inactivo).
 */
import { useState, useEffect, useCallback, useRef } from "react";
import { useAuth } from "../contexts/AuthContext";
import { toast } from "sonner";

const API_URL = process.env.REACT_APP_BACKEND_URL || "";

export function useProcessPortalMessages(processId, { isActive = false } = {}) {
  const { token } = useAuth();
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [newMessage, setNewMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const unreadAvailableRef = useRef(true);

  const fetchMessages = useCallback(async () => {
    if (!processId) return;
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/processes/${processId}/portal-messages`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        // Backend returns { messages: [...], total: N, process_id: "..." }
        const msgs = Array.isArray(data) ? data : (data.messages || []);
        setMessages(msgs);
      } else if (response.status === 404) {
        // Portal inativo / sem mensagens ainda — estado neutro, sem erro na UI.
        setMessages([]);
      } else {
        console.error(`[PortalMessages] API returned ${response.status}`);
      }
    } catch {
      // Falha de rede ao carregar mensagens do portal — falha silenciosa,
      // mantém a lista atual em vez de quebrar a UI.
      setMessages((prev) => prev || []);
    } finally {
      setLoading(false);
    }
  }, [processId, token]);

  const fetchUnreadCount = useCallback(async () => {
    if (!processId || !token) return;
    try {
      const response = await fetch(
        `${API_URL}/api/processes/${processId}/portal-messages/unread`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (response.ok) {
        const data = await response.json();
        setUnreadCount(data.unread_count || 0);
      } else if (response.status === 404 || response.status === 401 || response.status === 403) {
        // Desativar polling para evitar loop de 404s / auth
        setUnreadCount(0);
        return "ENDPOINT_NOT_AVAILABLE";
      }
    } catch {
      // Silent — erro de rede, tentará novamente no próximo intervalo
    }
  }, [processId, token]);

  const refresh = useCallback(() => {
    fetchMessages();
    fetchUnreadCount();
  }, [fetchMessages, fetchUnreadCount]);

  const sendMessage = useCallback(async () => {
    if (!newMessage.trim() || !processId) return;
    setSending(true);
    try {
      const response = await fetch(`${API_URL}/api/processes/${processId}/portal-messages`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ content: newMessage.trim() }),
      });
      if (response.ok) {
        setNewMessage("");
        fetchMessages();
        toast.success("Mensagem enviada");
      } else {
        toast.error("Erro ao enviar mensagem");
      }
    } catch {
      toast.error("Erro ao enviar mensagem");
    } finally {
      setSending(false);
    }
  }, [processId, token, newMessage, fetchMessages]);

  // Buscar mensagens e unread quando o tab fica activo
  useEffect(() => {
    if (isActive) {
      fetchMessages();
      fetchUnreadCount();
    }
  }, [isActive, fetchMessages, fetchUnreadCount]);

  // Polling unread a cada 30s (desliga em 404/401/403)
  useEffect(() => {
    unreadAvailableRef.current = true;
    if (!processId || !token) return undefined;

    const interval = setInterval(async () => {
      if (!unreadAvailableRef.current) {
        clearInterval(interval);
        return;
      }
      const result = await fetchUnreadCount();
      if (result === "ENDPOINT_NOT_AVAILABLE") {
        unreadAvailableRef.current = false;
        clearInterval(interval);
      }
    }, 30000);

    fetchUnreadCount().then((result) => {
      if (result === "ENDPOINT_NOT_AVAILABLE") {
        unreadAvailableRef.current = false;
        clearInterval(interval);
      }
    });

    return () => clearInterval(interval);
  }, [fetchUnreadCount, processId, token]);

  return {
    messages,
    loading,
    newMessage,
    setNewMessage,
    sending,
    unreadCount,
    fetchMessages,
    sendMessage,
    refresh,
  };
}
