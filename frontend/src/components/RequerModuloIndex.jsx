import React from "react";
import { Navigate } from "react-router-dom";

import { useAuth } from "../contexts/AuthContext";
import { redeTemIndex } from "../utils/capacidadesDaRede";

/**
 * A supervisão do Index só existe numa rede com Index (caso Domus, Out 2026): sem ele o menu já não a mostra e o
 * link directo (favorito, histórico) vai ao painel em vez de abrir uma fila que nunca recebe processos.
 * Fica DENTRO do `ProtectedRoute` — o perfil decide primeiro, a rede depois.
 */
export default function RequerModuloIndex({ children }) {
  const { user } = useAuth();
  if (!redeTemIndex(user)) {
    return <Navigate to="/staff" replace />;
  }
  return children;
}
