/**
 * WeeklyExecutiveReport — Relatório Semanal Executivo (Admin/CEO).
 *
 * Bloco 4, ponto 13: o progresso da semana (mudanças de fase) e as tarefas
 * concluídas/pendentes de cada colaborador da REDE de quem vê. Uma semana
 * fechada é um REGISTO (calculado uma vez e guardado); a semana em curso é
 * uma vista ao vivo que não se guarda.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarRange, ChevronLeft, ChevronRight, FileDown, Loader2, RotateCw } from "lucide-react";
import { toast } from "sonner";

import DashboardLayout from "../layouts/DashboardLayout";
import ExecutiveCharts from "../components/executive/ExecutiveCharts";
import ExecutiveKpis from "../components/executive/ExecutiveKpis";
import ExecutiveUsersTable from "../components/executive/ExecutiveUsersTable";
import { descarregarPdf } from "../components/executive/descarregarPdf";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import {
  downloadExecutiveWeeklyPdf,
  getExecutiveWeekly,
  regenerateExecutiveWeekly,
} from "../services/api";
import { extractErrorMessage } from "../utils/extractErrorMessage";
import { listaOuVazia, rotuloDaSemana } from "../utils/executivo";

const formatarInstante = (texto) => {
  if (!texto) return "";
  const d = new Date(texto);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleString("pt-PT", { dateStyle: "short", timeStyle: "short" });
};

export default function WeeklyExecutiveReport() {
  const queryClient = useQueryClient();
  const [semana, setSemana] = useState(""); // "" = a semana anterior (fechada)
  const [aGerarPdf, setAGerarPdf] = useState(false);
  const [aRecalcular, setARecalcular] = useState(false);

  const { data, error, isFetching } = useQuery({
    queryKey: ["executive-weekly", semana],
    queryFn: async () => (await getExecutiveWeekly(semana || undefined)).data,
    retry: false,
  });

  const semanas = listaOuVazia(data?.semanas);
  const actual = data?.start_date || "";
  const indice = semanas.findIndex((s) => s.week_start === actual);
  // `semanas` vem da mais recente para a mais antiga.
  const maisRecente = indice > 0 ? semanas[indice - 1] : null;
  const maisAntiga = indice >= 0 && indice < semanas.length - 1 ? semanas[indice + 1] : null;

  const recalcular = async () => {
    setARecalcular(true);
    try {
      const { data: novo } = await regenerateExecutiveWeekly(actual);
      queryClient.setQueryData(["executive-weekly", semana], novo);
      toast.success("Registo da semana recalculado");
    } catch (e) {
      toast.error(extractErrorMessage(e?.response?.data?.detail, "Não foi possível recalcular a semana"));
    } finally {
      setARecalcular(false);
    }
  };

  const gerarPdf = async () => {
    setAGerarPdf(true);
    const r = await descarregarPdf(() => downloadExecutiveWeeklyPdf(actual || undefined), "relatorio-semanal.pdf");
    setAGerarPdf(false);
    if (r.ok) toast.success("PDF gerado");
    else toast.error(r.erro);
  };

  const mensagemDeErro = error
    ? extractErrorMessage(error?.response?.data?.detail, "Erro ao carregar o relatório semanal")
    : "";
  const registo = data?.registo;
  const movimentos = listaOuVazia(data?.movimentos);

  return (
    <DashboardLayout title="Relatório Semanal">
      <div className="space-y-6 p-1">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <CalendarRange className="h-6 w-6 text-primary" aria-hidden="true" />
              Relatório Semanal
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Progresso dos processos e tarefas de cada colaborador, de segunda a domingo.
            </p>
          </div>
          <Button type="button" size="sm" onClick={gerarPdf} disabled={aGerarPdf || !data} className="gap-1.5">
            {aGerarPdf ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <FileDown className="h-4 w-4" aria-hidden="true" />}
            Gerar PDF
          </Button>
        </div>

        <div className="flex flex-wrap items-center gap-2" data-testid="navegador-de-semanas">
          <Button type="button" variant="outline" size="icon" aria-label="Semana anterior"
            disabled={!maisAntiga || isFetching} onClick={() => maisAntiga && setSemana(maisAntiga.week_start)}>
            <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          </Button>
          <Select value={actual} onValueChange={setSemana} disabled={semanas.length === 0}>
            <SelectTrigger className="w-[220px]" aria-label="Semana">
              <SelectValue placeholder="Semana" />
            </SelectTrigger>
            <SelectContent>
              {semanas.map((s) => (
                <SelectItem key={s.week_start} value={s.week_start}>
                  {rotuloDaSemana(s)}{!s.fechada ? " (em curso)" : s.tem_registo ? " · registo" : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button type="button" variant="outline" size="icon" aria-label="Semana seguinte"
            disabled={!maisRecente || isFetching} onClick={() => maisRecente && setSemana(maisRecente.week_start)}>
            <ChevronRight className="h-4 w-4" aria-hidden="true" />
          </Button>

          {registo && (
            <Badge variant={registo.guardado ? "secondary" : "outline"} data-testid="estado-do-registo">
              {registo.guardado
                ? `Registo de ${formatarInstante(registo.gerado_em)}${registo.gerado_por ? ` · ${registo.gerado_por}` : ""}`
                : "Semana em curso — vista ao vivo, ainda não é registo"}
            </Badge>
          )}
          {registo?.guardado && (
            <Button type="button" variant="ghost" size="sm" onClick={recalcular} disabled={aRecalcular} className="gap-1.5">
              {aRecalcular ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <RotateCw className="h-4 w-4" aria-hidden="true" />}
              Recalcular
            </Button>
          )}
        </div>

        {isFetching && !data && (
          <p className="text-sm text-muted-foreground flex items-center gap-2" role="status">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> A calcular o relatório…
          </p>
        )}
        {mensagemDeErro && (
          <p className="text-sm text-destructive border border-destructive/40 rounded-md p-3" role="alert">{mensagemDeErro}</p>
        )}

        {data && (
          <>
            <ExecutiveKpis summary={data.summary} />
            <ExecutiveCharts relatorio={data} />

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Por colaborador</CardTitle>
                <CardDescription>
                  Tarefa concluída conta a quem a concluiu; pendentes e em atraso são no fim da semana.
                </CardDescription>
              </CardHeader>
              <CardContent className="pt-0">
                <ExecutiveUsersTable utilizadores={data.users} />
              </CardContent>
            </Card>

            <Card data-testid="movimentos-de-fase">
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Movimentos de fase</CardTitle>
                <CardDescription>
                  Os mais recentes, dos processos da sua organização ({movimentos.length}).
                </CardDescription>
              </CardHeader>
              <CardContent className="pt-0">
                {movimentos.length === 0 ? (
                  <p className="text-center py-8 text-sm text-muted-foreground">Sem movimentos de fase registados na semana.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Quando</TableHead>
                          <TableHead>Colaborador</TableHead>
                          <TableHead>Processo</TableHead>
                          <TableHead>De</TableHead>
                          <TableHead>Para</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {movimentos.map((m, i) => (
                          <TableRow key={`${m.process_id}-${m.em}-${i}`}>
                            <TableCell className="text-muted-foreground whitespace-nowrap">{formatarInstante(m.em)}</TableCell>
                            <TableCell>{m.user_name}</TableCell>
                            <TableCell>
                              <Link to={`/processo/${m.process_id}`} className="text-primary hover:underline">
                                {m.process_number != null ? `#${m.process_number}` : "Processo"}
                                {m.client_name ? ` · ${m.client_name}` : ""}
                              </Link>
                            </TableCell>
                            <TableCell className="text-muted-foreground">{m.de_rotulo}</TableCell>
                            <TableCell className="font-medium">{m.para_rotulo}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </DashboardLayout>
  );
}
