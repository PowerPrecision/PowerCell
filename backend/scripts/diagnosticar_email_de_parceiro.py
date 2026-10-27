#!/usr/bin/env python3
"""Porque é que este email «não pode ser usado para um parceiro»? (só leitura)

O convite de parceiro (`POST /api/admin/partners/invite`) responde 409 com a
mesma frase opaca em todos os casos — de propósito: não diz a quem convida se
o endereço é de um colaborador. Este script, corrido por quem tem acesso à
base de dados (Shell do Render), diz QUAL das regras recusou:

    cd backend && python scripts/diagnosticar_email_de_parceiro.py fulano@exemplo.pt

O QUE FAZ
  * Procura o email (normalizado como no convite) em `partners` e em `users`.
  * Para cada correspondência explica o motivo e o que fazer.

O QUE NÃO FAZ
  * Não escreve nada em lado nenhum.

CÓDIGOS DE SAÍDA: 0 o email está livre; 1 está em uso (motivo impresso);
2 argumentos ou `MONGO_URL` em falta.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PROJECCAO_PARCEIRO = {"_id": 0, "id": 1, "name": 1, "status": 1, "redes": 1, "convidado_pela_rede": 1, "invite": 1}
PROJECCAO_UTILIZADOR = {
    "_id": 0, "id": 1, "name": 1, "role": 1, "is_active": 1, "partner_directory": 1,
    "password": 1, "hashed_password": 1, "criado_pela_rede": 1,
}


def explicar_parceiro(parceiro: dict) -> str:
    """Já existe uma conta de parceiro com este email."""
    from services.partner_accounts import convite_vigente

    estado = parceiro.get("status") or "?"
    empresas = ", ".join(
        str(r.get("company_name") or r.get("company_id") or "?")
        for r in (parceiro.get("redes") or []) if isinstance(r, dict)
    ) or "nenhuma (agente independente)"
    if estado == "invited":
        vigente = "ainda válido" if convite_vigente(parceiro) else "EXPIRADO"
        accao = f"Já foi convidado (convite {vigente}). Use «Reenviar Convite» na lista de Parceiros."
    elif estado == "suspended":
        accao = "Conta suspensa. Reactive-a na lista de Parceiros em vez de convidar de novo."
    else:
        accao = "A conta já existe. Se não aparece na sua lista, pertence ao âmbito de outra rede."
    return (
        f"PARCEIRO já existente: «{parceiro.get('name')}» (id {parceiro.get('id')}), "
        f"estado {estado}, empresas: {empresas}, rede de quem convidou: "
        f"{parceiro.get('convidado_pela_rede') or '—'}.\n    → {accao}"
    )


def explicar_utilizador(utilizador: dict) -> str:
    """Um registo em `users` (colaborador, cliente ou parceiro antigo) com este email."""
    papel = utilizador.get("role") or "?"
    activo = "activo" if utilizador.get("is_active", True) else "inactivo"
    base = f"UTILIZADOR «{utilizador.get('name')}» (id {utilizador.get('id')}), perfil {papel}, {activo}."
    if papel == "parceiro" and not (utilizador.get("password") or utilizador.get("hashed_password")):
        if utilizador.get("partner_directory"):
            accao = "É a linha de directório de um parceiro já convidado (ver acima)."
        else:
            accao = (
                "É um parceiro ANTIGO criado em Utilizadores (sem portal). O convite só o aceita "
                "por adopção (`adopt_user_id`), que o ecrã de Parceiros ainda não oferece."
            )
    else:
        accao = (
            "O email pertence a uma conta da equipa/cliente. Um parceiro tem de usar outro endereço "
            "(nunca se liga uma conta de parceiro à de um colaborador)."
        )
    return f"{base}\n    → {accao}"


def explicar(email: str, parceiros: list[dict], utilizadores: list[dict]) -> list[str]:
    linhas = [explicar_parceiro(p) for p in parceiros if p.get("status") != "deleted"]
    linhas += [explicar_utilizador(u) for u in utilizadores]
    return linhas


async def _procurar(email: str) -> tuple[list[dict], list[dict], list[dict]]:
    from database import db

    exacto = {"email": email}
    parceiros = await db.partners.find(exacto, PROJECCAO_PARCEIRO).to_list(10)
    utilizadores = await db.users.find(exacto, PROJECCAO_UTILIZADOR).to_list(10)
    # Só informativo: o convite compara o email EXACTO (minúsculas). Um registo
    # com maiúsculas não bloqueia o convite, mas é bom saber que existe.
    sem_caixa = {"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}}
    parecidos = [
        u for u in await db.users.find(sem_caixa, PROJECCAO_UTILIZADOR).to_list(10)
        if u.get("id") not in {x.get("id") for x in utilizadores}
    ]
    return parceiros, utilizadores, parecidos


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("email")
    args = parser.parse_args(argv)

    if not os.environ.get("MONGO_URL"):
        print("MONGO_URL por definir — nada a fazer.")
        return 2

    from services.partner_accounts import normalizar_email

    email = normalizar_email(args.email)
    if not email:
        print("Email inválido.")
        return 2

    parceiros, utilizadores, parecidos = asyncio.run(_procurar(email))
    linhas = explicar(email, parceiros, utilizadores)

    print(f"Email analisado: {email}")
    if not linhas:
        print("LIVRE — nenhum parceiro nem utilizador usa este email; o convite deve passar.")
        for u in parecidos:
            print(f"  (nota: existe {u.get('role')} «{u.get('name')}» com o mesmo email noutra caixa de letras)")
        return 0
    print("EM USO — é por isto que o convite responde 409:")
    for linha in linhas:
        print(f"  • {linha}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
