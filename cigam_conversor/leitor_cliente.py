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

import re
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd


def ler_planilha_cliente(
    caminho,
    *,
    aba: str | int = 0,
    linha_cabecalho: int = 0,
) -> tuple[list[str], list[dict[str, Any]]]:
    """
    caminho: caminho de arquivo (str/Path) OU um objeto tipo-arquivo com
    atributo `.filename` (ex.: werkzeug FileStorage de um upload) — usado
    pela interface web para ler o upload direto da memoria, sem tocar em
    disco.
    """
    nome = caminho.filename if hasattr(caminho, "filename") else str(caminho)
    ext = Path(nome).suffix.lower()
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


def _normalizar_texto(s: Any) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().replace("_", "").replace(" ", "").strip()


def _normalizar_documento(s: Any) -> str:
    """So os digitos — pra comparar CNPJ/CPF sem depender de formatacao."""
    return re.sub(r"\D", "", str(s))


def sugerir_mapeamento(
    colunas_cliente: list[str],
    colunas_cigam: list[str],
) -> dict[str, str]:
    """
    Sugestao automatica simples de De-Para por similaridade de nome
    (normalizando acentos, espacos e underscores). O usuario revisa/ajusta
    na tela. Retorna {coluna_cigam: coluna_cliente}.
    """
    idx_cli = {_normalizar_texto(c): c for c in colunas_cliente}
    mapa: dict[str, str] = {}
    for cig in colunas_cigam:
        n = _normalizar_texto(cig)
        if n in idx_cli:
            mapa[cig] = idx_cli[n]
        else:
            for ncli, cli in idx_cli.items():
                if n and (n in ncli or ncli in n):
                    mapa[cig] = cli
                    break
    return mapa


def construir_lookup_empresas(
    registros_referencia: list[dict],
    *,
    col_codigo: str = "Cd_empresa",
    cols_documento: tuple[str, ...] = ("Cnpj_cpf",),
    cols_nome: tuple[str, ...] = ("Nome_completo", "Fantasia"),
) -> dict[str, dict[str, str]]:
    """
    Monta as tabelas de busca a partir de uma planilha de referencia
    (ex.: SELECT * FROM GEEMPRES do banco, colado com cabecalho): uma
    por documento (CNPJ/CPF, so digitos) e outra por nome/razao social/
    fantasia (normalizado). Usado pra resolver "nome do fornecedor" ->
    Cd_empresa nas tabelas de Contas a Pagar/Receber.
    """
    por_documento: dict[str, str] = {}
    por_nome: dict[str, str] = {}
    for reg in registros_referencia:
        codigo = reg.get(col_codigo)
        if codigo in (None, ""):
            continue
        codigo = str(codigo).strip()

        for col in cols_documento:
            doc = reg.get(col)
            if doc not in (None, ""):
                chave = _normalizar_documento(doc)
                if chave:
                    por_documento[chave] = codigo

        for col in cols_nome:
            nome = reg.get(col)
            if nome not in (None, ""):
                por_nome[_normalizar_texto(nome)] = codigo

    return {"documento": por_documento, "nome": por_nome}
