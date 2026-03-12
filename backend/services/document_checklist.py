"""
Serviço para verificação de documentos no OneDrive
Verifica se os documentos esperados existem na pasta do cliente
"""
import os
import re
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class DocumentStatus(str, Enum):
    """Estado de um documento na checklist"""
    PRESENTE = "presente"
    EM_FALTA = "em_falta"
    EXPIRADO = "expirado"
    A_EXPIRAR = "a_expirar"  # Expira em menos de 30 dias
    NAO_VERIFICADO = "nao_verificado"


# Lista de documentos esperados por tipo de processo
DOCUMENTOS_CREDITO_HABITACAO = [
    {
        "id": "cc_titular",
        "nome": "Cartão de Cidadão - Titular",
        "patterns": ["cc", "cartao cidadao", "cidadao", "bi", "identificacao"],
        "obrigatorio": True,
        "validade_meses": None,  # Não expira (verificar manualmente)
    },
    {
        "id": "cc_conjuge",
        "nome": "Cartão de Cidadão - Cônjuge",
        "patterns": ["cc conjuge", "cc 2", "conjuge", "segundo titular"],
        "obrigatorio": False,
        "validade_meses": None,
    },
    {
        "id": "recibo_vencimento",
        "nome": "Recibos de Vencimento (3 últimos)",
        "patterns": ["recibo", "vencimento", "salario", "ordenado", "payslip"],
        "obrigatorio": True,
        "validade_meses": 3,
    },
    {
        "id": "irs",
        "nome": "Declaração IRS / P60",
        "patterns": ["irs", "declaracao", "p60", "p45", "imposto"],
        "obrigatorio": True,
        "validade_meses": 12,
    },
    {
        "id": "extrato_bancario",
        "nome": "Extratos Bancários (3 últimos)",
        "patterns": ["extrato", "bancario", "conta", "bank statement"],
        "obrigatorio": True,
        "validade_meses": 3,
    },
    {
        "id": "contrato_trabalho",
        "nome": "Contrato de Trabalho / Declaração Entidade Patronal",
        "patterns": ["contrato", "trabalho", "vinculo", "efetividade", "employment"],
        "obrigatorio": True,
        "validade_meses": None,
    },
    {
        "id": "certidao_domicilio_fiscal",
        "nome": "Certidão de Domicílio Fiscal",
        "patterns": ["certidao", "domicilio", "fiscal", "morada"],
        "obrigatorio": True,
        "validade_meses": 6,
    },
    {
        "id": "mapa_crc",
        "nome": "Mapa de Responsabilidades (CRC)",
        "patterns": ["crc", "responsabilidade", "mapa", "central"],
        "obrigatorio": True,
        "validade_meses": 1,
    },
    {
        "id": "caderneta_predial",
        "nome": "Caderneta Predial",
        "patterns": ["caderneta", "predial"],
        "obrigatorio": True,
        "validade_meses": None,
    },
    {
        "id": "certidao_permanente",
        "nome": "Certidão Permanente do Imóvel",
        "patterns": ["certidao permanente", "registo predial", "conservatoria"],
        "obrigatorio": True,
        "validade_meses": 6,
    },
    {
        "id": "cpcv",
        "nome": "CPCV (Contrato Promessa Compra e Venda)",
        "patterns": ["cpcv", "promessa", "compra venda", "sinal"],
        "obrigatorio": False,
        "validade_meses": None,
    },
    {
        "id": "simulacao",
        "nome": "Simulação de Crédito",
        "patterns": ["simulacao", "simulação", "proposta", "financiamento"],
        "obrigatorio": False,
        "validade_meses": 1,
    },
]


def check_document_in_files(doc_config: dict, files: List[str]) -> Dict[str, Any]:
    """
    Verifica se um documento específico existe na lista de ficheiros.
    
    Args:
        doc_config: Configuração do documento esperado
        files: Lista de nomes de ficheiros na pasta
        
    Returns:
        Resultado da verificação com status e ficheiros encontrados
    """
    patterns = doc_config.get("patterns", [])
    found_files = []
    
    for filename in files:
        filename_lower = filename.lower()
        for pattern in patterns:
            if pattern.lower() in filename_lower:
                found_files.append(filename)
                break
    
    # Determinar status
    if found_files:
        status = DocumentStatus.PRESENTE
        # TODO: Verificar validade baseado na data do ficheiro
    else:
        status = DocumentStatus.EM_FALTA
    
    return {
        "id": doc_config["id"],
        "nome": doc_config["nome"],
        "obrigatorio": doc_config.get("obrigatorio", False),
        "validade_meses": doc_config.get("validade_meses"),
        "status": status.value,
        "ficheiros": found_files,
        "quantidade": len(found_files),
    }


def generate_checklist(files: List[str], tipo_processo: str = "credito_habitacao") -> Dict[str, Any]:
    """
    Gera uma checklist completa de documentos baseada nos ficheiros encontrados.
    
    Args:
        files: Lista de nomes de ficheiros na pasta do cliente
        tipo_processo: Tipo de processo (para seleccionar documentos esperados)
        
    Returns:
        Checklist completa com status de cada documento
    """
    # Seleccionar lista de documentos baseado no tipo
    if tipo_processo == "credito_habitacao":
        docs_esperados = DOCUMENTOS_CREDITO_HABITACAO
    else:
        docs_esperados = DOCUMENTOS_CREDITO_HABITACAO  # Default
    
    checklist = []
    total_obrigatorios = 0
    encontrados_obrigatorios = 0
    
    for doc_config in docs_esperados:
        result = check_document_in_files(doc_config, files)
        checklist.append(result)
        
        if doc_config.get("obrigatorio"):
            total_obrigatorios += 1
            if result["status"] == DocumentStatus.PRESENTE.value:
                encontrados_obrigatorios += 1
    
    # Calcular percentagem de conclusão
    percentagem = (encontrados_obrigatorios / total_obrigatorios * 100) if total_obrigatorios > 0 else 0
    
    return {
        "checklist": checklist,
        "resumo": {
            "total_documentos": len(checklist),
            "total_obrigatorios": total_obrigatorios,
            "encontrados_obrigatorios": encontrados_obrigatorios,
            "em_falta_obrigatorios": total_obrigatorios - encontrados_obrigatorios,
            "percentagem_conclusao": round(percentagem, 1),
        },
        "ficheiros_analisados": len(files),
        "tipo_processo": tipo_processo,
    }


def get_documentos_em_falta(checklist_result: Dict[str, Any], apenas_obrigatorios: bool = True) -> List[Dict]:
    """
    Retorna lista de documentos em falta.
    """
    em_falta = []
    for doc in checklist_result.get("checklist", []):
        if doc["status"] == DocumentStatus.EM_FALTA.value:
            if not apenas_obrigatorios or doc.get("obrigatorio"):
                em_falta.append(doc)
    return em_falta


def get_documentos_a_expirar(checklist_result: Dict[str, Any], dias: int = 30) -> List[Dict]:
    """
    Retorna lista de documentos que vão expirar em breve.
    Nota: Requer datas dos ficheiros para funcionar completamente.
    """
    # TODO: Implementar verificação de datas
    return []
