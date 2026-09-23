/**
 * Monitor de Sinais Vitais do motor de background (Lote 4, ponto 14).
 *
 * READ-ONLY por desenho. O motor corre em DOIS processos distintos do
 * `render.yaml` — a aplicação (`powercell`) e o worker
 * (`powercell-worker`) — e um disparo a partir da web nunca chegaria ao
 * segundo. Um botão que não faz nada é pior do que não existir.
 *
 * O estado vem todo calculado do backend (`services/job_heartbeat.py`):
 * este componente apresenta, não decide. Em particular, a distinção
 * DESACTIVADO vs. EM BAIXO é regra de negócio e vive lá.
 */
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Clock, PauseCircle, XCircle } from "lucide-react";

import { getAutomationsEngineStatus } from "../../services/api";
import { Badge } from "../ui/badge";
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

function LinhaDeJob({ job }) {
  const estado = ESTADOS[job.estado] || ESTADOS.nunca_correu;
  const { Icone } = estado;

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
    </div>
  );
}

export default function EngineStatusPanel() {
  const [dados, setDados] = useState(null);
  const [erro, setErro] = useState(false);
  const [aCarregar, setACarregar] = useState(true);

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
          <LinhaDeJob key={job.chave} job={job} />
        ))}
      </CardContent>
    </Card>
  );
}
