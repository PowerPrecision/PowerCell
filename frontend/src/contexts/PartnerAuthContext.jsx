/**
 * A sessão do Portal do Parceiro.
 *
 * É um contexto à parte do `AuthContext` do staff, e não uma extensão dele:
 * o parceiro tem outro token, outro armazenamento (`utils/partnerSession`),
 * outro cliente HTTP e NENHUM dos conceitos do CRM (empresa activa, perfil
 * activo, UCR). Misturá-los era a forma mais curta de um dia o parceiro
 * herdar um cabeçalho de empresa do staff.
 *
 * ESTADOS: `a_carregar` (há token, ainda não sabemos se vale) → `autenticado`
 * ou `anonimo`. Um estado de carregamento nunca cai no ramo de um estado de
 * dados (a regra do `WebmailCompanyTabs`): enquanto se confirma o token não
 * se mostra nem o login nem a área reservada.
 *
 * A sessão MORRE por três vias, todas com o mesmo efeito (limpar o token,
 * a cache `partner` e voltar ao login): `sair()`, um 401 fora da entrada
 * (evento do cliente HTTP) e um `/me` que falha no arranque.
 */
import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { queryKeys } from "@/lib/queryClient";
import * as api from "@/services/partnerApi";
import {
  EVENTO_SESSAO_EXPIRADA,
  guardarSessao,
  lerToken,
  limparSessao,
} from "@/utils/partnerSession";

export const ESTADO_A_CARREGAR = "a_carregar";
export const ESTADO_AUTENTICADO = "autenticado";
export const ESTADO_ANONIMO = "anonimo";

const PartnerAuthContext = createContext(null);

export function PartnerAuthProvider({ children }) {
  const queryClient = useQueryClient();
  const [partner, setPartner] = useState(null);
  const [estado, setEstado] = useState(() => (lerToken() ? ESTADO_A_CARREGAR : ESTADO_ANONIMO));

  const terminar = useCallback(() => {
    limparSessao();
    setPartner(null);
    setEstado(ESTADO_ANONIMO);
    // Nada do parceiro anterior fica em cache para o próximo.
    queryClient.removeQueries({ queryKey: queryKeys.partner.all });
  }, [queryClient]);

  // Arranque: há token → confirma-o com o servidor (que relê o estado).
  useEffect(() => {
    if (estado !== ESTADO_A_CARREGAR) return undefined;
    let activo = true;
    api
      .obterPerfil()
      .then((perfil) => {
        if (!activo) return;
        setPartner(perfil);
        setEstado(ESTADO_AUTENTICADO);
      })
      .catch(() => {
        if (activo) terminar();
      });
    return () => {
      activo = false;
    };
    // Só no arranque: o estado muda a partir de dentro.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 401 fora da entrada (expirou, suspenderam-no, mudaram-lhe a password).
  useEffect(() => {
    const aoExpirar = () => terminar();
    window.addEventListener(EVENTO_SESSAO_EXPIRADA, aoExpirar);
    return () => window.removeEventListener(EVENTO_SESSAO_EXPIRADA, aoExpirar);
  }, [terminar]);

  const iniciarSessao = useCallback((sessao) => {
    guardarSessao(sessao.access_token, sessao.expires_in);
    setPartner(sessao.partner);
    setEstado(ESTADO_AUTENTICADO);
    return sessao.partner;
  }, []);

  const valor = useMemo(
    () => ({
      partner,
      estado,
      autenticado: estado === ESTADO_AUTENTICADO,
      entrar: async (email, password) => iniciarSessao(await api.entrar(email, password)),
      activarConvite: async (dados) => iniciarSessao(await api.aceitarConvite(dados)),
      mudarPalavraPasse: async (actual, nova) => iniciarSessao(await api.mudarPalavraPasse(actual, nova)),
      sair: terminar,
    }),
    [partner, estado, iniciarSessao, terminar]
  );

  return <PartnerAuthContext.Provider value={valor}>{children}</PartnerAuthContext.Provider>;
}

export function usePartnerAuth() {
  const ctx = useContext(PartnerAuthContext);
  if (!ctx) throw new Error("usePartnerAuth só pode ser usado dentro de <PartnerAuthProvider>.");
  return ctx;
}
