# -*- coding: utf-8 -*-
import os
import json
import hashlib
import hmac
import re
import tempfile
import permissoes
from werkzeug.security import check_password_hash, generate_password_hash

try:
    from filelock import FileLock, Timeout as FileLockTimeout
    _HAS_FILELOCK = True
except ImportError:
    _HAS_FILELOCK = False

    class FileLock:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class FileLockTimeout(Exception):
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DADOS = os.path.join(BASE_DIR, "dados")
os.makedirs(DADOS, exist_ok=True)

ARQ_USUARIOS = os.path.join(DADOS, "usuarios.json")
LOCK_USUARIOS = FileLock(os.path.join(DADOS, ".usuarios.lock"), timeout=10)

# Hash dummy para gastar tempo igual quando usuário não existe (timing attack)
_HASH_DUMMY = generate_password_hash("senha_dummy_para_timing_equalizar")


def _hash(senha):
    return generate_password_hash(senha)


def _criar_usuario_inicial():
    usuario = os.environ.get("BOOTSTRAP_ADMIN_USER", "").strip()
    senha = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")
    if not usuario or not senha:
        raise RuntimeError(
            "Arquivo de usuários ausente. Configure BOOTSTRAP_ADMIN_USER e "
            "BOOTSTRAP_ADMIN_PASSWORD para criar o primeiro administrador."
        )
    usuarios = [{
        "usuario": usuario,
        "senha_hash": _hash(senha),
        "nome": os.environ.get("BOOTSTRAP_ADMIN_NAME", "Administrador TI"),
        "tipo": "admin",
    }]
    _salvar(usuarios)
    return usuarios


def carregar_usuarios():
    if not os.path.exists(ARQ_USUARIOS):
        return _criar_usuario_inicial()
    with open(ARQ_USUARIOS, "r", encoding="utf-8") as f:
        usuarios = json.load(f)
    if not isinstance(usuarios, list):
        raise ValueError(
            "O arquivo de usuários precisa conter uma lista JSON.")
    return usuarios


def _salvar(usuarios):
    fd, temporario = tempfile.mkstemp(
        prefix=".usuarios-", suffix=".tmp", dir=DADOS
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as arquivo:
            json.dump(usuarios, arquivo, ensure_ascii=False, indent=2)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, ARQ_USUARIOS)
    except Exception:
        if os.path.exists(temporario):
            os.unlink(temporario)
        raise


def autenticar(usuario, senha):
    usuarios = carregar_usuarios()
    alvo = None
    for u in usuarios:
        if u.get("usuario") == usuario:
            alvo = u
            break

    # Timing attack: gasta tempo igual mesmo se usuário não existe
    if alvo is None:
        try:
            check_password_hash(_HASH_DUMMY, senha)
        except ValueError:
            pass
        return None

    senha_hash = alvo.get("senha_hash", "")

    # Hash legado SHA-256 sem salt → força migração imediata
    if re.fullmatch(r"[0-9a-fA-F]{64}", senha_hash):
        legado = hashlib.sha256(senha.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(senha_hash.lower(), legado):
            return None
        with LOCK_USUARIOS:
            lista = carregar_usuarios()
            for u in lista:
                if u.get("usuario") == usuario:
                    u["senha_hash"] = _hash(senha)
                    break
            _salvar(lista)
        return alvo

    try:
        if check_password_hash(senha_hash, senha):
            return alvo
    except ValueError:
        return None
    return None


def trocar_senha(usuario, senha_nova):
    with LOCK_USUARIOS:
        usuarios = carregar_usuarios()
        for u in usuarios:
            if u.get("usuario") == usuario:
                u["senha_hash"] = _hash(senha_nova)
                break
        _salvar(usuarios)


def listar():
    nomes_perfis = {
        perfil["id"]: perfil["nome"]
        for perfil in permissoes.listar_perfis()
    }
    return [
        {
            "usuario": u.get("usuario", ""),
            "nome": u.get("nome", ""),
            "tipo": u.get("tipo", ""),
            "perfil_nome": nomes_perfis.get(u.get("tipo"), "Perfil sem acesso"),
        }
        for u in carregar_usuarios()
    ]


def resetar_senha(usuario, senha_nova):
    with LOCK_USUARIOS:
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


def criar_usuario(usuario, nome, tipo, senha):
    if not isinstance(usuario, str) or not isinstance(nome, str) or not isinstance(
        tipo, str
    ) or not isinstance(senha, str):
        return False, "Dados de usuário inválidos."
    usuario = usuario.strip().lower()
    nome = nome.strip()
    if not re.fullmatch(r"[a-z0-9._-]{3,40}", usuario):
        return False, "Use de 3 a 40 caracteres: letras, números, ponto, hífen ou sublinhado."
    if not nome:
        return False, "Informe o nome da pessoa."
    if not permissoes.obter_perfil(tipo):
        return False, "Perfil inválido."
    if len(senha) < 6:
        return False, "A senha deve ter ao menos 6 caracteres."

    with LOCK_USUARIOS:
        usuarios = carregar_usuarios()
        if any(u.get("usuario", "").casefold() == usuario.casefold() for u in usuarios):
            return False, "Esse nome de usuário já está cadastrado."
        usuarios.append({
            "usuario": usuario,
            "senha_hash": _hash(senha),
            "nome": nome,
            "tipo": tipo,
        })
        _salvar(usuarios)
    return True, "Usuário criado."


def alterar_perfil_usuario(usuario, perfil_id):
    if not isinstance(usuario, str) or not isinstance(perfil_id, str):
        return False, "Dados inválidos."
    if not permissoes.obter_perfil(perfil_id):
        return False, "Perfil não encontrado."
    with LOCK_USUARIOS:
        usuarios = carregar_usuarios()
        alvo = next(
            (u for u in usuarios if u.get("usuario",
             "").casefold() == usuario.casefold()),
            None,
        )
        if not alvo:
            return False, "Usuário não encontrado."
        if alvo.get("tipo") == "admin" and perfil_id != "admin" and sum(
            u.get("tipo") == "admin" for u in usuarios
        ) <= 1:
            return False, "Não é possível remover o perfil TI do último administrador."
        alvo["tipo"] = perfil_id
        _salvar(usuarios)
    return True, "Perfil do usuário atualizado."


def excluir_usuario(usuario):
    with LOCK_USUARIOS:
        usuarios = carregar_usuarios()
        alvo = next(
            (u for u in usuarios if u.get("usuario",
             "").casefold() == usuario.casefold()),
            None,
        )
        if not alvo:
            return False, "Usuário não encontrado."
        if alvo.get("tipo") == "admin" and sum(
            u.get("tipo") == "admin" for u in usuarios
        ) <= 1:
            return False, "Não é possível excluir o último administrador."

        _salvar([u for u in usuarios if u is not alvo])
    return True, "Usuário excluído."
