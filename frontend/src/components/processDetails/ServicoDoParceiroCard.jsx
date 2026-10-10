/**
 * ServicoDoParceiroCard — «Serviço pago pelo parceiro» (Portal do Parceiro).
 *
 * O parceiro paga-nos o tratamento do processo do cliente dele; aqui a
 * equipa interna marca que o serviço foi pago e deixa observações. Só se
 * desenha para processos COM parceiro, e o parceiro nunca o vê.
 *
 * Divulgação progressiva: a caixa à vista; as observações num texto que só
 * pede «Guardar» quando mudam. Quem pode ver mas não alterar (consultor,
 * intermediário) vê o estado sem controlos activos — o servidor é a parede.
 */
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { HandCoins, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { getServicoDoParceiro, setServicoDoParceiro } from "../../services/api";
import { queryKeys } from "../../lib/queryClient";
import { extractErrorMessage } from "../../utils/extractErrorMessage";
import {
  LIMITE_DE_OBSERVACOES,
  corpoDaCaixa,
  corpoDasObservacoes,
  normalizarServico,
  observacoesMudaram,
} from "../../utils/servicoDoParceiro";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Checkbox } from "../ui/checkbox";
import { Label } from "../ui/label";
import { Textarea } from "../ui/textarea";

/**
 * @param {Object} props
 * @param {string} props.processId
 * @param {boolean} props.podeVer - Perfil efectivo que vê o controlo.
 */
export default function ServicoDoParceiroCard({ processId, podeVer }) {
  const queryClient = useQueryClient();
  const chave = queryKeys.processes.servicoDoParceiro(processId);
  const [texto, setTexto] = useState("");
  const [erro, setErro] = useState("");

  const consulta = useQuery({
    queryKey: chave,
    queryFn: async () => normalizarServico((await getServicoDoParceiro(processId)).data),
    enabled: Boolean(podeVer && processId),
    retry: false,
  });

  // O texto parte do que está gravado; só se reescreve quando o servidor muda.
  useEffect(() => {
    if (consulta.data) setTexto(consulta.data.observacoes);
  }, [consulta.data]);

  const guardar = useMutation({
    mutationFn: async (corpo) => normalizarServico((await setServicoDoParceiro(processId, corpo)).data),
    onSuccess: (dados) => {
      queryClient.setQueryData(chave, dados);
      setErro("");
      toast.success("Controlo do serviço do parceiro atualizado");
    },
    onError: (e) => {
      setErro(extractErrorMessage(e?.response?.data?.detail, "Não foi possível guardar"));
    },
  });

  if (!podeVer) return null;
  // Sem parceiro: o servidor diz-o, e o cartão não se desenha.
  if (consulta.data && !consulta.data.aplicavel) return null;

  const dados = consulta.data;
  const editavel = Boolean(dados?.podeAlterar) && !guardar.isPending;
  const erroDeLeitura = consulta.isError
    ? extractErrorMessage(consulta.error?.response?.data?.detail, "Não foi possível ler o controlo do serviço")
    : "";

  return (
    <Card data-testid="cartao-servico-do-parceiro">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <HandCoins className="h-4 w-4 text-primary" aria-hidden="true" />
          Serviço do parceiro
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {consulta.isLoading && (
          <p className="text-sm text-muted-foreground flex items-center gap-2" role="status">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> A carregar…
          </p>
        )}
        {erroDeLeitura && <p className="text-sm text-destructive" role="alert">{erroDeLeitura}</p>}

        {dados && (
          <>
            {dados.parceiro?.nome && (
              <p className="text-xs text-muted-foreground">Parceiro: {dados.parceiro.nome}</p>
            )}
            <div className="flex items-center gap-2">
              <Checkbox
                id={`servico-pago-${processId}`}
                checked={dados.pago}
                disabled={!editavel}
                onCheckedChange={(v) => guardar.mutate(corpoDaCaixa(v === true))}
              />
              <Label htmlFor={`servico-pago-${processId}`} className="text-sm font-medium">
                Serviço pago pelo parceiro
              </Label>
            </div>
            {dados.pago && dados.pagoEm && (
              <p className="text-xs text-muted-foreground">
                Marcado em {new Date(dados.pagoEm).toLocaleDateString("pt-PT")}
              </p>
            )}

            <div className="space-y-1">
              <Label htmlFor={`servico-obs-${processId}`} className="text-xs">Observações</Label>
              <Textarea
                id={`servico-obs-${processId}`}
                rows={3}
                maxLength={LIMITE_DE_OBSERVACOES}
                value={texto}
                disabled={!editavel}
                onChange={(e) => setTexto(e.target.value)}
              />
            </div>
            {editavel && observacoesMudaram(texto, dados.observacoes) && (
              <Button type="button" size="sm" onClick={() => guardar.mutate(corpoDasObservacoes(texto))}>
                Guardar observações
              </Button>
            )}
            {erro && <p className="text-sm text-destructive" role="alert">{erro}</p>}
            <p className="text-xs text-muted-foreground">
              Visível apenas à equipa interna. O parceiro não vê este cartão.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
