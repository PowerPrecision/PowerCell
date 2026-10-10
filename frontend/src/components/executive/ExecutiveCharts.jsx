/**
 * Gráficos do relatório executivo (Bloco 4, pontos 13 e 16).
 *
 * Três vistas do MESMO relatório que o PDF compila: actividade por pessoa,
 * entradas por fase e evolução diária. Sem eixo duplo; legenda sempre que há
 * mais de uma série; cores validadas para daltonismo (ver `cores.js`); e a
 * tabela por colaborador é a alternativa em texto.
 */
import {
  Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { dadosDoGraficoDePessoas, listaOuVazia } from "../../utils/executivo";
import { COR_CONCLUIDAS, COR_FASES, SERIES_POR_PESSOA } from "./cores";

function Dica({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const titulo = payload[0]?.payload?.nomeCompleto || label;
  return (
    <div className="rounded-md border bg-background p-3 shadow-md text-sm">
      <p className="font-semibold mb-1">{titulo}</p>
      {payload.map((entrada) => (
        <p key={entrada.name} className="flex items-center gap-2 text-muted-foreground">
          <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: entrada.color }} aria-hidden="true" />
          {entrada.name}: <span className="font-semibold text-foreground">{entrada.value}</span>
        </p>
      ))}
    </div>
  );
}

function Moldura({ titulo, descricao, children, testid }) {
  return (
    <Card data-testid={testid}>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{titulo}</CardTitle>
        {descricao && <CardDescription>{descricao}</CardDescription>}
      </CardHeader>
      <CardContent className="pt-0">{children}</CardContent>
    </Card>
  );
}

/**
 * @param {Object} props
 * @param {object} props.relatorio - O relatório do servidor.
 * @param {Array} [props.utilizadores] - Linhas a mostrar (já filtradas).
 */
export default function ExecutiveCharts({ relatorio, utilizadores }) {
  const pessoas = dadosDoGraficoDePessoas(utilizadores ?? relatorio?.users);
  const fases = listaOuVazia(relatorio?.por_fase).slice(0, 10).map((f) => ({ nome: f.rotulo, nomeCompleto: f.rotulo, "Entradas": f.n }));
  const serie = listaOuVazia(relatorio?.serie_diaria).map((d) => ({
    nome: `${d.dia.slice(8, 10)}/${d.dia.slice(5, 7)}`,
    nomeCompleto: d.dia.split("-").reverse().join("/"),
    "Fases alteradas": d.mudancas_de_fase,
    "Tarefas concluídas": d.tarefas_concluidas,
  }));

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="lg:col-span-2">
        <Moldura
          testid="grafico-pessoas"
          titulo="Actividade por colaborador"
          descricao={`${pessoas.length} colaborador${pessoas.length === 1 ? "" : "es"} no período`}
        >
          {pessoas.length === 0 ? (
            <p className="text-center py-12 text-sm text-muted-foreground">Sem dados para o período seleccionado</p>
          ) : (
            <div className="h-[320px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={pessoas} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barGap={2}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.3} vertical={false} />
                  <XAxis dataKey="nome" tick={{ fontSize: 12 }} interval={0}
                    angle={pessoas.length > 8 ? -30 : 0} textAnchor={pessoas.length > 8 ? "end" : "middle"}
                    height={pessoas.length > 8 ? 56 : 30} />
                  <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
                  <Tooltip content={<Dica />} />
                  <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
                  {SERIES_POR_PESSOA.map(({ chave, cor }) => (
                    <Bar key={chave} dataKey={chave} fill={cor} radius={[4, 4, 0, 0]} maxBarSize={28} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Moldura>
      </div>

      {fases.length > 0 && (
        <Moldura testid="grafico-fases" titulo="Entradas por fase" descricao="Fases de destino das mudanças registadas">
          <div style={{ height: Math.max(160, fases.length * 32 + 30) }} className="w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={fases} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.3} horizontal={false} />
                <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12 }} />
                <YAxis type="category" dataKey="nome" width={120} tick={{ fontSize: 12 }} />
                <Tooltip content={<Dica />} />
                <Bar dataKey="Entradas" fill={COR_FASES} radius={[0, 4, 4, 0]} maxBarSize={20} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Moldura>
      )}

      {serie.length > 0 ? (
        <Moldura testid="grafico-serie" titulo="Evolução diária" descricao="Fases alteradas e tarefas concluídas por dia">
          <div className="h-[220px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={serie} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barGap={2}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.3} vertical={false} />
                <XAxis dataKey="nome" tick={{ fontSize: 12 }} interval={serie.length > 14 ? "preserveStartEnd" : 0} />
                <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
                <Tooltip content={<Dica />} />
                <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
                <Bar dataKey="Fases alteradas" fill={COR_FASES} radius={[4, 4, 0, 0]} maxBarSize={24} />
                <Bar dataKey="Tarefas concluídas" fill={COR_CONCLUIDAS} radius={[4, 4, 0, 0]} maxBarSize={24} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Moldura>
      ) : relatorio?.serie_omitida ? (
        <p className="text-sm text-muted-foreground self-center" data-testid="serie-omitida">
          A evolução diária não é apresentada em períodos com mais de 92 dias.
        </p>
      ) : null}
    </div>
  );
}
