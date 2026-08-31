"""
leitor_cliente.py
-----------------
Le a planilha "baguncada" do cliente (xlsx/csv) e devolve:
  - lista de colunas encontradas
  - lista de registros (dicts)
Assume que a primeira linha e o cabecalho. Ajuste 'linha_cabecalho'
se o cliente tiver titulo/linhas em branco no topo.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def ler_planilha_cliente(
    caminho: str,
    *,
    aba: str | int = 0,
    linha_cabecalho: int = 0,
) -> tuple[list[str], list[dict[str, Any]]]:
    ext = Path(caminho).suffix.lower()
    if ext in (".xlsx", ".xlsm", ".xls"):
        df = pd.read_excel(caminho, sheet_name=aba, header=linha_cabecalho,
                           dtype=object)
    elif ext in (".csv", ".txt"):
        df = pd.read_csv(caminho, header=linha_cabecalho, dtype=object,
                         sep=None, engine="python")
    elif ext == ".tsv":
        df = pd.read_csv(caminho, header=linha_cabecalho, dtype=object,
                         sep="\t")
    else:
        raise ValueError(f"Formato nao suportado: {ext}")

    df.columns = [str(c).strip() for c in df.columns]
    df = df.where(pd.notnull(df), None)      # NaN -> None

    colunas = list(df.columns)
    registros = df.to_dict(orient="records")
    return colunas, registros


def sugerir_mapeamento(
    colunas_cliente: list[str],
    colunas_cigam: list[str],
) -> dict[str, str]:
    """
    Sugestao automatica simples de De-Para por similaridade de nome
    (normalizando acentos, espacos e underscores). O usuario revisa/ajusta
    na tela. Retorna {coluna_cigam: coluna_cliente}.
    """
    import unicodedata

    def norm(s: str) -> str:
        s = unicodedata.normalize("NFKD", str(s))
        s = "".join(c for c in s if not unicodedata.combining(c))
        return s.lower().replace("_", "").replace(" ", "").strip()

    idx_cli = {norm(c): c for c in colunas_cliente}
    mapa: dict[str, str] = {}
    for cig in colunas_cigam:
        n = norm(cig)
        if n in idx_cli:
            mapa[cig] = idx_cli[n]
        else:
            for ncli, cli in idx_cli.items():
                if n and (n in ncli or ncli in n):
                    mapa[cig] = cli
                    break
    return mapa
