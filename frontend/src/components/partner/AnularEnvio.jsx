/**
 * «Anular envio»: o parceiro enganou-se no ficheiro e quer voltar a submeter.
 *
 * Só aparece nos ficheiros que o próprio enviou (`by === "eu"`); a parede é o
 * servidor, que também recusa o resto e explica quando já não dá (a equipa já
 * tratou o documento, o comprovativo já seguiu…). Pede confirmação antes.
 */
import React, { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, Undo2 } from "lucide-react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { queryKeys } from "@/lib/queryClient";
import { anularEnvio } from "@/services/partnerApi";
import { mensagemDeErro } from "@/utils/partnerPortal";

export default function AnularEnvio({ caseId, ficheiro, onErro }) {
  const queryClient = useQueryClient();
  const [aAnular, setAAnular] = useState(false);
  const nome = ficheiro.filename || "ficheiro";

  const anular = async () => {
    setAAnular(true);
    onErro?.("");
    try {
      await anularEnvio(caseId, ficheiro.id);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.partner.caso(caseId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.partner.casosAll() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.partner.painel() }),
      ]);
    } catch (e) {
      onErro?.(mensagemDeErro(e, "Não foi possível anular o envio."));
    } finally {
      setAAnular(false);
    }
  };

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={aAnular}
          aria-label={`Anular envio de ${nome}`}
          title="Anular envio"
          data-testid="anular-envio"
        >
          {aAnular ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Undo2 className="h-4 w-4" aria-hidden="true" />}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Anular o envio deste ficheiro?</AlertDialogTitle>
          <AlertDialogDescription>
            «{nome}» deixa de contar para o processo e sai da sua lista. Depois pode enviar o ficheiro correcto.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Manter</AlertDialogCancel>
          <AlertDialogAction onClick={anular}>Anular envio</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
