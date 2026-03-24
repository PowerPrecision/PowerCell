/**
 * RGPD Public Page
 * 
 * Página pública para assinatura do RGPD pelo cliente.
 * O cliente acede através de um link temporário enviado por email.
 */
import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Alert, AlertDescription } from '../components/ui/alert';
import { Loader2, CheckCircle, AlertTriangle, Clock, FileText } from 'lucide-react';

// ====================================================================
// CONCORRIOS DE PORTUGAL - Lista de concelhos
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
  "Vouzela"
];

// ====================================================================
// TIPOS DE DOCUMENTO
// ====================================================================
const TIPOS_DOCUMENTO = [
  { value: "bilhete_de_identidade", label: "Bilhete de Identidade" },
  { value: "cartao_de_cidadao", label: "Cartão de Cidadão" },
  { value: "passaporte", label: "Passaporte" },
  { value: "carta_de_conducao", label: "Carta de Condução" },
  { value: "autorizacao_de_residencia", label: "Autorização de Residência" }
];

// ====================================================================
// COMPONENTE DE ASSINATURA
// ====================================================================
const SignaturePad = ({ onSignatureChange }) => {
  const canvasRef = useRef(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [hasSignature, setHasSignature] = useState(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    ctx.strokeStyle = '#000';
    ctx.lineWidth = 2;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    // Limpar canvas
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
  }, []);

  const startDrawing = (e) => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const rect = canvas.getBoundingClientRect();
    
    setIsDrawing(true);
    setHasSignature(true);
    
    // Escalar coordenadas para o tamanho do buffer do canvas
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const x = ((e.clientX || e.touches?.[0]?.clientX) - rect.left) * scaleX;
    const y = ((e.clientY || e.touches?.[0]?.clientY) - rect.top) * scaleY;
    
    ctx.beginPath();
    ctx.moveTo(x, y);
  };

  const draw = (e) => {
    if (!isDrawing) return;
    
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const rect = canvas.getBoundingClientRect();
    
    // Escalar coordenadas para o tamanho do buffer do canvas
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const x = ((e.clientX || e.touches?.[0]?.clientX) - rect.left) * scaleX;
    const y = ((e.clientY || e.touches?.[0]?.clientY) - rect.top) * scaleY;
    
    ctx.lineTo(x, y);
    ctx.stroke();
  };

  const stopDrawing = () => {
    if (isDrawing) {
      setIsDrawing(false);
      const canvas = canvasRef.current;
      const signatureData = canvas.toDataURL('image/png');
      onSignatureChange(signatureData);
    }
  };

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
      <Label>Assinatura *</Label>
      <div className="border border-border rounded-lg overflow-hidden bg-white dark:bg-slate-100">
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
      <p className="text-xs text-muted-foreground">Desenhe a sua assinatura na área acima</p>
      {hasSignature && (
        <Button type="button" variant="outline" size="sm" onClick={clearSignature}>
          Limpar Assinatura
        </Button>
      )}
    </div>
  );
};

// ====================================================================
// PÁGINA PRINCIPAL
// ====================================================================
const RGPDPage = () => {
  const { token } = useParams();
  const navigate = useNavigate();
  
  // Estados
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);
  const [tokenData, setTokenData] = useState(null);
  const [formData, setFormData] = useState(null);
  
  // Dados do formulário
  const [form, setForm] = useState({
    nome: '',
    contribuinte: '',
    tipo_documento: '',
    numero_documento: '',
    validade_documento: '',
    morada: '',
    concelho: '',
    codigo_postal: '',
    assinatura: null
  });

  // Validar token ao carregar
  useEffect(() => {
    const validateToken = async () => {
      try {
        const response = await fetch(`/api/rgpd/validate/${token}`);
        
        if (!response.ok) {
          throw new Error('Token inválido ou expirado');
        }
        
        const data = await response.json();
        setTokenData(data);
        
        // Buscar dados pré-preenchidos
        const formDataResponse = await fetch(`/api/rgpd/data/${token}`);
        if (formDataResponse.ok) {
          const prefilledData = await formDataResponse.json();
          setFormData(prefilledData);
          setForm(prev => ({
            ...prev,
            nome: prefilledData.client_name || '',
            contribuinte: prefilledData.nif || '',
            morada: prefilledData.morada || '',
            numero_documento: prefilledData.documento_id || '',
            validade_documento: prefilledData.data_validade_cc || ''
          }));
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    if (token) {
      validateToken();
    }
  }, [token]);

  // Handlers
  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setForm(prev => ({ ...prev, [name]: value }));
  };

  const handleSelectChange = (name, value) => {
    setForm(prev => ({ ...prev, [name]: value }));
  };

  const handleSignatureChange = (signature) => {
    setForm(prev => ({ ...prev, assinatura: signature }));
  };

  // Formatar código postal
  const formatCodigoPostal = (value) => {
    const cleaned = value.replace(/\D/g, '');
    if (cleaned.length <= 4) return cleaned;
    return `${cleaned.slice(0, 4)}-${cleaned.slice(4, 7)}`;
  };

  // Formatar data
  const formatDate = (value) => {
    const cleaned = value.replace(/\D/g, '');
    if (cleaned.length <= 2) return cleaned;
    if (cleaned.length <= 4) return `${cleaned.slice(0, 2)}-${cleaned.slice(2)}`;
    return `${cleaned.slice(0, 2)}-${cleaned.slice(2, 4)}-${cleaned.slice(4, 8)}`;
  };

  // Submeter formulário
  const handleSubmit = async (e) => {
    e.preventDefault();
    
    // Validações
    if (!form.nome || !form.contribuinte || !form.tipo_documento || 
        !form.numero_documento || !form.morada || !form.assinatura) {
      toast.error('Por favor preencha todos os campos obrigatórios');
      return;
    }

    if (form.contribuinte.length !== 9) {
      toast.error('O contribuinte deve ter 9 dígitos');
      return;
    }

    setSubmitting(true);

    try {
      const response = await fetch(`/api/rgpd/sign/${token}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form)
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Erro ao assinar RGPD');
      }

      setSuccess(true);
      toast.success('RGPD assinado com sucesso!');
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  // Loading state
  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="max-w-lg w-full mx-auto space-y-4 p-6">
          <div className="h-8 w-48 bg-muted animate-pulse rounded mx-auto" />
          <div className="h-4 w-72 bg-muted animate-pulse rounded mx-auto" />
          <div className="h-40 bg-muted animate-pulse rounded-lg" />
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <Card className="max-w-md w-full">
          <CardContent className="pt-6">
            <div className="text-center">
              <AlertTriangle className="h-12 w-12 text-destructive mx-auto" />
              <h2 className="mt-4 text-xl font-semibold text-foreground">Link Inválido</h2>
              <p className="mt-2 text-muted-foreground">{error}</p>
              <p className="mt-4 text-sm text-muted-foreground">
                O link pode ter expirado (24h) ou já ter sido utilizado.
                Por favor contacte o seu intermediário de crédito.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Success state
  if (success) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <Card className="max-w-md w-full">
          <CardContent className="pt-6">
            <div className="text-center">
              <CheckCircle className="h-12 w-12 text-green-500 mx-auto" />
              <h2 className="mt-4 text-xl font-semibold text-foreground">RGPD Assinado!</h2>
              <p className="mt-2 text-muted-foreground">
                O seu documento RGPD foi assinado com sucesso.
                Uma cópia foi enviada para o seu intermediário de crédito.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Form
  return (
    <div className="min-h-screen bg-muted/30 py-8 px-4">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="bg-card rounded-lg shadow-sm p-5 mb-6 border border-border">
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
              <span className="text-sm text-muted-foreground">Português</span>
            </div>
          </div>
        </div>

        {/* Alerta de segurança */}
        <Alert className="mb-6 border-amber-300 bg-amber-50 dark:bg-amber-950/30 dark:border-amber-800">
          <Clock className="h-4 w-4 text-amber-600 dark:text-amber-400" />
          <AlertDescription className="text-amber-800 dark:text-amber-300">
            <strong>Atenção:</strong> Este link expira em 24 horas por motivos de segurança.
          </AlertDescription>
        </Alert>

        {/* Informação ao consumidor */}
        <Card className="mb-6">
          <CardHeader className="bg-primary/10 dark:bg-primary/5 border-b border-border rounded-t-lg">
            <CardTitle className="text-center text-base text-foreground">
              INFORMAÇÃO AO CONSUMIDOR NO ÂMBITO DA ATIVIDADE DE INTERMEDIÁRIO DE CRÉDITO
            </CardTitle>
            <p className="text-center text-sm text-muted-foreground">
              Art.º 54.º do Decreto-Lei n.º81-C/2017 de 7 de Julho – Regime Jurídico dos Intermediários de Crédito
            </p>
            <p className="text-center text-sm font-semibold text-foreground">
              Atividade sujeita à supervisão do Banco de Portugal
            </p>
          </CardHeader>
          <CardContent className="prose prose-sm max-w-none pt-4 text-foreground">
            <p className="text-sm text-muted-foreground">
              <strong className="text-foreground">Precisiontime, Lda</strong>, com sede na Rua de Santa Cruz do Castelo, n.º 22, 1.º Andar, 
              1100-480, Lisboa, <strong className="text-foreground">Intermediário de crédito, autorizado pelo Banco de Portugal na categoria 
              de intermediários de crédito Vinculado, com o número de registo 0008026</strong> (consulta pública 
              da lista de intermediários de crédito autorizados pelo Banco de Portugal em{' '}
              <a href="https://www.bportugal.pt/intermediariocreditofar/precisiontime-lda" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                www.bportugal.pt
              </a>)
            </p>
            <p className="text-sm text-muted-foreground">
              No âmbito da atividade que desenvolve, encontra-se habilitado para a intermediação de contratos 
              de Crédito Hipotecário e está autorizado a prestar os serviços de: apresentação ou proposta de 
              contratos de crédito a consumidores; assistência a consumidores, mediante a realização de atos 
              preparatórios ou de outros trabalhos de gestão pré-contratual relativamente a contratos de crédito 
              que não tenham sido por si apresentados ou propostos.
            </p>
            <p className="text-sm text-muted-foreground">
              <strong className="text-foreground">Mutuantes com quem o intermediário de crédito tem contrato de vinculação:</strong>{' '}
              NovoBanco S.A, Caixa Geral de Depósitos, Banco CTT, Banco Santander Totta SA, Eurobic/Abanca, Bankinter SA
            </p>
            <p className="text-sm text-muted-foreground">
              O intermediário de crédito está interdito de receber ou entregar quaisquer valores relacionados 
              com a formação, execução e o cumprimento antecipado dos contratos de crédito.
            </p>
          </CardContent>
        </Card>

        {/* Formulário RGPD */}
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-primary" />
              RGPD - Regulamento Geral sobre a Proteção de Dados
            </CardTitle>
            <p className="text-muted-foreground text-sm">Para darmos seguimento ao seu processo deverá preencher o RGPD.</p>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-6">
              {/* Dados pessoais */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="nome">Nome *</Label>
                  <Input
                    id="nome"
                    name="nome"
                    value={form.nome}
                    onChange={handleInputChange}
                    placeholder="Insira o seu nome completo"
                    required
                  />
                </div>
                <div>
                  <Label htmlFor="contribuinte">NIF (Contribuinte) *</Label>
                  <Input
                    id="contribuinte"
                    name="contribuinte"
                    value={form.contribuinte}
                    onChange={(e) => {
                      const value = e.target.value.replace(/\D/g, '').slice(0, 9);
                      setForm(prev => ({ ...prev, contribuinte: value }));
                    }}
                    placeholder="9 dígitos"
                    maxLength={9}
                    required
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="tipo_documento">Tipo de Documento *</Label>
                  <Select
                    value={form.tipo_documento}
                    onValueChange={(value) => handleSelectChange('tipo_documento', value)}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Selecione o tipo" />
                    </SelectTrigger>
                    <SelectContent>
                      {TIPOS_DOCUMENTO.map(doc => (
                        <SelectItem key={doc.value} value={doc.value}>
                          {doc.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label htmlFor="numero_documento">Número do Documento *</Label>
                  <Input
                    id="numero_documento"
                    name="numero_documento"
                    value={form.numero_documento}
                    onChange={handleInputChange}
                    placeholder="Número de identificação"
                    required
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="validade_documento">Validade do Documento</Label>
                  <Input
                    id="validade_documento"
                    name="validade_documento"
                    value={form.validade_documento}
                    onChange={(e) => {
                      const formatted = formatDate(e.target.value);
                      setForm(prev => ({ ...prev, validade_documento: formatted }));
                    }}
                    placeholder="DD-MM-AAAA"
                    maxLength={10}
                  />
                </div>
                <div>
                  <Label htmlFor="concelho">Concelho</Label>
                  <Select
                    value={form.concelho}
                    onValueChange={(value) => handleSelectChange('concelho', value)}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Selecione o concelho" />
                    </SelectTrigger>
                    <SelectContent>
                      {CONCELHOS.map(c => (
                        <SelectItem key={c} value={c}>{c}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="sm:col-span-2">
                  <Label htmlFor="morada">Morada *</Label>
                  <Input
                    id="morada"
                    name="morada"
                    value={form.morada}
                    onChange={handleInputChange}
                    placeholder="Rua, número, localidade"
                    required
                  />
                </div>
                <div>
                  <Label htmlFor="codigo_postal">Código Postal</Label>
                  <Input
                    id="codigo_postal"
                    name="codigo_postal"
                    value={form.codigo_postal}
                    onChange={(e) => {
                      const formatted = formatCodigoPostal(e.target.value);
                      setForm(prev => ({ ...prev, codigo_postal: formatted }));
                    }}
                    placeholder="XXXX-XXX"
                    maxLength={8}
                  />
                </div>
              </div>

              {/* Política de Privacidade */}
              <div className="bg-primary/5 dark:bg-primary/10 border border-primary/20 p-4 rounded-lg">
                <h3 className="font-semibold mb-2 text-foreground">POLÍTICA DE PRIVACIDADE</h3>
                <p className="text-xs text-muted-foreground mb-2">
                  (Ao abrigo do Regulamento Geral sobre a Proteção de Dados Pessoais)
                </p>
                <div className="text-xs text-muted-foreground space-y-2 max-h-36 overflow-y-auto pr-2">
                  <p>
                    No seguimento do contacto para a prestação de um serviço de intermediação de crédito, 
                    com a licença nº 0008026 da Precisiontime, Lda, no âmbito do qual terão que ser 
                    recolhidos e tratados dados pessoais dos quais é titular, informa-se:
                  </p>
                  <p>
                    <strong className="text-foreground">1. IDENTIFICAÇÃO DO RESPONSÁVEL PELO TRATAMENTO:</strong><br />
                    Precisiontime, Lda, Rua de Santa Cruz do Castelo, n.º 22, 1.º Andar, 1100-480, Lisboa<br />
                    E-mail: precisiontime.geral@gmail.com | Telefone: (+351) 961405170
                  </p>
                  <p>
                    <strong className="text-foreground">2. DADOS PESSOAIS RECOLHIDOS:</strong><br />
                    a) Dados de identificação (nome completo, data de nascimento, documento de identificação, NIF)<br />
                    b) Dados de contacto (telefone, morada)<br />
                    c) Dados bancários (IBAN, extratos, declarações)<br />
                    d) Dados fiscais (declarações IRS)<br />
                    e) Dados salariais (recibos de vencimento)<br />
                    f) Documentação relacionada com a habitação
                  </p>
                  <p>
                    <strong className="text-foreground">3. FINALIDADE DO TRATAMENTO:</strong><br />
                    Os dados pessoais são recolhidos para a prestação do serviço de intermediação de crédito, 
                    incluindo a transferência para Instituições de Crédito para análise da situação jurídica 
                    e financeira.
                  </p>
                </div>
              </div>

              {/* Assinatura */}
              <SignaturePad onSignatureChange={handleSignatureChange} />

              <p className="text-xs text-muted-foreground">* Campos obrigatórios</p>

              {/* Botões */}
              <div className="flex gap-4 justify-end">
                <Button type="submit" disabled={submitting} className="bg-primary hover:bg-primary/90 text-primary-foreground">
                  {submitting ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      A processar...
                    </>
                  ) : (
                    'Aceitar e Assinar RGPD'
                  )}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        {/* Footer */}
        <div className="text-center text-sm text-muted-foreground pb-4">
          <p>
            <strong className="text-foreground">Precisiontime, Lda</strong><br />
            Rua de Santa Cruz do Castelo, n.º 22, 1.º Andar<br />
            1100-480, Lisboa<br />
            precisiontime.geral@gmail.com | (+351) 961405170
          </p>
        </div>
      </div>
    </div>
  );
};

export default RGPDPage;
