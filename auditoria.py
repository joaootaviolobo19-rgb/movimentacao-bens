# -*- coding: utf-8 -*-
"""Registro de auditoria para ações administrativas."""
import csv
import os
import threading
from datetime import datetime
from flask import session, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DADOS = os.path.join(BASE_DIR, "dados")
ARQ_AUDIT = os.path.join(DADOS, "auditoria.csv")
_lock = threading.Lock()

CABECALHO = ["data", "usuario", "nome", "ip", "acao", "alvo", "detalhe"]


def registrar(acao, alvo="", detalhe=""):
    """
    Registra ação administrativa.
    Ex.: registrar("criar_usuario", alvo="joao", detalhe="perfil=recepcao")
    """
    ip = ""
    try:
        forwarded = request.headers.get("X-Forwarded-For", "")
        ip = forwarded.split(",")[0].strip() if forwarded else (
            request.remote_addr or "")
    except Exception:
        pass

    linha = {
        "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "usuario": session.get("usuario", "?"),
        "nome": session.get("nome", ""),
        "ip": ip,
        "acao": acao,
        "alvo": alvo,
        "detalhe": detalhe,
    }

    os.makedirs(DADOS, exist_ok=True)
    with _lock:
        existe = os.path.exists(ARQ_AUDIT)
        with open(ARQ_AUDIT, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CABECALHO)
            if not existe:
                w.writeheader()
            w.writerow(linha)
