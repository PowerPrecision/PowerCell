"""Helpers de paths S3 (variações underscore/espaço)."""
from __future__ import annotations


def s3_path_variations(file_path: str) -> list[str]:
    """Gera variações de path para tolerar underscore vs espaço no S3."""
    variations = [file_path]
    if "_" in file_path:
        variations.append(file_path.replace("_", " "))
    if " " in file_path:
        variations.append(file_path.replace(" ", "_"))
    if "Documentação Clientes/" in file_path:
        variations.append(
            file_path.replace("Documentação Clientes/", "Documentação_Clientes/")
        )
    if "Documentação_Clientes/" in file_path:
        variations.append(
            file_path.replace("Documentação_Clientes/", "Documentação Clientes/")
        )
    # Deduplicate preserving order
    seen = set()
    out = []
    for v in variations:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out
