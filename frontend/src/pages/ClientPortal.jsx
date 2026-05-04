/**
 * ClientPortal — Portal do Cliente (Magic Link, passwordless).
 *
 * Layout: responsivo — grid 2 colunas em desktop, stack em mobile.
 * - Coluna Esquerda: Estado do processo + Stepper + Consultor
 * - Coluna Direita: Documentos (pendentes + upload + entregues)
 *
 * Fluxo de autenticação:
 *   short_id → resolve → JWT (sessionStorage) → status + upload
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
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
} from 'lucide-react';

const BACKEND_URL = (process.env.REACT_APP_BACKEND_URL || 'https://powercell.onrender.com') + '/api';

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
// PROGRESS STEPPER — Vertical timeline (desktop) / Horizontal (mobile)
// ====================================================================
function WorkflowStepper({ stepper }) {
  if (!stepper || stepper.length === 0) return null;

  return (
    <>
      {/* Mobile: horizontal stepper */}
      <div className="lg:hidden">
        <div className="flex items-center relative">
          <div className="absolute top-5 left-5 right-5 h-1 bg-gray-200 rounded-full" />
          <div
            className="absolute top-5 left-5 h-1 bg-emerald-500 rounded-full transition-all duration-500"
            style={{
              width: stepper.length > 1
                ? `${((stepper.filter(s => s.is_completed || s.is_current).length - 1) / (stepper.length - 1)) * (100 - 6)}%`
                : '0%',
            }}
          />
          {stepper.map((step, i) => {
            const colors = step.is_completed ? stepColor('green') : step.is_current ? stepColor(step.color) : null;
            return (
              <div key={step.id} className="flex flex-col items-center relative z-10" style={{ flex: 1 }}>
                <div className={`w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold border-2 transition-all ${
                  colors
                    ? `${colors.bg} ${colors.border} ${colors.text}`
                    : 'bg-white border-gray-300 text-gray-400'
                } ${step.is_current ? 'scale-110 shadow-lg ring-4 ring-white' : ''}`}>
                  {step.is_completed ? <Check className="w-5 h-5" /> : <span>{i + 1}</span>}
                </div>
                <span className={`mt-1.5 text-center text-[10px] leading-tight max-w-[64px] ${
                  step.is_current ? 'font-semibold text-gray-800' : step.is_completed ? 'text-emerald-600' : 'text-gray-400'
                }`}>
                  {step.label}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Desktop: vertical timeline */}
      <div className="hidden lg:block space-y-1">
        {stepper.map((step, i) => {
          const colors = stepColor(step.color);
          const isActive = step.is_current;
          const isDone = step.is_completed;
          return (
            <div key={step.id} className={`flex gap-3 items-start rounded-lg p-2 -mx-2 transition-colors ${isActive ? 'bg-gray-50' : ''}`}>
              {/* Line + circle */}
              <div className="flex flex-col items-center flex-shrink-0 pt-0.5">
                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold border-2 transition-all ${
                  isDone
                    ? 'bg-emerald-500 border-emerald-500 text-white'
                    : isActive
                    ? `${colors.bg} ${colors.border} ${colors.text} scale-110 shadow-lg ${colors.ring}`
                    : 'bg-white border-gray-300 text-gray-400'
                }`}>
                  {isDone ? <Check className="w-4 h-4" /> : <span>{i + 1}</span>}
                </div>
                {i < stepper.length - 1 && (
                  <div className={`w-0.5 h-8 mt-1 rounded-full ${isDone ? 'bg-emerald-500' : 'bg-gray-200'}`} />
                )}
              </div>
              {/* Label */}
              <div className="pt-1">
                <p className={`text-sm font-medium ${isDone ? 'text-emerald-700' : isActive ? 'text-gray-900' : 'text-gray-400'}`}>
                  {step.label}
                </p>
                {isActive && step.description && (
                  <p className="text-xs text-gray-500 mt-0.5">{step.description}</p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </>
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
          {doc.notes && <p className="text-xs text-gray-400 truncate">{doc.notes}</p>}
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
function DocumentsPanel({ documents, onUploadSuccess }) {
  const { requested = [], uploaded = [], received = [], has_pending } = documents || {};

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
                  <p className="text-sm text-gray-700 truncate font-medium">{doc.filename}</p>
                  <p className="text-xs text-gray-400">
                    {doc.category_label || doc.category}
                    {doc.uploaded_at && ` · ${new Date(doc.uploaded_at).toLocaleDateString('pt-PT')}`}
                  </p>
                </div>
                <Check className="w-4 h-4 text-emerald-500 flex-shrink-0" />
              </div>
            ))}
          </div>
        </div>
      )}

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
                  <p className="text-sm text-gray-700 truncate font-medium">{doc.filename}</p>
                  <p className="text-xs text-gray-400">
                    {doc.category_label || doc.category}
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
  const whatsappUrl = contact.phone ? `https://wa.me/351${contact.phone.replace(/\D/g, '')}` : null;
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

  const { process, progress, stepper, documents, team, consultor } = data;
  const currentStep = stepper?.find(s => s.is_current);
  const statusColor = currentStep ? stepColor(currentStep.color) : stepColor('green');

  return (
    <IframeDetector>
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-gray-100 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 shadow-sm sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-3.5 flex items-center gap-3">
          <img
            src="/PowerLogo-removebg-preview.png"
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

      {/* Main Content — 2 column grid */}
      <main className="flex-1 max-w-6xl w-full mx-auto px-4 sm:px-6 py-6 pb-28">
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">

          {/* ═══ LEFT COLUMN: Process Status ═══ */}
          <div className="lg:col-span-3 space-y-5">

            {/* Greeting + Status */}
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

            {/* Workflow Stepper */}
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 sm:p-6">
              <h3 className="text-base font-bold text-gray-800 mb-4">Etapas do Processo</h3>
              <WorkflowStepper stepper={stepper} />
            </div>

            {/* Team (mobile) */}
            <div className="lg:hidden">
              <TeamCard team={team} consultor={consultor} />
            </div>
          </div>

          {/* ═══ RIGHT COLUMN: Documents ═══ */}
          <div className="lg:col-span-2">
            <DocumentsPanel documents={documents} onUploadSuccess={handleUploadSuccess} />

            {/* Team (desktop) */}
            <div className="hidden lg:block">
              <TeamCard team={team} consultor={consultor} />
            </div>
          </div>

        </div>
      </main>

      {/* Footer */}
      <footer className="mt-auto bg-white border-t border-gray-100 py-3">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 text-center">
          <p className="text-xs text-gray-400">© {new Date().getFullYear()} Power Precision · Crédito Habitação</p>
          <p className="text-[10px] text-gray-300 mt-0.5">Acesso seguro via Magic Link · Válido por 90 dias</p>
        </div>
      </footer>
    </div>
    </IframeDetector>
  );
}
