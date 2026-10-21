/**
 * As acções de DECISÃO de uma lead de parceiro, na coluna ACÇÕES da lista de registos.
 *
 * A coluna ESTADO só mostra a badge; Validar, Rejeitar e Ver comprovativo vivem aqui, atrás de um menu
 * «⋯» discreto. Só aparece a quem decide (CEO, Diretor, Administrativo — perfil EFECTIVO) e enquanto a
 * lead estiver por validar. Nunca bloqueia nada: é o mesmo aviso, não um travão.
 */
import { CheckCircle2, FileSearch, Loader2, MoreHorizontal, XCircle } from "lucide-react";

import { Button } from "../ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { podeDecidir } from "../../utils/validacaoFinanceira";
import { useValidacaoFinanceira } from "../validacao/useValidacaoFinanceira";

export default function AccoesDaLead({ registo, nome, papelEfectivo, onDecidido }) {
  const decisao = useValidacaoFinanceira({ registo, tipo: "lead", onDecidido });

  if (!decisao.porValidar || !podeDecidir(papelEfectivo)) return null;

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-8 w-8 p-0"
            aria-label={`Acções de validação — ${nome || "lead"}`}
            data-testid={`accoes-validacao-${registo?.id}`}
          >
            {decisao.aDecidir || decisao.aAbrirComprovativo
              ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              : <MoreHorizontal className="h-4 w-4" aria-hidden="true" />}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={decisao.verComprovativo} data-testid="ver-comprovativo">
            <FileSearch className="mr-2 h-4 w-4" aria-hidden="true" />Ver comprovativo
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={decisao.validar} data-testid="validar-processo">
            <CheckCircle2 className="mr-2 h-4 w-4" aria-hidden="true" />Validar
          </DropdownMenuItem>
          {!decisao.rejeitado && (
            <DropdownMenuItem onSelect={decisao.pedirRejeicao} className="text-destructive focus:text-destructive" data-testid="rejeitar-processo">
              <XCircle className="mr-2 h-4 w-4" aria-hidden="true" />Rejeitar
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
      {decisao.dialogo}
    </>
  );
}
