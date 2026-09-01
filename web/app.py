"""
web/app.py
----------
Interface web do conversor CIGAM: envia a planilha do cliente, escolhe a
tabela de destino, revisa o De-Para sugerido e baixa o XLSX + SQL
gerados. Camada fina sobre a biblioteca `cigam_conversor` (a mesma do
cli.py) — sem duplicar logica de conversao.

Sem estado no servidor: nada e salvo em disco entre uma requisicao e
outra (ambientes serverless como a Vercel nao garantem que o mesmo
arquivo temporario sobreviva ate a proxima requisicao). Os dados da
planilha do cliente e do modelo (se customizado) viajam de volta e para
frente dentro dos proprios formularios HTML, como campos ocultos, e os
arquivos finais (xlsx/sql) sao gerados em memoria e entregues como link
de download (data: URI) na propria pagina de resultado.

Rodar (a partir da raiz do projeto):
    python -m web.app
Depois abrir http://127.0.0.1:5000
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
import uuid
from datetime import date, datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, flash, render_template, request
from werkzeug.utils import secure_filename

from cigam_conversor import (
    CigamTemplate, Conversor, gerar_sql_promocao, gerar_sql_staging,
    gerar_xlsx, ler_planilha_cliente, listar_abas, sugerir_mapeamento,
)

RAIZ = Path(__file__).resolve().parent.parent
MODELO_PADRAO = RAIZ / "modelo" / "modelo_cigam.xlsx"

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or uuid.uuid4().hex


def _tamanho_legivel(n: float) -> str:
    for unidade in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unidade}" if unidade == "B" else f"{n:.1f} {unidade}"
        n /= 1024
    return f"{n:.1f} TB"


# ---------------------------------------------------- serializacao ------ #
def _serializar_registros(registros: list[dict]) -> str:
    def default(o):
        if isinstance(o, (datetime, date)):
            return {"__date__": o.isoformat()}
        if hasattr(o, "item"):  # escalar numpy
            return o.item()
        return str(o)
    return json.dumps(registros, default=default)


def _desserializar_registros(texto: str) -> list[dict]:
    def object_hook(d):
        if set(d.keys()) == {"__date__"}:
            return datetime.fromisoformat(d["__date__"])
        return d
    return json.loads(texto, object_hook=object_hook)


def _resolver_modelo(modelo_custom_b64: str | None):
    """Devolve algo que CigamTemplate.de_arquivo/listar_abas aceitam."""
    if modelo_custom_b64:
        return io.BytesIO(base64.b64decode(modelo_custom_b64))
    return str(MODELO_PADRAO)


# --------------------------------------------------------- 1. upload ---- #
@app.get("/")
def index():
    return render_template("upload.html", passo_atual=1)


@app.post("/enviar")
def enviar():
    cliente = request.files.get("cliente")
    if not cliente or not cliente.filename:
        flash("Selecione a planilha do cliente.", "erro")
        return render_template("upload.html", passo_atual=1)

    modelo = request.files.get("modelo")
    modelo_bytes = modelo.read() if (modelo and modelo.filename) else None

    try:
        colunas_cliente, registros = ler_planilha_cliente(cliente)
        fonte_modelo = io.BytesIO(modelo_bytes) if modelo_bytes else str(MODELO_PADRAO)
        abas = listar_abas(fonte_modelo)
    except Exception as exc:
        flash(f"Não foi possível ler a planilha ou o modelo: {exc}", "erro")
        return render_template("upload.html", passo_atual=1)

    return render_template(
        "escolher_aba.html",
        abas=abas,
        registros_json=_serializar_registros(registros),
        colunas_cliente_json=json.dumps(colunas_cliente),
        modelo_custom_b64=base64.b64encode(modelo_bytes).decode("ascii") if modelo_bytes else "",
        passo_atual=2,
    )


# ---------------------------------------------------- 2. escolher aba --- #
@app.post("/aba")
def definir_aba():
    registros_json = request.form.get("registros_json", "")
    colunas_cliente_json = request.form.get("colunas_cliente_json", "")
    modelo_custom_b64 = request.form.get("modelo_custom_b64", "")
    aba = request.form.get("aba")

    if not aba:
        flash("Escolha uma tabela.", "erro")
        abas = listar_abas(_resolver_modelo(modelo_custom_b64))
        return render_template(
            "escolher_aba.html",
            abas=abas,
            registros_json=registros_json,
            colunas_cliente_json=colunas_cliente_json,
            modelo_custom_b64=modelo_custom_b64,
            passo_atual=2,
        )

    try:
        t = CigamTemplate.de_arquivo(_resolver_modelo(modelo_custom_b64), aba)
        colunas_cliente = json.loads(colunas_cliente_json)
    except Exception as exc:
        flash(f"Não foi possível abrir o modelo: {exc}", "erro")
        return render_template("upload.html", passo_atual=1)

    sugestao = sugerir_mapeamento(colunas_cliente, t.colunas)

    return render_template(
        "mapear.html",
        tabela=t.tabela,
        aba=aba,
        colunas_info=t.resumo_colunas(),
        colunas_cliente=colunas_cliente,
        sugestao=sugestao,
        nome_saida_padrao=t.tabela,
        registros_json=registros_json,
        modelo_custom_b64=modelo_custom_b64,
        passo_atual=3,
    )


# --------------------------------------------------------- 3. mapear ---- #
@app.post("/converter")
def converter():
    aba = request.form.get("aba")
    registros_json = request.form.get("registros_json", "")
    modelo_custom_b64 = request.form.get("modelo_custom_b64", "")

    try:
        t = CigamTemplate.de_arquivo(_resolver_modelo(modelo_custom_b64), aba)
        registros = _desserializar_registros(registros_json)
    except Exception as exc:
        flash(f"Não foi possível processar a planilha: {exc}", "erro")
        return render_template("upload.html", passo_atual=1)

    mapa = {}
    for col in t.colunas:
        origem = request.form.get(f"map__{col}")
        if origem:
            mapa[col] = origem

    pk = request.form.getlist("pk") or None
    obrigatorios = request.form.getlist("obrig") or None
    truncar = bool(request.form.get("truncar"))

    res = Conversor(t).converter(
        registros, mapa, truncar=truncar, pk=pk, obrigatorios=obrigatorios,
    )

    nome = secure_filename(request.form.get("saida_nome") or t.tabela) or t.tabela

    buf_xlsx = io.BytesIO()
    gerar_xlsx(res, buf_xlsx)

    buf_staging = io.StringIO()
    gerar_sql_staging(res, buf_staging)

    buf_promocao = io.StringIO()
    gerar_sql_promocao(res, buf_promocao, pk=pk)

    arquivos = [
        {
            "nome": f"{nome}.xlsx",
            "tipo": "xlsx",
            "tamanho": _tamanho_legivel(buf_xlsx.getbuffer().nbytes),
            "href": (
                "data:application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet;base64,"
                + base64.b64encode(buf_xlsx.getvalue()).decode("ascii")
            ),
        },
        {
            "nome": f"{nome}_staging.sql",
            "tipo": "sql",
            "tamanho": _tamanho_legivel(len(buf_staging.getvalue().encode("utf-8"))),
            "href": (
                "data:text/plain;charset=utf-8;base64,"
                + base64.b64encode(buf_staging.getvalue().encode("utf-8")).decode("ascii")
            ),
        },
        {
            "nome": f"{nome}_promocao.sql",
            "tipo": "sql",
            "tamanho": _tamanho_legivel(len(buf_promocao.getvalue().encode("utf-8"))),
            "href": (
                "data:text/plain;charset=utf-8;base64,"
                + base64.b64encode(buf_promocao.getvalue().encode("utf-8")).decode("ascii")
            ),
        },
    ]

    return render_template(
        "resultado.html", res=res, arquivos=arquivos, passo_atual=3, concluido=True,
    )


# ------------------------------------------------------- limpeza de base -- #
@app.get("/limpeza")
def limpeza():
    return render_template("limpeza.html")


if __name__ == "__main__":
    app.run(debug=True)
