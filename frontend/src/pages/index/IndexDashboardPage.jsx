/**
 * IndexDashboardPage — a fila de trabalho do Index (Lote 12, Fase 4).
 *
 * Duas abas: «Fila de Espera» (por indexar) e «Revisões Pendentes» (indexados com campos por
 * rever). O estado (separador, página, pesquisa) vive no URL (`useEstadoNaUrl`): «Voltar» a
 * partir da bancada devolve a lista como estava.
 *
 * Um erro de LEITURA nunca se apresenta como «fila vazia»: diz-se, com «Tentar de novo».
 */
import { useMemo } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ClipboardCheck, RefreshCw, Search } from "lucide-react";

import DashboardLayout from "../../layouts/DashboardLayout";
import { Alert, AlertDescription, AlertTitle } from "../../components/ui/alert";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "../../components/ui/tabs";
import { Skeleton } from "../../components/ui/skeleton";
import { PageHeader } from "../../components/shared/PageHeader";
import Paginacao from "../../components/shared/Paginacao";
import { FiltrosDaFila } from "../../components/index/FiltrosDaFila";
import { IndexQueueTable } from "../../components/index/IndexQueueTable";
import { PedidosDeAtribuicaoCard } from "../../components/index/PedidosDeAtribuicaoCard";
import { CODEC_NUMERO, useEstadoNaUrl, useTextoNaUrl } from "../../hooks/useEstadoNaUrl";
import { useIndexQueueQuery } from "../../hooks/queries/useIndexQueries";
import {
  ORDENACAO_POR_OMISSAO,
  SEPARADORES,
  SEPARADOR_OMISSAO,
  filtrosDaFila,
  ordenacaoValida,
  proximaOrdenacao,
  separadorValido,
  totalDeFiltrosLigados,
} from "../../utils/indexRevisao";

/** Campo do ecrã → parâmetro do URL. */
const PARAMETRO_DO_URL = { ordem: "idx_sort", estado: "idx_status", empresa: "idx_company", origem: "idx_origin" };

export default function IndexDashboardPage() {
  const navigate = useNavigate();
  const [, setParametros] = useSearchParams();
  const [separadorCru] = useEstadoNaUrl("idx_tab", SEPARADOR_OMISSAO);
  const separador = separadorValido(separadorCru);
  const [pagina, setPagina] = useEstadoNaUrl("idx_p", 1, CODEC_NUMERO);
  const [pesquisaEscrita, setPesquisaEscrita] = useTextoNaUrl("idx_q");
  // a consulta usa o valor já ASSENTE no URL, não o que se está a escrever
  const [pesquisa] = useEstadoNaUrl("idx_q", "");

  // ordem e filtros vivem no URL: «Voltar» a partir da bancada devolve a lista como estava
  const [ordemCrua] = useEstadoNaUrl(PARAMETRO_DO_URL.ordem, "");
  const [estadoCru] = useEstadoNaUrl(PARAMETRO_DO_URL.estado, "");
  const [empresaCrua] = useEstadoNaUrl(PARAMETRO_DO_URL.empresa, "");
  const [origemCrua] = useEstadoNaUrl(PARAMETRO_DO_URL.origem, "");
  const ordem = ordenacaoValida(separador, ordemCrua);
  const filtros = useMemo(
    () => filtrosDaFila(separador, { estado: estadoCru, empresa: empresaCrua, origem: origemCrua }),
    [separador, estadoCru, empresaCrua, origemCrua],
  );

  const fila = useIndexQueueQuery({ tab: separador, page: pagina, q: pesquisa, ordem, filtros });

  // UMA só escrita no URL (ver `mudarSeparador`): `alteracoes` = `{ordem?, estado?, empresa?, origem?}`.
  // O valor por omissão (a ordem da aba, «todos») não vai para o URL, e outra lista começa na página 1.
  const escrever = (alteracoes) =>
    setParametros(
      (anterior) => {
        const seguinte = new URLSearchParams(anterior);
        for (const [campo, valor] of Object.entries(alteracoes)) {
          const chave = PARAMETRO_DO_URL[campo];
          const omissao = campo === "ordem" ? ORDENACAO_POR_OMISSAO[separador] : "";
          if (!valor || valor === omissao) seguinte.delete(chave);
          else seguinte.set(chave, valor);
        }
        seguinte.delete("idx_p");
        return seguinte;
      },
      { replace: true },
    );

  // UMA só escrita no URL: duas chamadas funcionais seguidas (`setSeparador` e `setPagina(1)`)
  // partem ambas do URL do render actual e a segunda pisava a primeira — o separador nunca mudava.
  const mudarSeparador = (valor) =>
    setParametros(
      (anterior) => {
        const seguinte = new URLSearchParams(anterior);
        if (valor === SEPARADOR_OMISSAO) seguinte.delete("idx_tab");
        else seguinte.set("idx_tab", valor);
        seguinte.delete("idx_p"); // outra lista começa na página 1
        // a ordem e o estado são de cada aba (`indexed_*` só existe nas Revisões; os estados diferem)
        seguinte.delete(PARAMETRO_DO_URL.ordem);
        seguinte.delete(PARAMETRO_DO_URL.estado);
        return seguinte;
      },
      { replace: true },
    );

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <PageHeader
          icon={ClipboardCheck}
          title="Indexação"
          description="Processos à espera de indexação e indexações com campos por rever."
          onRefresh={() => fila.refetch()}
          actions={
            <Button asChild variant="outline">
              <Link to="/index/pesquisa">
                <Search className="mr-2 h-4 w-4" aria-hidden="true" />Pesquisa avançada
              </Link>
            </Button>
          }
        />

        {/* Pedidos de alteração de atribuição do Index: só aparece quando há pendentes */}
        <PedidosDeAtribuicaoCard />

        <Tabs value={separador} onValueChange={mudarSeparador}>
          <TabsList>
            {SEPARADORES.map((s) => (
              <TabsTrigger key={s.valor} value={s.valor}>
                {s.rotulo}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        <FiltrosDaFila
          separador={separador}
          ordem={ordem}
          filtros={filtros}
          empresas={fila.empresas}
          onMudar={(campo, valor) => escrever({ [campo]: valor })}
          onLimpar={() => escrever({ estado: "", empresa: "", origem: "" })}
        />

        <Input
          value={pesquisaEscrita}
          onChange={(e) => {
            setPesquisaEscrita(e.target.value);
            setPagina(1);
          }}
          placeholder="Pesquisar por cliente ou nº do processo"
          aria-label="Pesquisar processos"
          className="max-w-sm"
        />

        <Card>
          <CardContent className="pt-6">
            {fila.isError ? (
              <Alert variant="destructive" data-testid="index-erro-de-leitura">
                <AlertTitle>Não foi possível carregar a fila</AlertTitle>
                <AlertDescription className="flex items-center justify-between gap-3">
                  <span>Os dados não foram alterados. Tente de novo.</span>
                  <Button size="sm" variant="outline" onClick={() => fila.refetch()}>
                    <RefreshCw className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                    Tentar de novo
                  </Button>
                </AlertDescription>
              </Alert>
            ) : fila.isLoading ? (
              <div className="space-y-2" data-testid="index-a-carregar">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
              </div>
            ) : (
              <>
                <IndexQueueTable
                  itens={fila.itens}
                  separador={separador}
                  ordem={ordem}
                  onOrdenar={(coluna) => escrever({ ordem: proximaOrdenacao(separador, ordem, coluna) })}
                  comFiltros={totalDeFiltrosLigados(filtros) > 0 || Boolean(pesquisa)}
                  onAbrir={(id) => navigate(`/index/${id}`)}
                />
                <Paginacao
                  total={fila.total}
                  page={pagina}
                  size={fila.tamanho || 25}
                  onPageChange={setPagina}
                  etiqueta="processos"
                />
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </DashboardLayout>
  );
}
