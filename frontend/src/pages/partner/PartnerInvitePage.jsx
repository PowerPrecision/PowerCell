/**
 * Activação da conta a partir do link do convite: o parceiro define a
 * palavra-passe e aceita os termos. O link é de uso único e expira — um
 * link inválido diz-se com clareza e aponta para pedir um novo.
 */
import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Navigate, useNavigate, useParams } from "react-router-dom";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ESTADO_AUTENTICADO, usePartnerAuth } from "@/contexts/PartnerAuthContext";
import { lerConvite } from "@/services/partnerApi";
import { mensagemDeErro } from "@/utils/partnerPortal";

export default function PartnerInvitePage() {
  const { token } = useParams();
  const { estado, activarConvite } = usePartnerAuth();
  const navegar = useNavigate();
  const [password, setPassword] = useState("");
  const [confirmacao, setConfirmacao] = useState("");
  const [termos, setTermos] = useState(false);
  const [erro, setErro] = useState("");
  const [aEnviar, setAEnviar] = useState(false);

  const convite = useQuery({
    queryKey: ["partner", "convite", token],
    queryFn: () => lerConvite(token),
    retry: false,
    staleTime: 0,
  });

  if (estado === ESTADO_AUTENTICADO) return <Navigate to="/parceiro" replace />;

  const submeter = async (e) => {
    e.preventDefault();
    if (aEnviar) return;
    setErro("");
    if (password !== confirmacao) {
      setErro("As palavras-passe não coincidem.");
      return;
    }
    setAEnviar(true);
    try {
      await activarConvite({ token, password, accept_terms: termos });
      navegar("/parceiro", { replace: true });
    } catch (falha) {
      setErro(mensagemDeErro(falha, "Não foi possível activar a conta."));
    } finally {
      setAEnviar(false);
    }
  };

  let corpo;
  if (convite.isPending) {
    corpo = <p className="text-sm text-muted-foreground" role="status">A verificar o convite…</p>;
  } else if (convite.isError) {
    corpo = (
      <Alert variant="destructive" role="alert">
        <AlertDescription>
          Este convite é inválido ou expirou. Peça à equipa que lhe envie um novo.
        </AlertDescription>
      </Alert>
    );
  } else {
    const c = convite.data;
    corpo = (
      <form onSubmit={submeter} className="space-y-4" noValidate>
        <p className="text-sm">
          Olá <strong>{c.name}</strong>. A sua conta ({c.email}) fica activa quando definir uma palavra-passe.
        </p>
        <div className="space-y-2">
          <Label htmlFor="convite-password">Palavra-passe</Label>
          <Input id="convite-password" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          <p className="text-xs text-muted-foreground">Mínimo 8 caracteres, com maiúscula, minúscula, número e símbolo.</p>
        </div>
        <div className="space-y-2">
          <Label htmlFor="convite-confirmacao">Repetir palavra-passe</Label>
          <Input id="convite-confirmacao" type="password" autoComplete="new-password" value={confirmacao} onChange={(e) => setConfirmacao(e.target.value)} />
        </div>
        {c.first_access && (
          <div className="flex items-start gap-2">
            <Checkbox id="convite-termos" checked={termos} onCheckedChange={(v) => setTermos(v === true)} />
            <Label htmlFor="convite-termos" className="text-sm font-normal leading-snug">
              Aceito os termos de utilização do Portal do Parceiro (versão {c.terms_version}).
            </Label>
          </div>
        )}
        {erro && (
          <Alert variant="destructive" role="alert">
            <AlertDescription>{erro}</AlertDescription>
          </Alert>
        )}
        <Button type="submit" className="w-full" disabled={aEnviar || !password || !confirmacao || (c.first_access && !termos)}>
          {aEnviar ? "A activar…" : "Activar conta"}
        </Button>
      </form>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Bem-vindo ao Portal do Parceiro</CardTitle>
          <CardDescription>Defina a sua palavra-passe para começar.</CardDescription>
        </CardHeader>
        <CardContent>{corpo}</CardContent>
      </Card>
    </div>
  );
}
