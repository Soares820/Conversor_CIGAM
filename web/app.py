"""
web/app.py
----------
Interface web minimalista para o conversor CIGAM: envia a planilha do
cliente, escolhe a tabela de destino, revisa o De-Para sugerido e baixa
o XLSX + SQL gerados. E so uma camada fina sobre a biblioteca
`cigam_conversor` — a mesma usada pelo cli.py — sem duplicar logica.

Rodar (a partir da raiz do projeto):
    python -m web.app
Depois abrir http://127.0.0.1:5000
"""
from __future__ import annotations

import os
import sys
import uuid
import shutil
import tempfile
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import (
    Flask, flash, redirect, render_template, request,
    send_from_directory, session, url_for,
)
from werkzeug.utils import secure_filename

from cigam_conversor import (
    CigamTemplate, Conversor, gerar_sql_promocao, gerar_sql_staging,
    gerar_xlsx, ler_planilha_cliente, listar_abas, sugerir_mapeamento,
)

RAIZ = Path(__file__).resolve().parent.parent
MODELO_PADRAO = RAIZ / "modelo" / "modelo_cigam.xlsx"
TMP_BASE = Path(tempfile.gettempdir()) / "cigam_web"


def _tamanho_legivel(n: float) -> str:
    for unidade in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unidade}" if unidade == "B" else f"{n:.1f} {unidade}"
        n /= 1024
    return f"{n:.1f} TB"

app = Flask(__name__)
# Em serverless (Vercel), cada cold start e um processo novo: uma chave
# aleatoria invalidaria os cookies de sessao de quem estiver no meio do
# fluxo. SECRET_KEY fixa via env var resolve isso; localmente cai para
# uma chave aleatoria por execucao (nao precisa persistir entre reinicios).
app.secret_key = os.environ.get("SECRET_KEY") or uuid.uuid4().hex


def _dir_sessao() -> Path:
    sid = session.get("sid")
    if not sid:
        sid = uuid.uuid4().hex
        session["sid"] = sid
    d = TMP_BASE / sid
    d.mkdir(parents=True, exist_ok=True)
    return d


def _limpar_sessao() -> None:
    sid = session.get("sid")
    if sid:
        shutil.rmtree(TMP_BASE / sid, ignore_errors=True)
    # so remove as chaves da aplicacao — preserva a fila de flash messages,
    # senao um erro sinalizado logo antes do redirect para "/" nunca aparece.
    for chave in ("sid", "cliente_path", "modelo_path", "aba"):
        session.pop(chave, None)


# --------------------------------------------------------- 1. upload ---- #
@app.get("/")
def index():
    _limpar_sessao()
    return render_template("upload.html", passo_atual=1)


@app.post("/enviar")
def enviar():
    cliente = request.files.get("cliente")
    if not cliente or not cliente.filename:
        flash("Selecione a planilha do cliente.", "erro")
        return redirect(url_for("index"))

    d = _dir_sessao()
    nome_cliente = secure_filename(cliente.filename) or "cliente.xlsx"
    caminho_cliente = d / nome_cliente
    cliente.save(caminho_cliente)
    session["cliente_path"] = str(caminho_cliente)

    modelo = request.files.get("modelo")
    if modelo and modelo.filename:
        nome_modelo = secure_filename(modelo.filename) or "modelo.xlsx"
        caminho_modelo = d / nome_modelo
        modelo.save(caminho_modelo)
        session["modelo_path"] = str(caminho_modelo)
    else:
        session["modelo_path"] = str(MODELO_PADRAO)

    return redirect(url_for("escolher_aba"))


# ---------------------------------------------------- 2. escolher aba --- #
@app.get("/aba")
def escolher_aba():
    modelo_path = session.get("modelo_path")
    if not modelo_path:
        return redirect(url_for("index"))
    try:
        abas = listar_abas(modelo_path)
    except Exception as exc:
        flash(f"Nao foi possivel ler o modelo: {exc}", "erro")
        return redirect(url_for("index"))
    return render_template("escolher_aba.html", abas=abas, passo_atual=2)


@app.post("/aba")
def definir_aba():
    aba = request.form.get("aba")
    if not aba:
        flash("Escolha uma tabela.", "erro")
        return redirect(url_for("escolher_aba"))
    session["aba"] = aba
    return redirect(url_for("mapear"))


# --------------------------------------------------------- 3. mapear ---- #
@app.get("/mapear")
def mapear():
    modelo_path = session.get("modelo_path")
    cliente_path = session.get("cliente_path")
    aba = session.get("aba")
    if not (modelo_path and cliente_path and aba):
        return redirect(url_for("index"))

    try:
        t = CigamTemplate.de_arquivo(modelo_path, aba)
        colunas_cliente, _ = ler_planilha_cliente(cliente_path)
    except Exception as exc:
        flash(f"Erro ao ler os arquivos: {exc}", "erro")
        return redirect(url_for("index"))

    sugestao = sugerir_mapeamento(colunas_cliente, t.colunas)

    return render_template(
        "mapear.html",
        tabela=t.tabela,
        colunas_info=t.resumo_colunas(),
        colunas_cliente=colunas_cliente,
        sugestao=sugestao,
        nome_saida_padrao=t.tabela,
        passo_atual=3,
    )


@app.post("/converter")
def converter():
    modelo_path = session.get("modelo_path")
    cliente_path = session.get("cliente_path")
    aba = session.get("aba")
    if not (modelo_path and cliente_path and aba):
        return redirect(url_for("index"))

    t = CigamTemplate.de_arquivo(modelo_path, aba)
    _, registros = ler_planilha_cliente(cliente_path)

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

    saida_dir = _dir_sessao() / "saida"
    saida_dir.mkdir(exist_ok=True)
    nome = secure_filename(request.form.get("saida_nome") or t.tabela) or t.tabela
    base = saida_dir / nome

    gerar_xlsx(res, str(base) + ".xlsx")
    gerar_sql_staging(res, str(base) + "_staging.sql")
    gerar_sql_promocao(res, str(base) + "_promocao.sql", pk=pk)

    arquivos = []
    for nome_arq, tipo in (
        (f"{nome}.xlsx", "xlsx"),
        (f"{nome}_staging.sql", "sql"),
        (f"{nome}_promocao.sql", "sql"),
    ):
        arquivos.append({
            "nome": nome_arq,
            "tipo": tipo,
            "tamanho": _tamanho_legivel((saida_dir / nome_arq).stat().st_size),
        })

    return render_template(
        "resultado.html", res=res, arquivos=arquivos, passo_atual=3, concluido=True,
    )


# -------------------------------------------------------- 4. download --- #
@app.get("/download/<path:nome_arquivo>")
def download(nome_arquivo):
    sid = session.get("sid")
    if not sid:
        return redirect(url_for("index"))
    saida_dir = TMP_BASE / sid / "saida"
    return send_from_directory(saida_dir, nome_arquivo, as_attachment=True)


# ------------------------------------------------------- limpeza de base -- #
@app.get("/limpeza")
def limpeza():
    return render_template("limpeza.html")


if __name__ == "__main__":
    app.run(debug=True)
