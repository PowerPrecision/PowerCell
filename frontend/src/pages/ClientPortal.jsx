/**
 * ClientPortal — Portal do cliente (passwordless) acedido via Magic Link.
 *
 * PORQUÊ: Nem todos os clientes têm ou querem ter conta no PowerCell. O Magic Link
 * permite enviar um link seguro (válido por 90 dias) para o email do cliente,
 * dando-lhe acesso directo ao estado do seu processo sem necessidade de registo
 * ou password. Isto é essencial para cumprir boas práticas de UX — o cliente não
 * precisa de memorizar credenciais apenas para acompanhar o seu processo.
 *
 * DECISÕES ARQUITECTURAIS:
 * - Mobile-first: 90% dos clientes acedem via telemóvel. Interface minimalista
 *   sem navegação complexa — foco no progresso, documentos pendentes e contacto
 *   do consultor.
 * - Token na URL (path-based, não query param) para simplicidade.
 * - Token armazenado em sessionStorage (não localStorage) para evitar conflitos
 *   quando o mesmo navegador acede a portais de clientes diferentes.
 * - Upload directo para S3 via pre-signed URLs em 3 passos: gerar URL → upload
 *   binário → confirmar metadados no backend.
 * - Stepper visual das etapas do processo com cores dinâmicas por estado.
 * - Cartão de contacto do consultor com links para telefone, email e WhatsApp.
 * - Subcomponentes modulares (ProgressStepper, PendingDocumentsCard, ConsultantCard,
 *   UploadedDocumentsList) para manter o ficheiro gerível.
 *
 * @route /portal/:token — Rota pública parametrizada pelo token do Magic Link
 *
 * @example
 * // O cliente recebe um link como: https://app.powercell.pt/portal/abc123def
 * <ClientPortal />
 * // O token é extraído automaticamente da URL
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
  Copy,
  Check,
} from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'https://powercell.onrender.com/api';

// ====================================================================
// STEPPER COMPONENT
// ====================================================================
function ProgressStepper({ stepper }) {
  if (!stepper || stepper.length === 0) return null;

  return (
    <div className="w-full py-2">
      <div className="flex items-center justify-between relative">
        {/* Progress line background */}
        <div className="absolute top-5 left-6 right-6 h-1 bg-gray-200 rounded-full" />
        {/* Progress line filled */}
        <div
          className="absolute top-5 left-6 h-1 bg-emerald-500 rounded-full transition-all duration-500"
          style={{
            width: stepper.length > 1
              ? `${((stepper.filter(s => s.is_completed || s.is_current).length - 1) / (stepper.length - 1)) * (100 - 4)}%`
              : '0%',
          }}
        />

        {stepper.map((step, index) => (
          <div
            key={step.id}
            className="flex flex-col items-center relative z-10"
            style={{ flex: 1 }}
          >
            {/* Step circle */}
            <div
              className={`w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold transition-all duration-300 border-2 ${
                step.is_current
                  ? 'bg-emerald-500 border-emerald-500 text-white scale-110 shadow-lg shadow-emerald-500/30'
                  : step.is_completed
                  ? 'bg-emerald-500 border-emerald-500 text-white'
                  : 'bg-white border-gray-300 text-gray-400'
              }`}
            >
              {step.is_completed ? (
                <CheckCircle2 className="w-5 h-5" />
              ) : step.is_current ? (
                <span>{index + 1}</span>
              ) : (
                <span>{index + 1}</span>
              )}
            </div>

            {/* Step label (hidden on very small screens) */}
            <span
              className={`mt-2 text-center text-[10px] leading-tight max-w-[70px] ${
                step.is_current
                  ? 'text-emerald-700 font-semibold'
                  : step.is_completed
                  ? 'text-emerald-600'
                  : 'text-gray-400'
              }`}
            >
              {step.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ====================================================================
// DOCUMENT UPLOAD CARD
// ====================================================================
function PendingDocumentsCard({ pending, onUpload }) {
  const [uploading, setUploading] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadResult, setUploadResult] = useState(null);
  const fileInputRef = useRef(null);

  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (file) {
      setSelectedFile(file);
      setUploadResult(null);
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) return;

    setUploading(true);
    setUploadProgress(0);
    setUploadResult(null);

    try {
      const token = sessionStorage.getItem('portal_token');
      if (!token) {
        setUploadResult({ error: 'Sessão expirada. Recarregue a página.' });
        setUploading(false);
        return;
      }

      // Step 1: Get pre-signed URL
      setUploadProgress(10);
      const urlResponse = await fetch(`${BACKEND_URL}/portal/upload-url`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          filename: selectedFile.name,
          content_type: selectedFile.type || 'application/octet-stream',
          category: 'Outros',
        }),
      });

      if (!urlResponse.ok) {
        const err = await urlResponse.json();
        throw new Error(err.detail || 'Erro ao gerar link de upload');
      }

      const { upload_url, file_key, expires_in_seconds } = await urlResponse.json();

      // Step 2: Upload directly to S3
      setUploadProgress(30);
      await new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('PUT', upload_url);
        xhr.setRequestHeader('Content-Type', selectedFile.type || 'application/octet-stream');

        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            const percent = 30 + Math.round((e.loaded / e.total) * 60);
            setUploadProgress(percent);
          }
        };

        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve();
          } else {
            reject(new Error('Erro ao enviar ficheiro'));
          }
        };

        xhr.onerror = () => reject(new Error('Erro de ligação'));
        xhr.send(selectedFile);
      });

      // Step 3: Confirm upload
      setUploadProgress(95);
      const confirmResponse = await fetch(`${BACKEND_URL}/portal/confirm-upload`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          file_key,
          original_filename: selectedFile.name,
          category: 'Outros',
          file_size: selectedFile.size,
          content_type: selectedFile.type,
        }),
      });

      if (!confirmResponse.ok) {
        const err = await confirmResponse.json();
        throw new Error(err.detail || 'Erro ao confirmar upload');
      }

      setUploadProgress(100);
      setUploadResult({ success: true, filename: selectedFile.name });
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';

      // Notify parent to refresh status
      setTimeout(() => onUpload && onUpload(), 1000);
    } catch (err) {
      setUploadResult({ error: err.message });
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
      <h3 className="text-base font-bold text-gray-800 mb-1 flex items-center gap-2">
        <FileUp className="w-5 h-5 text-orange-500" />
        Documentos Pendentes
      </h3>
      <p className="text-sm text-gray-500 mb-4">
        Submeta os documentos em falta para avançar com o seu processo.
      </p>

      {/* Pending categories */}
      {pending && pending.length > 0 && (
        <div className="space-y-2 mb-4">
          {pending.map((cat) => (
            <div
              key={cat.category}
              className="flex items-center gap-3 p-3 bg-orange-50 border border-orange-100 rounded-xl"
            >
              <span className="text-lg">{cat.icon}</span>
              <span className="text-sm text-orange-800 font-medium">{cat.label}</span>
              <AlertCircle className="w-4 h-4 text-orange-400 ml-auto" />
            </div>
          ))}
        </div>
      )}

      {/* Upload area */}
      <div className="border-2 border-dashed border-gray-200 rounded-xl p-4 text-center hover:border-emerald-400 transition-colors">
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          onChange={handleFileSelect}
          accept=".pdf,.jpg,.jpeg,.png,.doc,.docx"
        />

        {selectedFile ? (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 min-w-0">
              <FileText className="w-5 h-5 text-emerald-600 flex-shrink-0" />
              <span className="text-sm text-gray-700 truncate">{selectedFile.name}</span>
              <span className="text-xs text-gray-400">
                ({(selectedFile.size / 1024).toFixed(0)} KB)
              </span>
            </div>
            <button
              onClick={() => { setSelectedFile(null); setUploadResult(null); }}
              className="ml-2 p-1 hover:bg-gray-100 rounded-full"
            >
              <X className="w-4 h-4 text-gray-400" />
            </button>
          </div>
        ) : (
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex flex-col items-center gap-1 w-full"
          >
            <Upload className="w-8 h-8 text-gray-400" />
            <span className="text-sm text-gray-500">
              Toque para selecionar ficheiro
            </span>
            <span className="text-xs text-gray-400">PDF, Imagens, Word</span>
          </button>
        )}
      </div>

      {/* Upload button */}
      {selectedFile && (
        <button
          onClick={handleUpload}
          disabled={uploading}
          className="w-full mt-3 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold py-3 px-4 rounded-xl flex items-center justify-center gap-2 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {uploading ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              A enviar... {uploadProgress}%
            </>
          ) : (
            <>
              <Upload className="w-5 h-5" />
              Submeter Documento
            </>
          )}
        </button>
      )}

      {/* Progress bar */}
      {uploading && (
        <div className="w-full bg-gray-200 rounded-full h-2 mt-3">
          <div
            className="bg-emerald-500 h-2 rounded-full transition-all duration-300"
            style={{ width: `${uploadProgress}%` }}
          />
        </div>
      )}

      {/* Result */}
      {uploadResult && (
        <div
          className={`mt-3 p-3 rounded-xl flex items-center gap-2 text-sm ${
            uploadResult.error
              ? 'bg-red-50 text-red-700 border border-red-100'
              : 'bg-emerald-50 text-emerald-700 border border-emerald-100'
          }`}
        >
          {uploadResult.error ? (
            <AlertCircle className="w-4 h-4" />
          ) : (
            <CheckCircle2 className="w-4 h-4" />
          )}
          {uploadResult.error || `✓ "${uploadResult.filename}" enviado com sucesso!`}
        </div>
      )}
    </div>
  );
}

// ====================================================================
// CONSULTANT CONTACT CARD
// ====================================================================
function ConsultantCard({ consultor }) {
  if (!consultor) return null;

  const whatsappUrl = consultor.phone
    ? `https://wa.me/351${consultor.phone.replace(/\D/g, '')}`
    : null;

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
      <h3 className="text-base font-bold text-gray-800 mb-3">
        O seu Consultor
      </h3>
      <div className="flex items-center gap-3 mb-4">
        <div className="w-12 h-12 bg-emerald-100 rounded-full flex items-center justify-center text-emerald-700 font-bold text-lg">
          {consultor.name ? consultor.name.charAt(0).toUpperCase() : '?'}
        </div>
        <div>
          <p className="font-semibold text-gray-800">{consultor.name || 'Consultor'}</p>
          <p className="text-sm text-gray-500">
            Power Precision
          </p>
        </div>
      </div>
      <div className="space-y-2">
        {consultor.phone && (
          <a
            href={`tel:${consultor.phone}`}
            className="flex items-center gap-3 p-3 bg-gray-50 rounded-xl hover:bg-gray-100 transition-colors"
          >
            <Phone className="w-5 h-5 text-emerald-600" />
            <span className="text-sm text-gray-700">{consultor.phone}</span>
          </a>
        )}
        {consultor.email && (
          <a
            href={`mailto:${consultor.email}`}
            className="flex items-center gap-3 p-3 bg-gray-50 rounded-xl hover:bg-gray-100 transition-colors"
          >
            <Mail className="w-5 h-5 text-emerald-600" />
            <span className="text-sm text-gray-700">{consultor.email}</span>
          </a>
        )}
        {whatsappUrl && (
          <a
            href={whatsappUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-3 p-3 bg-green-50 rounded-xl hover:bg-green-100 transition-colors"
          >
            <MessageCircle className="w-5 h-5 text-green-600" />
            <span className="text-sm text-green-700 font-medium">WhatsApp</span>
          </a>
        )}
      </div>
    </div>
  );
}

// ====================================================================
// UPLOADED DOCUMENTS LIST
// ====================================================================
function UploadedDocumentsList({ documents }) {
  if (!documents || documents.length === 0) return null;

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
      <h3 className="text-base font-bold text-gray-800 mb-3 flex items-center gap-2">
        <CheckCircle2 className="w-5 h-5 text-emerald-500" />
        Documentos Entregues ({documents.length})
      </h3>
      <div className="space-y-2 max-h-48 overflow-y-auto">
        {documents.map((doc) => (
          <div
            key={doc.id}
            className="flex items-center gap-3 p-2 rounded-lg bg-emerald-50/50"
          >
            <FileText className="w-4 h-4 text-emerald-600 flex-shrink-0" />
            <div className="min-w-0 flex-1">
              <p className="text-sm text-gray-700 truncate">{doc.filename}</p>
              <p className="text-xs text-gray-400">
                {doc.category}
                {doc.uploaded_at && ` · ${new Date(doc.uploaded_at).toLocaleDateString('pt-PT')}`}
              </p>
            </div>
            <Check className="w-4 h-4 text-emerald-500 flex-shrink-0" />
          </div>
        ))}
      </div>
    </div>
  );
}

// ====================================================================
// MAIN CLIENT PORTAL COMPONENT
// ====================================================================
export default function ClientPortal() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);

  // Extract token from URL
  const token = window.location.pathname.split('/portal/')[1];

  useEffect(() => {
    if (!token) {
      setError('Link inválido. Contacte o seu consultor para receber um novo link.');
      setLoading(false);
      return;
    }

    // Store token in sessionStorage (not localStorage to avoid conflicts)
    sessionStorage.setItem('portal_token', token);

    // Fetch portal status
    const fetchStatus = async () => {
      try {
        const response = await fetch(`${BACKEND_URL}/portal/status`, {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (!response.ok) {
          const err = await response.json().catch(() => ({}));
          throw new Error(err.detail || 'Erro ao carregar dados');
        }

        const result = await response.json();
        setData(result);
        setError(null);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchStatus();
  }, [token, refreshKey]);

  const handleUploadSuccess = useCallback(() => {
    setRefreshKey((k) => k + 1);
  }, []);

  // ---- LOADING STATE ----
  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center p-4">
        <div className="text-center">
          <Loader2 className="w-10 h-10 text-emerald-600 animate-spin mx-auto mb-4" />
          <p className="text-gray-600 font-medium">A carregar o seu processo...</p>
        </div>
      </div>
    );
  }

  // ---- ERROR STATE ----
  if (error) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-lg p-8 max-w-md w-full text-center">
          <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <AlertCircle className="w-8 h-8 text-red-500" />
          </div>
          <h2 className="text-xl font-bold text-gray-800 mb-2">Link Inválido</h2>
          <p className="text-gray-600 mb-6">{error}</p>
          <p className="text-sm text-gray-400">
            Se precisa de acesso, contacte o seu consultor.
          </p>
        </div>
      </div>
    );
  }

  if (!data) return null;

  const { process, progress, stepper, documents, consultor } = data;

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
      {/* Header */}
      <header className="bg-white border-b border-gray-100 shadow-sm sticky top-0 z-50">
        <div className="max-w-lg mx-auto px-4 py-4 flex items-center gap-3">
          <div className="w-10 h-10 bg-emerald-600 rounded-xl flex items-center justify-center text-white font-bold text-sm">
            PC
          </div>
          <div className="flex-1 min-w-0">
            <h1 className="text-lg font-bold text-gray-800 truncate">PowerCell</h1>
            <p className="text-xs text-gray-400">Acompanhe o seu processo</p>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-lg mx-auto px-4 py-6 space-y-5 pb-32">
        {/* Greeting */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-400">Olá,</p>
              <h2 className="text-xl font-bold text-gray-800">
                {process.client_name || 'Cliente'}
              </h2>
            </div>
            <div className="text-right">
              <span
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-sm font-medium"
                style={{
                  backgroundColor: process.status_label
                    ? `${data.stepper?.find(s => s.is_current)?.color || '#94a3b8'}20`
                    : '#f1f5f9',
                  color: data.stepper?.find(s => s.is_current)?.color || '#64748b',
                }}
              >
                <Clock className="w-3.5 h-3.5" />
                {process.status_label || process.status}
              </span>
            </div>
          </div>

          {/* Progress bar */}
          <div className="mt-4">
            <div className="flex items-center justify-between text-xs text-gray-500 mb-1">
              <span>Progresso</span>
              <span className="font-medium text-emerald-600">{progress.percent}%</span>
            </div>
            <div className="w-full bg-gray-100 rounded-full h-2.5">
              <div
                className="bg-emerald-500 h-2.5 rounded-full transition-all duration-700 ease-out"
                style={{ width: `${progress.percent}%` }}
              />
            </div>
          </div>
        </div>

        {/* Progress Stepper */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
          <h3 className="text-base font-bold text-gray-800 mb-4">Etapas do Processo</h3>
          <ProgressStepper stepper={stepper} />
        </div>

        {/* Pending Documents CTA */}
        {documents.has_pending && (
          <PendingDocumentsCard
            pending={documents.pending}
            onUpload={handleUploadSuccess}
          />
        )}

        {/* Uploaded Documents */}
        {documents.uploaded && documents.uploaded.length > 0 && (
          <UploadedDocumentsList documents={documents.uploaded} />
        )}

        {/* Consultant Contact */}
        <ConsultantCard consultor={consultor} />
      </main>

      {/* Footer */}
      <footer className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-100 py-3">
        <div className="max-w-lg mx-auto px-4 text-center">
          <p className="text-xs text-gray-400">
            © {new Date().getFullYear()} Power Precision · Crédito Habitação
          </p>
          <p className="text-[10px] text-gray-300 mt-0.5">
            Acesso seguro via Magic Link · Válido por 90 dias
          </p>
        </div>
      </footer>
    </div>
  );
}
