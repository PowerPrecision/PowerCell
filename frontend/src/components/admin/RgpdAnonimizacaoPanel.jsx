/**
 * RgpdAnonimizacaoPanel — anonimização RGPD (Compliance › Anonimização).
 *
 * Anonimizar apaga dados pessoais e NÃO SE DESFAZ. Por isso:
 *  - o servidor exige a password ACTUAL de quem executa (`reauth_password`) e o cliente da API
 *    recusa o pedido sem ela; aqui o `ConfirmarComPasswordDialog` é o único caminho até lá;
 *  - a lista é a do ÂMBITO de quem pergunta (o servidor filtra por rede): um Admin/CEO só vê e
 *    anonimiza os processos da sua rede;
 *  - o lote é só do Master (operação global sobre a base), e tem sempre uma SIMULAÇÃO à frente —
 *    que não altera nada, não pede password e mostra quantos processos seriam tocados.
 *
 * @param {boolean} isMaster  mostra o lote (o servidor responde 403 a quem não é Master)
 */
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, FlaskConical, Loader2, ShieldAlert, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { anonymizeData, getGdprEligible, getGdprStatistics, runGdprBatch } from "../../services/api";
import { lerErroDeConfirmacao } from "../../utils/confirmarComPassword";
import { extractErrorMessage } from "../../utils/extractErrorMessage";
import { Button } from "../ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../ui/table";
import ConfirmarComPasswordDialog from "./ConfirmarComPasswordDialog";

const TAMANHO_DO_LOTE_POR_OMISSAO = 100;
const TAMANHO_MAXIMO_DO_LOTE = 500;
const LIMITE_DA_LISTA = 50;

const CHAVE = ["gdpr", "anonimizacao"];

const TEXTOS_DE_ERRO = {
  recusado: "Não foi possível anonimizar.",
  naoEncontrado: "O processo já não existe ou não pertence à sua rede.",
  erro: "Não foi possível anonimizar. Tente novamente.",
};
const lerErroDaAnonimizacao = (err) => lerErroDeConfirmacao(err, TEXTOS_DE_ERRO);

/** O tamanho do lote como número válido (1..máximo), ou `null`. Texto vazio/lixo → `null`. */
export function tamanhoDoLoteValido(texto) {
  // Só dígitos: `parseInt` aceitava «12abc» e «1e3» (→ 12 e 1) e o lote seria diferente do que se leu.
  const limpo = String(texto ?? "").trim();
  if (!/^\d+$/.test(limpo)) return null;
  const n = Number.parseInt(limpo, 10);
  return n >= 1 && n <= TAMANHO_MAXIMO_DO_LOTE ? n : null;
}

export default function RgpdAnonimizacaoPanel({ isMaster = false }) {
  const queryClient = useQueryClient();
  const [processoAAnonimizar, setProcessoAAnonimizar] = useState(null);
  const [loteAberto, setLoteAberto] = useState(false);
  const [tamanhoTexto, setTamanhoTexto] = useState(String(TAMANHO_DO_LOTE_POR_OMISSAO));
  const [simulacao, setSimulacao] = useState(null);
  const [aSimular, setASimular] = useState(false);

  const estatisticas = useQuery({
    queryKey: [...CHAVE, "estatisticas"],
    queryFn: async () => (await getGdprStatistics()).data?.data ?? null,
  });
  const elegiveis = useQuery({
    queryKey: [...CHAVE, "elegiveis"],
    queryFn: async () => {
      const res = await getGdprEligible({ limit: LIMITE_DA_LISTA });
      // `Array.isArray` e não `|| []`: ver FRONTEND_GUIDELINES § 27.38.
      return Array.isArray(res.data?.processes) ? res.data.processes : [];
    },
  });

  const tamanho = tamanhoDoLoteValido(tamanhoTexto);
  const stats = estatisticas.data;
  const lista = elegiveis.data ?? [];

  const atualizar = () => queryClient.invalidateQueries({ queryKey: CHAVE });

  const simularLote = async () => {
    if (!tamanho || aSimular) return;
    setASimular(true);
    try {
      const res = await runGdprBatch({ dry_run: true, batch_size: tamanho });
      setSimulacao({ ...res.data, batch_size: tamanho });
    } catch (err) {
      setSimulacao(null);
      toast.error(extractErrorMessage(err.response?.data?.detail, "Falha ao simular o lote."));
    } finally {
      setASimular(false);
    }
  };

  const confirmarProcesso = (password) =>
    anonymizeData({ process_id: processoAAnonimizar.id, dry_run: false, password });

  const confirmarLote = (password) => runGdprBatch({ dry_run: false, batch_size: tamanho, password });

  return (
    <div className="space-y-4" data-testid="rgpd-anonimizacao-panel">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldAlert className="h-5 w-5" aria-hidden="true" />
            Anonimização RGPD
          </CardTitle>
          <CardDescription>
            Remove os dados pessoais de processos antigos, depois do período de retenção. Não se desfaz.
            {!isMaster && " Vê e anonimiza apenas os processos da sua rede."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {estatisticas.isError ? (
            <p role="alert" className="text-sm text-destructive" data-testid="rgpd-estatisticas-erro">
              Não foi possível carregar as estatísticas.
            </p>
          ) : (
            <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4" data-testid="rgpd-estatisticas">
              <Estatistica rotulo="Processos" valor={stats?.total_processes} />
              <Estatistica rotulo="Já anonimizados" valor={stats?.anonymized_processes} />
              <Estatistica rotulo="Elegíveis" valor={stats?.eligible_for_anonymization} />
              <Estatistica
                rotulo="Retenção (dias)"
                valor={stats?.retention_period_days}
              />
            </dl>
          )}
        </CardContent>
      </Card>

      {isMaster && (
        <Card data-testid="rgpd-lote">
          <CardHeader>
            <CardTitle className="text-base">Anonimização em lote</CardTitle>
            <CardDescription>
              Operação global sobre a base de dados (só o Master). Faça sempre a simulação primeiro: não
              altera nada e diz quantos processos seriam anonimizados.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap items-end gap-3">
              <div className="space-y-1">
                <Label htmlFor="rgpd-tamanho-do-lote">Processos por lote</Label>
                <Input
                  id="rgpd-tamanho-do-lote"
                  type="number"
                  inputMode="numeric"
                  min={1}
                  max={TAMANHO_MAXIMO_DO_LOTE}
                  value={tamanhoTexto}
                  onChange={(e) => {
                    setTamanhoTexto(e.target.value);
                    setSimulacao(null);
                  }}
                  aria-invalid={tamanho === null || undefined}
                  className="w-32"
                  data-testid="rgpd-tamanho-do-lote"
                />
              </div>
              <Button
                type="button"
                variant="outline"
                onClick={simularLote}
                disabled={!tamanho || aSimular}
                className="gap-2"
                data-testid="rgpd-simular-lote"
              >
                {aSimular ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <FlaskConical className="h-4 w-4" aria-hidden="true" />}
                Simular lote
              </Button>
              <Button
                type="button"
                variant="destructive"
                onClick={() => setLoteAberto(true)}
                disabled={!tamanho || !simulacao}
                className="gap-2"
                data-testid="rgpd-anonimizar-lote"
              >
                <Trash2 className="h-4 w-4" aria-hidden="true" />
                Anonimizar em lote
              </Button>
            </div>
            {tamanho === null && (
              <p className="text-xs text-destructive" role="alert">
                Indique um número entre 1 e {TAMANHO_MAXIMO_DO_LOTE}.
              </p>
            )}
            {simulacao ? (
              <p className="text-sm text-muted-foreground" data-testid="rgpd-simulacao">
                Simulação: {simulacao.processed ?? 0} processo(s) seriam analisados e{" "}
                {simulacao.succeeded ?? 0} anonimizados. Nada foi alterado.
              </p>
            ) : (
              <p className="text-xs text-muted-foreground">
                O botão «Anonimizar em lote» só se activa depois de uma simulação com este tamanho.
              </p>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Processos elegíveis</CardTitle>
          <CardDescription>
            Passaram o período de retenção e ainda não foram anonimizados (primeiros {LIMITE_DA_LISTA}).
          </CardDescription>
        </CardHeader>
        <CardContent>
          {elegiveis.isLoading ? (
            <Loader2 className="h-5 w-5 animate-spin" aria-label="A carregar" />
          ) : elegiveis.isError ? (
            <p role="alert" className="text-sm text-destructive" data-testid="rgpd-elegiveis-erro">
              Não foi possível carregar os processos elegíveis.
            </p>
          ) : lista.length === 0 ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground" data-testid="rgpd-sem-elegiveis">
              <AlertTriangle className="h-4 w-4" aria-hidden="true" />
              Não há processos elegíveis para anonimização.
            </p>
          ) : (
            <Table data-testid="rgpd-elegiveis">
              <TableHeader>
                <TableRow>
                  <TableHead>Cliente</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead>Última actualização</TableHead>
                  <TableHead className="text-right">Acção</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {lista.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell>{p.client_name || "—"}</TableCell>
                    <TableCell>{p.status || "—"}</TableCell>
                    <TableCell>{String(p.updated_at || "").slice(0, 10) || "—"}</TableCell>
                    <TableCell className="text-right">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="gap-1.5 text-destructive hover:text-destructive"
                        onClick={() => setProcessoAAnonimizar(p)}
                        data-testid={`rgpd-anonimizar-${p.id}`}
                      >
                        <Trash2 className="h-4 w-4" aria-hidden="true" />
                        Anonimizar
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <ConfirmarComPasswordDialog
        open={Boolean(processoAAnonimizar)}
        onOpenChange={(aberto) => !aberto && setProcessoAAnonimizar(null)}
        titulo="Anonimizar processo"
        descricao={
          <>
            <p>
              Vai anonimizar os dados pessoais do processo de <strong>{processoAAnonimizar?.client_name || "—"}</strong>.
              Esta acção não se desfaz.
            </p>
            <p>Confirme com a sua password actual.</p>
          </>
        }
        onConfirmar={confirmarProcesso}
        onSucesso={() => {
          toast.success("Processo anonimizado.");
          setProcessoAAnonimizar(null);
          atualizar();
        }}
        rotuloConfirmar="Anonimizar"
        Icone={Trash2}
        testIdBase="anonimizar-processo"
        lerErro={lerErroDaAnonimizacao}
      />

      {isMaster && (
        <ConfirmarComPasswordDialog
          open={loteAberto}
          onOpenChange={setLoteAberto}
          titulo="Anonimizar em lote"
          descricao={
            <>
              <p>
                Vai anonimizar até <strong>{tamanho}</strong> processo(s) elegíveis de TODAS as redes. Esta
                acção não se desfaz.
              </p>
              <p>Confirme com a sua password actual.</p>
            </>
          }
          onConfirmar={confirmarLote}
          onSucesso={(resposta) => {
            toast.success(`Lote concluído: ${resposta?.succeeded ?? 0} processo(s) anonimizado(s).`);
            setSimulacao(null);
            atualizar();
          }}
          rotuloConfirmar="Anonimizar em lote"
          Icone={Trash2}
          testIdBase="anonimizar-lote"
          lerErro={lerErroDaAnonimizacao}
        />
      )}
    </div>
  );
}

function Estatistica({ rotulo, valor }) {
  return (
    <div className="rounded-md border p-3">
      <dt className="text-xs text-muted-foreground">{rotulo}</dt>
      <dd className="text-lg font-semibold">{valor ?? "—"}</dd>
    </div>
  );
}
