"""
conversor.py
------------
Aplica o De-Para (mapeamento coluna CIGAM -> coluna do cliente),
injeta defaults do gabarito, valida e gera as linhas no layout CIGAM.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from .template import CigamTemplate


@dataclass
class Ocorrencia:
    """Um problema encontrado durante a validacao."""
    severidade: str          # "erro" | "aviso"
    linha: int               # indice da linha de dados (1-based), 0 = geral
    coluna: str
    mensagem: str

    def __str__(self) -> str:
        loc = f"linha {self.linha}, " if self.linha else ""
        return f"[{self.severidade.upper()}] {loc}{self.coluna}: {self.mensagem}"


@dataclass
class ResultadoConversao:
    tabela: str
    colunas: list[str]
    linhas: list[list[Any]]
    ocorrencias: list[Ocorrencia] = field(default_factory=list)

    @property
    def erros(self) -> list[Ocorrencia]:
        return [o for o in self.ocorrencias if o.severidade == "erro"]

    @property
    def avisos(self) -> list[Ocorrencia]:
        return [o for o in self.ocorrencias if o.severidade == "aviso"]

    @property
    def ok(self) -> bool:
        return not self.erros


class Conversor:
    """Converte linhas do cliente para o layout de uma tabela CIGAM."""

    def __init__(self, template: CigamTemplate):
        self.t = template

    # ------------------------------------------------------------------ #
    def converter(
        self,
        linhas_cliente: list[dict],
        mapeamento: dict[str, str],
        *,
        truncar: bool = False,
        pk: list[str] | None = None,
        obrigatorios: list[str] | None = None,
    ) -> ResultadoConversao:
        """
        linhas_cliente : lista de dicts (uma por registro do cliente).
        mapeamento     : {coluna_cigam: coluna_cliente}.
        truncar        : se True, corta valores maiores que o tamanho do
                         campo (senao, apenas gera aviso).
        pk             : colunas CIGAM que formam a chave (checa duplicidade).
        obrigatorios   : colunas CIGAM que nao podem ficar vazias.
        """
        self._validar_mapeamento(mapeamento)

        oc: list[Ocorrencia] = []
        linhas: list[list[Any]] = []
        vistos_pk: set[tuple] = set()
        obrig = set(obrigatorios or [])

        for i, reg in enumerate(linhas_cliente, start=1):
            linha = self._montar_linha(reg, mapeamento, i, obrig, truncar, oc)
            linhas.append(linha)

            if pk:
                chave = tuple(linha[self.t.indice(c)] for c in pk)
                if chave in vistos_pk:
                    oc.append(Ocorrencia(
                        "erro", i, ",".join(pk),
                        f"PK duplicada: {chave}",
                    ))
                vistos_pk.add(chave)

        return ResultadoConversao(
            tabela=self.t.tabela,
            colunas=list(self.t.colunas),
            linhas=linhas,
            ocorrencias=oc,
        )

    # ------------------------------------------------------------------ #
    def _validar_mapeamento(self, mapeamento: dict[str, str]) -> None:
        for col_cigam in mapeamento:
            if col_cigam not in self.t.colunas:
                raise KeyError(
                    f"'{col_cigam}' nao e coluna de {self.t.tabela}."
                )

    def _montar_linha(
        self,
        reg: dict,
        mapeamento: dict[str, str],
        i: int,
        obrig: set[str],
        truncar: bool,
        oc: list[Ocorrencia],
    ) -> list[Any]:
        linha: list[Any] = []
        for idx, col in enumerate(self.t.colunas):
            origem = mapeamento.get(col)
            valor = reg.get(origem) if origem else None

            if valor in (None, ""):
                if col in obrig:
                    oc.append(Ocorrencia(
                        "erro", i, col, "campo obrigatorio vazio",
                    ))
                valor = self.t.defaults[idx]      # injeta default do gabarito
            else:
                valor = self._checar_tamanho(valor, idx, col, i, truncar, oc)

            linha.append(valor)
        return linha

    def _checar_tamanho(
        self, valor: Any, idx: int, col: str, i: int,
        truncar: bool, oc: list[Ocorrencia],
    ) -> Any:
        tam = self.t.tamanhos[idx]
        if tam is None or isinstance(valor, (int, float, date, datetime)):
            return valor
        s = str(valor)
        if len(s) > tam:
            if truncar:
                oc.append(Ocorrencia(
                    "aviso", i, col,
                    f"valor truncado de {len(s)} para {tam} chars",
                ))
                return s[:tam]
            oc.append(Ocorrencia(
                "aviso", i, col,
                f"tamanho {len(s)} excede o limite {tam}",
            ))
        return valor
