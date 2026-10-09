"""Desvio inteligente: para onde vai um ficheiro que entra, e se gasta IA.

O PEDIDO (Bloco 2, Lote 12)
===========================
* **Qualquer upload de um utilizador entra, inicialmente, na pasta `Index`.**
  Só depois de o processo ser marcado como indexado é que os ficheiros
  passam para as categorias finais;
* **Desvio inteligente (poupança de IA):** se o processo NÃO está indexado,
  o ficheiro entra na fila da IA (a estação de Indexação); se JÁ está
  indexado, é apenas guardado na pasta, **ignorando a IA**.

Aplica-se por igual ao upload (multipart e directo) e ao «Arquivar no
Processo» do Webmail: é por isso que a decisão vive aqui e não em cada
fluxo — três cópias da mesma regra divergem sem dar erro, e a que divergir
gasta IA onde não devia (ou deixa um ficheiro na pasta errada).

AS REGRAS
=========
1. **«Já passou a indexação»** = `is_indexed is True` **ou** `skip_index is
   True` (Via Verde: o processo foi criado para saltar a Indexação e nunca
   será marcado como indexado — sem esta cláusula os ficheiros dele
   acumulavam-se na `Index` para sempre e a IA corria em cada upload);
2. antes disso a categoria é SEMPRE `Index`, seja qual for a pedida — a
   pedida fica registada (`categoria_pedida`) para o ecrã dizer ao
   utilizador onde o ficheiro foi parar e porquê;
3. depois disso a categoria pedida manda, e **a IA não corre**: nem a
   triagem à entrada (a categoria «Outros»/«Auto» que antes chamava o
   modelo) nem a categorização em background. Pedir «Auto» sem IA dá
   «Outros»;
4. a IA corre **no máximo uma vez** por ficheiro (a categorização em
   background). A triagem à entrada era uma SEGUNDA chamada ao modelo sobre
   o mesmo ficheiro, cujo resultado só escolhia a pasta — e a pasta, antes
   da indexação, já é a `Index`.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from database import db

logger = logging.getLogger(__name__)

CATEGORIA_INDEX = "Index"
CATEGORIA_POR_OMISSAO = "Outros"
#: Pedidos que não escolhem pasta nenhuma.
CATEGORIAS_SEM_ESCOLHA = ("", "auto", "other", "outros")

#: Quem VÊ a pasta `Index` (a «pasta cofre»). Espelha o
#: `INDEX_CATEGORY_ALLOWED_ROLES` do S3FileManager: o ecrã escondia-a e o
#: servidor devolvia-a na mesma, pelo que aqui passa a ser o servidor a
#: decidir. Escrever na `Index` não exige poder lê-la (um consultor envia,
#: não vê).
PAPEIS_QUE_VEEM_O_INDEX = ("admin", "ceo", "diretor", "indexacao")


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor is not None else ""


def processo_ja_passou_a_indexacao(processo: Optional[dict]) -> bool:
    """O processo está indexado — ou foi criado para não passar por ela."""
    processo = processo or {}
    return processo.get("is_indexed") is True or processo.get("skip_index") is True


@dataclass(frozen=True)
class PlanoDeEntrada:
    """O que acontece a um ficheiro que entra."""

    categoria: str
    categoria_pedida: str
    passa_pela_ia: bool
    motivo: str

    @property
    def em_fila_de_indexacao(self) -> bool:
        return self.passa_pela_ia


def planear_entrada(processo: Optional[dict], categoria_pedida: Any = None) -> PlanoDeEntrada:
    """Decide a pasta e a IA de um ficheiro novo. Pura."""
    pedida = _texto(categoria_pedida)

    if not processo_ja_passou_a_indexacao(processo):
        return PlanoDeEntrada(
            categoria=CATEGORIA_INDEX,
            categoria_pedida=pedida,
            passa_pela_ia=True,
            motivo=(
                "O processo ainda não está indexado: o ficheiro fica na pasta "
                "Index e entra na fila da Indexação."
            ),
        )

    categoria = CATEGORIA_POR_OMISSAO if pedida.lower() in CATEGORIAS_SEM_ESCOLHA else pedida
    return PlanoDeEntrada(
        categoria=categoria,
        categoria_pedida=pedida,
        passa_pela_ia=False,
        motivo="O processo já está indexado: o ficheiro é guardado sem passar pela IA.",
    )


def categoria_para_o_portal(plano: PlanoDeEntrada) -> str:
    """A categoria com que se tenta satisfazer um pedido do Portal.

    O ficheiro fica na `Index`, mas o pedido do cliente («Cartão de Cidadão»)
    não fala em pastas: com a categoria `Index` nunca casava com nada e o
    cliente continuava a ver como pendente o que a equipa já recebeu. Usa-se
    a categoria PEDIDA quando o utilizador escolheu uma.
    """
    pedida = plano.categoria_pedida
    if pedida and pedida.lower() not in CATEGORIAS_SEM_ESCOLHA:
        return pedida
    return plano.categoria


def descreve_destino(plano: PlanoDeEntrada) -> str:
    """O texto do histórico: `Index` e, entre parêntesis, o que foi pedido."""
    if plano.categoria != plano.categoria_pedida and plano.categoria_pedida:
        return f"{plano.categoria}; pedido: {plano.categoria_pedida}"
    return plano.categoria


def descricao_para_o_utilizador(plano: PlanoDeEntrada) -> dict:
    """O bloco que as respostas de upload acrescentam, para o ecrã falar."""
    return {
        "fila_ia": plano.passa_pela_ia,
        "categoria_pedida": plano.categoria_pedida or None,
        "categoria_final": plano.categoria,
        "aviso": plano.motivo if plano.passa_pela_ia else None,
    }


def pode_ver_o_index(user: Optional[dict]) -> bool:
    """Este utilizador vê a pasta `Index`? Pelo perfil EFECTIVO.

    `__all_roles__` (o modo «todos os perfis») não é um papel: basta ter um
    dos papéis que a vêem.
    """
    if not user:
        return False
    papel = _texto(user.get("effective_role") or user.get("role")).lower()
    if papel == "__all_roles__":
        from services.auth import get_all_user_roles

        return any(
            _texto(p).lower() in PAPEIS_QUE_VEEM_O_INDEX
            for p in get_all_user_roles(user)
        )
    return papel in PAPEIS_QUE_VEEM_O_INDEX


def chave_esta_na_index(s3_path: Any) -> bool:
    """A chave S3 vive na pasta `Index`? (a pasta imediatamente acima do ficheiro).

    Compara o SEGMENTO, não o texto: `Documentação Clientes/Indexador/x.pdf`
    não está na `Index`. Falha para o lado de esconder — uma chave que não
    consigo ler não é mostrada a quem não vê a pasta cofre.
    """
    if not isinstance(s3_path, str) or not s3_path:
        return False
    segmentos = [p for p in s3_path.split("/") if p]
    return len(segmentos) >= 2 and segmentos[-2].strip().lower() == CATEGORIA_INDEX.lower()


def retirar_documentos_da_index(documentos: Any, user: Optional[dict], *, campo: str = "s3_path") -> Any:
    """Tira de uma lista de documentos os que estão na `Index` (ou na fila da IA).

    Para as listagens que não passam pelo `list_files` (metadados e modal de
    envio a balcões): sem isto, a parede da listagem era contornada pela
    outra porta — e os metadados trazem URLs pré-assinados.
    """
    if pode_ver_o_index(user) or not isinstance(documentos, list):
        return documentos
    return [
        d for d in documentos
        if not (
            isinstance(d, dict)
            and (chave_esta_na_index(d.get(campo)) or d.get("in_index_queue") is True)
        )
    ]


def retirar_o_index_da_listagem(listagem: Any, user: Optional[dict]) -> Any:
    """Tira a pasta `Index` da listagem de ficheiros de quem não a vê.

    O ecrã já a escondia (Pacote BL), mas a API devolvia-a: esconder no
    cliente é cortesia, não é uma parede. Recalcula as estatísticas, para o
    total do rodapé não contradizer o que se vê.
    """
    if pode_ver_o_index(user) or not isinstance(listagem, dict):
        return listagem
    por_categoria = listagem.get("files")
    if not isinstance(por_categoria, dict) or CATEGORIA_INDEX not in por_categoria:
        return listagem

    visiveis = {k: v for k, v in por_categoria.items() if k != CATEGORIA_INDEX}
    retirados = por_categoria.get(CATEGORIA_INDEX)
    resultado = {
        **listagem,
        "files": visiveis,
        # Diz QUANTOS ficheiros estão a aguardar a Indexação, sem os mostrar:
        # um consultor que acabou de enviar um documento e não o vê em lado
        # nenhum conclui que o envio falhou.
        "em_indexacao": len(retirados) if isinstance(retirados, list) else 0,
    }
    stats = listagem.get("stats")
    if isinstance(stats, dict):
        ficheiros = [f for lista in visiveis.values() if isinstance(lista, list) for f in lista]
        tamanho = sum(int(f.get("size") or 0) for f in ficheiros if isinstance(f, dict))
        resultado["stats"] = {
            **stats,
            "total_files": len(ficheiros),
            "total_size": tamanho,
        }
        if "total_size_formatted" in stats:
            resultado["stats"]["total_size_formatted"] = _formatar_tamanho(tamanho)
    return resultado


def _formatar_tamanho(n: int) -> str:
    valor = float(n)
    for unidade in ("B", "KB", "MB", "GB"):
        if valor < 1024 or unidade == "GB":
            return f"{valor:.0f} {unidade}" if unidade == "B" else f"{valor:.1f} {unidade}"
        valor /= 1024
    return f"{n} B"


async def registar_na_fila_da_ia(
    *,
    process_id: str,
    client_name: str,
    s3_path: str,
    filename: str,
    origem: str,
) -> None:
    """Marca o ficheiro como «à espera da IA» — a fila da estação de Indexação.

    Escreve o registo de metadados ANTES de a categorização em background
    correr (que o encontra por `s3_path` e actualiza-o, mantendo o `id`).
    Assim a fila é visível desde o primeiro segundo, e um ficheiro cuja IA
    falhou fica **na fila** (`is_categorized` falso) em vez de desaparecer.

    Nunca propaga: o registo da fila é uma observação, e o ficheiro já está
    gravado quando isto corre.
    """
    agora = datetime.now(timezone.utc).isoformat()
    try:
        existente = await db.document_metadata.find_one({"s3_path": s3_path}, {"_id": 0, "id": 1})
        if existente:
            await db.document_metadata.update_one(
                {"s3_path": s3_path},
                {"$set": {"in_index_queue": True, "queued_at": agora, "queue_source": origem}},
            )
            return
        await db.document_metadata.insert_one({
            "id": str(uuid.uuid4()),
            "process_id": process_id,
            "client_name": client_name,
            "s3_path": s3_path,
            "filename": filename,
            "is_categorized": False,
            "in_index_queue": True,
            "queued_at": agora,
            "queue_source": origem,
            "created_at": agora,
            "updated_at": agora,
        })
    except Exception as exc:
        logger.warning(
            "[INTAKE] Falha a registar %s na fila da IA (%s); o ficheiro está "
            "guardado e a categorização segue.", s3_path, exc,
        )
