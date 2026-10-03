"""Religamento manual de pastas S3 — a válvula humana (Lote 6, ponto 2).

PORQUE É QUE ISTO EXISTE
========================
A identidade da pasta documental passou a derivar do ID, e o automatismo
deixou de adivinhar: quando não sabe a quem uma pasta pertence, **recusa**
(``run_auto_map_client_s3_folders`` reporta-a como ambígua em vez de escolher
uma ficha à sorte). Essa é a decisão certa, e deixa em aberto exactamente os
casos que só uma pessoa pode resolver:

* o mapeamento aponta para a pasta legada ERRADA — a colisão que deu origem a
  este lote ("Carolina Agostinho da Silva" na pasta da "Carolina Silva");
* duas fichas partilham a mesma pasta e é preciso separar uma (D-19);
* um ``rename`` antigo deixou a ligação partida (205 medidas no Épico 10);
* uma pasta nova aparece como uuid e o administrador quer consolidá-la numa
  pasta existente que já tem histórico.

A ferramenta que existia só sabia religar **processos** — a rota de "cliente"
era um alias que recebia `process_id`. Um cliente da Pool que nunca chegou a
ter processo não tinha como ser religado, e é precisamente ele que vive sozinho
na raiz documental.

SEIS REGRAS QUE NÃO SE PODEM PERDER
===================================
1. **Só ADMIN.** Não é hierarquia: é que esta escrita move a fronteira de
   posse. Depois dela, ``assert_s3_file_belongs_to_process`` autoriza TUDO o
   que estiver na pasta escolhida.
2. **A pasta tem de estar dentro da raiz documental.** Um `backups/` gravado
   aqui transformava a guarda de posse num passe para o bucket inteiro — é
   exactamente o "prefixo de dono ENVENENADO" que a guarda da raiz do Portal
   foi escrita para travar, e aqui estaria a ser gravado de propósito.
3. **A raiz NUA é recusada.** `Documentação Clientes/` autorizaria a árvore
   toda, que é o degradado que o Lote 6 fechou do outro lado.
4. **Apontar para uma pasta que já tem dono é PERMITIDO, com aviso.**
   Consolidar duas fichas na mesma pasta é um uso legítimo (um cliente com dois
   registos), e proibi-lo tirava a ferramenta de servir metade dos casos. Mas
   quem decide tem de saber que vai partilhar — por isso o aviso NOMEIA os
   donos actuais.
5. **Deixa rasto no trilho de auditoria**, com o papel EFECTIVO em `metadata`
   (o campo partilhado guarda o do JWT) — e **nunca falha a operação**: quando
   o registo se escreve, o mapeamento já mudou, e levantar aqui mostraria um
   erro sobre algo bem sucedido.
6. **Remover o mapeamento é explícito.** Não se confunde com "não mexas": a
   ficha volta ao recurso por nome, que é um estado conhecido e pior — e por
   isso tem de ser pedido.

Nada aqui MOVE objectos no S3. Religar é mudar o ponteiro; mover ficheiros é o
`rename` do Explorador, que tem o seu próprio caminho e foi o que produziu as
205 ligações partidas.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from fastapi import HTTPException

from database import db
from services.audit_trail_service import log_audit_event
from services.s3_document_root import RAIZ, dentro_da_pasta, e_id_gerado, normalizar

logger = logging.getLogger(__name__)

#: As duas entidades que têm pasta documental própria, e onde vive o nome de
#: cada uma. Uma lista escrita em cada função divergiria — é a lição dos campos
#: canónicos de atribuição.
ENTIDADES = {
    "processo": {"coleccao": "processes", "campo_do_nome": "client_name"},
    "cliente": {"coleccao": "clients", "campo_do_nome": "nome"},
}


def _coleccao(tipo: str):
    return getattr(db, ENTIDADES[tipo]["coleccao"])


def validar_pasta(s3_folder: Optional[str]) -> Optional[str]:
    """A pasta normalizada, ou `None` para remover o mapeamento.

    Levanta 400 para tudo o que não seja uma pasta DENTRO da raiz documental.
    A raiz nua é recusada: autoriza a árvore inteira.
    """
    if s3_folder is None or not str(s3_folder).strip():
        return None
    caminho = normalizar(s3_folder)
    if not caminho:
        # Escreveram algo (`/`, `///`) que não é um caminho. Tratá-lo como
        # "remover o mapeamento" seria responder a uma pergunta diferente da
        # feita — remover é explícito (string vazia), não um efeito lateral de
        # uma normalização.
        raise HTTPException(status_code=400, detail="Caminho inválido.")

    raiz = normalizar(RAIZ)
    if caminho == raiz:
        raise HTTPException(
            status_code=400,
            detail="A raiz da documentação não é uma pasta de cliente — "
                   "autorizaria o acesso a tudo.",
        )
    if not dentro_da_pasta(caminho, raiz):
        raise HTTPException(
            status_code=400,
            detail=f"A pasta tem de estar dentro de «{raiz}».",
        )
    if ".." in caminho.split("/"):
        raise HTTPException(status_code=400, detail="Caminho inválido.")
    return caminho


async def _donos_actuais(caminho: str, excepto: tuple[str, str]) -> list[str]:
    """Os nomes das fichas que JÁ apontam para esta pasta (menos a que muda)."""
    tipo_actual, id_actual = excepto
    nomes: list[str] = []
    for tipo, cfg in ENTIDADES.items():
        campo = cfg["campo_do_nome"]
        try:
            cursor = _coleccao(tipo).find(
                {"s3_folder": caminho}, {"_id": 0, "id": 1, campo: 1}
            )
            for doc in await cursor.to_list(50):
                if tipo == tipo_actual and doc.get("id") == id_actual:
                    continue
                nome = (doc.get(campo) or "").strip()
                nomes.append(nome or f"{tipo} {doc.get('id')}")
        except Exception as exc:  # pragma: no cover - leitura informativa
            logger.warning("[S3-RELINK] Falha a procurar donos de %s: %s", caminho, exc)
    return nomes


async def _registar_na_auditoria(
    *,
    tipo: str,
    entity_id: str,
    anterior: Optional[str],
    novo: Optional[str],
    user: dict,
    papel_efectivo: Optional[str],
    request: Any = None,
) -> None:
    """Rasto do religamento. Nunca propaga — ver a regra 5."""
    try:
        await log_audit_event(
            process_id=entity_id,
            user=user,
            action=(
                f"Pasta S3 de {tipo} religada: "
                f"{anterior or '(sem pasta)'} → {novo or '(sem pasta)'}"
            ),
            field="s3_folder",
            old_value=anterior,
            new_value=novo,
            request=request,
            source="web",
            metadata={
                "tipo_de_entidade": tipo,
                "entity_id": entity_id,
                "papel_efectivo": papel_efectivo or user.get("role"),
            },
        )
    except Exception as exc:
        logger.warning(
            "[S3-RELINK] Religamento de %s %s não deixou rasto: %s",
            tipo, entity_id, exc,
        )


async def run_set_s3_mapping(
    *,
    tipo: str,
    entity_id: str,
    s3_folder: Optional[str],
    user: dict,
    papel_efectivo: Optional[str] = None,
    request: Any = None,
) -> dict:
    """Aponta a pasta documental de UM cliente ou processo."""
    if tipo not in ENTIDADES:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo desconhecido: {tipo}. Use «processo» ou «cliente».",
        )

    caminho = validar_pasta(s3_folder)

    campo = ENTIDADES[tipo]["campo_do_nome"]
    coleccao = _coleccao(tipo)
    doc = await coleccao.find_one(
        {"id": entity_id}, {"_id": 0, "id": 1, "s3_folder": 1, campo: 1}
    )
    if not doc or not doc.get("id"):
        raise HTTPException(status_code=404, detail=f"{tipo.capitalize()} não encontrado")

    anterior = doc.get("s3_folder")
    aviso = ""
    if caminho:
        outros = await _donos_actuais(caminho, (tipo, entity_id))
        if outros:
            aviso = (
                "Esta pasta já está associada a: "
                + ", ".join(sorted(set(outros)))
                + ". A documentação passa a ser partilhada."
            )

    await coleccao.update_one({"id": entity_id}, {"$set": {"s3_folder": caminho}})

    await _registar_na_auditoria(
        tipo=tipo, entity_id=entity_id, anterior=anterior, novo=caminho,
        user=user, papel_efectivo=papel_efectivo, request=request,
    )

    logger.info(
        "[S3-RELINK] %s %s: %s → %s (por %s)",
        tipo, entity_id, anterior, caminho, user.get("id"),
    )
    return {
        "success": True,
        "tipo": tipo,
        "id": entity_id,
        "nome": doc.get(campo),
        "s3_folder": caminho,
        "s3_folder_anterior": anterior,
        "aviso": aviso,
    }


async def run_get_s3_relink(
    *,
    search: Optional[str] = None,
    tipo: Optional[str] = None,
    apenas_por_resolver: bool = False,
    page: int = 1,
    limit: int = 50,
    user: dict,
) -> dict:
    """As fichas e as pastas, lado a lado, para o administrador decidir.

    `apenas_por_resolver` isola o trabalho pendente: sem pasta gravada (volta
    ao recurso por nome) **ou** com a pasta a apontar para um sítio que já não
    existe não se sabe daqui — por isso o critério é o primeiro, que é o único
    que se pode afirmar sem ir ao S3 a cada linha.
    """
    tipos = [tipo] if tipo in ENTIDADES else list(ENTIDADES)
    entidades: list[dict] = []

    for t in tipos:
        campo = ENTIDADES[t]["campo_do_nome"]
        query: dict[str, Any] = {}
        if search:
            query[campo] = {"$regex": re.escape(search), "$options": "i"}
        if apenas_por_resolver:
            query["$or"] = [
                {"s3_folder": {"$exists": False}},
                {"s3_folder": None},
                {"s3_folder": ""},
            ]
        try:
            cursor = _coleccao(t).find(
                query,
                {"_id": 0, "id": 1, campo: 1, "s3_folder": 1,
                 "process_number": 1, "client_id": 1},
            )
            docs = await cursor.to_list(1000)
        except Exception as exc:
            logger.warning("[S3-RELINK] Falha a listar %s: %s", t, exc)
            docs = []

        for doc in docs:
            pasta = normalizar(doc.get("s3_folder"))
            segmento = pasta[len(normalizar(RAIZ)) + 1:].split("/")[0] if pasta else ""
            entidades.append({
                "tipo": t,
                "id": doc.get("id"),
                "nome": doc.get(campo),
                "process_number": doc.get("process_number"),
                "client_id": doc.get("client_id"),
                "s3_folder": doc.get("s3_folder"),
                # Serve ao ecrã para dizer "esta pasta é a nova, por id" — o
                # administrador precisa de distinguir um uuid legítimo de um
                # mapeamento legado antes de decidir.
                "pasta_por_id": bool(segmento) and e_id_gerado(segmento),
            })

    entidades.sort(key=lambda e: ((e.get("nome") or "").lower(), e["tipo"]))
    total = len(entidades)
    inicio = max(0, (page - 1) * limit)
    pagina = entidades[inicio:inicio + limit]

    pastas = await _pastas_disponiveis()

    return {
        "entidades": pagina,
        "pastas": pastas,
        "total": total,
        "page": page,
        "limit": limit,
        "stats": {
            "total": total,
            "sem_pasta": sum(1 for e in entidades if not e["s3_folder"]),
            "por_id": sum(1 for e in entidades if e["pasta_por_id"]),
        },
    }


async def _pastas_disponiveis() -> list[dict]:
    """As pastas do bucket, com o nome resolvido e os donos nomeados.

    O nome mostrado vem do MESMO ponto que o do Explorador
    (`s3_explorer_scope.nome_legivel`): duas resoluções do mesmo nome
    divergiriam, e o administrador veria uma coisa aqui e outra lá.
    """
    from services.s3_explorer_scope import carregar_pastas, nome_legivel
    from services.s3_storage import s3_service

    if not s3_service.is_configured():
        return []

    caminhos: list[tuple[str, str]] = []
    try:
        resposta = s3_service.s3_client.list_objects_v2(
            Bucket=s3_service.bucket_name, Prefix=RAIZ, Delimiter="/"
        )
        for prefixo in resposta.get("CommonPrefixes", []):
            caminho = (prefixo.get("Prefix") or "").rstrip("/")
            nome = caminho.replace(RAIZ, "")
            if nome:
                caminhos.append((caminho, nome))
    except Exception as exc:
        logger.warning("[S3-RELINK] Falha a listar as pastas do bucket: %s", exc)
        return []

    mapa = await carregar_pastas([c for c, _ in caminhos])
    return [
        {
            "path": caminho,
            "name": nome,
            "display_name": nome_legivel(mapa.get(caminho), nome),
            "nomes_dos_clientes": sorted((mapa.get(caminho).nomes if mapa.get(caminho) else [])),
            "orfa": bool(mapa.get(caminho).orfa) if mapa.get(caminho) else True,
            "por_id": e_id_gerado(nome),
        }
        for caminho, nome in caminhos
    ]
