"""Importação do ARQUIVO HISTÓRICO do Index a partir de ZIPs (Out 2026) — `scripts/import_historico_zip.py`.

Há anos de recibos, extratos e declarações na OneDrive que nunca passaram pelo CRM. Não têm cliente nem processo:
só interessa alimentar a **pesquisa avançada** (por valor, banco, zona, entidade) e o **directório de entidades
patronais**. Este módulo lê um ZIP — de 85 MB ou de mais de 2 GB — ficheiro a ficheiro, classifica e extrai com a
IA do Index e grava UMA linha pesquisável por documento. Os ficheiros em si **não são guardados** (nem no S3 nem
em disco): do documento só ficam os factos que a pesquisa usa.

REGRAS QUE NÃO SE PODEM PERDER
------------------------------
1. **Nunca se descomprime o ZIP.** Abre-se o índice (o directório central) e lê-se UM membro de cada vez, em blocos
   de 1 MB, com tecto REAL (`TAMANHO_MAXIMO`): o tamanho que o ZIP declara é do atacante (zip bomb), o que se
   conta é o que sai. Memória = um ficheiro; disco = nada. Como nada se escreve com o nome do membro, não há
   `../` (zip slip) para explorar.
2. **A rede é obrigatória e tem de existir.** As linhas históricas não têm processo de onde herdar a fronteira; o
   único carimbo que as protege é o `network_id` (a pesquisa só as mostra a quem tem essa rede no âmbito, e o
   Master vê todas). Uma rede escrita com uma gralha criava dados que ninguém vê (a lição do «Campo de Rede»), por
   isso `rede_existe` recusa o que nenhuma empresa declara.
3. **Idempotente e retomável.** O `process_id` é artificial e determinístico (`historical_import_<hash do ZIP>`); o
   id de cada linha deriva do CONTEÚDO e da rede. Repetir o comando (ou retomar um que caiu a meio) nunca duplica
   nem volta a pagar: o que já está importado — e o que a IA já disse que não serve — salta-se ANTES da chamada.
   Uma falha da IA/leitura não fica marcada: tenta-se de novo na próxima.
4. **Nada pessoal.** Nem o nome do ficheiro nem o caminho no ZIP (levam o nome do cliente) chegam ao modelo, ao
   registo ou ao ecrã; para o modelo o ficheiro chama-se `documento.<ext>`. Os documentos de **identificação** são
   reconhecidos e ignorados: o arquivo não os lê. O progresso (stdout) só leva contagens e tipos.
5. **O código dispõe, a IA propõe.** Reutiliza `index_ai` (os mesmos esquemas e normalizadores do CRM) e
   `index_store.linha_historica` (a MESMA projecção): uma linha sem dados úteis é `sem_dados` e não entra na pesquisa.
   Só um NIF válido, com nome e sem dúvida entra no directório (`registar_entidades`).
6. **Custo contido.** `limite_ia` pára a execução depois de N documentos enviados ao modelo; o nome/pasta
   classificam de graça quando há pista (`classificar_sempre` força a IA); com o motor simulado recusa-se a correr
   (`IASimulada`) — um arquivo com dados inventados é pior do que um arquivo vazio.
7. **Reversível.** Cada linha leva o `import_id`; `desfazer` apaga uma importação (o directório de entidades fica:
   é global e partilhado).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import posixpath
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Awaitable, Callable, Iterator, Optional

from database import db
from services import index_store as store
from services.index_ai import (
    PROVIDER_OPENAI,
    TIPO_DECLARACAO,
    TIPO_EXTRATO,
    TIPO_IDENTIFICACAO,
    TIPO_OUTRO,
    TIPO_RECIBO,
    analisar_documento,
    classificar_documento,
    resolver_provider,
    tipo_de_analise,
)

logger = logging.getLogger(__name__)

EXTENSOES_ANALISAVEIS = (".pdf", ".jpg", ".jpeg", ".png")
#: Mesmo tecto da análise do CRM (`index_jobs.TAMANHO_MAXIMO`): o que o motor não lê lá, não lê aqui.
TAMANHO_MAXIMO = 20 * 1024 * 1024
BLOCO = 1024 * 1024
PAUSA_POR_OMISSAO_SEGUNDOS = 0.5
TAMANHO_DA_ETIQUETA = 80
PREFIXO_DO_ID = "hist_"

#: veredictos negativos que a IA já custou e que se lembram (uma reexecução não os repete)
ESTADOS_QUE_SE_LEMBRAM = ("identificacao", "outro", "sem_dados")


class IASimulada(RuntimeError):
    """O motor de IA configurado é o simulado: o arquivo não se alimenta com dados inventados."""


class RedeDesconhecida(ValueError):
    """Nenhuma empresa declara esta rede."""


class ZipInvalido(ValueError):
    """O ficheiro não é um ZIP legível."""


# ====================================================================
# PURO
# ====================================================================
def hash_do_zip(caminho: str) -> str:
    """SHA-256 do ficheiro, em blocos de 1 MB (um ZIP de 2 GB nunca está inteiro na memória)."""
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        while bloco := f.read(BLOCO):
            h.update(bloco)
    return h.hexdigest()


def import_id_do_zip(hash_hex: str) -> str:
    return hash_hex[:12]


def id_do_documento(rede: str, conteudo_sha256: str) -> str:
    """Id determinístico: o MESMO ficheiro, na mesma rede, é sempre a mesma linha (mesmo noutro ZIP)."""
    return PREFIXO_DO_ID + hashlib.sha256(f"{rede}|{conteudo_sha256}".encode()).hexdigest()[:24]


def etiqueta_da_importacao(texto: Optional[str], caminho: str) -> str:
    """A etiqueta que o ecrã mostra («Arquivo histórico — <etiqueta>»): a pedida, ou o nome do ZIP. Sem controlo."""
    base = (texto or PurePosixPath(caminho.replace("\\", "/")).stem or "").strip()
    limpa = "".join(c for c in " ".join(base.split()) if c.isprintable() and c not in "<>")
    return limpa[:TAMANHO_DA_ETIQUETA]


def motivo_de_exclusao(info: zipfile.ZipInfo) -> Optional[str]:
    """Porque é que um membro do ZIP nem é candidato (`None` = é). Não lê o conteúdo."""
    nome = info.filename.replace("\\", "/")
    if info.is_dir() or nome.endswith("/"):
        return "pasta"
    partes = [p for p in nome.split("/") if p]
    ficheiro = partes[-1] if partes else ""
    if not ficheiro or "__MACOSX" in partes or ficheiro.startswith((".", "~$")) or ficheiro.lower() in ("thumbs.db", "desktop.ini"):
        return "lixo_do_sistema"
    if info.flag_bits & 0x1:
        return "cifrado"
    extensao = posixpath.splitext(ficheiro)[1].lower()
    if extensao == ".zip":
        return "zip_aninhado"
    if extensao not in EXTENSOES_ANALISAVEIS:
        return "formato"
    return None


def pista_do_tipo(nome_do_membro: str) -> Optional[str]:
    """O tipo que o NOME e as PASTAS sugerem (de graça), ou `None`. Só se usa para decidir; nunca é guardado."""
    caminho = PurePosixPath(nome_do_membro.replace("\\", "/"))
    # as pistas são palavras: `cartao_de_cidadao` e `recibo-vencimento` têm de valer como `cartao de cidadao`
    ficheiro = re.sub(r"[_\-.]+", " ", caminho.stem)
    pastas = re.sub(r"[_\-.]+", " ", " ".join(caminho.parent.parts))
    return tipo_de_analise(None, pastas, ficheiro)


def tem_dados_uteis(linha: Optional[dict]) -> bool:
    """A linha diz alguma coisa que a pesquisa use? (senão é ruído: um recibo ilegível não pode entrar)."""
    if not linha:
        return False
    tipo = linha.get("doc_type")
    if tipo == store.DOC_TYPE_RECIBO:
        return linha.get("net_salary_num") is not None or bool(linha.get("employer_nif") or linha.get("employer_name"))
    if tipo == store.DOC_TYPE_DECLARACAO:
        return bool(linha.get("employer_nif") or linha.get("employer_name"))
    if tipo == store.DOC_TYPE_EXTRATO:
        return bool(linha.get("bank") or linha.get("period"))
    return False


def ler_membro(zf: zipfile.ZipFile, info: zipfile.ZipInfo, limite: Optional[int] = None) -> tuple[Optional[bytes], Optional[str]]:
    """`(bytes, motivo)` de UM membro, em blocos, com tecto sobre o que SAI (não sobre o que o ZIP declara)."""
    limite = TAMANHO_MAXIMO if limite is None else limite
    if info.file_size > limite:
        return None, "demasiado_grande"
    saida = bytearray()
    try:
        with zf.open(info) as f:
            while bloco := f.read(BLOCO):
                saida += bloco
                if len(saida) > limite:
                    return None, "demasiado_grande"
    except (zipfile.BadZipFile, RuntimeError, EOFError, OSError, NotImplementedError) as exc:
        logger.warning("[IMPORT-HISTORICO] Membro ilegível (%s)", type(exc).__name__)
        return None, "ilegivel"
    return bytes(saida), None


def membros_candidatos(zf: zipfile.ZipFile) -> Iterator[tuple[zipfile.ZipInfo, Optional[str]]]:
    """Cada membro com o motivo de exclusão (ou `None`). Percorre só o directório central."""
    for info in zf.infolist():
        yield info, motivo_de_exclusao(info)


# ====================================================================
# I/O
# ====================================================================
async def redes_conhecidas() -> list[str]:
    valores = await db.companies.distinct("network_id")
    return sorted({str(v).strip() for v in valores if isinstance(v, str) and v.strip()})


async def rede_existe(rede: str) -> bool:
    """Alguma empresa declara esta rede? (comparação EXACTA: uma rede escrita à pressa não passa)"""
    return bool(rede) and rede in await redes_conhecidas()


@dataclass
class Resumo:
    import_id: str
    process_id: str
    rede: str
    membros: int = 0
    estados: dict[str, int] = field(default_factory=dict)
    entidades_novas: int = 0
    chamadas_ia: int = 0
    parou_por: Optional[str] = None

    def contar(self, estado: str) -> None:
        self.estados[estado] = self.estados.get(estado, 0) + 1

    def linha(self) -> str:
        e = self.estados
        return (
            f"PROGRESSO: importacao={self.import_id} membros={self.membros} importados={e.get('importado', 0)} "
            f"ja_importados={e.get('ja_importado', 0)} duplicados_no_zip={e.get('duplicado_no_zip', 0)} "
            f"identificacao={e.get('identificacao', 0)} outro={e.get('outro', 0)} sem_dados={e.get('sem_dados', 0)} "
            f"falhas_ia={e.get('falha_ia', 0)} ilegiveis={e.get('ilegivel', 0)} grandes={e.get('demasiado_grande', 0)} "
            f"excluidos={sum(v for k, v in e.items() if k.startswith('excluido_'))} "
            f"entidades_novas={self.entidades_novas} chamadas_ia={self.chamadas_ia}"
            + (f" parou_por={self.parou_por}" if self.parou_por else "")
        )


def analise_previa(caminho: str) -> dict[str, Any]:
    """O que o ZIP tem, SEM ler conteúdo nem chamar a IA (a omissão do script). Só percorre o directório central."""
    try:
        zf = zipfile.ZipFile(caminho)
    except (zipfile.BadZipFile, OSError) as exc:
        raise ZipInvalido(f"{type(exc).__name__}") from exc
    with zf:
        total = candidatos = 0
        bytes_candidatos = 0
        excluidos: dict[str, int] = {}
        por_pista: dict[str, int] = {"recibo": 0, "extrato": 0, "declaracao": 0, "identificacao": 0, "sem_pista": 0}
        demasiado_grandes = 0
        for info, motivo in membros_candidatos(zf):
            total += 1
            if motivo:
                excluidos[motivo] = excluidos.get(motivo, 0) + 1
                continue
            if info.file_size > TAMANHO_MAXIMO:
                demasiado_grandes += 1
                continue
            candidatos += 1
            bytes_candidatos += info.file_size
            pista = pista_do_tipo(info.filename)
            chave = {TIPO_RECIBO: "recibo", TIPO_EXTRATO: "extrato", TIPO_DECLARACAO: "declaracao",
                     TIPO_IDENTIFICACAO: "identificacao"}.get(pista, "sem_pista")
            por_pista[chave] += 1
    return {
        "membros": total, "candidatos": candidatos, "bytes_candidatos": bytes_candidatos,
        "excluidos": excluidos, "demasiado_grandes": demasiado_grandes, "por_pista": por_pista,
    }


async def importar_zip(
    caminho: str,
    *,
    rede: str,
    etiqueta: Optional[str] = None,
    limite_ia: Optional[int] = None,
    classificar_sempre: bool = False,
    pausa: float = 0.0,
    permitir_simulado: bool = False,
    escrever: Callable[[str], None] = print,
    dormir: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> Resumo:
    """Importa o ZIP. Levanta `RedeDesconhecida`, `ZipInvalido` ou `IASimulada` ANTES de gastar nada."""
    if not await rede_existe(rede):
        raise RedeDesconhecida(rede)
    if resolver_provider() != PROVIDER_OPENAI and not permitir_simulado:
        raise IASimulada("INDEX_AI_PROVIDER não é 'openai': o arquivo histórico só se alimenta com o motor real.")
    try:
        hash_hex = await asyncio.to_thread(hash_do_zip, caminho)
        zf = zipfile.ZipFile(caminho)
    except (zipfile.BadZipFile, OSError) as exc:
        raise ZipInvalido(type(exc).__name__) from exc

    import_id = import_id_do_zip(hash_hex)
    resumo = Resumo(import_id=import_id, process_id=store.processo_historico(import_id), rede=rede)
    label = etiqueta_da_importacao(etiqueta, caminho)
    vistos_neste_zip: set[str] = set()
    entrada = 0
    with zf:
        membros = [(info, motivo) for info, motivo in membros_candidatos(zf)]
        resumo.membros = len(membros)
        for info, motivo in membros:
            entrada += 1
            if motivo:
                resumo.contar(f"excluido_{motivo}")
                continue
            if limite_ia is not None and resumo.chamadas_ia >= limite_ia:
                resumo.parou_por = "limite_ia"
                break
            try:
                estado = await _importar_membro(
                    zf, info, resumo, rede=rede, label=label, vistos=vistos_neste_zip,
                    classificar_sempre=classificar_sempre, permitir_simulado=permitir_simulado,
                )
            except Exception as exc:  # noqa: BLE001 — um ficheiro a rebentar não pára a importação
                logger.warning("[IMPORT-HISTORICO] Ficheiro %d: %s", entrada, type(exc).__name__)
                estado = "falha_ia"
            resumo.contar(estado)
            escrever(f"[import-historico] {entrada}/{len(membros)} → {estado}")
            if pausa > 0 and estado in ("importado", "sem_dados", "outro", "identificacao", "falha_ia"):
                await dormir(pausa)
    escrever(resumo.linha())
    return resumo


async def _importar_membro(
    zf: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    resumo: Resumo,
    *,
    rede: str,
    label: str,
    vistos: set[str],
    classificar_sempre: bool,
    permitir_simulado: bool,
) -> str:
    conteudo, motivo = await asyncio.to_thread(ler_membro, zf, info)
    if conteudo is None:
        return motivo or "ilegivel"

    doc_id = id_do_documento(rede, hashlib.sha256(conteudo).hexdigest())
    if doc_id in vistos:
        return "duplicado_no_zip"
    vistos.add(doc_id)
    if doc_id in await store.ids_historicos_conhecidos([doc_id]):
        return "ja_importado"

    extensao = posixpath.splitext(info.filename.replace("\\", "/"))[1].lower() or ".pdf"
    # para o modelo o ficheiro não tem nome: o do ZIP leva o do cliente
    nome_neutro = f"documento{extensao}"
    mime = {".pdf": "application/pdf", ".png": "image/png"}.get(extensao, "image/jpeg")

    tipo = None if classificar_sempre else pista_do_tipo(info.filename)
    if tipo is None:
        resumo.chamadas_ia += 1
        classificacao = await classificar_documento(conteudo=conteudo, filename=nome_neutro, mime=mime)
        if classificacao.tipo is None:
            return "falha_ia"  # «não sei» (IA em baixo, sem conteúdo): não se lembra, tenta-se de novo
        tipo = classificacao.tipo
        if tipo in (TIPO_OUTRO, TIPO_IDENTIFICACAO):
            estado = "identificacao" if tipo == TIPO_IDENTIFICACAO else "outro"
            await store.marcar_visto_no_arquivo(doc_id, resumo.import_id, estado)
            return estado
    if tipo == TIPO_IDENTIFICACAO:
        return "identificacao"  # a pista chegou: nem se paga a leitura

    resumo.chamadas_ia += 1
    resultado = await analisar_documento(tipo=tipo, conteudo=conteudo, filename=nome_neutro, mime=mime, document_id=doc_id)
    if not resultado.ok:
        return "falha_ia"
    linha = store.linha_historica(resultado, document_id=doc_id, import_id=resumo.import_id, network_id=rede, label=label)
    if not tem_dados_uteis(linha):
        await store.marcar_visto_no_arquivo(doc_id, resumo.import_id, "sem_dados")
        return "sem_dados"

    inserida = await store.gravar_documento_historico(linha)
    if tipo == TIPO_RECIBO and resultado.job is not None:
        resumo.entidades_novas += await store.registar_entidades([resultado.job])
    elif tipo == TIPO_DECLARACAO:
        resumo.entidades_novas += await store.registar_entidades([], extra=store.entidades_das_declaracoes([resultado.factos]))
    return "importado" if inserida else "ja_importado"


async def desfazer_importacao(import_id: str) -> int:
    """Apaga as linhas de UMA importação. Devolve quantas."""
    return await store.apagar_importacao_historica(import_id)


__all__ = [
    "IASimulada", "RedeDesconhecida", "ZipInvalido", "Resumo", "analise_previa", "desfazer_importacao",
    "etiqueta_da_importacao", "hash_do_zip", "id_do_documento", "importar_zip", "import_id_do_zip",
    "ler_membro", "membros_candidatos", "motivo_de_exclusao", "pista_do_tipo", "rede_existe", "redes_conhecidas",
    "tem_dados_uteis",
]
