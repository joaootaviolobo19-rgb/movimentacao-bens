# -*- coding: utf-8 -*-
"""Extensões compartilhadas — evita import circular."""
from flask_limiter import Limiter
from flask_wtf.csrf import CSRFProtect
from flask import request


def _chave_por_usuario_ou_ip():
    """
    Para POST /login: usa 'login:<usuario>' como chave (não bloqueia outras contas).
    Para os demais endpoints: usa o IP de origem.
    """
    if request.path == "/login" and request.method == "POST":
        usuario = (request.form.get("usuario") or "").strip().lower()
        if usuario:
            return f"login:{usuario}"
    # IP real, considerando proxy
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "anon"


limiter = Limiter(
    key_func=_chave_por_usuario_ou_ip,
    storage_uri="memory://",
    default_limits=[],
)

csrf = CSRFProtect()
