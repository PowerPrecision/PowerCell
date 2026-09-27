"""A Parede no Gestor de Ficheiros (Épico 10, Gestor S3, Passo 3).

O bucket está arrumado por pasta de CLIENTE e o S3 não sabe o que é uma
rede. A ponte é `processes.s3_folder` → `processes.network_id`, e a decisão
pertence ao **primeiro segmento** do caminho: tudo abaixo de
`Documentação Clientes/Joao_Silva/` é do Joao_Silva, pelo que navegar cinco
níveis custa a mesma decisão que navegar um.

POLÍTICA CONFIRMADA (números de produção, Set 2026: 12.450 pastas)
  * Só a **Camada 1** (rede). O Explorador é ferramenta de arrumação
    documental da empresa; o limite da carteira individual não se aplica.
  * Pasta **órfã** (ninguém a reclama) → invisível, excepto ADMIN/CEO.
  * Pasta **ambígua** (reclamada por redes DIFERENTES) → invisível a ambas,
    excepto ADMIN/CEO. Mostrar à "primeira" seria escolher à sorte qual das
    redes vê os documentos da outra.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from models.auth import UserRoleEnum as UserRole
from services.s3_explorer_paths import RAIZ_DO_EXPLORADOR as R
from services.s3_explorer_scope import (
    PastaDoExplorador,
    carregar_pastas,
    filtrar_subpastas,
    pode_ver,
    assert_pasta_no_ambito,
)
from services.tenant_network import TenantScope

REDE_POWER = "grupo_power_precision"
REDE_DOMUS = "domus"

ESCOPO_POWER = TenantScope(network_ids=(REDE_POWER,), company_ids=("cmp-power",))
ESCOPO_DOMUS = TenantScope(network_ids=(REDE_DOMUS,), company_ids=("cmp-domus",))


def pasta(nome, *, redes=(REDE_POWER,), orfa=False):
    return PastaDoExplorador(
        caminho=f"{R}/{nome}",
        network_ids=frozenset(redes),
        company_ids=frozenset(),
        company_names=frozenset(),
        orfa=orfa,
    )


class TestPodeVer:
    def test_mesma_rede_ve(self):
        assert pode_ver(pasta("Joao"), ESCOPO_POWER, role=UserRole.CONSULTOR)

    def test_a_domus_nao_ve_a_power(self):
        """O requisito central: tolerância zero ao cruzamento."""
        assert not pode_ver(pasta("Joao"), ESCOPO_DOMUS, role=UserRole.DIRETOR)

    def test_a_power_nao_ve_a_domus(self):
        assert not pode_ver(
            pasta("Ana", redes=(REDE_DOMUS,)), ESCOPO_POWER, role=UserRole.CONSULTOR
        )

    def test_consultor_ve_a_carteira_dos_colegas_da_sua_rede(self):
        """Decisão de produto: SÓ a Camada 1. O Explorador é ferramenta de
        arrumação da empresa, não uma vista de carteira — estreitar por
        atribuição tornaria a página inútil para quem organiza ficheiros."""
        assert pode_ver(pasta("Cliente_De_Outro"), ESCOPO_POWER, role=UserRole.CONSULTOR)


class TestOrfasEAmbiguas:
    def test_orfa_e_invisivel_a_um_utilizador_normal(self):
        assert not pode_ver(
            pasta("Antiga", redes=(), orfa=True), ESCOPO_POWER, role=UserRole.CONSULTOR
        )

    @pytest.mark.parametrize("papel", [UserRole.ADMIN, UserRole.CEO])
    def test_orfa_e_visivel_a_gestao_de_topo(self, papel):
        """São 250 pastas depois do backfill, e alguém tem de as reconciliar.
        Invisíveis a toda a gente seria perder o histórico em silêncio."""
        assert pode_ver(pasta("Antiga", redes=(), orfa=True), ESCOPO_POWER, role=papel)

    def test_diretor_NAO_conta_como_gestao_de_topo_aqui(self):
        """A excepção é para reconciliação, não para hierarquia: um director
        da Domus veria pastas cuja rede não se sabe qual é."""
        assert not pode_ver(
            pasta("Antiga", redes=(), orfa=True), ESCOPO_DOMUS, role=UserRole.DIRETOR
        )

    def test_ambigua_e_invisivel_as_DUAS_redes(self):
        ambigua = pasta("Maria_Santos", redes=(REDE_POWER, REDE_DOMUS))
        assert not pode_ver(ambigua, ESCOPO_POWER, role=UserRole.DIRETOR)
        assert not pode_ver(ambigua, ESCOPO_DOMUS, role=UserRole.DIRETOR)

    def test_ambigua_e_visivel_ao_admin_para_reconciliar(self):
        ambigua = pasta("Maria_Santos", redes=(REDE_POWER, REDE_DOMUS))
        assert pode_ver(ambigua, ESCOPO_POWER, role=UserRole.ADMIN)

    def test_duas_empresas_da_MESMA_rede_nao_e_ambiguidade(self):
        """Power e Precision partilham rede: um cliente de ambas é normal."""
        p = PastaDoExplorador(
            caminho=f"{R}/Joao",
            network_ids=frozenset({REDE_POWER}),
            company_ids=frozenset({"cmp-power", "cmp-precision"}),
            company_names=frozenset(),
        )
        assert pode_ver(p, ESCOPO_POWER, role=UserRole.CONSULTOR)


class TestCarregarPastas:
    """UMA query em lote, nunca N+1."""

    async def test_uma_so_leitura_para_muitas_pastas(self, fake_async_db, monkeypatch):
        import services.s3_explorer_scope as alvo

        monkeypatch.setattr(alvo, "db", fake_async_db)
        for i in range(5):
            await fake_async_db.processes.insert_one({
                "id": f"p{i}", "s3_folder": f"{R}/C{i}", "network_id": REDE_POWER,
            })

        chamadas = []
        original = fake_async_db.processes.find

        def espiar(*args, **kwargs):
            chamadas.append(args[0] if args else kwargs.get("filter"))
            return original(*args, **kwargs)

        monkeypatch.setattr(fake_async_db.processes, "find", espiar)

        mapa = await alvo.carregar_pastas([f"{R}/C{i}" for i in range(5)])
        assert len(mapa) == 5
        assert len(chamadas) == 1, "uma pasta por query seria N+1"

    async def test_pasta_sem_processo_vem_marcada_como_orfa(self, fake_async_db, monkeypatch):
        import services.s3_explorer_scope as alvo

        monkeypatch.setattr(alvo, "db", fake_async_db)
        mapa = await alvo.carregar_pastas([f"{R}/Ninguem"])
        assert mapa[f"{R}/Ninguem"].orfa is True

    async def test_redes_diferentes_marcam_ambiguidade(self, fake_async_db, monkeypatch):
        import services.s3_explorer_scope as alvo

        monkeypatch.setattr(alvo, "db", fake_async_db)
        await fake_async_db.processes.insert_one(
            {"id": "p1", "s3_folder": f"{R}/M", "network_id": REDE_POWER})
        await fake_async_db.processes.insert_one(
            {"id": "p2", "s3_folder": f"{R}/M", "network_id": REDE_DOMUS})

        mapa = await alvo.carregar_pastas([f"{R}/M"])
        assert mapa[f"{R}/M"].ambigua is True

    async def test_barra_final_nao_falha_a_correspondencia(self, fake_async_db, monkeypatch):
        import services.s3_explorer_scope as alvo

        monkeypatch.setattr(alvo, "db", fake_async_db)
        await fake_async_db.processes.insert_one(
            {"id": "p1", "s3_folder": f"{R}/J", "network_id": REDE_POWER})
        mapa = await alvo.carregar_pastas([f"{R}/J/"])
        assert mapa[f"{R}/J/"].orfa is False

    async def test_lista_vazia_nao_faz_query_nenhuma(self, fake_async_db, monkeypatch):
        import services.s3_explorer_scope as alvo

        monkeypatch.setattr(alvo, "db", fake_async_db)
        assert await alvo.carregar_pastas([]) == {}


class TestAssertPastaNoAmbito:
    """404, nunca 403 — o nome da pasta É o nome do cliente."""

    async def test_fora_do_ambito_devolve_404(self, fake_async_db, monkeypatch):
        import services.s3_explorer_scope as alvo

        monkeypatch.setattr(alvo, "db", fake_async_db)
        await fake_async_db.processes.insert_one(
            {"id": "p1", "s3_folder": f"{R}/Joao", "network_id": REDE_POWER})

        with pytest.raises(HTTPException) as exc:
            await assert_pasta_no_ambito(
                f"{R}/Joao/Financeiros", ESCOPO_DOMUS, role=UserRole.CONSULTOR
            )
        assert exc.value.status_code == 404
        # Um 403 confirmaria que a pasta existe, e o nome da pasta é o nome
        # do cliente — confirmaria a carteira da concorrência.
        assert "Joao" not in str(exc.value.detail)

    async def test_dentro_do_ambito_passa(self, fake_async_db, monkeypatch):
        import services.s3_explorer_scope as alvo

        monkeypatch.setattr(alvo, "db", fake_async_db)
        await fake_async_db.processes.insert_one(
            {"id": "p1", "s3_folder": f"{R}/Joao", "network_id": REDE_POWER})
        await assert_pasta_no_ambito(
            f"{R}/Joao/Financeiros/a.pdf", ESCOPO_POWER, role=UserRole.CONSULTOR
        )

    async def test_a_raiz_e_sempre_permitida(self, fake_async_db, monkeypatch):
        """A raiz não é de ninguém — quem a lista recebe a lista FILTRADA."""
        import services.s3_explorer_scope as alvo

        monkeypatch.setattr(alvo, "db", fake_async_db)
        await assert_pasta_no_ambito(R, ESCOPO_DOMUS, role=UserRole.CONSULTOR)

    async def test_a_decisao_e_do_PRIMEIRO_segmento(self, fake_async_db, monkeypatch):
        """Profundidade não acrescenta decisão: é o que torna isto barato."""
        import services.s3_explorer_scope as alvo

        monkeypatch.setattr(alvo, "db", fake_async_db)
        await fake_async_db.processes.insert_one(
            {"id": "p1", "s3_folder": f"{R}/Joao", "network_id": REDE_DOMUS})

        for profundidade in [
            f"{R}/Joao",
            f"{R}/Joao/Financeiros",
            f"{R}/Joao/Financeiros/2024/IRS/anexo.pdf",
        ]:
            with pytest.raises(HTTPException) as exc:
                await assert_pasta_no_ambito(
                    profundidade, ESCOPO_POWER, role=UserRole.CONSULTOR
                )
            assert exc.value.status_code == 404


class TestFiltrarSubpastas:
    async def test_a_raiz_devolve_so_o_que_e_da_rede(self, fake_async_db, monkeypatch):
        import services.s3_explorer_scope as alvo

        monkeypatch.setattr(alvo, "db", fake_async_db)
        await fake_async_db.processes.insert_one(
            {"id": "p1", "s3_folder": f"{R}/Power_A", "network_id": REDE_POWER})
        await fake_async_db.processes.insert_one(
            {"id": "p2", "s3_folder": f"{R}/Domus_A", "network_id": REDE_DOMUS})

        entrada = [
            {"path": f"{R}/Power_A", "name": "Power_A"},
            {"path": f"{R}/Domus_A", "name": "Domus_A"},
            {"path": f"{R}/Orfa", "name": "Orfa"},
        ]
        visiveis = await filtrar_subpastas(entrada, ESCOPO_DOMUS, role=UserRole.CONSULTOR)
        assert [p["name"] for p in visiveis] == ["Domus_A"]

    async def test_admin_ve_tudo_incluindo_as_orfas(self, fake_async_db, monkeypatch):
        import services.s3_explorer_scope as alvo

        monkeypatch.setattr(alvo, "db", fake_async_db)
        entrada = [{"path": f"{R}/Orfa", "name": "Orfa"}]
        visiveis = await filtrar_subpastas(entrada, ESCOPO_DOMUS, role=UserRole.ADMIN)
        assert len(visiveis) == 1


class TestFalhaFechadaQueAsMutacoesDenunciaram:
    """Duas propriedades que eu tinha escrito em comentário e nunca afirmado.

    Ambas as mutações sobreviveram à primeira passagem — não por serem
    código morto, mas porque nenhum teste as exercitava.
    """

    def test_pasta_desconhecida_nao_e_visivel(self):
        """`pode_ver` é pública: um chamador pode passar-lhe `None`.

        Devolver `True` aí seria abrir a porta sempre que a pasta não
        constasse do mapa — e o mapa é construído por uma leitura que pode
        falhar.
        """
        assert pode_ver(None, ESCOPO_POWER, role=UserRole.ADMIN) is False
        assert pode_ver(None, None, role=UserRole.ADMIN) is False

    def test_pasta_sem_orfandade_mas_sem_escopo_nao_e_visivel(self):
        assert pode_ver(pasta("Joao"), None, role=UserRole.CONSULTOR) is False

    async def test_leitura_falhada_esconde_TUDO(self, monkeypatch):
        """Uma leitura falhada não pode abrir o que a leitura bem sucedida
        fecharia.

        Se `carregar_pastas` propagasse a excepção, o Explorador devolvia
        500 — visível, mas o pior é o contrário: devolver as pastas sem
        pertença conhecida. Aqui, um Mongo em baixo torna TODAS as pastas
        órfãs, logo invisíveis a quem não reconcilia.
        """
        import services.s3_explorer_scope as alvo

        class BaseDeDadosPartida:
            def __getattr__(self, _):
                raise RuntimeError("Mongo em baixo")

        monkeypatch.setattr(alvo, "db", BaseDeDadosPartida())

        mapa = await alvo.carregar_pastas([f"{R}/Joao"])
        assert mapa[f"{R}/Joao"].orfa is True
        assert pode_ver(mapa[f"{R}/Joao"], ESCOPO_POWER, role=UserRole.CONSULTOR) is False

    async def test_leitura_falhada_nao_esconde_do_admin(self, monkeypatch):
        """Contraprova: quem reconcilia continua a poder trabalhar."""
        import services.s3_explorer_scope as alvo

        class BaseDeDadosPartida:
            def __getattr__(self, _):
                raise RuntimeError("Mongo em baixo")

        monkeypatch.setattr(alvo, "db", BaseDeDadosPartida())
        mapa = await alvo.carregar_pastas([f"{R}/Joao"])
        assert pode_ver(mapa[f"{R}/Joao"], ESCOPO_POWER, role=UserRole.ADMIN) is True
