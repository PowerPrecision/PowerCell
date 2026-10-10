/**
 * OrigemFinanceiraCard — a quem se atribui o negócio (Bloco 4, ponto 7).
 *
 * Só a gestão (admin, CEO, diretor) o vê. O cartão NEM SE PEDE a quem não
 * pode: o pai decide por `podeGerir` (perfil efectivo) e o servidor é a
 * parede (403/404 com o motivo, mostrado tal e qual).
 *
 * Divulgação progressiva: o estado actual numa linha; o formulário só
 * abre em «Alterar», e a lista de candidatos só é pedida nessa altura.
 */
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Coins, Loader2 } from "lucide-react";
import { toast } from "sonner";

import {
  getCandidatosOrigemFinanceira,
  getOrigemFinanceira,
  setOrigemFinanceira,
} from "../../services/api";
import { queryKeys } from "../../lib/queryClient";
import { extractErrorMessage } from "../../utils/extractErrorMessage";
import {
  ROTULOS_DA_ORIGEM,
  TIPO_ANGARIACAO,
  TIPO_ORGANICA,
  candidatosValidos,
  montarPedido,
  resumoDaOrigem,
} from "../../utils/origemFinanceira";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Label } from "../ui/label";
import { RadioGroup, RadioGroupItem } from "../ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";

/**
 * @param {Object} props
 * @param {string} props.processId
 * @param {boolean} props.podeGerir - Perfil efectivo admin/CEO/diretor.
 */
export default function OrigemFinanceiraCard({ processId, podeGerir }) {
  const queryClient = useQueryClient();
  const [aEditar, setAEditar] = useState(false);
  const [tipo, setTipo] = useState("");
  const [angariadorId, setAngariadorId] = useState("");
  const [erro, setErro] = useState("");

  const origem = useQuery({
    queryKey: queryKeys.processes.origemFinanceira(processId),
    queryFn: async () => (await getOrigemFinanceira(processId)).data,
    enabled: Boolean(podeGerir && processId),
    retry: false,
  });

  const candidatos = useQuery({
    queryKey: queryKeys.processes.candidatosOrigemFinanceira(processId),
    queryFn: async () => (await getCandidatosOrigemFinanceira(processId)).data,
    enabled: Boolean(podeGerir && processId && aEditar),
    retry: false,
  });

  // Ao abrir o formulário parte-se do que está gravado.
  useEffect(() => {
    if (!aEditar) return;
    setTipo(origem.data?.tipo || "");
    setAngariadorId(origem.data?.angariador?.id || "");
    setErro("");
  }, [aEditar, origem.data]);

  const guardar = useMutation({
    mutationFn: async (corpo) => (await setOrigemFinanceira(processId, corpo)).data,
    onSuccess: (dados) => {
      queryClient.setQueryData(queryKeys.processes.origemFinanceira(processId), dados);
      toast.success("Origem financeira atualizada");
      setAEditar(false);
    },
    onError: (e) => {
      setErro(extractErrorMessage(e?.response?.data?.detail, "Não foi possível guardar a origem financeira"));
    },
  });

  if (!podeGerir) return null;

  const submeter = () => {
    const pedido = montarPedido(tipo, angariadorId);
    if (!pedido.ok) {
      setErro(pedido.erro);
      return;
    }
    setErro("");
    guardar.mutate(pedido.corpo);
  };

  const lista = candidatosValidos(candidatos.data);
  const erroDeLeitura = origem.isError
    ? extractErrorMessage(origem.error?.response?.data?.detail, "Não foi possível ler a origem financeira")
    : "";

  return (
    <Card data-testid="cartao-origem-financeira">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <Coins className="h-4 w-4 text-primary" aria-hidden="true" />
          Origem financeira
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {origem.isLoading && (
          <p className="text-sm text-muted-foreground flex items-center gap-2" role="status">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> A carregar…
          </p>
        )}

        {erroDeLeitura && (
          <p className="text-sm text-destructive" role="alert">{erroDeLeitura}</p>
        )}

        {origem.data && !aEditar && (
          <>
            <p className="text-sm font-medium" data-testid="resumo-origem-financeira">
              {resumoDaOrigem(origem.data)}
            </p>
            {origem.data.definida && origem.data.definido_por && (
              <p className="text-xs text-muted-foreground">
                Definida por {origem.data.definido_por}
              </p>
            )}
            <Button type="button" variant="outline" size="sm" onClick={() => setAEditar(true)}>
              {origem.data.definida ? "Alterar" : "Definir"}
            </Button>
            <p className="text-xs text-muted-foreground">
              Visível apenas à gestão. Base do cálculo de comissões.
            </p>
          </>
        )}

        {aEditar && (
          <div className="space-y-3">
            <RadioGroup
              value={tipo}
              onValueChange={(valor) => { setTipo(valor); setErro(""); }}
              aria-label="Origem do cliente"
            >
              {[TIPO_ORGANICA, TIPO_ANGARIACAO].map((valor) => (
                <div key={valor} className="flex items-center gap-2">
                  <RadioGroupItem value={valor} id={`origem-${valor}`} />
                  <Label htmlFor={`origem-${valor}`} className="text-sm font-normal">
                    {ROTULOS_DA_ORIGEM[valor]}
                  </Label>
                </div>
              ))}
            </RadioGroup>

            {tipo === TIPO_ANGARIACAO && (
              <div className="space-y-1.5">
                <Label htmlFor="angariador-origem" className="text-xs">Angariado por</Label>
                {candidatos.isLoading ? (
                  <p className="text-xs text-muted-foreground" role="status">A carregar utilizadores…</p>
                ) : (
                  <Select value={angariadorId} onValueChange={(valor) => { setAngariadorId(valor); setErro(""); }}>
                    <SelectTrigger id="angariador-origem" aria-label="Utilizador que angariou o cliente">
                      <SelectValue placeholder="Escolha um utilizador" />
                    </SelectTrigger>
                    <SelectContent>
                      {lista.map((c) => (
                        <SelectItem key={c.id} value={c.id}>{c.nome}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
                {candidatos.isError && (
                  <p className="text-xs text-destructive" role="alert">
                    Não foi possível carregar os utilizadores.
                  </p>
                )}
              </div>
            )}

            {erro && <p className="text-sm text-destructive" role="alert">{erro}</p>}

            <div className="flex gap-2">
              <Button type="button" size="sm" onClick={submeter} disabled={guardar.isPending}>
                {guardar.isPending ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : "Guardar"}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setAEditar(false)}
                disabled={guardar.isPending}
              >
                Cancelar
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
