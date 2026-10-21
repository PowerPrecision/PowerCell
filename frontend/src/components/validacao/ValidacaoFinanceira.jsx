/**
 * Validação financeira: o selo vermelho «⚠️ Processo Não Validado» e, para
 * CEO, Diretor e Administrativo, os botões «Validar Processo» e «Rejeitar».
 *
 * NUNCA bloqueia nada: é só um aviso. A equipa (Index, consultores) trabalha
 * a documentação e avança o processo por todas as fases mesmo sem validação.
 *
 * Serve a ficha do processo (`tipo="process"`) e a lead na lista de registos
 * (`tipo="lead"`, em modo compacto).
 */
import React from "react";
import { AlertTriangle, CheckCircle2, FileSearch, Loader2, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  ESTADO_VALIDADO,
  TEXTO_DO_SELO,
  motivoDaRejeicao,
  podeDecidir,
} from "@/utils/validacaoFinanceira";

import { useValidacaoFinanceira } from "./useValidacaoFinanceira";

export default function ValidacaoFinanceira({
  registo,
  tipo = "process",
  papelEfectivo,
  onDecidido,
  compacto = false,
  // «tudo» (a ficha e o modo compacto de sempre) ou «selo»: só a badge do estado, sem botões
  // (a coluna ESTADO da lista de registos — as acções vivem na coluna ACÇÕES).
  parte = "tudo",
}) {
  const {
    estado, porValidar, rejeitado, aDecidir, aAbrirComprovativo,
    validar, pedirRejeicao, verComprovativo, dialogo,
  } = useValidacaoFinanceira({ registo, tipo, onDecidido });

  if (estado === null) return null; // não passa por validação financeira (não veio de um parceiro)

  const decide = podeDecidir(papelEfectivo);

  // Já validado: um selo discreto, sem alarme.
  if (!porValidar) {
    return (
      <Badge variant="secondary" className="gap-1" data-testid="validacao-validada">
        <CheckCircle2 className="h-3 w-3" aria-hidden="true" />Validado
      </Badge>
    );
  }

  if (parte === "selo") {
    return rejeitado ? (
      <Badge variant="destructive" className="gap-1" data-testid="validacao-rejeitada">
        <XCircle className="h-3 w-3" aria-hidden="true" />Rejeitado
      </Badge>
    ) : (
      <Badge variant="destructive" className="gap-1" data-testid="validacao-nao-validado">
        <AlertTriangle className="h-3 w-3" aria-hidden="true" />Não validado
      </Badge>
    );
  }

  const acoes = decide && (
    <div className="flex flex-wrap items-center gap-2">
      <Button type="button" size="sm" onClick={validar} disabled={aDecidir} data-testid="validar-processo">
        {aDecidir ? <Loader2 className="mr-1 h-4 w-4 animate-spin" aria-hidden="true" /> : <CheckCircle2 className="mr-1 h-4 w-4" aria-hidden="true" />}
        Validar Processo
      </Button>
      {!rejeitado && (
        <Button type="button" size="sm" variant="destructive" onClick={pedirRejeicao} disabled={aDecidir} data-testid="rejeitar-processo">
          <XCircle className="mr-1 h-4 w-4" aria-hidden="true" />Rejeitar
        </Button>
      )}
      <Button type="button" size="sm" variant="outline" onClick={verComprovativo} disabled={aAbrirComprovativo} data-testid="ver-comprovativo">
        {aAbrirComprovativo ? <Loader2 className="mr-1 h-4 w-4 animate-spin" aria-hidden="true" /> : <FileSearch className="mr-1 h-4 w-4" aria-hidden="true" />}
        Ver comprovativo
      </Button>
    </div>
  );

  if (compacto) {
    return (
      <div className="flex flex-wrap items-center gap-2" data-testid="validacao-nao-validado">
        <Badge variant="destructive" className="gap-1">
          <AlertTriangle className="h-3 w-3" aria-hidden="true" />Não validado
        </Badge>
        {acoes}
        {dialogo}
      </div>
    );
  }

  return (
    <div
      role="alert"
      className="space-y-2 rounded-lg border-2 border-destructive bg-destructive/10 p-3 text-destructive"
      data-testid="validacao-nao-validado"
    >
      <p className="flex items-center gap-2 text-sm font-bold">
        <AlertTriangle className="h-5 w-5 shrink-0" aria-hidden="true" />
        <span data-testid="selo-nao-validado">{TEXTO_DO_SELO}</span>
      </p>
      <p className="text-sm text-foreground">
        {rejeitado
          ? `A validação financeira foi rejeitada${motivoDaRejeicao(registo) ? `: ${motivoDaRejeicao(registo)}` : "."} `
          : "Aguarda validação financeira. "}
        Continua a poder trabalhar o processo — este aviso só indica que a viabilidade ainda não está confirmada.
      </p>
      {acoes}
      {dialogo}
    </div>
  );
}

export { ESTADO_VALIDADO };
