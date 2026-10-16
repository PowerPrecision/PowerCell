"""O email de «Acesso ao Portal do Cliente» nunca é esperado por um pedido HTTP (Lote 7.2).

O pedido: o envio deve ser uma tarefa em segundo plano, como o RGPD. Lido o código, todos os caminhos
já o eram (`spawn_background_task` no registo público, na criação do processo, na criação do cliente,
na atribuição e no link mágico). O que faltava era a PROPRIEDADE: nada impedia um caminho novo de fazer
`await deliver_registration_email(...)` dentro do pedido — e um servidor de email pendurado paga-se em
30 s de formulário. O inventário por AST abaixo falha por omissão.
"""
from __future__ import annotations

import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

#: Quem ENVIA o email do Portal (o trabalho lento).
ENVIADORES = {
    "deliver_registration_email",
    "send_registration_confirmation",
    "_entregar_magic_link",
    "enviar_email_do_portal",
}
#: Funções cujo corpo faz `await` a um enviador — e que por isso só podem correr em segundo plano.
EXECUTORES = {
    "deliver_registration_email",           # é o próprio enviador (fila de retry incluída)
    "send_portal_welcome_email_from_process",
    "_send_portal_welcome_email_safe",
    "_enviar_email_de_registo",              # aninhada em public_registration
    "_entregar_magic_link",
    "send_registration_email_task",          # consumidor da fila (já fora do pedido)
    "send_registration_email",               # idem: o handler da fila Mongo do worker
    "enviar_email_do_portal",
}


def _modulos():
    for pasta in ("services", "routes"):
        for ficheiro in (RAIZ / pasta).rglob("*.py"):
            yield ficheiro, ast.parse(ficheiro.read_text(encoding="utf-8"))


def _pais(arvore):
    mapa = {}
    for no in ast.walk(arvore):
        for filho in ast.iter_child_nodes(no):
            mapa[filho] = no
    return mapa


def _nome_chamado(call: ast.Call):
    f = call.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None


def _funcao_que_contem(no, pais):
    while no in pais:
        no = pais[no]
        if isinstance(no, (ast.AsyncFunctionDef, ast.FunctionDef)):
            return no.name
    return None


def test_nenhum_pedido_espera_pelo_envio_do_portal():
    intrusos = []
    lidos = 0
    for ficheiro, arvore in _modulos():
        pais = _pais(arvore)
        for no in ast.walk(arvore):
            if isinstance(no, ast.Await) and isinstance(no.value, ast.Call):
                alvo = _nome_chamado(no.value)
                if alvo in {"deliver_registration_email", "send_registration_confirmation", "_entregar_magic_link"}:
                    lidos += 1
                    dona = _funcao_que_contem(no, pais)
                    if dona not in EXECUTORES:
                        intrusos.append(f"{ficheiro.relative_to(RAIZ)}:{no.lineno} {dona} → await {alvo}")
    assert lidos >= 4, "o leitor não leu os envios que existem (contraprova)"
    assert not intrusos, "envio do Portal esperado dentro de um pedido:\n" + "\n".join(intrusos)


def test_os_executores_so_sao_chamados_dentro_de_spawn_background_task():
    sem_spawn = []
    chamadas = 0
    alvos = EXECUTORES - {
        "deliver_registration_email", "send_registration_email_task", "send_registration_email",
        "enviar_email_do_portal",
    }
    for ficheiro, arvore in _modulos():
        pais = _pais(arvore)
        for no in ast.walk(arvore):
            if isinstance(no, ast.Call) and _nome_chamado(no) in alvos:
                dona = _funcao_que_contem(no, pais)
                if dona == _nome_chamado(no):
                    continue
                chamadas += 1
                pai = pais.get(no)
                if not (isinstance(pai, ast.Call) and _nome_chamado(pai) == "spawn_background_task"):
                    sem_spawn.append(f"{ficheiro.relative_to(RAIZ)}:{no.lineno} {_nome_chamado(no)}")
    assert chamadas >= 5, "o leitor não encontrou as chamadas que existem (contraprova)"
    assert not sem_spawn, "executor chamado fora de spawn_background_task:\n" + "\n".join(sem_spawn)
