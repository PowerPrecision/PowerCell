/**
 * SimulatorCH — Simulador de Crédito Habitação (Nível Bancário)
 *
 * Pacote AD — Simulador Avançado:
 *   - Modo Básico (sempre visível) + Opções Avançadas (Accordion)
 *   - Taxa Mista com motor matemático de 2 fases (fixa → variável)
 *   - Fallbacks invisíveis de TAEG (Seguro Vida 15€, Multiriscos 10€, Comissões 0€)
 *   - Travas de Idade (maturidade Banco de Portugal) no slider do Prazo
 *
 * MOTOR MATEMÁTICO — Sistema Francês de Amortização:
 *   PMT = (M * r) / (1 - (1 + r)^(-n))
 *
 * Taxa Mista (2 fases):
 *   Fase 1 (prazoTaxaFixa anos): prestação constante com taxaFixa sobre o prazo total
 *   Amortização: capital em dívida = VP das (n - k) prestações restantes
 *   Fase 2 (anos restantes): nova prestação com taxa variável sobre o capital amortizado
 *
 * TAEG (Taxa Anual de Encargos Efetiva):
 *   Calculada por bisseção — taxa que iguala o montante líquido (após comissões)
 *   ao valor presente de todas as prestações + seguros.
 *
 * TRAVAS DE IDADE (Banco de Portugal):
 *   <= 30 anos  → máx 40 anos de prazo
 *   31-35 anos  → máx 37 anos
 *   > 35 anos   → máx 35 anos
 */
import { useState, useMemo, useEffect } from 'react';
import {
  Calculator,
  Info,
  Euro,
  Calendar,
  Percent,
  TrendingUp,
  Settings,
  Shield,
  Home,
  Heart,
} from 'lucide-react';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '../ui/accordion';

// ====================================================================
// CÁLCULO MATEMÁTICO — Sistema Francês de Amortização
// ====================================================================

/**
 * Calcula a prestação mensal do sistema francês.
 *
 * @param {number} montante    - Capital emprestado (€)
 * @param {number} taxaAnual   - Taxa anual nominal em percentagem (ex: 3.5)
 * @param {number} numMeses    - Número total de prestações
 * @returns {number} Prestação mensal (€)
 */
function prestacaoFrances(montante, taxaAnual, numMeses) {
  if (montante <= 0 || numMeses <= 0) return 0;
  const r = taxaAnual / 100 / 12;
  if (r === 0) return montante / numMeses;
  const fator = Math.pow(1 + r, -numMeses);
  return (montante * r) / (1 - fator);
}

/**
 * Capital em dívida após k prestações (sistema francês).
 *
 * O capital em dívida é o valor presente das (n - k) prestações restantes.
 * Usado na Taxa Mista para calcular o capital amortizado no fim da fase fixa.
 *
 * @param {number} prestacaoMensal - Prestação constante
 * @param {number} taxaAnual       - Taxa anual nominal (%)
 * @param {number} numMesesTotal   - Número total de prestações
 * @param {number} k               - Número de prestações já pagas
 * @returns {number} Capital em dívida (€)
 */
function capitalEmDivida(prestacaoMensal, taxaAnual, numMesesTotal, k) {
  const mesesRestantes = numMesesTotal - k;
  if (mesesRestantes <= 0) return 0;
  const r = taxaAnual / 100 / 12;
  if (r === 0) return prestacaoMensal * mesesRestantes;
  // VP de uma anuidade: PMT * (1 - (1+r)^-m) / r
  return prestacaoMensal * (1 - Math.pow(1 + r, -mesesRestantes)) / r;
}

/**
 * Calcula a TAEG por bisseção.
 *
 * A TAEG é a taxa anual que iguala o montante líquido recebido pelo cliente
 * (montante - comissões) ao valor presente de todas as prestações + seguros.
 *
 * @param {number} montanteLiquido  - Montante - comissões (o que o cliente recebe)
 * @param {number} prestacaoMensal  - Prestação mensal (só capital + juros)
 * @param {number} segurosMensal    - Seguros mensais (vida + multiriscos)
 * @param {number} numMeses         - Número total de prestações
 * @returns {number} TAEG em percentagem (ex: 4.12)
 */
function calcularTAEG(montanteLiquido, prestacaoMensal, segurosMensal, numMeses) {
  if (montanteLiquido <= 0 || numMeses <= 0) return 0;
  const fluxoMensal = prestacaoMensal + segurosMensal;

  // Bisseção: encontrar a taxa mensal i tal que
  // montanteLiquido = fluxoMensal * (1 - (1+i)^-n) / i
  let lo = 0.000001;    // 0.0001% mensal
  let hi = 0.10;        // 10% mensal (120% anual) — limite superior generoso
  let mid = 0;

  for (let iter = 0; iter < 100; iter++) {
    mid = (lo + hi) / 2;
    const vp = fluxoMensal * (1 - Math.pow(1 + mid, -numMeses)) / mid;
    if (vp > montanteLiquido) {
      lo = mid; // taxa demasiado baixa → VP alto → subir taxa
    } else {
      hi = mid; // taxa demasiado alta → VP baixo → baixar taxa
    }
    if (hi - lo < 0.0000001) break;
  }

  // Converter taxa mensal para anual (proporcional)
  return mid * 12 * 100;
}

/**
 * Cálculo completo da simulação.
 *
 * Suporta 3 tipos de taxa:
 * - 'fixa': cálculo simples com TAN constante
 * - 'variavel': igual a fixa mas TAN = euribor + spread
 * - 'mista': 2 fases — fase fixa (taxaFixa) + fase variável (tan)
 *
 * @param {object} params - Parâmetros da simulação
 * @returns {object} Resultado com prestação, TAEG, decomposição, etc.
 */
function calcularSimulacao({
  montante,
  prazoAnos,
  tipoTaxa,
  tan,
  taxaFixa,
  prazoTaxaFixaAnos,
  seguroVida,
  seguroMultiriscos,
  comissoesIniciais,
}) {
  const n = prazoAnos * 12;
  if (montante <= 0 || n <= 0) return null;

  const segurosMensal = (Number(seguroVida) || 0) + (Number(seguroMultiriscos) || 0);
  const comissoes = Number(comissoesIniciais) || 0;

  let prestacaoFase1 = 0;
  let prestacaoFase2 = 0;
  let capitalAmortizadoFase1 = montante;
  let mesesFase1 = 0;
  let mesesFase2 = 0;

  if (tipoTaxa === 'mista' && prazoTaxaFixaAnos > 0 && prazoTaxaFixaAnos < prazoAnos) {
    // ═══════ TAXA MISTA — Motor de 2 fases ═══════
    mesesFase1 = prazoTaxaFixaAnos * 12;
    mesesFase2 = n - mesesFase1;

    // Fase 1: prestação com taxaFixa sobre o prazo total
    prestacaoFase1 = prestacaoFrances(montante, Number(taxaFixa), n);

    // Capital em dívida após a fase 1 (k = mesesFase1 prestações pagas)
    capitalAmortizadoFase1 = capitalEmDivida(prestacaoFase1, Number(taxaFixa), n, mesesFase1);

    // Fase 2: nova prestação com taxa variável (tan) sobre o capital restante
    prestacaoFase2 = prestacaoFrances(capitalAmortizadoFase1, Number(tan), mesesFase2);
  } else {
    // ═══════ TAXA FIXA OU VARIÁVEL — Cálculo simples ═══════
    prestacaoFase1 = prestacaoFrances(montante, Number(tan), n);
    mesesFase1 = n;
  }

  // Prestação mensal total (capital + juros + seguros)
  const prestacaoMensal = prestacaoFase1 + segurosMensal;
  const prestacaoMensalFase2 = tipoTaxa === 'mista' && mesesFase2 > 0
    ? prestacaoFase2 + segurosMensal
    : null;

  // Totais
  let totalPagar;
  let totalJuros;
  if (tipoTaxa === 'mista' && mesesFase2 > 0) {
    const totalFase1 = prestacaoFase1 * mesesFase1;
    const totalFase2 = prestacaoFase2 * mesesFase2;
    totalPagar = totalFase1 + totalFase2 + (segurosMensal * n) + comissoes;
    totalJuros = totalPagar - montante - comissoes - (segurosMensal * n);
  } else {
    totalPagar = (prestacaoFase1 * n) + (segurosMensal * n) + comissoes;
    totalJuros = (prestacaoFase1 * n) - montante;
  }

  // TAEG (montante líquido = montante - comissões)
  const montanteLiquido = montante - comissoes;
  const taeg = calcularTAEG(montanteLiquido, prestacaoFase1, segurosMensal, n);

  return {
    prestacaoMensal,
    prestacaoMensalFase2,
    prestacaoFase1,
    prestacaoFase2,
    prestacaoBase: prestacaoFase1,
    segurosMensal,
    comissoes,
    totalPagar,
    totalJuros,
    taeg,
    n,
    mesesFase1,
    mesesFase2,
    capitalAmortizadoFase1,
  };
}

// ====================================================================
// TRAVAS DE IDADE (Maturidade Banco de Portugal)
// ====================================================================

/**
 * Calcula a idade a partir da data de nascimento.
 * @param {string} dataNascimento - ISO date string
 * @returns {number|null} Idade em anos, ou null se inválida
 */
function calcularIdade(dataNascimento) {
  if (!dataNascimento) return null;
  const birth = new Date(dataNascimento);
  if (isNaN(birth.getTime())) return null;
  const now = new Date();
  let age = now.getFullYear() - birth.getFullYear();
  const monthDiff = now.getMonth() - birth.getMonth();
  if (monthDiff < 0 || (monthDiff === 0 && now.getDate() < birth.getDate())) {
    age--;
  }
  return age >= 18 && age <= 100 ? age : null;
}

/**
 * Prazo máximo de empréstimo conforme a idade do cliente (Banco de Portugal).
 *
 * Regras:
 *   <= 30 anos → máx 40 anos
 *   31-35 anos → máx 37 anos
 *   > 35 anos  → máx 35 anos
 *
 * @param {number|null} idade - Idade do cliente (null se desconhecida)
 * @returns {number} Prazo máximo em anos (default 40 se idade desconhecida)
 */
function prazoMaximoPorIdade(idade) {
  if (idade == null) return 40; // Default generoso se não soubermos a idade
  if (idade <= 30) return 40;
  if (idade <= 35) return 37;
  return 35;
}

// ====================================================================
// COMPONENTE — SimulatorCH
// ====================================================================

export default function SimulatorCH({ clienteDataNascimento }) {
  // ── Estado: Simulação Básica (sempre visível) ──
  const [montante, setMontante] = useState(200000);
  const [prazoAnos, setPrazoAnos] = useState(30);
  const [tan, setTan] = useState(3.5);
  const [tipoTaxa, setTipoTaxa] = useState('fixa'); // 'fixa' | 'variavel' | 'mista'

  // ── Estado: Taxa Variável (Euribor) ──
  const [euribor12m, setEuribor12m] = useState(null);
  const [euriborLoading, setEuriborLoading] = useState(false);
  const [euriborIsFallback, setEuriborIsFallback] = useState(false);
  const [spread, setSpread] = useState(1.0);

  // ── Estado: Taxa Mista (Pacote AD) ──
  const [prazoTaxaFixaAnos, setPrazoTaxaFixaAnos] = useState(5);
  const [taxaFixa, setTaxaFixa] = useState(2.5);

  // ── Estado: Opções Avançadas (Pacote AD) ──
  // Fallbacks invisíveis: usados no cálculo mas só visíveis se o Accordion for aberto.
  // Defaults realistas para TAEG: Vida 15€/mês, Multiriscos 10€/mês, Comissões 0€.
  const [seguroVida, setSeguroVida] = useState(15);
  const [seguroMultiriscos, setSeguroMultiriscos] = useState(10);
  const [comissoesIniciais, setComissoesIniciais] = useState(0);

  // ── Idade do cliente (para travas de prazo) ──
  const idade = useMemo(() => calcularIdade(clienteDataNascimento), [clienteDataNascimento]);
  const prazoMax = useMemo(() => prazoMaximoPorIdade(idade), [idade]);

  // ── Euribor automática quando Taxa Variável ──
  useEffect(() => {
    if (tipoTaxa !== 'variavel') return;
    let cancelled = false;
    if (euribor12m != null) {
      setTan(Number((euribor12m + spread).toFixed(2)));
      return;
    }
    setEuriborLoading(true);
    fetch('/api/public/euribor')
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return;
        const eur = Number(data.euribor_12m);
        if (!isNaN(eur)) {
          setEuribor12m(eur);
          setEuriborIsFallback(data.is_fallback === true);
          setTan(Number((eur + spread).toFixed(2)));
        }
      })
      .catch((err) => console.warn('[SimulatorCH] Erro ao buscar Euribor:', err))
      .finally(() => { if (!cancelled) setEuriborLoading(false); });
    return () => { cancelled = true; };
  }, [tipoTaxa, euribor12m, spread]);

  // ── Trava de idade: se o prazo exceder o máximo, ajustar automaticamente ──
  useEffect(() => {
    if (prazoAnos > prazoMax) {
      setPrazoAnos(prazoMax);
    }
  }, [prazoMax, prazoAnos]);

  // ── Handler: mudar tipo de taxa ──
  const handleTipoTaxaChange = (novoTipo) => {
    setTipoTaxa(novoTipo);
    if (novoTipo === 'fixa' && euribor12m != null) {
      setTan(3.5);
    }
  };

  const handleSpreadChange = (novoSpread) => {
    setSpread(Number(novoSpread));
    if (euribor12m != null) {
      setTan(Number((euribor12m + Number(novoSpread)).toFixed(2)));
    }
  };

  // ── Cálculo reactivo ──
  const resultado = useMemo(() => {
    return calcularSimulacao({
      montante,
      prazoAnos,
      tipoTaxa,
      tan,
      taxaFixa,
      prazoTaxaFixaAnos,
      seguroVida,
      seguroMultiriscos,
      comissoesIniciais,
    });
  }, [montante, prazoAnos, tipoTaxa, tan, taxaFixa, prazoTaxaFixaAnos, seguroVida, seguroMultiriscos, comissoesIniciais]);

  // ── Formatação ──
  const fmtEUR = (v) =>
    new Intl.NumberFormat('pt-PT', {
      style: 'currency',
      currency: 'EUR',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(v || 0);

  const pct = (val, min, max) =>
    `${Math.min(100, Math.max(0, ((val - min) / (max - min)) * 100))}%`;

  return (
    <div className="space-y-5">
      {/* ── Card principal: Simulação Rápida ── */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 sm:p-6">
        <h3 className="text-base font-bold text-gray-800 mb-1 flex items-center gap-2">
          <Calculator className="w-5 h-5 text-blue-500" />
          Simulador de Crédito Habitação
        </h3>
        <p className="text-sm text-gray-500 mb-6">
          Estime a sua prestação mensal com o sistema francês de amortização.
        </p>

        <div className="space-y-6">
          {/* ── Tipo de Taxa (3 opções: Fixa / Variável / Mista) ── */}
          <div>
            <label className="text-sm font-medium text-gray-700 flex items-center gap-1.5 mb-2">
              <TrendingUp className="w-4 h-4 text-indigo-500" />
              Tipo de Taxa
            </label>
            <div className="grid grid-cols-3 gap-2">
              <button
                type="button"
                onClick={() => handleTipoTaxaChange('fixa')}
                className={`px-2 py-2 rounded-lg text-xs sm:text-sm font-medium transition-all ${
                  tipoTaxa === 'fixa'
                    ? 'bg-indigo-600 text-white shadow-md'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                Taxa Fixa
              </button>
              <button
                type="button"
                onClick={() => handleTipoTaxaChange('variavel')}
                className={`px-2 py-2 rounded-lg text-xs sm:text-sm font-medium transition-all ${
                  tipoTaxa === 'variavel'
                    ? 'bg-indigo-600 text-white shadow-md'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                Taxa Variável
              </button>
              <button
                type="button"
                onClick={() => handleTipoTaxaChange('mista')}
                className={`px-2 py-2 rounded-lg text-xs sm:text-sm font-medium transition-all ${
                  tipoTaxa === 'mista'
                    ? 'bg-indigo-600 text-white shadow-md'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                Taxa Mista
              </button>
            </div>

            {/* Painel Euribor (Taxa Variável) */}
            {tipoTaxa === 'variavel' && (
              <div className="mt-2 p-2.5 bg-indigo-50 border border-indigo-100 rounded-lg">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-gray-600">Euribor 12M:</span>
                  {euriborLoading ? (
                    <span className="text-gray-400 italic">A carregar...</span>
                  ) : euribor12m != null ? (
                    <span className="font-mono font-bold text-indigo-700">
                      {euribor12m.toFixed(3)}%
                      {euriborIsFallback && <span className="ml-1 text-[9px] text-amber-600">(estimada)</span>}
                    </span>
                  ) : (
                    <span className="text-gray-400 italic">Indisponível</span>
                  )}
                </div>
                <div className="flex items-center justify-between text-xs mt-1.5">
                  <span className="text-gray-600">Spread:</span>
                  <div className="flex items-center gap-1">
                    <input
                      type="number"
                      min="0"
                      max="5"
                      step="0.1"
                      value={spread}
                      onChange={(e) => handleSpreadChange(e.target.value)}
                      className="w-16 px-1.5 py-0.5 text-right text-xs border border-gray-200 rounded font-mono"
                      disabled={euriborLoading}
                    />
                    <span className="text-gray-500">%</span>
                  </div>
                </div>
                {euribor12m != null && (
                  <div className="flex items-center justify-between text-xs mt-1.5 pt-1.5 border-t border-indigo-100">
                    <span className="text-gray-600 font-medium">TAN = Euribor + Spread:</span>
                    <span className="font-mono font-bold text-indigo-800">{tan.toFixed(2)}%</span>
                  </div>
                )}
              </div>
            )}

            {/* ── Campos Taxa Mista (Pacote AD) ── */}
            {tipoTaxa === 'mista' && (
              <div className="mt-2 p-3 bg-violet-50 border border-violet-100 rounded-lg space-y-3">
                <p className="text-xs text-violet-700 flex items-center gap-1.5">
                  <Info className="w-3.5 h-3.5" />
                  <strong>Taxa Mista:</strong> prestação fixa nos primeiros anos, depois variável.
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs text-gray-600 block mb-1">Prazo da Taxa Fixa (anos)</label>
                    <input
                      type="number"
                      min="1"
                      max={prazoAnos - 1}
                      step="1"
                      value={prazoTaxaFixaAnos}
                      onChange={(e) => {
                        const v = parseInt(e.target.value) || 1;
                        setPrazoTaxaFixaAnos(Math.min(v, prazoAnos - 1));
                      }}
                      className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded font-mono"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-gray-600 block mb-1">Taxa Fixa Aplicável (%)</label>
                    <input
                      type="number"
                      min="0.1"
                      max="10"
                      step="0.05"
                      value={taxaFixa}
                      onChange={(e) => setTaxaFixa(Number(e.target.value))}
                      className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded font-mono"
                    />
                  </div>
                </div>
                <div className="flex items-center justify-between text-xs pt-1.5 border-t border-violet-100">
                  <span className="text-gray-600">Taxa Variável após fase fixa (TAN):</span>
                  <span className="font-mono font-bold text-violet-700">{tan.toFixed(2)}%</span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-gray-600">Estrutura:</span>
                  <span className="font-mono text-violet-700 text-[11px]">
                    {prazoTaxaFixaAnos} anos fixa → {prazoAnos - prazoTaxaFixaAnos} anos variável
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* ── Montante ── */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium text-gray-700 flex items-center gap-1.5">
                <Euro className="w-4 h-4 text-emerald-500" />
                Montante do Empréstimo
              </label>
              <span className="text-sm font-bold text-emerald-700 bg-emerald-50 px-3 py-1 rounded-lg">
                {fmtEUR(montante)}
              </span>
            </div>
            <input
              type="range"
              min={50000}
              max={1000000}
              step={5000}
              value={montante}
              onChange={(e) => setMontante(Number(e.target.value))}
              className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-emerald-500"
              style={{
                background: `linear-gradient(to right, #10b981 0%, #10b981 ${pct(montante, 50000, 1000000)}, #e5e7eb ${pct(montante, 50000, 1000000)}, #e5e7eb 100%)`,
              }}
            />
            <div className="flex justify-between text-[10px] text-gray-400 mt-1">
              <span>50 000 EUR</span>
              <span>1 000 000 EUR</span>
            </div>
          </div>

          {/* ── Prazo (com trava de idade dinâmica) ── */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium text-gray-700 flex items-center gap-1.5">
                <Calendar className="w-4 h-4 text-blue-500" />
                Prazo
                {idade != null && (
                  <span className="text-[10px] text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded ml-1">
                    Idade: {idade} anos • máx {prazoMax} anos
                  </span>
                )}
              </label>
              <span className="text-sm font-bold text-blue-700 bg-blue-50 px-3 py-1 rounded-lg">
                {prazoAnos} anos ({prazoAnos * 12} meses)
              </span>
            </div>
            <input
              type="range"
              min={5}
              max={prazoMax}
              step={1}
              value={Math.min(prazoAnos, prazoMax)}
              onChange={(e) => setPrazoAnos(Number(e.target.value))}
              className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-500"
              style={{
                background: `linear-gradient(to right, #3b82f6 0%, #3b82f6 ${pct(prazoAnos, 5, prazoMax)}, #e5e7eb ${pct(prazoAnos, 5, prazoMax)}, #e5e7eb 100%)`,
              }}
            />
            <div className="flex justify-between text-[10px] text-gray-400 mt-1">
              <span>5 anos</span>
              <span>{prazoMax} anos {idade != null && '(limite por idade)'}</span>
            </div>
            {idade != null && prazoAnos >= prazoMax && (
              <p className="text-[10px] text-amber-600 mt-1 flex items-center gap-1">
                <Info className="w-3 h-3" />
                Prazo máximo para a sua idade ({idade} anos) atingido — Banco de Portugal.
              </p>
            )}
          </div>

          {/* ── TAN (Taxa de Juro) — só para Fixa e Mista (Variável usa Euribor+spread) ── */}
          {tipoTaxa !== 'variavel' && (
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm font-medium text-gray-700 flex items-center gap-1.5">
                  <Percent className="w-4 h-4 text-amber-500" />
                  {tipoTaxa === 'mista' ? 'Taxa Variável (após fase fixa)' : 'Taxa de Juro / TAN'}
                </label>
                <span className="text-sm font-bold text-amber-700 bg-amber-50 px-3 py-1 rounded-lg">
                  {tan.toFixed(2)}%
                </span>
              </div>
              <input
                type="range"
                min={0.5}
                max={10}
                step={0.05}
                value={tan}
                onChange={(e) => setTan(Number(e.target.value))}
                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-amber-500"
                style={{
                  background: `linear-gradient(to right, #f59e0b 0%, #f59e0b ${pct(tan, 0.5, 10)}, #e5e7eb ${pct(tan, 0.5, 10)}, #e5e7eb 100%)`,
                }}
              />
              <div className="flex justify-between text-[10px] text-gray-400 mt-1">
                <span>0.5%</span>
                <span>10%</span>
              </div>
            </div>
          )}

          {/* ═══════ OPÇÕES AVANÇADAS (Accordion) ═══════ */}
          <Accordion type="single" collapsible className="border border-gray-200 rounded-lg">
            <AccordionItem value="avancadas" className="border-0">
              <AccordionTrigger className="px-4 py-3 hover:no-underline text-sm font-medium text-gray-700">
                <span className="flex items-center gap-2">
                  <Settings className="w-4 h-4 text-gray-500" />
                  Opções Avançadas
                  <span className="text-[10px] text-gray-400 font-normal">
                    (seguros e comissões — valores por defeito aplicados)
                  </span>
                </span>
              </AccordionTrigger>
              <AccordionContent className="px-4 pb-4 pt-1">
                <div className="space-y-4">
                  <p className="text-xs text-gray-500 bg-gray-50 p-2.5 rounded-lg">
                    Estes valores são usados no cálculo da TAEG. Se não os alterar, são aplicados
                    os valores por defeito: <strong>Seguro de Vida 15€/mês</strong>,
                    <strong> Multiriscos 10€/mês</strong>, <strong>Comissões 0€</strong>.
                  </p>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    {/* Seguro de Vida */}
                    <div>
                      <label className="text-xs text-gray-600 flex items-center gap-1 mb-1">
                        <Heart className="w-3.5 h-3.5 text-rose-500" />
                        Seguro de Vida (€/mês)
                      </label>
                      <input
                        type="number"
                        min="0"
                        step="0.5"
                        value={seguroVida}
                        onChange={(e) => setSeguroVida(Number(e.target.value) || 0)}
                        className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded font-mono"
                      />
                    </div>
                    {/* Seguro Multiriscos */}
                    <div>
                      <label className="text-xs text-gray-600 flex items-center gap-1 mb-1">
                        <Home className="w-3.5 h-3.5 text-blue-500" />
                        Multiriscos (€/mês)
                      </label>
                      <input
                        type="number"
                        min="0"
                        step="0.5"
                        value={seguroMultiriscos}
                        onChange={(e) => setSeguroMultiriscos(Number(e.target.value) || 0)}
                        className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded font-mono"
                      />
                    </div>
                    {/* Comissões Iniciais */}
                    <div>
                      <label className="text-xs text-gray-600 flex items-center gap-1 mb-1">
                        <Shield className="w-3.5 h-3.5 text-amber-500" />
                        Comissões Iniciais (€)
                      </label>
                      <input
                        type="number"
                        min="0"
                        step="50"
                        value={comissoesIniciais}
                        onChange={(e) => setComissoesIniciais(Number(e.target.value) || 0)}
                        className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded font-mono"
                      />
                    </div>
                  </div>
                </div>
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        </div>
      </div>

      {/* ── Resultado ── */}
      {resultado && resultado.prestacaoMensal > 0 && (
        <div className="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-2xl shadow-sm border border-blue-200 p-5 sm:p-6">
          {/* Prestação Mensal — destaque principal */}
          <div className="text-center mb-5">
            <p className="text-sm text-blue-600 font-medium mb-1">
              {tipoTaxa === 'mista' && resultado.prestacaoMensalFase2
                ? `Prestação Fase 1 (anos 1-${prazoTaxaFixaAnos})`
                : 'Prestação Estimada'}
            </p>
            <p className="text-4xl sm:text-5xl font-extrabold text-blue-900 tracking-tight">
              {fmtEUR(resultado.prestacaoMensal)}
              <span className="text-lg font-medium text-blue-500 ml-1">/ mês</span>
            </p>
            {/* TAEG — destaque secundário (Pacote AD) */}
            <div className="mt-2 inline-flex items-center gap-1.5 bg-white/70 px-3 py-1 rounded-full">
              <Percent className="w-3.5 h-3.5 text-indigo-600" />
              <span className="text-xs text-gray-600">TAEG estimada:</span>
              <span className="text-sm font-bold text-indigo-700">{resultado.taeg.toFixed(2)}%</span>
            </div>
          </div>

          {/* Prestação Fase 2 (Taxa Mista) */}
          {tipoTaxa === 'mista' && resultado.prestacaoMensalFase2 && (
            <div className="mb-5 p-3 bg-violet-100/60 rounded-xl text-center">
              <p className="text-xs text-violet-700 font-medium mb-1">
                Prestação Fase 2 (anos {prazoTaxaFixaAnos + 1}-{prazoAnos}) — Taxa Variável
              </p>
              <p className="text-2xl font-extrabold text-violet-900">
                {fmtEUR(resultado.prestacaoMensalFase2)}
                <span className="text-sm font-medium text-violet-500 ml-1">/ mês</span>
              </p>
              <p className="text-[10px] text-violet-600 mt-1">
                Capital em dívida no fim da fase fixa: {fmtEUR(resultado.capitalAmortizadoFase1)}
              </p>
            </div>
          )}

          {/* Detalhes */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="bg-white/70 rounded-xl p-3.5 text-center">
              <p className="text-[10px] text-gray-500 uppercase tracking-wide mb-0.5">Montante</p>
              <p className="text-sm font-bold text-gray-800">{fmtEUR(montante)}</p>
            </div>
            <div className="bg-white/70 rounded-xl p-3.5 text-center">
              <p className="text-[10px] text-gray-500 uppercase tracking-wide mb-0.5">Total a Pagar</p>
              <p className="text-sm font-bold text-gray-800">{fmtEUR(resultado.totalPagar)}</p>
            </div>
            <div className="bg-white/70 rounded-xl p-3.5 text-center">
              <p className="text-[10px] text-gray-500 uppercase tracking-wide mb-0.5">Total de Juros</p>
              <p className="text-sm font-bold text-amber-700">{fmtEUR(resultado.totalJuros)}</p>
            </div>
            <div className="bg-white/70 rounded-xl p-3.5 text-center">
              <p className="text-[10px] text-gray-500 uppercase tracking-wide mb-0.5">Seguros + Comissões</p>
              <p className="text-sm font-bold text-rose-600">
                {fmtEUR((resultado.segurosMensal * resultado.n) + resultado.comissoes)}
              </p>
            </div>
          </div>

          {/* Rácio juros/capital */}
          <div className="mt-4">
            <div className="flex items-center justify-between text-xs text-gray-500 mb-1.5">
              <span>Capital</span>
              <span>Juros ({((resultado.totalJuros / resultado.totalPagar) * 100).toFixed(1)}%)</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden flex">
              <div
                className="bg-gradient-to-r from-emerald-400 to-emerald-500 h-3 transition-all duration-500"
                style={{ width: `${(montante / resultado.totalPagar) * 100}%` }}
              />
              <div
                className="bg-gradient-to-r from-amber-400 to-amber-500 h-3 transition-all duration-500"
                style={{ width: `${(resultado.totalJuros / resultado.totalPagar) * 100}%` }}
              />
            </div>
            <div className="flex items-center justify-between text-[10px] mt-1">
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-emerald-400 inline-block" />
                Capital: {fmtEUR(montante)}
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-amber-400 inline-block" />
                Juros: {fmtEUR(resultado.totalJuros)}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* ── Disclaimer ── */}
      <div className="flex items-start gap-2 bg-gray-50 rounded-xl p-4 border border-gray-100">
        <Info className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
        <p className="text-xs text-gray-500 leading-relaxed">
          <strong>Simulação indicativa.</strong> Os valores apresentados são estimativas baseadas
          no sistema francês de amortização. A TAEG inclui seguros e comissões conforme os valores
          introduzidos (ou os valores por defeito de 15€/10€/0€). {tipoTaxa === 'mista' && 'Na taxa mista, a prestação da fase 2 é estimada com a taxa variável atual e pode variar no futuro. '}
          Para uma proposta personalizada, contacte a nossa equipa de consultores.
        </p>
      </div>
    </div>
  );
}
