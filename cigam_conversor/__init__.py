"""Conversor de planilhas do cliente para o padrao de importacao CIGAM."""
from .template import CigamTemplate, listar_abas, extrair_tabela
from .conversor import Conversor, ResultadoConversao, Ocorrencia
from .saida import gerar_xlsx, gerar_sql_staging, gerar_sql_promocao
from .leitor_cliente import ler_planilha_cliente, sugerir_mapeamento
from .limpeza import limpar_registros, ResultadoLimpeza, gerar_xlsx_limpo

__all__ = [
    "CigamTemplate", "listar_abas", "extrair_tabela",
    "Conversor", "ResultadoConversao", "Ocorrencia",
    "gerar_xlsx", "gerar_sql_staging", "gerar_sql_promocao",
    "ler_planilha_cliente", "sugerir_mapeamento",
    "limpar_registros", "ResultadoLimpeza", "gerar_xlsx_limpo",
]
