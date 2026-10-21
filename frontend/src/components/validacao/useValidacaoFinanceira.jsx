/**
 * Decisão da validação financeira (validar / rejeitar / ver comprovativo) como hook.
 *
 * Quem desenha — o selo da ficha, o menu «⋯» da lista de registos, o rodapé da gaveta de detalhes —
 * escolhe ONDE aparece; a regra (motivo obrigatório, um pedido de cada vez, avisos) é esta, uma só vez.
 */
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { decidirValidacaoFinanceira, obterComprovativoDaValidacao } from "@/services/api";
import {
  ESTADO_REJEITADO,
  MOTIVO_MAXIMO,
  estadoDaValidacao,
  estaPorValidar,
  validarMotivo,
} from "@/utils/validacaoFinanceira";

const mensagem = (erro, recuo) => {
  const detail = erro?.response?.data?.detail;
  return typeof detail === "string" && detail.trim() ? detail : recuo;
};

/**
 * A lógica da decisão (validar / rejeitar / ver o comprovativo) sem decidir ONDE aparece:
 * o selo da ficha usa-a com botões, a lista de registos com um menu «⋯» e a gaveta de detalhes
 * da lead com um rodapé. Uma só implementação — três cópias da regra do motivo divergiam.
 */
export function useValidacaoFinanceira({ registo, tipo = "process", onDecidido }) {
  const [aDecidir, setADecidir] = useState(false);
  const [aRejeitar, setARejeitar] = useState(false);
  const [motivo, setMotivo] = useState("");
  const [erroDoMotivo, setErroDoMotivo] = useState("");
  const [aAbrirComprovativo, setAAbrirComprovativo] = useState(false);

  const estado = estadoDaValidacao(registo);
  const id = registo?.id;

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

  return {
    estado,
    porValidar: estaPorValidar(registo),
    rejeitado: estado === ESTADO_REJEITADO,
    aDecidir,
    aAbrirComprovativo,
    validar: () => decidir("validate"),
    pedirRejeicao: () => setARejeitar(true),
    verComprovativo,
    dialogo,
  };
}

