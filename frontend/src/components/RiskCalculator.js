/**
 * RiskCalculator — Calculadora de risco de crédito para avaliação de processos.
 *
 * PORQUÊ: Permite ao consultor/mediador avaliar o risco de crédito de forma estruturada,
 * considerando factores como LTV, DSTI, rendimento, e histórico. O resultado ajuda
 * na decisão de recomendar ou não a aprovação do crédito.
 *
 * @context {AuthContext} — Consome user, token para autenticação e permissões
 */

import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "../components/ui/dialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Card, CardContent } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import {
  TrendingUp,
  AlertTriangle,
  CheckCircle,
  Info,
  Percent,
  Building2,
  Calculator,
  PiggyBank,
  Clock,
  User,
  Banknote,
  ArrowUpRight,
  ArrowDownRight,
} from "lucide-react";
import { safeDateStr } from "../lib/utils";

/**
 * Componente de medidor circular (Gauge) - versão avançada
 */
const RadialGauge = ({ value, max = 100, size = 130, strokeWidth = 12, label, thresholds = [30, 50, 70], unit = "%" }) => {
  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const percentage = Math.min((value / max) * 100, 100);
  const offset = circumference - (percentage / 100) * circumference;
  
  const getColor = () => {
    if (percentage <= thresholds[0]) return '#22c55e';
    if (percentage <= thresholds[1]) return '#eab308';
    if (percentage <= thresholds[2]) return '#f97316';
    return '#ef4444';
  };
  
  const getRiskLabel = () => {
    if (percentage <= thresholds[0]) return { text: 'Baixo', color: 'text-green-600' };
    if (percentage <= thresholds[1]) return { text: 'Moderado', color: 'text-yellow-600' };
    if (percentage <= thresholds[2]) return { text: 'Elevado', color: 'text-orange-600' };
    return { text: 'Crítico', color: 'text-red-600' };
  };
  
  const riskLabel = getRiskLabel();
  
  return (
    <div className="flex flex-col items-center">
      <div className="relative inline-flex items-center justify-center">
        <svg width={size} height={size} className="transform -rotate-90">
          <defs>
            <linearGradient id={`gradient-${label}`} x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor={getColor()} stopOpacity="0.8" />
              <stop offset="100%" stopColor={getColor()} stopOpacity="1" />
            </linearGradient>
          </defs>
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            stroke="#f3f4f6"
            strokeWidth={strokeWidth}
            fill="none"
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            stroke={`url(#gradient-${label})`}
            strokeWidth={strokeWidth}
            fill="none"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            className="transition-all duration-700 ease-out"
          />
        </svg>
        <div className="absolute flex flex-col items-center justify-center">
          <span className="text-2xl font-bold" style={{ color: getColor() }}>
            {value.toFixed(1)}{unit}
          </span>
          <span className={`text-xs font-medium ${riskLabel.color}`}>{riskLabel.text}</span>
        </div>
      </div>
      <span className="text-xs text-gray-500 mt-2 font-medium">{label}</span>
    </div>
  );
};

/**
 * Mini gráfico de barras
 */
const MiniBarChart = ({ data }) => {
  const maxValue = Math.max(...data.map(d => d.value));
  
  return (
    <div className="space-y-2">
      {data.map((item, index) => (
        <div key={index} className="flex items-center gap-3">
          <div className="w-20 text-xs text-gray-500">{item.label}</div>
          <div className="flex-1 h-5 bg-gray-100 rounded-full overflow-hidden relative">
            <div
              className={`h-full rounded-full transition-all duration-500 ${item.color}`}
              style={{ width: `${(item.value / maxValue) * 100}%` }}
            />
            <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs font-medium">
              {typeof item.value === 'number' && item.value >= 1000 
                ? `${(item.value / 1000).toFixed(0)}k€`
                : `${item.value.toFixed(0)}${item.unit || '€'}`
              }
            </span>
          </div>
        </div>
      ))}
    </div>
  );
};

/**
 * Card de métrica
 */
const MetricCard = ({ label, value, icon, color, trend, subtitle }) => {
  const colorClasses = {
    blue: 'bg-blue-50 border-blue-200 text-blue-600',
    green: 'bg-green-50 border-green-200 text-green-600',
    red: 'bg-red-50 border-red-200 text-red-600',
    orange: 'bg-orange-50 border-orange-200 text-orange-600',
    purple: 'bg-purple-50 border-purple-200 text-purple-600',
  };
  
  return (
    <div className={`${colorClasses[color]} border rounded-xl p-4`}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-gray-500 font-medium">{label}</p>
          <p className="text-2xl font-bold mt-1">{value}</p>
          {subtitle && <p className="text-xs mt-1">{subtitle}</p>}
        </div>
        {icon && (
          <div className={`p-2 rounded-lg bg-white/50`}>
            {icon}
          </div>
        )}
      </div>
      {trend !== undefined && (
        <div className={`flex items-center gap-1 mt-2 text-xs ${trend >= 0 ? 'text-green-500' : 'text-red-500'}`}>
          {trend >= 0 ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
          <span>{Math.abs(trend).toFixed(1)}%</span>
        </div>
      )}
    </div>
  );
};

/**
 * Calculadora de Risco de Crédito
 * Simula custos e valor mensal do crédito habitacional
 */
const RiskCalculator = ({ trigger, clientData, onCalculate }) => {
  const [open, setOpen] = useState(false);

  // Campos do formulário
  const [valorImovel, setValorImovel] = useState("");
  const [valorEntrada, setValorEntrada] = useState("");
  const [prazoAnos, setPrazoAnos] = useState("30");
  const [taxaAnual, setTaxaAnual] = useState("3.5");
  const [tipoTaxa, setTipoTaxa] = useState("fixa");
  const [rendimentoMensal, setRendimentoMensal] = useState("");
  const [idadeProponente, setIdadeProponente] = useState("");

  // Resultados
  const [resultado, setResultado] = useState(null);

  // Pré-preencher com dados do cliente
  useEffect(() => {
    if (clientData && open) {
      if (clientData.valor_imovel) {
        setValorImovel(clientData.valor_imovel.toString());
      }
      if (clientData.valor_entrada || clientData.capital_proprio) {
        setValorEntrada((clientData.valor_entrada || clientData.capital_proprio).toString());
      }
      if (clientData.rendimento_mensal || clientData.salario_liquido) {
        setRendimentoMensal((clientData.rendimento_mensal || clientData.salario_liquido).toString());
      }
      if (clientData.idade || clientData.data_nascimento) {
        if (clientData.idade) {
          setIdadeProponente(clientData.idade.toString());
        } else if (clientData.data_nascimento) {
          const birthDate = new Date(safeDateStr(clientData.data_nascimento));
          const age = new Date().getFullYear() - birthDate.getFullYear();
          setIdadeProponente(age.toString());
        }
      }
    }
  }, [clientData, open]);

  // Calcular financiamento
  const calcular = () => {
    const vImovel = parseFloat(valorImovel) || 0;
    const vEntrada = parseFloat(valorEntrada) || 0;
    const prazo = parseInt(prazoAnos) || 30;
    const taxa = parseFloat(taxaAnual) / 100 || 0.035;
    const rendimento = parseFloat(rendimentoMensal) || 0;
    const idade = parseInt(idadeProponente) || 30;

    // Cálculos básicos
    const valorFinanciar = vImovel - vEntrada;
    const ltv = vImovel > 0 ? (valorFinanciar / vImovel) * 100 : 0;

    // Prestação mensal (fórmula de amortização)
    const taxaMensal = taxa / 12;
    const numPrestacoes = prazo * 12;
    let prestacaoMensal = 0;

    if (taxaMensal > 0 && valorFinanciar > 0) {
      prestacaoMensal =
        (valorFinanciar * taxaMensal * Math.pow(1 + taxaMensal, numPrestacoes)) /
        (Math.pow(1 + taxaMensal, numPrestacoes) - 1);
    }

    // MTIC e juros
    const mtic = prestacaoMensal * numPrestacoes;
    const jurosTotal = mtic - valorFinanciar;

    // TAEG estimada
    const taegEstimada = taxa * 1.15;

    // DSTI
    const dsti = rendimento > 0 ? (prestacaoMensal / rendimento) * 100 : 0;

    // Análise de risco
    let riscoLTV = "", riscoDSTI = "", riscoIdade = "";
    let scoreLTV = 0, scoreDSTI = 0, scoreIdade = 0;

    // Risco LTV
    if (ltv <= 80) {
      riscoLTV = "Baixo"; scoreLTV = 100;
    } else if (ltv <= 90) {
      riscoLTV = "Moderado"; scoreLTV = 60;
    } else if (ltv <= 100) {
      riscoLTV = "Elevado"; scoreLTV = 30;
    } else {
      riscoLTV = "Crítico"; scoreLTV = 0;
    }

    // Risco DSTI
    if (dsti <= 30) {
      riscoDSTI = "Baixo"; scoreDSTI = 100;
    } else if (dsti <= 40) {
      riscoDSTI = "Moderado"; scoreDSTI = 70;
    } else if (dsti <= 50) {
      riscoDSTI = "Elevado"; scoreDSTI = 40;
    } else {
      riscoDSTI = "Crítico"; scoreDSTI = 0;
    }

    // Risco Idade
    const idadeFinal = idade + prazo;
    if (idadeFinal <= 70) {
      riscoIdade = "Baixo"; scoreIdade = 100;
    } else if (idadeFinal <= 75) {
      riscoIdade = "Moderado"; scoreIdade = 60;
    } else {
      riscoIdade = "Elevado"; scoreIdade = 20;
    }

    // Score geral (0-100)
    const scoreGeral = (scoreLTV + scoreDSTI + scoreIdade) / 3;

    // Classificação geral
    let classificacaoGeral = "", corClassificacao = "";
    if (scoreGeral >= 80) {
      classificacaoGeral = "Perfil Excelente";
      corClassificacao = "bg-green-500 text-white";
    } else if (scoreGeral >= 60) {
      classificacaoGeral = "Perfil Aprovado";
      corClassificacao = "bg-green-500 text-white";
    } else if (scoreGeral >= 40) {
      classificacaoGeral = "Perfil Aceitável";
      corClassificacao = "bg-yellow-500 text-yellow-900";
    } else if (scoreGeral >= 20) {
      classificacaoGeral = "Perfil de Risco";
      corClassificacao = "bg-orange-500 text-white";
    } else {
      classificacaoGeral = "Perfil Crítico";
      corClassificacao = "bg-red-500 text-white";
    }

    // Prazo máximo
    const prazoMaxIdade = Math.max(5, 70 - idade);
    const prazoRecomendado = Math.min(prazo, prazoMaxIdade);

    const resultados = {
      valorImovel: vImovel,
      valorEntrada: vEntrada,
      valorFinanciar,
      prestacaoMensal,
      ltv,
      mtic,
      jurosTotal,
      taegEstimada,
      dsti,
      prazo,
      prazoAnos: prazo,
      riscoLTV,
      riscoDSTI,
      riscoIdade,
      scoreLTV,
      scoreDSTI,
      scoreIdade,
      scoreGeral,
      classificacaoGeral,
      corClassificacao,
      prazoMaxIdade,
      prazoRecomendado,
      idadeFinal,
      dentroLimites: ltv <= 90 && dsti <= 50 && idadeFinal <= 75,
    };

    setResultado(resultados);

    if (onCalculate) {
      onCalculate(resultados);
    }
  };

  const limpar = () => {
    setValorImovel("");
    setValorEntrada("");
    setPrazoAnos("30");
    setTaxaAnual("3.5");
    setTipoTaxa("fixa");
    setRendimentoMensal("");
    setIdadeProponente("");
    setResultado(null);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger || (
          <Button variant="outline" size="sm" className="gap-2">
            <TrendingUp className="h-4 w-4" />
            Risco
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5 text-purple-600" />
            Calculadora de Risco de Crédito
          </DialogTitle>
          <DialogDescription>
            Simule os custos e valor mensal do crédito habitacional. Analise o perfil de risco do cliente.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-4">
          {/* Dados do Imóvel */}
          <div className="space-y-4">
            <h3 className="font-semibold text-sm text-blue-600 flex items-center gap-2">
              <Building2 className="h-4 w-4" />
              Dados do Imóvel
            </h3>
            <div className="space-y-3">
              <div>
                <Label className="text-xs">Valor do Imóvel (€)</Label>
                <Input
                  type="number"
                  value={valorImovel}
                  onChange={(e) => setValorImovel(e.target.value)}
                  placeholder="Ex: 250000"
                  className="h-9"
                />
              </div>
              <div>
                <Label className="text-xs">Valor de Entrada (€)</Label>
                <Input
                  type="number"
                  value={valorEntrada}
                  onChange={(e) => setValorEntrada(e.target.value)}
                  placeholder="Ex: 50000"
                  className="h-9"
                />
              </div>
            </div>
          </div>

          {/* Condições do Crédito */}
          <div className="space-y-4">
            <h3 className="font-semibold text-sm text-purple-600 flex items-center gap-2">
              <Percent className="h-4 w-4" />
              Condições do Crédito
            </h3>
            <div className="space-y-3">
              <div>
                <Label className="text-xs">Prazo (anos)</Label>
                <Select value={prazoAnos} onValueChange={setPrazoAnos}>
                  <SelectTrigger className="h-9">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {[5, 10, 15, 20, 25, 30, 35, 40].map((ano) => (
                      <SelectItem key={ano} value={ano.toString()}>
                        {ano} anos
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Taxa Anual (%)</Label>
                <Input
                  type="number"
                  step="0.1"
                  value={taxaAnual}
                  onChange={(e) => setTaxaAnual(e.target.value)}
                  placeholder="Ex: 3.5"
                  className="h-9"
                />
              </div>
              <div>
                <Label className="text-xs">Tipo de Taxa</Label>
                <Select value={tipoTaxa} onValueChange={setTipoTaxa}>
                  <SelectTrigger className="h-9">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="fixa">Taxa Fixa</SelectItem>
                    <SelectItem value="variavel">Taxa Variável</SelectItem>
                    <SelectItem value="mista">Taxa Mista</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>

          {/* Dados do Cliente */}
          <div className="space-y-4 md:col-span-2">
            <h3 className="font-semibold text-sm text-green-600 flex items-center gap-2">
              <User className="h-4 w-4" />
              Dados do Cliente
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label className="text-xs">Rendimento Mensal Líquido (€)</Label>
                <Input
                  type="number"
                  value={rendimentoMensal}
                  onChange={(e) => setRendimentoMensal(e.target.value)}
                  placeholder="Ex: 2000"
                  className="h-9"
                />
              </div>
              <div>
                <Label className="text-xs">Idade do Proponente</Label>
                <Input
                  type="number"
                  value={idadeProponente}
                  onChange={(e) => setIdadeProponente(e.target.value)}
                  placeholder="Ex: 35"
                  className="h-9"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Botões */}
        <div className="flex gap-3 mt-6">
          <Button onClick={calcular} className="flex-1 bg-gradient-to-r from-purple-500 to-purple-600 hover:from-purple-600 hover:to-purple-700">
            <Calculator className="h-4 w-4 mr-2" />
            Calcular Risco
          </Button>
          <Button variant="outline" onClick={limpar}>
            Limpar
          </Button>
        </div>

        {/* Resultados */}
        {resultado && (
          <Card className="mt-6 border-2 border-purple-200 bg-gradient-to-br from-white to-purple-50">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between mb-6">
                <h3 className="font-semibold text-lg">Resultados da Simulação</h3>
                <Badge className={resultado.corClassificacao}>
                  {resultado.classificacaoGeral}
                </Badge>
              </div>

              {/* Gauges de Risco */}
              <div className="flex flex-wrap justify-center gap-6 mb-8">
                <RadialGauge 
                  value={resultado.ltv} 
                  max={100} 
                  label="LTV" 
                  thresholds={[80, 90, 100]}
                />
                <RadialGauge 
                  value={resultado.dsti} 
                  max={100} 
                  label="DSTI" 
                  thresholds={[30, 40, 50]}
                />
                <RadialGauge 
                  value={resultado.scoreGeral} 
                  max={100} 
                  label="Score Geral" 
                  thresholds={[40, 60, 80]}
                  unit=""
                />
              </div>

              {/* Métricas principais */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
                <MetricCard
                  label="Valor a Financiar"
                  value={`${resultado.valorFinanciar.toLocaleString('pt-PT')}€`}
                  icon={<Banknote className="h-4 w-4" />}
                  color="blue"
                />
                <MetricCard
                  label="Prestação Mensal"
                  value={`${resultado.prestacaoMensal.toFixed(0)}€`}
                  icon={<PiggyBank className="h-4 w-4" />}
                  color="green"
                />
                <MetricCard
                  label="Total Juros"
                  value={`${resultado.jurosTotal.toLocaleString('pt-PT', { maximumFractionDigits: 0 })}€`}
                  icon={<TrendingUp className="h-4 w-4" />}
                  color="red"
                  subtitle={`${resultado.mtic.toLocaleString('pt-PT', { maximumFractionDigits: 0 })}€ MTIC`}
                />
                <MetricCard
                  label="TAEG Estimada"
                  value={`${(resultado.taegEstimada * 100).toFixed(2)}%`}
                  icon={<Percent className="h-4 w-4" />}
                  color="purple"
                />
              </div>

              {/* Gráfico de barras - composição do valor total */}
              <div className="bg-white rounded-xl p-4 mb-6 border">
                <h4 className="font-medium text-sm mb-4 flex items-center gap-2">
                  <PiggyBank className="h-4 w-4 text-purple-500" />
                  Composição do Custo Total
                </h4>
                <MiniBarChart data={[
                  { label: 'Capital', value: resultado.valorFinanciar, color: 'bg-blue-400' },
                  { label: 'Juros', value: resultado.jurosTotal, color: 'bg-red-400' },
                  { label: 'MTIC', value: resultado.mtic, color: 'bg-purple-400' },
                ]} />
              </div>

              {/* Análise de risco por fator */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                {/* Risco LTV */}
                <div className={`p-4 rounded-xl border-2 ${
                  resultado.riscoLTV === 'Baixo' ? 'bg-green-50 border-green-300' :
                  resultado.riscoLTV === 'Moderado' ? 'bg-yellow-50 border-yellow-300' :
                  resultado.riscoLTV === 'Elevado' ? 'bg-orange-50 border-orange-300' :
                  'bg-red-50 border-red-300'
                }`}>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-gray-500">Risco LTV</span>
                    <span className="font-semibold">{resultado.riscoLTV}</span>
                  </div>
                  <div className="text-lg font-bold">{resultado.ltv.toFixed(1)}%</div>
                  <div className="mt-2 h-2 bg-gray-200 rounded-full overflow-hidden">
                    <div 
                      className={`h-full rounded-full ${
                        resultado.ltv <= 80 ? 'bg-green-500' :
                        resultado.ltv <= 90 ? 'bg-yellow-500' :
                        'bg-red-500'
                      }`}
                      style={{ width: `${Math.min(resultado.ltv, 100)}%` }}
                    />
                  </div>
                  <p className="text-xs text-gray-500 mt-2">
                    {resultado.ltv <= 80 ? '✓ Dentro do recomendado (≤80%)' :
                     resultado.ltv <= 90 ? '⚠ Limite aceitável (≤90%)' :
                     '✗ Ultrapassa limites'}
                  </p>
                </div>

                {/* Risco DSTI */}
                <div className={`p-4 rounded-xl border-2 ${
                  resultado.riscoDSTI === 'Baixo' ? 'bg-green-50 border-green-300' :
                  resultado.riscoDSTI === 'Moderado' ? 'bg-yellow-50 border-yellow-300' :
                  resultado.riscoDSTI === 'Elevado' ? 'bg-orange-50 border-orange-300' :
                  'bg-red-50 border-red-300'
                }`}>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-gray-500">Risco DSTI</span>
                    <span className="font-semibold">{resultado.riscoDSTI}</span>
                  </div>
                  <div className="text-lg font-bold">{resultado.dsti.toFixed(1)}%</div>
                  <div className="mt-2 h-2 bg-gray-200 rounded-full overflow-hidden">
                    <div 
                      className={`h-full rounded-full ${
                        resultado.dsti <= 30 ? 'bg-green-500' :
                        resultado.dsti <= 40 ? 'bg-yellow-500' :
                        resultado.dsti <= 50 ? 'bg-orange-500' :
                        'bg-red-500'
                      }`}
                      style={{ width: `${Math.min(resultado.dsti, 100)}%` }}
                    />
                  </div>
                  <p className="text-xs text-gray-500 mt-2">
                    {resultado.dsti <= 30 ? '✓ Excelente capacidade' :
                     resultado.dsti <= 40 ? '⚠ Risco moderado' :
                     resultado.dsti <= 50 ? '⚠ Limite do BdP' :
                     '✗ Ultrapassa 50%'}
                  </p>
                </div>

                {/* Risco Idade */}
                <div className={`p-4 rounded-xl border-2 ${
                  resultado.riscoIdade === 'Baixo' ? 'bg-green-50 border-green-300' :
                  resultado.riscoIdade === 'Moderado' ? 'bg-yellow-50 border-yellow-300' :
                  'bg-orange-50 border-orange-300'
                }`}>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-gray-500">Risco Idade</span>
                    <span className="font-semibold">{resultado.riscoIdade}</span>
                  </div>
                  <div className="text-lg font-bold">{resultado.idadeFinal} anos</div>
                  <div className="mt-2 flex items-center gap-1 text-xs">
                    <Clock className="h-3 w-3" />
                    <span>Idade final do contrato</span>
                  </div>
                  <p className="text-xs text-gray-500 mt-2">
                    {resultado.idadeFinal <= 70 ? '✓ Dentro do limite' :
                     resultado.idadeFinal <= 75 ? '⚠ Limite aceitável' :
                     '✗ Pode comprometer aprovação'}
                  </p>
                </div>
              </div>

              {/* Avisos */}
              {!resultado.dentroLimites && (
                <div className="p-4 bg-amber-50 rounded-xl border border-amber-200 flex items-start gap-3">
                  <AlertTriangle className="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" />
                  <div className="text-sm text-amber-800">
                    <strong>Atenção:</strong> Alguns parâmetros estão fora dos limites recomendados.
                    <ul className="list-disc list-inside mt-1">
                      {resultado.ltv > 90 && <li>LTV superior a 90%</li>}
                      {resultado.dsti > 50 && <li>DSTI superior a 50%</li>}
                      {resultado.idadeFinal > 75 && <li>Idade final superior a 75 anos</li>}
                    </ul>
                  </div>
                </div>
              )}

              {/* Info adicional */}
              <div className="mt-4 p-4 bg-gray-50 rounded-xl flex items-start gap-3">
                <Info className="h-5 w-5 text-gray-400 flex-shrink-0 mt-0.5" />
                <div className="text-sm text-gray-600">
                  <strong>Prazo máximo recomendado:</strong> {resultado.prazoMaxIdade} anos
                  <span className="text-gray-400 ml-2">(baseado na idade final do contrato não exceder 70-75 anos)</span>
                </div>
              </div>
            </CardContent>
          </Card>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default RiskCalculator;

