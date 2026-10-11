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
import React, { useState } from "react";
import { AlertTriangle, CheckCircle2, FileSearch, Loader2, XCircle } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { decidirValidacaoFinanceira, obterComprovativoDaValidacao } from "@/services/api";
import {
  ESTADO_REJEITADO,
  ESTADO_VALIDADO,
  MOTIVO_MAXIMO,
  TEXTO_DO_SELO,
  estadoDaValidacao,
  estaPorValidar,
  motivoDaRejeicao,
  podeDecidir,
  validarMotivo,
} from "@/utils/validacaoFinanceira";

const mensagem = (erro, recuo) => {
  const detail = erro?.response?.data?.detail;
  return typeof detail === "string" && detail.trim() ? detail : recuo;
};

export default function ValidacaoFinanceira({
  registo,
  tipo = "process",
  papelEfectivo,
  onDecidido,
  compacto = false,
}) {
  const [aDecidir, setADecidir] = useState(false);
  const [aRejeitar, setARejeitar] = useState(false);
  const [motivo, setMotivo] = useState("");
  const [erroDoMotivo, setErroDoMotivo] = useState("");
  const [aAbrirComprovativo, setAAbrirComprovativo] = useState(false);

  const estado = estadoDaValidacao(registo);
  if (estado === null) return null; // não passa por validação financeira (não veio de um parceiro)

  const id = registo?.id;
  const decide = podeDecidir(papelEfectivo);
  const porValidar = estaPorValidar(registo);

  const decidir = async (decisao, razao) => {
    if (aDecidir) return;
    setADecidir(true);
    try {
      const r = await decidirValidacaoFinanceira(tipo, id, {
        decision: decisao,
        ...(razao ? { reason: razao } : {}),
      });
      toast.success(decisao === "validate" ? "Processo validado." : "Rejeitado — o parceiro foi avisado.");
      setARejeitar(false);
      setMotivo("");
      await onDecidido?.(r);
    } catch (erro) {
      toast.error(mensagem(erro, "Não foi possível registar a decisão."));
    } finally {
      setADecidir(false);
    }
  };

  const confirmarRejeicao = () => {
    const erro = validarMotivo(motivo);
    setErroDoMotivo(erro);
    if (!erro) decidir("reject", motivo.trim());
  };

  const verComprovativo = async () => {
    setAAbrirComprovativo(true);
    try {
      const r = await obterComprovativoDaValidacao(tipo, id);
      window.open(r.url, "_blank", "noopener,noreferrer");
    } catch (erro) {
      toast.error(mensagem(erro, "Não foi possível abrir o comprovativo."));
    } finally {
      setAAbrirComprovativo(false);
    }
  };

  // Já validado: um selo discreto, sem alarme.
  if (!porValidar) {
    return (
      <Badge variant="secondary" className="gap-1" data-testid="validacao-validada">
        <CheckCircle2 className="h-3 w-3" aria-hidden="true" />Validado
      </Badge>
    );
  }

  const rejeitado = estado === ESTADO_REJEITADO;
  const acoes = decide && (
    <div className="flex flex-wrap items-center gap-2">
      <Button type="button" size="sm" onClick={() => decidir("validate")} disabled={aDecidir} data-testid="validar-processo">
        {aDecidir ? <Loader2 className="mr-1 h-4 w-4 animate-spin" aria-hidden="true" /> : <CheckCircle2 className="mr-1 h-4 w-4" aria-hidden="true" />}
        Validar Processo
      </Button>
      {!rejeitado && (
        <Button type="button" size="sm" variant="destructive" onClick={() => setARejeitar(true)} disabled={aDecidir} data-testid="rejeitar-processo">
          <XCircle className="mr-1 h-4 w-4" aria-hidden="true" />Rejeitar
        </Button>
      )}
      <Button type="button" size="sm" variant="outline" onClick={verComprovativo} disabled={aAbrirComprovativo} data-testid="ver-comprovativo">
        {aAbrirComprovativo ? <Loader2 className="mr-1 h-4 w-4 animate-spin" aria-hidden="true" /> : <FileSearch className="mr-1 h-4 w-4" aria-hidden="true" />}
        Ver comprovativo
      </Button>
    </div>
  );

  const dialogo = (
    <Dialog open={aRejeitar} onOpenChange={setARejeitar}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Rejeitar validação financeira</DialogTitle>
          <DialogDescription>
            {tipo === "lead"
              ? "A lead é devolvida ao parceiro e sai da vista da equipa."
              : "O processo é fechado e sai da fila do Index. Pode ser reaberto mais tarde."}
            {" "}O parceiro recebe o motivo por email.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="motivo-rejeicao">Motivo</Label>
          <Textarea
            id="motivo-rejeicao"
            value={motivo}
            maxLength={MOTIVO_MAXIMO}
            onChange={(e) => { setMotivo(e.target.value); setErroDoMotivo(""); }}
            placeholder="Ex.: o comprovativo está ilegível ou não corresponde ao serviço."
            aria-invalid={Boolean(erroDoMotivo)}
          />
          {erroDoMotivo && <p role="alert" className="text-sm text-destructive">{erroDoMotivo}</p>}
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => setARejeitar(false)} disabled={aDecidir}>Cancelar</Button>
          <Button type="button" variant="destructive" onClick={confirmarRejeicao} disabled={aDecidir} data-testid="confirmar-rejeicao">
            {aDecidir ? "A rejeitar…" : "Rejeitar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
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
