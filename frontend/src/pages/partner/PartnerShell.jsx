/**
 * A moldura da área reservada do parceiro.
 *
 * Guarda a porta: enquanto se confirma o token (`a_carregar`) não mostra
 * nem o login nem a área reservada; sem sessão, manda para o login
 * lembrando para onde ia.
 */
import React from "react";
import { Link, NavLink, Navigate, Outlet, useLocation } from "react-router-dom";
import { LogOut, PlusCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  ESTADO_A_CARREGAR,
  ESTADO_AUTENTICADO,
  usePartnerAuth,
} from "@/contexts/PartnerAuthContext";

const ligacao = ({ isActive }) =>
  cn(
    "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
    isActive ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground"
  );

export default function PartnerShell() {
  const { estado, partner, sair } = usePartnerAuth();
  const local = useLocation();

  if (estado === ESTADO_A_CARREGAR) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background text-muted-foreground" role="status">
        A carregar…
      </div>
    );
  }
  if (estado !== ESTADO_AUTENTICADO) {
    return <Navigate to="/parceiro/entrar" replace state={{ de: local.pathname }} />;
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex flex-wrap items-center gap-4">
            <Link to="/parceiro" className="text-base font-semibold">Portal do Parceiro</Link>
            <nav aria-label="Navegação principal" className="flex items-center gap-1">
              <NavLink to="/parceiro" end className={ligacao}>Painel</NavLink>
              <NavLink to="/parceiro/conta" className={ligacao}>A minha conta</NavLink>
            </nav>
          </div>
          <div className="flex items-center gap-2">
            <span className="hidden text-sm text-muted-foreground sm:inline" data-testid="nome-do-parceiro">
              {partner?.name}
            </span>
            <Button asChild size="sm">
              <Link to="/parceiro/novo-lead"><PlusCircle className="mr-2 h-4 w-4" aria-hidden="true" />Novo lead</Link>
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={sair} aria-label="Terminar sessão">
              <LogOut className="h-4 w-4" aria-hidden="true" />
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
