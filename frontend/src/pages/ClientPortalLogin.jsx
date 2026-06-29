/**
 * ClientPortalLogin — Ecrã de Login do Portal do Cliente (Email + Código de Acesso).
 *
 * Fluxo de autenticação:
 *   O utilizador insere o seu Email e o Código de Acesso fixo (formato XXX-XXX)
 *   que foi gerado automaticamente quando o seu registo foi criado.
 *   POST /portal/auth/login → recebe token JWT + client_id
 *
 * O token devolvido é guardado em localStorage (portalToken) para persistir
 * entre reloads (dentro do prazo de 15 min de inatividade).
 * A última actividade é registada em localStorage (portalLastActivity).
 */
import React, { useState, useCallback, useEffect } from 'react';
import { toast } from 'sonner';
import {
  Shield,
  Loader2,
  AlertCircle,
  Mail,
  KeyRound,
  LogIn,
  Lock,
} from 'lucide-react';

const BACKEND_URL = (process.env.REACT_APP_BACKEND_URL || 'https://powercell.onrender.com') + '/api';

// ====================================================================
// FETCH WITH RETRY — handles Render cold starts (503) automatically
// ====================================================================
const FETCH_RETRY_DELAYS = [3000, 6000];
const MAX_RETRIES = FETCH_RETRY_DELAYS.length;

async function fetchWithRetry(url, options = {}, retries = MAX_RETRIES) {
  let lastError = null;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const res = await fetch(url, options);
      if (res.status === 503 && attempt < retries) {
        const contentType = res.headers.get('content-type') || '';
        if (contentType.includes('application/json')) return res;
        await new Promise((r) => setTimeout(r, FETCH_RETRY_DELAYS[attempt]));
        continue;
      }
      return res;
    } catch (err) {
      lastError = err;
      if (attempt < retries) {
        await new Promise((r) => setTimeout(r, FETCH_RETRY_DELAYS[attempt]));
        continue;
      }
    }
  }
  throw lastError || new Error('Erro de ligação após várias tentativas.');
}

// ====================================================================
// CLIENT-ONLY WRAPPER — prevents hydration mismatches
// ====================================================================
function ClientOnly({ children, fallback = null }) {
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => { setMounted(true); }, []);
  return mounted ? children : fallback;
}

// ====================================================================
// MAIN LOGIN COMPONENT
// ====================================================================
export default function ClientPortalLogin({ onLoginSuccess }) {
  // ── State ──
  const [email, setEmail] = useState('');
  const [accessCode, setAccessCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  // ── Lockout state (countdown quando a conta está bloqueada por 429) ──
  const [lockoutSeconds, setLockoutSeconds] = useState(0);

  // ── Countdown do lockout — decrementa a cada segundo até 0 ──
  useEffect(() => {
    if (lockoutSeconds <= 0) return;
    const timer = setInterval(() => {
      setLockoutSeconds((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          // Limpar erro quando o lockout expira
          setError(null);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [lockoutSeconds]);

  // ── Helper: formatar segundos como "Xm Ys" ──
  const formatCountdown = useCallback((totalSeconds) => {
    const m = Math.floor(totalSeconds / 60);
    const s = totalSeconds % 60;
    if (m > 0) return `${m}m ${s.toString().padStart(2, '0')}s`;
    return `${s}s`;
  }, []);

  // ── Formatar código de acesso enquanto o utilizador digita ──
  const handleAccessCodeChange = useCallback((raw) => {
    // Permitir apenas letras e dígitos
    let clean = raw.replace(/[^A-Za-z0-9]/g, '').toUpperCase();
    // Limitar a 6 caracteres
    clean = clean.slice(0, 6);
    // Inserir hífen após 3 caracteres (visual: XXX-XXX)
    if (clean.length > 3) {
      clean = clean.slice(0, 3) + '-' + clean.slice(3);
    }
    setAccessCode(clean);
  }, []);

  // ── Submeter login ──
  const handleLogin = useCallback(async (e) => {
    e?.preventDefault();
    setError(null);

    // Validações locais
    const cleanEmail = email.trim().toLowerCase();
    if (!cleanEmail || !cleanEmail.includes('@')) {
      setError('Introduza um email válido.');
      return;
    }

    // Remover hífen para enviar ao backend (A4B-9X2 → A4B9X2)
    const cleanCode = accessCode.replace(/[^A-Za-z0-9]/g, '').toUpperCase();
    if (cleanCode.length !== 6) {
      setError('O código de acesso deve conter 6 caracteres.');
      return;
    }

    setLoading(true);
    try {
      const res = await fetchWithRetry(`${BACKEND_URL}/portal/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: cleanEmail,
          access_code: cleanCode,
        }),
      });

      let data;
      try {
        data = await res.json();
      } catch {
        if (res.status === 503) {
          setError('O servidor está a iniciar. Aguarde uns segundos e tente novamente.');
          return;
        }
        setError('Erro inesperado. Tente novamente.');
        return;
      }

      if (res.ok && data.token) {
        // ── Sucesso! Guardar token e actividade em localStorage ──
        localStorage.setItem('portalToken', data.token);
        localStorage.setItem('portalClientId', data.client_id || '');
        localStorage.setItem('portalClientName', data.client_name || '');
        localStorage.setItem('portalProcessId', data.process_id || '');
        localStorage.setItem('portalAuthMethod', 'access_code');
        localStorage.setItem('portalLastActivity', String(Date.now()));

        // Limpar sessionStorage legado (modelo antigo OTP)
        sessionStorage.removeItem('portalToken');
        sessionStorage.removeItem('portalClientId');
        sessionStorage.removeItem('portalAuthMethod');
        sessionStorage.removeItem('portalVerified');

        toast.success(`Bem-vindo, ${data.client_name || 'Cliente'}!`);

        if (onLoginSuccess) {
          onLoginSuccess(data.token);
        }
      } else if (res.status === 429) {
        // Rate limited / lockout — muitas tentativas falhadas.
        // O backend devolve detail como objecto com retry_after (segundos)
        // ou como string (rate limit global do middleware).
        let message = 'Muitas tentativas falhadas. Tente novamente mais tarde.';
        let retryAfter = 0;
        if (data.detail && typeof data.detail === 'object') {
          message = data.detail.message || data.detail.error || message;
          retryAfter = data.detail.retry_after || 0;
        } else if (typeof data.detail === 'string') {
          message = data.detail;
          // Tentar extrair minutos da mensagem (ex: "...em 9 minutos")
          const minMatch = data.detail.match(/(\d+)\s*min/i);
          if (minMatch) retryAfter = parseInt(minMatch[1], 10) * 60;
        }
        setError(message);
        if (retryAfter > 0) {
          setLockoutSeconds(retryAfter);
        }
      } else if (res.status === 401) {
        // Credenciais inválidas
        setError(typeof data.detail === 'string' ? data.detail : 'Credenciais inválidas. Verifique o seu email e código.');
      } else {
        setError(typeof data.detail === 'string' ? data.detail : 'Erro ao fazer login. Tente novamente.');
      }
    } catch (err) {
      setError(err.message || 'Erro de ligação. Tente novamente.');
    } finally {
      setLoading(false);
    }
  }, [email, accessCode, onLoginSuccess]);

  // Código limpo para habilitar botão
  const cleanCode = accessCode.replace(/[^A-Za-z0-9]/g, '');
  const isLockedOut = lockoutSeconds > 0;
  const canSubmit = email.trim().includes('@') && cleanCode.length === 6 && !loading && !isLockedOut;

  return (
    <ClientOnly>
      <div className="min-h-screen bg-gradient-to-br from-slate-50 via-gray-50 to-gray-100 flex items-center justify-center p-4">
        <div className="w-full max-w-md">
          {/* Logo */}
          <div className="flex items-center justify-center mb-8">
            <img
              src="/PowerCell-default.png"
              alt="PowerCell"
              className="h-14 w-auto object-contain"
            />
          </div>

          {/* Login Card */}
          <div className="bg-white rounded-2xl shadow-xl border border-gray-100 p-8">
            {/* Header */}
            <div className="text-center mb-6">
              <div className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-4 shadow-lg bg-gradient-to-br from-emerald-500 to-teal-600">
                <LogIn className="w-8 h-8 text-white" />
              </div>
              <h1 className="text-xl font-bold text-gray-900">Portal do Cliente</h1>
              <p className="text-sm text-gray-500 mt-1">
                Introduza o seu email e código de acesso
              </p>
            </div>

            {/* Security notice */}
            <div className="flex items-start gap-2 rounded-lg p-3 mb-5 bg-emerald-50 border border-emerald-200">
              <Shield className="w-4 h-4 text-emerald-600 mt-0.5 flex-shrink-0" />
              <p className="text-xs text-emerald-700">
                <strong>Acesso seguro.</strong> Os seus dados são encriptados e nunca são partilhados. 
                O código de acesso foi enviado para o seu email quando se registou.
              </p>
            </div>

            {/* Formulário */}
            <form onSubmit={handleLogin} className="space-y-4">
              {/* Email Input */}
              <div>
                <label className="text-sm font-medium text-gray-700 mb-1.5 block">
                  Email
                </label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="exemplo@email.com"
                    className="w-full pl-10 pr-4 py-3 text-sm border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-400 focus:border-transparent transition-all"
                    disabled={loading}
                    autoComplete="email"
                    autoFocus
                  />
                </div>
              </div>

              {/* Access Code Input */}
              <div>
                <label className="text-sm font-medium text-gray-700 mb-1.5 block">
                  Código de Acesso
                </label>
                <div className="relative">
                  <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    type="text"
                    value={accessCode}
                    onChange={(e) => handleAccessCodeChange(e.target.value)}
                    placeholder="A4B-9X2"
                    className="w-full pl-10 pr-4 py-3 text-sm border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-400 focus:border-transparent transition-all font-mono tracking-widest text-center text-base uppercase"
                    disabled={loading}
                    autoComplete="off"
                    maxLength={7}  // XXX-XXX = 7 chars com hífen
                    style={{ letterSpacing: '0.2em' }}
                  />
                </div>
                <p className="text-[10px] text-gray-400 mt-1">
                  6 caracteres alfanuméricos (ex: A4B-9X2)
                </p>
              </div>

              {/* Error */}
              {error && !isLockedOut && (
                <div className="flex items-start gap-2 text-xs text-red-600 bg-red-50 rounded-xl px-4 py-3 border border-red-200">
                  <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              {/* Lockout countdown — destaque especial para bloqueio temporário */}
              {error && isLockedOut && (
                <div className="flex items-start gap-2 text-xs text-amber-700 bg-amber-50 rounded-xl px-4 py-3 border border-amber-300">
                  <Lock className="w-4 h-4 mt-0.5 flex-shrink-0" />
                  <div className="flex flex-col gap-1">
                    <span className="font-medium">{error}</span>
                    <span className="font-mono text-sm font-bold text-amber-800">
                      Aguarde {formatCountdown(lockoutSeconds)} para tentar novamente
                    </span>
                  </div>
                </div>
              )}

              {/* Submit */}
              <button
                type="submit"
                disabled={!canSubmit}
                className="w-full py-3 text-sm font-semibold bg-gradient-to-r from-emerald-600 to-teal-600 text-white rounded-xl hover:from-emerald-700 hover:to-teal-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-md hover:shadow-lg flex items-center justify-center gap-2"
              >
                {loading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    A verificar...
                  </>
                ) : (
                  <>
                    <LogIn className="w-4 h-4" />
                    Entrar
                  </>
                )}
              </button>
            </form>
          </div>

          {/* Footer */}
          <div className="text-center mt-6">
            <p className="text-xs text-gray-400">
              Não tem o código de acesso? Contacte o seu consultor.
            </p>
            <div className="flex items-center justify-center gap-1.5 mt-2 text-xs text-gray-400">
              <Shield className="w-3 h-3" />
              <span>Ligação segura e encriptada</span>
            </div>
          </div>
        </div>
      </div>
    </ClientOnly>
  );
}
