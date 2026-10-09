/**
 * PartilhaCard — quem mais vê este processo, e como retirar o acesso (D-25).
 *
 * A partilha nasce da atribuição (Via Rápida, sem aprovação) e NÃO se desfaz
 * ao tirar a atribuição — o parceiro mantém o que produziu. Sem este cartão a
 * abertura era irreversível sem acesso à base de dados.
 *
 * Só aparece quando há parceiros: um cartão vazio em todos os processos seria
 * ruído. Quem pode revogar vem por `podeRevogar` (perfil efectivo); a decisão
 * final é do servidor, e a mensagem dele é mostrada tal e qual.
 */
import { useState } from "react";
import { Handshake, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { revokeProcessPartner } from "../../services/api";
import { extractErrorMessage } from "../../utils/extractErrorMessage";
import { parceirosDoProcesso, sePodeRevogar } from "../../utils/partilhaProcesso";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "../ui/alert-dialog";

/**
 * @param {Object} props
 * @param {object} props.process
 * @param {boolean} props.podeRevogar - Perfil efectivo admin/CEO/diretor.
 * @param {(restantes: Array) => void} [props.onRevoked] - Recebe `partner_companies` actualizado.
 */
export default function PartilhaCard({ process, podeRevogar, onRevoked }) {
  const parceiros = parceirosDoProcesso(process);
  const [alvo, setAlvo] = useState(null);
  const [aRevogar, setARevogar] = useState(false);

  if (parceiros.length === 0) return null;

  const confirmar = async () => {
    if (!alvo) return;
    setARevogar(true);
    try {
      const res = await revokeProcessPartner(process.id, alvo.id);
      toast.success(`Partilha com ${alvo.nome} revogada`);
      if (onRevoked) onRevoked(res?.data?.parceiros_restantes ?? []);
      setAlvo(null);
    } catch (error) {
      toast.error(
        extractErrorMessage(error?.response?.data?.detail, "Não foi possível revogar a partilha"),
      );
    } finally {
      setARevogar(false);
    }
  };

  return (
    <Card data-testid="cartao-partilha">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <Handshake className="h-4 w-4 text-primary" aria-hidden="true" />
          Partilhado com
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <ul className="divide-y rounded-md border text-sm">
          {parceiros.map((parceiro) => (
            <li key={parceiro.id || parceiro.nome} className="flex items-center justify-between gap-2 px-3 py-2">
              <span className="min-w-0 truncate font-medium">{parceiro.nome}</span>
              {podeRevogar && sePodeRevogar(parceiro) && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  aria-label={`Revogar partilha com ${parceiro.nome}`}
                  onClick={() => setAlvo(parceiro)}
                >
                  Revogar
                </Button>
              )}
            </li>
          ))}
        </ul>
        <p className="text-xs text-muted-foreground">
          Tirar uma atribuição não revoga a partilha: o acesso só se retira aqui.
        </p>
      </CardContent>

      <AlertDialog open={Boolean(alvo)} onOpenChange={(aberto) => { if (!aberto && !aRevogar) setAlvo(null); }}>
        <AlertDialogContent data-testid="dialogo-revogar-partilha">
          <AlertDialogHeader>
            <AlertDialogTitle>Revogar a partilha com {alvo?.nome}?</AlertDialogTitle>
            <AlertDialogDescription>
              {alvo?.nome} deixa de ver este processo. Mantém o que já produziu (histórico e
              documentos), e pode voltar a ter acesso se alguém dessa empresa for atribuído de novo.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={aRevogar}>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              disabled={aRevogar}
              onClick={(evento) => {
                // O Radix fecha o diálogo no clique; só fecha depois da resposta.
                evento.preventDefault();
                confirmar();
              }}
            >
              {aRevogar ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : "Revogar partilha"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
