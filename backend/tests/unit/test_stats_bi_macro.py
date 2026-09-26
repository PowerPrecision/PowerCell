"""
BI por macro-fase — Dashboard, Camada 2.

Ver `services/stats_macro_bridge.py`, `stats_funnel.py`, `stats_sla.py` e
`stats_networks.py`.

O QUE ESTES TESTES DEFENDEM
  1. **Que a ponte conta o mesmo que o quadro.** Um processo gravado como
     `cpcv` entra na macro-fase da fase a que corresponde, não numa coluna
     de reconciliação. Sem isto, o gráfico e o Kanban contavam coisas
     diferentes sobre os mesmos 217 processos.
  2. **Que a fronteira de rede está no PRIMEIRO `$match`.** Depois do
     `$group` já teria somado os processos da outra rede.
  3. **Que as macro-fases terminais ficam fora dos SLAs.** Um processo
     concluído não demora em concluído. A medição de produção mostra 3.200
     na banda `61+` de `concluido`, e um painel que grita sem razão ensina
     toda a gente a ignorá-lo.
  4. **Que as estimativas aberrantes ficam fora das médias.** Erram para
     lados opostos e não se anulam.
  5. **Que os limiares vêm do painel de admin.** Nunca do código.
"""
import pathlib
from unittest.mock import AsyncMock, patch

import pytest

from tests.unit.helpers_fonte import codigo_sem_comentarios
from tests.unit.helpers_tenant import (
    ANA,
    BRUNO,
    CARLA,
    REDE_DOMUS,
    REDE_INCUMBENTE,
    db_tenant,  # noqa: F401  (fixture)
    rede_de_omissao_incumbente,  # noqa: F401  (fixture)
    tenant_db,
)
from services.phase_clock_backfill import CAMPO_QUALIDADE
from services.phase_clock_coverage import (
    ETIQUETAS_DAS_BANDAS,
    LIMITES_DAS_BANDAS,
    QUALIDADE_NUNCA_TOCADO,
    QUALIDADE_PLAUSIVEL,
)
from services.process_phase_clock import CAMPO_MACRO_DESDE, CAMPO_TEMPOS
from services.stats_macro_bridge import (
    MACROS_COM_SLA,
    ORDEM_DO_FUNIL,
    PonteDeMacros,
    construir_ponte,
)
from services.workflow_phases import FASE_DESCONHECIDA

RAIZ_BACKEND = pathlib.Path(__file__).resolve().parents[2]

MODULOS_DE_BI = ("stats_funnel", "stats_sla", "stats_networks", "stats_macro_bridge")


def fase(nome, macro=None, **extra):
    base = {"id": nome, "name": nome, "label": nome, "order": 1}
    if macro:
        base["macro_fase"] = macro
    base.update(extra)
    return base


FASES = [
    # `novo` existe porque é o estado dos processos do cenário partilhado
    # (`helpers_tenant`). Sem ele, esses processos caíam na reconciliação e
    # cada asserção sobre as etapas tinha de descontar dois — um teste que
    # se lê a contar processos de outra parte não prova nada com clareza.
    fase("novo", "novo"),
    fase("clientes_espera", "novo"),
    fase("analise_documental", "analise"),
    fase("pre_aprovado", "aprovado"),
    fase("fase_escritura", "aprovado"),
    fase("concluidos", "concluido", is_active=False),
]


@pytest.fixture
def motor(db_tenant):
    for f in FASES:
        db_tenant.workflow_statuses.docs.append(dict(f))
    return db_tenant


@pytest.fixture
def sem_cache():
    import contextlib

    with contextlib.ExitStack() as pilha:
        for nome in ("stats_funnel", "stats_sla", "stats_networks"):
            pilha.enter_context(patch(
                f"services.{nome}.cache_get", new_callable=AsyncMock,
                return_value=None,
            ))
            pilha.enter_context(patch(
                f"services.{nome}.cache_set", new_callable=AsyncMock,
                return_value=True,
            ))
        yield


@pytest.fixture
def pode_ver():
    with patch("models.permissions.resolve_capability", return_value=True):
        yield


def ponte_de_teste():
    """A ponte tal como o motor de teste a produz, incluindo o alias."""
    return PonteDeMacros(mapa={
        "clientes_espera": "novo",
        "analise_documental": "analise",
        "pre_aprovado": "aprovado",
        "fase_escritura": "aprovado",
        "cpcv": "aprovado",          # alias -> fase_escritura
        "concluidos": "concluido",
        "perdido": None,             # o motor não conhece
    })


# ════════════════════════════════════════════════════════════════════
# A PONTE
# ════════════════════════════════════════════════════════════════════

class TestPonteDeMacros:
    def test_valores_de_inclui_os_aliases(self):
        """O que distingue isto do `nomes_por_macro`, que só devolve
        nomes que o motor conhece."""
        ponte = ponte_de_teste()

        assert ponte.valores_de("aprovado") == [
            "cpcv", "fase_escritura", "pre_aprovado",
        ]

    def test_a_expressao_e_um_switch_com_reconciliacao_no_default(self):
        expressao = ponte_de_teste().expressao()

        assert "$switch" in expressao
        assert expressao["$switch"]["default"] == FASE_DESCONHECIDA
        casos = {
            ramo["then"] for ramo in expressao["$switch"]["branches"]
        }
        assert casos == {"novo", "analise", "aprovado", "concluido"}

    def test_uma_ponte_vazia_nao_produz_um_switch_invalido(self):
        """Um `$switch` sem ramos é um erro no Mongo; um dashboard que
        rebenta porque a colecção de fases está vazia é pior do que um que
        diz "nada classificado"."""
        expressao = PonteDeMacros(mapa={}).expressao()

        assert expressao == {"$literal": FASE_DESCONHECIDA}

    def test_macros_presentes_segue_a_ordem_do_enum(self):
        assert ponte_de_teste().macros_presentes == [
            "novo", "analise", "aprovado", "concluido",
        ]

    async def test_o_distinct_leva_o_ambito_de_rede(
        self, motor, rede_de_omissao_incumbente,
    ):
        """Sem isto, a ponte revelava que fases existem noutra rede."""
        import services.stats_macro_bridge as smb
        import services.stats_scope as ss

        filtros = []
        original = motor.processes.distinct

        async def espiar(chave, query=None):
            filtros.append(query)
            return await original(chave, query)

        with tenant_db(motor, smb, ss):
            with patch.object(motor.processes, "distinct", espiar):
                ambito = await ss.resolver_ambito(BRUNO)
                await construir_ponte(ambito)

        assert len(filtros) == 1
        assert REDE_DOMUS in repr(filtros[0])
        assert REDE_INCUMBENTE not in repr(filtros[0])
        # E os eliminados ficam de fora. Contrato de CUSTO, não de
        # resultado (mutação Q26): um status que só existe em processos
        # eliminados ganharia um ramo no `$switch` que nenhum documento
        # alcança. Não muda a saída — muda o tamanho da expressão e a
        # coerência com o `$match` do funil, que também os exclui.
        assert "is_deleted" in repr(filtros[0])

    async def test_a_ponte_resolve_os_aliases_do_motor_real(
        self, motor, rede_de_omissao_incumbente,
    ):
        """Ponta a ponta: `cpcv` está na base de dados e o motor não o tem."""
        import services.stats_macro_bridge as smb
        import services.stats_scope as ss

        motor.processes.docs.append({
            "id": "p-cpcv", "status": "cpcv", "network_id": REDE_DOMUS,
        })

        with tenant_db(motor, smb, ss):
            ponte = await construir_ponte(await ss.resolver_ambito(BRUNO))

        assert ponte.mapa["cpcv"] == "aprovado"

    def test_as_macros_com_sla_excluem_as_terminais(self):
        """Derivada, não escrita: duas listas divergem na primeira mudança."""
        assert set(MACROS_COM_SLA) == {"novo", "analise", "aprovado"}


# ════════════════════════════════════════════════════════════════════
# O FUNIL
# ════════════════════════════════════════════════════════════════════

class TestFunil:
    from services.stats_funnel import construir_pipeline, montar_funil

    def test_a_rede_entra_no_primeiro_match(self):
        from services.stats_funnel import construir_pipeline
        from services.stats_scope import AmbitoEstatistico
        from services.tenant_network import TenantScope

        ambito = AmbitoEstatistico(
            scope=TenantScope(network_ids=(REDE_DOMUS,)),
            condicao={"network_id": {"$in": [REDE_DOMUS]}},
            sufixo="a1" + "0" * 16,
        )
        pipeline = construir_pipeline(ambito, ponte_de_teste())

        assert list(pipeline[0].keys()) == ["$match"]
        assert REDE_DOMUS in repr(pipeline[0]["$match"])

    def test_alcancaram_e_monotono(self):
        from services.stats_funnel import montar_funil

        funil = montar_funil([
            {"_id": "novo", "processos": 10},
            {"_id": "analise", "processos": 20},
            {"_id": "aprovado", "processos": 5},
            {"_id": "concluido", "processos": 2},
        ])
        alcancaram = {e["macro_fase"]: e["alcancaram"] for e in funil["etapas"]}

        assert alcancaram["novo"] == 37
        assert alcancaram["analise"] == 27
        assert alcancaram["aprovado"] == 7
        assert alcancaram["concluido"] == 2

    def test_a_conversao_e_entre_etapas_consecutivas(self):
        from services.stats_funnel import montar_funil

        funil = montar_funil([
            {"_id": "novo", "processos": 50},
            {"_id": "analise", "processos": 50},
        ])
        etapas = {e["macro_fase"]: e for e in funil["etapas"]}

        # 100 alcançaram `novo`, 50 alcançaram `analise`.
        assert etapas["novo"]["conversao_para_seguinte"] == 50.0
        assert etapas["concluido"]["conversao_para_seguinte"] is None

    def test_o_perdido_fica_fora_da_cadeia(self):
        """Um processo perde-se de qualquer etapa e não se sabe de qual.

        Contá-lo em `alcancaram(novo)` inflacionava o denominador da
        primeira conversão e fazia a taxa parecer pior do que é.
        """
        from services.stats_funnel import montar_funil

        funil = montar_funil([
            {"_id": "novo", "processos": 10},
            {"_id": "perdido", "processos": 90},
        ])
        etapas = {e["macro_fase"]: e for e in funil["etapas"]}

        assert etapas["novo"]["alcancaram"] == 10
        assert funil["perdidos"]["processos"] == 90

    def test_a_reconciliacao_aparece_e_nao_se_soma_a_uma_etapa(self):
        from services.stats_funnel import montar_funil

        funil = montar_funil([
            {"_id": "analise", "processos": 10},
            {"_id": FASE_DESCONHECIDA, "processos": 3},
        ])

        assert funil["desconhecidos"]["processos"] == 3
        assert sum(e["processos"] for e in funil["etapas"]) == 10

    def test_nada_se_perde_no_total(self):
        """Invariante: etapas + perdidos + reconciliação == total."""
        from services.stats_funnel import montar_funil

        linhas = [
            {"_id": "novo", "processos": 4},
            {"_id": "analise", "processos": 5},
            {"_id": "concluido", "processos": 6},
            {"_id": "perdido", "processos": 7},
            {"_id": FASE_DESCONHECIDA, "processos": 8},
        ]
        funil = montar_funil(linhas)

        assert funil["total_processos"] == 30

    def test_soma_os_valores(self):
        from services.stats_funnel import montar_funil

        funil = montar_funil([{
            "_id": "analise", "processos": 2,
            "valor_imovel": 300000.0, "valor_financiado": 250000.0,
        }])
        etapa = next(e for e in funil["etapas"] if e["macro_fase"] == "analise")

        assert etapa["valor_imovel"] == 300000.0
        assert etapa["valor_financiado"] == 250000.0

    def test_funil_vazio_nao_rebenta(self):
        from services.stats_funnel import montar_funil

        funil = montar_funil([])

        assert funil["total_processos"] == 0
        assert funil["taxa_de_conclusao"] is None
        assert len(funil["etapas"]) == len(ORDEM_DO_FUNIL)


class TestFunilDePontaAPonta:
    """A agregação a correr, não só o construtor.

    A base de dados falsa ganhou `$project` e as expressões da ponte
    exactamente para isto: o `$switch` que resolve `cpcv` é o coração
    deste endpoint, e testá-lo contra um ciclo em Python provava o ciclo.
    """

    async def _funil(self, db, user):
        import services.stats_funnel as sf
        import services.stats_macro_bridge as smb
        import services.stats_scope as ss

        with tenant_db(db, sf, smb, ss):
            return await sf.run_get_funnel(dict(user))

    async def test_o_alias_conta_na_macro_certa(
        self, motor, rede_de_omissao_incumbente, sem_cache, pode_ver,
    ):
        """O teste discriminante: `cpcv` não existe no motor.

        O resolvedor manda-o para `fase_escritura` (macro `aprovado`), a
        mesma coluna que o quadro lhe desenha. Sem a ponte, caía na
        reconciliação e o gráfico contradizia o Kanban.
        """
        motor.processes.docs.extend([
            {"id": "d1", "status": "analise_documental", "network_id": REDE_DOMUS},
            {"id": "d2", "status": "cpcv", "network_id": REDE_DOMUS},
        ])

        funil = await self._funil(motor, BRUNO)
        etapas = {e["macro_fase"]: e["processos"] for e in funil["etapas"]}

        assert etapas["aprovado"] == 1
        assert etapas["analise"] == 1
        assert funil["desconhecidos"]["processos"] == 0

    async def test_um_valor_que_o_motor_nao_conhece_vai_para_a_reconciliacao(
        self, motor, rede_de_omissao_incumbente, sem_cache, pode_ver,
    ):
        motor.processes.docs.append(
            {"id": "d3", "status": "perdido", "network_id": REDE_DOMUS},
        )

        funil = await self._funil(motor, BRUNO)

        assert funil["desconhecidos"]["processos"] == 1

    async def test_o_funil_nao_atravessa_redes(
        self, motor, rede_de_omissao_incumbente, sem_cache, pode_ver,
    ):
        # Estados DIFERENTES de propósito: comparar totais não provava
        # nada (as duas redes têm três processos cada no cenário) e a
        # asserção que interessa é a composição — o `aprovado` só existe
        # do lado da Power.
        motor.processes.docs.extend([
            {"id": "d-power", "status": "pre_aprovado",
             "network_id": REDE_INCUMBENTE},
            {"id": "d-domus", "status": "analise_documental",
             "network_id": REDE_DOMUS},
        ])

        domus = await self._funil(motor, BRUNO)
        power = await self._funil(motor, ANA)

        def por_macro(funil):
            return {e["macro_fase"]: e["processos"] for e in funil["etapas"]}

        assert por_macro(domus)["aprovado"] == 0
        assert por_macro(power)["aprovado"] == 1
        assert por_macro(domus)["analise"] == 1
        assert por_macro(power)["analise"] == 0

    async def test_os_eliminados_nao_entram(
        self, motor, rede_de_omissao_incumbente, sem_cache, pode_ver,
    ):
        motor.processes.docs.append({
            "id": "d-morto", "status": "analise_documental",
            "network_id": REDE_DOMUS, "is_deleted": True,
        })

        antes = await self._funil(motor, BRUNO)

        motor.processes.docs.append({
            "id": "d-morto-2", "status": "analise_documental",
            "network_id": REDE_DOMUS, "is_deleted": True,
        })
        depois = await self._funil(motor, BRUNO)

        # O TOTAL, e não só a etapa: apanhado por mutação (Q7). Assertar
        # `analise == 0` passava mesmo com o filtro removido, porque a PONTE
        # também filtra os eliminados — o status do processo morto nem
        # chegava ao `$switch` e ele caía na reconciliação em vez da etapa.
        # O teste dava verde pela razão errada e deixava passar um funil que
        # contava processos eliminados na coluna de reconciliação.
        assert depois["total_processos"] == antes["total_processos"]
        analise = next(e for e in depois["etapas"] if e["macro_fase"] == "analise")
        assert analise["processos"] == 0
        assert depois["desconhecidos"]["processos"] == antes["desconhecidos"]["processos"]

    async def test_sem_permissao_e_403(self, motor):
        import services.stats_funnel as sf
        from fastapi import HTTPException

        with patch("models.permissions.resolve_capability", return_value=False):
            with pytest.raises(HTTPException) as erro:
                await sf.run_get_funnel(dict(BRUNO))

        assert erro.value.status_code == 403

    async def test_a_chave_de_cache_leva_o_ambito(
        self, motor, rede_de_omissao_incumbente, pode_ver,
    ):
        import services.stats_funnel as sf
        import services.stats_macro_bridge as smb
        import services.stats_scope as ss

        chaves = []

        async def cache_get(chave, *a, **k):
            chaves.append(chave)
            return None

        with tenant_db(motor, sf, smb, ss):
            with patch.object(sf, "cache_get", cache_get), \
                 patch.object(sf, "cache_set", AsyncMock(return_value=True)):
                await sf.run_get_funnel(dict(BRUNO))
                await sf.run_get_funnel(dict(ANA))

        assert chaves[0] != chaves[1]
        assert all(c.startswith("stats:funil:v1:") for c in chaves)


# ════════════════════════════════════════════════════════════════════
# OS SLAs
# ════════════════════════════════════════════════════════════════════

class TestPipelineDeSla:
    def _ambito(self):
        from services.stats_scope import AmbitoEstatistico
        from services.tenant_network import TenantScope

        return AmbitoEstatistico(
            scope=TenantScope(network_ids=(REDE_DOMUS,)),
            condicao={"network_id": {"$in": [REDE_DOMUS]}},
            sufixo="a1" + "0" * 16,
        )

    def _pipeline(self):
        from services.stats_sla import construir_pipeline_de_presos

        return construir_pipeline_de_presos(self._ambito(), ponte_de_teste())

    def test_a_rede_entra_no_primeiro_match(self):
        pipeline = self._pipeline()

        assert list(pipeline[0].keys()) == ["$match"]
        assert REDE_DOMUS in repr(pipeline[0]["$match"])

    def test_as_estimativas_aberrantes_ficam_fora(self):
        """Erram para lados opostos — juntá-las na média não as anula."""
        correspondencia = repr(self._pipeline()[0]["$match"])

        assert CAMPO_QUALIDADE in correspondencia
        assert QUALIDADE_NUNCA_TOCADO in correspondencia
        assert "$nin" in correspondencia

    def test_as_macros_terminais_nao_tem_faceta(self):
        """Um processo concluído não demora em concluído."""
        pipeline = self._pipeline()
        facetas = pipeline[-1]["$facet"]

        assert set(facetas) == {"novo", "analise", "aprovado"}
        assert "concluido" not in facetas

    def test_o_bucket_usa_as_bandas_da_medicao(self):
        """Bandas diferentes fariam o retrato e o gráfico contar histórias
        distintas sobre os mesmos dados."""
        facetas = self._pipeline()[-1]["$facet"]
        bucket = facetas["analise"][-1]["$bucket"]

        assert bucket["boundaries"] == [0, *LIMITES_DAS_BANDAS]
        assert bucket["default"] == ETIQUETAS_DAS_BANDAS[-1]

    def test_uma_permanencia_negativa_e_excluida(self):
        """Dado corrompido não é zero dias."""
        pipeline = self._pipeline()

        assert {"$match": {"dias": {"$gte": 0}}} in pipeline

    def test_sem_valores_no_ambito_nao_ha_pipeline(self):
        """Uma `$facet` vazia é um erro no Mongo."""
        from services.stats_sla import construir_pipeline_de_presos

        assert construir_pipeline_de_presos(
            self._ambito(), PonteDeMacros(mapa={}),
        ) == []

    def test_o_historico_le_o_acumulador_por_macro(self):
        from services.stats_sla import construir_pipeline_de_historico

        pipeline = construir_pipeline_de_historico(self._ambito())
        grupo = pipeline[-1]["$group"]

        for macro in MACROS_COM_SLA:
            assert grupo[f"media_{macro}"] == {"$avg": f"${CAMPO_TEMPOS}.{macro}"}


class TestMontarSla:
    from services.stats_sla import montar_sla

    def _baldes(self, **por_banda):
        """Simula o que o `$bucket` devolve: `_id` = fronteira inferior."""
        fronteiras = [0, *LIMITES_DAS_BANDAS]
        saida = []
        for etq, quantos in por_banda.items():
            etiqueta = etq.replace("_", "-").replace("mais", "+")
            indice = ETIQUETAS_DAS_BANDAS.index(etiqueta)
            chave = (
                ETIQUETAS_DAS_BANDAS[-1]
                if indice == len(ETIQUETAS_DAS_BANDAS) - 1
                else fronteiras[indice]
            )
            saida.append({"_id": chave, "processos": quantos, "dias_medios": 1.0})
        return saida

    def test_as_bandas_vazias_entram_com_zero(self):
        """Um histograma com buracos lê-se como se a banda não existisse."""
        from services.stats_sla import montar_sla

        linhas = montar_sla({"analise": self._baldes(**{"0_7": 5})}, {}, {})
        analise = next(l for l in linhas if l["macro_fase"] == "analise")

        assert [b["banda"] for b in analise["bandas"]] == list(ETIQUETAS_DAS_BANDAS)
        assert analise["bandas"][0]["processos"] == 5
        assert analise["bandas"][1]["processos"] == 0

    def test_conta_os_acima_do_limiar(self):
        from services.stats_sla import montar_sla

        baldes = self._baldes(**{"0_7": 10, "8_15": 4, "16_30": 3, "61mais": 2})
        linhas = montar_sla({"analise": baldes}, {}, {"analise": 16})
        analise = next(l for l in linhas if l["macro_fase"] == "analise")

        # Limiar 16: as bandas `16-30`, `31-60` e `61+` contam. A `8-15`
        # não — e a que CONTÉM o limiar também não existe aqui, porque 16 é
        # exactamente uma fronteira.
        assert analise["acima_do_limiar"] == 5
        assert analise["limiar_dias"] == 16

    def test_sem_limiar_nao_inventa_atrasos(self):
        from services.stats_sla import montar_sla

        linhas = montar_sla({"analise": self._baldes(**{"61mais": 9})}, {}, {})
        analise = next(l for l in linhas if l["macro_fase"] == "analise")

        assert analise["limiar_dias"] is None
        assert analise["acima_do_limiar"] == 0

    def test_a_banda_mediana(self):
        """A mediana é uma BANDA e não um número: é o que se sabe."""
        from services.stats_sla import montar_sla

        baldes = self._baldes(**{"0_7": 1, "8_15": 1, "16_30": 8})
        linhas = montar_sla({"analise": baldes}, {}, {})
        analise = next(l for l in linhas if l["macro_fase"] == "analise")

        assert analise["banda_mediana_em_curso"] == "16-30"

    def test_a_media_nao_substitui_o_histograma(self):
        """O processo esquecido há 400 dias arrasta a média e a mediana
        mostra-o: os dois números vão, nunca só um."""
        from services.stats_sla import montar_sla

        baldes = [
            {"_id": 0, "processos": 9, "dias_medios": 5.0},
            {"_id": ETIQUETAS_DAS_BANDAS[-1], "processos": 1, "dias_medios": 400.0},
        ]
        linhas = montar_sla({"analise": baldes}, {}, {})
        analise = next(l for l in linhas if l["macro_fase"] == "analise")

        assert analise["dias_medios_em_curso"] > 40
        assert analise["banda_mediana_em_curso"] == "0-7"

    def test_o_historico_vem_em_dias_e_traz_a_amostra(self):
        from services.stats_sla import montar_sla

        linhas = montar_sla(
            {}, {"media_analise": 12 * 86400, "amostra_analise": 37}, {},
        )
        analise = next(l for l in linhas if l["macro_fase"] == "analise")

        assert analise["dias_medios_historico"] == 12.0
        assert analise["amostra_historico"] == 37

    def test_sem_historico_o_campo_e_none_e_nao_zero(self):
        """Zero dias e "não se sabe" são coisas diferentes."""
        from services.stats_sla import montar_sla

        linhas = montar_sla({}, {}, {})
        analise = next(l for l in linhas if l["macro_fase"] == "analise")

        assert analise["dias_medios_historico"] is None
        assert analise["amostra_historico"] == 0

    def test_so_as_macros_com_sla_aparecem(self):
        from services.stats_sla import montar_sla

        macros = {l["macro_fase"] for l in montar_sla({}, {}, {})}

        assert macros == set(MACROS_COM_SLA)


class TestLimiaresDoPainel:
    async def test_os_limiares_vem_da_configuracao(self):
        """Nunca do código — a mesma regra do `financial_simulator`."""
        import services.stats_sla as ssla
        from models.system_config import DashboardSlaConfig, SystemConfig

        config = SystemConfig()
        config.dashboard_slas = DashboardSlaConfig(analise=42)

        async def falsa():
            return config

        with patch("services.system_config.get_system_config", falsa):
            limiares = await ssla._limiares()

        assert limiares["analise"] == 42

    async def test_uma_falha_a_ler_nao_inventa_limiares(self):
        """Sem limiar, "acima do limiar" é zero — nunca um número inventado."""
        import services.stats_sla as ssla

        async def rebenta():
            raise RuntimeError("config em baixo")

        with patch("services.system_config.get_system_config", rebenta):
            assert await ssla._limiares() == {}

    def test_a_configuracao_nao_tem_limiar_para_as_terminais(self):
        from models.system_config import DashboardSlaConfig

        campos = set(DashboardSlaConfig.model_fields)

        assert "concluido" not in campos
        assert "perdido" not in campos
        assert {"novo", "analise", "aprovado"} <= campos

    async def test_um_limiar_invalido_cai_no_anterior(self):
        """Regra do `SMTP_CONNECT_TIMEOUT`: nunca desligar o limite.

        Os limiares chegam do formulário de admin como TEXTO. Um `int()`
        cru sobre "quinze" rebentava o endpoint de configuração inteiro; um
        `or 0` punha o limiar a zero e marcava todos os processos como
        atrasados. Cai no anterior, e regista.
        """
        import services.system_config as sc
        from models.system_config import SystemConfig

        config = SystemConfig()

        async def carregar(company_id="default"):
            return config

        with patch.object(sc, "get_system_config", carregar), \
             patch.object(sc, "save_system_config", AsyncMock(return_value=True)):
            actualizada = await sc.update_config_section(
                "dashboard_slas", {"analise": "quinze"},
            )

        assert actualizada.dashboard_slas.analise == 15

    async def test_um_limiar_valido_em_texto_e_aceite(self):
        """Contraprova: o formulário manda texto e o número tem de entrar."""
        import services.system_config as sc
        from models.system_config import SystemConfig

        config = SystemConfig()

        async def carregar(company_id="default"):
            return config

        with patch.object(sc, "get_system_config", carregar), \
             patch.object(sc, "save_system_config", AsyncMock(return_value=True)):
            actualizada = await sc.update_config_section(
                "dashboard_slas", {"analise": "21"},
            )

        assert actualizada.dashboard_slas.analise == 21

    async def test_um_limiar_de_zero_dias_nao_e_aceite(self):
        """Zero dias marcava TODOS os processos como atrasados no dia 1."""
        import services.system_config as sc
        from models.system_config import SystemConfig

        config = SystemConfig()

        async def carregar(company_id="default"):
            return config

        with patch.object(sc, "get_system_config", carregar), \
             patch.object(sc, "save_system_config", AsyncMock(return_value=True)):
            actualizada = await sc.update_config_section(
                "dashboard_slas", {"analise": 0},
            )

        assert actualizada.dashboard_slas.analise == 1


# ════════════════════════════════════════════════════════════════════
# A COMPARAÇÃO DE REDES
# ════════════════════════════════════════════════════════════════════

class TestComparacaoDeRedes:
    def test_agrupa_por_rede_e_macro(self):
        from services.stats_networks import montar_comparacao

        redes = montar_comparacao([
            {"_id": {"rede": REDE_DOMUS, "macro": "analise"}, "processos": 3},
            {"_id": {"rede": REDE_DOMUS, "macro": "concluido"}, "processos": 7},
            {"_id": {"rede": REDE_INCUMBENTE, "macro": "analise"}, "processos": 1},
        ])
        por_rede = {r["rede"]: r for r in redes}

        assert por_rede[REDE_DOMUS]["processos"] == 10
        assert por_rede[REDE_DOMUS]["concluidos"] == 7
        assert por_rede[REDE_INCUMBENTE]["processos"] == 1

    def test_a_taxa_e_sobre_os_DECIDIDOS(self):
        """Com o total no denominador, uma rede jovem com muitos processos
        em curso parecia pior do que uma antiga — mediria a idade da
        carteira, não a eficiência."""
        from services.stats_networks import montar_comparacao

        redes = montar_comparacao([
            {"_id": {"rede": "r1", "macro": "analise"}, "processos": 900},
            {"_id": {"rede": "r1", "macro": "concluido"}, "processos": 8},
            {"_id": {"rede": "r1", "macro": "perdido"}, "processos": 2},
        ])

        assert redes[0]["taxa_de_conclusao"] == 80.0

    def test_sem_decididos_a_taxa_e_none(self):
        from services.stats_networks import montar_comparacao

        redes = montar_comparacao([
            {"_id": {"rede": "r1", "macro": "novo"}, "processos": 5},
        ])

        assert redes[0]["taxa_de_conclusao"] is None

    def test_a_reconciliacao_nao_conta_como_em_curso(self):
        """Contá-la era afirmar algo que não se sabe sobre aqueles processos."""
        from services.stats_networks import montar_comparacao

        redes = montar_comparacao([
            {"_id": {"rede": "r1", "macro": "analise"}, "processos": 4},
            {"_id": {"rede": "r1", "macro": FASE_DESCONHECIDA}, "processos": 6},
        ])

        assert redes[0]["em_curso"] == 4
        assert redes[0]["desconhecidos"] == 6

    def test_a_pilha_por_carimbar_tem_grupo_proprio(self):
        from services.stats_networks import SEM_REDE, montar_comparacao

        redes = montar_comparacao([
            {"_id": {"rede": SEM_REDE, "macro": "novo"}, "processos": 2},
        ])

        assert redes[0]["rede"] == SEM_REDE

    def test_ordena_pela_dimensao(self):
        from services.stats_networks import montar_comparacao

        redes = montar_comparacao([
            {"_id": {"rede": "pequena", "macro": "novo"}, "processos": 1},
            {"_id": {"rede": "grande", "macro": "novo"}, "processos": 99},
        ])

        assert [r["rede"] for r in redes] == ["grande", "pequena"]


class TestRedesDePontaAPonta:
    async def _redes(self, db, user):
        import services.stats_macro_bridge as smb
        import services.stats_networks as sn
        import services.stats_scope as ss

        with tenant_db(db, sn, smb, ss):
            return await sn.run_get_network_comparison(dict(user))

    async def test_quem_esta_numa_rede_ve_UMA_linha(
        self, motor, rede_de_omissao_incumbente, sem_cache, pode_ver,
    ):
        """E isso é comportamento correcto, não falta de dados.

        "A Direção só poderá comparar a Domus e a Power se a conta de
        utilizador deles os credenciar nas três empresas. A segurança
        sobrepõe-se à vaidade do relatório."
        """
        motor.processes.docs.extend([
            {"id": "d-power", "status": "analise_documental",
             "network_id": REDE_INCUMBENTE},
            {"id": "d-domus", "status": "analise_documental",
             "network_id": REDE_DOMUS},
        ])

        saida = await self._redes(motor, BRUNO)
        redes = {r["rede"] for r in saida["redes"]}

        assert REDE_INCUMBENTE not in redes
        assert REDE_DOMUS in redes
        # O `(sem rede)` aparece porque o cenário partilhado tem um
        # processo da Domus com empresa e ainda SEM carimbo de rede — é
        # exactamente o grupo que existe para não o confundir com uma rede.
        assert redes <= {REDE_DOMUS, "(sem rede)"}
        assert saida["redes_no_ambito"] == 1

    async def test_quem_trabalha_nas_duas_redes_compara_as_duas(
        self, motor, rede_de_omissao_incumbente, sem_cache, pode_ver,
    ):
        """A Carla não é uma fuga: são os dois empregos dela."""
        motor.processes.docs.extend([
            {"id": "d-power", "status": "analise_documental",
             "network_id": REDE_INCUMBENTE},
            {"id": "d-domus", "status": "analise_documental",
             "network_id": REDE_DOMUS},
        ])

        saida = await self._redes(motor, CARLA)

        assert {r["rede"] for r in saida["redes"]} >= {REDE_DOMUS, REDE_INCUMBENTE}
        assert saida["redes_no_ambito"] >= 2

    async def test_nao_devolve_processos_nem_clientes(
        self, motor, rede_de_omissao_incumbente, sem_cache, pode_ver,
    ):
        """Só agregados. Uma comparação de eficiência não precisa de saber
        de QUEM é o processo — e se precisasse, não era uma comparação."""
        motor.processes.docs.append({
            "id": "d-domus", "status": "analise_documental",
            "network_id": REDE_DOMUS, "client_name": "Cliente Secreto",
        })

        saida = await self._redes(motor, BRUNO)
        texto = repr(saida)

        assert "Cliente Secreto" not in texto
        assert "d-domus" not in texto

        # E as CHAVES são uma lista fechada. A versão anterior deste teste
        # procurava duas cadeias de caracteres, e uma mutação que
        # acrescentasse as linhas cruas da agregação à resposta passava por
        # baixo — não por haver fuga (as linhas já são agregados), mas
        # porque procurar strings não afirma a forma da resposta. Uma lista
        # fechada apanha qualquer campo novo, incluindo um que alguém
        # acrescente "só para depurar".
        assert set(saida) == {"redes", "redes_no_ambito"}
        for linha in saida["redes"]:
            assert set(linha) == {
                "rede", "processos", "valor_financiado", "em_curso",
                "concluidos", "perdidos", "desconhecidos",
                "taxa_de_conclusao", "por_macro",
            }


# ════════════════════════════════════════════════════════════════════
# GUARDAS DO PONTO ÚNICO
# ════════════════════════════════════════════════════════════════════

class TestGuardas:
    @pytest.mark.parametrize("nome", ("stats_funnel", "stats_sla", "stats_networks"))
    def test_o_modulo_pede_o_ambito_ao_ponto_unico(self, nome):
        fonte = codigo_sem_comentarios(
            (RAIZ_BACKEND / "services" / f"{nome}.py").read_text(encoding="utf-8")
        )
        assert "from services.stats_scope import" in fonte, nome
        assert "resolver_ambito" in fonte, nome

    @pytest.mark.parametrize("nome", MODULOS_DE_BI)
    def test_o_modulo_nao_reconstroi_a_condicao_de_rede(self, nome):
        fonte = codigo_sem_comentarios(
            (RAIZ_BACKEND / "services" / f"{nome}.py").read_text(encoding="utf-8")
        )
        assert "build_network_scope_condition" not in fonte, nome
        # O `stats_networks` agrupa PELO campo e por isso menciona-o; os
        # outros não têm razão nenhuma para o escrever.
        if nome != "stats_networks":
            assert '"network_id"' not in fonte, nome

    @pytest.mark.parametrize("nome", ("stats_funnel", "stats_sla", "stats_networks"))
    def test_o_modulo_usa_a_ponte_e_nao_reimplementa_o_resolvedor(self, nome):
        fonte = codigo_sem_comentarios(
            (RAIZ_BACKEND / "services" / f"{nome}.py").read_text(encoding="utf-8")
        )
        assert "construir_ponte" in fonte, nome
        assert "resolver_nome" not in fonte, nome

    def test_a_ponte_usa_mesmo_o_resolvedor(self):
        """Contraprova: sem isto, uma ponte vazia satisfazia tudo acima."""
        fonte = codigo_sem_comentarios(
            (RAIZ_BACKEND / "services" / "stats_macro_bridge.py").read_text(
                encoding="utf-8",
            )
        )
        assert "resolver_muitos" in fonte
        assert "macro_da_fase" in fonte

    def test_os_limiares_nao_estao_cravados_no_codigo(self):
        """Guarda sobre o código-fonte: nenhum número de dias literal."""
        import ast

        fonte = (RAIZ_BACKEND / "services" / "stats_sla.py").read_text(encoding="utf-8")
        arvore = ast.parse(fonte)

        # Um dicionário de limiares escrito à mão seria `{"analise": 15}`.
        for no in ast.walk(arvore):
            if not isinstance(no, ast.Dict):
                continue
            chaves = {
                k.value for k in no.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            }
            assert not (chaves & set(MACROS_COM_SLA)), (
                "limiares de SLA escritos à mão em `stats_sla.py`"
            )

    @pytest.mark.parametrize("rota", ("/stats/funil", "/stats/sla", "/stats/redes"))
    def test_a_rota_existe_e_e_de_staff(self, rota):
        fonte = (RAIZ_BACKEND / "routes" / "stats.py").read_text(encoding="utf-8")

        assert f'"{rota}"' in fonte
        assert "require_staff()" in fonte


# ════════════════════════════════════════════════════════════════════
# O FILTRO POR CONSULTOR E AS PRIORIDADES
# ════════════════════════════════════════════════════════════════════

class TestFiltroPorConsultor:
    def _ambito(self):
        from services.stats_scope import AmbitoEstatistico
        from services.tenant_network import TenantScope

        return AmbitoEstatistico(
            scope=TenantScope(network_ids=(REDE_DOMUS,)),
            condicao={"network_id": {"$in": [REDE_DOMUS]}},
            sufixo="a1" + "0" * 16,
        )

    def test_sem_consultor_e_so_o_ambito(self):
        from services.stats_funnel import construir_correspondencia

        correspondencia = construir_correspondencia(self._ambito())

        assert "$and" in correspondencia
        assert "assigned_consultor_id" not in repr(correspondencia)

    def test_com_consultor_usa_a_condicao_CANONICA(self):
        """A página filtrava no cliente por `p.assigned_consultor`, um campo
        que NÃO existe nos processos — escolher um utilizador esvaziava
        todos os gráficos sem dar erro."""
        from services.stats_funnel import construir_correspondencia

        texto = repr(construir_correspondencia(self._ambito(), "u-2"))

        # Os campos canónicos E os legados, todos.
        for campo in ("assigned_consultor_id", "consultant_id", "consultor_id"):
            assert campo in texto
        assert "assigned_consultor" in texto
        assert REDE_DOMUS in texto

    @pytest.mark.parametrize("sentinela", ["", "  ", "all", None])
    def test_os_sentinelas_nao_filtram(self, sentinela):
        """`"all"` é o valor que o `<Select>` manda para "todos"."""
        from services.stats_funnel import construir_correspondencia

        texto = repr(construir_correspondencia(self._ambito(), sentinela))

        assert "assigned_consultor_id" not in texto

    def test_a_rede_continua_a_aplicar_se_com_o_filtro(self):
        """O filtro por pessoa ACRESCENTA; nunca substitui a fronteira."""
        from services.stats_funnel import construir_correspondencia

        correspondencia = construir_correspondencia(self._ambito(), "u-2")

        assert REDE_DOMUS in repr(correspondencia["$and"][0])

    async def test_a_chave_de_cache_distingue_o_consultor(
        self, motor, rede_de_omissao_incumbente, pode_ver,
    ):
        """Sem isto, o primeiro pedido filtrado servia os números de uma
        pessoa a toda a gente durante 15 minutos."""
        import services.stats_funnel as sf
        import services.stats_macro_bridge as smb
        import services.stats_scope as ss

        chaves = []

        async def cache_get(chave, *a, **k):
            chaves.append(chave)
            return None

        with tenant_db(motor, sf, smb, ss):
            with patch.object(sf, "cache_get", cache_get), \
                 patch.object(sf, "cache_set", AsyncMock(return_value=True)):
                await sf.run_get_funnel(dict(BRUNO))
                await sf.run_get_funnel(dict(BRUNO), consultor_id="u-2")

        assert chaves[0] != chaves[1]
        assert chaves[1].endswith(":c=u-2")


class TestPrioridades:
    def test_o_campo_canonico_e_prioridade_em_portugues(self):
        """A página contava `p.priority === 'high'` — outro campo, outros
        valores. O gráfico de prioridades mostrava zero desde sempre."""
        from services.process_update import VALID_PRIORIDADES
        from services.stats_funnel import PRIORIDADES

        assert set(PRIORIDADES) == set(VALID_PRIORIDADES)

    def test_o_group_e_sobre_prioridade(self):
        from services.stats_funnel import construir_pipeline_de_prioridade
        from services.stats_scope import AmbitoEstatistico
        from services.tenant_network import TenantScope

        ambito = AmbitoEstatistico(
            scope=TenantScope(network_ids=(REDE_DOMUS,)),
            condicao={"network_id": {"$in": [REDE_DOMUS]}},
            sufixo="a1" + "0" * 16,
        )
        pipeline = construir_pipeline_de_prioridade(ambito)

        assert pipeline[-1]["$group"]["_id"] == "$prioridade"
        assert "$ifNull" in repr(pipeline[1]["$project"])
        assert REDE_DOMUS in repr(pipeline[0]["$match"])

    def test_conta_as_tres_e_a_ausencia(self):
        from services.stats_funnel import montar_prioridades

        contagens = montar_prioridades([
            {"_id": "alta", "processos": 4},
            {"_id": "baixa", "processos": 7},
            {"_id": "sem", "processos": 37},
        ])

        assert contagens == {"alta": 4, "media": 0, "baixa": 7, "sem": 37}

    def test_um_valor_legado_desconhecido_cai_em_sem(self):
        """Não se inventa uma fatia nova para uma gralha de dados legados."""
        from services.stats_funnel import montar_prioridades

        contagens = montar_prioridades([
            {"_id": "high", "processos": 5},
            {"_id": None, "processos": 2},
        ])

        assert contagens["sem"] == 7
        assert contagens["alta"] == 0

    async def test_o_funil_traz_as_prioridades(
        self, motor, rede_de_omissao_incumbente, sem_cache, pode_ver,
    ):
        import services.stats_funnel as sf
        import services.stats_macro_bridge as smb
        import services.stats_scope as ss

        motor.processes.docs.extend([
            {"id": "pa", "status": "analise_documental",
             "network_id": REDE_DOMUS, "prioridade": "alta"},
            {"id": "pb", "status": "analise_documental",
             "network_id": REDE_DOMUS, "prioridade": "alta"},
            {"id": "pc", "status": "analise_documental",
             "network_id": REDE_DOMUS},
        ])

        with tenant_db(motor, sf, smb, ss):
            funil = await sf.run_get_funnel(dict(BRUNO))

        assert funil["por_prioridade"]["alta"] == 2
        assert funil["por_prioridade"]["sem"] >= 1
