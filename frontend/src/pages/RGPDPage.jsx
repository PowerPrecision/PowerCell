/**
 * RGPD Public Page - Multi-step Form
 *
 * Página pública para assinatura do RGPD pelo cliente.
 * O cliente acede através de um link temporário enviado por email.
 *
 * Step 1: Dados pessoais + Política de Privacidade + Consentimentos
 * Step 2: Minuta de Exclusividade + Assinatura
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { sanitizeHtml } from '../utils/sanitize';
import { validateNIF as validateNIFShared } from '../utils/validateNIF';
import { useParams } from 'react-router-dom';
import { toast } from 'sonner';

const API_URL = process.env.REACT_APP_BACKEND_URL || '';

import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Alert, AlertDescription } from '../components/ui/alert';
import { RadioGroup, RadioGroupItem } from '../components/ui/radio-group';
import {
  Loader2,
  CheckCircle,
  AlertTriangle,
  Clock,
  FileText,
  Shield,
  ChevronRight,
  ChevronLeft,
  PenLine,
  RotateCcw,
} from 'lucide-react';

// ====================================================================
// CONCELHOS DE PORTUGAL - Lista de concelhos
// ====================================================================
const CONCELHOS = [
  "Abrantes", "Águeda", "Albergaria-a-Velha", "Albufeira", "Alcácer do Sal",
  "Alcanena", "Alcobaça", "Alcochete", "Alcoutim", "Alenquer", "Alfândega da Fé",
  "Alijó", "Aljezur", "Aljustrel", "Almada", "Almeida", "Almeirim", "Almodôvar",
  "Alpiarça", "Alter do Chão", "Alvaiázere", "Alvito", "Amadora", "Amarante",
  "Amares", "Anadia", "Angra do Heroísmo", "Arcos de Valdevez", "Arganil",
  "Armamar", "Arouca", "Arraiolos", "Arronches", "Arruda dos Vinhos", "Aveiro",
  "Avis", "Azambuja", "Baião", "Barcelos", "Barrancos", "Barreiro", "Batalha",
  "Beja", "Belmonte", "Benavente", "Bombarral", "Borba", "Boticas", "Braga",
  "Bragança", "Cabeceiras de Basto", "Cadalde", "Caldas da Rainha", "Calheta",
  "Câmara de Lobos", "Caminha", "Campo Maior", "Cantanhede", "Carrazeda de Ansiães",
  "Carregal do Sal", "Carregal do Sal", "Cartaxo", "Cascais", "Castanheira de Pera",
  "Castelo Branco", "Castelo de Vide", "Castro Daire", "Castro Marim", "Castro Verde",
  "Celorico da Beira", "Celorico de Basto", "Chamusca", "Chaves", "Cinfães",
  "Coimbra", "Condeixa-a-Nova", "Constância", "Coruche", "Corvo", "Covilhã",
  "Crato", "Cuba", "Elvas", "Entroncamento", "Espinho", "Esposende", "Estarreja",
  "Estremoz", "Évora", "Fafe", "Faro", "Felgueiras", "Ferreira do Alentejo",
  "Ferreira do Zêzere", "Figueira da Foz", "Figueiró dos Vinhos", "Fornos de Algodres",
  "Freamunde", "Freixo de Espada à Cinta", "Fronteira", "Funchal", "Fundão",
  "Gavião", "Góis", "Golegã", "Gondomar", "Gouveia", "Grandola", "Guarda",
  "Guimarães", "Horta", "Idanha-a-Nova", "Ílhavo", "Lagoa", "Lagoa", "Lagos",
  "Lamego", "Leiria", "Lisboa", "Loulé", "Loures", "Lourinhã", "Macedo de Cavaleiros",
  "Machico", "Maia", "Mangualde", "Manteigas", "Marco de Canaveses", "Marinha Grande",
  "Marvão", "Matosinhos", "Mealhada", "Mêda", "Melgaço", "Mértola", "Mesão Frio",
  "Mira", "Miranda do Corvo", "Miranda do Douro", "Mirandela", "Mogadouro",
  "Moimenta da Beira", "Moita", "Monção", "Monchique", "Mondim de Basto",
  "Monforte", "Montalegre", "Montemor-o-Novo", "Montemor-o-Velho", "Montijo",
  "Mora", "Mortágua", "Moura", "Mourão", "Murça", "Murtosa", "Nazaré", "Nelas",
  "Nisa", "Nordeste", "Óbidos", "Odemira", "Odivelas", "Oeiras", "Oleiros",
  "Olhão", "Oliveira de Azeméis", "Oliveira de Frades", "Oliveira do Bairro",
  "Oliveira do Hospital", "Ourém", "Ourique", "Ovar", "Palmela", "Pampilhosa da Serra",
  "Paredes", "Paredes de Coura", "Pedrógão Grande", "Penacova", "Penafiel",
  "Penalva do Castelo", "Penedono", "Penela", "Peniche", "Peso da Régua",
  "Pinhel", "Pombal", "Ponta Delgada", "Ponta do Sol", "Ponte de Lima",
  "Ponte de Sor", "Portalegre", "Portel", "Portimão", "Porto", "Porto de Mós",
  "Porto Moniz", "Porto Santo", "Póvoa de Lanhoso", "Póvoa de Varzim", "Povoação",
  "Proença-a-Nova", "Redondo", "Reguengos de Monsaraz", "Resende", "Ribeira Brava",
  "Ribeira de Pena", "Ribeira Grande", "Rio Maior", "Sabrosa", "Sabugal",
  "Salvaterra de Magos", "Santa Comba Dão", "Santa Cruz", "Santa Cruz da Graciosa",
  "Santa Cruz das Flores", "Santa Maria da Feira", "Santana", "Santarém", "Santiago do Cacém",
  "Santo Tirso", "São Brás de Alportel", "São João da Madeira", "São João da Pesqueira",
  "São Pedro do Sul", "São Roque do Pico", "São Vicente", "Sardoal", "Sátão",
  "Seia", "Seixal", "Sernancelhe", "Serpa", "Sertã", "Setúbal", "Sever do Vouga",
  "Silves", "Sines", "Sintra", "Sobral de Monte Agraço", "Soure", "Sousel",
  "Tábua", "Tabuaço", "Tarouca", "Tavira", "Terras de Bouro", "Tomar", "Tondela",
  "Torre de Moncorvo", "Torres Novas", "Torres Vedras", "Trancoso", "Trofa",
  "Vagos", "Vale de Cambra", "Valença", "Valongo", "Valpaços", "Velas",
  "Vendas Novas", "Viana do Alentejo", "Viana do Castelo", "Vidigueira",
  "Vieira do Minho", "Vila de Rei", "Vila do Conde", "Vila do Porto",
  "Vila Flor", "Vila Franca da Beira", "Vila Franca de Xira", "Vila Franca do Campo",
  "Vila Nova da Barquinha", "Vila Nova de Cerveira", "Vila Nova de Famalicão",
  "Vila Nova de Foz Côa", "Vila Nova de Gaia", "Vila Nova de Paiva",
  "Vila Nova de Poiares", "Vila Pouca de Aguiar", "Vila Real", "Vila Real de Santo António",
  "Vila Velha de Ródão", "Vila Viçosa", "Vimioso", "Vinhais", "Viseu", "Vizela",
  "Vouzela",
];

// ====================================================================
// TIPOS DE DOCUMENTO
// ====================================================================
const TIPOS_DOCUMENTO = [
  { value: 'bilhete_de_identidade', label: 'Bilhete de Identidade' },
  { value: 'cartao_de_cidadao', label: 'Cartão de Cidadão' },
  { value: 'passaporte', label: 'Passaporte' },
  { value: 'carta_de_conducao', label: 'Carta de Condução' },
  { value: 'autorizacao_de_residencia', label: 'Autorização de Residência' },
];

// ====================================================================
// CONSENT DEFINITIONS
// ====================================================================
const CONSENTS = [
  {
    key: 'consent_a',
    letter: 'A',
    label: 'Transmissão de dados à entidade vinculada',
    description:
      'Autorizo a transmissão dos meus dados pessoais à entidade vinculada, para efeitos da análise e celebração do contrato de crédito.',
  },
  {
    key: 'consent_b',
    letter: 'B',
    label: 'Divulgação de produtos/serviços',
    description:
      'Autorizo a utilização dos meus dados pessoais para efeitos de divulgação de produtos e serviços da Precisiontime, Lda.',
  },
  {
    key: 'consent_c',
    letter: 'C',
    label: 'Consulta Central de Responsabilidades de Crédito',
    description:
      'Autorizo a consulta da minha situação na Central de Responsabilidades de Crédito do Banco de Portugal.',
  },
  {
    key: 'consent_d',
    letter: 'D',
    label: 'Transmissão para propostas de financiamento',
    description:
      'Autorizo a transmissão dos meus dados pessoais a instituições de crédito para efeitos de apresentação de propostas de financiamento.',
  },
];

// ====================================================================
// NIF VALIDATION
// ====================================================================
// Delega o checksum para o utilitário partilhado; mantém a permissão de NIFs
// de empresa (comportamento original desta página, para pessoas e outras entidades).
const validateNIF = (nif) => validateNIFShared(nif, { allowCompanyNIF: true }).valid;

// ====================================================================
// CC (CARTÃO DE CIDADÃO) VALIDATION
// ====================================================================
const validateCC = (cc) => {
  if (!cc) return false;
  const cleaned = cc.trim().replace(/\s/g, '');
  // CC format: 8 digits + 1 check digit + 2 alphanumerical check chars
  // With spaces: XXXXXXXX X ZZ (12 chars) or without: XXXXXXXXX ZZ (11 chars)
  const pattern = /^\d{8}\d?[A-Z0-9]{2}$/i;
  if (!pattern.test(cleaned)) return false;
  if (cleaned.length < 11 || cleaned.length > 12) return false;
  return true;
};

const formatCC = (value) => {
  const cleaned = value.replace(/[^\dA-Za-z]/g, '').toUpperCase();
  if (cleaned.length <= 8) return cleaned;
  if (cleaned.length <= 9) return `${cleaned.slice(0, 8)} ${cleaned.slice(8)}`;
  return `${cleaned.slice(0, 8)} ${cleaned.slice(8, 9)} ${cleaned.slice(9, 11)}`;
};

// ====================================================================
// FORMAT HELPERS
// ====================================================================
const formatCodigoPostal = (value) => {
  const cleaned = value.replace(/\D/g, '');
  if (cleaned.length <= 4) return cleaned;
  return `${cleaned.slice(0, 4)}-${cleaned.slice(4, 7)}`;
};

const formatDate = (value) => {
  const cleaned = value.replace(/\D/g, '');
  if (cleaned.length <= 2) return cleaned;
  if (cleaned.length <= 4) return `${cleaned.slice(0, 2)}-${cleaned.slice(2)}`;
  return `${cleaned.slice(0, 2)}-${cleaned.slice(2, 4)}-${cleaned.slice(4, 8)}`;
};

// Converte qualquer formato de data para DD-MM-AAAA.
// Aceita: ISO (AAAA-MM-DD), DD-MM-AAAA, DD/MM/AAAA, AAAA/MM/DD, Date object.
const toDisplayDate = (value) => {
  if (!value) return '';
  if (typeof value === 'string') {
    const s = value.trim();
    // Já está em DD-MM-AAAA
    if (/^\d{2}-\d{2}-\d{4}$/.test(s)) return s;
    // ISO AAAA-MM-DD (com ou sem hora)
    const iso = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (iso) return `${iso[3]}-${iso[2]}-${iso[1]}`;
    // DD/MM/AAAA
    const slash = s.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    if (slash) return `${slash[1]}-${slash[2]}-${slash[3]}`;
    // AAAA/MM/DD
    const slashIso = s.match(/^(\d{4})\/(\d{2})\/(\d{2})$/);
    if (slashIso) return `${slashIso[3]}-${slashIso[2]}-${slashIso[1]}`;
    return s;
  }
  if (value instanceof Date && !isNaN(value)) {
    const dd = String(value.getDate()).padStart(2, '0');
    const mm = String(value.getMonth() + 1).padStart(2, '0');
    const yyyy = value.getFullYear();
    return `${dd}-${mm}-${yyyy}`;
  }
  return '';
};

// ====================================================================
// SIGNATURE PAD COMPONENT
// ====================================================================
function SignaturePad({ onSignatureChange }) {
  const canvasRef = useRef(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [hasSignature, setHasSignature] = useState(false);

  const getCanvasCoordinates = useCallback((e) => {
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const clientX = e.clientX ?? e.touches?.[0]?.clientX ?? 0;
    const clientY = e.clientY ?? e.touches?.[0]?.clientY ?? 0;
    return {
      x: (clientX - rect.left) * scaleX,
      y: (clientY - rect.top) * scaleY,
    };
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    ctx.strokeStyle = '#000';
    ctx.lineWidth = 2;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
  }, []);

  const startDrawing = useCallback(
    (e) => {
      e.preventDefault();
      const canvas = canvasRef.current;
      const ctx = canvas.getContext('2d');
      const { x, y } = getCanvasCoordinates(e);

      setIsDrawing(true);
      setHasSignature(true);
      ctx.beginPath();
      ctx.moveTo(x, y);
    },
    [getCanvasCoordinates]
  );

  const draw = useCallback(
    (e) => {
      e.preventDefault();
      if (!isDrawing) return;

      const canvas = canvasRef.current;
      const ctx = canvas.getContext('2d');
      const { x, y } = getCanvasCoordinates(e);

      ctx.lineTo(x, y);
      ctx.stroke();
    },
    [isDrawing, getCanvasCoordinates]
  );

  const stopDrawing = useCallback(() => {
    if (isDrawing) {
      setIsDrawing(false);
      const canvas = canvasRef.current;
      const signatureData = canvas.toDataURL('image/png');
      onSignatureChange(signatureData);
    }
  }, [isDrawing, onSignatureChange]);

  const clearSignature = () => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    setHasSignature(false);
    onSignatureChange(null);
  };

  return (
    <div className="space-y-2">
      <Label className="flex items-center gap-2">
        <PenLine className="h-4 w-4" />
        Assinatura *
      </Label>
      {/* Mobile landscape hint */}
      <div className="block sm:hidden">
        <p className="text-xs text-amber-600 bg-amber-50 dark:bg-amber-950/30 dark:text-amber-400 px-2 py-1.5 rounded">
          💡 Sugestão: Rode o dispositivo para o modo horizontal (paisagem) para uma melhor experiência de assinatura.
        </p>
      </div>
      <div className="border-2 border-dashed border-muted-foreground/30 rounded-lg overflow-hidden bg-white dark:bg-slate-50">
        <canvas
          ref={canvasRef}
          width={600}
          height={180}
          className="w-full cursor-crosshair touch-none"
          onMouseDown={startDrawing}
          onMouseMove={draw}
          onMouseUp={stopDrawing}
          onMouseLeave={stopDrawing}
          onTouchStart={startDrawing}
          onTouchMove={draw}
          onTouchEnd={stopDrawing}
        />
      </div>
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          Desenhe a sua assinatura na área acima
        </p>
        {hasSignature && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={clearSignature}
            className="text-muted-foreground hover:text-destructive"
          >
            <RotateCcw className="h-3 w-3 mr-1" />
            Limpar
          </Button>
        )}
      </div>
    </div>
  );
}

// ====================================================================
// STEP INDICATOR COMPONENT
// ====================================================================
function StepIndicator({ currentStep }) {
  return (
  <div className="flex items-center justify-center gap-4 mb-6">
    <div
      className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium transition-colors ${
        currentStep === 1
          ? 'bg-primary text-primary-foreground'
          : 'bg-muted text-muted-foreground'
      }`}
    >
      <span className="flex items-center justify-center h-6 w-6 rounded-full bg-primary-foreground/20 text-xs font-bold">
        1
      </span>
      Dados Pessoais
    </div>
    <div className="h-px w-8 bg-border" />
    <div
      className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium transition-colors ${
        currentStep === 2
          ? 'bg-primary text-primary-foreground'
          : 'bg-muted text-muted-foreground'
      }`}
    >
      <span className="flex items-center justify-center h-6 w-6 rounded-full bg-primary-foreground/20 text-xs font-bold">
        2
      </span>
      Assinatura
    </div>
  </div>
  );
}

// ====================================================================
// MAIN PAGE COMPONENT
// ====================================================================
export default function RGPDPage() {
  const { token } = useParams();

  // ------------------------------------------------------------------
  // STATES
  // ------------------------------------------------------------------
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [step, setStep] = useState(1);
  const [, setTokenData] = useState(null);
  const [formData, setFormData] = useState(null);

  // Form fields
  const [form, setForm] = useState({
    nome: '',
    contribuinte: '',
    tipo_documento: '',
    numero_documento: '',
    validade_documento: '',
    morada: '',
    localidade: '',
    codigo_postal: '',
    consent_a: '',
    consent_b: '',
    consent_c: '',
    consent_d: '',
    assinatura: null,
  });

  // ------------------------------------------------------------------
  // TOKEN VALIDATION & DATA FETCH
  // ------------------------------------------------------------------
  useEffect(() => {
    const init = async () => {
      if (!token) {
        setError('Token não fornecido');
        setLoading(false);
        return;
      }

      try {
        // Validate token
        const validateRes = await fetch(`${API_URL}/api/rgpd/validate/${token}`);
        if (!validateRes.ok) {
          const errData = await validateRes.json().catch(() => ({}));
          throw new Error(errData.detail || 'Token inválido ou expirado');
        }
        const validData = await validateRes.json();
        setTokenData(validData);

        // Fetch pre-filled data
        const dataRes = await fetch(`${API_URL}/api/rgpd/data/${token}`);
        if (dataRes.ok) {
          const prefilled = await dataRes.json();
          setFormData(prefilled);
          setForm((prev) => ({
            ...prev,
            nome: prefilled.client_name || prev.nome,
            contribuinte: prefilled.nif || prev.contribuinte,
            tipo_documento: prefilled.tipo_documento || prev.tipo_documento,
            numero_documento: prefilled.numero_documento || prev.numero_documento,
            validade_documento: toDisplayDate(prefilled.validade_documento) || prev.validade_documento,
            morada: prefilled.morada || prev.morada,
            localidade: prefilled.localidade || prev.localidade,
            codigo_postal: prefilled.codigo_postal || prev.codigo_postal,
          }));
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    init();
  }, [token]);

  // ------------------------------------------------------------------
  // HANDLERS
  // ------------------------------------------------------------------
  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSelectChange = (name, value) => {
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSignatureChange = useCallback((signature) => {
    setForm((prev) => ({ ...prev, assinatura: signature }));
  }, []);

  const handleConsentChange = (key, value) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  // ------------------------------------------------------------------
  // STEP 1 VALIDATION
  // ------------------------------------------------------------------
  const validateStep1 = () => {
    const requiredFields = [
      'nome',
      'contribuinte',
      'tipo_documento',
      'numero_documento',
      'validade_documento',
      'morada',
      'localidade',
      'codigo_postal',
    ];

    for (const field of requiredFields) {
      if (!form[field] || form[field].trim() === '') {
        toast.error('Por favor preencha todos os campos obrigatórios');
        return false;
      }
    }

    // NIF validation
    if (form.contribuinte.length !== 9) {
      toast.error('O NIF (Contribuinte) deve ter exatamente 9 dígitos');
      return false;
    }
    if (!validateNIF(form.contribuinte)) {
      toast.error('O NIF inserido não é válido');
      return false;
    }

    // Date validation (DD-MM-AAAA)
    const dateRegex = /^\d{2}-\d{2}-\d{4}$/;
    if (!dateRegex.test(form.validade_documento)) {
      toast.error('A validade do documento deve estar no formato DD-MM-AAAA');
      return false;
    }

    // Postal code validation (XXXX-XXX)
    const postalRegex = /^\d{4}-\d{3}$/;
    if (!postalRegex.test(form.codigo_postal)) {
      toast.error('O código postal deve estar no formato XXXX-XXX');
      return false;
    }

    // CC format validation (if Cartão de Cidadão selected)
    if (form.tipo_documento === 'cartao_de_cidadao' && !validateCC(form.numero_documento)) {
      toast.error('O número do Cartão de Cidadão não é válido (ex: 00000000 0 AA)');
      return false;
    }

    // Consent validation
    const consentKeys = ['consent_a', 'consent_b', 'consent_c', 'consent_d'];
    for (const key of consentKeys) {
      if (!form[key]) {
        toast.error('Por favor seleccione todas as opções de consentimento (A, B, C e D)');
        return false;
      }
    }

    return true;
  };

  // ------------------------------------------------------------------
  // STEP 2 VALIDATION (full)
  // ------------------------------------------------------------------
  const validateStep2 = () => {
    if (!validateStep1()) return false;
    if (!form.assinatura) {
      toast.error('Por favor assine o documento');
      return false;
    }
    return true;
  };

  // ------------------------------------------------------------------
  // NAVIGATION
  // ------------------------------------------------------------------
  const goToStep2 = () => {
    if (validateStep1()) {
      setStep(2);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  };

  const goToStep1 = () => {
    setStep(1);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // ------------------------------------------------------------------
  // SUBMIT
  // ------------------------------------------------------------------
  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!validateStep2()) return;

    setSubmitting(true);
    try {
      const payload = {
        nome: form.nome.trim(),
        contribuinte: form.contribuinte.trim(),
        tipo_documento: form.tipo_documento,
        numero_documento: form.numero_documento.trim(),
        validade_documento: form.validade_documento.trim(),
        morada: form.morada.trim(),
        localidade: form.localidade.trim(),
        codigo_postal: form.codigo_postal.trim(),
        consent_a: form.consent_a,
        consent_b: form.consent_b,
        consent_c: form.consent_c,
        consent_d: form.consent_d,
        assinatura: form.assinatura,
      };

      const response = await fetch(`${API_URL}/api/rgpd/sign/${token}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Erro ao assinar o documento RGPD');
      }

      setSuccess(true);
      toast.success('Documento RGPD assinado com sucesso!');
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  // ------------------------------------------------------------------
  // RENDER: LOADING
  // ------------------------------------------------------------------
  if (loading) {
    return (
      <div className="min-h-screen bg-muted/30 flex items-center justify-center">
        <div className="max-w-lg w-full mx-auto space-y-4 p-6">
          <div className="h-10 w-48 bg-muted animate-pulse rounded mx-auto" />
          <div className="h-4 w-72 bg-muted animate-pulse rounded mx-auto" />
          <div className="h-40 bg-muted animate-pulse rounded-lg" />
          <div className="h-32 bg-muted animate-pulse rounded-lg" />
          <div className="flex justify-center pt-2">
            <Loader2 className="h-6 w-6 text-muted-foreground animate-spin" />
          </div>
        </div>
      </div>
    );
  }

  // ------------------------------------------------------------------
  // RENDER: ERROR
  // ------------------------------------------------------------------
  if (error) {
    return (
      <div className="min-h-screen bg-muted/30 flex items-center justify-center p-4">
        <Card className="max-w-md w-full border-destructive/30">
          <CardContent className="pt-6">
            <div className="text-center">
              <AlertTriangle className="h-12 w-12 text-destructive mx-auto" />
              <h2 className="mt-4 text-xl font-semibold text-foreground">
                Link Inválido
              </h2>
              <p className="mt-2 text-muted-foreground">{error}</p>
              <p className="mt-4 text-sm text-muted-foreground">
                O link pode ter expirado (24h) ou já ter sido utilizado. Por
                favor contacte o seu intermediário de crédito.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // ------------------------------------------------------------------
  // RENDER: SUCCESS
  // ------------------------------------------------------------------
  if (success) {
    return (
      <div className="min-h-screen bg-muted/30 flex items-center justify-center p-4">
        <Card className="max-w-md w-full">
          <CardContent className="pt-6">
            <div className="text-center">
              <div className="mx-auto h-16 w-16 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center mb-4">
                <CheckCircle className="h-10 w-10 text-green-600 dark:text-green-400" />
              </div>
              <h2 className="mt-2 text-xl font-semibold text-foreground">
                Assinatura de Consentimento RGPD enviada com sucesso
              </h2>
              <p className="mt-3 text-muted-foreground">
                Obrigado pela sua confiança!
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // ------------------------------------------------------------------
  // RENDER: FORM
  // ------------------------------------------------------------------
  return (
    <div className="min-h-screen bg-muted/30 py-6 px-4 sm:py-8">
      <div className="max-w-4xl mx-auto">
        {/* ============================================================ */}
        {/* HEADER                                                       */}
        {/* ============================================================ */}
        <div className="bg-card rounded-lg shadow-sm p-4 sm:p-5 mb-6 border border-border">
          <div className="flex items-center justify-between">
            <img
              src="https://5af40e69fb2205f1674bdd6edbe227cd.cdn.bubble.io/cdn-cgi/image/w=,h=,f=auto,dpr=1,fit=contain/f1744120174601x242645494868973340/logo-transp-crm-ok-300x90%20%281%29.png"
              alt="Precision Crédito"
              className="h-10"
            />
            <div className="flex items-center gap-2">
              <img
                src="https://f0e785c1333181247df815fb60475618.cdn.bubble.io/cdn-cgi/image/w=64,h=64,f=auto,dpr=1,fit=contain/f1701108491434x891671701074144900/bandeira%20%281%29.png"
                alt="Portugal"
                className="h-5"
              />
              <span className="text-sm text-muted-foreground hidden sm:inline">
                Português
              </span>
            </div>
          </div>
        </div>

        {/* ============================================================ */}
        {/* SECURITY ALERT                                               */}
        {/* ============================================================ */}
        <Alert className="mb-6 border-amber-300 bg-amber-50 dark:bg-amber-950/30 dark:border-amber-800">
          <Clock className="h-4 w-4 text-amber-600 dark:text-amber-400" />
          <AlertDescription className="text-amber-800 dark:text-amber-300">
            <strong>Atenção:</strong> Este link expira em 24 horas por motivos
            de segurança. Após esse período, será necessário solicitar um novo
            link ao seu intermediário de crédito.
          </AlertDescription>
        </Alert>

        {/* ============================================================ */}
        {/* STEP INDICATOR                                               */}
        {/* ============================================================ */}
        <StepIndicator currentStep={step} />

        {/* ============================================================ */}
        {/* STEP 1 - DADOS PESSOAIS + PRIVACIDADE + CONSENTIMENTOS       */}
        {/* ============================================================ */}
        {step === 1 && (
          <div className="space-y-6">
            {/* INFORMAÇÃO AO CONSUMIDOR */}
            <Card className="overflow-hidden">
              <CardHeader className="bg-primary/10 dark:bg-primary/5 border-b border-border">
                <CardTitle className="text-center text-sm sm:text-base text-foreground leading-snug">
                  INFORMAÇÃO AO CONSUMIDOR NO ÂMBITO DA ATIVIDADE DE
                  INTERMEDIÁRIO DE CRÉDITO
                </CardTitle>
                <p className="text-center text-xs sm:text-sm text-muted-foreground">
                  Art.º 54.º do Decreto-Lei n.º81-C/2017 de 7 de Julho –
                  Regime Jurídico dos Intermediários de Crédito
                </p>
                <p className="text-center text-sm font-semibold text-foreground">
                  Atividade sujeita à supervisão do Banco de Portugal
                </p>
              </CardHeader>
              <CardContent className="pt-4 space-y-3">
                <p className="text-sm text-muted-foreground">
                  <strong className="text-foreground">Precisiontime, Lda</strong>,
                  com sede na Rua de Santa Cruz do Castelo, n.º 22, 1.º Andar,
                  1100-480, Lisboa,{' '}
                  <strong className="text-foreground">
                    Intermediário de crédito, autorizado pelo Banco de Portugal
                    na categoria de intermediários de crédito Vinculado, com o
                    número de registo 0008026
                  </strong>{' '}
                  (consulta pública da lista de intermediários de crédito
                  autorizados pelo Banco de Portugal em{' '}
                  <a
                    href="https://www.bportugal.pt/intermediariocreditofar/precisiontime-lda"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary hover:underline"
                  >
                    www.bportugal.pt
                  </a>
                  )
                </p>
                <p className="text-sm text-muted-foreground">
                  No âmbito da atividade que desenvolve, encontra-se habilitado
                  para a intermediação de contratos de Crédito Hipotecário e está
                  autorizado a prestar os serviços de: apresentação ou proposta de
                  contratos de crédito a consumidores; assistência a consumidores,
                  mediante a realização de atos preparatórios ou de outros
                  trabalhos de gestão pré-contratual relativamente a contratos de
                  crédito que não tenham sido por si apresentados ou propostos.
                </p>
                <p className="text-sm text-muted-foreground">
                  <strong className="text-foreground">
                    Mutuantes com quem o intermediário de crédito tem contrato de
                    vinculação:
                  </strong>{' '}
                  NovoBanco S.A, Caixa Geral de Depósitos, Banco CTT, Banco
                  Santander Totta SA, Eurobic/Abanca, Bankinter SA
                </p>
                <p className="text-sm text-muted-foreground">
                  O intermediário de crédito está interdito de receber ou entregar
                  quaisquer valores relacionados com a formação, execução e o
                  cumprimento antecipado dos contratos de crédito.
                </p>
              </CardContent>
            </Card>

            {/* FORMULÁRIO DE DADOS PESSOAIS */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Shield className="h-5 w-5 text-primary" />
                  Dados Pessoais
                </CardTitle>
                <p className="text-muted-foreground text-sm">
                  Preencha os seus dados pessoais. Todos os campos são de
                  preenchimento obrigatório.
                </p>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Row 1: Nome + Contribuinte */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <Label htmlFor="nome">
                      Nome <span className="text-destructive">*</span>
                    </Label>
                    <Input
                      id="nome"
                      name="nome"
                      value={form.nome}
                      onChange={handleInputChange}
                      placeholder="Nome completo"
                      required
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="contribuinte">
                      Contribuinte (NIF) <span className="text-destructive">*</span>
                    </Label>
                    <Input
                      id="contribuinte"
                      name="contribuinte"
                      value={form.contribuinte}
                      onChange={(e) => {
                        const v = e.target.value.replace(/\D/g, '').slice(0, 9);
                        setForm((prev) => ({ ...prev, contribuinte: v }));
                      }}
                      placeholder="9 dígitos"
                      maxLength={9}
                      required
                    />
                    {form.contribuinte.length === 9 &&
                      !validateNIF(form.contribuinte) && (
                        <p className="text-xs text-destructive">
                          NIF inválido
                        </p>
                      )}
                    {form.contribuinte.length === 9 &&
                      validateNIF(form.contribuinte) && (
                        <p className="text-xs text-green-600">
                          ✓ NIF válido
                        </p>
                      )}
                  </div>
                </div>

                {/* Row 2: Tipo de Documento + Número do Documento */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <Label>
                      Tipo de Documento <span className="text-destructive">*</span>
                    </Label>
                    <Select
                      value={form.tipo_documento}
                      onValueChange={(v) =>
                        handleSelectChange('tipo_documento', v)
                      }
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Selecione o tipo" />
                      </SelectTrigger>
                      <SelectContent>
                        {TIPOS_DOCUMENTO.map((doc) => (
                          <SelectItem key={doc.value} value={doc.value}>
                            {doc.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="numero_documento">
                      Número do Documento <span className="text-destructive">*</span>
                    </Label>
                    <Input
                      id="numero_documento"
                      name="numero_documento"
                      value={form.numero_documento}
                      onChange={(e) => {
                        const formatted = form.tipo_documento === 'cartao_de_cidadao'
                          ? formatCC(e.target.value)
                          : e.target.value;
                        setForm((prev) => ({ ...prev, numero_documento: formatted }));
                      }}
                      placeholder={form.tipo_documento === 'cartao_de_cidadao' ? '00000000 0 AA' : 'Número de identificação'}
                      maxLength={form.tipo_documento === 'cartao_de_cidadao' ? 14 : 30}
                      required
                    />
                    {form.tipo_documento === 'cartao_de_cidadao' && form.numero_documento && !validateCC(form.numero_documento) && (
                      <p className="text-xs text-destructive">
                        Formato de CC inválido (ex: 00000000 0 AA)
                      </p>
                    )}
                    {form.tipo_documento === 'cartao_de_cidadao' && validateCC(form.numero_documento) && (
                      <p className="text-xs text-green-600">
                        ✓ Formato de CC válido
                      </p>
                    )}
                  </div>
                </div>

                {/* Row 3: Validade do Documento */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <Label htmlFor="validade_documento">
                      Validade do Documento{' '}
                      <span className="text-destructive">*</span>
                    </Label>
                    <Input
                      id="validade_documento"
                      name="validade_documento"
                      value={form.validade_documento}
                      onChange={(e) => {
                        const formatted = formatDate(e.target.value);
                        setForm((prev) => ({
                          ...prev,
                          validade_documento: formatted,
                        }));
                      }}
                      placeholder="DD-MM-AAAA"
                      maxLength={10}
                      required
                    />
                  </div>
                </div>

                {/* Row 4: Morada (full width) */}
                <div className="space-y-1.5">
                  <Label htmlFor="morada">
                    Morada <span className="text-destructive">*</span>
                  </Label>
                  <Input
                    id="morada"
                    name="morada"
                    value={form.morada}
                    onChange={handleInputChange}
                    placeholder="Rua, número, andar"
                    required
                  />
                </div>

                {/* Row 5: Localidade + Código Postal */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <Label htmlFor="localidade">
                      Localidade <span className="text-destructive">*</span>
                    </Label>
                    <Select
                      value={form.localidade}
                      onValueChange={(v) =>
                        handleSelectChange('localidade', v)
                      }
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Selecione a localidade" />
                      </SelectTrigger>
                      <SelectContent>
                        {CONCELHOS.map((c) => (
                          <SelectItem key={c} value={c}>
                            {c}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="codigo_postal">
                      Código Postal <span className="text-destructive">*</span>
                    </Label>
                    <Input
                      id="codigo_postal"
                      name="codigo_postal"
                      value={form.codigo_postal}
                      onChange={(e) => {
                        const formatted = formatCodigoPostal(e.target.value);
                        setForm((prev) => ({
                          ...prev,
                          codigo_postal: formatted,
                        }));
                      }}
                      placeholder="XXXX-XXX"
                      maxLength={8}
                      required
                    />
                  </div>
                </div>

                {/* ============================================================ */}
                {/* POLÍTICA DE PRIVACIDADE (dynamic from backend template)        */}
                {/* ============================================================ */}
                <div className="bg-muted/40 border border-border rounded-lg p-4 sm:p-5 space-y-3">
                  <h3 className="font-semibold text-foreground text-sm flex items-center gap-2">
                    <FileText className="h-4 w-4 text-primary" />
                    POLÍTICA DE PRIVACIDADE
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    (Ao abrigo do Regulamento Geral sobre a Proteção de Dados
                    Pessoais)
                  </p>
                  {/*
                    Usamos uma div com overflow-y:auto em vez de Radix ScrollArea
                    para garantir scroll fiável em mobile e evitar que o conteúdo
                    apareça truncado. min-h garante que mesmo em ecrãs muito
                    pequenos há sempre uma janela usável de leitura.
                  */}
                  <div
                    className="max-h-[60vh] min-h-[16rem] overflow-y-auto overscroll-contain rounded border border-border/40 bg-background/60 p-3 pr-4"
                    data-testid="rgpd-policy-scroll"
                  >
                    {formData?.rgpd_text ? (
                      <div
                        className="space-y-3 text-xs sm:text-sm text-foreground/90 leading-relaxed prose prose-sm dark:prose-invert max-w-none break-words"
                        dangerouslySetInnerHTML={{ __html: sanitizeHtml(formData.rgpd_text) }}
                      />
                    ) : (
                      <div className="space-y-3 text-xs text-muted-foreground">
                        <p className="italic">Texto da política de privacidade indisponível. O documento será gerado com o texto padrão após a assinatura.</p>
                      </div>
                    )}
                  </div>
                </div>

                {/* ============================================================ */}
                {/* CONSENTIMENTOS (A, B, C, D)                                  */}
                {/* ============================================================ */}
                <div className="space-y-4">
                  <h3 className="font-semibold text-foreground text-sm flex items-center gap-2">
                    <Shield className="h-4 w-4 text-primary" />
                    Consentimentos
                    <span className="text-xs text-muted-foreground font-normal">
                      — Todos os campos são de preenchimento obrigatório
                    </span>
                  </h3>

                  {CONSENTS.map((consent) => (
                    <div
                      key={consent.key}
                      className="bg-muted/30 border border-border rounded-lg p-4 space-y-3"
                    >
                      <div className="flex items-start gap-3">
                        <span className="flex items-center justify-center shrink-0 h-7 w-7 rounded-full bg-primary/10 text-primary text-xs font-bold">
                          {consent.letter}
                        </span>
                        <div className="space-y-1 flex-1">
                          <p className="text-sm font-medium text-foreground">
                            {consent.label}
                            <span className="text-destructive"> *</span>
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {consent.description}
                          </p>
                        </div>
                      </div>
                      <RadioGroup
                        value={form[consent.key]}
                        onValueChange={(v) =>
                          handleConsentChange(consent.key, v)
                        }
                        className="flex flex-row gap-4 sm:gap-6 pl-10"
                      >
                        <div className="flex items-center gap-2">
                          <RadioGroupItem
                            value="autorizo"
                            id={`${consent.key}_autorizo`}
                          />
                          <Label
                            htmlFor={`${consent.key}_autorizo`}
                            className="text-sm font-medium cursor-pointer"
                          >
                            Autorizo
                          </Label>
                        </div>
                        <div className="flex items-center gap-2">
                          <RadioGroupItem
                            value="nao_autorizo"
                            id={`${consent.key}_nao_autorizo`}
                          />
                          <Label
                            htmlFor={`${consent.key}_nao_autorizo`}
                            className="text-sm font-medium cursor-pointer"
                          >
                            Não Autorizo
                          </Label>
                        </div>
                      </RadioGroup>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* NAVIGATION BUTTON */}
            <div className="flex justify-end">
              <Button
                type="button"
                onClick={goToStep2}
                className="bg-primary hover:bg-primary/90 text-primary-foreground px-6"
              >
                Seguinte
                <ChevronRight className="ml-1 h-4 w-4" />
              </Button>
            </div>
          </div>
        )}

        {/* ============================================================ */}
        {/* STEP 2 - MINUTA DE EXCLUSIVIDADE + ASSINATURA                */}
        {/* ============================================================ */}
        {step === 2 && (
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* MINUTA DE EXCLUSIVIDADE */}
            <Card className="overflow-hidden">
              <CardHeader className="bg-primary/10 dark:bg-primary/5 border-b border-border">
                <CardTitle className="text-center text-sm sm:text-base text-foreground leading-snug">
                  MINUTA DE EXCLUSIVIDADE
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-4">
                {formData?.minuta_text ? (
                  <div
                    className="max-h-[60vh] min-h-[16rem] overflow-y-auto overscroll-contain rounded border border-border/40 bg-background/60 p-3 pr-4"
                    data-testid="rgpd-minuta-scroll"
                  >
                    <div
                      className="text-sm text-foreground/90 leading-relaxed whitespace-pre-wrap break-words"
                      dangerouslySetInnerHTML={{
                        __html: formData.minuta_text,
                      }}
                    />
                  </div>
                ) : (
                  <div className="text-sm text-muted-foreground text-center py-8">
                    <p className="italic">Texto da minuta indisponível. O documento será gerado com o texto padrão após a assinatura.</p>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* ASSINATURA */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <PenLine className="h-5 w-5 text-primary" />
                  Assinatura
                </CardTitle>
                <p className="text-muted-foreground text-sm">
                  Assine abaixo para confirmar e aceitar os termos do documento.
                </p>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Mobile rotation hint */}
                <div className="bg-muted/50 border border-border rounded-md p-3 text-center">
                  <p className="text-xs text-muted-foreground">
                    📱 Está a assinar com o Smartphone? Vire o equipamento para
                    assinar em conformidade.
                  </p>
                </div>

                <SignaturePad
                  onSignatureChange={handleSignatureChange}
                  signature={form.assinatura}
                />

                {!form.assinatura && (
                  <p className="text-xs text-destructive text-center">
                    A assinatura é obrigatória para submeter o documento.
                  </p>
                )}
              </CardContent>
            </Card>

            {/* NAVIGATION BUTTONS */}
            <div className="flex flex-col-reverse sm:flex-row gap-3 sm:justify-between">
              <Button
                type="button"
                variant="outline"
                onClick={goToStep1}
                className="w-full sm:w-auto"
              >
                <ChevronLeft className="mr-1 h-4 w-4" />
                Voltar
              </Button>
              <Button
                type="submit"
                disabled={submitting}
                className="bg-primary hover:bg-primary/90 text-primary-foreground px-6 w-full sm:w-auto"
              >
                {submitting ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    A processar...
                  </>
                ) : (
                  'Aceitar e Assinar'
                )}
              </Button>
            </div>
          </form>
        )}

        {/* ============================================================ */}
        {/* FOOTER                                                       */}
        {/* ============================================================ */}
        <div className="text-center text-sm text-muted-foreground pb-4 pt-6 border-t border-border mt-8">
          <p>
            <strong className="text-foreground">Precisiontime, Lda</strong>
            <br />
            Rua de Santa Cruz do Castelo, n.º 22, 1.º Andar
            <br />
            1100-480, Lisboa
            <br />
            precisiontime.geral@gmail.com | (+351) 961405170
          </p>
        </div>
      </div>
    </div>
  );
}

