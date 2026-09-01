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

from .leitor_cliente import _normalizar_documento, _normalizar_texto
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


class NumeradorSequencial:
    """Gera codigos sequenciais (zero-padded) pra registros novos que nao
    tem Cd_empresa ainda — continua a partir do maior codigo ja existente
    na planilha de referencia, pra nao colidir com quem ja esta cadastrado."""

    def __init__(self, proximo: int, largura: int):
        self._proximo = proximo
        self._largura = largura

    def gerar(self) -> str:
        codigo = str(self._proximo).zfill(self._largura)
        self._proximo += 1
        return codigo


def _eh_documento(regra: Any) -> bool:
    r = str(regra or "").upper()
    return "CNPJ" in r or "CPF" in r


def construir_numerador_empresas(
    registros_referencia: list[dict],
    template: CigamTemplate,
    *,
    col_codigo: str = "Cd_empresa",
) -> NumeradorSequencial | None:
    """
    A partir da mesma planilha de referencia usada no lookup, acha o
    maior Cd_empresa ja em uso e devolve um numerador pra continuar dali
    — usado ao gerar codigo novo pra cliente/fornecedor que ainda nao
    existe no GEEMPRES (quem ja existe reaproveita o codigo via lookup).
    """
    if col_codigo not in template.colunas:
        return None
    maximo = 0
    for reg in registros_referencia:
        codigo = str(reg.get(col_codigo) or "").strip()
        if codigo.isdigit():
            maximo = max(maximo, int(codigo))
    largura = template.tamanhos[template.indice(col_codigo)] or len(str(maximo)) or 6
    return NumeradorSequencial(maximo + 1, largura)


def detectar_forcar_sinal(template: CigamTemplate) -> dict[str, str] | None:
    """
    Em GFLANCAM, Valor/Vl_saldo tem que ser negativo em Contas a Pagar e
    positivo em Contas a Receber — o gabarito ja marca isso no default de
    Cd_tipo ('P' ou 'R') de cada aba. Devolve o forcar_sinal pronto pra
    passar em Conversor.converter, ou None se a tabela nao for essa.
    """
    if template.tabela != "GFLANCAM" or "Cd_tipo" not in template.colunas:
        return None
    tipo_default = template.defaults[template.indice("Cd_tipo")]
    sinal = {"P": "negativo", "R": "positivo"}.get(tipo_default)
    if not sinal:
        return None
    campos = [c for c in ("Valor", "Vl_saldo") if c in template.colunas]
    return {c: sinal for c in campos} if campos else None


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
        forcar_sinal: dict[str, str] | None = None,
        lookup: dict[str, dict[str, dict[str, str]]] | None = None,
        auto_numerar: dict[str, NumeradorSequencial] | None = None,
    ) -> ResultadoConversao:
        """
        linhas_cliente : lista de dicts (uma por registro do cliente).
        mapeamento     : {coluna_cigam: coluna_cliente}.
        truncar        : se True, corta valores maiores que o tamanho do
                         campo (senao, apenas gera aviso).
        pk             : colunas CIGAM que formam a chave (checa duplicidade).
        obrigatorios   : colunas CIGAM que nao podem ficar vazias.
        forcar_sinal   : {coluna: "negativo"|"positivo"} — forca o sinal do
                         valor numerico (usa o valor absoluto do que veio do
                         cliente/default). Existe porque em GFLANCAM, por
                         exemplo, Valor/Vl_saldo tem que ser negativo em
                         Contas a Pagar e positivo em Contas a Receber,
                         independente do sinal que o cliente mandou.
        lookup         : {coluna: tabelas} onde tabelas e o dict devolvido
                         por construir_lookup_empresas — troca o valor
                         (nome, razao social, fantasia ou CNPJ/CPF) pelo
                         Cd_empresa correspondente.
        auto_numerar   : {coluna: NumeradorSequencial} — quando o lookup
                         nao acha correspondencia (ou o campo nem veio
                         mapeado), gera um codigo novo em vez de erro.
                         Existe pra importar cliente/fornecedor novo no
                         proprio GEEMPRES: quem ja existe reaproveita o
                         codigo (lookup), quem nao existe ganha um codigo
                         sequencial novo (auto_numerar). Sem isso, uma
                         correspondencia nao encontrada vira erro.
        """
        self._validar_mapeamento(mapeamento)

        oc: list[Ocorrencia] = []
        linhas: list[list[Any]] = []
        vistos_pk: set[tuple] = set()
        obrig = set(obrigatorios or [])

        for i, reg in enumerate(linhas_cliente, start=1):
            linha = self._montar_linha(
                reg, mapeamento, i, obrig, truncar, oc, forcar_sinal, lookup, auto_numerar,
            )
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
        forcar_sinal: dict[str, str] | None = None,
        lookup: dict[str, dict] | None = None,
        auto_numerar: dict[str, NumeradorSequencial] | None = None,
    ) -> list[Any]:
        linha: list[Any] = []
        for idx, col in enumerate(self.t.colunas):
            origem = mapeamento.get(col)
            valor = reg.get(origem) if origem else None

            if valor not in (None, "") and _eh_documento(self.t.regras[idx]):
                valor = _normalizar_documento(valor) or valor

            if lookup and col in lookup and valor not in (None, ""):
                valor = self._resolver_lookup(
                    valor, col, lookup[col], i, oc,
                    numerador=(auto_numerar or {}).get(col),
                )

            if valor in (None, "") and auto_numerar and col in auto_numerar:
                valor = auto_numerar[col].gerar()
                oc.append(Ocorrencia(
                    "aviso", i, col,
                    f"código {valor} atribuído automaticamente (novo registro)",
                ))

            if valor in (None, ""):
                if col in obrig:
                    oc.append(Ocorrencia(
                        "erro", i, col, "campo obrigatorio vazio",
                    ))
                valor = self.t.defaults[idx]      # injeta default do gabarito
            else:
                valor = self._checar_tamanho(valor, idx, col, i, truncar, oc)

            if forcar_sinal and col in forcar_sinal:
                valor = self._aplicar_sinal(valor, col, forcar_sinal[col], i, oc)

            linha.append(valor)
        return linha

    def _resolver_lookup(
        self, valor: Any, col: str, tabelas: dict, i: int, oc: list[Ocorrencia],
        numerador: NumeradorSequencial | None = None,
    ) -> Any:
        bruto = str(valor).strip()

        doc = _normalizar_documento(bruto)
        if doc and doc in tabelas.get("documento", {}):
            return tabelas["documento"][doc]

        nome = _normalizar_texto(bruto)
        if nome in tabelas.get("nome", {}):
            return tabelas["nome"][nome]

        if numerador is not None:
            codigo = numerador.gerar()
            oc.append(Ocorrencia(
                "aviso", i, col,
                f"'{valor}' não encontrado na referência — novo registro, código {codigo} atribuído automaticamente",
            ))
            return codigo

        oc.append(Ocorrencia(
            "erro", i, col,
            f"'{valor}' não encontrado na planilha de referência (nem por CNPJ/CPF, nem por nome)",
        ))
        return None

    def _aplicar_sinal(
        self, valor: Any, col: str, sinal: str, i: int, oc: list[Ocorrencia],
    ) -> Any:
        if not isinstance(valor, (int, float)) or isinstance(valor, bool):
            return valor
        alvo = -abs(valor) if sinal == "negativo" else abs(valor)
        if alvo != valor:
            oc.append(Ocorrencia(
                "aviso", i, col,
                f"sinal ajustado para {sinal} (era {valor}, virou {alvo})",
            ))
        return alvo

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
