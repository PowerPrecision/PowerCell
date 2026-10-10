/**
 * Entrada do parceiro: email e palavra-passe. Sem registo público e sem
 * Google — a conta nasce de um convite da equipa.
 */
import React, { useState } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import PartnerTemaToggle from "@/components/partner/PartnerTemaToggle";
import PasswordInput from "@/components/shared/PasswordInput";
import { Label } from "@/components/ui/label";
import { ESTADO_A_CARREGAR, ESTADO_AUTENTICADO, usePartnerAuth } from "@/contexts/PartnerAuthContext";
import { mensagemDeErro } from "@/utils/partnerPortal";

export default function PartnerLoginPage() {
  const { estado, entrar } = usePartnerAuth();
  const local = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [erro, setErro] = useState("");
  const [aEnviar, setAEnviar] = useState(false);

  if (estado === ESTADO_A_CARREGAR) {
    return <div className="flex min-h-screen items-center justify-center text-muted-foreground" role="status">A carregar…</div>;
  }
  // Autenticado (já estava, ou acabou de entrar): vai para onde ia. Foi aqui
  // que se perdia o link profundo — o `entrar` muda o estado, o render
  // seguinte cai neste ramo ANTES de uma navegação explícita correr.
  if (estado === ESTADO_AUTENTICADO) return <Navigate to={local.state?.de || "/parceiro"} replace />;

  const submeter = async (e) => {
    e.preventDefault();
    if (aEnviar) return;
    setAEnviar(true);
    setErro("");
    try {
      await entrar(email.trim(), password);
    } catch (falha) {
      setErro(mensagemDeErro(falha, "Não foi possível iniciar sessão."));
      setPassword("");
    } finally {
      setAEnviar(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-background px-4">
      <PartnerTemaToggle className="absolute right-4 top-4" />
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Portal do Parceiro</CardTitle>
          <CardDescription>Inicie sessão para acompanhar os seus processos.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submeter} className="space-y-4" noValidate>
            <div className="space-y-2">
              <Label htmlFor="parceiro-email">Email</Label>
              <Input
                id="parceiro-email" type="email" autoComplete="username" required
                value={email} onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="parceiro-password">Palavra-passe</Label>
              <PasswordInput
                id="parceiro-password" autoComplete="current-password" required
                value={password} onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            {erro && (
              <Alert variant="destructive" role="alert">
                <AlertDescription>{erro}</AlertDescription>
              </Alert>
            )}
            <Button type="submit" className="w-full" disabled={aEnviar || !email || !password}>
              {aEnviar ? "A entrar…" : "Entrar"}
            </Button>
            <p className="text-center text-xs text-muted-foreground">
              Ainda não tem conta? Use o link do convite que lhe enviámos por email.
            </p>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
