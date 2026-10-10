/**
 * TeamPerformanceDashboard — Dashboard Executivo de Desempenho (Admin/CEO).
 *
 * Bloco 4, pontos 13 e 16: período à escolha (predefinido ou intervalo de
 * datas), filtros por colaborador e por perfil — aplicados NO SERVIDOR, que
 * só agrega o que foi pedido —, e «Gerar PDF» com o MESMO relatório que o
 * ecrã mostra (gerado no servidor, não capturado do browser).
 *
 * Tudo pelo cliente Axios: o `fetch` cru que esta página usava não levava
 * `X-Company-Id`/`X-Active-Role` (incidente de 2026-09-21, outra instância).
 */
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity } from "lucide-react";
import { toast } from "sonner";

import DashboardLayout from "../layouts/DashboardLayout";
import ExecutiveCharts from "../components/executive/ExecutiveCharts";
import ExecutiveFilters from "../components/executive/ExecutiveFilters";
import ExecutiveKpis from "../components/executive/ExecutiveKpis";
import ExecutiveUsersTable from "../components/executive/ExecutiveUsersTable";
import { descarregarPdf } from "../components/executive/descarregarPdf";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { downloadTeamPerformancePdf, getTeamPerformance } from "../services/api";
import { extractErrorMessage } from "../utils/extractErrorMessage";
import {
  intervaloDaPredefinicao,
  listaOuVazia,
  parametrosDoRelatorio,
  validarIntervalo,
} from "../utils/executivo";

const formatarData = (texto) => (texto ? texto.split("-").reverse().join("/") : "");

export default function TeamPerformanceDashboard() {
  const inicial = intervaloDaPredefinicao("this_week");
  const [predefinicao, setPredefinicao] = useState("this_week");
  const [inicio, setInicio] = useState(inicial.inicio);
  const [fim, setFim] = useState(inicial.fim);
  const [utilizador, setUtilizador] = useState("");
  const [papel, setPapel] = useState("");
  const [opcoes, setOpcoes] = useState([]);
  const [aGerarPdf, setAGerarPdf] = useState(false);

  const erroDoIntervalo = validarIntervalo(inicio, fim);
  const params = useMemo(
    () => parametrosDoRelatorio({ inicio, fim, utilizadores: utilizador ? [utilizador] : [], papeis: papel ? [papel] : [] }),
    [inicio, fim, utilizador, papel],
  );

  const { data, error, isFetching, refetch } = useQuery({
    queryKey: ["team-performance", params],
    queryFn: async () => (await getTeamPerformance(params)).data,
    enabled: !erroDoIntervalo,
    retry: false,
  });

  // A lista do seletor vem do relatório SEM colaborador escolhido: com um
  // escolhido o servidor devolve só esse, e a lista encolheria para um.
  useEffect(() => {
    if (utilizador || !data) return;
    setOpcoes(listaOuVazia(data.users).map((u) => ({ id: u.user_id, nome: u.name })));
  }, [data, utilizador]);

  const escolherPredefinicao = (chave) => {
    setPredefinicao(chave);
    setUtilizador("");
    const intervalo = intervaloDaPredefinicao(chave);
    if (intervalo) {
      setInicio(intervalo.inicio);
      setFim(intervalo.fim);
    }
  };

  const gerarPdf = async () => {
    setAGerarPdf(true);
    const resultado = await descarregarPdf(() => downloadTeamPerformancePdf(params), "relatorio-executivo.pdf");
    setAGerarPdf(false);
    if (resultado.ok) toast.success("PDF gerado");
    else toast.error(resultado.erro);
  };

  const utilizadores = listaOuVazia(data?.users);
  const escolhido = utilizador ? utilizadores.find((u) => u.user_id === utilizador) || null : null;
  const mensagemDeErro = error
    ? extractErrorMessage(error?.response?.data?.detail, "Erro ao carregar dados de desempenho")
    : "";

  return (
    <DashboardLayout title="Desempenho da Equipa">
      <div className="space-y-6 p-1">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Activity className="h-6 w-6 text-primary" aria-hidden="true" />
            Desempenho da Equipa
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Dashboard Executivo — {formatarData(inicio)} a {formatarData(fim)}
          </p>
        </div>

        <ExecutiveFilters
          predefinicao={predefinicao} inicio={inicio} fim={fim} utilizador={utilizador} papel={papel}
          opcoesDeUtilizadores={opcoes} erroDoIntervalo={erroDoIntervalo}
          aCarregar={isFetching} aGerarPdf={aGerarPdf}
          onPredefinicao={escolherPredefinicao}
          onInicio={(v) => { setInicio(v); setPredefinicao("custom"); setUtilizador(""); }}
          onFim={(v) => { setFim(v); setPredefinicao("custom"); setUtilizador(""); }}
          onUtilizador={setUtilizador}
          onPapel={(v) => { setPapel(v); setUtilizador(""); }}
          onActualizar={() => refetch()}
          onGerarPdf={gerarPdf}
        />

        {mensagemDeErro && (
          <p className="text-sm text-destructive border border-destructive/40 rounded-md p-3" role="alert">
            {mensagemDeErro}
          </p>
        )}

        {data?.truncado && (
          <p className="text-sm text-muted-foreground" role="status">
            Lista limitada às primeiras {data.limite_de_utilizadores} pessoas — use os filtros para afunilar.
          </p>
        )}

        <ExecutiveKpis summary={data?.summary} utilizador={escolhido} />
        <ExecutiveCharts relatorio={data} utilizadores={utilizadores} />

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Desempenho por colaborador</CardTitle>
            <CardDescription>
              {utilizadores.length} colaborador{utilizadores.length === 1 ? "" : "es"} no período
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-0">
            <ExecutiveUsersTable
              utilizadores={utilizadores}
              selecionado={utilizador}
              onSelecionar={(id) => setUtilizador(utilizador === id ? "" : id)}
            />
          </CardContent>
        </Card>

        {listaOuVazia(data?.notas).length > 0 && (
          <ul className="text-xs text-muted-foreground space-y-1" data-testid="criterios">
            {data.notas.map((nota) => <li key={nota}>• {nota}</li>)}
          </ul>
        )}
      </div>
    </DashboardLayout>
  );
}
