"""Client S3 mapping ops (auto-map) — aliases live in the route stubs.

Do NOT name this module `admin_storage.py` (collides with routes/admin_storage.py).
Extraído de `routes/admin_storage.py`.
"""
from __future__ import annotations

import logging
import re

from fastapi import HTTPException

from database import db
from services.s3_document_root import e_id_gerado

logger = logging.getLogger(__name__)


async def run_auto_map_client_s3_folders(user: dict):
    """
    Mapeamento automático de pastas S3 ↔ processos, **só quando é inequívoco**.

    LOTE 6, ponto 1 — O BOTÃO QUE FABRICAVA A COLISÃO
    =================================================
    Esta função resolvia pasta → processo com três tentativas, a última das
    quais um `find_one` sobre
    ``{"client_name": {"$regex": f"{primeiro}.*{último}"}}`` — e ficava com o
    PRIMEIRO documento que o Mongo devolvesse, **sem verificar unicidade**. A
    pasta `Carolina_Silva` casa com "Carolina Silva" e com "Carolina Agostinho
    da Silva"; qual das duas era escolhida dependia da ordem de varrimento.
    Depois gravava `s3_folder`, de forma permanente.

    Hoje:
      * conta TODOS os candidatos de cada tentativa e **recusa quando há mais
        do que um** — a pasta vai para `ambiguas` e espera decisão humana
        (é para isso que existe o religamento manual);
      * o nome da pasta é escapado com ``re.escape`` antes de entrar no
        ``$regex`` — as pastas antigas foram criadas à mão no Explorador e um
        parêntese no nome fazia a consulta casar com outra coisa, ou rebentar;
      * nunca sobrescreve um `s3_folder` existente (já era assim).

    A diferença entre "não encontrei" e "encontrei dois" é a que importa: a
    primeira é trabalho pendente, a segunda é um cruzamento de dados à espera
    de acontecer.
    """
    from services.s3_storage import s3_service

    if not s3_service.is_configured():
        raise HTTPException(status_code=503, detail="S3 não configurado")

    results = {
        "mapped": 0,
        "skipped": 0,
        "updated_names": 0,
        "ambiguas": [],
        "errors": [],
    }

    PROJECCAO = {"_id": 0, "id": 1, "s3_folder": 1, "client_name": 1}

    async def _candidatos(padrao: str) -> list[dict]:
        """Os processos que casam — no PLURAL, de propósito."""
        return await db.processes.find(
            {"client_name": {"$regex": padrao, "$options": "i"}}, PROJECCAO
        ).to_list(length=5)

    try:
        response = s3_service.s3_client.list_objects_v2(
            Bucket=s3_service.bucket_name,
            Prefix="Documentação Clientes/",
            Delimiter="/",
        )

        folders = []
        for prefix in response.get("CommonPrefixes", []):
            folder_path = prefix.get("Prefix", "").rstrip("/")
            folder_name = folder_path.replace("Documentação Clientes/", "")
            if folder_name:
                folders.append({"path": folder_path, "name": folder_name})

        for folder in folders:
            folder_name = folder["name"]
            folder_name_readable = folder_name.replace("_", " ").replace("  ", " ")

            # As tentativas, da mais exacta para a mais lata. A ordem importa:
            # um nome exacto não deve ser recusado por o padrão largo também
            # casar com outro processo.
            tentativas = [
                f"^{re.escape(folder_name)}$",
                f"^{re.escape(folder_name_readable)}$",
            ]
            partes = folder_name_readable.split()
            if len(partes) >= 2:
                tentativas.append(
                    f"^{re.escape(partes[0])}.*{re.escape(partes[-1])}$"
                )

            candidatos: list[dict] = []
            for padrao in tentativas:
                candidatos = await _candidatos(padrao)
                if candidatos:
                    break

            if not candidatos:
                results["skipped"] += 1
                continue

            if len(candidatos) > 1:
                # Mapear aqui seria escolher um cliente à sorte e gravá-lo.
                results["ambiguas"].append({
                    "pasta": folder["path"],
                    "processos": [c.get("id") for c in candidatos],
                    "nomes": [c.get("client_name") for c in candidatos],
                })
                logger.warning(
                    "[AUTO-MAP] Pasta %s casa com %d processos (%s) — não mapeada.",
                    folder["path"], len(candidatos),
                    ", ".join(str(c.get("client_name")) for c in candidatos),
                )
                continue

            process = candidatos[0]
            if process.get("s3_folder"):
                results["skipped"] += 1
                continue

            update_fields = {"s3_folder": folder["path"]}
            # Um uuid não é um nome: ver a guarda gémea em
            # `admin_s3_process_mappings.run_fix_missing_client_names`.
            if (
                not e_id_gerado(folder_name)
                and (
                    not process.get("client_name")
                    or process.get("client_name") == "Sem nome"
                )
            ):
                update_fields["client_name"] = folder_name_readable
                results["updated_names"] += 1

            await db.processes.update_one(
                {"id": process["id"]}, {"$set": update_fields}
            )
            results["mapped"] += 1

    except Exception as e:
        results["errors"].append(str(e))

    return results
