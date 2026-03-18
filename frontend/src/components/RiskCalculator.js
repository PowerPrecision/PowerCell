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
} from "lucide-react";

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

  // Pré-preencher com dados do cliente quando disponível
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
          const birthDate = new Date(clientData.data_nascimento);
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

    // Cálculos
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

    // MTIC (Montante Total Imputado ao Consumidor)
    const mtic = prestacaoMensal * numPrestacoes;
    const jurosTotal = mtic - valorFinanciar;

    // TAEG estimada (simplificada)
    const taegEstimada = taxa * 1.15; // Adiciona custos estimados

    // DSTI
    const dsti = rendimento > 0 ? (prestacaoMensal / rendimento) * 100 : 0;

    // Análise de risco
    let riscoLTV = "";
    let riscoDSTI = "";
    let riscoIdade = "";
    let classificacaoGeral = "";
    let corClassificacao = "";

    // Risco LTV
    if (ltv <= 80) {
      riscoLTV = "Baixo";
    } else if (ltv <= 90) {
      riscoLTV = "Moderado";
    } else if (ltv <= 100) {
      riscoLTV = "Elevado";
    } else {
      riscoLTV = "Muito Elevado";
    }

    // Risco DSTI
    if (dsti <= 30) {
      riscoDSTI = "Baixo";
    } else if (dsti <= 40) {
      riscoDSTI = "Moderado";
    } else if (dsti <= 50) {
      riscoDSTI = "Elevado";
    } else {
      riscoDSTI = "Muito Elevado";
    }

    // Risco Idade (limitação de prazo)
    const idadeFinal = idade + prazo;
    if (idadeFinal <= 70) {
      riscoIdade = "Baixo";
    } else if (idadeFinal <= 75) {
      riscoIdade = "Moderado";
    } else {
      riscoIdade = "Elevado";
    }

    // Classificação geral
    const riscos = [riscoLTV, riscoDSTI, riscoIdade];
    const riscosAltos = riscos.filter((r) => r === "Elevado" || r === "Muito Elevado").length;

    if (riscosAltos === 0) {
      classificacaoGeral = "Perfil Aprovado";
      corClassificacao = "bg-green-500 text-white";
    } else if (riscosAltos === 1) {
      classificacaoGeral = "Perfil Aceitável";
      corClassificacao = "bg-yellow-500 text-yellow-900";
    } else if (riscosAltos === 2) {
      classificacaoGeral = "Perfil de Risco";
      corClassificacao = "bg-orange-500 text-white";
    } else {
      classificacaoGeral = "Perfil Crítico";
      corClassificacao = "bg-red-500 text-white";
    }

    // Prazo máximo recomendado
    const prazoMaxIdade = Math.max(5, 70 - idade);
    const prazoRecomendado = Math.min(prazo, prazoMaxIdade);

    const resultados = {
      valorFinanciar,
      prestacaoMensal,
      ltv,
      mtic,
      jurosTotal,
      taegEstimada,
      dsti,
      riscoLTV,
      riscoDSTI,
      riscoIdade,
      classificacaoGeral,
      corClassificacao,
      prazoMaxIdade,
      prazoRecomendado,
      dentroLimites: ltv <= 90 && dsti <= 50 && idadeFinal <= 75,
    };

    setResultado(resultados);

    if (onCalculate) {
      onCalculate(resultados);
    }
  };

  // Limpar formulário
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
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
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

          {/* Dados do Financiamento */}
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
              👤 Dados do Cliente
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
          <Button onClick={calcular} className="flex-1">
            <Calculator className="h-4 w-4 mr-2" />
            Calcular Risco
          </Button>
          <Button variant="outline" onClick={limpar}>
            Limpar
          </Button>
        </div>

        {/* Resultados */}
        {resultado && (
          <Card className="mt-6 border-2 border-purple-200">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold text-lg">Resultados da Simulação</h3>
                <Badge className={resultado.corClassificacao}>
                  {resultado.classificacaoGeral}
                </Badge>
              </div>

              {/* Valores principais */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                <div className="text-center p-3 bg-blue-50 rounded-lg">
                  <p className="text-xs text-muted-foreground">Valor a Financiar</p>
                  <p className="text-xl font-bold text-blue-600">
                    {resultado.valorFinanciar.toLocaleString('pt-PT')}€
                  </p>
                </div>
                <div className="text-center p-3 bg-green-50 rounded-lg">
                  <p className="text-xs text-muted-foreground">Prestação Mensal</p>
                  <p className="text-xl font-bold text-green-600">
                    {resultado.prestacaoMensal.toFixed(2)}€
                  </p>
                </div>
                <div className="text-center p-3 bg-purple-50 rounded-lg">
                  <p className="text-xs text-muted-foreground">LTV</p>
                  <p className="text-xl font-bold text-purple-600">
                    {resultado.ltv.toFixed(1)}%
                  </p>
                </div>
                <div className="text-center p-3 bg-orange-50 rounded-lg">
                  <p className="text-xs text-muted-foreground">DSTI</p>
                  <p className="text-xl font-bold text-orange-600">
                    {resultado.dsti.toFixed(1)}%
                  </p>
                </div>
              </div>

              {/* Custos totais */}
              <div className="grid grid-cols-3 gap-4 mb-6">
                <div className="text-center p-2 bg-gray-50 rounded">
                  <p className="text-xs text-muted-foreground">MTIC</p>
                  <p className="font-semibold">{resultado.mtic.toLocaleString('pt-PT', { maximumFractionDigits: 0 })}€</p>
                </div>
                <div className="text-center p-2 bg-gray-50 rounded">
                  <p className="text-xs text-muted-foreground">Total Juros</p>
                  <p className="font-semibold text-red-600">{resultado.jurosTotal.toLocaleString('pt-PT', { maximumFractionDigits: 0 })}€</p>
                </div>
                <div className="text-center p-2 bg-gray-50 rounded">
                  <p className="text-xs text-muted-foreground">TAEG Est.</p>
                  <p className="font-semibold">{(resultado.taegEstimada * 100).toFixed(2)}%</p>
                </div>
              </div>

              {/* Análise de risco */}
              <div className="space-y-3">
                <h4 className="font-semibold text-sm">Análise de Risco</h4>
                <div className="grid grid-cols-3 gap-3">
                  <div className={`p-2 rounded border ${
                    resultado.riscoLTV === 'Baixo' ? 'bg-green-50 border-green-200' :
                    resultado.riscoLTV === 'Moderado' ? 'bg-yellow-50 border-yellow-200' :
                    'bg-red-50 border-red-200'
                  }`}>
                    <p className="text-xs text-muted-foreground">Risco LTV</p>
                    <p className="font-semibold">{resultado.riscoLTV}</p>
                  </div>
                  <div className={`p-2 rounded border ${
                    resultado.riscoDSTI === 'Baixo' ? 'bg-green-50 border-green-200' :
                    resultado.riscoDSTI === 'Moderado' ? 'bg-yellow-50 border-yellow-200' :
                    'bg-red-50 border-red-200'
                  }`}>
                    <p className="text-xs text-muted-foreground">Risco DSTI</p>
                    <p className="font-semibold">{resultado.riscoDSTI}</p>
                  </div>
                  <div className={`p-2 rounded border ${
                    resultado.riscoIdade === 'Baixo' ? 'bg-green-50 border-green-200' :
                    resultado.riscoIdade === 'Moderado' ? 'bg-yellow-50 border-yellow-200' :
                    'bg-red-50 border-red-200'
                  }`}>
                    <p className="text-xs text-muted-foreground">Risco Idade</p>
                    <p className="font-semibold">{resultado.riscoIdade}</p>
                  </div>
                </div>
              </div>

              {/* Avisos */}
              {!resultado.dentroLimites && (
                <div className="mt-4 p-3 bg-amber-50 rounded-lg border border-amber-200 flex items-start gap-2">
                  <AlertTriangle className="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" />
                  <div className="text-sm text-amber-800">
                    <strong>Atenção:</strong> Alguns parâmetros estão fora dos limites recomendados.
                    <ul className="list-disc list-inside mt-1">
                      {resultado.ltv > 90 && <li>LTV superior a 90%</li>}
                      {resultado.dsti > 50 && <li>DSTI superior a 50%</li>}
                    </ul>
                  </div>
                </div>
              )}

              {/* Info adicional */}
              <div className="mt-4 p-3 bg-gray-50 rounded-lg text-xs text-muted-foreground">
                <p>
                  <strong>Prazo máximo recomendado:</strong> {resultado.prazoMaxIdade} anos
                  (baseado na idade final do contrato não exceder 70-75 anos)
                </p>
              </div>
            </CardContent>
          </Card>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default RiskCalculator;
