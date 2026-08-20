/**
 * DSTICalculator — Calculadora automática de DSTI (Debt Service To Income) para processos de crédito habitação.
 *
 * PORQUÊ: O DSTI é a métrica regulatória fundamental usada pelo Banco de Portugal para avaliar a capacidade de
 * endividamento do cliente. Esta componente calcula automaticamente o rácio entre as prestações mensais totais
 * e o rendimento mensal, garantindo que o processo cumpre os limites legais (actualmente 60% do rendimento líquido).
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
import { Calculator, AlertTriangle, CheckCircle, Info, TrendingUp, TrendingDown, PiggyBank, Home, CreditCard, Wallet } from "lucide-react";

/**
 * Componente de medidor circular (Gauge)
 */
const CircularProgress = ({ value, max = 100, size = 120, strokeWidth = 10, color, label, showValue = true }) => {
  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const percentage = Math.min((value / max) * 100, 100);
  const offset = circumference - (percentage / 100) * circumference;
  
  // Cores baseadas no valor
  const getColor = () => {
    if (color) return color;
    if (percentage <= 30) return '#22c55e'; // green
    if (percentage <= 40) return '#eab308'; // yellow
    if (percentage <= 50) return '#f97316'; // orange
    return '#ef4444'; // red
  };
  
  return (
    <div className="relative inline-flex items-center justify-center">
      <svg width={size} height={size} className="transform -rotate-90">
        {/* Background circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke="#e5e7eb"
          strokeWidth={strokeWidth}
          fill="none"
        />
        {/* Progress circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={getColor()}
          strokeWidth={strokeWidth}
          fill="none"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className="transition-all duration-500 ease-out"
        />
      </svg>
      <div className="absolute flex flex-col items-center justify-center">
        {showValue && (
          <span className="text-2xl font-bold" style={{ color: getColor() }}>
            {value.toFixed(1)}%
          </span>
        )}
        {label && (
          <span className="text-xs text-gray-500 mt-1">{label}</span>
        )}
      </div>
    </div>
  );
};

/**
 * Barra de progresso com gradiente
 */
const GradientProgressBar = ({ value, max = 100, label, showLabel = true, height = "h-4" }) => {
  const percentage = Math.min((value / max) * 100, 100);
  
  const getGradient = () => {
    if (percentage <= 30) return 'from-green-400 to-green-600';
    if (percentage <= 40) return 'from-yellow-400 to-yellow-600';
    if (percentage <= 50) return 'from-orange-400 to-orange-600';
    return 'from-red-400 to-red-600';
  };
  
  return (
    <div className="w-full">
      {showLabel && (
        <div className="flex justify-between text-xs text-gray-500 mb-1">
          <span>{label}</span>
          <span className="font-medium">{percentage.toFixed(1)}%</span>
        </div>
      )}
      <div className={`w-full bg-gray-200 rounded-full ${height} overflow-hidden`}>
        <div
          className={`${height} rounded-full bg-gradient-to-r ${getGradient()} transition-all duration-500 ease-out`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
};

/**
 * Barra de comparação visual
 */
const ComparisonBar = ({ label, value, max, color = "bg-blue-500", icon }) => {
  const percentage = max > 0 ? (value / max) * 100 : 0;
  
  return (
    <div className="flex items-center gap-3">
      {icon && <div className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center">{icon}</div>}
      <div className="flex-1">
        <div className="flex justify-between text-sm mb-1">
          <span className="text-gray-600">{label}</span>
          <span className="font-semibold">{value.toLocaleString('pt-PT')}€</span>
        </div>
        <div className="w-full bg-gray-100 rounded-full h-2">
          <div className={`h-2 rounded-full ${color} transition-all duration-300`} style={{ width: `${Math.min(percentage, 100)}%` }} />
        </div>
      </div>
    </div>
  );
};

/**
 * Calculadora DSTI (Debt Service-to-Income Ratio)
 * Analisa a taxa de esforço do cliente para avaliar capacidade de crédito
 */
const DSTICalculator = ({ trigger, clientData, onCalculate, open: openProp, onOpenChange }) => {
  const [uncontrolledOpen, setUncontrolledOpen] = useState(false);
  const isControlled = openProp !== undefined;
  const open = isControlled ? openProp : uncontrolledOpen;
  const setOpen = (next) => {
    if (!isControlled) setUncontrolledOpen(next);
    onOpenChange?.(next);
  };

  // Campos do formulário
  const [rendimentoBruto, setRendimentoBruto] = useState("");
  const [rendimentoLiquido, setRendimentoLiquido] = useState("");
  const [rendimentoCoTitular, setRendimentoCoTitular] = useState("");
  const [prestacaoHipoteca, setPrestacaoHipoteca] = useState("");
  const [prestacaoNova, setPrestacaoNova] = useState("");
  const [outrosCreditos, setOutrosCreditos] = useState("");
  const [renda, setRenda] = useState("");
  const [outrasDespesas, setOutrasDespesas] = useState("");

  // Resultados
  const [resultado, setResultado] = useState(null);

  // Pré-preencher com dados do cliente quando disponível
  useEffect(() => {
    if (clientData) {
      if (clientData.rendimento_bruto) {
        setRendimentoBruto(clientData.rendimento_bruto.toString());
      }
      if (clientData.rendimento_mensal || clientData.salario_liquido) {
        setRendimentoLiquido((clientData.rendimento_mensal || clientData.salario_liquido).toString());
      }
      if (clientData.renda_habitacao_atual) {
        setRenda(clientData.renda_habitacao_atual.toString());
      }
      if (clientData.rendimento_co_titular) {
        setRendimentoCoTitular(clientData.rendimento_co_titular.toString());
      }
      if (clientData.prestacao_nova || clientData.monthly_payment) {
        setPrestacaoNova((clientData.prestacao_nova || clientData.monthly_payment).toString());
      }
    }
  }, [clientData, open]);

  // Calcular DSTI
  const calcular = () => {
    const rendBruto = parseFloat(rendimentoBruto) || 0;
    const rendCoTit = parseFloat(rendimentoCoTitular) || 0;
    const prestHipoteca = parseFloat(prestacaoHipoteca) || 0;
    const prestNova = parseFloat(prestacaoNova) || 0;
    const outros = parseFloat(outrosCreditos) || 0;
    const rendaVal = parseFloat(renda) || 0;
    const outras = parseFloat(outrasDespesas) || 0;

    // Rendimento bruto total
    const rendimentoTotal = rendBruto + rendCoTit;

    // Despesas mensais de crédito
    const despesasCredito = prestHipoteca + prestNova + outros;

    // DSTI = Despesas de crédito / Rendimento Bruto
    const dsti = rendimentoTotal > 0 ? (despesasCredito / rendimentoTotal) * 100 : 0;

    // Taxa de esforço com habitação (inclui renda)
    const despesasTotais = despesasCredito + rendaVal + outras;
    const taxaEsforco = rendimentoTotal > 0 ? (despesasTotais / rendimentoTotal) * 100 : 0;

    // Disponibilidade mensal
    const rendLiquido = parseFloat(rendimentoLiquido) || (rendBruto * 0.75);
    const disponibilidade = rendLiquido - despesasTotais;

    // Classificação de risco
    let classificacao = "";
    let cor = "";
    let icone = null;

    if (dsti <= 30) {
      classificacao = "Baixo Risco";
      cor = "bg-green-500 text-white";
      icone = <CheckCircle className="h-5 w-5" />;
    } else if (dsti <= 40) {
      classificacao = "Risco Moderado";
      cor = "bg-yellow-500 text-yellow-900";
      icone = <Info className="h-5 w-5" />;
    } else if (dsti <= 50) {
      classificacao = "Risco Elevado";
      cor = "bg-orange-500 text-white";
      icone = <AlertTriangle className="h-5 w-5" />;
    } else {
      classificacao = "Risco Muito Elevado";
      cor = "bg-red-500 text-white";
      icone = <AlertTriangle className="h-5 w-5" />;
    }

    // Limite do Banco de Portugal (50% para novos créditos)
    const dentroLimite = dsti <= 50;

    const resultados = {
      rendimentoTotal,
      despesasCredito,
      despesasTotais,
      dsti,
      taxaEsforco,
      disponibilidade,
      classificacao,
      cor,
      icone,
      dentroLimite,
      prestacaoMaxima: rendimentoTotal * 0.5 - prestHipoteca - outros,
      rendimentoBrutoTitular: rendBruto,
      rendimentoCoTitular: rendCoTit,
      prestacaoHipoteca: prestHipoteca,
      prestacaoNova: prestNova,
      outrosCreditos: outros,
      renda: rendaVal,
      outrasDespesas: outras,
    };

    setResultado(resultados);

    if (onCalculate) {
      onCalculate(resultados);
    }
  };

  // Limpar formulário
  const limpar = () => {
    setRendimentoBruto("");
    setRendimentoLiquido("");
    setRendimentoCoTitular("");
    setPrestacaoHipoteca("");
    setPrestacaoNova("");
    setOutrosCreditos("");
    setRenda("");
    setOutrasDespesas("");
    setResultado(null);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      {(trigger || !isControlled) && (
        <DialogTrigger asChild>
          {trigger || (
            <Button variant="outline" size="sm" className="gap-2">
              <Calculator className="h-4 w-4" />
              DSTI
            </Button>
          )}
        </DialogTrigger>
      )}
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Calculator className="h-5 w-5 text-blue-600" />
            Calculadora DSTI - Taxa de Esforço
          </DialogTitle>
          <DialogDescription>
            Analise a capacidade de crédito do cliente através da taxa DSTI (Debt Service-to-Income Ratio).
            O limite recomendado pelo Banco de Portugal é de 50% para novos créditos.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-4">
          {/* Coluna de Rendimentos */}
          <div className="space-y-4">
            <h3 className="font-semibold text-sm text-green-600 flex items-center gap-2">
              <TrendingUp className="h-4 w-4" />
              Rendimentos
            </h3>
            <div className="space-y-3">
              <div>
                <Label className="text-xs">Rendimento Bruto Titular (€)</Label>
                <Input
                  type="number"
                  value={rendimentoBruto}
                  onChange={(e) => setRendimentoBruto(e.target.value)}
                  placeholder="Ex: 2500"
                  className="h-9"
                />
              </div>
              <div>
                <Label className="text-xs">Rendimento Líquido Titular (€)</Label>
                <Input
                  type="number"
                  value={rendimentoLiquido}
                  onChange={(e) => setRendimentoLiquido(e.target.value)}
                  placeholder="Ex: 1900"
                  className="h-9"
                />
              </div>
              <div>
                <Label className="text-xs">Rendimento Co-Titular (€)</Label>
                <Input
                  type="number"
                  value={rendimentoCoTitular}
                  onChange={(e) => setRendimentoCoTitular(e.target.value)}
                  placeholder="Ex: 1500"
                  className="h-9"
                />
              </div>
            </div>
          </div>

          {/* Coluna de Despesas */}
          <div className="space-y-4">
            <h3 className="font-semibold text-sm text-red-600 flex items-center gap-2">
              <TrendingDown className="h-4 w-4" />
              Despesas Mensais
            </h3>
            <div className="space-y-3">
              <div>
                <Label className="text-xs">Prestação Hipoteca Atual (€)</Label>
                <Input
                  type="number"
                  value={prestacaoHipoteca}
                  onChange={(e) => setPrestacaoHipoteca(e.target.value)}
                  placeholder="Ex: 450"
                  className="h-9"
                />
              </div>
              <div>
                <Label className="text-xs">Nova Prestação Pretendida (€)</Label>
                <Input
                  type="number"
                  value={prestacaoNova}
                  onChange={(e) => setPrestacaoNova(e.target.value)}
                  placeholder="Ex: 800"
                  className="h-9"
                />
              </div>
              <div>
                <Label className="text-xs">Outros Créditos (€)</Label>
                <Input
                  type="number"
                  value={outrosCreditos}
                  onChange={(e) => setOutrosCreditos(e.target.value)}
                  placeholder="Ex: 200 (automóvel, pessoal)"
                  className="h-9"
                />
              </div>
              <div>
                <Label className="text-xs">Renda / Habitação (€)</Label>
                <Input
                  type="number"
                  value={renda}
                  onChange={(e) => setRenda(e.target.value)}
                  placeholder="Ex: 600"
                  className="h-9"
                />
              </div>
              <div>
                <Label className="text-xs">Outras Despesas Fixas (€)</Label>
                <Input
                  type="number"
                  value={outrasDespesas}
                  onChange={(e) => setOutrasDespesas(e.target.value)}
                  placeholder="Ex: pensão de alimentos"
                  className="h-9"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Botões */}
        <div className="flex gap-3 mt-6">
          <Button onClick={calcular} className="flex-1 bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700">
            <Calculator className="h-4 w-4 mr-2" />
            Calcular DSTI
          </Button>
          <Button variant="outline" onClick={limpar}>
            Limpar
          </Button>
        </div>

        {/* Resultados */}
        {resultado && (
          <Card className="mt-6 border-2 border-blue-200 bg-gradient-to-br from-white to-blue-50">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between mb-6">
                <h3 className="font-semibold text-lg">Resultados da Análise</h3>
                <Badge className={resultado.cor}>
                  {resultado.icone}
                  <span className="ml-1">{resultado.classificacao}</span>
                </Badge>
              </div>

              {/* Gauge Principal - DSTI */}
              <div className="flex flex-col md:flex-row items-center justify-center gap-8 mb-8">
                <div className="text-center">
                  <CircularProgress 
                    value={resultado.dsti} 
                    max={100} 
                    size={140} 
                    strokeWidth={12}
                    label="DSTI"
                  />
                  <p className="text-sm text-gray-500 mt-2">Taxa de Esforço de Crédito</p>
                </div>
                
                <div className="text-center">
                  <CircularProgress 
                    value={resultado.taxaEsforco} 
                    max={100} 
                    size={140} 
                    strokeWidth={12}
                    label="Esforço Total"
                  />
                  <p className="text-sm text-gray-500 mt-2">Taxa de Esforço Global</p>
                </div>
              </div>

              {/* Escala visual de DSTI */}
              <div className="mb-8">
                <div className="flex justify-between text-xs text-gray-500 mb-2">
                  <span>0%</span>
                  <span>30%</span>
                  <span>40%</span>
                  <span>50%</span>
                  <span>100%</span>
                </div>
                <div className="h-6 rounded-full overflow-hidden flex">
                  <div className="w-[30%] bg-gradient-to-r from-green-300 to-green-500 relative">
                    <span className="absolute inset-0 flex items-center justify-center text-xs font-medium text-white">Baixo</span>
                  </div>
                  <div className="w-[10%] bg-gradient-to-r from-yellow-300 to-yellow-500 relative">
                    <span className="absolute inset-0 flex items-center justify-center text-xs font-medium text-yellow-900">Mod.</span>
                  </div>
                  <div className="w-[10%] bg-gradient-to-r from-orange-300 to-orange-500 relative">
                    <span className="absolute inset-0 flex items-center justify-center text-xs font-medium text-white">Elev.</span>
                  </div>
                  <div className="w-[50%] bg-gradient-to-r from-red-300 to-red-500 relative">
                    <span className="absolute inset-0 flex items-center justify-center text-xs font-medium text-white">Muito Elevado</span>
                  </div>
                </div>
                {/* Marcador da posição atual */}
                <div 
                  className="relative h-0 -mt-1"
                  style={{ marginLeft: `${Math.min(resultado.dsti, 100)}%` }}
                >
                  <div className="absolute -translate-x-1/2 w-0 h-0 border-l-4 border-r-4 border-t-8 border-l-transparent border-r-transparent border-t-gray-800" />
                </div>
              </div>

              {/* Barras de progresso */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
                <div className="space-y-4">
                  <h4 className="font-medium text-sm flex items-center gap-2">
                    <Wallet className="h-4 w-4 text-green-500" />
                    Disponibilidade Mensal
                  </h4>
                  <div className={`text-3xl font-bold ${resultado.disponibilidade >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {resultado.disponibilidade.toFixed(0)}€
                  </div>
                  <GradientProgressBar 
                    value={Math.max(0, resultado.disponibilidade)} 
                    max={resultado.rendimentoTotal} 
                    label="Saldo após despesas"
                  />
                </div>
                
                <div className="space-y-4">
                  <h4 className="font-medium text-sm flex items-center gap-2">
                    <CreditCard className="h-4 w-4 text-amber-500" />
                    Prestação Máxima Possível
                  </h4>
                  <div className="text-3xl font-bold text-amber-600">
                    {resultado.prestacaoMaxima.toFixed(0)}€
                  </div>
                  <GradientProgressBar 
                    value={resultado.prestacaoMaxima} 
                    max={resultado.rendimentoTotal * 0.5} 
                    label="Limite 50% do rendimento"
                  />
                </div>
              </div>

              {/* Comparação visual de rendimentos vs despesas */}
              <div className="bg-white rounded-xl p-4 mb-6 border">
                <h4 className="font-medium text-sm mb-4 flex items-center gap-2">
                  <PiggyBank className="h-4 w-4 text-blue-500" />
                  Distribuição Financeira
                </h4>
                <div className="space-y-4">
                  <ComparisonBar 
                    label="Rendimento Bruto Total" 
                    value={resultado.rendimentoTotal} 
                    max={resultado.rendimentoTotal}
                    color="bg-green-400"
                    icon={<TrendingUp className="h-4 w-4 text-green-500" />}
                  />
                  <ComparisonBar 
                    label="Créditos" 
                    value={resultado.despesasCredito} 
                    max={resultado.rendimentoTotal}
                    color="bg-red-400"
                    icon={<CreditCard className="h-4 w-4 text-red-500" />}
                  />
                  <ComparisonBar 
                    label="Renda/Habitação" 
                    value={resultado.renda} 
                    max={resultado.rendimentoTotal}
                    color="bg-orange-400"
                    icon={<Home className="h-4 w-4 text-orange-500" />}
                  />
                  <ComparisonBar 
                    label="Outras Despesas" 
                    value={resultado.outrasDespesas} 
                    max={resultado.rendimentoTotal}
                    color="bg-yellow-400"
                    icon={<Wallet className="h-4 w-4 text-yellow-500" />}
                  />
                </div>
              </div>

              {/* Legenda */}
              <div className="p-4 bg-blue-50 rounded-xl border border-blue-200">
                <p className="text-sm text-blue-800">
                  <strong>Legenda:</strong><br />
                  • <strong>DSTI até 30%:</strong> Baixo risco - boa capacidade de pagamento<br />
                  • <strong>DSTI 30-40%:</strong> Risco moderado - cuidado com novos créditos<br />
                  • <strong>DSTI 40-50%:</strong> Risco elevado - limite próximo do máximo<br />
                  • <strong>DSTI acima 50%:</strong> Ultrapassa o limite do Banco de Portugal
                </p>
              </div>

              {!resultado.dentroLimite && (
                <div className="mt-4 p-4 bg-red-50 rounded-xl border border-red-200 flex items-start gap-3">
                  <AlertTriangle className="h-5 w-5 text-red-600 flex-shrink-0 mt-0.5" />
                  <p className="text-sm text-red-800">
                    <strong>Atenção:</strong> O DSTI ultrapassa os 50% limite do Banco de Portugal.
                    O cliente pode ter dificuldades em obter novo crédito.
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default DSTICalculator;

