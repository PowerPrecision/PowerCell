/**
 * useSlidingSession — Hook de segurança para sessão do Portal do Cliente.
 *
 * Implementa o padrão "Sliding Expiration": a sessão do cliente não expira
 * enquanto ele estiver activo na página, mas expira automaticamente após
 * 15 minutos de inatividade. Isto evita que o cliente seja expulso enquanto
 * vai buscar documentos para fazer upload.
 *
 * Funcionalidades:
 * 1. Ouve eventos de interação (mousemove, keydown, click) e actualiza
 *    o localStorage.portalLastActivity com um throttle de 5 segundos.
 * 2. Verifica a cada minuto se a inatividade ultrapassa 15 minutos.
 *    Se sim, faz logout automático (limpa storage, mostra toast, redireciona).
 * 3. No beforeunload (fechar aba/janela), limpa imediatamente o localStorage
 *    para obrigar a novo login na próxima visita.
 *
 * Uso:
 *   const { logout } = useSlidingSession({ onExpired: () => setIsVerified(false) });
 *
 * Parâmetros:
 *   - onExpired: callback chamado quando a sessão expira por inatividade
 *   - inactivityMs: tempo de inatividade antes de expirar (default: 15 * 60 * 1000 = 15 min)
 *   - checkIntervalMs: intervalo de verificação (default: 60 * 1000 = 1 min)
 *   - throttleMs: throttle para actualizar última actividade (default: 5000 = 5 seg)
 */
import { useEffect, useCallback, useRef } from 'react';
import { toast } from 'sonner';

// Chaves usadas no localStorage para a sessão do portal
const PORTAL_STORAGE_KEYS = [
  'portalToken',
  'portalClientId',
  'portalClientName',
  'portalProcessId',
  'portalAuthMethod',
  'portalLastActivity',
  // Chaves legadas (para limpeza completa)
  'portal_token',
  'portal_verified',
  'portal_client_id',
  'portal_client_name',
  'portal_process_id',
];

// Chaves no sessionStorage (legado OTP)
const PORTAL_SESSION_KEYS = [
  'portalToken',
  'portalClientId',
  'portalAuthMethod',
  'portalVerified',
];

export default function useSlidingSession({
  onExpired,
  inactivityMs = 15 * 60 * 1000,  // 15 minutos
  checkIntervalMs = 60 * 1000,      // 1 minuto
  throttleMs = 5000,                // 5 segundos de throttle
} = {}) {
  const lastUpdateRef = useRef(0);
  const onExpiredRef = useRef(onExpired);

  // Manter a referência do callback actualizada
  useEffect(() => {
    onExpiredRef.current = onExpired;
  }, [onExpired]);

  // ── Função de logout ──
  const logout = useCallback((showMessage = false) => {
    // Limpar localStorage
    PORTAL_STORAGE_KEYS.forEach(key => {
      try { localStorage.removeItem(key); } catch { /* private mode / quota */ }
    });
    // Limpar sessionStorage
    PORTAL_SESSION_KEYS.forEach(key => {
      try { sessionStorage.removeItem(key); } catch { /* private mode / quota */ }
    });

    if (showMessage) {
      toast.error('Sessão expirada por inatividade', {
        description: 'Faça login novamente para continuar.',
        duration: 6000,
      });
    }

    // Chamar callback de expiração
    if (onExpiredRef.current) {
      onExpiredRef.current();
    }
  }, []);

  // ── 1. Ouvir eventos de interação e actualizar última actividade ──
  useEffect(() => {
    const updateActivity = () => {
      const now = Date.now();
      // Throttle: só actualizar se passaram mais de throttleMs desde a última
      if (now - lastUpdateRef.current < throttleMs) return;
      lastUpdateRef.current = now;
      try {
        localStorage.setItem('portalLastActivity', String(now));
      } catch { /* private mode / quota */ }
    };

    // Eventos que indicam actividade do utilizador
    const events = ['mousemove', 'keydown', 'click', 'touchstart', 'scroll'];
    events.forEach(event => {
      window.addEventListener(event, updateActivity, { passive: true });
    });

    return () => {
      events.forEach(event => {
        window.removeEventListener(event, updateActivity);
      });
    };
  }, [throttleMs]);

  // ── 2. Verificar inactividade a cada minuto ──
  useEffect(() => {
    const checkInactivity = () => {
      const token = localStorage.getItem('portalToken') || sessionStorage.getItem('portalToken');
      if (!token) return; // Não há sessão — não verificar

      const lastActivity = localStorage.getItem('portalLastActivity');
      if (!lastActivity) {
        // Sem registo de actividade — provavelmente sessão antiga, inicializar
        localStorage.setItem('portalLastActivity', String(Date.now()));
        return;
      }

      const elapsed = Date.now() - parseInt(lastActivity, 10);
      if (elapsed > inactivityMs) {
        // Sessão expirou por inactividade — fazer logout
        logout(true); // true = mostrar toast
      }
    };

    // Verificação imediata (caso reabra uma aba com sessão antiga)
    checkInactivity();

    // Verificação periódica
    const interval = setInterval(checkInactivity, checkIntervalMs);

    return () => clearInterval(interval);
  }, [inactivityMs, checkIntervalMs, logout]);

  // ── 3. Limpar storage ao fechar a aba/janela ──
  useEffect(() => {
    const handleUnload = () => {
      // Limpar tudo imediatamente — obrigar novo login na próxima visita
      PORTAL_STORAGE_KEYS.forEach(key => {
        try { localStorage.removeItem(key); } catch { /* private mode / quota */ }
      });
      PORTAL_SESSION_KEYS.forEach(key => {
        try { sessionStorage.removeItem(key); } catch { /* private mode / quota */ }
      });
    };

    window.addEventListener('beforeunload', handleUnload);

    return () => {
      window.removeEventListener('beforeunload', handleUnload);
    };
  }, []);

  return { logout };
}
