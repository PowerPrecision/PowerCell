/**
 * DashboardCalendar — calendário visual simples do Dashboard (Bloco 4, ponto 29).
 *
 * Marcações, datas de escritura e de CPCV e ausências da equipa, num mês. O
 * servidor decide o que o utilizador pode ver (rede, empresa, agenda pessoal
 * ou de equipa); aqui só se desenha.
 *
 * Acessibilidade: cada categoria tem cor E letra, a legenda está sempre
 * visível e o dia seleccionado lista tudo por extenso — a identidade nunca
 * depende só da cor.
 */
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { CalendarDays, ChevronLeft, ChevronRight, Loader2 } from "lucide-react";

import { getDashboardCalendar } from "../../services/api";
import { queryKeys } from "../../lib/queryClient";
import { extractErrorMessage } from "../../utils/extractErrorMessage";
import {
  CATEGORIAS,
  agruparPorDia,
  categoriaDe,
  categoriasDoDia,
  construirGrelha,
  contagemDe,
  mesDe,
  rotaDoItem,
  rotuloDoMes,
  somarMeses,
} from "../../utils/calendarioDashboard";
import { Button } from "../ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";

const DIAS_DA_SEMANA = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];

function Marca({ categoria }) {
  const c = categoriaDe(categoria);
  return (
    <span
      className="inline-flex h-4 w-4 items-center justify-center rounded-sm text-[10px] font-bold text-white"
      style={{ backgroundColor: c.cor }}
      title={c.rotulo}
      aria-hidden="true"
    >
      {c.letra}
    </span>
  );
}

export default function DashboardCalendar() {
  const hoje = new Date().toISOString().slice(0, 10);
  const [mes, setMes] = useState(() => mesDe(new Date()));
  const [seleccionado, setSeleccionado] = useState(hoje);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: queryKeys.deadlines.dashboardCalendar(mes),
    queryFn: async () => (await getDashboardCalendar(mes)).data,
    retry: false,
    staleTime: 60_000,
  });

  const grelha = useMemo(() => construirGrelha(mes), [mes]);
  const porDia = useMemo(() => agruparPorDia(data?.itens), [data]);
  const doDia = porDia[seleccionado] || [];

  const irParaMes = (novo) => {
    setMes(novo);
    // Ao mudar de mês o dia seleccionado passa ao dia 1 (ou a hoje, se for o mês actual).
    setSeleccionado(novo === mesDe(new Date()) ? hoje : `${novo}-01`);
  };

  return (
    <Card data-testid="calendario-do-dashboard">
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <CalendarDays className="h-5 w-5 text-primary" aria-hidden="true" />
              Calendário
            </CardTitle>
            <CardDescription>Marcações, escrituras, CPCVs e ausências da equipa</CardDescription>
          </div>
          <div className="flex items-center gap-1">
            <Button type="button" variant="outline" size="icon" aria-label="Mês anterior" onClick={() => irParaMes(somarMeses(mes, -1))}>
              <ChevronLeft className="h-4 w-4" aria-hidden="true" />
            </Button>
            <span className="min-w-[10rem] text-center text-sm font-medium" data-testid="mes-do-calendario">{rotuloDoMes(mes)}</span>
            <Button type="button" variant="outline" size="icon" aria-label="Mês seguinte" onClick={() => irParaMes(somarMeses(mes, 1))}>
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => irParaMes(mesDe(new Date()))}>Hoje</Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground" aria-label="Legenda">
          {CATEGORIAS.map((c) => (
            <li key={c.chave} className="flex items-center gap-1.5">
              <Marca categoria={c.chave} />
              {c.rotulo}
              <span className="font-semibold text-foreground" data-testid={`contagem-${c.chave}`}>{contagemDe(data?.contagens, c.chave)}</span>
            </li>
          ))}
        </ul>

        {isError && (
          <p className="text-sm text-destructive" role="alert">
            {extractErrorMessage(error?.response?.data?.detail, "Não foi possível carregar o calendário")}
          </p>
        )}

        <div className="relative" aria-busy={isLoading}>
          {isLoading && (
            <div className="absolute inset-0 flex items-center justify-center bg-background/60 z-10" role="status">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-label="A carregar" />
            </div>
          )}
          <div className="grid grid-cols-7 gap-px rounded-md border bg-border overflow-hidden text-xs" role="grid" aria-label={rotuloDoMes(mes)}>
            {DIAS_DA_SEMANA.map((d) => (
              <div key={d} className="bg-muted px-1 py-1 text-center font-medium text-muted-foreground" role="columnheader">{d}</div>
            ))}
            {grelha.flat().map(({ dia, numero, doMes }) => {
              const itens = porDia[dia] || [];
              const cats = categoriasDoDia(itens);
              const activo = dia === seleccionado;
              return (
                <button
                  key={dia}
                  type="button"
                  role="gridcell"
                  data-testid={`dia-${dia}`}
                  aria-label={`${numero}${itens.length ? `, ${itens.length} evento${itens.length === 1 ? "" : "s"}` : ""}`}
                  aria-pressed={activo}
                  onClick={() => setSeleccionado(dia)}
                  className={`min-h-[3.25rem] bg-background p-1 text-left align-top hover:bg-muted/60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring ${doMes ? "" : "text-muted-foreground/60"} ${activo ? "ring-2 ring-inset ring-primary" : ""}`}
                >
                  <span className={`block text-[11px] ${dia === hoje ? "font-bold text-primary" : ""}`}>{numero}</span>
                  <span className="mt-0.5 flex flex-wrap gap-0.5">
                    {cats.slice(0, 4).map((c) => <Marca key={c.chave} categoria={c.chave} />)}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <div data-testid="itens-do-dia">
          <h3 className="text-sm font-medium mb-1">
            {seleccionado.split("-").reverse().join("/")}
          </h3>
          {doDia.length === 0 ? (
            <p className="text-sm text-muted-foreground">Sem eventos neste dia.</p>
          ) : (
            <ul className="space-y-1.5">
              {doDia.map((item) => {
                const rota = rotaDoItem(item);
                const c = categoriaDe(item.categoria);
                return (
                  <li key={item.id} className="flex items-start gap-2 text-sm">
                    <Marca categoria={item.categoria} />
                    <div className="min-w-0">
                      <p className="truncate">
                        <span className="text-muted-foreground">{c.rotulo}{item.hora ? ` · ${item.hora}` : ""} — </span>
                        {rota ? (
                          <Link to={rota} className="text-primary hover:underline">{item.titulo}</Link>
                        ) : item.titulo}
                      </p>
                      {(item.client_name || item.responsavel) && (
                        <p className="text-xs text-muted-foreground truncate">
                          {[item.client_name, item.responsavel].filter(Boolean).join(" · ")}
                        </p>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {data?.truncado && (
          <p className="text-xs text-muted-foreground" role="status">
            Há mais processos neste mês do que os que cabem no calendário.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
