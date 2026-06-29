/**
 * SimulatorCH — Simulador de Crédito Habitação (Sistema Francês de Amortização)
 *
 * Permite ao cliente estimar a prestação mensal com base em:
 *   - Montante do Empréstimo (EUR)
 *   - Prazo em Anos
 *   - Taxa de Juro / TAN (%)
 *
 * Fórmula do Sistema Francês:
 *   PMT = (M * r) / (1 - (1 + r)^(-n))
 *
 *   Onde:
 *     M = Montante do empréstimo
 *     r = Taxa mensal = TAN / 100 / 12
 *     n = Número de meses = Prazo * 12
 *     PMT = Prestação mensal estimada
 *
 * Nota: Este simulador é meramente indicativo e não constitui uma proposta
 * vinculativa. Os valores reais podem variar em função de seguros, comissões
 * e outras condições do financiamento.
 */
import React, { useState, useMemo, useEffect } from 'react';
import { Calculator, TrendingDown, Info, Euro, Calendar, Percent, TrendingUp } from 'lucide-react';

// ====================================================================
// CÁLCULO MATEMÁTICO — Sistema Francês de Amortização
// ====================================================================

/**
 * Calcula a prestação mensal usando o sistema francês de amortização.
 *
 * Fórmula:  PMT = (M * r) / (1 - (1 + r)^(-n))
 *
 * @param {number} montante  - Montante do empréstimo em EUR
 * @param {number} prazoAnos - Prazo do empréstimo em anos
 * @param {number} tan       - Taxa Anual Nominal em percentagem (ex: 3.5)
 * @returns {object} { prestacaoMensal, totalPagar, totalJuros, amortizacao: [] }
 */
function calcularPrestacaoFrances(montante, prazoAnos, tan) {
  // Converter taxa anual para mensal (taxa proporcional)
  const r = tan / 100 / 12; // Taxa mensal decimal
  const n = prazoAnos * 12; // Número total de meses

  // Casos especiais
  if (montante <= 0 || n <= 0) return null;
  if (r === 0) {
    // Taxa zero — prestação é simplesmente montante / meses
    const prestacaoMensal = montante / n;
    return {
      prestacaoMensal,
      totalPagar: montante,
      totalJuros: 0,
      n,
    };
  }

  // ═══════════════════════════════════════════════════════════════
  // FÓRMULA DO SISTEMA FRANCÊS
  //
  //   PMT = (M * r) / (1 - (1 + r)^(-n))
  //
  // Onde:
  //   M = montante (capital emprestado)
  //   r = taxa de juro mensal (TAN / 12)
  //   n = número total de prestações (prazo em anos * 12)
  //   PMT = prestação mensal constante
  // ═══════════════════════════════════════════════════════════════
  const fator = Math.pow(1 + r, -n); // (1 + r)^(-n)
  const prestacaoMensal = (montante * r) / (1 - fator);

  const totalPagar = prestacaoMensal * n;
  const totalJuros = totalPagar - montante;

  return {
    prestacaoMensal,
    totalPagar,
    totalJuros,
    n,
  };
}

// ====================================================================
// COMPONENTE — SimulatorCH
// ====================================================================

export default function SimulatorCH() {
  const [montante, setMontante] = useState(200000);
  const [prazoAnos, setPrazoAnos] = useState(30);
  const [tan, setTan] = useState(3.5);
  // Pacote AC: Taxa Variável com Euribor automática
  const [tipoTaxa, setTipoTaxa] = useState('fixa'); // 'fixa' | 'variavel'
  const [euribor12m, setEuribor12m] = useState(null);
  const [euriborLoading, setEuriborLoading] = useState(false);
  const [euriborIsFallback, setEuriborIsFallback] = useState(false);
  const [spread, setSpread] = useState(1.0); // spread sobre Euribor (padrão 1.0%)

  // Pacote AC: quando Taxa Variável é selecionada, buscar Euribor automática
  // do endpoint público (com cache diário no backend) e preencher TAN = euribor + spread.
  useEffect(() => {
    if (tipoTaxa !== 'variavel') return;
    let cancelled = false;
    // Se já temos a Euribor, recalcular TAN imediatamente
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

  // Se o utilizador voltar a Taxa Fixa, restaurar TAN padrão
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

  // Cálculo reactivo — atualiza automaticamente quando os inputs mudam
  const resultado = useMemo(() => {
    return calcularPrestacaoFrances(montante, prazoAnos, tan);
  }, [montante, prazoAnos, tan]);

  // Formatação em EUR (pt-PT)
  const fmtEUR = (v) =>
    new Intl.NumberFormat('pt-PT', {
      style: 'currency',
      currency: 'EUR',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(v);

  // Slider track fill percentage
  const pct = (val, min, max) =>
    `${Math.min(100, Math.max(0, ((val - min) / (max - min)) * 100))}%`;

  return (
    <div className="space-y-5">
      {/* ── Card principal do simulador ── */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 sm:p-6">
        <h3 className="text-base font-bold text-gray-800 mb-1 flex items-center gap-2">
          <Calculator className="w-5 h-5 text-blue-500" />
          Simulador de Crédito Habitação
        </h3>
        <p className="text-sm text-gray-500 mb-6">
          Estime a sua prestação mensal com o sistema francês de amortização.
        </p>

        {/* ── Inputs ── */}
        <div className="space-y-6">
          {/* Pacote AC: Seletor de Tipo de Taxa (Fixa / Variável) */}
          <div>
            <label className="text-sm font-medium text-gray-700 flex items-center gap-1.5 mb-2">
              <TrendingUp className="w-4 h-4 text-indigo-500" />
              Tipo de Taxa
            </label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => handleTipoTaxaChange('fixa')}
                className={`px-3 py-2 rounded-lg text-sm font-medium transition-all ${
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
                className={`px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                  tipoTaxa === 'variavel'
                    ? 'bg-indigo-600 text-white shadow-md'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                Taxa Variável
              </button>
            </div>
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
          </div>

          {/* Montante */}
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

          {/* Prazo */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium text-gray-700 flex items-center gap-1.5">
                <Calendar className="w-4 h-4 text-blue-500" />
                Prazo
              </label>
              <span className="text-sm font-bold text-blue-700 bg-blue-50 px-3 py-1 rounded-lg">
                {prazoAnos} anos ({prazoAnos * 12} meses)
              </span>
            </div>
            <input
              type="range"
              min={5}
              max={40}
              step={1}
              value={prazoAnos}
              onChange={(e) => setPrazoAnos(Number(e.target.value))}
              className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-500"
              style={{
                background: `linear-gradient(to right, #3b82f6 0%, #3b82f6 ${pct(prazoAnos, 5, 40)}, #e5e7eb ${pct(prazoAnos, 5, 40)}, #e5e7eb 100%)`,
              }}
            />
            <div className="flex justify-between text-[10px] text-gray-400 mt-1">
              <span>5 anos</span>
              <span>40 anos</span>
            </div>
          </div>

          {/* Taxa de Juro */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium text-gray-700 flex items-center gap-1.5">
                <Percent className="w-4 h-4 text-amber-500" />
                Taxa de Juro / TAN
              </label>
              <span className="text-sm font-bold text-amber-700 bg-amber-50 px-3 py-1 rounded-lg">
                {tan.toFixed(2)}%
              </span>
            </div>
            <input
              type="range"
              min={0.5}
              max={10}
              step={0.1}
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
        </div>
      </div>

      {/* ── Resultado ── */}
      {resultado && resultado.prestacaoMensal > 0 && (
        <div className="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-2xl shadow-sm border border-blue-200 p-5 sm:p-6">
          {/* Prestação Mensal — destaque principal */}
          <div className="text-center mb-5">
            <p className="text-sm text-blue-600 font-medium mb-1">Prestação Estimada</p>
            <p className="text-4xl sm:text-5xl font-extrabold text-blue-900 tracking-tight">
              {fmtEUR(resultado.prestacaoMensal)}
              <span className="text-lg font-medium text-blue-500 ml-1">/ mês</span>
            </p>
          </div>

          {/* Detalhes */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
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
          <strong>Simulação indicativa.</strong> Os valores apresentados são estimativas
          baseadas no sistema francês de amortização com taxa fixa e não incluem seguros,
          comissões ou outros encargos. Para uma proposta personalizada, contacte a nossa
          equipa de consultores.
        </p>
      </div>
    </div>
  );
}
