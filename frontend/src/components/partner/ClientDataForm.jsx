/**
 * «Dados do cliente» no Portal do Parceiro — a MESMA estrutura do registo
 * público, com a adição de um 2.º titular.
 *
 * O esquema (campos, etiquetas, opções, obrigatoriedade) vem do servidor, que
 * o deriva do `form_config` do administrador: o ecrã não conhece nenhum campo.
 * É o `DynamicFormField` do registo público que desenha cada um, e as chaves
 * do pedido são as `field_key` do formulário público.
 *
 * O 2.º titular liga-se com um interruptor (`compra_tipo = outra_pessoa` na
 * ficha). Desligá-lo e guardar APAGA os dados do 2.º titular — e o ecrã di-lo
 * antes, em vez de o fazer em silêncio.
 */
import React, { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { UserPlus } from "lucide-react";

import DynamicFormField from "@/components/DynamicFormField";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { queryKeys } from "@/lib/queryClient";
import { guardarFormularioDoCliente, obterFormularioDoCliente } from "@/services/partnerApi";
import { mensagemDeErro } from "@/utils/partnerPortal";
import { camposAlterados, passoDoSegundoTitular, passosDoTitular, segundoTitularLigado } from "@/utils/partnerClientForm";

const CHAVE_DO_SEGUNDO_TITULAR = "compra_tipo";
const VALOR_LIGADO = "outra_pessoa";
const VALOR_DESLIGADO = "individual";

export default function ClientDataForm({ caseId }) {
  const queryClient = useQueryClient();
  const consulta = useQuery({
    queryKey: queryKeys.partner.formulario(caseId),
    queryFn: () => obterFormularioDoCliente(caseId),
  });

  const inicial = useMemo(() => consulta.data?.values ?? {}, [consulta.data]);
  const [valores, setValores] = useState({});
  const [guardado, setGuardado] = useState(false);

  // Hidrata quando os dados chegam (e depois de cada gravação).
  useEffect(() => {
    if (consulta.data) setValores({ ...consulta.data.values });
  }, [consulta.data]);

  const guardar = useMutation({
    mutationFn: (alterados) => guardarFormularioDoCliente(caseId, alterados),
    onSuccess: async () => {
      setGuardado(true);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.partner.formulario(caseId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.partner.caso(caseId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.partner.casosAll() }),
      ]);
    },
  });

  if (consulta.isPending) return <Skeleton className="h-40" />;
  if (consulta.isError) {
    return <p role="alert" className="text-sm text-destructive">{mensagemDeErro(consulta.error, "Não foi possível carregar os dados do cliente.")}</p>;
  }

  const form = consulta.data;
  const editavel = form.editavel === true;
  const titular = passosDoTitular(form.passos);
  const segundo = passoDoSegundoTitular(form.passos);
  const ligado = segundoTitularLigado(valores);
  const tinhaSegundo = segundoTitularLigado(inicial);

  const mudar = (chave, valor) => {
    setGuardado(false);
    guardar.reset();
    setValores((v) => ({ ...v, [chave]: valor }));
  };

  // Desligar só é uma alteração se o 2.º titular JÁ existia na ficha; se foi
  // ligado e desligado antes de guardar, repõe-se o valor de origem (não se
  // escreve «individual» por cima de um campo que nunca foi preenchido).
  const alterarSegundoTitular = (activo) =>
    mudar(
      CHAVE_DO_SEGUNDO_TITULAR,
      activo ? VALOR_LIGADO : tinhaSegundo ? VALOR_DESLIGADO : inicial[CHAVE_DO_SEGUNDO_TITULAR]
    );

  const aSubmeter = (e) => {
    e.preventDefault();
    const alterados = camposAlterados(inicial, valores, form.passos, { ligado });
    if (Object.keys(alterados).length === 0) {
      setGuardado(true);
      return;
    }
    guardar.mutate(alterados);
  };

  return (
    <form onSubmit={aSubmeter} className="space-y-6" aria-label="Dados do cliente" noValidate>
      {!editavel && (
        <p role="status" className="rounded-md border border-border bg-secondary p-3 text-sm text-muted-foreground">
          Estes dados já não podem ser editados por si.
        </p>
      )}

      {titular.map((passo) => (
        <fieldset key={passo.step} className="space-y-4" disabled={!editavel}>
          <legend className="text-base font-semibold">{passo.label}</legend>
          <div className="grid gap-4 md:grid-cols-2">
            {passo.fields.map((campo) => (
              <DynamicFormField
                key={campo.field_key}
                field={campo}
                value={valores[campo.field_key]}
                onChange={mudar}
                disabled={!editavel}
              />
            ))}
          </div>
        </fieldset>
      ))}

      {segundo && (
        <fieldset className="space-y-4" disabled={!editavel}>
          <legend className="text-base font-semibold">{segundo.label}</legend>
          <div className="flex items-center gap-3">
            <Switch
              id="segundo-titular"
              checked={ligado}
              onCheckedChange={alterarSegundoTitular}
              disabled={!editavel}
              aria-label="Adicionar 2.º titular"
            />
            <label htmlFor="segundo-titular" className="flex items-center gap-2 text-sm font-medium">
              <UserPlus className="h-4 w-4" aria-hidden="true" />Adicionar 2.º titular
            </label>
          </div>
          {tinhaSegundo && !ligado && (
            <p role="status" className="text-sm text-destructive">
              Ao guardar, os dados do 2.º titular serão apagados.
            </p>
          )}
          {ligado && (
            <div className="grid gap-4 md:grid-cols-2" data-testid="campos-do-segundo-titular">
              {segundo.fields.map((campo) => (
                <DynamicFormField
                  key={campo.field_key}
                  field={campo}
                  value={valores[campo.field_key]}
                  onChange={mudar}
                  disabled={!editavel}
                />
              ))}
            </div>
          )}
        </fieldset>
      )}

      {guardar.isError && (
        <p role="alert" className="text-sm text-destructive">{mensagemDeErro(guardar.error, "Não foi possível guardar.")}</p>
      )}
      {guardado && !guardar.isError && !guardar.isPending && (
        <p role="status" className="text-sm text-muted-foreground">Dados guardados.</p>
      )}

      {editavel && (
        <Button type="submit" disabled={guardar.isPending}>
          {guardar.isPending ? "A guardar…" : "Guardar dados"}
        </Button>
      )}
    </form>
  );
}
