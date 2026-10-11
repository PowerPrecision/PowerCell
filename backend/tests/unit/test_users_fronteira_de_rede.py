"""Duas dívidas da Via Rápida, fechadas: `GET /users/{id}` e a dropdown do Master.

O QUE ESTAVA EM JOGO
====================
1. `GET /users/{id}` devolvia o perfil (email, telefone, empresas) de
   QUALQUER utilizador a qualquer membro da equipa que soubesse o id —
   `require_staff` autoriza o verbo, não o objecto. A lista já filtrava
   por rede; o pedido por id não. Hoje: o próprio, o Master (tudo) ou
   alguém das empresas da minha rede; o resto é **404**, igual ao de
   «não existe» (um 403 confirmava o id).
2. A dropdown de atribuição mostrava TODOS ao Master, e o servidor
   recusava ao gravar o que o processo não alcança: a interface a
   contradizer o servidor. Hoje `?process_id=` faz a lista do Master
   sair já limitada ao que o processo alcança.

`TestAExploracao` é o ataque: escrito para morder primeiro.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from tests.unit.helpers_tenant import (  # noqa: F401
    ANA,
    BRUNO,
    CARLA,
    REDE_DOMUS,
    REDE_INCUMBENTE,
    db_tenant,  # noqa: F401  (fixture)
    tenant_db as _tenant_db,
)

NUNO = {"id": "u-nuno", "name": "Nuno", "email": "nuno@domus.pt", "role": "consultor"}
PEDRO = {"id": "u-pedro", "name": "Pedro", "email": "pedro@precision.pt", "role": "consultor"}
MASTER = {"id": "u-master", "name": "Master", "email": "m@sistema.pt", "role": "master"}

EMPRESA_DE = {
    "u-ana": "Power Real Estate", "u-bruno": "Domus",
    "u-carla": "Precision Crédito", "u-nuno": "Domus",
    "u-pedro": "Precision Crédito",
}


@pytest.fixture
def casa(db_tenant):  # noqa: F811
    db_tenant.user_company_roles.docs.extend([
        {"user_id": "u-nuno", "company_id": "cmp-domus", "company_name": "Domus",
         "role": "consultor", "is_default": True},
        {"user_id": "u-pedro", "company_id": "cmp-precision",
         "company_name": "Precision Crédito", "role": "consultor", "is_default": True},
    ])
    for u in (ANA, BRUNO, CARLA, NUNO, PEDRO, MASTER):
        db_tenant.users.docs.append({
            **u, "is_active": True, "password": "hash-secreto",
            **({"company": EMPRESA_DE[u["id"]]} if u["id"] in EMPRESA_DE else {}),
        })
    return db_tenant


def _ctx(fake_db):
    from services import (
        admin_users_scope,
        assignment_network_guard,
        user_management_scope,
        users_api_list,
    )

    return _tenant_db(
        fake_db, admin_users_scope, assignment_network_guard,
        user_management_scope, users_api_list,
    )


async def _ler(casa, ator, user_id):
    from services.users_api_list import run_get_user

    with _ctx(casa):
        return await run_get_user(user_id, ator)


# ════════════════════════════════════════════════════════════════════
#  1 · GET /users/{id}
# ════════════════════════════════════════════════════════════════════
class TestAExploracao:

    @pytest.mark.asyncio
    async def test_conhecer_o_id_de_alguem_de_outra_rede_nao_chega(self, casa):
        with pytest.raises(HTTPException) as erro:
            await _ler(casa, ANA, "u-nuno")
        assert erro.value.status_code == 404

    @pytest.mark.asyncio
    async def test_a_Domus_tambem_nao_le_a_Precision(self, casa):
        with pytest.raises(HTTPException) as erro:
            await _ler(casa, BRUNO, "u-pedro")
        assert erro.value.status_code == 404

    @pytest.mark.asyncio
    async def test_fora_do_ambito_e_inexistente_respondem_o_mesmo(self, casa):
        """Sem oráculo: «não é teu» e «não existe» são indistinguíveis."""
        with pytest.raises(HTTPException) as alheio:
            await _ler(casa, ANA, "u-nuno")
        with pytest.raises(HTTPException) as inexistente:
            await _ler(casa, ANA, "u-ninguem")
        assert (alheio.value.status_code, alheio.value.detail) == (
            inexistente.value.status_code, inexistente.value.detail,
        )

    @pytest.mark.asyncio
    async def test_um_perfil_local_nunca_ve_o_master(self, casa):
        with pytest.raises(HTTPException) as erro:
            await _ler(casa, ANA, "u-master")
        assert erro.value.status_code == 404

    @pytest.mark.asyncio
    async def test_a_rota_passa_o_utilizador_que_pede(self, casa):
        """A rota fina tem de entregar o ator ao serviço: sem isso a
        guarda existia e nunca decidia nada."""
        from routes import users as rotas

        with _ctx(casa):
            with pytest.raises(HTTPException) as erro:
                await rotas.get_user("u-nuno", user=ANA)
            assert erro.value.status_code == 404
            visto = await rotas.get_user("u-pedro", user=ANA)
        assert visto["id"] == "u-pedro"


class TestOQueContinuaPermitido:

    @pytest.mark.asyncio
    async def test_alguem_da_minha_rede_mesmo_noutra_empresa(self, casa):
        """Ana (Power) lê o Pedro (Precision): mesma rede."""
        visto = await _ler(casa, ANA, "u-pedro")
        assert visto["id"] == "u-pedro"

    @pytest.mark.asyncio
    async def test_o_proprio_perfil(self, casa):
        visto = await _ler(casa, BRUNO, "u-bruno")
        assert visto["id"] == "u-bruno"

    @pytest.mark.asyncio
    async def test_quem_trabalha_nas_duas_redes_le_as_duas(self, casa):
        """A Carla tem UCR na Precision e na Domus: lê o Nuno e o Pedro."""
        assert (await _ler(casa, CARLA, "u-nuno"))["id"] == "u-nuno"
        assert (await _ler(casa, CARLA, "u-pedro"))["id"] == "u-pedro"

    @pytest.mark.asyncio
    async def test_o_master_le_qualquer_um(self, casa):
        for alvo in ("u-nuno", "u-pedro", "u-ana"):
            assert (await _ler(casa, MASTER, alvo))["id"] == alvo

    @pytest.mark.asyncio
    async def test_a_palavra_passe_nunca_e_pedida_a_base_de_dados(self, casa):
        """O duplo de Mongo ignora a projecção em `find_one` (contrato
        histórico), pelo que olhar para o resultado provava o duplo. Mede-se
        o que SAI: todas as leituras de `users` excluem `password`."""
        projeccoes = []
        original = casa.users.find_one

        async def espiar(query, projection=None, *a, **k):
            projeccoes.append(projection)
            return await original(query, projection, *a, **k)

        casa.users.find_one = espiar
        await _ler(casa, ANA, "u-pedro")

        # A leitura do objecto devolvido ao cliente é a primeira.
        assert projeccoes[0] is not None
        assert projeccoes[0].get("password") == 0
        assert projeccoes[0].get("_id") == 0

    @pytest.mark.asyncio
    async def test_a_guarda_corre_sobre_o_objecto_e_nao_sobre_o_papel(self):
        """Contraprova da guarda de fonte: `run_get_user` delega na
        guarda de gestão e já não faz um `find_one` por id à mão."""
        from services import users_api_list
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        fonte = codigo_da_funcao_sem_comentarios(users_api_list.run_get_user)
        assert "carregar_utilizador_gerivel" in fonte
        assert "find_one" not in fonte


# ════════════════════════════════════════════════════════════════════
#  2 · A DROPDOWN DO MASTER ACOMPANHA O ALCANCE DO PROCESSO
# ════════════════════════════════════════════════════════════════════
def _processo(db_tenant, **campos):  # noqa: F811
    db_tenant.processes.docs.append({"status": "novo", **campos})


async def _lista(casa, ator, *, process_id=None, staff=False):
    from services.users_api_list import run_get_staff_users, run_get_users

    with _ctx(casa):
        if staff:
            return await run_get_staff_users(ator, process_id=process_id)
        return await run_get_users(
            None, ator, for_assignment=True, process_id=process_id,
        )


def _ids(lista):
    return {u["id"] for u in lista}


class TestADropdownDoMaster:

    @pytest.mark.asyncio
    async def test_sem_processo_o_master_continua_a_ver_todos(self, casa):
        """Criação: ainda não há processo, o destino é que decide."""
        ids = _ids(await _lista(casa, MASTER))
        assert {"u-ana", "u-nuno", "u-pedro", "u-bruno"} <= ids

    @pytest.mark.asyncio
    async def test_com_processo_da_Power_o_master_nao_ve_a_Domus(self, casa):
        _processo(casa, id="p-1", network_id=REDE_INCUMBENTE)
        ids = _ids(await _lista(casa, MASTER, process_id="p-1"))
        assert {"u-ana", "u-pedro", "u-carla"} <= ids
        assert "u-nuno" not in ids and "u-bruno" not in ids

    @pytest.mark.asyncio
    async def test_com_processo_da_Domus_o_master_nao_ve_a_Power(self, casa):
        _processo(casa, id="p-2", network_id=REDE_DOMUS)
        ids = _ids(await _lista(casa, MASTER, process_id="p-2"))
        assert {"u-nuno", "u-bruno"} <= ids
        assert "u-ana" not in ids and "u-pedro" not in ids

    @pytest.mark.asyncio
    async def test_a_rede_convidada_entra_na_lista(self, casa):
        """Partilha explícita: o processo da Power já alcança a Domus."""
        _processo(casa, id="p-3", network_id=REDE_INCUMBENTE,
                  partner_network_ids=[REDE_DOMUS])
        ids = _ids(await _lista(casa, MASTER, process_id="p-3"))
        assert {"u-ana", "u-nuno"} <= ids

    @pytest.mark.asyncio
    async def test_quem_ja_esta_na_equipa_nao_desaparece(self, casa):
        """A Via Rápida antiga deixou o Nuno num processo da Power. A
        interface devolve a lista inteira ao gravar: se o nome sumisse,
        sumia da equipa sem ninguém o pedir."""
        _processo(casa, id="p-4", network_id=REDE_INCUMBENTE,
                  assigned_consultor_ids=["u-nuno"], consultor_id="u-nuno")
        ids = _ids(await _lista(casa, MASTER, process_id="p-4"))
        assert "u-nuno" in ids
        assert "u-bruno" not in ids  # quem NÃO estava continua de fora

    @pytest.mark.asyncio
    async def test_processo_inexistente_e_como_sem_processo(self, casa):
        ids = _ids(await _lista(casa, MASTER, process_id="p-nao-existe"))
        assert {"u-ana", "u-nuno"} <= ids

    @pytest.mark.asyncio
    async def test_o_staff_usa_a_mesma_regra(self, casa):
        _processo(casa, id="p-5", network_id=REDE_INCUMBENTE)
        ids = _ids(await _lista(casa, MASTER, process_id="p-5", staff=True))
        assert "u-ana" in ids and "u-nuno" not in ids

    @pytest.mark.asyncio
    async def test_a_lista_e_a_mesma_pergunta_que_o_servidor_faz_ao_gravar(self, casa):
        """Concordância: tudo o que a lista oferece, a guarda aceita; tudo
        o que omite, a guarda recusa. É o que impede o ecrã e o servidor
        de voltarem a divergir."""
        from services.assignment_network_guard import (
            exigir_atribuidos_da_minha_rede,
        )

        processo = {"id": "p-6", "network_id": REDE_INCUMBENTE}
        _processo(casa, **processo)
        candidatos = [ANA, PEDRO, CARLA, NUNO, BRUNO]
        oferecidos = _ids(await _lista(casa, MASTER, process_id="p-6"))
        for u in candidatos:
            with _ctx(casa):
                try:
                    await exigir_atribuidos_da_minha_rede(
                        MASTER, [u["id"]], processo=processo,
                    )
                    aceite = True
                except HTTPException:
                    aceite = False
            assert aceite == (u["id"] in oferecidos), u["id"]

    @pytest.mark.asyncio
    async def test_quem_nao_e_master_nao_muda_com_o_process_id(self, casa):
        """A lista da Ana já é a da sua rede; o processo nada acrescenta
        (e não é por aqui que se descobre processos alheios)."""
        _processo(casa, id="p-7", network_id=REDE_DOMUS,
                  assigned_consultor_ids=["u-nuno"])
        lidos = []
        original = casa.processes.find_one

        async def espiar(query, *a, **k):
            lidos.append(query)
            return await original(query, *a, **k)

        casa.processes.find_one = espiar
        sem = _ids(await _lista(casa, ANA))
        com = _ids(await _lista(casa, ANA, process_id="p-7"))
        assert sem == com
        assert "u-nuno" not in com
        # E o processo nem é lido: quem tem fronteira não precisa dele, e
        # ler um processo alheio só para o ignorar é trabalho (e superfície)
        # que não devia existir.
        assert lidos == []

    @pytest.mark.asyncio
    async def test_o_processo_e_lido_so_com_o_que_a_pergunta_precisa(self, casa):
        """Projecção medida um nível abaixo (o duplo ignora-a): sem o
        carimbo ou as convidadas a guarda decidia sobre um documento
        incompleto — e sem projecção nenhuma trazia o cliente inteiro."""
        from services.tenant_network import CAMPO_REDE, CAMPO_REDES_PARCEIRAS

        _processo(casa, id="p-8", network_id=REDE_INCUMBENTE)
        projeccoes = []
        original = casa.processes.find_one

        async def espiar(query, projection=None, *a, **k):
            projeccoes.append(projection)
            return await original(query, projection, *a, **k)

        casa.processes.find_one = espiar
        await _lista(casa, MASTER, process_id="p-8")

        assert projeccoes, "o processo nem chegou a ser lido"
        projeccao = projeccoes[0]
        assert projeccao and projeccao.get(CAMPO_REDE) == 1
        assert projeccao.get(CAMPO_REDES_PARCEIRAS) == 1
        assert projeccao.get("assigned_consultor_ids") == 1
        assert "client_name" not in projeccao and "dados_pessoais" not in projeccao

    @pytest.mark.asyncio
    async def test_as_rotas_aceitam_o_process_id(self):
        """Contraprova da ligação: as DUAS rotas passam-no ao serviço."""
        import inspect

        from routes import users as rotas
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        for rota in (rotas.get_users, rotas.get_staff_users):
            assert "process_id" in inspect.signature(rota).parameters
            assert "process_id=process_id" in codigo_da_funcao_sem_comentarios(rota)
