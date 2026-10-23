/**
 * IndexSearchPage — a pesquisa avançada do Index (recibos por valor, declarações por região, extratos por banco).
 *
 * A pergunta vive no URL (`ps_*`): abrir um processo num novo separador não a perde, «Voltar» devolve-a
 * como estava e um link partilha-se. Cada linha tem «Ver documento»: abre o PDF ou a imagem que fez match
 * num diálogo sobreposto, SEM sair da lista. Um erro de LEITURA nunca é «sem resultados»: diz-se.
 */
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { RefreshCw, Search } from "lucide-react";

import DashboardLayout from "../../layouts/DashboardLayout";
import { Alert, AlertDescription, AlertTitle } from "../../components/ui/alert";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { EmptyState } from "../../components/ui/EmptyState";
import { Skeleton } from "../../components/ui/skeleton";
import { PageHeader } from "../../components/shared/PageHeader";
import Paginacao from "../../components/shared/Paginacao";
import PesquisaAvancadaFiltros from "../../components/index/PesquisaAvancadaFiltros";
import ResultadosDaPesquisa from "../../components/index/ResultadosDaPesquisa";
import VisualizadorDeDocumento from "../../components/index/VisualizadorDeDocumento";
import { useIndexSearchQuery } from "../../hooks/queries/useIndexQueries";
import { useDescarregarDocumentos } from "../../hooks/useDescarregarDocumentos";
import { mensagemDeErro } from "../../utils/indexRevisao";
import {
  FILTROS_VAZIOS,
  filtrosDoUrl,
  filtrosParaPedido,
  filtrosParaUrl,
  haPesquisaNoUrl,
  normalizarFiltros,
  paginaDoUrl,
  validarFiltros,
} from "../../utils/pesquisaIndex";

const TAMANHO_DA_PAGINA = 25;

export default function IndexSearchPage() {
  const [parametros, setParametros] = useSearchParams();
  const chaveDoUrl = parametros.toString();
  const submetidos = useMemo(() => filtrosDoUrl(parametros), [chaveDoUrl]); // eslint-disable-line react-hooks/exhaustive-deps
  const pagina = paginaDoUrl(parametros);
  const pesquisou = haPesquisaNoUrl(parametros);

  const [rascunho, setRascunho] = useState(submetidos);
  const [erros, setErros] = useState({});
  const [aVer, setAVer] = useState(null);
  const { descarregar, emCurso } = useDescarregarDocumentos();

  // «Voltar» (ou um link) muda o URL por fora: o formulário acompanha-o.
  useEffect(() => {
    setRascunho(submetidos);
    setErros({});
  }, [submetidos]);

  const pedido = useMemo(
    () => (pesquisou ? filtrosParaPedido(submetidos, { pagina, tamanho: TAMANHO_DA_PAGINA }) : null),
    [pesquisou, submetidos, pagina],
  );
  const consulta = useIndexSearchQuery(pedido, { enabled: pesquisou });
  const resultado = consulta.data;

  const mudar = (campo, valor) => setRascunho((r) => normalizarFiltros({ ...r, [campo]: valor }));

  const pesquisar = () => {
    const encontrados = validarFiltros(rascunho);
    setErros(encontrados);
    if (Object.keys(encontrados).length) return;
    const igual = filtrosParaUrl(parametros, rascunho, 1).toString() === chaveDoUrl;
    setParametros((anterior) => filtrosParaUrl(anterior, rascunho, 1), { replace: true });
    if (igual) consulta.refetch(); // a mesma pergunta outra vez: ir buscar de novo
  };

  const limpar = () => {
    setRascunho(FILTROS_VAZIOS);
    setErros({});
    setParametros(
      (anterior) => {
        const seguinte = new URLSearchParams(anterior);
        for (const chave of [...seguinte.keys()]) if (chave.startsWith("ps_")) seguinte.delete(chave);
        return seguinte;
      },
      { replace: true },
    );
  };

  const irParaPagina = (n) =>
    setParametros((anterior) => filtrosParaUrl(anterior, submetidos, n), { replace: true });

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <PageHeader
          icon={Search}
          title="Pesquisa avançada"
          description="Recibos por valor, declarações de efetividade por região e extratos por banco, nos processos a que tem acesso."
        />

        <Card>
          <CardContent className="pt-6">
            <PesquisaAvancadaFiltros
              valores={rascunho}
              erros={erros}
              aPesquisar={consulta.isFetching}
              onMudar={mudar}
              onPesquisar={pesquisar}
              onLimpar={limpar}
            />
          </CardContent>
        </Card>

        {!pesquisou && (
          <EmptyState
            icon={Search}
            title="Escolha o que procurar"
            message="Defina os filtros e carregue em «Pesquisar». Pode pesquisar sem filtros para listar tudo."
          />
        )}

        {pesquisou && consulta.isError && !resultado && (
          <Alert variant="destructive" role="alert" data-testid="pesquisa-erro">
            <AlertTitle>Não foi possível pesquisar</AlertTitle>
            <AlertDescription className="flex flex-wrap items-center gap-3">
              <span>{mensagemDeErro(consulta.error, "A pesquisa falhou. Tente de novo.")}</span>
              <Button type="button" size="sm" variant="outline" onClick={() => consulta.refetch()} className="gap-1">
                <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />Tentar de novo
              </Button>
            </AlertDescription>
          </Alert>
        )}

        {pesquisou && consulta.isLoading && (
          <div className="space-y-2" role="status" aria-label="A pesquisar">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        )}

        {pesquisou && resultado && (
          <Card>
            <CardContent className="pt-6">
              <ResultadosDaPesquisa
                vista={resultado.vista}
                tipo={submetidos.document_type}
                itens={resultado.itens}
                onVerDocumento={(documentos, titulo) => setAVer({ documentos, titulo })}
                onDescarregar={descarregar}
                emCurso={emCurso}
              />
              <Paginacao
                total={resultado.total}
                page={resultado.pagina}
                size={resultado.tamanho}
                onPageChange={irParaPagina}
                etiqueta="resultados"
              />
            </CardContent>
          </Card>
        )}
      </div>

      <VisualizadorDeDocumento
        documentos={aVer?.documentos}
        titulo={aVer?.titulo}
        onFechar={() => setAVer(null)}
        onDescarregar={descarregar}
        emCurso={emCurso}
      />
    </DashboardLayout>
  );
}
