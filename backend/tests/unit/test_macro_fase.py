"""A macro-fase: enum fechado, backfill idempotente, leitura oficial.

ÉPICO 10, PARTE 2.

O campo `workflow_statuses.macro_fase` passou a existir. É ele que o
funil de negócio e o Portal lêem, e o administrador edita-o no
WorkflowEditor por um `<Select>` fechado.

PORQUE É QUE O ENUM É FECHADO
  Texto livre criaria um grupo novo com uma gralha — `aprovdo` — e o
  funil partia-se em silêncio: os processos dessa fase saíam do grupo
  certo e apareciam num grupo de um só, com ar de categoria legítima. É
  a lição do Campo de Rede (Lote 5, ponto 2), e aqui há duas defesas: o
  Pydantic recusa ao gravar e o `macro_da_fase` ignora ao ler.
"""
import pathlib

import pytest
from pydantic import ValidationError

from models.workflow import (
    MacroFase,
    WorkflowStatusCreate,
    WorkflowStatusResponse,
    WorkflowStatusUpdate,
)
from services.workflow_phases import (
    MACRO_FASES_VALIDAS,
    MACRO_FASE_POR_OMISSAO,
    ensure_macro_fase_backfill,
    macro_da_fase,
    nomes_por_macro,
)


def fase(nome, **extra):
    # `color` faz parte do contrato do `WorkflowStatusResponse`: um doc
    # sem ele faz o handler de actualização levantar ValidationError ao
    # devolver a fase. Construir fases incompletas nos testes esconderia
    # isso — a lição do Lote 5, ponto 4 (usar os construtores reais).
    base = {
        "id": nome, "name": nome, "label": nome.title(),
        "order": 1, "color": "blue",
    }
    base.update(extra)
    return base


# ====================================================================
# O ENUM FECHADO
# ====================================================================

class TestOEnumNoModelo:
    @pytest.mark.parametrize("valida", ["novo", "analise", "aprovado",
                                        "concluido", "perdido"])
    def test_aceita_os_cinco(self, valida):
        criado = WorkflowStatusCreate(
            name="x", label="X", order=1, macro_fase=valida,
        )
        assert criado.macro_fase == valida

    @pytest.mark.parametrize("invalida", [
        "aprovdo", "Aprovado", "APROVADO", "ganho", "novo ", "",
    ])
    def test_recusa_tudo_o_resto(self, invalida):
        """O Pydantic recusa ANTES de chegar à base de dados."""
        with pytest.raises(ValidationError):
            WorkflowStatusCreate(
                name="x", label="X", order=1, macro_fase=invalida,
            )

    def test_o_update_recusa_igual(self):
        with pytest.raises(ValidationError):
            WorkflowStatusUpdate(macro_fase="quase_aprovado")

    def test_sem_macro_fase_e_valido(self):
        """`None` é uma resposta: cai em «Outras fases», não desaparece."""
        assert WorkflowStatusCreate(name="x", label="X", order=1).macro_fase is None

    def test_a_resposta_leva_o_campo_ate_ao_frontend(self):
        resposta = WorkflowStatusResponse(
            id="1", name="concluidos", label="Concluídos", order=13,
            color="green", macro_fase="concluido",
        )
        assert resposta.macro_fase == MacroFase.CONCLUIDO

    def test_o_resolvedor_e_o_modelo_declaram_o_mesmo_conjunto(self):
        """Duas cópias divergiriam — e a divergência seria o Pydantic a
        recusar um valor que o resolvedor aceita, ou o contrário."""
        assert set(MACRO_FASES_VALIDAS) == {m.value for m in MacroFase}

    def test_o_mixin_str_nao_pode_desaparecer_da_declaracao(self):
        """Tirar `str` do Enum é uma linha inocente que parte tudo.

        Sem o mixin, `MacroFase.NOVO == "novo"` passa a False e o
        agrupamento deixa de casar — sem erro nenhum.
        """
        assert issubclass(MacroFase, str)
        assert MacroFase.NOVO == "novo"
        assert MacroFase.NOVO in {"novo"}


class TestLerAMacroFase:
    def test_o_campo_do_motor_ganha_a_omissao(self):
        """Senão a UI de edição era decorativa."""
        assert macro_da_fase(fase("concluidos", macro_fase="perdido")) == "perdido"

    def test_sem_campo_recorre_a_omissao(self):
        assert macro_da_fase(fase("concluidos")) == "concluido"

    def test_um_membro_do_enum_sai_como_str(self):
        """O documento pode vir do Pydantic; daqui sai sempre `str`."""
        resultado = macro_da_fase(fase("x", macro_fase=MacroFase.APROVADO))
        assert resultado == "aprovado"
        assert type(resultado) is str

    def test_um_valor_fora_do_enum_e_ignorado(self):
        """Defesa de LEITURA, a par da do Pydantic: um documento antigo
        pode trazer um valor que o modelo de hoje recusaria."""
        assert macro_da_fase(fase("fase_nova", macro_fase="inventado")) is None

    def test_ignorado_mesmo_havendo_omissao_a_que_recorrer(self):
        assert macro_da_fase(fase("concluidos", macro_fase="inventado")) == "concluido"

    @pytest.mark.parametrize("lixo", [None, "", {}, {"name": None}])
    def test_nao_rebenta_com_lixo(self, lixo):
        assert macro_da_fase(lixo) is None


# ====================================================================
# O BACKFILL
# ====================================================================

class TestBackfillIdempotente:
    async def test_semeia_as_fases_sem_classificacao(self, fake_async_db, monkeypatch):
        import services.workflow_phases as wp

        monkeypatch.setattr(wp, "db", fake_async_db)
        await fake_async_db.workflow_statuses.insert_many([
            fase("clientes_espera"), fase("concluidos"), fase("desistencias"),
        ])

        resumo = await ensure_macro_fase_backfill()
        assert resumo["escritas"] == 3

        gravadas = {
            d["name"]: d.get("macro_fase")
            for d in await fake_async_db.workflow_statuses.find({}).to_list(10)
        }
        assert gravadas == {
            "clientes_espera": "novo",
            "concluidos": "concluido",
            "desistencias": "perdido",
        }

    async def test_correr_duas_vezes_nao_escreve_nada_na_segunda(
        self, fake_async_db, monkeypatch,
    ):
        import services.workflow_phases as wp

        monkeypatch.setattr(wp, "db", fake_async_db)
        await fake_async_db.workflow_statuses.insert_one(fase("clientes_espera"))

        primeira = await ensure_macro_fase_backfill()
        segunda = await ensure_macro_fase_backfill()
        assert primeira["escritas"] == 1
        assert segunda["escritas"] == 0
        assert segunda["ja_classificadas"] == 1

    async def test_nunca_desfaz_uma_decisao_do_administrador(
        self, fake_async_db, monkeypatch,
    ):
        """É isto que torna seguro chamá-lo em TODOS os arranques.

        O admin decidiu que `concluidos` é «perdido». Um backfill que
        lhe passasse por cima repunha a omissão a cada reinício do
        servidor — e ninguém perceberia porquê.
        """
        import services.workflow_phases as wp

        monkeypatch.setattr(wp, "db", fake_async_db)
        await fake_async_db.workflow_statuses.insert_one(
            fase("concluidos", macro_fase="perdido"),
        )

        resumo = await ensure_macro_fase_backfill()
        assert resumo["escritas"] == 0

        doc = await fake_async_db.workflow_statuses.find_one({"name": "concluidos"})
        assert doc["macro_fase"] == "perdido"

    async def test_o_que_o_mapa_nao_cobre_fica_por_classificar(
        self, fake_async_db, monkeypatch,
    ):
        """Inventar um grupo seria pior do que não ter nenhum."""
        import services.workflow_phases as wp

        monkeypatch.setattr(wp, "db", fake_async_db)
        await fake_async_db.workflow_statuses.insert_one(fase("fase_do_admin"))

        resumo = await ensure_macro_fase_backfill()
        assert resumo["escritas"] == 0
        assert resumo["sem_proposta"] == ["fase_do_admin"]

        doc = await fake_async_db.workflow_statuses.find_one({"name": "fase_do_admin"})
        assert doc.get("macro_fase") is None

    async def test_as_fases_de_producao_sao_semeadas(
        self, fake_async_db, monkeypatch,
    ):
        """`renegociacao` e `pausa_cliente`, vistas no retrato."""
        import services.workflow_phases as wp

        monkeypatch.setattr(wp, "db", fake_async_db)
        await fake_async_db.workflow_statuses.insert_many([
            fase("renegociacao"), fase("pausa_cliente"),
        ])
        await ensure_macro_fase_backfill()
        for nome in ("renegociacao", "pausa_cliente"):
            doc = await fake_async_db.workflow_statuses.find_one({"name": nome})
            assert doc["macro_fase"] == "analise"

    async def test_uma_base_vazia_nao_rebenta(self, fake_async_db, monkeypatch):
        import services.workflow_phases as wp

        monkeypatch.setattr(wp, "db", fake_async_db)
        assert (await ensure_macro_fase_backfill())["escritas"] == 0

    async def test_uma_leitura_falhada_nao_propaga(self, monkeypatch):
        """Um arranque não pode falhar por causa disto."""
        import services.workflow_phases as wp

        class BDPartida:
            def __getattr__(self, _):
                raise RuntimeError("Mongo em baixo")

        monkeypatch.setattr(wp, "db", BDPartida())
        assert (await ensure_macro_fase_backfill())["escritas"] == 0

    def test_o_mapa_so_propoe_valores_do_enum(self):
        """Uma proposta fora do enum semearia um valor que o modelo
        recusa — gravado pelo arranque e impossível de editar na UI."""
        assert set(MACRO_FASE_POR_OMISSAO.values()) <= set(MACRO_FASES_VALIDAS)


# ====================================================================
# OS HANDLERS QUE GRAVAM
# ====================================================================

class TestOAdminGrava:
    """Sobreviveram DUAS mutações aqui (N8 e N9).

    Testei o modelo e testei o resolvedor, e não testei a costura: o
    handler que pega no que o Pydantic validou e o põe na base de dados.
    Entre os dois há duas maneiras de falhar em silêncio — gravar o
    membro do Enum em vez do valor, e ignorar o campo no update.
    """

    async def test_criar_grava_a_str_e_nao_o_membro_do_enum(
        self, fake_async_db, monkeypatch,
    ):
        """O que fica gravado tem de ser igual ao que vem da BD nos
        outros sítios. Um membro do Enum passa pelo `str` do mixin e
        engana o olho, mas o que sai do Mongo noutra leitura é `str`."""
        import services.admin_workflow as aw

        monkeypatch.setattr(aw, "db", fake_async_db)
        await aw.run_create_workflow_status(
            WorkflowStatusCreate(
                name="fase_nova", label="Fase Nova", order=9,
                macro_fase="aprovado",
            ),
            {"id": "u1", "name": "Admin"},
        )
        doc = await fake_async_db.workflow_statuses.find_one({"name": "fase_nova"})
        assert doc["macro_fase"] == "aprovado"
        assert type(doc["macro_fase"]) is str

    async def test_criar_sem_grupo_grava_none(self, fake_async_db, monkeypatch):
        import services.admin_workflow as aw

        monkeypatch.setattr(aw, "db", fake_async_db)
        await aw.run_create_workflow_status(
            WorkflowStatusCreate(name="sem_grupo", label="Sem Grupo", order=1),
            {"id": "u1", "name": "Admin"},
        )
        doc = await fake_async_db.workflow_statuses.find_one({"name": "sem_grupo"})
        assert doc["macro_fase"] is None

    async def test_actualizar_grava_a_reclassificacao(
        self, fake_async_db, monkeypatch,
    ):
        """Sem isto, o `<Select>` da UI era decorativo: o administrador
        escolhia, gravava, recebia 200 — e nada mudava."""
        import services.admin_workflow as aw

        monkeypatch.setattr(aw, "db", fake_async_db)
        await fake_async_db.workflow_statuses.insert_one(
            fase("concluidos", macro_fase="concluido"),
        )
        await aw.run_update_workflow_status(
            "concluidos",
            WorkflowStatusUpdate(macro_fase="perdido"),
            {"id": "u1", "name": "Admin"},
        )
        doc = await fake_async_db.workflow_statuses.find_one({"name": "concluidos"})
        assert doc["macro_fase"] == "perdido"
        assert type(doc["macro_fase"]) is str

    async def test_actualizar_sem_macro_fase_nao_apaga_a_que_la_esta(
        self, fake_async_db, monkeypatch,
    ):
        """Actualização PARCIAL: mudar a cor não desclassifica a fase."""
        import services.admin_workflow as aw

        monkeypatch.setattr(aw, "db", fake_async_db)
        await fake_async_db.workflow_statuses.insert_one(
            fase("concluidos", macro_fase="concluido"),
        )
        await aw.run_update_workflow_status(
            "concluidos",
            WorkflowStatusUpdate(color="red"),
            {"id": "u1", "name": "Admin"},
        )
        doc = await fake_async_db.workflow_statuses.find_one({"name": "concluidos"})
        assert doc["macro_fase"] == "concluido"
        assert doc["color"] == "red"


class TestAGuardaDeCorridaDoBackfill:
    """TRIAGEM HONESTA de uma mutação sobrevivente (N6).

    A condição de ausência está na QUERY do `update_one` e não só no `if`
    em Python. Tirá-la não muda nada num teste: a corrida que ela evita —
    o administrador a gravar entre a leitura e a escrita do backfill — não
    se reproduz num só fio de execução.

    Não é um teste fraco nem código morto: é uma guarda cujo efeito só
    existe sob concorrência. O que se pode afirmar é que a condição vai
    mesmo na query, e é isso que se afirma — dizendo-o.
    """

    def test_a_condicao_de_ausencia_vai_na_query(self):
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        fonte = codigo_da_funcao_sem_comentarios(ensure_macro_fase_backfill)
        assert "'$exists': False" in fonte or '"$exists": False' in fonte
        assert "update_one" in fonte

    def test_contraprova_o_backfill_escreve_mesmo(self):
        """Sem isto, um backfill que não escrevesse nada passava acima."""
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        fonte = codigo_da_funcao_sem_comentarios(ensure_macro_fase_backfill)
        assert "'macro_fase': proposta" in fonte or '"macro_fase": proposta' in fonte


# ====================================================================
# LEITURA OFICIAL
# ====================================================================

class TestQuemLe:
    MOTOR = [
        fase("clientes_espera", macro_fase="novo"),
        fase("fase_bancaria", macro_fase="analise"),
        fase("ch_aprovado", macro_fase="aprovado"),
        fase("concluidos", macro_fase="concluido", is_active=False),
        fase("desistencias", macro_fase="perdido", is_active=False),
    ]

    def test_o_bi_agrupa_pelo_campo_e_nao_pelo_nome(self):
        assert nomes_por_macro(self.MOTOR, "concluido") == ["concluidos"]
        assert nomes_por_macro(self.MOTOR, "perdido") == ["desistencias"]

    def test_uma_reclassificacao_do_admin_muda_o_bi(self):
        motor = [fase("concluidos", macro_fase="perdido", is_active=False)]
        assert nomes_por_macro(motor, "concluido") == []
        assert nomes_por_macro(motor, "perdido") == ["concluidos"]

    def test_o_enum_do_backend_e_o_select_do_frontend_sao_o_mesmo(self):
        """A paridade que nenhuma das duas linguagens consegue impor.

        O `<Select>` do WorkflowEditor e o enum `MacroFase` são a mesma
        lista escrita duas vezes. Se divergirem, o administrador escolhe
        um grupo na UI e leva um 422 ao gravar — ou, pior, um grupo
        válido no backend deixa de estar disponível na UI e ninguém
        percebe porque é que aquela fase não se consegue classificar.
        """
        import re

        raiz = pathlib.Path(__file__).resolve().parents[3]
        editor = (
            raiz / "frontend" / "src" / "components" / "WorkflowEditor.js"
        ).read_text(encoding="utf-8")
        bloco = re.search(r"const macroFaseOptions = \[([\s\S]*?)\];", editor)
        assert bloco, "o `macroFaseOptions` mudou de forma — rever esta guarda"
        do_frontend = re.findall(r'value:\s*"([^"]+)"', bloco.group(1))

        assert do_frontend == [m.value for m in MacroFase]

    def test_o_funil_do_frontend_declara_os_mesmos_grupos(self):
        import re

        raiz = pathlib.Path(__file__).resolve().parents[3]
        funil = (
            raiz / "frontend" / "src" / "utils" / "funilDeFases.js"
        ).read_text(encoding="utf-8")
        bloco = re.search(r"export const MACRO_FASES = \[([\s\S]*?)\];", funil)
        assert bloco, "o `MACRO_FASES` mudou de forma — rever esta guarda"
        chaves = re.findall(r'key:\s*"([^"]+)"', bloco.group(1))

        assert chaves == [m.value for m in MacroFase]

    def test_o_portal_expoe_o_mesmo_campo(self):
        """Uma segunda classificação no Portal divergiria da interna."""
        import inspect

        from services.portal_status import run_get_portal_status

        fonte = inspect.getsource(run_get_portal_status)
        assert '"macro_fase": macro_da_fase(status)' in fonte
        assert '"macro_fase": current_macro_fase' in fonte
