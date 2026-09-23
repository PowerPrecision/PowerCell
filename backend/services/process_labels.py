"""
Etiquetas dos processos — Lote 5, Secção B, ponto 15.

O PEDIDO
  Marcadores personalizados ("Sub 35", "VIP", "Urgente") para segmentar
  processos, porque as fases já não chegam.

O QUE JÁ EXISTIA
  `labels: Optional[List[str]]` está no modelo desde sempre, persiste em
  `process_update` e vem nas projecções. Faltava o editor (o comentário
  no `ProcessDetails` prometia um Dialog que nunca foi construído) e
  faltava a FILTRAGEM: nem `build_process_list_query` nem
  `build_kanban_query` conheciam o campo.

PORQUE É QUE CONTINUAM A SER STRINGS
  Passar a objectos obrigaria a migrar os dados existentes e a mexer em
  todas as projecções, e a única coisa que os objectos dariam a mais era
  a cor — que se deriva do próprio texto, deterministicamente, no
  frontend (`utils/processLabels.js`). "VIP" fica da mesma cor em todo o
  lado sem uma segunda colecção para manter em dia.

NORMALIZAR À ESCRITA, NUNCA À LEITURA
  "VIP", "vip" e " VIP " são a mesma etiqueta para quem segmenta e três
  para o Mongo. Com a normalização na leitura, cada filtro teria de a
  repetir — e o primeiro que se esquecesse devolvia uma lista a menos
  sem ninguém reparar.

O CATÁLOGO TEM ÂMBITO DE TENANT, E ISSO NÃO É OPCIONAL
  Para filtrar é preciso saber que etiquetas existem, e a fonte honesta
  é o que está nos processos. Um `distinct` sem a condição de rede seria
  uma fuga nova, da mesma família das do Lote 4/5: o nome de uma
  campanha da concorrência no dropdown de quem não a devia ver.
"""
import logging
from typing import Any, Iterable, Optional

from database import db
from services.tenant_network import build_tenant_condition

logger = logging.getLogger(__name__)

#: Uma etiqueta é um marcador, não um campo de notas.
MAX_COMPRIMENTO = 40
#: Acima disto deixa de segmentar e passa a ser ruído no cabeçalho.
MAX_ETIQUETAS = 20

CAMPO = "labels"


def normalizar_etiquetas(valor: Any) -> list[str]:
    """Etiquetas limpas, sem repetições e em número comportável.

    Aceita lista ou string separada por vírgulas (é assim que chegam de
    um campo de texto). Compara sem olhar à capitalização mas **preserva
    a forma da primeira ocorrência**: quem escreve "Sub 35" não quer ver
    "sub 35" no crachá.

    Devolve sempre uma lista — uma lista vazia é uma resposta legítima
    (limpar as etiquetas de um processo), não um erro.
    """
    if valor is None:
        return []

    if isinstance(valor, str):
        cruas: Iterable[Any] = valor.split(",")
    elif isinstance(valor, (list, tuple, set)):
        cruas = valor
    else:
        return []

    etiquetas: list[str] = []
    vistas: set[str] = set()
    for crua in cruas:
        if crua is None:
            continue
        texto = str(crua).strip()[:MAX_COMPRIMENTO].strip()
        if not texto:
            continue
        chave = texto.casefold()
        if chave in vistas:
            continue
        vistas.add(chave)
        etiquetas.append(texto)
        if len(etiquetas) >= MAX_ETIQUETAS:
            break
    return etiquetas


def build_labels_condition(
    etiquetas: Any,
    logica: Optional[str] = "OR",
) -> Optional[dict]:
    """Condição Mongo para filtrar por etiquetas, ou ``None``.

    ``None`` quer dizer **não filtrar** — o chamador tem de o testar
    antes de a juntar à query. Um filtro sempre presente esconderia os
    processos sem etiqueta nenhuma, que são a maioria.

    ``logica`` espelha o ``assigned_logic`` que já existe neste ficheiro:
    ``OR`` (qualquer uma) por omissão, ``AND`` (todas) para segmentar a
    sério ("Sub 35" **e** "VIP").
    """
    limpas = normalizar_etiquetas(etiquetas)
    if not limpas:
        return None
    operador = "$all" if str(logica or "").strip().upper() == "AND" else "$in"
    return {CAMPO: {operador: limpas}}


async def listar_etiquetas_em_uso(
    *,
    tenant_condition: Optional[dict] = None,
) -> list[str]:
    """Etiquetas que existem mesmo, dentro do âmbito do utilizador.

    Nunca levanta: sem catálogo o filtro fica sem sugestões (e o
    utilizador pode sempre escrever a etiqueta), mas a página abre.
    """
    filtro: dict = dict(tenant_condition) if tenant_condition else {}
    try:
        valores = await db.processes.distinct(CAMPO, filtro)
    except Exception as e:  # noqa: BLE001 — degradação graciosa deliberada
        logger.warning("Não foi possível ler o catálogo de etiquetas: %s", e)
        return []

    etiquetas: list[str] = []
    vistas: set[str] = set()
    for valor in valores or []:
        texto = str(valor).strip()
        if not texto:
            continue
        chave = texto.casefold()
        if chave in vistas:
            continue
        vistas.add(chave)
        etiquetas.append(texto)
    return sorted(etiquetas, key=str.casefold)


async def run_get_process_labels(user: dict) -> dict[str, Any]:
    """Handler de ``GET /processes/labels`` — o catálogo para o filtro.

    O âmbito é o do UTILIZADOR (a rede), não o da empresa activa: a
    empresa activa é uma vista, a rede é a fronteira de segurança. É a
    mesma condição que as listagens usam, vinda do mesmo ponto único.
    """
    tenant_condition = await build_tenant_condition(user)
    etiquetas = await listar_etiquetas_em_uso(tenant_condition=tenant_condition)
    return {"labels": etiquetas, "count": len(etiquetas)}
