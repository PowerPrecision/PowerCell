"""Presença global: a falésia dos dois workers, simulada.

LIMPEZA ESTRUTURAL, PONTOS 2 e 3.

O DEFEITO, EM UMA FRASE
  `manager.is_user_connected` responde pela memória DESTE processo. Com
  `UVICORN_WORKERS=2`, um utilizador com o socket no worker B lê-se como
  desligado no worker A — e leva um push no telemóvel **enquanto está a
  olhar para a aplicação**.

COMO É QUE ISTO SE TESTA SEM DOIS PROCESSOS
  Não se simula o processo: simula-se o que o distingue. Cada worker tem
  o SEU `ConnectionManager` e os dois partilham UM Redis. Trocar qual
  dos dois está "activo" é exactamente a diferença entre atender o
  pedido no worker A ou no worker B — e é a única coisa que o defeito
  dependia.
"""
import time

import pytest

import services.presenca as presenca


# ====================================================================
# O REDIS FALSO — só o que o ZSET precisa
# ====================================================================

class RedisFalso:
    """ZSET em memória, partilhado pelos "workers" do teste.

    Implementa a semântica que o serviço usa, não a do Redis inteiro:
    `zadd` substitui o score, `zrangebyscore` é inclusivo, `zscore`
    devolve `None` para quem não existe.
    """

    def __init__(self):
        self.zset: dict[str, float] = {}
        self.chamadas: list[str] = []   # para contar idas ao Redis
        self.rebenta = False

    def _talvez_rebentar(self):
        if self.rebenta:
            raise RuntimeError("Redis em baixo")

    async def zadd(self, chave, mapa):
        self.chamadas.append("zadd")
        self._talvez_rebentar()
        self.zset.update(mapa)
        return len(mapa)

    async def zscore(self, chave, membro):
        self.chamadas.append("zscore")
        self._talvez_rebentar()
        return self.zset.get(membro)

    async def zrangebyscore(self, chave, minimo, maximo):
        self.chamadas.append("zrangebyscore")
        self._talvez_rebentar()
        lo = float("-inf") if minimo in ("-inf",) else float(minimo)
        hi = float("inf") if maximo in ("+inf",) else float(maximo)
        return sorted(m for m, s in self.zset.items() if lo <= s <= hi)

    async def zremrangebyscore(self, chave, minimo, maximo):
        self.chamadas.append("zremrangebyscore")
        self._talvez_rebentar()
        lo = float("-inf") if minimo in ("-inf",) else float(minimo)
        hi = float("inf") if maximo in ("+inf",) else float(maximo)
        saem = [m for m, s in self.zset.items() if lo <= s <= hi]
        for m in saem:
            del self.zset[m]
        return len(saem)


class ManagerFalso:
    """O `ConnectionManager` de UM worker: só sabe das suas ligações."""

    def __init__(self, ligados=()):
        self.ligados = set(ligados)

    def is_user_connected(self, user_id):
        return user_id in self.ligados

    def get_connected_users(self):
        return list(self.ligados)


@pytest.fixture
def redis_partilhado(monkeypatch):
    falso = RedisFalso()

    async def _cliente():
        return falso

    monkeypatch.setattr(presenca, "_cliente", _cliente)
    return falso


@pytest.fixture
def sem_redis(monkeypatch):
    async def _cliente():
        return None

    monkeypatch.setattr(presenca, "_cliente", _cliente)


def no_worker(monkeypatch, manager):
    """Faz o processo do teste comportar-se como ESTE worker."""
    import services.websocket_manager as wm

    monkeypatch.setattr(wm, "manager", manager)


# ====================================================================
# A FALÉSIA
# ====================================================================

class TestAFalesiaDosDoisWorkers:
    async def test_sem_redis_o_worker_A_nao_ve_quem_esta_no_worker_B(
        self, sem_redis, monkeypatch,
    ):
        """O defeito, afirmado. Sem isto não há prova de que existia."""
        worker_b = ManagerFalso(ligados={"u-ana"})
        worker_a = ManagerFalso(ligados=set())

        no_worker(monkeypatch, worker_b)
        assert await presenca.esta_online("u-ana") is True

        no_worker(monkeypatch, worker_a)
        assert await presenca.esta_online("u-ana") is False   # a mentira

    async def test_com_redis_o_worker_A_ve_quem_esta_no_worker_B(
        self, redis_partilhado, monkeypatch,
    ):
        """A correcção: a Ana liga-se ao worker B; o worker A sabe."""
        worker_b = ManagerFalso(ligados={"u-ana"})
        worker_a = ManagerFalso(ligados=set())

        no_worker(monkeypatch, worker_b)
        await presenca.marcar_online("u-ana")

        no_worker(monkeypatch, worker_a)
        assert await presenca.esta_online("u-ana") is True

    async def test_quem_nunca_se_ligou_continua_offline(
        self, redis_partilhado, monkeypatch,
    ):
        """Contraprova: um `esta_online` que dissesse sempre True
        satisfazia o teste acima."""
        no_worker(monkeypatch, ManagerFalso())
        assert await presenca.esta_online("u-fantasma") is False

    async def test_o_worker_local_ganha_a_um_redis_que_ainda_nao_sabe(
        self, redis_partilhado, monkeypatch,
    ):
        """Uma ligação acabada de abrir cuja escrita no Redis falhou.

        Dizer "offline" mandava push a quem está mesmo online — e é
        precisamente o defeito que isto veio corrigir.
        """
        no_worker(monkeypatch, ManagerFalso(ligados={"u-ana"}))
        assert redis_partilhado.zset == {}
        assert await presenca.esta_online("u-ana") is True


# ====================================================================
# O TTL
# ====================================================================

class TestExpiracao:
    async def test_marcar_online_grava_com_expiracao_futura(
        self, redis_partilhado, monkeypatch,
    ):
        no_worker(monkeypatch, ManagerFalso())
        antes = time.time()
        await presenca.marcar_online("u-ana")
        score = redis_partilhado.zset["u-ana"]
        assert antes + presenca.TTL_SEGUNDOS - 1 <= score <= time.time() + presenca.TTL_SEGUNDOS

    async def test_passado_o_ttl_deixa_de_estar_online(
        self, redis_partilhado, monkeypatch,
    ):
        no_worker(monkeypatch, ManagerFalso())
        await presenca.marcar_online("u-ana")

        relogio = [time.time() + presenca.TTL_SEGUNDOS + 1]
        monkeypatch.setattr(presenca, "_agora", lambda: relogio[0])
        assert await presenca.esta_online("u-ana") is False

    async def test_o_batimento_renova(self, redis_partilhado, monkeypatch):
        """O `ping` de 30s do cliente é o que mantém a presença viva."""
        no_worker(monkeypatch, ManagerFalso())
        relogio = [time.time()]
        monkeypatch.setattr(presenca, "_agora", lambda: relogio[0])

        await presenca.marcar_online("u-ana")
        relogio[0] += presenca.TTL_SEGUNDOS - 10     # quase a expirar
        await presenca.marcar_online("u-ana")        # batimento
        relogio[0] += presenca.TTL_SEGUNDOS - 10
        assert await presenca.esta_online("u-ana") is True

    async def test_o_ttl_tolera_um_ping_perdido(self):
        """90s = 3× o batimento de 30s do `useWebSocket`."""
        assert presenca.TTL_SEGUNDOS >= 90

    async def test_a_desconexao_NAO_remove_do_zset(
        self, redis_partilhado, monkeypatch,
    ):
        """Decisão de desenho, afirmada.

        Se o worker A removesse ao fechar o seu socket, o worker B — que
        ainda tem um separador aberto — só repunha no batimento
        seguinte, e nesse intervalo o utilizador apanhava push estando
        online. Deixar expirar é o erro para o lado seguro.
        """
        worker_a = ManagerFalso(ligados={"u-ana"})
        no_worker(monkeypatch, worker_a)
        await presenca.marcar_online("u-ana")

        worker_a.ligados.clear()                     # o separador fechou
        assert "u-ana" in redis_partilhado.zset
        assert await presenca.esta_online("u-ana") is True

    async def test_a_higiene_remove_os_expirados(
        self, redis_partilhado, monkeypatch,
    ):
        no_worker(monkeypatch, ManagerFalso())
        redis_partilhado.zset["u-velho"] = time.time() - 1
        redis_partilhado.zset["u-novo"] = time.time() + 999

        assert await presenca.limpar_expirados() == 1
        assert list(redis_partilhado.zset) == ["u-novo"]


# ====================================================================
# O LOTE — era N idas ao Redis, é uma
# ====================================================================

class TestLeituraEmLote:
    async def test_cinquenta_utilizadores_custam_UMA_chamada(
        self, redis_partilhado, monkeypatch,
    ):
        """`chat_presence` perguntava um a um DENTRO do ciclo."""
        no_worker(monkeypatch, ManagerFalso())
        for i in range(50):
            await presenca.marcar_online(f"u{i}")
        redis_partilhado.chamadas.clear()

        online = await presenca.online_entre(f"u{i}" for i in range(50))

        assert len(online) == 50
        assert redis_partilhado.chamadas.count("zrangebyscore") == 1
        assert "zscore" not in redis_partilhado.chamadas

    async def test_devolve_so_os_pedidos(self, redis_partilhado, monkeypatch):
        no_worker(monkeypatch, ManagerFalso())
        await presenca.marcar_online("u-ana")
        await presenca.marcar_online("u-bruno")
        assert await presenca.online_entre(["u-ana", "u-carla"]) == {"u-ana"}

    async def test_junta_quem_esta_ligado_localmente(
        self, redis_partilhado, monkeypatch,
    ):
        """Mesmo caso do `esta_online`: ligado aqui, ainda não no Redis."""
        no_worker(monkeypatch, ManagerFalso(ligados={"u-carla"}))
        await presenca.marcar_online("u-ana")
        assert await presenca.online_entre(["u-ana", "u-carla"]) == {"u-ana", "u-carla"}

    async def test_lista_vazia_nao_vai_ao_redis(
        self, redis_partilhado, monkeypatch,
    ):
        no_worker(monkeypatch, ManagerFalso())
        redis_partilhado.chamadas.clear()
        assert await presenca.online_entre([]) == set()
        assert redis_partilhado.chamadas == []

    async def test_ids_vazios_sao_ignorados(self, redis_partilhado, monkeypatch):
        no_worker(monkeypatch, ManagerFalso())
        assert await presenca.online_entre([None, "", "  "]) == set()

    async def test_todos_online_une_o_redis_e_o_local(
        self, redis_partilhado, monkeypatch,
    ):
        no_worker(monkeypatch, ManagerFalso(ligados={"u-local"}))
        await presenca.marcar_online("u-remoto")
        assert await presenca.todos_online() == {"u-remoto", "u-local"}


# ====================================================================
# DEGRADAÇÃO: ABERTA, E DE PROPÓSITO
# ====================================================================

class TestDegradacao:
    """Presença NÃO é fronteira de segurança: nenhum dado muda de dono
    por causa dela. Uma leitura falhada que respondesse "ninguém está
    online" partia o Chat e enchia telemóveis de push."""

    async def test_sem_redis_responde_a_memoria_local(
        self, sem_redis, monkeypatch,
    ):
        no_worker(monkeypatch, ManagerFalso(ligados={"u-ana"}))
        assert await presenca.esta_online("u-ana") is True
        assert await presenca.online_entre(["u-ana", "u-bruno"]) == {"u-ana"}
        assert await presenca.todos_online() == {"u-ana"}

    async def test_um_redis_que_REBENTA_tambem_recai_no_local(
        self, redis_partilhado, monkeypatch,
    ):
        """Não basta `None`: o cliente pode existir e a chamada falhar."""
        no_worker(monkeypatch, ManagerFalso(ligados={"u-ana"}))
        redis_partilhado.rebenta = True

        assert await presenca.esta_online("u-ana") is True
        assert await presenca.online_entre(["u-ana"]) == {"u-ana"}
        assert await presenca.todos_online() == {"u-ana"}

    async def test_marcar_online_falhado_nunca_levanta(
        self, redis_partilhado, monkeypatch,
    ):
        """A presença é acessória à ligação, não o contrário: uma
        escrita falhada não pode derrubar o WebSocket."""
        no_worker(monkeypatch, ManagerFalso())
        redis_partilhado.rebenta = True
        assert await presenca.marcar_online("u-ana") is False

    async def test_a_higiene_falhada_nunca_levanta(
        self, redis_partilhado, monkeypatch,
    ):
        no_worker(monkeypatch, ManagerFalso())
        redis_partilhado.rebenta = True
        assert await presenca.limpar_expirados() == 0

    async def test_user_id_vazio_nao_vai_ao_redis(
        self, redis_partilhado, monkeypatch,
    ):
        no_worker(monkeypatch, ManagerFalso())
        assert await presenca.esta_online("") is False
        assert await presenca.marcar_online("") is False
        assert redis_partilhado.chamadas == []


# ====================================================================
# ONDE A MENTIRA CUSTAVA: O PUSH
# ====================================================================

class TestOPushNoTelemovel:
    """O ramo que decide se o utilizador leva uma notificação no
    telemóvel. É aqui que a presença local errada custava: um push a
    quem está a olhar para o ecrã."""

    async def _notificar(self, fake_async_db, monkeypatch, ligado_em):
        from unittest.mock import AsyncMock

        import services.realtime_notifications as rn

        enviados = []

        async def _push(**kwargs):
            enviados.append(kwargs["user_id"])

        monkeypatch.setattr(rn, "db", fake_async_db)
        monkeypatch.setattr(rn, "send_push_notification", _push)
        monkeypatch.setattr(rn, "entregar_a_utilizador", AsyncMock())
        no_worker(monkeypatch, ligado_em)

        await rn.send_realtime_notification(
            user_id="u-ana", title="T", message="M",
        )
        return enviados

    async def test_online_NOUTRO_worker_nao_leva_push(
        self, fake_async_db, redis_partilhado, monkeypatch,
    ):
        """O defeito corrigido, ponta a ponta.

        A Ana está ligada ao worker B. A notificação é emitida no worker
        A, que não tem ligação nenhuma dela. Antes: push no telemóvel.
        """
        no_worker(monkeypatch, ManagerFalso(ligados={"u-ana"}))   # worker B
        await presenca.marcar_online("u-ana")

        worker_a = ManagerFalso(ligados=set())
        assert await self._notificar(fake_async_db, monkeypatch, worker_a) == []

    async def test_mesmo_offline_leva_push(
        self, fake_async_db, redis_partilhado, monkeypatch,
    ):
        """Contraprova: um `esta_online` que dissesse sempre True
        calava o push para toda a gente, e ninguém dava por isso."""
        enviados = await self._notificar(
            fake_async_db, monkeypatch, ManagerFalso(ligados=set()),
        )
        assert enviados == ["u-ana"]

    async def test_sem_redis_mantem_o_comportamento_de_hoje(
        self, fake_async_db, sem_redis, monkeypatch,
    ):
        """Degradação: com Redis em baixo, decide o worker local."""
        assert await self._notificar(
            fake_async_db, monkeypatch, ManagerFalso(ligados={"u-ana"}),
        ) == []
        assert await self._notificar(
            fake_async_db, monkeypatch, ManagerFalso(ligados=set()),
        ) == ["u-ana"]


# ====================================================================
# PONTO 3: O CAMPO MORTO
# ====================================================================

class TestIsNotifiedExtinto:
    async def test_a_notificacao_gravada_ja_nao_leva_o_campo(
        self, fake_async_db, redis_partilhado, monkeypatch,
    ):
        from unittest.mock import AsyncMock

        import services.realtime_notifications as rn

        monkeypatch.setattr(rn, "db", fake_async_db)
        monkeypatch.setattr(rn, "send_push_notification", AsyncMock())
        monkeypatch.setattr(rn, "entregar_a_utilizador", AsyncMock())
        no_worker(monkeypatch, ManagerFalso())

        await rn.send_realtime_notification(
            user_id="u-ana", title="T", message="M",
        )
        doc = await fake_async_db.notifications.find_one({"user_id": "u-ana"})
        assert doc is not None, "contraprova: a notificação é mesmo gravada"
        assert "is_notified" not in doc

    def test_ninguem_escreve_nem_le_o_campo(self):
        """Guarda sobre o código-fonte: era escrito em DOIS sítios e lido
        em ZERO. Não prevenia re-emissão nenhuma, ao contrário do que o
        comentário original afirmava."""
        import pathlib

        raiz = pathlib.Path(__file__).resolve().parents[2]
        from tests.unit.helpers_fonte import codigo_sem_comentarios

        for pasta in ("services", "routes", "models"):
            for f in (raiz / pasta).rglob("*.py"):
                fonte = codigo_sem_comentarios(f.read_text(encoding="utf-8"))
                assert "is_notified" not in fonte, f"{f.name} ainda mexe no campo"

    def test_o_script_de_limpeza_so_conta_por_omissao(self):
        """Uma escrita em massa numa colecção de produção merece um
        número antes de um comando."""
        import pathlib

        raiz = pathlib.Path(__file__).resolve().parents[2]
        fonte = (raiz / "scripts" / "limpar_is_notified.py").read_text(encoding="utf-8")
        assert "--aplicar" in fonte
        assert '{"$unset": {CAMPO: ""}}' in fonte
        # `$unset` remove o CAMPO; `delete_many` removeria o documento.
        assert "delete_many" not in fonte and "drop(" not in fonte


# ====================================================================
# AS LIGAÇÕES: QUEM CHAMA O QUÊ
# ====================================================================

class TestOsPontosDeLigacao:
    """Sem estas guardas, o serviço podia existir e não ser usado por
    ninguém — código morto com ar de correcção."""

    def _fonte(self, caminho):
        import pathlib

        from tests.unit.helpers_fonte import codigo_sem_comentarios

        raiz = pathlib.Path(__file__).resolve().parents[2]
        return codigo_sem_comentarios((raiz / caminho).read_text(encoding="utf-8"))

    def test_o_ping_renova_a_presenca(self):
        """O batimento de 30s que já existia — sem temporizador novo.

        `ast.unparse` normaliza as aspas (AGENTS.md): procurar o literal
        com aspas duplas não o encontra. Comparar sem elas.
        """
        fonte = self._fonte("services/websocket_api_notifications.py")
        i = fonte.index("msg_type == 'ping'")
        assert "marcar_online(user_id)" in fonte[i:i + 400]

    def test_a_ligacao_marca_logo_sem_esperar_pelo_ping(self):
        """Senão eram 30s em que quem acabou de entrar apanhava push."""
        fonte = self._fonte("services/websocket_api_notifications.py")
        i = fonte.index("manager.connect(websocket, user_id)")
        assert "marcar_online(user_id)" in fonte[i:i + 900]

    @pytest.mark.parametrize("modulo", [
        "services/chat_presence.py",
        "services/chat_conversations.py",
        "services/realtime_notifications.py",
    ])
    def test_os_consumidores_deixaram_de_perguntar_a_memoria_local(self, modulo):
        """GUARDA APERTADA — sobreviveu à mutação Q13.

        Procurava `manager.is_user_connected`, uma GRAFIA. Bastou a
        mutação escrever `_m.is_user_connected` (outro nome para o mesmo
        objecto) para passar por baixo. A guarda passou a procurar o
        MÉTODO, seja qual for o nome de quem o recebe.

        Uma guarda sobre o código-fonte que casa um nome de variável
        está a testar ortografia, não comportamento — e é por isso que
        ela nunca chega sozinha (ver o teste de comportamento abaixo).
        """
        fonte = self._fonte(modulo)
        assert "is_user_connected" not in fonte
        assert "get_connected_users" not in fonte

    @pytest.mark.parametrize("modulo,funcao", [
        ("services/chat_presence.py", "online_entre"),
        ("services/chat_presence.py", "todos_online"),
        ("services/chat_conversations.py", "online_entre"),
        ("services/realtime_notifications.py", "esta_online"),
    ])
    def test_contraprova_chamam_mesmo_o_servico(self, modulo, funcao):
        assert funcao in self._fonte(modulo)

    def test_o_chat_resolve_a_presenca_FORA_do_ciclo(self):
        """Uma chamada por utilizador dentro do ciclo seria N idas ao
        Redis — pior do que a memória local que veio substituir."""
        fonte = self._fonte("services/chat_conversations.py")
        assert fonte.index("online_entre(") < fonte.index("for conv in")

    def test_a_higiene_do_zset_corre_num_ciclo_que_ja_existia(self):
        fonte = self._fonte("server.py")
        assert "limpar_expirados" in fonte


class TestODirectorioDoChat:
    """Comportamento, não ortografia. Sobreviveu à mutação Q13 porque o
    único teste que cobria este caminho era uma guarda de código-fonte a
    casar um nome de variável."""

    async def _directorio(self, fake_async_db, monkeypatch, worker_local):
        import services.chat_presence as cp

        monkeypatch.setattr(cp, "db", fake_async_db)
        no_worker(monkeypatch, worker_local)
        return await cp.run_get_chat_users(
            {"id": "u-eu", "role": "consultor", "name": "Eu"},
        )

    async def test_ve_online_quem_esta_no_OUTRO_worker(
        self, fake_async_db, redis_partilhado, monkeypatch,
    ):
        await fake_async_db.users.insert_many([
            {"id": "u-ana", "name": "Ana", "role": "consultor", "email": "a@x.pt"},
            {"id": "u-bruno", "name": "Bruno", "role": "consultor", "email": "b@x.pt"},
        ])
        # A Ana ligou-se ao worker B.
        no_worker(monkeypatch, ManagerFalso(ligados={"u-ana"}))
        await presenca.marcar_online("u-ana")

        # O directório é pedido ao worker A, que não a conhece.
        resposta = await self._directorio(
            fake_async_db, monkeypatch, ManagerFalso(ligados=set()),
        )
        estado = {u["id"]: u["is_online"] for u in resposta["users"]}
        assert estado == {"u-ana": True, "u-bruno": False}

    async def test_uma_so_ida_ao_redis_para_o_directorio_inteiro(
        self, fake_async_db, redis_partilhado, monkeypatch,
    ):
        await fake_async_db.users.insert_many([
            {"id": f"u{i}", "name": f"U{i}", "role": "consultor",
             "email": f"u{i}@x.pt"}
            for i in range(30)
        ])
        redis_partilhado.chamadas.clear()
        await self._directorio(fake_async_db, monkeypatch, ManagerFalso())
        assert redis_partilhado.chamadas.count("zrangebyscore") == 1
        assert "zscore" not in redis_partilhado.chamadas

    async def test_a_lista_de_online_ve_o_outro_worker(
        self, fake_async_db, redis_partilhado, monkeypatch,
    ):
        """`run_get_online_users` usava `get_connected_users()` local:
        metade da equipa aparecia offline conforme o worker."""
        import services.chat_presence as cp

        await fake_async_db.users.insert_one(
            {"id": "u-ana", "name": "Ana", "role": "consultor"},
        )
        no_worker(monkeypatch, ManagerFalso(ligados={"u-ana"}))
        await presenca.marcar_online("u-ana")

        monkeypatch.setattr(cp, "db", fake_async_db)
        no_worker(monkeypatch, ManagerFalso(ligados=set()))
        resposta = await cp.run_get_online_users(
            {"id": "u-eu", "role": "consultor"},
        )
        assert [u["id"] for u in resposta["users"]] == ["u-ana"]
