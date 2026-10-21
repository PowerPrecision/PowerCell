"""A Via Rápida foi extinta: atribuição directa só dentro da própria rede.

O QUE ESTÁ EM JOGO
==================
Atribuir um processo a alguém de outra rede abria-o a essa rede
(`sincronizar_parceiros`). Quem atribuía escolhia o utilizador final de
outra rede, saltava a fila de triagem central dela, e — pior — quem tem
UCRs em duas redes (a Carla, o caso real do grupo) abria a segunda por
acaso. Hoje:

* o atribuído tem de pertencer a uma rede de quem atribui (403 com o
  caminho certo: «Partilhar com Empresa…»);
* a lista de «quem posso escolher» sai do servidor já filtrada;
* passar um processo a outra rede é a Partilha Explícita.

`TestAExploracao` é o ataque: escrito para morder primeiro.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from services.assignment_network_guard import (
    MENSAGEM_DE_RECUSA,
    exigir_atribuidos_da_minha_rede,
    pode_atribuir,
    redes_permitidas,
)
from services.tenant_network import TenantScope
from tests.unit.helpers_tenant import (
    ANA,
    BRUNO,
    CARLA,
    REDE_DOMUS,
    REDE_INCUMBENTE,
    db_tenant,  # noqa: F401  (fixture)
    tenant_db as _tenant_db,
)

#: Só na Domus — a rede de OUTRA ilha.
NUNO = {"id": "u-nuno", "name": "Nuno", "email": "nuno@domus.pt", "role": "consultor"}
#: Só na Precision — mesma rede da Power.
PEDRO = {"id": "u-pedro", "name": "Pedro", "email": "pedro@precision.pt", "role": "consultor"}
#: Um Master (único perfil global).
MASTER = {"id": "u-master", "name": "Master", "email": "m@sistema.pt", "role": "master"}


@pytest.fixture
def casa(db_tenant):  # noqa: F811
    db_tenant.user_company_roles.docs.extend([
        {"user_id": "u-nuno", "company_id": "cmp-domus", "company_name": "Domus",
         "role": "consultor", "is_default": True},
        {"user_id": "u-pedro", "company_id": "cmp-precision",
         "company_name": "Precision Crédito", "role": "consultor", "is_default": True},
    ])
    # Em produção cada conta leva o NOME da empresa em `company` (o campo
    # legado). Sem ele uma conta conta como «órfã», que o âmbito admite
    # por desenho — e a lista deixava de filtrar nos testes.
    empresa_de = {
        "u-ana": "Power Real Estate", "u-bruno": "Domus",
        "u-carla": "Precision Crédito", "u-nuno": "Domus",
        "u-pedro": "Precision Crédito",
    }
    for u in (ANA, BRUNO, CARLA, NUNO, PEDRO, MASTER):
        db_tenant.users.docs.append({
            **u, "is_active": True,
            **({"company": empresa_de[u["id"]]} if u["id"] in empresa_de else {}),
        })
    return db_tenant


def _ctx(fake_db):
    from services import (
        admin_users_scope,
        assignment_network_guard,
        process_staff_assignment,
    )

    return _tenant_db(
        fake_db, assignment_network_guard, process_staff_assignment,
        admin_users_scope,
    )


def _processo(fake_db, pid="p-power") -> dict:
    return next(p for p in fake_db.processes.docs if p["id"] == pid)


# ════════════════════════════════════════════════════════════════════
#  AS DUAS PERGUNTAS PURAS
# ════════════════════════════════════════════════════════════════════
class TestAsRegrasPuras:

    def test_um_utilizador_normal_atribui_as_redes_a_que_pertence(self):
        ator = TenantScope(network_ids=(REDE_INCUMBENTE,))
        assert redes_permitidas(ator) == {REDE_INCUMBENTE}

    def test_o_master_sem_processo_nao_tem_limite(self):
        assert redes_permitidas(TenantScope(sem_fronteira=True)) is None

    def test_o_master_com_processo_so_alcanca_o_que_o_processo_ja_alcanca(self):
        """Sem isto o Master reabria a Via Rápida pela janela: atribuir
        como Master a alguém de uma rede nova abria essa rede."""
        processo = {
            "network_id": REDE_INCUMBENTE,
            "partner_network_ids": [REDE_DOMUS],
        }
        assert redes_permitidas(
            TenantScope(sem_fronteira=True), processo,
        ) == {REDE_INCUMBENTE, REDE_DOMUS}

    def test_as_redes_tem_de_se_cruzar(self):
        assert pode_atribuir({REDE_INCUMBENTE}, {REDE_INCUMBENTE}) is True
        assert pode_atribuir({REDE_INCUMBENTE}, {REDE_DOMUS}) is False
        # Quem trabalha nas duas redes cruza com qualquer delas.
        assert pode_atribuir({REDE_INCUMBENTE}, {REDE_INCUMBENTE, REDE_DOMUS}) is True

    def test_um_alvo_sem_rede_determinavel_falha_FECHADO(self):
        """A alternativa é abrir a fronteira por não se saber a empresa de
        alguém — falha aberta no sítio exactamente errado."""
        assert pode_atribuir({REDE_INCUMBENTE}, set()) is False

    def test_um_alvo_global_ou_um_ator_sem_limite_passam(self):
        assert pode_atribuir({REDE_INCUMBENTE}, None) is True
        assert pode_atribuir(None, {REDE_DOMUS}) is True


# ════════════════════════════════════════════════════════════════════
#  O ATAQUE — escrito para morder primeiro
# ════════════════════════════════════════════════════════════════════
class TestAExploracao:

    @pytest.mark.asyncio
    async def test_atribuir_a_alguem_de_OUTRA_rede_e_recusado(self, casa):
        with _ctx(casa):
            with pytest.raises(HTTPException) as erro:
                await exigir_atribuidos_da_minha_rede(
                    ANA, ["u-nuno"], processo=_processo(casa),
                )
        assert erro.value.status_code == 403

    @pytest.mark.asyncio
    async def test_a_mensagem_diz_para_onde_ir_e_nao_nomeia_ninguem(self, casa):
        with _ctx(casa):
            with pytest.raises(HTTPException) as erro:
                await exigir_atribuidos_da_minha_rede(ANA, ["u-nuno"])
        assert erro.value.detail == MENSAGEM_DE_RECUSA
        assert "Partilhar com Empresa" in erro.value.detail
        assert "Nuno" not in erro.value.detail
        assert REDE_DOMUS not in erro.value.detail

    @pytest.mark.asyncio
    async def test_a_Domus_tambem_nao_atribui_a_Precision(self, casa):
        """O inverso: a ilha não escolhe o utilizador final do Hub."""
        with _ctx(casa):
            with pytest.raises(HTTPException):
                await exigir_atribuidos_da_minha_rede(BRUNO, ["u-pedro"])

    @pytest.mark.asyncio
    async def test_uma_lista_mista_e_recusada_por_inteiro(self, casa):
        """Um só atribuído de fora basta: não se grava metade."""
        with _ctx(casa):
            with pytest.raises(HTTPException):
                await exigir_atribuidos_da_minha_rede(
                    ANA, ["u-pedro", "u-nuno"],
                )

    @pytest.mark.asyncio
    async def test_o_Master_nao_abre_uma_rede_nova_por_atribuicao(self, casa):
        with _ctx(casa):
            with pytest.raises(HTTPException):
                await exigir_atribuidos_da_minha_rede(
                    MASTER, ["u-nuno"], processo=_processo(casa),
                )

    @pytest.mark.asyncio
    async def test_sem_rede_determinavel_o_atribuido_e_recusado(self, casa):
        """Utilizador sem empresa nenhuma e sem rede de omissão: falha
        fechada."""
        casa.users.docs.append({
            "id": "u-semempresa", "name": "Sem Empresa", "role": "consultor",
            "is_active": True,
        })
        with _ctx(casa):
            with pytest.raises(HTTPException):
                await exigir_atribuidos_da_minha_rede(ANA, ["u-semempresa"])


# ════════════════════════════════════════════════════════════════════
#  O QUE CONTINUA A FUNCIONAR (a regra não pode ser largueza demais)
# ════════════════════════════════════════════════════════════════════
class TestOQueContinuaPermitido:

    @pytest.mark.asyncio
    async def test_dentro_da_mesma_rede_mesmo_noutra_empresa(self, casa):
        """Power → Precision é outra EMPRESA da mesma REDE."""
        with _ctx(casa):
            await exigir_atribuidos_da_minha_rede(ANA, ["u-pedro"])

    @pytest.mark.asyncio
    async def test_quem_trabalha_nas_duas_redes_cruza_com_a_do_ator(self, casa):
        """A Carla é da Precision (a rede da Ana) **e** da Domus."""
        with _ctx(casa):
            await exigir_atribuidos_da_minha_rede(ANA, ["u-carla"])

    @pytest.mark.asyncio
    async def test_o_Master_atribui_a_quem_o_processo_ja_alcanca(self, casa):
        with _ctx(casa):
            await exigir_atribuidos_da_minha_rede(
                MASTER, ["u-pedro"], processo=_processo(casa),
            )

    @pytest.mark.asyncio
    async def test_um_processo_ja_partilhado_aceita_a_rede_convidada_ao_Master(self, casa):
        _processo(casa)["partner_network_ids"] = [REDE_DOMUS]
        with _ctx(casa):
            await exigir_atribuidos_da_minha_rede(
                MASTER, ["u-nuno"], processo=_processo(casa),
            )

    @pytest.mark.asyncio
    async def test_os_JA_atribuidos_nao_se_revalidam(self, casa):
        """A Via Rápida antiga deixou processos com gente de duas redes, e a
        interface devolve a lista inteira ao gravar. Validar tudo
        bloqueava a edição de qualquer um desses processos."""
        with _ctx(casa):
            await exigir_atribuidos_da_minha_rede(
                ANA, ["u-nuno", "u-pedro"], ja_atribuidos=["u-nuno"],
            )

    @pytest.mark.asyncio
    async def test_um_atribuido_inexistente_nao_e_uma_pergunta_desta_guarda(self, casa):
        """Os escritores já o ignoravam; responder 403 distinguia «não
        existe» de «não é da tua rede» e confirmava ids."""
        with _ctx(casa):
            await exigir_atribuidos_da_minha_rede(ANA, ["u-fantasma"])

    @pytest.mark.asyncio
    async def test_sem_ids_nao_faz_nada(self, casa):
        with _ctx(casa):
            await exigir_atribuidos_da_minha_rede(ANA, [])


# ════════════════════════════════════════════════════════════════════
#  O ESCRITOR REAL — recusa ANTES de escrever o que quer que seja
# ════════════════════════════════════════════════════════════════════
class TestOEscritorReal:

    @pytest.mark.asyncio
    async def test_o_assign_recusa_sem_gravar_nem_deixar_historico(self, casa):
        from unittest.mock import AsyncMock, patch

        from services.process_staff_assignment import run_staff_assign_process

        antes = dict(_processo(casa))
        historico = AsyncMock()
        with _ctx(casa), patch("services.history.log_history", historico):
            with pytest.raises(HTTPException) as erro:
                await run_staff_assign_process(
                    "p-power", ANA, consultor_ids="u-nuno",
                    inject_cdc_fn=lambda *a, **k: None,
                    invalidate_stats_fn=AsyncMock(),
                    broadcast_fn=AsyncMock(),
                )

        assert erro.value.status_code == 403
        assert _processo(casa) == antes, "a recusa tem de ser antes de gravar"
        historico.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_os_ids_validados_sao_os_que_o_escritor_grava(self, casa):
        """Uma segunda leitura dos parâmetros validava uma coisa e gravava
        outra: `ids_a_atribuir` usa a mesma normalização do escritor."""
        from services.process_staff_assignment import ids_a_atribuir

        assert ids_a_atribuir(consultor_ids="a, b", mediador_ids="c") == ["a", "b", "c"]
        # compat: os parâmetros singulares valem como listas de um
        assert ids_a_atribuir(consultor_id="x", mediador_id="y") == ["x", "y"]
        # limpar não é pôr: nada a validar
        assert ids_a_atribuir(consultor_ids="null", mediador_ids="") == []
        # indexação e parceiro também são pessoas escolhidas
        assert ids_a_atribuir(indexacao_id="i", parceiro_id="p") == ["i", "p"]


    @pytest.mark.asyncio
    async def test_a_sala_de_triagem_nao_passa_um_cliente_a_outra_rede(self, casa):
        """O processo nasce carimbado com a rede do utilizador de DESTINO:
        atribuir um cliente a alguém de outra rede era passá-lo para lá por
        escolha de quem distribui. Recusa-se ANTES de criar o processo."""
        from unittest.mock import patch

        from services import client_assign

        antes = len(casa.processes.docs)
        with _ctx(casa), patch.object(client_assign, "db", casa):
            with pytest.raises(HTTPException) as erro:
                await client_assign.run_assign_client_to_user(
                    "c-power", ANA, assign_to_user_id="u-nuno",
                    create_process=True,
                )

        assert erro.value.status_code == 403
        assert len(casa.processes.docs) == antes


# ════════════════════════════════════════════════════════════════════
#  A LISTA DE «QUEM POSSO ESCOLHER» SAI DO SERVIDOR, JÁ FILTRADA
# ════════════════════════════════════════════════════════════════════
class TestAListaDeAtribuiveis:

    @pytest.mark.asyncio
    async def test_a_Ana_nao_ve_a_Domus_na_lista_de_atribuicao(self, casa):
        from services.users_api_list import run_get_users

        with _ctx(casa):
            from services import users_api_list

            with __import__("unittest.mock", fromlist=["patch"]).patch.object(
                users_api_list, "db", casa,
            ):
                lista = await run_get_users(None, ANA, for_assignment=True)

        ids = {u["id"] for u in lista}
        assert "u-pedro" in ids and "u-carla" in ids
        assert "u-nuno" not in ids and "u-bruno" not in ids

    @pytest.mark.asyncio
    async def test_o_Bruno_nao_ve_a_Precision(self, casa):
        from unittest.mock import patch

        from services import users_api_list
        from services.users_api_list import run_get_users

        with _ctx(casa), patch.object(users_api_list, "db", casa):
            lista = await run_get_users(None, BRUNO, for_assignment=True)

        ids = {u["id"] for u in lista}
        assert "u-nuno" in ids
        assert "u-pedro" not in ids and "u-ana" not in ids

    @pytest.mark.asyncio
    async def test_as_rotas_de_listagem_usam_o_ambito(self):
        """Guarda de fonte com contraprova: `/users` e `/users/staff`
        passam ambas por `run_get_users`, que é onde a regra vive."""
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        from services import users_api_list

        fonte = codigo_da_funcao_sem_comentarios(users_api_list.run_get_users)
        # P5: o âmbito é o da EMPRESA activa (que cai no de rede quando não há cabeçalho válido).
        assert "empresas_da_empresa_activa" in fonte
        assert "build_users_scope_query" in fonte
        assert "run_get_users(" in codigo_da_funcao_sem_comentarios(
            users_api_list.run_get_staff_users
        )
