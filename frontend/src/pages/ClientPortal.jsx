/**
 * ClientPortal — Portal do Cliente (Magic Link, passwordless).
 *
 * Layout: Dashboard profissional full-width — horizontal stepper + 2 colunas.
 * - Topo (lg:col-span-12): Resumo + Timeline Horizontal (Stepper)
 * - Esquerda (lg:col-span-7): Gestão de Documentos + RGPD + Equipa
 * - Direita (lg:col-span-5): Mensagens / Chat
 *
 * Fluxo de autenticação:
 *   short_id → resolve → JWT (sessionStorage) → status + upload
 */
import React, { useState, useEffect, useCallback, useRef, useMemo, Suspense } from 'react';
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

} from 'lucide-react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';

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
      // Only retry on 503 (Service Unavailable — cold start or transient issue)
      if (res.status === 503 && attempt < retries) {
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
      const token = sessionStorage.getItem('portal_token');
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

  const isFinancas = source === 'financas';
  const idLabel = isFinancas ? 'NIF' : 'NISS';
  const idLength = isFinancas ? 9 : 11;
  const sourceLabel = isFinancas ? 'Portal das Finanças' : 'Segurança Social';
  const sourceIcon = isFinancas ? <Landmark className="w-5 h-5 text-teal-600" /> : <HeartPulse className="w-5 h-5 text-rose-500" />;

  // Reset state when dialog opens (safe: only runs on open transition)
  const prevOpenRef = useRef(false);
  useEffect(() => {
    if (open && !prevOpenRef.current) {
      setIdField(''); setPassword(''); setShowPassword(false); setLoading(false); setError(null); setSuccess(null);
    }
    prevOpenRef.current = open;
  }, [open]);

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
    try {
      const token = sessionStorage.getItem('portal_token');
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

      if (res.ok && data.success) {
        setSuccess(data.message || 'Documentos obtidos com sucesso!');
        setTimeout(() => { onOpenChange(false); if (onSuccess) onSuccess(); }, 2500);
      } else if (res.status === 503) {
        setError(data.detail || 'O serviço de obtenção automática não está disponível de momento. Por favor, faça download manualmente e envie os documentos através do botão de upload.');
      } else if (res.status === 401 && data.detail) {
        setError(data.detail);
      } else {
        setError(data.detail || 'Erro ao obter documentos. Tente novamente.');
      }
    } catch (err) {
      setError(err.message || 'Erro de ligação. Tente novamente.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <ClientOnly>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent title={sourceLabel} description={`Obter documentos do ${sourceLabel}`} className="sm:max-w-md">
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
  const { requested = [], uploaded = [], received = [], has_pending } = documents || {};
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
        const data = await res.json();
        if (!cancelled) setScraperAvailable(data.available === true);
      } catch {
        if (!cancelled) setScraperAvailable(false);
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
        const data = await res.json();
        const available = data.available === true;
        setScraperAvailable(available);
        if (available) {
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

      {/* Uploaded by client */}
      {uploaded.length > 0 && (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
          <h3 className="text-base font-bold text-gray-800 mb-3 flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-emerald-500" />
            Documentos Entregues ({uploaded.length})
          </h3>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {uploaded.map((doc) => (
              <div key={doc.id} className="flex items-center gap-3 p-2.5 rounded-lg bg-emerald-50/50 hover:bg-emerald-50 transition-colors">
                <span className="text-base flex-shrink-0">{doc.icon || '📄'}</span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-gray-700 truncate font-medium">{typeof doc.filename === 'string' ? doc.filename : String(doc.filename || '')}</p>
                  <p className="text-xs text-gray-400">
                    {typeof (doc.category_label || doc.category) === 'string' ? (doc.category_label || doc.category) : String(doc.category_label || doc.category || '')}
                    {doc.uploaded_at && ` · ${new Date(doc.uploaded_at).toLocaleDateString('pt-PT')}`}
                  </p>
                </div>
                <Check className="w-4 h-4 text-emerald-500 flex-shrink-0" />
              </div>
            ))}
          </div>
        </div>
      )}

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

      {/* Received by admin (documents delivered outside portal) */}
      {received && received.length > 0 && (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
          <h3 className="text-base font-bold text-gray-800 mb-3 flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-teal-500" />
            Documentos Recebidos ({received.length})
          </h3>
          <p className="text-xs text-gray-400 mb-3">Estes documentos foram recebidos pela nossa equipa.</p>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {received.map((doc) => (
              <div key={doc.id} className="flex items-center gap-3 p-2.5 rounded-lg bg-teal-50/50 hover:bg-teal-50 transition-colors">
                <span className="text-base flex-shrink-0">{doc.icon || '📄'}</span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-gray-700 truncate font-medium">{typeof doc.filename === 'string' ? doc.filename : String(doc.filename || '')}</p>
                  <p className="text-xs text-gray-400">
                    {typeof (doc.category_label || doc.category) === 'string' ? (doc.category_label || doc.category) : String(doc.category_label || doc.category || '')}
                    {doc.received_at && ` · ${new Date(doc.received_at).toLocaleDateString('pt-PT')}`}
                  </p>
                </div>
                <Check className="w-4 h-4 text-teal-500 flex-shrink-0" />
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
    const now = new Date();
    const date = new Date(isoDate);
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
    return date.toLocaleDateString('pt-PT');
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
// MAIN CLIENT PORTAL
// ====================================================================
export default function ClientPortal() {
  const [loading, setLoading] = useState(true);
  const [loadingMessage, setLoadingMessage] = useState('A carregar o seu processo...');
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const rawToken = useRef(window.location.pathname.split('/portal/')[1]);

  useEffect(() => {
    let cancelled = false;
    const token = rawToken.current;

    if (!token) { setError('Link inválido. Contacte o seu consultor.'); setLoading(false); return; }

    const isShortToken = !token.includes('.');

    const fetchStatus = async (jwt) => {
      if (cancelled) return;
      try {
        sessionStorage.setItem('portal_token', jwt);
        const ctrl = new AbortController();
        const t = setTimeout(() => ctrl.abort(), 20000);
        const res = await fetch(`${BACKEND_URL}/portal/status`, { headers: { Authorization: `Bearer ${jwt}` }, signal: ctrl.signal });
        clearTimeout(t);
        if (cancelled) return;
        if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || 'Erro ao carregar dados'); }
        const result = await res.json();
        if (cancelled) return;
        setData(result);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError(err.name === 'AbortError' ? 'Ligação demorou demais. Tente novamente.' : err.message);
      } finally { if (!cancelled) setLoading(false); }
    };

    const init = async () => {
      try {
        if (isShortToken) {
          setLoadingMessage('A verificar link...');
          const ctrl = new AbortController();
          const t = setTimeout(() => ctrl.abort(), 15000);
          const r = await fetch(`${BACKEND_URL}/portal/resolve/${token}`, { signal: ctrl.signal });
          clearTimeout(t);
          if (cancelled) return;
          if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || 'Link não encontrado ou expirado'); }
          const jwt = (await r.json())?.token;
          if (!jwt) throw new Error('Erro ao resolver link');
          setLoadingMessage('A carregar o seu processo...');
          await fetchStatus(jwt);
        } else {
          await fetchStatus(token);
        }
      } catch (err) {
        if (cancelled) return;
        setError(err.name === 'AbortError' ? 'Ligação demorou demais. Tente novamente.' : err.message);
        setLoading(false);
      }
    };

    init();
    return () => { cancelled = true; };
  }, [refreshKey]);

  const handleUploadSuccess = useCallback(() => setRefreshKey((k) => k + 1), []);

  // ── Messaging state ──
  const [messages, setMessages] = useState([]);
  const [messagesLoading, setMessagesLoading] = useState(true);
  const [newMessage, setNewMessage] = useState('');
  const [sendingMessage, setSendingMessage] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isMobileChatOpen, setIsMobileChatOpen] = useState(false);

  const fetchMessages = useCallback(async () => {
    const token = sessionStorage.getItem('portal_token');
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
    const token = sessionStorage.getItem('portal_token');
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
    const token = sessionStorage.getItem('portal_token');
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
  useEffect(() => {
    fetchMessages();
    fetchUnreadCount();
    const interval = setInterval(() => {
      fetchMessages();
      fetchUnreadCount();
    }, 15000);
    return () => clearInterval(interval);
  }, [fetchMessages, fetchUnreadCount]);

  // ── Welcome message (from API, already rendered with variables) ──
  // MUST be before early returns (Rules of Hooks)
  const welcomeMessage = useMemo(() => {
    // The backend returns welcome_message already with {{cliente}}, {{consultor}},
    // {{empresa}} replaced by the actual values. Fallback to nothing if not available.
    return data?.welcome_message || '';
  }, [data?.welcome_message]);

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

          {/* ═══ LEFT COLUMN: Documentos + RGPD + Equipa ═══ */}
          <div className="lg:col-span-7 space-y-5">
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
                            <> a <strong>{new Date(rgpd.signed_at).toLocaleDateString('pt-PT')}</strong></>
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
                            Pedido enviado a <strong>{new Date(rgpd.requested_at).toLocaleDateString('pt-PT')}</strong>
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
