/**
 * ClientPortal — Portal do Cliente (Email + Código de Acesso + Sliding Session).
 *
 * Layout: Dashboard profissional full-width — horizontal stepper + 2 colunas.
 * - Topo (lg:col-span-12): Resumo + Timeline Horizontal (Stepper)
 * - Esquerda (lg:col-span-7): Gestão de Documentos + RGPD + Equipa
 * - Direita (lg:col-span-5): Mensagens / Chat
 *
 * Fluxo de autenticação (v4 — Código de Acesso Fixo):
 *   1. Utilizador acede ao portal (/portal)
 *   2. Se não tem token em localStorage → Mostra ecrã de login
 *   3. Login: Email + Código de Acesso → POST /portal/auth/login → Token JWT
 *   4. Token gravado em localStorage com Sliding Session (15 min de inactividade)
 *   5. Fluxo legado (magic link) ainda funciona como fallback
 *
 * Sliding Session:
 *   - A sessão não expira enquanto o utilizador estiver activo
 *   - Após 15 min de inactividade → logout automático
 *   - Ao fechar a aba → limpa storage (obriga novo login)
 */
import React, { useState, useEffect, useCallback, useRef, useMemo, Suspense } from 'react';
import { toast } from 'sonner';
import { extractErrorMessage } from '../utils/extractErrorMessage';
import useSlidingSession from '../hooks/useSlidingSession';
import {
  FileText,
  Upload,
  CheckCircle2,
  Clock,
  AlertCircle,
  ChevronRight,
  Phone,
  Mail,
  MessageCircle,
  Loader2,
  FileUp,
  X,
  Check,
  ExternalLink,
  Shield,
  BarChart3,
  Send,
  Landmark,
  HeartPulse,
  HelpCircle,
  Eye,
  EyeOff,
  Home,
  MapPin,
  CalendarClock,
  User,
  Save,
  Lock,
  Download,
  Calculator,
} from 'lucide-react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';
import { formatDate, safeDate } from '../lib/utils';
import ClientPortalLogin from './ClientPortalLogin';
import SimulatorCH from '../components/portal/SimulatorCH';

// ====================================================================
// CLIENT-ONLY WRAPPER — prevents hydration mismatches with Radix portals
// ====================================================================
function ClientOnly({ children, fallback = null }) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => { setMounted(true); }, []);
  return mounted ? children : fallback;
}

// ====================================================================
// LOADER FALLBACK for Suspense boundaries
// ====================================================================
function LoaderFallback() {
  return (
    <div className="flex items-center justify-center py-8">
      <Loader2 className="w-5 h-5 text-emerald-500 animate-spin mr-2" />
      <span className="text-sm text-gray-500">A carregar...</span>
    </div>
  );
}

const BACKEND_URL = (process.env.REACT_APP_BACKEND_URL || 'https://powercell.onrender.com') + '/api';

// ── Helper: obter token do portal (localStorage > sessionStorage legado) ──
function getPortalToken() {
  return localStorage.getItem('portalToken') || localStorage.getItem('portal_token') || sessionStorage.getItem('portalToken');
}

// ====================================================================
// FETCH WITH RETRY — handles Render cold starts (503) automatically
// ====================================================================
const FETCH_RETRY_DELAYS = [3000, 6000]; // retry after 3s, then 6s
const MAX_RETRIES = FETCH_RETRY_DELAYS.length;

async function fetchWithRetry(url, options = {}, retries = MAX_RETRIES) {
  let lastError = null;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const res = await fetch(url, options);
      // Only retry on 503 from Render's proxy (cold start).
      // Render's 503 returns HTML (non-JSON), while our app-level 503s return JSON.
      // We clone the response to peek at the content-type without consuming the body.
      if (res.status === 503 && attempt < retries) {
        const contentType = res.headers.get('content-type') || '';
        // If it's JSON, it's an app-level 503 (not a cold start) — don't retry
        if (contentType.includes('application/json')) {
          return res;
        }
        // Non-JSON 503 (Render's HTML page) — likely a cold start, retry
        await new Promise((r) => setTimeout(r, FETCH_RETRY_DELAYS[attempt]));
        continue;
      }
      return res;
    } catch (err) {
      lastError = err;
      // Network errors might be transient too — retry once
      if (attempt < retries) {
        await new Promise((r) => setTimeout(r, FETCH_RETRY_DELAYS[attempt]));
        continue;
      }
    }
  }
  throw lastError || new Error('Erro de ligação após várias tentativas.');
}

// ====================================================================
// STEP COLOR HELPER
// ====================================================================
function stepColor(colorStr) {
  const map = {
    yellow: { bg: 'bg-amber-100', border: 'border-amber-400', text: 'text-amber-700', ring: 'shadow-amber-400/30', fill: 'bg-amber-500' },
    blue:   { bg: 'bg-blue-100',   border: 'border-blue-400',   text: 'text-blue-700',   ring: 'shadow-blue-400/30',   fill: 'bg-blue-500' },
    orange: { bg: 'bg-orange-100', border: 'border-orange-400', text: 'text-orange-700', ring: 'shadow-orange-400/30', fill: 'bg-orange-500' },
    green:  { bg: 'bg-emerald-100',border: 'border-emerald-400',text: 'text-emerald-700',ring: 'shadow-emerald-400/30',fill: 'bg-emerald-500' },
    red:    { bg: 'bg-red-100',    border: 'border-red-400',    text: 'text-red-700',    ring: 'shadow-red-400/30',    fill: 'bg-red-500' },
    purple: { bg: 'bg-purple-100', border: 'border-purple-400', text: 'text-purple-700', ring: 'shadow-purple-400/30', fill: 'bg-purple-500' },
  };
  return map[colorStr] || map.green;
}

// ====================================================================
// PROGRESS STEPPER — Horizontal stepper (full-width, top of page)
// Mobile: scrollable horizontal; Desktop: fits naturally
// ====================================================================
function WorkflowStepper({ stepper }) {
  if (!stepper || stepper.length === 0) return null;

  const completedCount = stepper.filter(s => s.is_completed || s.is_current).length;

  return (
    <div className="w-full overflow-x-auto" style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}>
      <style>{`div[data-stepper-scroll]::-webkit-scrollbar { display: none; }`}</style>
      <div data-stepper-scroll className="flex items-start w-min min-w-full py-2" style={{ scrollbarWidth: 'none' }}>
        {stepper.map((step, i) => {
          const colors = stepColor(step.color);
          const isActive = step.is_current;
          const isDone = step.is_completed;

          return (
            <div key={step.id} className="flex flex-col items-center relative" style={{ minWidth: '80px', flex: '1 1 0%' }}>
              {/* Connection line (between circles) */}
              {i < stepper.length - 1 && (
                <div
                  className={`absolute top-[18px] h-0.5 z-0 transition-colors duration-500 ${
                    isDone ? 'bg-emerald-500' : 'bg-gray-200'
                  }`}
                  style={{ left: 'calc(50% + 18px)', right: 'calc(-50% + 18px)' }}
                />
              )}

              {/* Circle */}
              <div className={`w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold border-2 transition-all z-10 ${
                isDone
                  ? 'bg-emerald-500 border-emerald-500 text-white'
                  : isActive
                  ? `${colors.bg} ${colors.border} ${colors.text} scale-110 shadow-lg ring-4 ring-white`
                  : 'bg-white border-gray-300 text-gray-400'
              }`}>
                {isDone ? <Check className="w-4 h-4" /> : <span>{i + 1}</span>}
              </div>

              {/* Label below */}
              <span className={`mt-2 text-[11px] font-medium text-center leading-tight max-w-[90px] ${
                isActive ? 'text-gray-900' : isDone ? 'text-emerald-600' : 'text-gray-400'
              }`}>
                {step.label}
              </span>

              {/* Description for active step */}
              {isActive && step.description && (
                <span className="mt-0.5 text-[10px] text-gray-400 text-center max-w-[100px] leading-tight">
                  {step.description}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ====================================================================
// SINGLE DOCUMENT UPLOAD ITEM (supports multi-file via drag & drop / multiple)
// ====================================================================
function DocumentUploadItem({ doc, onUploadSuccess }) {
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploadCount, setUploadCount] = useState(0);
  const [uploadTotal, setUploadTotal] = useState(1);
  const fileInputRef = useRef(null);

  const doUpload = async (file) => {
    setProgress(0);

    try {
      const token = getPortalToken();
      if (!token) throw new Error('Sessão expirada. Recarregue a página.');

      // Step 1: pre-signed URL
      setProgress(10);
      const urlRes = await fetch(`${BACKEND_URL}/portal/upload-url`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          filename: file.name,
          content_type: file.type || 'application/octet-stream',
          category: doc.category,
          document_id: doc.id || undefined,
        }),
      });
      if (!urlRes.ok) { const e = await urlRes.json(); throw new Error(e.detail || 'Erro ao gerar link'); }
      const { upload_url, file_key } = await urlRes.json();

      // Step 2: upload to S3
      setProgress(30);
      await new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('PUT', upload_url);
        xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream');
        xhr.upload.onprogress = (e) => { if (e.lengthComputable) setProgress(30 + Math.round((e.loaded / e.total) * 60)); };
        xhr.onload = () => (xhr.status >= 200 && xhr.status < 300) ? resolve() : reject(new Error('Erro ao enviar'));
        xhr.onerror = () => reject(new Error('Erro de ligação'));
        xhr.send(file);
      });

      // Step 3: confirm
      setProgress(95);
      const confRes = await fetch(`${BACKEND_URL}/portal/confirm-upload`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ file_key, original_filename: file.name, category: doc.category, file_size: file.size, content_type: file.type, document_id: doc.id || undefined }),
      });
      if (!confRes.ok) { const e = await confRes.json(); throw new Error(e.detail || 'Erro ao confirmar'); }

      return { success: true, filename: file.name };
    } catch (err) {
      return { error: err.message, filename: file.name };
    }
  };

  const uploadFiles = async (files) => {
    if (!files || files.length === 0) return;

    setUploading(true);
    setUploadTotal(files.length);
    setUploadCount(0);
    setProgress(0);
    setResult(null);

    const results = [];
    for (let i = 0; i < files.length; i++) {
      setUploadCount(i + 1);
      const res = await doUpload(files[i]);
      results.push(res);
    }

    const successes = results.filter(r => r.success);
    const errors = results.filter(r => r.error);

    if (errors.length === 0) {
      setResult({ success: true, count: successes.length });
      setTimeout(() => onUploadSuccess && onUploadSuccess(), 800);
    } else if (successes.length > 0) {
      setResult({ success: true, count: successes.length, errorCount: errors.length });
      setTimeout(() => onUploadSuccess && onUploadSuccess(), 800);
    } else {
      setResult({ error: errors[0].error });
    }
    setUploading(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files.length > 0) uploadFiles(Array.from(e.dataTransfer.files));
  };

  const handleFileChange = (e) => {
    if (e.target.files.length > 0) uploadFiles(Array.from(e.target.files));
    e.target.value = '';
  };

  const progressLabel = uploadTotal > 1
    ? `${uploadCount}/${uploadTotal}`
    : `${progress}%`;

  return (
    <div
      className={`border rounded-xl p-3 transition-all ${uploading ? 'border-emerald-300 bg-emerald-50/50' : result?.success ? 'border-emerald-200 bg-emerald-50' : dragOver ? 'border-emerald-400 bg-emerald-50' : 'border-gray-200 bg-white'}`}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragEnter={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
    >
      <div className="flex items-center gap-3">
        <span className="text-xl flex-shrink-0">{doc.icon}</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-800">{doc.label}</p>
          {doc.notes && <p className="text-xs text-gray-400 truncate">{typeof doc.notes === 'string' ? doc.notes : JSON.stringify(doc.notes)}</p>}
        </div>

        {!uploading && !result?.success && (
          <>
            <input ref={fileInputRef} type="file" className="hidden" accept=".pdf,.jpg,.jpeg,.png,.doc,.docx" multiple={true}
              onChange={handleFileChange} />
            <button onClick={() => fileInputRef.current?.click()}
              className="flex-shrink-0 px-3 py-1.5 text-xs font-medium bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors flex items-center gap-1">
              <Upload className="w-3.5 h-3.5" /> Submeter
            </button>
          </>
        )}

        {uploading && (
          <div className="flex-shrink-0 flex items-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin text-emerald-600" />
            <span className="text-xs text-emerald-600 font-medium">{progressLabel}</span>
          </div>
        )}

        {result?.success && (
          <div className="flex-shrink-0 flex items-center gap-1 text-emerald-600">
            <CheckCircle2 className="w-4 h-4" />
            <span className="text-xs font-medium">
              {result.count > 1 ? `${result.count} ficheiros` : 'Enviado'}
              {result.errorCount ? ` (${result.errorCount} erro${result.errorCount > 1 ? 's' : ''})` : ''}
            </span>
          </div>
        )}
      </div>

      {/* Progress bar */}
      {uploading && (
        <div className="w-full bg-gray-200 rounded-full h-1.5 mt-2.5">
          <div className="bg-emerald-500 h-1.5 rounded-full transition-all duration-300"
            style={{ width: `${uploadTotal > 1 ? ((uploadCount / uploadTotal) * 100) : progress}%` }} />
        </div>
      )}

      {/* Error */}
      {result?.error && !result?.success && (
        <div className="mt-2 flex items-center gap-1.5 text-xs text-red-600">
          <AlertCircle className="w-3.5 h-3.5" />
          <span>{result.error}</span>
          <button onClick={() => setResult(null)} className="ml-auto text-red-400 hover:text-red-600">Tentar</button>
        </div>
      )}
    </div>
  );
}

// ====================================================================
// DOCUMENTS PANEL — Right column (desktop) / Section (mobile)
// ====================================================================

// ====================================================================
// CREDENTIALS DIALOG — Finanças / Segurança Social
// ====================================================================
function CredentialsDialog({ open, onOpenChange, source, onSuccess }) {
  const [idField, setIdField] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // MFA state
  const [awaitingMfa, setAwaitingMfa] = useState(false);
  const [mfaCode, setMfaCode] = useState('');
  const [mfaSubmitting, setMfaSubmitting] = useState(false);
  const [scraperJobId, setScraperJobId] = useState(null);
  const [mfaPollCount, setMfaPollCount] = useState(0);

  const isFinancas = source === 'financas';
  const idLabel = isFinancas ? 'NIF' : 'NISS';
  const idLength = isFinancas ? 9 : 11;
  const sourceLabel = isFinancas ? 'Portal das Finanças' : 'Segurança Social';
  const sourceIcon = isFinancas ? <Landmark className="w-5 h-5 text-teal-600" /> : <HeartPulse className="w-5 h-5 text-rose-500" />;

  // Reset state when dialog opens (safe: only runs on open transition)
  const prevOpenRef = useRef(false);
  useEffect(() => {
    if (open && !prevOpenRef.current) {
      setIdField(''); setPassword(''); setShowPassword(false); setLoading(false);
      setError(null); setSuccess(null); setAwaitingMfa(false); setMfaCode('');
      setMfaSubmitting(false); setScraperJobId(null); setMfaPollCount(0);
    }
    prevOpenRef.current = open;
  }, [open]);

  // ── Poll scraper job status after credentials submitted ──
  useEffect(() => {
    if (!scraperJobId || !open || success) return;

    // Prevenir que o utilizador feche o tab do browser durante o scraping
    const handleBeforeUnload = (e) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', handleBeforeUnload);

    let cancelled = false;
    const pollInterval = setInterval(async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/portal/scraper-job/${scraperJobId}`);
        if (!res.ok || cancelled) return;
        const job = await res.json();

        if (job.status === 'awaiting_mfa' && !awaitingMfa) {
          setAwaitingMfa(true);
          setLoading(false);
          setMfaPollCount(prev => prev + 1);
        } else if (job.status === 'success' || job.status === 'completed') {
          // Scraper terminou com sucesso — fechar modal, toast, refetch
          setAwaitingMfa(false);
          setLoading(false);
          const successMsg = job.message || `${job.documents_count || ''} documento(s) obtido(s) com sucesso!`;
          setSuccess(successMsg);
          toast.success('Documentos extraídos com sucesso!');
          clearInterval(pollInterval);
          // Refetch da lista de documentos via onSuccess callback
          if (onSuccess) onSuccess();
          setTimeout(() => { onOpenChange(false); }, 2500);
        } else if (job.status === 'error') {
          setAwaitingMfa(false);
          setLoading(false);
          const MANUAL_UPLOAD_HINT =
            ' Pode também descarregar os documentos directamente do ' +
            sourceLabel + ' e enviá-los através do botão "Carregar documentos".';

          if (job.error_type === 'mfa_requerido') {
            // MFA requerido mas sem processo para esperar — mostrar input MFA
            setAwaitingMfa(true);
            setLoading(false);
            setError('O portal requere verificação em 2 passos (Chave Móvel Digital). Introduza o código enviado para o seu telemóvel.');
          } else if (job.error_type === 'mfa_timeout') {
            setError('O código de verificação não foi submetido a tempo. Tente novamente.');
          } else if (job.error_type === 'mfa_codigo_incorreto') {
            setError('O código SMS introduzido parece incorreto. Tente novamente.');
          } else if (job.error_type === 'mfa_error') {
            setError('Erro ao processar o código de verificação. Tente novamente.');
          } else if (job.error_type === 'credenciais_invalidas') {
            setError('As credenciais que introduziu estão incorretas. Verifique o seu ' + idLabel + ' e a password.');
          } else {
            setError((job.message || 'Erro ao obter documentos.') + MANUAL_UPLOAD_HINT);
          }
          // Se não for mfa_requerido, parar o polling; se for, continuar para aguardar código
          if (job.error_type !== 'mfa_requerido') {
            clearInterval(pollInterval);
          }
        }
      } catch {
        // Network error during polling — don't fail, just retry
      }
    }, 3000); // Poll every 3 seconds

    return () => { cancelled = true; clearInterval(pollInterval); window.removeEventListener('beforeunload', handleBeforeUnload); };
  }, [scraperJobId, open, success, awaitingMfa, sourceLabel, idLabel, onOpenChange, onSuccess]);

  // ── Submit MFA code ──
  const handleMfaSubmit = async (e) => {
    e?.preventDefault();
    if (!mfaCode || mfaCode.length < 4) return;

    setMfaSubmitting(true);
    setError(null);
    try {
      const token = getPortalToken();
      if (!token) throw new Error('Sessão expirada.');

      const res = await fetchWithRetry(`${BACKEND_URL}/portal/submit-mfa`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ process_id: localStorage.getItem('portalProcessId') || localStorage.getItem('portal_process_id') || '', mfa_code: mfaCode }),
      });

      let data;
      try { data = await res.json(); } catch { throw new Error('Erro de ligação.'); }

      if (!res.ok) {
        setError(typeof data.detail === 'string' ? data.detail : 'Erro ao submeter código.');
        setMfaSubmitting(false);
        return;
      }

      // Código aceite — voltar ao estado de loading (scraper continua)
      setAwaitingMfa(false);
      setLoading(true);
      setMfaCode('');
      // O polling continua automaticamente via useEffect
    } catch (err) {
      setError(err.message || 'Erro de ligação. Tente novamente.');
    } finally {
      setMfaSubmitting(false);
    }
  };

  const handleSubmit = async (e) => {
    e?.preventDefault();
    setError(null);
    setSuccess(null);

    const trimmed = idField.trim();
    if (!trimmed || trimmed.length !== idLength || !/^\d+$/.test(trimmed)) {
      setError(`${idLabel} inválido. Deve conter ${idLength} dígitos.`);
      return;
    }
    if (!password) {
      setError('A password é obrigatória.');
      return;
    }

    setLoading(true);
    let startedAsyncJob = false;
    try {
      const token = getPortalToken();
      if (!token) throw new Error('Sessão expirada.');

      const endpoint = isFinancas ? 'fetch-financas' : 'fetch-seguranca-social';
      const bodyKey = isFinancas ? 'nif' : 'niss';

      const res = await fetchWithRetry(`${BACKEND_URL}/portal/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ [bodyKey]: trimmed, password }),
      });

      // Safely parse JSON — 503 from Render proxy returns HTML, not JSON
      let data;
      try {
        data = await res.json();
      } catch {
        // Response wasn't JSON (e.g., Render's 503 HTML page)
        if (res.status === 503) {
          setError('O servidor está a iniciar. Por favor, aguarde uns segundos e tente novamente.');
          return;
        }
        setError('Erro inesperado do servidor. Tente novamente mais tarde.');
        return;
      }

      // Mensagem comum a usar em todos os erros de scraping
      // (sempre que falha, indicar ao cliente que pode fazer upload manual).
      const MANUAL_UPLOAD_HINT =
        ' Pode também descarregar os documentos directamente do ' +
        sourceLabel +
        ' e enviá-los através do botão "Carregar documentos" no portal.';

      if (res.ok && data.success && !data.scraper_job_id) {
        // Sucesso síncrono (dev mode, etc.)
        setSuccess(data.message || 'Documentos obtidos com sucesso!');
        toast.success('Documentos extraídos com sucesso!');
        if (onSuccess) onSuccess();
        setTimeout(() => { onOpenChange(false); }, 2500);
      } else if (res.ok && (data.status === 'processing' || data.scraper_job_id)) {
        // Processamento assíncrono: guardar job_id e iniciar polling.
        // O diálogo NÃO fecha — fica em estado de loading/polling
        // até o scraper terminar ou pedir MFA.
        if (data.scraper_job_id) {
          setScraperJobId(data.scraper_job_id);
        }
        if (data.process_id && !data.scraper_job_id) {
          // Fallback: usar process_id como job_id
          setScraperJobId(data.process_id);
        }
        startedAsyncJob = true;
        // O useEffect de polling vai verificar o estado automaticamente
      } else if (res.ok && data.success === false) {
        // App-level error returned as 200 + success:false (scraper unavailable, etc.)
        setError(
          (data.message ||
            'Não foi possível obter os documentos automaticamente.') +
          MANUAL_UPLOAD_HINT
        );
      } else if (res.status === 503) {
        // Render cold start 503 (shouldn't reach here after fetchWithRetry, but handle gracefully)
        setError(
          (data.detail ||
            'O servidor está a iniciar. Por favor, aguarde uns segundos e tente novamente.') +
          MANUAL_UPLOAD_HINT
        );
      } else if (res.status === 401 && data.detail) {
        // Credenciais incorretas: NÃO sugerir upload manual (o cliente pode só ter falhado o password)
        setError(typeof data.detail === 'string' ? data.detail : 'Credenciais inválidas. Verifique o seu ' + idLabel + ' e a password.');
      } else if (res.status === 400 && data.detail) {
        // Validação simples (NIF/NISS mal formado, password vazia)
        setError(typeof data.detail === 'string' ? data.detail : 'Dados inválidos.');
      } else {
        setError(
          (typeof data.detail === 'string' ? data.detail : 'Erro ao obter documentos. Tente novamente.') +
          MANUAL_UPLOAD_HINT
        );
      }
    } catch (err) {
      setError(err.message || 'Erro de ligação. Tente novamente.');
    } finally {
      // NÃO fazer setLoading(false) se iniciámos um job assíncrono —
      // o polling useEffect gere o estado loading daqui em diante.
      if (!startedAsyncJob) {
        setLoading(false);
      }
    }
  };

  return (
    <ClientOnly>
      <Dialog open={open} onOpenChange={(newOpen) => {
        // Impedir fecho acidental do diálogo durante polling do scraper
        if (!newOpen && scraperJobId && !success) return;
        onOpenChange(newOpen);
      }}>
        <DialogContent title={sourceLabel} description={`Obter documentos do ${sourceLabel}`} className="sm:max-w-md" onInteractOutside={(e) => { if (scraperJobId && !success) e.preventDefault(); }}>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {sourceIcon}
              {sourceLabel}
            </DialogTitle>
            <DialogDescription className="text-xs text-gray-500">
              Introduza as suas credenciais para obter automaticamente os seus documentos.
            </DialogDescription>
          </DialogHeader>

          {/* Security notice */}
          <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg p-3">
            <Shield className="w-4 h-4 text-amber-600 mt-0.5 flex-shrink-0" />
            <p className="text-xs text-amber-700">
              <strong>As suas credenciais não são guardadas.</strong> São usadas apenas em memória para obter os documentos e eliminadas de imediato.
            </p>
          </div>

          {success ? (
            <div className="flex items-start gap-2 bg-emerald-50 border border-emerald-200 rounded-lg p-4">
              <CheckCircle2 className="w-5 h-5 text-emerald-600 mt-0.5 flex-shrink-0" />
              <div>
                <p className="text-sm font-medium text-emerald-800">Sucesso!</p>
                <p className="text-xs text-emerald-600 mt-0.5">{success}</p>
              </div>
            </div>
          ) : awaitingMfa ? (
            /* ── MFA Input UI ── */
            <form onSubmit={handleMfaSubmit} className="space-y-3">
              <div className="flex items-start gap-2 bg-blue-50 border border-blue-200 rounded-lg p-4">
                <Shield className="w-5 h-5 text-blue-600 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="text-sm font-medium text-blue-800">Verificação em 2 passos</p>
                  <p className="text-xs text-blue-600 mt-1">
                    A {sourceLabel} enviou um código de verificação para o seu telemóvel.
                    Introduza o código abaixo para continuar.
                  </p>
                </div>
              </div>

              <div>
                <label className="text-xs font-medium text-gray-700 mb-1 block">
                  Código de verificação SMS
                </label>
                <input
                  type="text"
                  value={mfaCode}
                  onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, '').slice(0, 8))}
                  placeholder="123456"
                  className="w-full px-3 py-3 text-center text-2xl tracking-[0.5em] font-mono border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent"
                  inputMode="numeric"
                  disabled={mfaSubmitting}
                  autoFocus
                  maxLength={8}
                />
                <p className="text-[10px] text-gray-400 mt-1 text-center">
                  4 a 8 dígitos · O código expira em 5 minutos
                </p>
              </div>

              {error && (
                <div className="flex items-start gap-1.5 text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">
                  <AlertCircle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              <DialogFooter>
                <button type="button" onClick={() => onOpenChange(false)}
                  className="px-4 py-2 text-sm text-gray-500 hover:text-gray-700 transition-colors">
                  Cancelar
                </button>
                <button type="submit" disabled={mfaSubmitting || mfaCode.length < 4}
                  className="px-4 py-2 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2">
                  {mfaSubmitting ? <><Loader2 className="w-4 h-4 animate-spin" /> A verificar...</> : <><Shield className="w-4 h-4" /> Verificar Código</>}
                </button>
              </DialogFooter>
            </form>
          ) : loading && scraperJobId ? (
            /* ── Loading/Polling UI ── */
            <div className="space-y-3">
              <div className="flex items-center gap-3 py-4">
                <Loader2 className="w-6 h-6 text-emerald-600 animate-spin flex-shrink-0" />
                <div>
                  <p className="text-sm font-medium text-gray-800">A obter documentos...</p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    O robô está a aceder ao {sourceLabel}. Se for pedido um código SMS, aparecerá aqui automaticamente.
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2.5">
                <AlertCircle className="w-4 h-4 text-amber-600 mt-0.5 flex-shrink-0" />
                <div className="text-xs text-amber-800">
                  <p className="font-medium">Não feche nem saia desta janela!</p>
                  <p className="mt-0.5 text-amber-700">Se sair, a obtenção de documentos será interrompida e terá de recomeçar.</p>
                </div>
              </div>
              {error && (
                <div className="flex items-start gap-1.5 text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">
                  <AlertCircle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                  <span>{error}</span>
                </div>
              )}
              <DialogFooter>
                <button type="button" onClick={() => onOpenChange(false)}
                  className="px-4 py-2 text-sm text-gray-500 hover:text-gray-700 transition-colors">
                  Cancelar
                </button>
              </DialogFooter>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-3">
              <div>
                <label className="text-xs font-medium text-gray-700 mb-1 block">{idLabel}</label>
                <input
                  type="text"
                  value={idField}
                  onChange={(e) => setIdField(e.target.value.replace(/\D/g, '').slice(0, idLength))}
                  placeholder={isFinancas ? '123456789' : '12345678901'}
                  className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-400 focus:border-transparent"
                  inputMode="numeric"
                  disabled={loading}
                  autoFocus
                />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-700 mb-1 block">Password do {sourceLabel}</label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="A sua password"
                    className="w-full px-3 py-2 pr-10 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-400 focus:border-transparent"
                    disabled={loading}
                  />
                  <button type="button" onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              {error && (
                <div className="flex items-start gap-1.5 text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">
                  <AlertCircle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              <DialogFooter>
                <button type="button" onClick={() => onOpenChange(false)} disabled={loading}
                  className="px-4 py-2 text-sm text-gray-500 hover:text-gray-700 transition-colors">
                  Cancelar
                </button>
                <button type="submit" disabled={loading || !idField || !password}
                  className="px-4 py-2 text-sm font-medium bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2">
                  {loading ? <><Loader2 className="w-4 h-4 animate-spin" /> A obter...</> : <><ExternalLink className="w-4 h-4" /> Obter Documentos</>}
                </button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </ClientOnly>
  );
}

// ====================================================================
// DOCUMENT HELP DIALOG — Accordion com ajuda por documento
// ====================================================================
function DocumentHelpDialog({ open, onOpenChange }) {
  const helpItems = [
    {
      id: 'identificacao',
      title: 'Identificação (CC / Passaporte)',
      content: 'Precisa do Cartão de Cidadão ou Passaporte válido. Pode enviar fotografia (frente e verso) ou digitalização em PDF. Certifique-se que os dados são legíveis e que o documento não está caducado.',
    },
    {
      id: 'mapa-responsabilidades',
      title: 'Mapa de Responsabilidades',
      content: 'Este documento é emitido pelo Banco de Portugal e pode ser obtido gratuitamente em www.bportugal.pt ou num balcão do BdP. Mostra todos os seus créditos ativos (habitação, consumo, cartões). O mapa deve ter data recente (últimos 30 dias).',
    },
    {
      id: 'irs',
      title: 'IRS (Declaração de IRS)',
      content: 'Necessita da última declaração de IRS entregue às Finanças. Pode obter automaticamente através do botão "Obter IRS" acima, ou descarregar do Portal das Finanças (www.portaldasfinancas.gov.pt). Também pode enviar a Nota de Liquidação que recebeu das Finanças.',
    },
    {
      id: 'extratos',
      title: 'Extratos Bancários',
      content: 'São necessários os extratos bancários dos últimos 3 a 6 meses de todas as contas bancárias onde recebe vencimento ou tem despesas relevantes. Pode obter através da sua banca online ou app do banco. Formato PDF é preferível. Não é necessário enviar extratos de contas sem movimentos.',
    },
    {
      id: 'escritura',
      title: 'Escritura / CPCV',
      content: 'Se já tem um imóvel identificado, necessita da Cópia do Contrato de Promessa de Compra e Venda (CPCV) ou da Escritura de Compra e Venda. Este documento é fornecido pelo vendedor ou pelo notário. Inclui o valor do imóvel, prazos e condições.',
    },
  ];

  return (
    <ClientOnly>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent title="Ajuda com Documentos" description="Guia de ajuda para cada tipo de documento" className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <HelpCircle className="w-5 h-5 text-teal-500" />
              Ajuda com Documentos
            </DialogTitle>
            <DialogDescription className="text-xs text-gray-500">
              Clique em cada documento para ver detalhes e como obtê-lo.
            </DialogDescription>
          </DialogHeader>

          <Suspense fallback={<LoaderFallback />}>
            <Accordion type="single" collapsible className="w-full">
              {helpItems.map((item) => (
                <AccordionItem key={item.id} value={item.id}>
                  <AccordionTrigger className="text-sm text-gray-700 hover:text-emerald-700 hover:no-underline">
                    {item.title}
                  </AccordionTrigger>
                  <AccordionContent className="text-xs text-gray-600 leading-relaxed">
                    {item.content}
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </Suspense>

          <DialogFooter>
            <button onClick={() => onOpenChange(false)}
              className="px-4 py-2 text-sm font-medium bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors">
              Fechar
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </ClientOnly>
  );
}

function DocumentsPanel({ documents, onUploadSuccess }) {
  const { requested = [], received = [], has_pending } = documents || {};
  const [credDialogSource, setCredDialogSource] = useState(null); // 'financas' | 'seguranca_social' | null
  const [helpOpen, setHelpOpen] = useState(false);
  const [scraperAvailable, setScraperAvailable] = useState(null); // null=unchecked, true/false
  const [checkingScraper, setCheckingScraper] = useState(false);

  // Check scraper availability on mount
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/portal/scraper-status`);
        // 401 means the endpoint is auth-protected (shouldn't be, but handle gracefully)
        // 503 means server is still starting — don't assume scraper is down
        if (!res.ok) {
          if (!cancelled) setScraperAvailable(res.status === 503 ? null : false);
          return;
        }
        const data = await res.json();
        if (!cancelled) setScraperAvailable(data.available === true);
      } catch {
        // Network error — server might be waking up, don't assume it's down
        if (!cancelled) setScraperAvailable(null);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Re-check scraper when user clicks the button (may have become available after cold start)
  const handleOpenCredDialog = async (source) => {
    if (scraperAvailable === false) {
      setCheckingScraper(true);
      try {
        const res = await fetch(`${BACKEND_URL}/portal/scraper-status`);
        if (res.ok) {
          const data = await res.json();
          const available = data.available === true;
          setScraperAvailable(available);
          if (available) {
            setCredDialogSource(source);
          }
        } else {
          // Server responding but not 200 — might be waking up
          // Still let user try (they'll get a clear error if scraper is truly down)
          setScraperAvailable(null);
          setCredDialogSource(source);
        }
      } catch {
        // Server might be waking up — still let user try
        setScraperAvailable(null);
        setCredDialogSource(source);
      } finally {
        setCheckingScraper(false);
      }
    } else {
      setCredDialogSource(source);
    }
  };

  return (
    <div className="space-y-4">
      {/* Pending / Requested */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
        <h3 className="text-base font-bold text-gray-800 mb-1 flex items-center gap-2">
          <FileUp className="w-5 h-5 text-orange-500" />
          Documentos Pendentes
        </h3>
        <p className="text-sm text-gray-500 mb-4">
          Submeta os documentos solicitados para avançar com o seu processo.
        </p>

        {/* ── Auto-fetch buttons (Finanças + Seg. Social) ── */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-4">
          <button
            onClick={() => handleOpenCredDialog('financas')}
            disabled={checkingScraper}
            className="flex items-center gap-2 px-3 py-2.5 text-xs font-medium bg-teal-50 text-teal-800 border border-teal-200 rounded-xl hover:bg-teal-100 hover:border-teal-300 transition-all disabled:opacity-50 disabled:cursor-wait"
          >
            {checkingScraper ? <Loader2 className="w-4 h-4 flex-shrink-0 animate-spin" /> : <Landmark className="w-4 h-4 flex-shrink-0" />}
            Obter IRS e Nota de Liquidação (Finanças)
          </button>
          <button
            onClick={() => handleOpenCredDialog('seguranca_social')}
            disabled={checkingScraper}
            className="flex items-center gap-2 px-3 py-2.5 text-xs font-medium bg-rose-50 text-rose-800 border border-rose-200 rounded-xl hover:bg-rose-100 hover:border-rose-300 transition-all disabled:opacity-50 disabled:cursor-wait"
          >
            {checkingScraper ? <Loader2 className="w-4 h-4 flex-shrink-0 animate-spin" /> : <HeartPulse className="w-4 h-4 flex-shrink-0" />}
            Obter Documentos da Segurança Social
          </button>
        </div>

        {/* Scraper unavailable warning */}
        {scraperAvailable === false && !checkingScraper && (
          <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg p-3 mb-4">
            <AlertCircle className="w-4 h-4 text-amber-600 mt-0.5 flex-shrink-0" />
            <p className="text-xs text-amber-700">
              <strong>Obtenção automática indisponível.</strong> O serviço de download automático não está disponível de momento. Por favor, faça download manualmente dos portais e envie os documentos através do botão de upload.
            </p>
          </div>
        )}

        {has_pending && requested.length > 0 ? (
          <div className="space-y-2">
            {requested.map((doc) => (
              <DocumentUploadItem key={doc.id || doc.category} doc={doc} onUploadSuccess={onUploadSuccess} />
            ))}
          </div>
        ) : (
          <div className="text-center py-6">
            <CheckCircle2 className="w-10 h-10 text-emerald-500 mx-auto mb-2" />
            <p className="text-sm text-emerald-700 font-medium">Todos os documentos foram submetidos</p>
          </div>
        )}

        {/* Help button */}
        <button
          onClick={() => setHelpOpen(true)}
          className="mt-4 flex items-center gap-1.5 text-xs text-gray-400 hover:text-teal-600 transition-colors"
        >
          <HelpCircle className="w-3.5 h-3.5" />
          Precisa de ajuda com os documentos?
        </button>
      </div>

      {/* Credentials Dialog */}
      <CredentialsDialog
        open={credDialogSource !== null}
        onOpenChange={(v) => { if (!v) setCredDialogSource(null); }}
        source={credDialogSource}
        onSuccess={onUploadSuccess}
      />

      {/* Document Help Dialog */}
      <DocumentHelpDialog
        open={helpOpen}
        onOpenChange={setHelpOpen}
      />

      {/* Documentos Recebidos (via portal ou admin) */}
      {received && received.length > 0 && (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
          <h3 className="text-base font-bold text-gray-800 mb-3 flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-teal-500" />
            Documentos Recebidos ({received.length})
          </h3>
          <p className="text-xs text-gray-400 mb-3">Documentos submetidos e já recebidos pela nossa equipa. Clique no ícone para descarregar.</p>
          <div className="space-y-2 max-h-80 overflow-y-auto">
            {received.map((doc) => (
              <div key={doc.id} className="flex items-center gap-3 p-2.5 rounded-lg bg-teal-50/50 hover:bg-teal-50 transition-colors group">
                <span className="text-base flex-shrink-0">{doc.icon || '📄'}</span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-gray-700 truncate font-medium">{typeof doc.filename === 'string' ? doc.filename : String(doc.filename || '')}</p>
                  <p className="text-xs text-gray-400">
                    {typeof (doc.category_label || doc.category) === 'string' ? (doc.category_label || doc.category) : String(doc.category_label || doc.category || '')}
                    {doc.received_at && ` · ${formatDate(doc.received_at)}`}
                    {doc.file_size && ` · ${(doc.file_size / 1024).toFixed(0)} KB`}
                  </p>
                </div>
                {/* Botão Download — chama /portal/download-url com o token de sessão */}
                {doc.s3_path ? (
                  <button
                    onClick={async () => {
                      try {
                        const token = getPortalToken();
                        if (!token) { toast.error('Sessão expirada.'); return; }
                        const res = await fetchWithRetry(
                          `${BACKEND_URL}/portal/download-url?file_key=${encodeURIComponent(doc.s3_path)}`,
                          { headers: { Authorization: `Bearer ${token}` } }
                        );
                        const data = await res.json().catch(() => ({}));
                        if (res.ok && data.url) {
                          window.open(data.url, '_blank', 'noopener');
                        } else {
                          toast.error(extractErrorMessage(data.detail, 'Erro ao gerar link de download.'));
                        }
                      } catch (err) {
                        toast.error('Erro de ligação ao tentar descarregar.');
                      }
                    }}
                    className="flex-shrink-0 p-1.5 rounded-lg text-teal-500 hover:bg-teal-100 hover:text-teal-700 transition-colors opacity-60 group-hover:opacity-100"
                    title="Descarregar documento"
                  >
                    <Download className="w-4 h-4" />
                  </button>
                ) : (
                  <Check className="w-4 h-4 text-teal-500 flex-shrink-0" />
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ====================================================================
// TEAM CARD — Shows consultants and mediadores
// ====================================================================
function TeamCard({ team, consultor }) {
  const consultores = team?.consultores || [];
  const mediadores = team?.mediadores || [];
  const allContacts = [...consultores, ...mediadores];

  if (allContacts.length === 0 && !consultor) return null;

  // Fallback for backward compat (single consultor object)
  const displayContacts = allContacts.length > 0 ? allContacts : (consultor ? [consultor] : []);

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
      <h3 className="text-base font-bold text-gray-800 mb-4">A sua Equipa</h3>
      <div className="space-y-3">
        {displayContacts.map((contact, i) => (
          <ContactCard key={contact.name || i} contact={contact} />
        ))}
      </div>
    </div>
  );
}

function ContactCard({ contact }) {
  // Normalizar número para WhatsApp: remover +351/00351 duplicados
  let whatsappUrl = null;
  if (contact.phone) {
    let digits = contact.phone.replace(/\D/g, '');
    // Se já tem o indicativo 351 no início (com 12 dígitos: 351 + 9 do telemóvel), remover
    if (digits.startsWith('351') && digits.length === 12) {
      digits = digits.slice(3);
    }
    whatsappUrl = `https://wa.me/351${digits}`;
  }
  const initials = contact.name ? contact.name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2) : '?';
  const roleLabel = contact.role ? contact.role.charAt(0).toUpperCase() + contact.role.slice(1) : 'Power Precision';

  return (
    <div className="flex items-center gap-3">
      <div className="w-10 h-10 bg-gradient-to-br from-emerald-500 to-teal-600 rounded-xl flex items-center justify-center text-white font-bold text-xs shadow-md flex-shrink-0">
        {initials}
      </div>
      <div className="flex-1 min-w-0">
        <p className="font-semibold text-gray-800 text-sm truncate">{contact.name}</p>
        <p className="text-xs text-gray-400">{roleLabel}</p>
      </div>
      <div className="flex items-center gap-1.5 flex-shrink-0">
        {contact.phone && (
          <a href={`tel:${contact.phone}`} className="p-2 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors" title="Telefone">
            <Phone className="w-4 h-4 text-emerald-600" />
          </a>
        )}
        {contact.email && (
          <a href={`mailto:${contact.email}`} className="p-2 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors" title="Email">
            <Mail className="w-4 h-4 text-blue-600" />
          </a>
        )}
        {whatsappUrl && (
          <a href={whatsappUrl} target="_blank" rel="noopener noreferrer" className="p-2 bg-green-50 rounded-lg hover:bg-green-100 transition-colors" title="WhatsApp">
            <MessageCircle className="w-4 h-4 text-green-600" />
          </a>
        )}
      </div>
    </div>
  );
}

// ====================================================================
// PORTAL MESSAGES — Chat interface for client ↔ staff communication
// ====================================================================
function PortalMessages({ messages, loading, newMessage, setNewMessage, onSend, sending, unreadCount, isInSheet, welcomeMessage }) {
  const messagesEndRef = useRef(null);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Relative timestamp in Portuguese
  const formatRelativeTime = (isoDate) => {
    if (!isoDate) return '';
    const date = safeDate(isoDate);
    if (!date) return '';
    const now = new Date();
    const diffMs = now - date;
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHour = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHour / 24);

    if (diffSec < 60) return 'agora mesmo';
    if (diffMin < 60) return `há ${diffMin} min`;
    if (diffHour < 24) return `há ${diffHour} hora${diffHour > 1 ? 's' : ''}`;
    if (diffDay === 1) return 'ontem';
    if (diffDay < 7) return `há ${diffDay} dias`;
    return formatDate(isoDate);
  };

  // In Sheet mode: no card wrapper, fill full height, hide header (Sheet provides it)
  const containerClass = isInSheet
    ? 'flex flex-col h-full px-5 pb-5'
    : 'bg-white rounded-2xl shadow-sm border border-gray-100 p-5 flex flex-col min-h-[400px] lg:h-[650px]';

  return (
    <div className={containerClass}>
      {/* Header — hidden in Sheet (Sheet has its own) */}
      {!isInSheet && (
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-base font-bold text-gray-800 flex items-center gap-2">
            <MessageCircle className="w-5 h-5 text-emerald-500" />
            Mensagens
          </h3>
          {unreadCount > 0 && (
            <span className="inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full bg-emerald-500 text-white text-xs font-bold">
              {unreadCount}
            </span>
          )}
        </div>
      )}

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto space-y-3 min-h-0 mb-3 pr-1" style={{ scrollbarWidth: 'thin' }}>
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-5 h-5 text-emerald-500 animate-spin mr-2" />
            <span className="text-sm text-gray-500">A carregar mensagens...</span>
          </div>
        ) : (
          <>
            {/* Welcome message as the first message in the chat */}
            {welcomeMessage && (
              <div className="flex justify-start">
                <div className="max-w-[80%] rounded-2xl px-4 py-2.5 bg-gray-100 border border-gray-200">
                  <p className="text-xs font-semibold text-gray-600 mb-0.5">PowerCell</p>
                  <p className="text-sm text-gray-800 whitespace-pre-wrap">{welcomeMessage}</p>
                </div>
              </div>
            )}
            {messages.length === 0 && !welcomeMessage && (
              <div className="flex flex-col items-center justify-center py-8 text-center">
                <MessageCircle className="w-10 h-10 text-gray-300 mb-2" />
                <p className="text-sm text-gray-400">Sem mensagens ainda. Envie a primeira!</p>
              </div>
            )}
            {messages.map((msg) => {
              const isClient = msg.sender_type === 'client';
              return (
                <div key={msg.id} className={`flex ${isClient ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[80%] rounded-2xl px-4 py-2.5 ${
                    isClient
                      ? 'bg-emerald-50 border border-emerald-200 text-right'
                      : 'bg-gray-100 border border-gray-200'
                  }`}>
                    {!isClient && msg.sender_name && (
                      <p className="text-xs font-semibold text-gray-600 mb-0.5">{msg.sender_name}</p>
                    )}
                    <p className="text-sm text-gray-800 whitespace-pre-wrap">{msg.content}</p>
                    <p className={`text-[10px] mt-1 ${isClient ? 'text-emerald-500' : 'text-gray-400'}`}>
                      {formatRelativeTime(msg.created_at)}
                    </p>
                  </div>
                </div>
              );
            })}
          </>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="flex items-center gap-2 pt-2 border-t border-gray-100">
        <input
          type="text"
          value={newMessage}
          onChange={(e) => setNewMessage(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && newMessage.trim()) { e.preventDefault(); onSend(); } }}
          placeholder="Escreva uma mensagem..."
          className="flex-1 px-4 py-2.5 text-sm bg-gray-50 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-400 focus:border-transparent transition-all"
          disabled={sending}
        />
        <button
          onClick={onSend}
          disabled={sending || !newMessage.trim()}
          className="p-2.5 bg-emerald-600 text-white rounded-xl hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex-shrink-0"
          title="Enviar"
        >
          {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
        </button>
      </div>
    </div>
  );
}

// ====================================================================
// PROFILE PANEL — "O Meu Perfil" tab content
// ====================================================================
function ProfilePanel() {
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [saveResult, setSaveResult] = useState(null);
  const [formData, setFormData] = useState({
    // Contacto
    email: '',
    email_secundario: '',
    telefone: '',
    telefone_secundario: '',
    // Dados Pessoais
    morada_fiscal: '',
    estado_civil: '',
    profissao: '',
    naturalidade: '',
    nacionalidade: '',
    data_nascimento: '',
    documento_id: '',
    data_validade_cc: '',
    sexo: '',
  });

  // ── Fetch profile data ──
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const token = getPortalToken();
        if (!token) throw new Error('Sessão expirada.');

        const res = await fetchWithRetry(`${BACKEND_URL}/portal/me`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (cancelled) return;

        if (!res.ok) {
          const e = await res.json().catch(() => ({}));
          throw new Error(e.detail || 'Erro ao carregar perfil.');
        }

        const data = await res.json();
        if (cancelled) return;

        setProfile(data);
        setFormData({
          email: data.contacto?.email || '',
          email_secundario: data.contacto?.email_secundario || '',
          telefone: data.contacto?.telefone || '',
          telefone_secundario: data.contacto?.telefone_secundario || '',
          morada_fiscal: data.dados_pessoais?.morada_fiscal || '',
          estado_civil: data.dados_pessoais?.estado_civil || '',
          profissao: data.dados_pessoais?.profissao || '',
          naturalidade: data.dados_pessoais?.naturalidade || '',
          nacionalidade: data.dados_pessoais?.nacionalidade || '',
          data_nascimento: data.dados_pessoais?.data_nascimento || data.dados_pessoais?.birth_date || '',
          documento_id: data.dados_pessoais?.documento_id || '',
          data_validade_cc: data.dados_pessoais?.data_validade_cc || '',
          sexo: data.dados_pessoais?.sexo || '',
        });
      } catch (err) {
        if (!cancelled) setError(err.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    setSaveResult(null);
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSaveResult(null);

    try {
      const token = getPortalToken();
      if (!token) throw new Error('Sessão expirada.');

      const payload = {
        contacto: {
          email: formData.email || null,
          email_secundario: formData.email_secundario || null,
          telefone: formData.telefone || null,
          telefone_secundario: formData.telefone_secundario || null,
        },
        dados_pessoais: {
          morada_fiscal: formData.morada_fiscal || null,
          estado_civil: formData.estado_civil || null,
          profissao: formData.profissao || null,
          naturalidade: formData.naturalidade || null,
          nacionalidade: formData.nacionalidade || null,
          data_nascimento: formData.data_nascimento || null,
          documento_id: formData.documento_id || null,
          data_validade_cc: formData.data_validade_cc || null,
          sexo: formData.sexo || null,
        },
      };

      const res = await fetchWithRetry(`${BACKEND_URL}/portal/me`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      });

      const data = await res.json().catch(() => ({}));

      if (res.status === 403) {
        setError(typeof data.detail === 'string' ? data.detail : 'Dados trancados. Processo já em análise.');
        return;
      }

      if (!res.ok) {
        throw new Error(data.detail || 'Erro ao guardar perfil.');
      }

      setSaveResult({ success: true, message: data.message || 'Perfil atualizado com sucesso.' });
      toast.success('Perfil atualizado com sucesso!');
    } catch (err) {
      setError(err.message);
      setSaveResult({ success: false, message: err.message });
    } finally {
      setSaving(false);
    }
  };

  const isLocked = profile?.has_process === true;

  if (loading) {
    return (
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-8">
        <div className="flex items-center justify-center gap-2 text-sm text-gray-400">
          <Loader2 className="w-5 h-5 animate-spin text-blue-500" />
          A carregar o seu perfil...
        </div>
      </div>
    );
  }

  if (error && !profile) {
    return (
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-8">
        <div className="flex items-start gap-2 text-sm text-red-600 bg-red-50 rounded-lg px-4 py-3">
          <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      </div>
    );
  }

  // ── Field component for consistency ──
  const Field = ({ label, field, type = 'text', placeholder = '', options = null }) => (
    <div>
      <label className="text-xs font-medium text-gray-600 mb-1 block">{label}</label>
      {options ? (
        <select
          value={formData[field]}
          onChange={(e) => handleChange(field, e.target.value)}
          disabled={isLocked}
          className={`w-full px-3 py-2 text-sm border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent transition-colors ${
            isLocked ? 'bg-gray-50 text-gray-400 border-gray-100 cursor-not-allowed' : 'border-gray-200 bg-white'
          }`}
        >
          <option value="">—</option>
          {options.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      ) : (
        <input
          type={type}
          value={formData[field]}
          onChange={(e) => handleChange(field, e.target.value)}
          placeholder={placeholder}
          disabled={isLocked}
          className={`w-full px-3 py-2 text-sm border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent transition-colors ${
            isLocked ? 'bg-gray-50 text-gray-400 border-gray-100 cursor-not-allowed' : 'border-gray-200 bg-white'
          }`}
        />
      )}
    </div>
  );

  return (
    <div className="space-y-5">
      {/* ── Banner de bloqueio condicional ── */}
      {isLocked && (
        <div className="bg-blue-50 border border-blue-200 rounded-2xl p-5 sm:p-6">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center flex-shrink-0">
              <Lock className="w-5 h-5 text-blue-600" />
            </div>
            <div className="flex-1">
              <h3 className="text-sm font-bold text-blue-800">Processo em Análise</h3>
              <p className="text-xs text-blue-600 mt-0.5">
                O seu processo já se encontra em análise pela nossa equipa. Os dados estão protegidos e não podem ser alterados.
              </p>
              <p className="text-xs text-blue-500 mt-1">
                Se precisar de corrigir algum dado, contacte o seu consultor através do chat.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* ── Perfil editável (quando não tem processo) ── */}
      {!isLocked && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-2xl p-5 sm:p-6">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 bg-emerald-100 rounded-full flex items-center justify-center flex-shrink-0">
              <User className="w-5 h-5 text-emerald-600" />
            </div>
            <div className="flex-1">
              <h3 className="text-sm font-bold text-emerald-800">Complete o seu Perfil</h3>
              <p className="text-xs text-emerald-600 mt-0.5">
                Preencha os seus dados pessoais para agilizar o processo. Assim que o seu processo for criado, os dados ficarão protegidos.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* ── Nome (read-only, nunca editável pelo cliente) ── */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 sm:p-6">
        <h3 className="text-base font-bold text-gray-800 mb-4 flex items-center gap-2">
          <User className="w-5 h-5 text-blue-500" />
          Dados Pessoais
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Nome — read-only */}
          <div className="sm:col-span-2">
            <label className="text-xs font-medium text-gray-600 mb-1 block">Nome Completo</label>
            <input
              type="text"
              value={profile?.nome || ''}
              disabled
              className="w-full px-3 py-2 text-sm border border-gray-100 rounded-lg bg-gray-50 text-gray-400 cursor-not-allowed"
            />
            <p className="text-[10px] text-gray-400 mt-0.5">O nome não pode ser alterado. Contacte o seu consultor se precisar.</p>
          </div>

          <Field label="Data de Nascimento" field="data_nascimento" type="date" />
          <Field
            label="Estado Civil"
            field="estado_civil"
            options={[
              { value: 'solteiro', label: 'Solteiro(a)' },
              { value: 'casado', label: 'Casado(a)' },
              { value: 'divorciado', label: 'Divorciado(a)' },
              { value: 'viuvo', label: 'Viúvo(a)' },
              { value: 'uniao_de_facto', label: 'União de Facto' },
              { value: 'separado', label: 'Separado(a)' },
            ]}
          />
          <Field label="Nacionalidade" field="nacionalidade" placeholder="Portuguesa" />
          <Field label="Naturalidade" field="naturalidade" placeholder="Lisboa" />
          <Field label="Profissão" field="profissao" placeholder="Engenheiro(a)" />
          <Field
            label="Sexo"
            field="sexo"
            options={[
              { value: 'M', label: 'Masculino' },
              { value: 'F', label: 'Feminino' },
            ]}
          />
        </div>
      </div>

      {/* ── Documento de Identificação ── */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 sm:p-6">
        <h3 className="text-base font-bold text-gray-800 mb-4 flex items-center gap-2">
          <Shield className="w-5 h-5 text-teal-500" />
          Documento de Identificação
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Nº do Documento (CC/Passaporte)" field="documento_id" placeholder="00000000" />
          <Field label="Validade do Documento" field="data_validade_cc" type="date" />
        </div>
      </div>

      {/* ── Morada ── */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 sm:p-6">
        <h3 className="text-base font-bold text-gray-800 mb-4 flex items-center gap-2">
          <MapPin className="w-5 h-5 text-rose-500" />
          Morada Fiscal
        </h3>
        <div className="grid grid-cols-1 gap-4">
          <Field label="Morada Fiscal" field="morada_fiscal" placeholder="Rua Exemplo, Nº 1, 1000-001 Lisboa" />
        </div>
      </div>

      {/* ── Contactos ── */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 sm:p-6">
        <h3 className="text-base font-bold text-gray-800 mb-4 flex items-center gap-2">
          <Phone className="w-5 h-5 text-violet-500" />
          Contactos
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Email Principal" field="email" type="email" placeholder="email@exemplo.pt" />
          <Field label="Email Secundário" field="email_secundario" type="email" placeholder="email2@exemplo.pt" />
          <Field label="Telefone" field="telefone" type="tel" placeholder="912345678" />
          <Field label="Telefone Secundário" field="telefone_secundario" type="tel" placeholder="912345678" />
        </div>
      </div>

      {/* ── Botão Guardar (só visível se NÃO bloqueado) ── */}
      {!isLocked && (
        <div className="flex items-center justify-end gap-3">
          {saveResult?.success && (
            <div className="flex items-center gap-1.5 text-sm text-emerald-600">
              <CheckCircle2 className="w-4 h-4" />
              <span>{saveResult.message}</span>
            </div>
          )}
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-2 px-6 py-2.5 text-sm font-semibold bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
          >
            {saving ? (
              <><Loader2 className="w-4 h-4 animate-spin" /> A guardar...</>
            ) : (
              <><Save className="w-4 h-4" /> Guardar Alterações</>
            )}
          </button>
        </div>
      )}

      {/* ── Erro de atualização (ex: 403 bloqueado) ── */}
      {error && profile && (
        <div className="flex items-start gap-1.5 text-xs text-red-600 bg-red-50 rounded-lg px-4 py-2.5">
          <AlertCircle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}


// ====================================================================
// IFRAME DETECTOR (non-intrusive)
// ====================================================================
function IframeDetector({ children }) {
  const [isIframe, setIsIframe] = useState(false);
  useEffect(() => {
    try { setIsIframe(window.self !== window.top); } catch { setIsIframe(true); }
  }, []);

  if (!isIframe) return children;

  const url = window.self.location.href;
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-lg p-8 max-w-md w-full text-center">
        <div className="w-16 h-16 bg-emerald-100 rounded-full flex items-center justify-center mx-auto mb-4">
          <Shield className="w-8 h-8 text-emerald-600" />
        </div>
        <h2 className="text-xl font-bold text-gray-800 mb-2">Portal do Cliente</h2>
        <p className="text-gray-600 mb-6">Para aceder ao seu portal de forma segura, abra o link diretamente no seu navegador.</p>
        <a href={url} target="_blank" rel="noopener noreferrer"
          className="inline-flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold py-3 px-6 rounded-xl transition-colors">
          Abrir no Browser <ChevronRight className="w-5 h-5" />
        </a>
        <p className="text-xs text-gray-400 mt-4">Power Precision · Crédito Habitação</p>
      </div>
    </div>
  );
}

// ====================================================================
// PORTAL LOGIN SCREEN — Ecrã de login obrigatório
// ====================================================================
function PortalLoginScreen({ onLoginSuccess, client_id }) {
  const [nif, setNif] = useState('');
  const [processNumber, setProcessNumber] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showNif, setShowNif] = useState(false);

  const handleSubmit = async (e) => {
    e?.preventDefault();
    setError(null);

    const cleanNif = nif.replace(/\D/g, '');
    if (cleanNif.length !== 9) {
      setError('O NIF deve conter exatamente 9 dígitos.');
      return;
    }
    if (!processNumber || isNaN(Number(processNumber))) {
      setError('O Número do Processo é obrigatório e deve ser um número.');
      return;
    }

    setLoading(true);
    try {
      // Determinar o client_id para o endpoint de verificação
      // Pode vir da URL ou do localStorage (após resolver magic link)
      const cid = client_id || localStorage.getItem('portal_client_id');

      if (!cid) {
        setError('Identificação do cliente não encontrada. Aceda através do link fornecido pelo consultor.');
        setLoading(false);
        return;
      }

      const res = await fetchWithRetry(`${BACKEND_URL}/portal/${cid}/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          nif: cleanNif,
          process_number: Number(processNumber),
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
        // Guardar o token de sessão verificada no localStorage
        // (persiste entre tabs e reloads, ao contrário de localStorage)
        localStorage.setItem('portal_token', data.token);
        localStorage.setItem('portal_verified', 'true');
        localStorage.setItem('portal_client_name', data.client_name || '');
        localStorage.setItem('portal_process_id', data.process_id || '');
        if (cid) localStorage.setItem('portal_client_id', cid);

        if (onLoginSuccess) {
          onLoginSuccess(data.token);
        }
      } else {
        setError(typeof data.detail === 'string' ? data.detail : 'Credenciais inválidas. Verifique o seu NIF e Número de Processo.');
      }
    } catch (err) {
      setError(err.message || 'Erro de ligação. Tente novamente.');
    } finally {
      setLoading(false);
    }
  };

  return (
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
            <div className="w-16 h-16 bg-gradient-to-br from-emerald-500 to-teal-600 rounded-2xl flex items-center justify-center mx-auto mb-4 shadow-lg">
              <Shield className="w-8 h-8 text-white" />
            </div>
            <h1 className="text-xl font-bold text-gray-900">Portal do Cliente</h1>
            <p className="text-sm text-gray-500 mt-1">
              Introduza as suas credenciais para aceder ao seu processo
            </p>
          </div>

          {/* Security notice */}
          <div className="flex items-start gap-2 bg-emerald-50 border border-emerald-200 rounded-lg p-3 mb-5">
            <Shield className="w-4 h-4 text-emerald-600 mt-0.5 flex-shrink-0" />
            <p className="text-xs text-emerald-700">
              <strong>Acesso seguro.</strong> Os seus dados são encriptados e nunca são partilhados.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* NIF */}
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

            {/* Número do Processo */}
            <div>
              <label className="text-sm font-medium text-gray-700 mb-1.5 block">
                Número do Processo
              </label>
              <input
                type="text"
                value={processNumber}
                onChange={(e) => setProcessNumber(e.target.value.replace(/\D/g, ''))}
                placeholder="Ex: 1001"
                className="w-full px-4 py-3 text-sm border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-400 focus:border-transparent transition-all"
                inputMode="numeric"
                disabled={loading}
              />
              <p className="text-[10px] text-gray-400 mt-1">
                Fornecido pelo seu consultor (ex: nº do processo no CRM)
              </p>
            </div>

            {/* Error message */}
            {error && (
              <div className="flex items-start gap-2 text-xs text-red-600 bg-red-50 rounded-xl px-4 py-3 border border-red-200">
                <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {/* Submit button */}
            <button
              type="submit"
              disabled={loading || nif.length !== 9 || !processNumber}
              className="w-full py-3 text-sm font-semibold bg-gradient-to-r from-emerald-600 to-teal-600 text-white rounded-xl hover:from-emerald-700 hover:to-teal-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-md hover:shadow-lg flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  A verificar...
                </>
              ) : (
                <>
                  <Shield className="w-4 h-4" />
                  Entrar no Portal
                </>
              )}
            </button>
          </form>
        </div>

        {/* Footer */}
        <div className="text-center mt-6">
          <p className="text-xs text-gray-400">
            Não tem as suas credenciais? Contacte o seu consultor.
          </p>
          <div className="flex items-center justify-center gap-1.5 mt-2 text-xs text-gray-400">
            <Shield className="w-3 h-3" />
            <span>Ligação segura e encriptada</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ====================================================================
// MAIN CLIENT PORTAL
// ====================================================================
export default function ClientPortal() {
  const [loading, setLoading] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState('A carregar o seu processo...');
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);

  // ── Login obrigatório ──
  const [isVerified, setIsVerified] = useState(false);
  const [autoLoginAttempted, setAutoLoginAttempted] = useState(false);

  // AUTO-LOGIN VIA TOKEN NA QUERY STRING (Pacote M, Fix #1)
  // O endpoint /api/portal/impersonate/{id} (backend/routes/portal.py)
  // devolve um URL com o JWT na query string (?token=...). Este useEffect
  // intercepta esse parâmetro (e variantes ?magic_link=/?access_token=),
  // guarda o token, limpa a URL e faz setIsVerified(true) para saltar
  // o ecrã de login. Resolve o bug "Ver como Cliente" em que o utilizador
  // ficava retido no login mesmo tendo clicado o magic link.
  useEffect(() => {
    if (autoLoginAttempted) return; // idempotente — só corre uma vez

    const searchParams = new URLSearchParams(window.location.search);
    const rawToken =
      searchParams.get('token') || searchParams.get('magic_link') || searchParams.get('access_token');
    if (!rawToken) return;

    setAutoLoginAttempted(true);

    (async () => {
      try {
        let jwtToken = rawToken;
        // Se o token não tem '.' não é um JWT — pode ser um short_id (8 chars)
        // que precisa de ser resolvido via /portal/resolve/{short_id}
        if (!rawToken.includes('.')) {
          const resolveRes = await fetch(`/api/portal/resolve/${rawToken}`);
          if (!resolveRes.ok) throw new Error('resolve failed');
          const resolveData = await resolveRes.json();
          jwtToken = resolveData.token || resolveData.access_token || rawToken;
        }
        // Guardar o token em localStorage (lido pelo apiClient do Portal)
        localStorage.setItem('portalToken', jwtToken);
        localStorage.setItem('portal_token', jwtToken);
        localStorage.setItem('portalAuthMethod', 'magic_link_impersonate');
        localStorage.setItem('portal_verified', 'true');
        localStorage.setItem('portalLastActivity', Date.now().toString());
        sessionStorage.removeItem('portalAuthMethod');

        // Limpar o token da URL (segurança — não fica no histórico do browser)
        window.history.replaceState({}, document.title, window.location.pathname);

        // Saltar o ecrã de login — o useEffect de data-fetch existente
        // vai carregar /portal/status com o token guardado.
        setIsVerified(true);
      } catch (err) {
        console.error('[ClientPortal] Auto-login falhou:', err);
        localStorage.removeItem('portalToken');
        localStorage.removeItem('portal_token');
        localStorage.removeItem('portalAuthMethod');
        setAutoLoginAttempted(true);
      }
    })();
  }, [autoLoginAttempted]);
  const [clientId, setClientId] = useState(null);

  const rawToken = useRef(window.location.pathname.split('/portal/')[1]);

  // ── Sliding Session — auto-logout após 15 min de inactividade ──
  const { logout: sessionLogout } = useSlidingSession({
    onExpired: () => {
      setIsVerified(false);
      setData(null);
    },
  });

  // Verificar se já tem sessão verificada — validar token no backend
  // (nunca confiar apenas na presença do token; pode ter expirado)
  // Suporta localStorage (Código de Acesso v4) e sessionStorage legado (OTP v3)
  useEffect(() => {
    let cancelled = false;
    const token = getPortalToken();

    if (!token) return;

    // Tem token — validar no backend antes de conceder acesso
    (async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/portal/status`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (cancelled) return;

        if (res.ok) {
          // Token válido — auto-verificar e registar actividade
          setIsVerified(true);
          localStorage.setItem('portalLastActivity', String(Date.now()));
        } else {
          // Token inválido/expirado — limpar sessão e mostrar login
          localStorage.removeItem('portalToken');
          localStorage.removeItem('portalClientId');
          localStorage.removeItem('portalClientName');
          localStorage.removeItem('portalProcessId');
          localStorage.removeItem('portalAuthMethod');
          localStorage.removeItem('portalLastActivity');
          localStorage.removeItem('portal_token');
          localStorage.removeItem('portal_verified');
          localStorage.removeItem('portal_client_id');
          localStorage.removeItem('portal_client_name');
          localStorage.removeItem('portal_process_id');
          sessionStorage.removeItem('portalToken');
          sessionStorage.removeItem('portalClientId');
          sessionStorage.removeItem('portalAuthMethod');
          sessionStorage.removeItem('portalVerified');
        }
      } catch {
        // Erro de rede — não limpar sessão, pode ser temporário
      }
    })();

    return () => { cancelled = true; };
  }, []);

  // Extrair client_id da URL (para o login screen)
  useEffect(() => {
    const urlPart = rawToken.current;
    if (urlPart) {
      // Se é um UUID (client_id), guardar
      const isUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(urlPart);
      if (isUuid) {
        setClientId(urlPart);
        localStorage.setItem('portal_client_id', urlPart);
      }
    }
  }, []);

  // ── Resolve magic link (apenas extrai client_id, NÃO carrega dados) ──
  // Os dados do portal só são carregados APÓS o login ser verificado.
  // Se não há token na URL (fluxo OTP via /portal), simplesmente ignorar.
  useEffect(() => {
    let cancelled = false;
    const token = rawToken.current;

    if (!token) {
      // Sem token na URL — fluxo OTP normal (/portal), não fazer nada
      setLoading(false);
      return;
    }

    const isShortToken = !token.includes('.');

    const init = async () => {
      try {
        if (isShortToken) {
          // Resolver magic link para obter client_id (não carregar dados ainda)
          const ctrl = new AbortController();
          const t = setTimeout(() => ctrl.abort(), 15000);
          const r = await fetch(`${BACKEND_URL}/portal/resolve/${token}`, { signal: ctrl.signal });
          clearTimeout(t);
          if (cancelled) return;
          if (!r.ok) {
            const e = await r.json().catch(() => ({}));
            throw new Error(e.detail || 'Link não encontrado ou expirado');
          }
          const resolved = await r.json();
          if (cancelled) return;
          // Guardar client_id para o ecrã de login usar
          if (resolved.client_id) {
            setClientId(resolved.client_id);
            localStorage.setItem('portal_client_id', resolved.client_id);
          }
        } else {
          // Token JWT direto — guardar token e extrair client_id
          // (não carregar dados — o login ainda é obrigatório)
          localStorage.setItem('portal_token', token);
          // Extrair client_id do processo via /portal/status (sem mostrar dados)
          // Isto é necessário para o ecrã de login saber qual client_id verificar
          try {
            const ctrl2 = new AbortController();
            const t2 = setTimeout(() => ctrl2.abort(), 10000);
            const statusRes = await fetch(`${BACKEND_URL}/portal/status`, {
              headers: { Authorization: `Bearer ${token}` },
              signal: ctrl2.signal,
            });
            clearTimeout(t2);
            if (statusRes.ok) {
              const statusData = await statusRes.json();
              const cid = statusData?.process?.client_id;
              if (cid) {
                setClientId(cid);
                localStorage.setItem('portal_client_id', cid);
              }
            }
          } catch {
            // Se falhar, o utilizador pode ainda assim introduzir o client_id manualmente
          }
        }
      } catch (err) {
        if (cancelled) return;
        setError(err.name === 'AbortError' ? 'Ligação demorou demais. Tente novamente.' : err.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    init();
    return () => { cancelled = true; };
  }, []);

  // ── Carregar dados do portal APENAS quando isVerified for true ──
  useEffect(() => {
    if (!isVerified) return;
    let cancelled = false;

    const fetchStatus = async () => {
      const jwt = getPortalToken();
      if (!jwt) {
        setError('Sessão inválida. Recarregue a página.');
        setLoading(false);
        return;
      }

      setLoading(true);
      setLoadingMessage('A carregar o seu processo...');
      try {
        const ctrl = new AbortController();
        const t = setTimeout(() => ctrl.abort(), 20000);
        const res = await fetch(`${BACKEND_URL}/portal/status`, {
          headers: { Authorization: `Bearer ${jwt}` },
          signal: ctrl.signal,
        });
        clearTimeout(t);
        if (cancelled) return;
        if (!res.ok) {
          const e = await res.json().catch(() => ({}));
          throw new Error(e.detail || 'Erro ao carregar dados');
        }
        const result = await res.json();
        if (cancelled) return;
        setData(result);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError(err.name === 'AbortError' ? 'Ligação demorou demais. Tente novamente.' : err.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchStatus();
    return () => { cancelled = true; };
  }, [isVerified, refreshKey]);

  const handleUploadSuccess = useCallback(() => setRefreshKey((k) => k + 1), []);

  // ── Messaging state ──
  const [messages, setMessages] = useState([]);
  const [messagesLoading, setMessagesLoading] = useState(true);
  const [newMessage, setNewMessage] = useState('');
  const [sendingMessage, setSendingMessage] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isMobileChatOpen, setIsMobileChatOpen] = useState(false);

  // ── Recommended properties state ──
  const [recommendations, setRecommendations] = useState([]);
  const [recommendationsLoading, setRecommendationsLoading] = useState(true);

  // ── Tab navigation ──
  const [activeTab, setActiveTab] = useState('documentos'); // 'documentos' | 'visitas'

  // ── Visits state ──
  const [visits, setVisits] = useState([]);
  const [visitsLoading, setVisitsLoading] = useState(true);
  const [visitUrl, setVisitUrl] = useState('');
  const [requestingVisit, setRequestingVisit] = useState(false);
  const [visitRequestResult, setVisitRequestResult] = useState(null);

  const fetchMessages = useCallback(async () => {
    const token = getPortalToken();
    if (!token) return;
    try {
      const res = await fetch(`${BACKEND_URL}/portal/messages`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setMessages(Array.isArray(data) ? data : data.messages || []);
      }
    } catch {
      // silently fail — will retry on next poll
    } finally {
      setMessagesLoading(false);
    }
  }, []);

  const fetchUnreadCount = useCallback(async () => {
    const token = getPortalToken();
    if (!token) return;
    try {
      const res = await fetch(`${BACKEND_URL}/portal/messages/unread`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setUnreadCount(data.count ?? data.unread ?? 0);
      }
    } catch {
      // silently fail
    }
  }, []);

  const sendMessage = useCallback(async () => {
    if (!newMessage.trim()) return;
    const token = getPortalToken();
    if (!token) return;
    setSendingMessage(true);
    try {
      const res = await fetch(`${BACKEND_URL}/portal/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ content: newMessage.trim() }),
      });
      if (res.ok) {
        setNewMessage('');
        await fetchMessages();
      }
    } catch {
      // silently fail
    } finally {
      setSendingMessage(false);
    }
  }, [newMessage, fetchMessages]);

  // Fetch messages on mount and poll every 15s
  // CORREÇÃO: Só buscar mensagens quando isVerified === true.
  // Antes, este useEffect disparava no mount mesmo sem sessão verificada,
  // gerando 401s quando existia um token expirado em localStorage.
  useEffect(() => {
    if (!isVerified) return;
    fetchMessages();
    fetchUnreadCount();
    const interval = setInterval(() => {
      fetchMessages();
      fetchUnreadCount();
    }, 15000);
    return () => clearInterval(interval);
  }, [isVerified, fetchMessages, fetchUnreadCount]);

  // ── Fetch recommended properties ──
  const fetchRecommendations = useCallback(async () => {
    const token = getPortalToken();
    if (!token) return;
    try {
      const res = await fetch(`${BACKEND_URL}/portal/recommendations`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setRecommendations(data.recommendations || []);
      }
    } catch {
      // silently fail
    } finally {
      setRecommendationsLoading(false);
    }
  }, []);

  // CORREÇÃO: Só buscar recomendações quando isVerified === true.
  useEffect(() => {
    if (!isVerified) return;
    fetchRecommendations();
  }, [isVerified, fetchRecommendations]);

  // ── Fetch visits ──
  const fetchVisits = useCallback(async () => {
    const token = getPortalToken();
    if (!token) return;
    try {
      const res = await fetch(`${BACKEND_URL}/portal/visits`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setVisits(data.visits || []);
      }
    } catch {
      // silently fail
    } finally {
      setVisitsLoading(false);
    }
  }, []);

  // CORREÇÃO: Só buscar visitas quando isVerified === true.
  useEffect(() => {
    if (!isVerified) return;
    fetchVisits();
  }, [isVerified, fetchVisits]);

  // ── Welcome message (from API, already rendered with variables) ──
  // MUST be before early returns (Rules of Hooks)
  const welcomeMessage = useMemo(() => {
    // The backend returns welcome_message already with {{cliente}}, {{consultor}},
    // {{empresa}} replaced by the actual values. Fallback to nothing if not available.
    return data?.welcome_message || '';
  }, [data?.welcome_message]);

  // ── Login Gate — Se não está verificado, mostrar ecrã de login ──
  const handleLoginSuccess = useCallback((token) => {
    // Login verificado — o useEffect [isVerified, refreshKey] vai carregar os dados
    setIsVerified(true);
    // Registar actividade para o sliding session
    localStorage.setItem('portalLastActivity', String(Date.now()));
  }, []);

  if (!isVerified) {
    return (
      <ClientOnly>
        <ClientPortalLogin onLoginSuccess={handleLoginSuccess} />
      </ClientOnly>
    );
  }

  // ── Loading ──
  if (loading) {
    return (
      <IframeDetector>
        <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center p-4">
          <div className="text-center">
            <Loader2 className="w-10 h-10 text-emerald-600 animate-spin mx-auto mb-4" />
            <p className="text-gray-600 font-medium">{loadingMessage}</p>
          </div>
        </div>
      </IframeDetector>
    );
  }

  // ── Error ──
  if (error) {
    return (
      <IframeDetector>
        <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-lg p-8 max-w-md w-full text-center">
            <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <AlertCircle className="w-8 h-8 text-red-500" />
            </div>
            <h2 className="text-xl font-bold text-gray-800 mb-2">Link Inválido</h2>
            <p className="text-gray-600 mb-6">{error}</p>
            <p className="text-sm text-gray-400">Se precisa de acesso, contacte o seu consultor.</p>
          </div>
        </div>
      </IframeDetector>
    );
  }

  if (!data) return null;

  const { process, progress, stepper, documents, rgpd, team, consultor } = data;
  const currentStep = stepper?.find(s => s.is_current);
  const statusColor = currentStep ? stepColor(currentStep.color) : stepColor('green');

  return (
    <IframeDetector>
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-gray-100 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 shadow-sm sticky top-0 z-50">
        <div className="w-full px-4 sm:px-6 lg:px-10 py-3.5 flex items-center gap-3">
          <img
            src="/PowerCell-default.png"
            alt="PowerCell"
            className="h-10 w-auto object-contain flex-shrink-0"
          />
          <div className="flex-1 min-w-0">
            <h1 className="text-lg font-bold text-gray-800">PowerCell</h1>
            <p className="text-xs text-gray-400">Acompanhe o seu processo</p>
          </div>
          <div className="hidden sm:flex items-center gap-1.5 text-xs text-gray-400">
            <Shield className="w-3.5 h-3.5" />
            <span>Acesso Seguro</span>
          </div>
          {/* Botão Terminar Sessão */}
          {isVerified && (
            <button
              onClick={() => {
                sessionLogout(false); // false = sem toast (foi o utilizador que escolheu sair)
                setIsVerified(false);
                setData(null);
              }}
              className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-red-500 transition-colors ml-2"
              title="Terminar sessão"
            >
              <X className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Sair</span>
            </button>
          )}
        </div>
      </header>

      {/* Main Content — Top summary + stepper + 2-column body */}
      <main className="flex-1 w-full px-4 sm:px-6 lg:px-10 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">

          {/* ═══ TOP SECTION: Greeting + Horizontal Stepper (full width) ═══ */}
          <div className="lg:col-span-12 space-y-4">

            {/* Greeting + Status + Progress */}
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 sm:p-6">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-5">
                <div>
                  <p className="text-sm text-gray-400">Olá,</p>
                  <h2 className="text-2xl font-bold text-gray-900">{process.client_name || 'Cliente'}</h2>
                </div>
                <span className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-semibold self-start ${statusColor.bg} ${statusColor.text}`}>
                  <Clock className="w-4 h-4" />
                  {process.status_label || process.status}
                </span>
              </div>

              {/* Progress bar */}
              <div>
                <div className="flex items-center justify-between text-sm mb-2">
                  <span className="text-gray-500 flex items-center gap-1.5">
                    <BarChart3 className="w-4 h-4" /> Progresso
                  </span>
                  <span className="font-bold text-emerald-600">{progress.percent}%</span>
                </div>
                <div className="w-full bg-gray-100 rounded-full h-3">
                  <div
                    className="bg-gradient-to-r from-emerald-500 to-teal-500 h-3 rounded-full transition-all duration-700 ease-out"
                    style={{ width: `${progress.percent}%` }}
                  />
                </div>
                <p className="text-xs text-gray-400 mt-1.5">
                  Etapa {progress.current_step} de {progress.total_steps}
                </p>
              </div>
            </div>

            {/* Horizontal Stepper (full-width card) */}
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 sm:p-6">
              <h3 className="text-base font-bold text-gray-800 mb-3">Etapas do Processo</h3>
              <WorkflowStepper stepper={stepper} />
            </div>
          </div>

          {/* ═══ LEFT COLUMN: Tabs — Documentos / O Meu Perfil / As Minhas Visitas ═══ */}
          <div className="lg:col-span-7 space-y-5">
            {/* ── Tab Navigation ── */}
            <div className="flex gap-1 bg-white rounded-2xl shadow-sm border border-gray-100 p-1.5">
              <button
                onClick={() => setActiveTab('documentos')}
                className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition-all ${
                  activeTab === 'documentos'
                    ? 'bg-emerald-600 text-white shadow-md'
                    : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700'
                }`}
              >
                <FileText className="w-4 h-4" />
                <span className="hidden sm:inline">Documentos</span>
                <span className="sm:hidden">Docs</span>
              </button>
              <button
                onClick={() => setActiveTab('perfil')}
                className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition-all ${
                  activeTab === 'perfil'
                    ? 'bg-blue-600 text-white shadow-md'
                    : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700'
                }`}
              >
                <User className="w-4 h-4" />
                <span className="hidden sm:inline">O Meu Perfil</span>
                <span className="sm:hidden">Perfil</span>
              </button>
              <button
                onClick={() => setActiveTab('simulador')}
                className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition-all ${
                  activeTab === 'simulador'
                    ? 'bg-indigo-600 text-white shadow-md'
                    : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700'
                }`}
              >
                <Calculator className="w-4 h-4" />
                <span className="hidden sm:inline">Simulador</span>
                <span className="sm:hidden">Calc</span>
              </button>
              <button
                onClick={() => setActiveTab('visitas')}
                className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition-all ${
                  activeTab === 'visitas'
                    ? 'bg-violet-600 text-white shadow-md'
                    : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700'
                }`}
              >
                <Home className="w-4 h-4" />
                <span className="hidden sm:inline">As Minhas Visitas</span>
                <span className="sm:hidden">Visitas</span>
                {visits.filter(v => v.status === 'solicitada').length > 0 && (
                  <span className="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-violet-200 text-violet-800 text-[10px] font-bold">
                    {visits.filter(v => v.status === 'solicitada').length}
                  </span>
                )}
              </button>
            </div>

            {/* ── Tab Content ── */}
            {activeTab === 'documentos' && (
              <>
                <DocumentsPanel documents={documents} onUploadSuccess={handleUploadSuccess} />

            {/* RGPD Status */}
            {rgpd && (
              <>
                {rgpd.status === 'signed' && (
                  <div className="bg-emerald-50 rounded-2xl shadow-sm border border-emerald-200 p-5 sm:p-6">
                    <style>{`@keyframes rgpdCheckIn { 0% { transform: scale(0); opacity: 0; } 60% { transform: scale(1.2); } 100% { transform: scale(1); opacity: 1; } }`}</style>
                    <div className="flex items-start gap-3">
                      <div className="w-10 h-10 bg-emerald-100 rounded-full flex items-center justify-center flex-shrink-0" style={{ animation: 'rgpdCheckIn 0.5s ease-out' }}>
                        <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                      </div>
                      <div className="flex-1">
                        <h3 className="text-sm font-bold text-emerald-800">RGPD Assinado</h3>
                        <p className="text-xs text-emerald-600 mt-0.5">
                          O consentimento para tratamento de dados pessoais foi assinado
                          {rgpd.signed_at && (
                            <> a <strong>{formatDate(rgpd.signed_at)}</strong></>
                          )}.
                        </p>
                        {rgpd.signed_by && (
                          <p className="text-xs text-emerald-500 mt-1">
                            Assinado por: <strong>{rgpd.signed_by}</strong>
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                )}
                {rgpd.status === 'pending' && (
                  <div className="bg-amber-50 rounded-2xl shadow-sm border border-amber-200 p-5 sm:p-6">
                    <div className="flex items-start gap-3">
                      <div className='w-10 h-10 bg-amber-100 rounded-full flex items-center justify-center flex-shrink-0'>
                        <Clock className="w-5 h-5 text-amber-600" />
                      </div>
                      <div className="flex-1">
                        <h3 className="text-sm font-bold text-amber-800">RGPD Pendente</h3>
                        <p className="text-xs text-amber-600 mt-0.5">
                          O consentimento RGPD ainda não foi assinado.
                        </p>
                        {rgpd.requested_at && (
                          <p className="text-xs text-amber-500 mt-1">
                            Pedido enviado a <strong>{formatDate(rgpd.requested_at)}</strong>
                          </p>
                        )}
                        {rgpd.requested_by_name && (
                          <p className="text-xs text-amber-500 mt-0.5">
                            Solicitado por: <strong>{rgpd.requested_by_name}</strong>
                          </p>
                        )}
                        {rgpd.token_expired ? (
                          <div className="mt-2 flex items-center gap-1.5 text-xs text-red-600 bg-red-50 rounded-lg px-2.5 py-1.5">
                            <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
                            <span>Link de assinatura expirado. Contacte o seu consultor.</span>
                          </div>
                        ) : (
                          <div className="mt-2 flex items-center gap-1.5 text-xs text-amber-700 bg-amber-100 rounded-lg px-2.5 py-1.5">
                            <Mail className="w-3.5 h-3.5 flex-shrink-0" />
                            <span className="font-medium">Verifique o seu email para assinar</span>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )}
                {rgpd.status === 'none' && (
                  <div className="bg-gray-50 rounded-2xl shadow-sm border border-gray-200 p-5 sm:p-6">
                    <div className="flex items-start gap-3">
                      <div className='w-10 h-10 bg-gray-100 rounded-full flex items-center justify-center flex-shrink-0'>
                        <Shield className="w-5 h-5 text-gray-500" />
                      </div>
                      <div className="flex-1">
                        <h3 className="text-sm font-bold text-gray-600">RGPD Não Solicitado</h3>
                        <p className="text-xs text-gray-500 mt-0.5">
                          O consentimento RGPD ainda não foi solicitado.
                        </p>
                        <p className="text-xs text-gray-400 mt-1 italic">
                          O consentimento será solicitado pela equipa quando necessário.
                        </p>
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}

            <TeamCard team={team} consultor={consultor} />
              </>
            )}

            {/* ═══ Tab: O Meu Perfil ═══ */}
            {activeTab === 'perfil' && (
              <ProfilePanel />
            )}

            {/* ═══ Tab: Simulador de Crédito Habitação ═══ */}
            {activeTab === 'simulador' && (
              <SimulatorCH />
            )}

            {/* ═══ Tab: As Minhas Visitas ═══ */}
            {activeTab === 'visitas' && (
              <>
            {/* ── Pedir Visita ── */}
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
              <h3 className="text-base font-bold text-gray-800 mb-1 flex items-center gap-2">
                <Home className="w-5 h-5 text-violet-500" />
                Pedir Visita a um Imóvel
              </h3>
              <p className="text-sm text-gray-500 mb-4">
                Encontrou um imóvel que gostou? Cole o link e nós tratamos do resto.
              </p>

              {/* URL Input */}
              <div className="flex flex-col sm:flex-row gap-2 mb-3">
                <input
                  type="url"
                  value={visitUrl}
                  onChange={(e) => setVisitUrl(e.target.value)}
                  placeholder="Cole aqui o link do imóvel (Idealista, Imovirtual, Supercasa...)"
                  className="flex-1 px-4 py-2.5 text-sm border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-violet-400 focus:border-transparent bg-gray-50"
                  disabled={requestingVisit}
                />
                <button
                  onClick={async () => {
                    if (!visitUrl.trim()) return;
                    setRequestingVisit(true);
                    setVisitRequestResult(null);
                    try {
                      const token = getPortalToken();
                      if (!token) throw new Error('Sessão expirada.');
                      const res = await fetchWithRetry(`${BACKEND_URL}/portal/visits/request`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
                        body: JSON.stringify({ url: visitUrl.trim() }),
                      });
                      let data;
                      try { data = await res.json(); } catch { throw new Error('Erro inesperado do servidor.'); }
                      if (res.ok) {
                        setVisitRequestResult({ success: true, message: 'Pedido enviado com sucesso! O seu consultor será notificado e os dados do imóvel serão extraídos automaticamente.' });
                        setVisitUrl('');
                        toast.success('Pedido de visita enviado com sucesso!');
                        // Refresh visits list immediately (force reload even if already loaded)
                        try {
                          const vRes = await fetch(`${BACKEND_URL}/portal/visits`, { headers: { Authorization: `Bearer ${token}` } });
                          if (vRes.ok) { const vData = await vRes.json(); setVisits(vData.visits || []); }
                        } catch (vErr) {
                          console.warn('[PORTAL] Erro ao atualizar lista de visitas:', vErr);
                        }
                      } else {
                        setVisitRequestResult({ error: data.detail || 'Erro ao pedir visita.' });
                      }
                    } catch (err) {
                      setVisitRequestResult({ error: err.message || 'Erro de ligação.' });
                    } finally {
                      setRequestingVisit(false);
                    }
                  }}
                  disabled={requestingVisit || !visitUrl.trim()}
                  className="px-5 py-2.5 text-sm font-semibold bg-violet-600 text-white rounded-xl hover:bg-violet-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2 shrink-0 shadow-sm"
                >
                  {requestingVisit ? (
                    <><Loader2 className="w-4 h-4 animate-spin" /> A enviar...</>
                  ) : (
                    <><ExternalLink className="w-4 h-4" /> Pedir Visita</>
                  )}
                </button>
              </div>

              {/* Supported sites hint */}
              <div className="flex flex-wrap gap-1.5 mb-3">
                {['Idealista', 'Imovirtual', 'Supercasa', 'CasaSapo', 'Remax', 'ERA'].map((site) => (
                  <span key={site} className="text-[10px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-500 border border-gray-200">{site}</span>
                ))}
              </div>

              {/* Request result feedback */}
              {visitRequestResult?.success && (
                <div className="flex items-start gap-2 bg-emerald-50 border border-emerald-200 rounded-xl p-3 mb-4">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 mt-0.5 flex-shrink-0" />
                  <p className="text-xs text-emerald-700">{visitRequestResult.message}</p>
                </div>
              )}
              {visitRequestResult?.error && (
                <div className="flex items-start gap-1.5 text-xs text-red-600 bg-red-50 rounded-xl px-3 py-2.5 mb-4">
                  <AlertCircle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                  <span>{visitRequestResult.error}</span>
                </div>
              )}
            </div>

            {/* ── Lista de Visitas ── */}
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
              <h3 className="text-base font-bold text-gray-800 mb-1 flex items-center gap-2">
                <CalendarClock className="w-5 h-5 text-amber-500" />
                As Minhas Visitas
              </h3>
              <p className="text-sm text-gray-500 mb-4">
                Acompanhe o estado dos seus pedidos de visita.
              </p>

              {visitsLoading ? (
                <div className="flex items-center justify-center gap-2 text-sm text-gray-400 py-8">
                  <Loader2 className="w-5 h-5 animate-spin text-violet-500" />
                  A carregar as suas visitas...
                </div>
              ) : visits.length > 0 ? (
                <div className="space-y-3 max-h-[500px] overflow-y-auto pr-1" style={{ scrollbarWidth: 'thin' }}>
                  {visits.map((visit) => {
                    // ── Enhanced status labels ──
                    const getStatusInfo = (status, scheduledDate) => {
                      switch (status) {
                        case 'solicitada':
                          return { label: 'A aguardar contacto do consultor', color: 'bg-violet-100 text-violet-700 border-violet-200', icon: <Clock className="w-3.5 h-3.5" /> };
                        case 'agendada':
                          if (scheduledDate) {
                            const scheduledDateObj = safeDate(scheduledDate);
                            const dateStr = scheduledDateObj ? scheduledDateObj.toLocaleDateString('pt-PT', { day: 'numeric', month: 'long' }) : '';
                            const timeStr = scheduledDateObj ? scheduledDateObj.toLocaleTimeString('pt-PT', { hour: '2-digit', minute: '2-digit' }) : '';
                            return { label: `Agendada para ${dateStr} às ${timeStr}`, color: 'bg-amber-100 text-amber-700 border-amber-200', icon: <CalendarClock className="w-3.5 h-3.5" /> };
                          }
                          return { label: 'Agendada', color: 'bg-amber-100 text-amber-700 border-amber-200', icon: <CalendarClock className="w-3.5 h-3.5" /> };
                        case 'concluida':
                          return { label: 'Visita Concluída', color: 'bg-emerald-100 text-emerald-700 border-emerald-200', icon: <CheckCircle2 className="w-3.5 h-3.5" /> };
                        case 'cancelada':
                          return { label: 'Visita Cancelada', color: 'bg-red-100 text-red-700 border-red-200', icon: <X className="w-3.5 h-3.5" /> };
                        default:
                          return { label: status, color: 'bg-gray-100 text-gray-600 border-gray-200', icon: null };
                      }
                    };
                    const statusInfo = getStatusInfo(visit.status, visit.scheduled_date);

                    return (
                      <div key={visit.id} className="border border-gray-100 rounded-xl overflow-hidden hover:shadow-md transition-shadow group">
                        {/* Property photo */}
                        <div className="flex">
                          {visit.property_photo ? (
                            <div className="w-28 sm:w-36 bg-gray-100 overflow-hidden shrink-0">
                              <img src={visit.property_photo} alt="" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" onError={(e) => { e.target.style.display = 'none'; }} />
                            </div>
                          ) : (
                            <div className="w-28 sm:w-36 bg-gradient-to-br from-violet-50 to-teal-50 flex items-center justify-center shrink-0">
                              <Home className="w-8 h-8 text-violet-300" />
                            </div>
                          )}
                          <div className="p-3 flex-1 min-w-0">
                            <div className="flex items-start justify-between gap-2">
                              <h4 className="font-semibold text-sm text-gray-800 truncate">{visit.property_title || 'Imóvel'}</h4>
                            </div>
                            {/* Price */}
                            {visit.scraped_data?.price && (
                              <p className="text-sm font-bold text-emerald-600 mt-0.5">
                                {typeof visit.scraped_data.price === 'number'
                                  ? new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' }).format(visit.scraped_data.price)
                                  : visit.scraped_data.price}
                              </p>
                            )}
                            {/* Location */}
                            {(visit.property_address?.municipality || visit.scraped_data?.location) && (
                              <div className="flex items-center gap-1 text-xs text-gray-500 mt-1">
                                <MapPin className="w-3 h-3 shrink-0" />
                                <span className="truncate">{visit.property_address?.municipality || visit.scraped_data?.location}</span>
                              </div>
                            )}
                            {/* Typology */}
                            {visit.scraped_data?.typology && (
                              <p className="text-xs text-gray-400 mt-0.5">{visit.scraped_data.typology}</p>
                            )}
                            {/* Status badge with enhanced label */}
                            <div className={`inline-flex items-center gap-1 mt-2 text-[11px] px-2.5 py-1 rounded-full font-medium border ${statusInfo.color}`}>
                              {statusInfo.icon}
                              {statusInfo.label}
                            </div>
                            {/* Source link */}
                            {visit.scraped_url && (
                              <a href={visit.scraped_url} target="_blank" rel="noopener noreferrer" className="text-[10px] text-violet-500 hover:text-violet-700 mt-1.5 block">
                                Ver anúncio original ↗
                              </a>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="text-center py-8">
                  <div className="w-16 h-16 bg-violet-50 rounded-2xl flex items-center justify-center mx-auto mb-3">
                    <Home className="w-8 h-8 text-violet-300" />
                  </div>
                  <p className="text-sm text-gray-500 font-medium">Ainda não pediu nenhuma visita</p>
                  <p className="text-xs text-gray-400 mt-1">Cole o link de um imóvel acima para pedir uma visita</p>
                </div>
              )}
            </div>

            {/* ═══ Imóveis Recomendados (Smart Match) ═══ */}
            {!recommendationsLoading && recommendations.length > 0 && (
              <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
                <h3 className="text-base font-bold text-gray-800 mb-1 flex items-center gap-2">
                  <svg className="w-5 h-5 text-purple-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
                  </svg>
                  Imóveis Recomendados
                </h3>
                <p className="text-sm text-gray-500 mb-4">
                  Imóveis seleccionados pelo seu consultor especialmente para si.
                </p>
                <div className="space-y-3 max-h-96 overflow-y-auto">
                  {recommendations.map((rec) => (
                    <div key={rec.property_id} className="border border-gray-100 rounded-xl overflow-hidden hover:shadow-md transition-shadow">
                      {/* Photo */}
                      {rec.photo ? (
                        <div className="h-32 bg-gray-100 overflow-hidden">
                          <img
                            src={rec.photo}
                            alt={rec.title}
                            className="w-full h-full object-cover"
                          />
                        </div>
                      ) : (
                        <div className="h-24 bg-gradient-to-br from-purple-50 to-teal-50 flex items-center justify-center">
                          <svg className="w-10 h-10 text-purple-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" />
                          </svg>
                        </div>
                      )}
                      <div className="p-3">
                        {/* Title */}
                        <h4 className="font-semibold text-sm text-gray-800 truncate">{rec.title || 'Sem título'}</h4>
                        {/* Price */}
                        {rec.price && (
                          <p className="text-base font-bold text-emerald-600 mt-1">
                            {new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' }).format(rec.price)}
                          </p>
                        )}
                        {/* Location */}
                        <div className="flex items-center gap-1 text-xs text-gray-500 mt-1">
                          <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M15 10.5a3 3 0 11-6 0 3 3 0 016 0z" />
                            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1115 0z" />
                          </svg>
                          <span className="truncate">{[rec.municipality, rec.district].filter(Boolean).join(', ')}</span>
                        </div>
                        {/* Features */}
                        <div className="flex items-center gap-3 text-xs text-gray-400 mt-1.5">
                          {rec.bedrooms != null && <span>T{rec.bedrooms}</span>}
                          {rec.area && <span>{rec.area}m²</span>}
                          {rec.property_type && <span className="capitalize">{rec.property_type}</span>}
                        </div>
                        {/* Recommended by */}
                        <div className="mt-2 pt-2 border-t border-gray-50">
                          <p className="text-[10px] text-gray-400">
                            Recomendado por <span className="font-medium text-purple-600">{rec.recommended_by_name || 'Consultor'}</span>
                            {rec.recommended_at && (
                              <> · {formatDate(rec.recommended_at)}</>
                            )}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Loading recommendations */}
            {recommendationsLoading && (
              <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
                <div className="flex items-center gap-2 text-sm text-gray-400">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  A carregar imóveis recomendados...
                </div>
              </div>
            )}
              </>
            )}
          </div>

          {/* ═══ RIGHT COLUMN: Mensagens / Chat (Desktop only) ═══ */}
          <div className="hidden lg:block lg:col-span-5">
            <PortalMessages
              messages={messages}
              loading={messagesLoading}
              newMessage={newMessage}
              setNewMessage={setNewMessage}
              onSend={sendMessage}
              sending={sendingMessage}
              unreadCount={unreadCount}
              welcomeMessage={welcomeMessage}
            />
          </div>

        </div>
      </main>

      {/* ═══ MOBILE: Floating Chat Button + Sheet ═══ */}
      <div className="lg:hidden">
        {/* FAB — Floating Action Button */}
        <button
          onClick={() => setIsMobileChatOpen(true)}
          className="fixed bottom-6 right-6 z-50 h-14 w-14 rounded-full bg-emerald-600 text-white shadow-2xl flex items-center justify-center hover:bg-emerald-700 active:scale-95 transition-all"
          aria-label="Abrir chat"
        >
          <MessageCircle className="w-6 h-6" />
          {unreadCount > 0 && (
            <span className="absolute -top-1 -right-1 inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full bg-red-500 text-white text-[10px] font-bold shadow-sm">
              {unreadCount}
            </span>
          )}
        </button>

        {/* Sheet — Sliding chat panel */}
        <Sheet open={isMobileChatOpen} onOpenChange={setIsMobileChatOpen}>
          <SheetContent side="right" className="w-full sm:max-w-md p-0 flex flex-col">
            <SheetHeader className="px-5 pt-5 pb-2">
              <SheetTitle className="flex items-center gap-2 text-base">
                <MessageCircle className="w-5 h-5 text-emerald-500" />
                Mensagens
              </SheetTitle>
              <SheetDescription className="text-xs text-gray-400">
                Converse com a sua equipa de consultores
              </SheetDescription>
            </SheetHeader>
            <div className="flex-1 min-h-0 overflow-hidden">
              <PortalMessages
                messages={messages}
                loading={messagesLoading}
                newMessage={newMessage}
                setNewMessage={setNewMessage}
                onSend={sendMessage}
                sending={sendingMessage}
                unreadCount={unreadCount}
                isInSheet
                welcomeMessage={welcomeMessage}
              />
            </div>
          </SheetContent>
        </Sheet>
      </div>

      {/* Footer */}
      <footer className="mt-auto bg-white border-t border-gray-100 py-3">
        <div className="w-full px-4 sm:px-6 lg:px-10 text-center">
          <p className="text-xs text-gray-400">© {new Date().getFullYear()} Power Precision · Crédito Habitação</p>
          <p className="text-[10px] text-gray-300 mt-0.5">Acesso seguro via Magic Link · Válido por 90 dias</p>
        </div>
      </footer>
    </div>
    </IframeDetector>
  );
}
