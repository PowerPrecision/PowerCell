"""RGPD text template admin endpoints + active-template lookup.

Extraído de `routes/rgpd.py`.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field

from database import db

logger = logging.getLogger(__name__)

RGPD_TEMPLATE_VERSIONS_COLLECTION = "rgpd_template_versions"

# Pacote FQ-4 — a Precision Crédito, Lda. é a única entidade que emite
# pedidos de RGPD (a Power Real Estate, Lda. não emite pedidos de RGPD).
# Este emissor/responsável pelo tratamento é FIXO e não deve depender de
# configuração dinâmica (system_config / empresa activa do utilizador).
RGPD_ISSUER_NAME = "Precision Crédito, Lda."
RGPD_ISSUER_NIF = "515657514"

RGPD_DEFAULT_TEMPLATE = """AUTORIZAÇÃO PARA TRATAMENTO DE DADOS PESSOAIS – RGPD

Nos termos do Regulamento (UE) 2016/679 do Parlamento Europeu e do Conselho (Regulamento Geral sobre a Proteção de Dados – "RGPD"), o titular dos dados abaixo identificado autoriza expressamente o tratamento dos seus dados pessoais pela entidade responsável pelo tratamento, nos seguintes termos:

1. RESPONSÁVEL PELO TRATAMENTO
Empresa: Precision Crédito, Lda.
NIF: 515657514
Morada: {{MORADA_EMPRESA}}
Contacto: {{CONTACTO_EMPRESA}}

2. TITULAR DOS DADOS
Nome Completo: {{NOME}}
NIF/Contribuinte: {{CONTRIBUINTE}}
Morada: {{MORADA}}
Código Postal: {{CODIGO_POSTAL}}

3. TIPO DE DOCUMENTO DE IDENTIFICAÇÃO
Tipo: {{TIPO_DOCUMENTO}}
Número: {{NUMERO_DOCUMENTO}}
Validade: {{VALIDADE_DOCUMENTO}}

4. FINALIDADE DO TRATAMENTO
Os dados pessoais recolhidos são tratados para as seguintes finalidades:
a) Gestão do processo de mediação imobiliária;
b) Cumprimento de obrigações legais e regulatórias;
c) Comunicação relacionada com o processo em curso;
d) Elaboração de documentação contratual e fiscal.

5. CATEGORIAS DE DADOS PESSOAIS TRATADOS
- Dados de identificação (nome, NIF, documento de identificação);
- Dados de contacto (morada, código postal, telefone, email);
- Dados financeiros (relacionados com o processo imobiliário);
- Dados profissionais (profissão, entidade empregadora).

6. BASE LEGAL PARA O TRATAMENTO
O tratamento dos dados pessoais é realizado com base no consentimento do titular (Art. 6.º, n.º 1, alínea a) do RGPD) e na execução de contrato (Art. 6.º, n.º 1, alínea b) do RGPD).

7. CONSERVAÇÃO DOS DADOS
Os dados pessoais serão conservados durante o período necessário para a execução do processo e durante o prazo legalmente exigido para efeitos de responsabilização, não excedendo o prazo máximo de 10 (dez) anos após a conclusão do processo.

8. DIREITOS DO TITULAR
O titular dos dados tem o direito de:
- Aceder aos seus dados pessoais;
- Retificar dados incorretos ou incompletos;
- Solicitar a eliminação dos dados ("direito ao esquecimento");
- Limitar o tratamento dos dados;
- Solicitar a portabilidade dos dados;
- Opor-se ao tratamento dos dados;
- Retirar o consentimento a qualquer momento, sem comprometer a licitude do tratamento efetuado até essa data.

Para exercer os seus direitos, o titular pode contactar o responsável pelo tratamento através do endereço de email: [Email DPO] ou por escrito para a morada indicada no ponto 1.

9. PARTILHA DE DADOS
Os dados pessoais poderão ser partilhados com:
- Entidades bancárias, no âmbito da solicitação de financiamento;
- Notários e Conservatórias, para efeitos de escritura pública;
- Autoridades fiscais e tributárias;
- Outras entidades legalmente autorizadas.

10. COOKIES E TECNOLOGIAS DE RASTREAMENTO
Informamos que poderão ser utilizadas tecnologias de rastreamento no âmbito do processo, sempre com o conhecimento e consentimento do titular.

11. DECISÕES AUTOMATIZADAS
Informamos que não são tomadas decisões baseadas exclusivamente no tratamento automatizado, incluindo a definição de perfis, que produzam efeitos jurídicos ou de forma similar.

DECLARAÇÃO FINAL:
O titular dos dados declara ter sido informado de forma clara e completa sobre o tratamento dos seus dados pessoais, nos termos do disposto no Regulamento Geral sobre a Proteção de Dados (RGPD), e consente expressamente com o tratamento acima descrito.

Data: {{DATA_ASSINATURA}}
Assinatura: _________________________________"""


class RGPDTemplateUpdate(BaseModel):
    """Modelo para actualização do template RGPD."""
    content: str
    changelog: Optional[str] = Field(None, description="Descrição opcional da alteração realizada")


async def _get_active_rgpd_template() -> Optional[str]:
    """
    Função auxiliar para obter o texto do template RGPD ativo.

    Prioridade:
    1. Versão ativa na coleção rgpd_template_versions
    2. Conteúdo em system_config (compatibilidade retroativa)
    3. Template padrão definido no código

    Returns:
        Texto do template ou None em caso de erro
    """
    try:
        active_version = await db[RGPD_TEMPLATE_VERSIONS_COLLECTION].find_one(
            {"is_active": True},
            {"_id": 0, "content": 1},
        )
        if active_version and active_version.get("content"):
            return active_version["content"]

        doc = await db.system_config.find_one(
            {"_id": "rgpd_template"},
            {"_id": 0, "content": 1},
        )
        if doc and doc.get("content"):
            return doc["content"]

        return RGPD_DEFAULT_TEMPLATE
    except Exception as e:
        logger.error(f"Erro ao obter template RGPD ativo: {e}")
        return RGPD_DEFAULT_TEMPLATE


async def run_get_rgpd_template(user: dict):
    """Obter o template de texto RGPD."""
    try:
        doc = await db.system_config.find_one({"_id": "rgpd_template"}, {"_id": 0})

        if doc and doc.get("content"):
            return {
                "content": doc["content"],
                "updated_at": doc.get("updated_at"),
                "updated_by": doc.get("updated_by"),
                "is_default": False,
                "active_version_id": doc.get("active_version_id"),
                "active_version": doc.get("active_version"),
            }

        return {
            "content": RGPD_DEFAULT_TEMPLATE,
            "updated_at": None,
            "updated_by": None,
            "is_default": True,
            "active_version_id": None,
            "active_version": None,
        }
    except Exception as e:
        logger.error(f"Erro ao obter template RGPD: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao obter template RGPD")


async def run_update_rgpd_template(template_data: RGPDTemplateUpdate, user: dict):
    """Atualizar o template de texto RGPD (com versionamento)."""
    try:
        now = datetime.now(timezone.utc).isoformat()
        created_by = user.get("name", user.get("email", "unknown"))

        last_version = await db[RGPD_TEMPLATE_VERSIONS_COLLECTION].find_one(
            sort=[("version", -1)]
        )
        next_version = (last_version["version"] + 1) if last_version else 1

        new_version_id = str(uuid.uuid4())
        version_doc = {
            "id": new_version_id,
            "content": template_data.content,
            "version": next_version,
            "changelog": template_data.changelog,
            "created_at": now,
            "created_by": created_by,
            "is_active": True,
        }
        await db[RGPD_TEMPLATE_VERSIONS_COLLECTION].insert_one(version_doc)

        await db[RGPD_TEMPLATE_VERSIONS_COLLECTION].update_many(
            {"id": {"$ne": new_version_id}},
            {"$set": {"is_active": False}},
        )

        await db.system_config.update_one(
            {"_id": "rgpd_template"},
            {
                "$set": {
                    "content": template_data.content,
                    "active_version_id": new_version_id,
                    "active_version": next_version,
                    "updated_at": now,
                    "updated_by": created_by,
                },
                "$setOnInsert": {
                    "created_at": now,
                },
            },
            upsert=True,
        )

        logger.info(f"Template RGPD versão {next_version} criada por {created_by}")

        return {
            "success": True,
            "message": f"Template RGPD atualizado com sucesso (versão {next_version})",
            "version": next_version,
            "version_id": new_version_id,
            "updated_at": now,
        }
    except Exception as e:
        logger.error(f"Erro ao atualizar template RGPD: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao atualizar template RGPD")


async def run_list_rgpd_template_versions(user: dict):
    """Listar todas as versões do template RGPD (sem conteúdo completo)."""
    try:
        versions = await db[RGPD_TEMPLATE_VERSIONS_COLLECTION].find(
            {},
            {"_id": 0, "content": 0},
        ).sort("version", -1).to_list(100)

        return {
            "versions": versions,
            "total": len(versions),
        }
    except Exception as e:
        logger.error(f"Erro ao listar versões do template RGPD: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao listar versões do template RGPD")


async def run_get_rgpd_template_version(version_id: str, user: dict):
    """Obter o conteúdo completo de uma versão específica do template RGPD."""
    try:
        version = await db[RGPD_TEMPLATE_VERSIONS_COLLECTION].find_one(
            {"id": version_id},
            {"_id": 0},
        )

        if not version:
            raise HTTPException(status_code=404, detail="Versão do template RGPD não encontrada")

        return version
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter versão do template RGPD: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao obter versão do template RGPD")
