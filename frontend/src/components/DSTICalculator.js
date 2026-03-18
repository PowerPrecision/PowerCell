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
import { Calculator, AlertTriangle, CheckCircle, Info } from "lucide-react";

/**
 * Calculadora DSTI (Debt Service-to-Income Ratio)
 * Analisa a taxa de esforço do cliente para avaliar capacidade de crédito
 */
const DSTICalculator = ({ trigger, clientData, onCalculate }) => {
  const [open, setOpen] = useState(false);

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
      prestacaoMaxima: rendimentoTotal * 0.5 - prestHipoteca - outros, // Prestação máxima possível
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
      <DialogTrigger asChild>
        {trigger || (
          <Button variant="outline" size="sm" className="gap-2">
            <Calculator className="h-4 w-4" />
            DSTI
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
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
              💰 Rendimentos
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
              📉 Despesas Mensais
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
          <Button onClick={calcular} className="flex-1">
            <Calculator className="h-4 w-4 mr-2" />
            Calcular DSTI
          </Button>
          <Button variant="outline" onClick={limpar}>
            Limpar
          </Button>
        </div>

        {/* Resultados */}
        {resultado && (
          <Card className="mt-6 border-2 border-blue-200">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold text-lg">Resultados da Análise</h3>
                <Badge className={resultado.cor}>
                  {resultado.icone}
                  <span className="ml-1">{resultado.classificacao}</span>
                </Badge>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="text-center p-3 bg-gray-50 rounded-lg">
                  <p className="text-xs text-muted-foreground">DSTI</p>
                  <p className="text-2xl font-bold text-blue-600">
                    {resultado.dsti.toFixed(1)}%
                  </p>
                </div>
                <div className="text-center p-3 bg-gray-50 rounded-lg">
                  <p className="text-xs text-muted-foreground">Taxa Esforço</p>
                  <p className="text-2xl font-bold text-purple-600">
                    {resultado.taxaEsforco.toFixed(1)}%
                  </p>
                </div>
                <div className="text-center p-3 bg-gray-50 rounded-lg">
                  <p className="text-xs text-muted-foreground">Disponibilidade</p>
                  <p className={`text-2xl font-bold ${resultado.disponibilidade >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {resultado.disponibilidade.toFixed(0)}€
                  </p>
                </div>
                <div className="text-center p-3 bg-gray-50 rounded-lg">
                  <p className="text-xs text-muted-foreground">Prestação Máx.</p>
                  <p className="text-2xl font-bold text-amber-600">
                    {resultado.prestacaoMaxima.toFixed(0)}€
                  </p>
                </div>
              </div>

              <div className="mt-4 p-3 bg-blue-50 rounded-lg border border-blue-200">
                <p className="text-sm text-blue-800">
                  <strong>Legenda:</strong><br />
                  • <strong>DSTI até 30%:</strong> Baixo risco - boa capacidade de pagamento<br />
                  • <strong>DSTI 30-40%:</strong> Risco moderado - cuidado com novos créditos<br />
                  • <strong>DSTI 40-50%:</strong> Risco elevado - limite próximo do máximo<br />
                  • <strong>DSTI acima 50%:</strong> Ultrapassa o limite do Banco de Portugal
                </p>
              </div>

              {!resultado.dentroLimite && (
                <div className="mt-4 p-3 bg-red-50 rounded-lg border border-red-200 flex items-start gap-2">
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
