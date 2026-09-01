"""Conversor de planilhas do cliente para o padrao de importacao CIGAM."""
from .template import CigamTemplate, listar_abas, extrair_tabela
from .conversor import Conversor, ResultadoConversao, Ocorrencia, detectar_forcar_sinal
from .saida import gerar_xlsx, gerar_sql_staging, gerar_sql_promocao
from .leitor_cliente import (
    ler_planilha_cliente, sugerir_mapeamento, construir_lookup_empresas,
)

__all__ = [
    "CigamTemplate", "listar_abas", "extrair_tabela",
    "Conversor", "ResultadoConversao", "Ocorrencia", "detectar_forcar_sinal",
    "gerar_xlsx", "gerar_sql_staging", "gerar_sql_promocao",
    "ler_planilha_cliente", "sugerir_mapeamento", "construir_lookup_empresas",
]
