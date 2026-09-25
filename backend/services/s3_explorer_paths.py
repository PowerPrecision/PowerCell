"""Contenção de caminhos do Explorador de Ficheiros S3.

PORQUE EXISTE
=============
O explorador (`/ficheiros`) navega o BUCKET INTEIRO, e o bucket não guarda só
documentos de clientes — os **backups da base de dados** vivem no mesmo sítio,
sob `backups/`. Três das seis operações aceitavam uma chave S3 arbitrária,
sem contenção nenhuma:

    run_s3_download(path)      → get_object(Key=path)   → backups/dump.gz
    run_s3_delete(data.path)   → apaga o prefixo        → backups/
    run_s3_rename(old_path)    → move o prefixo         → qualquer coisa

Não era preciso `../`: bastava escrever `backups/`. E as outras três passavam
por uma verificação `path.startswith("Documentação Clientes")`, que aceita
tanto `Documentação Clientes/../backups` (o `..` nunca era resolvido) como
`Documentação Clientes_outro/` (prefixo de TEXTO não é fronteira de
SEGMENTO).

A REGRA
=======
Todo o caminho que entra no explorador é normalizado (`.`, `..`, barras
repetidas) e tem de cair **dentro** da raiz depois de resolvido. Um caminho
que saia é recusado com 400 — antes de tocar no S3.

Isto é pré-requisito de abrir a página a utilizadores normais, não um extra:
sem contenção, o filtro por rede do Passo 3 seria uma fechadura numa porta
que se pode contornar pelo lado.
"""
from __future__ import annotations

import posixpath
from typing import Optional

from fastapi import HTTPException

# Pasta raiz virtual do explorador dentro do bucket.
RAIZ_DO_EXPLORADOR = "Documentação Clientes"


def _texto(valor) -> str:
    return valor.strip() if isinstance(valor, str) else ""


def normalizar_caminho(path) -> str:
    """Resolve o caminho e devolve-o com a raiz do explorador à frente.

    Um caminho vazio é a raiz. Um caminho relativo passa a ser relativo à
    raiz. `.`, `..` e barras repetidas são resolvidos AQUI — não resolver o
    `..` era metade da falha, porque `startswith` dava-o por bom.

    O resultado pode cair FORA da raiz (é assim que se detecta a fuga);
    quem decide é `caminho_dentro_da_raiz`.
    """
    bruto = _texto(path)
    if not bruto:
        return RAIZ_DO_EXPLORADOR

    # Um caminho absoluto nunca é do explorador; mantém-se absoluto para que
    # a verificação de fronteira o recuse em vez de o "arrumar" na raiz.
    if bruto.startswith("/"):
        return posixpath.normpath(bruto)

    if not _comeca_na_raiz(bruto):
        bruto = f"{RAIZ_DO_EXPLORADOR}/{bruto}"

    return posixpath.normpath(bruto)


def _comeca_na_raiz(path: str) -> bool:
    """Fronteira de SEGMENTO, não prefixo de texto.

    `Documentação Clientes_outro` começa pelo mesmo texto e não é a raiz.
    """
    return path == RAIZ_DO_EXPLORADOR or path.startswith(f"{RAIZ_DO_EXPLORADOR}/")


def caminho_dentro_da_raiz(path) -> bool:
    """O caminho, depois de resolvido, fica dentro da raiz do explorador?"""
    return _comeca_na_raiz(normalizar_caminho(path))


def assert_dentro_da_raiz(path) -> str:
    """Devolve o caminho normalizado, ou levanta 400.

    400 e não 404: não é um recurso que não existe, é um pedido malformado —
    e a mensagem não diz o que há fora da raiz.
    """
    normalizado = normalizar_caminho(path)
    if not _comeca_na_raiz(normalizado):
        raise HTTPException(status_code=400, detail="Caminho inválido")
    return normalizado


def primeiro_segmento(path) -> Optional[str]:
    """A pasta de cliente do caminho (o segmento a seguir à raiz).

    É aqui que a decisão de âmbito por rede vai viver (Passo 3): tudo o que
    está abaixo de `Documentação Clientes/Joao_Silva/` é do Joao_Silva, pelo
    que a profundidade não acrescenta decisão nenhuma.

    Normaliza ANTES de extrair: sem isso, `Joao/../Maria` daria `Joao` e a
    decisão seria tomada sobre o cliente errado.
    """
    normalizado = normalizar_caminho(path)
    if not _comeca_na_raiz(normalizado) or normalizado == RAIZ_DO_EXPLORADOR:
        return None
    resto = normalizado[len(RAIZ_DO_EXPLORADOR) + 1:]
    return resto.split("/")[0] or None
