# Conversor de Planilhas → CIGAM

Recebe **qualquer planilha do cliente** (xlsx/csv), aplica um **De-Para**
(coluna do cliente → campo CIGAM), injeta os **defaults do gabarito** e gera:

- `.xlsx` no layout exato de importação CIGAM (mesma ordem e nomes de colunas);
- script **SQL de staging** (`INSERT` numa tabela `stg_*`);
- script **SQL de promoção** (`INSERT ... SELECT` da staging para a tabela CIGAM, sem duplicar por PK).

O gabarito vem do próprio arquivo-modelo: cada aba tem
`R1` = nome da coluna no banco, `R2` = regra/tamanho, `R3` = linha de valores-padrão.

## Instalação

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
```

## Uso pela linha de comando

```bash
# 1. listar as tabelas do modelo
python cli.py listar --modelo modelo/modelo_cigam.xlsx

# 2. ver as colunas de uma tabela (para montar o De-Para)
python cli.py colunas --modelo modelo/modelo_cigam.xlsx --aba "Material (ESMATERI)"

# 3. (opcional) gerar um De-Para automático como ponto de partida
python cli.py sugerir --modelo modelo/modelo_cigam.xlsx \
    --aba "Material (ESMATERI)" \
    --cliente exemplos/produtos_cliente.xlsx \
    --saida exemplos/mapa_auto.json

# 4. converter (revise o mapa antes!)
python cli.py converter \
    --modelo modelo/modelo_cigam.xlsx \
    --aba "Material (ESMATERI)" \
    --cliente exemplos/produtos_cliente.xlsx \
    --mapa exemplos/mapa_esmateri.json \
    --pk Cd_grupo,Cd_sub_grupo,Cd_material \
    --obrigatorios Cd_material,Descricao \
    --saida saida/ESMATERI
```

O mapa é um JSON simples `{ "campo_cigam": "coluna_cliente" }`. Só os
campos mapeados vêm do cliente; o resto recebe o default do gabarito.

## Uso como biblioteca (Python)

```python
from cigam_conversor import (
    CigamTemplate, Conversor,
    ler_planilha_cliente, gerar_xlsx, gerar_sql_staging, gerar_sql_promocao,
)

t = CigamTemplate.de_arquivo("modelo/modelo_cigam.xlsx", "Material (ESMATERI)")
_, registros = ler_planilha_cliente("exemplos/produtos_cliente.xlsx")

mapa = {
    "Cd_grupo": "GRUPO", "Cd_sub_grupo": "SUB", "Cd_material": "CODIGO",
    "Descricao": "PRODUTO", "Cd_unidade_medi": "UNID",
}
pk = ["Cd_grupo", "Cd_sub_grupo", "Cd_material"]

res = Conversor(t).converter(registros, mapa, pk=pk,
                             obrigatorios=["Cd_material", "Descricao"])

if res.ok:
    gerar_xlsx(res, "saida/ESMATERI.xlsx")
    gerar_sql_staging(res, "saida/ESMATERI_staging.sql")
    gerar_sql_promocao(res, "saida/ESMATERI_promocao.sql", pk=pk)
else:
    for o in res.erros:
        print(o)
```

## Validações incluídas

- **Tamanho de campo** — avisa (ou trunca, com `--truncar`) quando o valor
  excede o limite declarado na `R2`.
- **PK duplicada** — erro quando duas linhas repetem a chave informada em `--pk`.
- **Obrigatórios** — erro quando um campo de `--obrigatorios` fica vazio.

Enquanto houver **erro**, o comando avisa para não carregar no banco.
Avisos não bloqueiam.

## Interface web

Fluxo guiado (upload → escolher tabela → revisar De-Para → baixar) usando
a mesma biblioteca `cigam_conversor` do CLI, sem duplicar lógica.

```bash
pip install -r requirements.txt   # inclui o Flask
python -m web.app
```

Abra `http://127.0.0.1:5000`, envie a planilha do cliente (e, se quiser,
um modelo CIGAM diferente do padrão), escolha a tabela de destino, ajuste
o De-Para sugerido automaticamente, marque PK/obrigatórios e baixe o
`.xlsx` + os dois scripts SQL. É um servidor de desenvolvimento — para
uso multiusuário/produção, coloque atrás de um WSGI server (gunicorn/
waitress) apropriado.

## Limpeza de base

Em `/limpeza` na interface web: explica as validações acima, oferece uma
ferramenta para pré-limpar qualquer planilha (normaliza espaços, remove
linhas 100% duplicadas e colunas vazias, com download do `.xlsx` limpo)
e traz um checklist de preparação da base CIGAM antes da carga (backup,
staging antes da promoção, ordem de carga, etc.) — o checklist marca o
progresso salvo no navegador de quem está usando.

## Fluxo recomendado de carga no SQL Server

1. Rode o `*_staging.sql` para popular a `stg_<TABELA>`.
2. Confira os dados na staging (contagens, amostragem).
3. Rode o `*_promocao.sql` para inserir na tabela CIGAM real
   (ele pula registros cuja PK já existe).

## Ordem de carga (dependências)

Cadastros-base antes dos que dependem deles. Ex.:

- `ESGRUPO`, `ESSUBGRU`, `ESCLASFI` **antes de** `ESMATERI`
- `GEEMPRES` **antes de** `GFLANCAM` (contas a pagar/receber)

## Estrutura

```
cigam-conversor/
├── cli.py                     # linha de comando
├── requirements.txt
├── modelo/
│   └── modelo_cigam.xlsx      # arquivo-gabarito CIGAM
├── exemplos/                  # planilha e mapa de exemplo
├── saida/                     # artefatos gerados
├── cigam_conversor/
│   ├── template.py            # lê o gabarito de uma aba
│   ├── leitor_cliente.py      # lê xlsx/csv do cliente + sugestão de De-Para
│   ├── conversor.py           # aplica De-Para, injeta defaults, valida
│   ├── saida.py               # gera XLSX, SQL staging e SQL promoção
│   └── limpeza.py             # pré-limpeza de planilha (espaços, duplicados, colunas vazias)
└── web/                       # interface web (Flask) sobre o mesmo núcleo
    ├── app.py
    ├── templates/
    └── static/
```

## Próximos passos sugeridos

- Persistir templates de De-Para por cliente (reaproveita entre cargas).
- Validar FKs contra dados já existentes antes da promoção.
