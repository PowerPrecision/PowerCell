/**
 * Monitor de Sinais Vitais do motor de background (Lote 4, ponto 14) com
 * execução forçada (Lote 2, ponto 1).
 *
 * PORQUE É QUE DEIXOU DE SER READ-ONLY
 * A objecção original era: «o motor corre em DOIS processos distintos do
 * `render.yaml` e um disparo a partir da web nunca chegaria ao segundo;
 * um botão que não faz nada é pior do que não existir». A objecção está
 * certa, e a fila persistente é a resposta a ela — não a sua negação:
 *
 *   · job da Aplicação  → corre no processo que serve o pedido;
 *   · job do Processador → fica um PEDIDO que o worker reclama no ciclo
 *     seguinte (até 1 minuto).
 *
 * A UI tem de DISTINGUIR os dois («correu» vs «pedido entregue»), senão
 * é o botão a mentir — exactamente o que a objecção queria evitar. E um
 * pedido que fica pendente é o diagnóstico: prova que o Processador não
 * está a consumir a fila.
 *
 * O estado vem todo calculado do backend (`services/job_heartbeat.py`):
 * este componente apresenta, não decide. Em particular, a distinção
 * DESACTIVADO vs. EM BAIXO é regra de negócio e vive lá, e QUEM PODE ser
 * forçado também (`pode_forcar`/`motivo_sem_forcar`) — uma segunda lista
 * aqui divergiria da do servidor sem dar erro.
 */
import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Loader2,
  PauseCircle,
  Play,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";

import {
  forcarExecucaoDeAutomatismo,
  getAutomationsEngineStatus,
} from "../../services/api";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { safeFormat } from "../../lib/utils";

/**
 * Como cada estado se apresenta. `desactivado` é deliberadamente neutro:
 * em dev quase tudo está desligado por kill switch e um painel a gritar
 * vermelho ensina toda a gente a ignorá-lo.
 */
const ESTADOS = {
  saudavel: { rotulo: "Saudável", variante: "outline", Icone: CheckCircle2 },
  atrasado: { rotulo: "Atrasado", variante: "outline", Icone: Clock },
  falhou: { rotulo: "Falhou", variante: "destructive", Icone: XCircle },
  desactivado: { rotulo: "Desativado", variante: "secondary", Icone: PauseCircle },
  nunca_correu: { rotulo: "Nunca correu", variante: "outline", Icone: AlertTriangle },
  a_correr: { rotulo: "A correr", variante: "outline", Icone: Clock },
};

const PROCESSOS = {
  web: "Aplicação",
  worker: "Processador",
};

const SEM_DATA = "—";

function formatarMomento(iso) {
  if (!iso) return SEM_DATA;
  return safeFormat(iso, "dd/MM/yyyy HH:mm") || SEM_DATA;
}

function formatarDuracao(ms) {
  if (ms === null || ms === undefined) return SEM_DATA;
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

/**
 * O estado do último pedido de execução forçada, em texto.
 *
 * Função PURA e exportada: é a frase que transforma «Nunca correu» num
 * diagnóstico, e tem de poder ser afirmada sem montar o painel.
 */
export function descreverPedido(pedido) {
  if (!pedido) return "";
  if (pedido.estado === "pendente") {
    return "Pedido à espera do Processador. Se não sair deste estado, o Processador não está a consumir a fila.";
  }
  if (pedido.estado === "a_processar") return "Pedido em execução no Processador.";
  if (pedido.estado === "falhada") {
    return `Pedido falhou${pedido.erro ? `: ${pedido.erro}` : "."}`;
  }
  if (pedido.estado === "concluida") return "Último pedido manual concluído.";
  return "";
}

function LinhaDeJob({ job, onForcar, aForcar }) {
  const estado = ESTADOS[job.estado] || ESTADOS.nunca_correu;
  const { Icone } = estado;
  const textoDoPedido = descreverPedido(job.pedido_pendente);

  return (
    <div
      data-testid={`engine-job-${job.chave}`}
      className="flex flex-col gap-2 border-b border-border py-3 last:border-0 sm:flex-row sm:items-start sm:justify-between"
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <Icone className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <p className="truncate font-medium text-sm">{job.nome}</p>
          <Badge variant={estado.variante} className="text-[10px]">
            {estado.rotulo}
          </Badge>
        </div>
        {job.descricao ? (
          <p className="mt-1 text-xs text-muted-foreground">{job.descricao}</p>
        ) : null}
        {job.erro ? (
          <p className="mt-1 text-xs text-destructive break-words">{job.erro}</p>
        ) : null}
        {textoDoPedido ? (
          <p
            data-testid={`engine-pedido-${job.chave}`}
            className="mt-1 text-xs text-muted-foreground break-words"
          >
            {textoDoPedido}
          </p>
        ) : null}
        {/* O motivo de não se poder forçar vai À VISTA: um botão em falta
            sem explicação manda o utilizador procurar o que não existe. */}
        {!job.pode_forcar && job.motivo_sem_forcar ? (
          <p
            data-testid={`engine-sem-forcar-${job.chave}`}
            className="mt-1 text-xs text-muted-foreground"
          >
            {job.motivo_sem_forcar}
          </p>
        ) : null}
      </div>

      <dl className="grid shrink-0 grid-cols-2 gap-x-6 gap-y-1 text-xs sm:grid-cols-4">
        <div>
          <dt className="text-muted-foreground">Onde corre</dt>
          <dd>{PROCESSOS[job.processo] || job.processo}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Última</dt>
          <dd data-testid="engine-last-run" title={job.ultima_execucao || ""}>
            {formatarMomento(job.ultima_execucao)}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Próxima</dt>
          <dd data-testid="engine-next-run" title={job.proxima_execucao || ""}>
            {formatarMomento(job.proxima_execucao)}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Duração</dt>
          <dd>{formatarDuracao(job.duracao_ms)}</dd>
        </div>
      </dl>

      {/* Renderizado só quando `pode_forcar` — e é o servidor que decide
          (um job desativado não se força, e o CDC não tem ciclo). Um botão
          desenhado e desativado por CSS continua acessível ao teclado. */}
      {job.pode_forcar ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="shrink-0 self-start"
          disabled={aForcar}
          onClick={() => onForcar(job)}
        >
          {aForcar ? (
            <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" aria-hidden="true" />
          ) : (
            <Play className="mr-2 h-3.5 w-3.5" aria-hidden="true" />
          )}
          Forçar Execução
        </Button>
      ) : null}
    </div>
  );
}

export default function EngineStatusPanel() {
  const [dados, setDados] = useState(null);
  const [erro, setErro] = useState(false);
  const [aCarregar, setACarregar] = useState(true);
  // A chave do job em execução, e não um booleano: com um booleano, clicar
  // num job desativava o botão de TODOS.
  const [aForcar, setAForcar] = useState(null);

  const carregar = useCallback(async () => {
    try {
      const res = await getAutomationsEngineStatus();
      setDados(res.data);
      setErro(false);
    } catch {
      // Um monitor que fica em branco quando falha é inútil precisamente
      // quando faz falta: diz-se o que aconteceu.
      setErro(true);
    } finally {
      setACarregar(false);
    }
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  const forcar = useCallback(
    async (job) => {
      setAForcar(job.chave);
      try {
        const res = await forcarExecucaoDeAutomatismo(job.chave);
        // A mensagem vem do servidor, que é quem sabe qual dos dois
        // caminhos aconteceu. Escrevê-la aqui obrigava a UI a saber em que
        // processo vive cada job — uma segunda cópia dessa regra.
        toast.success(res.data?.mensagem || `«${job.nome}» accionado.`);
      } catch {
        // O interceptor já mostra o erro; aqui não se duplica o toast.
        // Mas o painel TEM de recarregar à mesma: um pedido que ficou
        // registado antes da falha continua a ser informação.
      } finally {
        setAForcar(null);
        await carregar();
      }
    },
    [carregar],
  );

  if (aCarregar) {
    return <p className="py-6 text-sm text-muted-foreground">A ler o estado do motor…</p>;
  }

  if (erro) {
    return (
      <p className="py-6 text-sm text-destructive">
        Não foi possível ler o estado do motor. Os automatismos podem estar a
        correr à mesma — isto é só o monitor.
      </p>
    );
  }

  const jobs = dados?.jobs || [];
  const resumo = dados?.resumo || {};

  return (
    <Card className="border-border">
      <CardHeader>
        <CardTitle className="text-lg">Estado do motor</CardTitle>
        <CardDescription data-testid="engine-summary">
          {resumo.com_problema > 0
            ? `${resumo.com_problema} de ${resumo.total} automatismos precisam de atenção.`
            : `${resumo.saudaveis || 0} automatismos a correr normalmente.`}
          {resumo.desactivados > 0
            ? ` ${resumo.desactivados} desativados neste ambiente.`
            : ""}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {jobs.map((job) => (
          <LinhaDeJob
            key={job.chave}
            job={job}
            onForcar={forcar}
            aForcar={aForcar === job.chave}
          />
        ))}
      </CardContent>
    </Card>
  );
}
