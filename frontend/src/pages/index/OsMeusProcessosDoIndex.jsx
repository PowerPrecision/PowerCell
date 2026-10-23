/**
 * OsMeusProcessosDoIndex — «Os Meus Processos» para quem trabalha como Index (perfil efectivo `indexacao`).
 *
 * A tabela genérica de processos (cliente, contacto, notas do consultor, equipa, prioridade…) é feita para
 * quem acompanha negócios; quem faz a triagem precisa de outra coisa: de que processo se trata, de que
 * empresa vem, em que estado está, quantos documentos tem (e quantos por analisar), quantos avisos tem
 * abertos e há quanto tempo entrou. É exactamente a tabela da fila do Index, aqui filtrada pelo que está
 * ATRIBUÍDO a quem pergunta (`mine` — o servidor decide quem é, nunca o ecrã).
 *
 * O estado (separador, página, pesquisa, ordem) vive no URL: «Voltar» a partir da bancada devolve a lista
 * como estava. Um erro de LEITURA nunca se apresenta como «não tem processos»: diz-se.
 */
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ClipboardCheck, Plus, RefreshCw } from "lucide-react";

import DashboardLayout from "../../layouts/DashboardLayout";
import { Alert, AlertDescription, AlertTitle } from "../../components/ui/alert";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { Skeleton } from "../../components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "../../components/ui/tabs";
import { PageHeader } from "../../components/shared/PageHeader";
import BotaoComPermissao from "../../components/shared/BotaoComPermissao";
import CreateProcessModal from "../../components/CreateProcessModal";
import { useAuth } from "../../contexts/AuthContext";
import { CRIAR_PROCESSO } from "../../utils/capacidades";
import Paginacao from "../../components/shared/Paginacao";
import { IndexQueueTable } from "../../components/index/IndexQueueTable";
import { CODEC_NUMERO, useEstadoNaUrl, useTextoNaUrl } from "../../hooks/useEstadoNaUrl";
import { useIndexQueueQuery } from "../../hooks/queries/useIndexQueries";
import { ORDENACAO_POR_OMISSAO, ordenacaoValida, proximaOrdenacao, separadorValido } from "../../utils/indexRevisao";

/** Os dois separadores da fila, com nomes que fazem sentido numa lista PESSOAL. */
const SEPARADORES_PESSOAIS = Object.freeze([
  { valor: "pending", rotulo: "Por tratar" },
  { valor: "reviews", rotulo: "Indexados a rever" },
]);

/** Só estes filtros chegam ao servidor: a posse (`mine`) é fixa e não se escolhe no ecrã. */
const FILTROS_PESSOAIS = Object.freeze({ mine: true });

export default function OsMeusProcessosDoIndex() {
  const navigate = useNavigate();
  const { user, effectiveRole } = useAuth();
  // O Index também cria processos (`PROCESS_CREATE`): o botão que a tabela completa tinha NÃO se perde ao
  // trocar de tabela. O papel é o EFECTIVO, o mesmo que a rota lê; sem capacidade fica com cadeado e motivo.
  const [aCriar, setACriar] = useState(false);
  const [separadorCru, setSeparadorCru] = useEstadoNaUrl("mp_tab", "pending");
  const separador = separadorValido(separadorCru);
  const [pagina, setPagina] = useEstadoNaUrl("mp_p", 1, CODEC_NUMERO);
  const [pesquisaEscrita, setPesquisaEscrita] = useTextoNaUrl("mp_q");
  const [pesquisa] = useEstadoNaUrl("mp_q", "");
  const [ordemCrua, setOrdemCrua] = useEstadoNaUrl("mp_sort", "");
  const ordem = ordenacaoValida(separador, ordemCrua);

  const fila = useIndexQueueQuery({
    tab: separador, page: pagina, q: pesquisa, ordem, filtros: FILTROS_PESSOAIS,
  });

  const rotuloDoSeparador = useMemo(
    () => SEPARADORES_PESSOAIS.find((s) => s.valor === separador)?.rotulo ?? "",
    [separador],
  );

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <PageHeader
          icon={ClipboardCheck}
          title="Os Meus Processos"
          description="Os processos que lhe estão atribuídos para indexar: de onde vêm, em que estado estão, quantos documentos e avisos têm."
          onRefresh={() => fila.refetch()}
          actions={
            <BotaoComPermissao
              user={user}
              capacidade={CRIAR_PROCESSO}
              papel={effectiveRole}
              className="gap-2"
              onClick={() => setACriar(true)}
              testId="btn-novo-processo"
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              Novo Processo
            </BotaoComPermissao>
          }
        />

        <Tabs
          value={separador}
          onValueChange={(valor) => {
            // outra lista começa na página 1 e na sua ordem (`indexed_*` só existe nas revisões)
            setSeparadorCru(valor);
            setOrdemCrua("");
            setPagina(1);
          }}
        >
          <TabsList>
            {SEPARADORES_PESSOAIS.map((s) => (
              <TabsTrigger key={s.valor} value={s.valor}>
                {s.rotulo}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        <Input
          value={pesquisaEscrita}
          onChange={(e) => {
            setPesquisaEscrita(e.target.value);
            setPagina(1);
          }}
          placeholder="Pesquisar por cliente ou nº do processo"
          aria-label="Pesquisar nos meus processos"
          className="max-w-sm"
        />

        <Card>
          <CardContent className="pt-6">
            {fila.isError ? (
              <Alert variant="destructive" data-testid="meus-processos-erro">
                <AlertTitle>Não foi possível carregar os seus processos</AlertTitle>
                <AlertDescription className="flex items-center justify-between gap-3">
                  <span>Os dados não foram alterados. Tente de novo.</span>
                  <Button size="sm" variant="outline" onClick={() => fila.refetch()}>
                    <RefreshCw className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                    Tentar de novo
                  </Button>
                </AlertDescription>
              </Alert>
            ) : fila.isLoading ? (
              <div className="space-y-2" data-testid="meus-processos-a-carregar">
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
                  onOrdenar={(coluna) => {
                    const seguinte = proximaOrdenacao(separador, ordem, coluna);
                    setOrdemCrua(seguinte === ORDENACAO_POR_OMISSAO[separador] ? "" : seguinte);
                    setPagina(1);
                  }}
                  comFiltros={Boolean(pesquisa)}
                  mensagemVazia={pesquisa ? undefined : `Sem processos ${rotuloDoSeparador.toLowerCase()}`}
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

      <CreateProcessModal open={aCriar} onOpenChange={setACriar} onSuccess={() => fila.refetch()} />
    </DashboardLayout>
  );
}
