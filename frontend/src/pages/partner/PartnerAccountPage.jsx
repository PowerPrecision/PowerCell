/** A conta do parceiro: os dados e a mudança de palavra-passe. */
import React, { useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import PasswordInput from "@/components/shared/PasswordInput";
import { Label } from "@/components/ui/label";
import { usePartnerAuth } from "@/contexts/PartnerAuthContext";
import { mensagemDeErro } from "@/utils/partnerPortal";

export default function PartnerAccountPage() {
  const { partner, mudarPalavraPasse } = usePartnerAuth();
  const [actual, setActual] = useState("");
  const [nova, setNova] = useState("");
  const [confirmacao, setConfirmacao] = useState("");
  const [erro, setErro] = useState("");
  const [feito, setFeito] = useState(false);
  const [aEnviar, setAEnviar] = useState(false);

  const submeter = async (e) => {
    e.preventDefault();
    if (aEnviar) return;
    setErro("");
    setFeito(false);
    if (nova !== confirmacao) {
      setErro("As palavras-passe novas não coincidem.");
      return;
    }
    setAEnviar(true);
    try {
      await mudarPalavraPasse(actual, nova);
      setActual(""); setNova(""); setConfirmacao("");
      setFeito(true);
    } catch (falha) {
      setErro(mensagemDeErro(falha, "Não foi possível alterar a palavra-passe."));
    } finally {
      setAEnviar(false);
    }
  };

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <Card>
        <CardHeader><CardTitle>A minha conta</CardTitle></CardHeader>
        <CardContent className="space-y-1 text-sm">
          <p><span className="text-muted-foreground">Nome: </span>{partner?.name}</p>
          <p><span className="text-muted-foreground">Email: </span>{partner?.email}</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Alterar palavra-passe</CardTitle>
          <CardDescription>As outras sessões abertas terminam quando a alterar.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submeter} className="space-y-4" noValidate>
            <div className="space-y-2">
              <Label htmlFor="pp-actual">Palavra-passe actual</Label>
              <PasswordInput id="pp-actual" autoComplete="current-password" value={actual} onChange={(e) => setActual(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="pp-nova">Palavra-passe nova</Label>
              <PasswordInput id="pp-nova" autoComplete="new-password" value={nova} onChange={(e) => setNova(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="pp-confirmacao">Repetir palavra-passe nova</Label>
              <PasswordInput id="pp-confirmacao" autoComplete="new-password" value={confirmacao} onChange={(e) => setConfirmacao(e.target.value)} />
            </div>
            {erro && <Alert variant="destructive" role="alert"><AlertDescription>{erro}</AlertDescription></Alert>}
            {feito && <p role="status" className="text-sm text-muted-foreground">Palavra-passe alterada.</p>}
            <Button type="submit" disabled={aEnviar || !actual || !nova || !confirmacao}>
              {aEnviar ? "A alterar…" : "Alterar palavra-passe"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
