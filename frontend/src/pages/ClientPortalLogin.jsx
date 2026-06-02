/**
 * ClientPortalLogin — Ecrã de Login do Portal do Cliente (NIF + OTP).
 *
 * Fluxo de autenticação:
 *   Fase 1: Utilizador insere NIF → POST /portal/auth/request-otp → email com código
 *   Fase 2: Utilizador insere código OTP (6 dígitos) → POST /portal/auth/verify-otp → token
 *
 * O token devolvido é guardado em sessionStorage (portalToken).
 * O URL fica sempre limpo (/portal) e a sessão mantém-se enquanto a aba estiver aberta.
 *
 * Integração com InputOTP do shadcn/ui para o código de 6 dígitos.
 */
import React, { useState, useCallback, useEffect, useRef } from 'react';
import { toast } from 'sonner';
import {
  Shield,
  Loader2,
  AlertCircle,
  Mail,
  ArrowLeft,
  KeyRound,
  RefreshCw,
} from 'lucide-react';
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSlot,
  InputOTPSeparator,
} from '@/components/ui/input-otp';

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
  const [mounted, setMounted] = useState(false);
  useEffect(() => { setMounted(true); }, []);
  return mounted ? children : fallback;
}

// ====================================================================
// MAIN LOGIN COMPONENT
// ====================================================================
export default function ClientPortalLogin({ onLoginSuccess }) {
  // ── State ──
  const [step, setStep] = useState(1); // 1 = NIF, 2 = OTP
  const [nif, setNif] = useState('');
  const [otpCode, setOtpCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [otpSent, setOtpSent] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);

  // Ref para auto-submit quando OTP estiver completo
  const otpCompleteRef = useRef(false);

  // ── Cooldown timer para reenvio de OTP ──
  useEffect(() => {
    if (resendCooldown <= 0) return;
    const timer = setTimeout(() => setResendCooldown((c) => c - 1), 1000);
    return () => clearTimeout(timer);
  }, [resendCooldown]);

  // ── Auto-submit OTP quando o código estiver completo (6 dígitos) ──
  useEffect(() => {
    if (step !== 2) return;
    if (otpCode.length === 6 && !otpCompleteRef.current && !loading) {
      otpCompleteRef.current = true;
      handleVerifyOtp(otpCode);
    }
    // Reset flag quando o utilizador apaga dígitos
    if (otpCode.length < 6) {
      otpCompleteRef.current = false;
    }
  }, [otpCode, step, loading]);

  // ── Fase 1: Pedir OTP ──
  const handleRequestOtp = useCallback(async (e) => {
    e?.preventDefault();
    setError(null);

    const cleanNif = nif.replace(/\D/g, '');
    if (cleanNif.length !== 9) {
      setError('O NIF deve conter exatamente 9 dígitos.');
      return;
    }

    setLoading(true);
    try {
      const res = await fetchWithRetry(`${BACKEND_URL}/portal/auth/request-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nif: cleanNif }),
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

      if (res.ok) {
        // OTP enviado com sucesso — passar para a Fase 2
        setStep(2);
        setOtpSent(true);
        setOtpCode('');
        setResendCooldown(30); // 30 segundos de cooldown para reenvio
        toast.success('Código enviado para o seu email!');
      } else {
        // Erro — mostrar mensagem do backend
        setError(data.detail || 'Erro ao enviar o código. Tente novamente.');
      }
    } catch (err) {
      setError(err.message || 'Erro de ligação. Tente novamente.');
    } finally {
      setLoading(false);
    }
  }, [nif]);

  // ── Fase 2: Verificar OTP ──
  const handleVerifyOtp = useCallback(async (code) => {
    const cleanNif = nif.replace(/\D/g, '');
    if (!code || code.length !== 6) {
      setError('Introduza o código de 6 dígitos.');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const res = await fetchWithRetry(`${BACKEND_URL}/portal/auth/verify-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nif: cleanNif, code }),
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
        // ── Sucesso! Guardar token em sessionStorage ──
        sessionStorage.setItem('portalToken', data.token);
        sessionStorage.setItem('portalClientId', data.client_id || '');
        sessionStorage.setItem('portalAuthMethod', 'otp');
        sessionStorage.setItem('portalVerified', 'true');

        // Limpar localStorage legado (evitar conflitos com o modelo antigo)
        localStorage.removeItem('portal_token');
        localStorage.removeItem('portal_verified');
        localStorage.removeItem('portal_client_id');
        localStorage.removeItem('portal_client_name');
        localStorage.removeItem('portal_process_id');

        if (onLoginSuccess) {
          onLoginSuccess(data.token);
        }
      } else {
        // OTP incorrecto ou expirado
        otpCompleteRef.current = false;
        setOtpCode('');
        setError(data.detail || 'Código inválido. Tente novamente.');
      }
    } catch (err) {
      otpCompleteRef.current = false;
      setError(err.message || 'Erro de ligação. Tente novamente.');
    } finally {
      setLoading(false);
    }
  }, [nif, onLoginSuccess]);

  // ── Reenviar OTP ──
  const handleResendOtp = useCallback(async () => {
    if (resendCooldown > 0) return;
    setError(null);
    setOtpCode('');
    otpCompleteRef.current = false;

    const cleanNif = nif.replace(/\D/g, '');
    if (cleanNif.length !== 9) return;

    setLoading(true);
    try {
      const res = await fetchWithRetry(`${BACKEND_URL}/portal/auth/request-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nif: cleanNif }),
      });

      let data;
      try { data = await res.json(); } catch {
        setError('Erro ao reenviar. Tente novamente.');
        return;
      }

      if (res.ok) {
        setResendCooldown(30);
        toast.success('Novo código enviado!');
      } else {
        setError(data.detail || 'Erro ao reenviar o código.');
      }
    } catch (err) {
      setError(err.message || 'Erro de ligação.');
    } finally {
      setLoading(false);
    }
  }, [nif, resendCooldown]);

  // ── Voltar à Fase 1 ──
  const handleBack = useCallback(() => {
    setStep(1);
    setOtpCode('');
    setError(null);
    otpCompleteRef.current = false;
  }, []);

  // NIF limpo para display
  const displayNif = nif.replace(/\D/g, '');
  // Máscara de email (mostrar apenas primeira letra + ***@dominio)
  const maskEmail = (email) => {
    if (!email) return 'o seu email';
    const [local, domain] = email.split('@');
    if (!domain) return email;
    return local.length > 1 ? `${local[0]}${'*'.repeat(Math.min(local.length - 1, 5))}@${domain}` : `***@${domain}`;
  };

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
            {/* Header — muda conforme a fase */}
            <div className="text-center mb-6">
              <div className={`w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-4 shadow-lg transition-colors duration-300 ${
                step === 1
                  ? 'bg-gradient-to-br from-emerald-500 to-teal-600'
                  : 'bg-gradient-to-br from-blue-500 to-indigo-600'
              }`}>
                {step === 1 ? (
                  <Shield className="w-8 h-8 text-white" />
                ) : (
                  <KeyRound className="w-8 h-8 text-white" />
                )}
              </div>
              <h1 className="text-xl font-bold text-gray-900">
                {step === 1 ? 'Portal do Cliente' : 'Verificação'}
              </h1>
              <p className="text-sm text-gray-500 mt-1">
                {step === 1
                  ? 'Introduza o seu NIF para receber um código de acesso'
                  : 'Introduza o código de 6 dígitos enviado para o seu email'
                }
              </p>
            </div>

            {/* Security notice */}
            <div className={`flex items-start gap-2 rounded-lg p-3 mb-5 transition-colors duration-300 ${
              step === 1
                ? 'bg-emerald-50 border border-emerald-200'
                : 'bg-blue-50 border border-blue-200'
            }`}>
              {step === 1 ? (
                <Shield className="w-4 h-4 text-emerald-600 mt-0.5 flex-shrink-0" />
              ) : (
                <Mail className="w-4 h-4 text-blue-600 mt-0.5 flex-shrink-0" />
              )}
              <p className={`text-xs ${step === 1 ? 'text-emerald-700' : 'text-blue-700'}`}>
                {step === 1 ? (
                  <><strong>Acesso seguro.</strong> Os seus dados são encriptados e nunca são partilhados.</>
                ) : (
                  <>Enviámos um código para <strong>o email associado ao seu NIF</strong>. O código é válido durante 5 minutos.</>
                )}
              </p>
            </div>

            {/* ═══════════════════════════════════════════════
                FASE 1 — Pedir NIF
            ═══════════════════════════════════════════════ */}
            {step === 1 && (
              <form onSubmit={handleRequestOtp} className="space-y-4">
                {/* NIF Input */}
                <div>
                  <label className="text-sm font-medium text-gray-700 mb-1.5 block">
                    NIF (Número de Identificação Fiscal)
                  </label>
                  <input
                    type="text"
                    value={nif}
                    onChange={(e) => setNif(e.target.value.replace(/\D/g, '').slice(0, 9))}
                    placeholder="123456789"
                    className="w-full px-4 py-3 text-sm border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-400 focus:border-transparent transition-all"
                    inputMode="numeric"
                    disabled={loading}
                    autoFocus
                  />
                  <p className="text-[10px] text-gray-400 mt-1">9 dígitos do seu Cartão de Cidadão</p>
                </div>

                {/* Error */}
                {error && (
                  <div className="flex items-start gap-2 text-xs text-red-600 bg-red-50 rounded-xl px-4 py-3 border border-red-200">
                    <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                    <span>{error}</span>
                  </div>
                )}

                {/* Submit */}
                <button
                  type="submit"
                  disabled={loading || displayNif.length !== 9}
                  className="w-full py-3 text-sm font-semibold bg-gradient-to-r from-emerald-600 to-teal-600 text-white rounded-xl hover:from-emerald-700 hover:to-teal-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-md hover:shadow-lg flex items-center justify-center gap-2"
                >
                  {loading ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      A enviar código...
                    </>
                  ) : (
                    <>
                      <Mail className="w-4 h-4" />
                      Enviar Código
                    </>
                  )}
                </button>
              </form>
            )}

            {/* ═══════════════════════════════════════════════
                FASE 2 — Código OTP (InputOTP)
            ═══════════════════════════════════════════════ */}
            {step === 2 && (
              <div className="space-y-5">
                {/* OTP Input — InputOTP do shadcn/ui */}
                <div className="flex flex-col items-center gap-2">
                  <InputOTP
                    maxLength={6}
                    value={otpCode}
                    onChange={(value) => setOtpCode(value)}
                    disabled={loading}
                    containerClassName="gap-2"
                  >
                    <InputOTPGroup>
                      <InputOTPSlot index={0} className="h-14 w-12 text-xl font-bold border-2 rounded-lg data-[active]:ring-2 data-[active]:ring-blue-400 data-[active]:border-blue-400" />
                      <InputOTPSlot index={1} className="h-14 w-12 text-xl font-bold border-2 rounded-lg data-[active]:ring-2 data-[active]:ring-blue-400 data-[active]:border-blue-400" />
                      <InputOTPSlot index={2} className="h-14 w-12 text-xl font-bold border-2 rounded-lg data-[active]:ring-2 data-[active]:ring-blue-400 data-[active]:border-blue-400" />
                    </InputOTPGroup>
                    <InputOTPSeparator className="mx-1" />
                    <InputOTPGroup>
                      <InputOTPSlot index={3} className="h-14 w-12 text-xl font-bold border-2 rounded-lg data-[active]:ring-2 data-[active]:ring-blue-400 data-[active]:border-blue-400" />
                      <InputOTPSlot index={4} className="h-14 w-12 text-xl font-bold border-2 rounded-lg data-[active]:ring-2 data-[active]:ring-blue-400 data-[active]:border-blue-400" />
                      <InputOTPSlot index={5} className="h-14 w-12 text-xl font-bold border-2 rounded-lg data-[active]:ring-2 data-[active]:ring-blue-400 data-[active]:border-blue-400" />
                    </InputOTPGroup>
                  </InputOTP>
                  <p className="text-[10px] text-gray-400">
                    {loading ? 'A verificar...' : 'Código de 6 dígitos · Verificação automática'}
                  </p>
                </div>

                {/* Error */}
                {error && (
                  <div className="flex items-start gap-2 text-xs text-red-600 bg-red-50 rounded-xl px-4 py-3 border border-red-200">
                    <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                    <span>{error}</span>
                  </div>
                )}

                {/* Loading overlay quando está a verificar */}
                {loading && (
                  <div className="flex items-center justify-center gap-2 py-2">
                    <Loader2 className="w-5 h-5 text-blue-600 animate-spin" />
                    <span className="text-sm text-blue-600 font-medium">A verificar código...</span>
                  </div>
                )}

                {/* Reenviar código */}
                <div className="text-center">
                  <p className="text-xs text-gray-500 mb-1">Não recebeu o código?</p>
                  {resendCooldown > 0 ? (
                    <p className="text-xs text-gray-400">
                      Reenviar disponível em <span className="font-medium text-gray-600">{resendCooldown}s</span>
                    </p>
                  ) : (
                    <button
                      onClick={handleResendOtp}
                      disabled={loading}
                      className="text-xs font-medium text-blue-600 hover:text-blue-700 disabled:opacity-50 flex items-center justify-center gap-1 mx-auto"
                    >
                      <RefreshCw className="w-3 h-3" />
                      Reenviar código
                    </button>
                  )}
                </div>

                {/* Voltar */}
                <button
                  onClick={handleBack}
                  disabled={loading}
                  className="w-full py-2 text-xs text-gray-500 hover:text-gray-700 transition-colors flex items-center justify-center gap-1"
                >
                  <ArrowLeft className="w-3 h-3" />
                  Voltar ao NIF
                </button>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="text-center mt-6">
            <p className="text-xs text-gray-400">
              Não tem acesso? Contacte o seu consultor.
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
