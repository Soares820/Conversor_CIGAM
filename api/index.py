"""
api/index.py
------------
Ponto de entrada da funcao serverless da Vercel. So reexpoe o app Flask
de web/app.py (o mesmo usado localmente com `python -m web.app`) — nao
duplica nenhuma rota nem logica.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web.app import app  # noqa: E402
