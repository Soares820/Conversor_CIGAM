"""
limpeza.py
----------
Limpeza basica da planilha do cliente, independente do De-Para de uma
tabela especifica: normaliza espacos, remove linhas totalmente
duplicadas e colunas 100% vazias. Nao decide regra de negocio nenhuma —
so tira o "lixo" mais comum de planilha exportada por sistemas diferentes,
antes de o usuario ir para a tela de mapeamento.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import openpyxl


@dataclass
class ResultadoLimpeza:
    colunas: list[str]
    registros: list[dict[str, Any]]
    linhas_removidas: int = 0
    celulas_normalizadas: int = 0
    colunas_vazias_removidas: list[str] = field(default_factory=list)


def limpar_registros(
    colunas: list[str],
    registros: list[dict[str, Any]],
    *,
    remover_duplicados: bool = True,
    normalizar_espacos: bool = True,
    remover_colunas_vazias: bool = True,
) -> ResultadoLimpeza:
    colunas_atuais = list(colunas)
    celulas_normalizadas = 0

    limpos: list[dict[str, Any]] = []
    for reg in registros:
        novo = dict(reg)
        if normalizar_espacos:
            for k, v in novo.items():
                if isinstance(v, str):
                    v2 = " ".join(v.split())
                    if v2 != v:
                        celulas_normalizadas += 1
                    novo[k] = v2 if v2 else None
        limpos.append(novo)

    linhas_removidas = 0
    if remover_duplicados:
        vistos: set[tuple] = set()
        sem_dup = []
        for reg in limpos:
            chave = tuple(reg.get(c) for c in colunas_atuais)
            if chave in vistos:
                linhas_removidas += 1
                continue
            vistos.add(chave)
            sem_dup.append(reg)
        limpos = sem_dup

    colunas_vazias_removidas = []
    if remover_colunas_vazias:
        for col in colunas_atuais:
            if all(reg.get(col) in (None, "") for reg in limpos):
                colunas_vazias_removidas.append(col)
        if colunas_vazias_removidas:
            colunas_atuais = [c for c in colunas_atuais if c not in colunas_vazias_removidas]

    return ResultadoLimpeza(
        colunas=colunas_atuais,
        registros=limpos,
        linhas_removidas=linhas_removidas,
        celulas_normalizadas=celulas_normalizadas,
        colunas_vazias_removidas=colunas_vazias_removidas,
    )


def gerar_xlsx_limpo(colunas: list[str], registros: list[dict[str, Any]], caminho: str) -> str:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Planilha limpa"
    ws.append(colunas)
    for reg in registros:
        ws.append([reg.get(c) for c in colunas])
    wb.save(caminho)
    return caminho
