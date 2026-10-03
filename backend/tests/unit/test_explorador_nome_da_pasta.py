"""O Explorador não pode mostrar um uuid onde devia estar um nome (Lote 6).

A identidade da pasta passou a derivar do ID, e isso tem um custo que o
refactor anterior deixou em aberto: no Explorador de Ficheiros e no diálogo de
mapeamento, uma pasta nova aparece como
`11111111-1111-4111-8111-111111111111`. O nome real é resolúvel — está no
mapeamento — e é o mapeamento que tem de o dar.

E HÁ UMA SEGUNDA METADE, PIOR
=============================
`carregar_pastas` resolvia a pertença lendo **só** `db.processes` pelo campo
`s3_folder`. Com a pasta do processo a viver DENTRO da do cliente
(`{cid}/processos/{pid}`), a pasta de topo `{cid}` deixou de ter um processo a
apontar-lhe — passou a contar como **órfã**, e uma órfã só é visível a
ADMIN/CEO. Ou seja: a correcção do ponto 1 tornava invisível ao staff normal a
pasta de todos os clientes novos.

Não é visível em teste nenhum do ponto 1, porque lá a pergunta era outra. É
este ficheiro que a faz.

A fronteira de rede NÃO se alarga com isto: a rede continua a vir dos
PROCESSOS (os clientes não são carimbados na criação), e a resolução por id
apenas encontra os processos que já lá estavam.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from services.s3_document_root import pasta_do_cliente, pasta_do_processo
from services.tenant_network import TenantScope

pytestmark = pytest.mark.asyncio

CID = "11111111-1111-4111-8111-111111111111"
PID = "22222222-2222-4222-8222-222222222222"
PASTA_DO_CLIENTE = pasta_do_cliente(CID)
PASTA_DO_PROCESSO = pasta_do_processo(PID, client_id=CID)


class TestAPastaPorIdDeixaDeSerOrfa:
    async def test_o_processo_dentro_da_pasta_resolve_a_pasta_de_topo(
        self, fake_async_db
    ):
        from services import s3_explorer_scope as mod

        await fake_async_db.processes.insert_one({
            "id": PID,
            "client_id": CID,
            "client_name": "Carolina Agostinho da Silva",
            "s3_folder": PASTA_DO_PROCESSO,
            "network_id": "grupo_power_precision",
        })

        with patch.object(mod, "db", fake_async_db):
            mapa = await mod.carregar_pastas([PASTA_DO_CLIENTE])

        pasta = mapa[PASTA_DO_CLIENTE]
        assert pasta.orfa is False
        assert "grupo_power_precision" in pasta.network_ids

    async def test_o_cliente_sozinho_da_o_NOME(self, fake_async_db):
        from services import s3_explorer_scope as mod

        await fake_async_db.clients.insert_one({
            "id": CID,
            "nome": "Carolina Agostinho da Silva",
            "s3_folder": PASTA_DO_CLIENTE,
        })

        with patch.object(mod, "db", fake_async_db):
            mapa = await mod.carregar_pastas([PASTA_DO_CLIENTE])

        assert "Carolina Agostinho da Silva" in mapa[PASTA_DO_CLIENTE].nomes

    async def test_o_nome_legivel_substitui_o_uuid(self, fake_async_db):
        from services import s3_explorer_scope as mod

        await fake_async_db.processes.insert_one({
            "id": PID, "client_id": CID, "client_name": "Rui Pereira",
            "s3_folder": PASTA_DO_PROCESSO, "network_id": "r1",
        })

        with patch.object(mod, "db", fake_async_db):
            mapa = await mod.carregar_pastas([PASTA_DO_CLIENTE])

        assert mod.nome_legivel(mapa[PASTA_DO_CLIENTE], CID) == "Rui Pereira"

    async def test_a_pasta_LEGADA_mantem_o_proprio_nome(self, fake_async_db):
        from services import s3_explorer_scope as mod

        legada = "Documentação Clientes/Joao_Silva"
        await fake_async_db.processes.insert_one({
            "id": "p9", "client_name": "João Silva",
            "s3_folder": legada, "network_id": "r1",
        })

        with patch.object(mod, "db", fake_async_db):
            mapa = await mod.carregar_pastas([legada])

        # O nome da pasta já é legível: não se troca por nada.
        assert mod.nome_legivel(mapa[legada], "Joao_Silva") == "Joao_Silva"

    async def test_sem_dono_o_uuid_fica_como_esta(self, fake_async_db):
        from services import s3_explorer_scope as mod

        with patch.object(mod, "db", fake_async_db):
            mapa = await mod.carregar_pastas([PASTA_DO_CLIENTE])

        # Inventar um nome seria pior: a pasta órfã tem de se ver como órfã,
        # que é o trabalho de reconciliação.
        assert mod.nome_legivel(mapa[PASTA_DO_CLIENTE], CID) == CID
        assert mapa[PASTA_DO_CLIENTE].orfa is True

    async def test_dois_nomes_na_mesma_pasta_nao_escolhem_um(self, fake_async_db):
        """Uma pasta reclamada por dois clientes é uma colisão (D-19).

        Mostrar um dos nomes faria a colisão parecer resolvida. Diz-se que são
        dois.
        """
        from services import s3_explorer_scope as mod

        legada = "Documentação Clientes/Carolina_Silva"
        await fake_async_db.processes.insert_one({
            "id": "p1", "client_name": "Carolina Silva",
            "s3_folder": legada, "network_id": "r1",
        })
        await fake_async_db.processes.insert_one({
            "id": "p2", "client_name": "Carolina Agostinho da Silva",
            "s3_folder": legada, "network_id": "r1",
        })

        with patch.object(mod, "db", fake_async_db):
            mapa = await mod.carregar_pastas([legada])

        pasta = mapa[legada]
        assert len(pasta.nomes) == 2
        assert mod.nome_legivel(pasta, "Carolina_Silva") == "Carolina_Silva"

    async def test_uma_pasta_POR_ID_com_dois_donos_mantem_o_uuid(
        self, fake_async_db
    ):
        """O caso que o teste acima NÃO cobria, e que uma mutação revelou.

        Com uma pasta de nome LEGADO, o `nome_legivel` devolve o nome cru
        porque o nome não é um uuid — a decisão sobre "quantos nomes há" nem
        chega a correr. A colisão que importa é a da pasta POR ID: aí o uuid
        seria substituído, e substituí-lo por UM dos dois nomes faria a colisão
        parecer resolvida.
        """
        from services import s3_explorer_scope as mod

        await fake_async_db.processes.insert_one({
            "id": "pa", "client_id": CID, "client_name": "Carolina Silva",
            "s3_folder": PASTA_DO_PROCESSO, "network_id": "r1",
        })
        # Um segundo processo religado À MÃO para a mesma pasta de topo — é
        # exactamente o que a ferramenta de religamento permite, com aviso.
        await fake_async_db.processes.insert_one({
            "id": "pb", "client_name": "Carolina Agostinho da Silva",
            "s3_folder": PASTA_DO_CLIENTE, "network_id": "r1",
        })

        with patch.object(mod, "db", fake_async_db):
            mapa = await mod.carregar_pastas([PASTA_DO_CLIENTE])

        pasta = mapa[PASTA_DO_CLIENTE]
        assert len(pasta.nomes) == 2
        assert mod.nome_legivel(pasta, CID) == CID


class TestAFronteiraDeRedeNaoSeAlarga:
    async def test_a_pasta_de_outra_rede_continua_invisivel(self, fake_async_db):
        from services import s3_explorer_scope as mod

        await fake_async_db.processes.insert_one({
            "id": PID, "client_id": CID, "client_name": "Cliente Domus",
            "s3_folder": PASTA_DO_PROCESSO, "network_id": "domus",
        })

        with patch.object(mod, "db", fake_async_db):
            mapa = await mod.carregar_pastas([PASTA_DO_CLIENTE])

        scope_power = TenantScope(network_ids=frozenset({"grupo_power_precision"}))
        assert mod.pode_ver(mapa[PASTA_DO_CLIENTE], scope_power, role="consultor") is False
        scope_domus = TenantScope(network_ids=frozenset({"domus"}))
        assert mod.pode_ver(mapa[PASTA_DO_CLIENTE], scope_domus, role="consultor") is True

    async def test_um_cliente_sem_processo_continua_so_para_reconciliacao(
        self, fake_async_db
    ):
        """O cliente não é carimbado com a rede na criação — logo uma pasta
        que só tenha cliente não tem rede, e sem rede é falha fechada. Era
        assim antes (a pasta por nome também não tinha processo) e continua."""
        from services import s3_explorer_scope as mod

        await fake_async_db.clients.insert_one({
            "id": CID, "nome": "Cliente Novo", "s3_folder": PASTA_DO_CLIENTE,
        })

        with patch.object(mod, "db", fake_async_db):
            mapa = await mod.carregar_pastas([PASTA_DO_CLIENTE])

        scope = TenantScope(network_ids=frozenset({"r1"}))
        assert mod.pode_ver(mapa[PASTA_DO_CLIENTE], scope, role="consultor") is False
        assert mod.pode_ver(mapa[PASTA_DO_CLIENTE], scope, role="admin") is True


class TestOQueOExploradorDevolve:
    async def test_a_listagem_traz_display_name_e_o_path_INTACTO(
        self, fake_async_db
    ):
        from services import s3_explorer_scope as mod

        await fake_async_db.processes.insert_one({
            "id": PID, "client_id": CID, "client_name": "Rui Pereira",
            "s3_folder": PASTA_DO_PROCESSO, "network_id": "r1",
        })

        with patch.object(mod, "db", fake_async_db):
            saida = await mod.filtrar_subpastas(
                [{"path": PASTA_DO_CLIENTE, "name": CID}],
                TenantScope(network_ids=frozenset({"r1"})),
                role="consultor",
            )

        assert len(saida) == 1
        assert saida[0]["display_name"] == "Rui Pereira"
        # O que as operações usam não muda: mostrar uma coisa e operar noutra
        # é a forma discreta de uma parede não valer nada.
        assert saida[0]["path"] == PASTA_DO_CLIENTE
        assert saida[0]["name"] == CID

    async def test_a_pasta_com_duas_fichas_diz_que_sao_duas(self, fake_async_db):
        from services import s3_explorer_scope as mod

        legada = "Documentação Clientes/Carolina_Silva"
        for pid, nome in (("p1", "Carolina Silva"), ("p2", "Carolina A. da Silva")):
            await fake_async_db.processes.insert_one({
                "id": pid, "client_name": nome, "s3_folder": legada,
                "network_id": "r1",
            })

        with patch.object(mod, "db", fake_async_db):
            saida = await mod.filtrar_subpastas(
                [{"path": legada, "name": "Carolina_Silva"}],
                TenantScope(network_ids=frozenset({"r1"})),
                role="consultor",
            )

        assert len(saida[0]["nomes_dos_clientes"]) == 2
