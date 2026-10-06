# -*- coding: utf-8 -*-
import os
import json
import hashlib

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DADOS = os.path.join(BASE_DIR, "dados")
os.makedirs(DADOS, exist_ok=True)

ARQ_USUARIOS = os.path.join(DADOS, "usuarios.json")


def _hash(senha):
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()


USUARIOS_PADRAO = [
    {
        "usuario": "admin",
        "senha_hash": _hash("adminrecord2026"),
        "nome": "Administrador TI",
        "tipo": "admin",
    },
    {
        "usuario": "recepcao",
        "senha_hash": _hash("recepcao123"),
        "nome": "Recepção",
        "tipo": "recepcao",
    },
]


def carregar_usuarios():
    if not os.path.exists(ARQ_USUARIOS):
        with open(ARQ_USUARIOS, "w", encoding="utf-8") as f:
            json.dump(USUARIOS_PADRAO, f, ensure_ascii=False, indent=2)
        return USUARIOS_PADRAO
    try:
        with open(ARQ_USUARIOS, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return USUARIOS_PADRAO


def _salvar(usuarios):
    with open(ARQ_USUARIOS, "w", encoding="utf-8") as f:
        json.dump(usuarios, f, ensure_ascii=False, indent=2)


def autenticar(usuario, senha):
    usuarios = carregar_usuarios()
    h = _hash(senha)
    for u in usuarios:
        if u.get("usuario") == usuario and u.get("senha_hash") == h:
            return u
    return None


def trocar_senha(usuario, senha_nova):
    usuarios = carregar_usuarios()
    for u in usuarios:
        if u.get("usuario") == usuario:
            u["senha_hash"] = _hash(senha_nova)
            break
    _salvar(usuarios)


# ===== NOVAS FUNÇÕES =====

def listar():
    """Retorna todos os usuários sem expor hash de senha."""
    return [
        {
            "usuario": u.get("usuario", ""),
            "nome": u.get("nome", ""),
            "tipo": u.get("tipo", ""),
        }
        for u in carregar_usuarios()
    ]


def resetar_senha(usuario, senha_nova):
    """Admin redefine a senha de qualquer usuário."""
    usuarios = carregar_usuarios()
    achou = False
    for u in usuarios:
        if u.get("usuario") == usuario:
            u["senha_hash"] = _hash(senha_nova)
            achou = True
            break
    if achou:
        _salvar(usuarios)
    return achou
