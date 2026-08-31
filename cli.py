"""
cli.py
------
Linha de comando do conversor CIGAM.

Exemplos:
  # listar as abas/tabelas do modelo
  python cli.py listar --modelo modelo/modelo_cigam.xlsx

  # ver as colunas de uma aba (para montar o De-Para)
  python cli.py colunas --modelo modelo/modelo_cigam.xlsx \
      --aba "Material (ESMATERI)"

  # converter usando um mapeamento em JSON
  python cli.py converter \
      --modelo modelo/modelo_cigam.xlsx \
      --aba "Material (ESMATERI)" \
      --cliente exemplos/produtos_cliente.xlsx \
      --mapa exemplos/mapa_esmateri.json \
      --pk Cd_grupo,Cd_sub_grupo,Cd_material \
      --saida saida/ESMATERI
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from cigam_conversor import (
    CigamTemplate,
    Conversor,
    gerar_sql_promocao,
    gerar_sql_staging,
    gerar_xlsx,
    ler_planilha_cliente,
    listar_abas,
    sugerir_mapeamento,
)


def cmd_listar(args):
    for item in listar_abas(args.modelo):
        print(f"{item['tabela']:12s}  <-  {item['aba']}")


def cmd_colunas(args):
    t = CigamTemplate.de_arquivo(args.modelo, args.aba)
    print(f"Tabela {t.tabela} — {t.ncolunas} colunas\n")
    for info in t.resumo_colunas():
        regra = info["regra"] or ""
        print(f"  {info['coluna']:24s} {str(regra):20s} "
              f"default={info['default']!r}")


def cmd_sugerir(args):
    t = CigamTemplate.de_arquivo(args.modelo, args.aba)
    cols_cli, _ = ler_planilha_cliente(args.cliente)
    mapa = sugerir_mapeamento(cols_cli, t.colunas)
    Path(args.saida).write_text(
        json.dumps(mapa, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Sugestao salva em {args.saida} ({len(mapa)} colunas mapeadas)")
    for cig, cli in mapa.items():
        print(f"  {cig:24s} <- {cli}")


def cmd_converter(args):
    t = CigamTemplate.de_arquivo(args.modelo, args.aba)
    _, registros = ler_planilha_cliente(args.cliente)
    mapa = json.loads(Path(args.mapa).read_text(encoding="utf-8"))

    pk = args.pk.split(",") if args.pk else None
    obrig = args.obrigatorios.split(",") if args.obrigatorios else None

    conv = Conversor(t)
    res = conv.converter(
        registros, mapa,
        truncar=args.truncar, pk=pk, obrigatorios=obrig,
    )

    base = Path(args.saida)
    base.parent.mkdir(parents=True, exist_ok=True)

    gerar_xlsx(res, str(base) + ".xlsx")
    gerar_sql_staging(res, str(base) + "_staging.sql")
    gerar_sql_promocao(res, str(base) + "_promocao.sql", pk=pk)

    print(f"Tabela {res.tabela}: {len(res.linhas)} linha(s) geradas.")
    print(f"  {len(res.erros)} erro(s), {len(res.avisos)} aviso(s).")
    for o in res.ocorrencias[:50]:
        print("   ", o)
    if res.ok:
        print("OK — arquivos gerados:")
        print("   ", base.with_suffix(".xlsx"))
        print("   ", str(base) + "_staging.sql")
        print("   ", str(base) + "_promocao.sql")
    else:
        print("ATENCAO: ha erros. Corrija antes de carregar no banco.")


def main():
    p = argparse.ArgumentParser(description="Conversor de planilhas -> CIGAM")
    sub = p.add_subparsers(required=True)

    pl = sub.add_parser("listar", help="lista abas/tabelas do modelo")
    pl.add_argument("--modelo", required=True)
    pl.set_defaults(func=cmd_listar)

    pc = sub.add_parser("colunas", help="mostra colunas de uma aba")
    pc.add_argument("--modelo", required=True)
    pc.add_argument("--aba", required=True)
    pc.set_defaults(func=cmd_colunas)

    ps = sub.add_parser("sugerir", help="gera De-Para automatico (JSON)")
    ps.add_argument("--modelo", required=True)
    ps.add_argument("--aba", required=True)
    ps.add_argument("--cliente", required=True)
    ps.add_argument("--saida", required=True)
    ps.set_defaults(func=cmd_sugerir)

    pv = sub.add_parser("converter", help="converte e gera XLSX + SQL")
    pv.add_argument("--modelo", required=True)
    pv.add_argument("--aba", required=True)
    pv.add_argument("--cliente", required=True)
    pv.add_argument("--mapa", required=True)
    pv.add_argument("--saida", required=True)
    pv.add_argument("--pk", default="")
    pv.add_argument("--obrigatorios", default="")
    pv.add_argument("--truncar", action="store_true")
    pv.set_defaults(func=cmd_converter)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
