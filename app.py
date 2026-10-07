# -*- coding: utf-8 -*-
import email_sender
import permissoes
import usuarios as mod_usuarios
import unicodedata
import os
import json
import csv
import hashlib
import re
import glob
import shutil
import secrets
import time
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime
from collections import defaultdict, Counter
from difflib import SequenceMatcher
from functools import wraps
from flask import (Flask, render_template, request, jsonify, send_file,
                   session, redirect, url_for)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DADOS = os.path.join(BASE_DIR, "dados")
os.makedirs(DADOS, exist_ok=True)

app = Flask(__name__)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_COOKIE_SECURE", "").lower()
    in {"1", "true", "yes"},
)


def _carregar_chave_sessao():
    chave = os.environ.get("FLASK_SECRET_KEY")
    if chave:
        return chave

    caminho = os.path.join(DADOS, "flask_secret_key")
    try:
        with open(caminho, encoding="utf-8") as arquivo:
            chave = arquivo.read().strip()
    except FileNotFoundError:
        chave = secrets.token_urlsafe(48)
        try:
            with open(caminho, "x", encoding="utf-8") as arquivo:
                arquivo.write(chave)
        except FileExistsError:
            with open(caminho, encoding="utf-8") as arquivo:
                chave = arquivo.read().strip()
    if not chave:
        raise RuntimeError("A chave de sessão está vazia.")
    return chave


app.secret_key = _carregar_chave_sessao()


RECURSO_POR_ENDPOINT = {
    "dashboard": "dashboard",
    "bens_view": "bens", "bens_salvar": "bens", "bens_transferir": "movimentacoes",
    "bens_excluir": "bens", "bens_exportar": "bens",
    "planilha_view": "planilha", "api_bens_celula": "planilha",
    "api_bens_planilha_lote": "planilha",
    "funcionarios_view": "funcionarios", "funcionarios_salvar": "funcionarios",
    "funcionarios_excluir": "funcionarios", "funcionario_detalhe": "funcionarios",
    "bem_detalhe": "bens", "alerta_funcionario_resolver": "alertas",
    "api_funcionarios_orfaos": "funcionarios",
    "organograma_view": "organograma",
    "movimentar_view": "movimentacoes", "movimentar_registrar": "movimentacoes",
    "movimentacoes_view": "movimentacoes", "movimentacoes_exportar": "movimentacoes",
    "ferias_view": "ferias", "ferias_salvar": "ferias", "ferias_excluir": "ferias",
    "api_alertas_ferias": "alertas",
    "ramais_view": "ramais", "api_ramais_agrupados": "ramais",
    "projetos_view": "projetos", "projetos_salvar": "projetos",
    "projetos_excluir": "projetos",
    "ponto_view": "ponto", "api_csv_info": "planilha",
    "configuracoes_view": "configuracoes",
    "api_config_email_salvar": "configuracoes",
    "api_config_email_testar": "configuracoes",
    "recepcao_view": "recepcao",
    "usuarios_view": "usuarios",
    "api_admin_trocar_senha": "usuarios",
    "api_admin_usuario_criar": "usuarios",
    "api_admin_usuario_excluir": "usuarios",
    "api_admin_perfil_salvar": "usuarios",
    "api_admin_perfil_excluir": "usuarios",
    "api_admin_usuario_perfil": "usuarios",
    "api_admin_status_salvar": "configuracoes",
}


def tem_permissao(permissao):
    return permissoes.tem_permissao(session.get("tipo", ""), permissao)


def _negar_acesso():
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "msg": "Acesso negado para este perfil."}), 403
    return "Acesso negado para este perfil.", 403


def perfil_home():
    destinos = (
        ("dashboard.ver", "dashboard"),
        ("recepcao.ver", "recepcao_view"),
        ("bens.ver", "bens_view"),
        ("planilha.ver", "planilha_view"),
        ("funcionarios.ver", "funcionarios_view"),
        ("ferias.ver", "ferias_view"),
        ("ramais.ver", "ramais_view"),
        ("movimentacoes.ver", "movimentacoes_view"),
        ("projetos.ver", "projetos_view"),
        ("organograma.ver", "organograma_view"),
        ("ponto.ver", "ponto_view"),
        ("configuracoes.ver", "configuracoes_view"),
        ("usuarios.ver", "usuarios_view"),
    )
    for permissao, endpoint in destinos:
        if permissoes.tem_permissao(session.get("tipo", ""), permissao):
            return redirect(url_for(endpoint))
    return _negar_acesso()


@app.before_request
def verificar_acesso():
    if request.endpoint in {
        "static",
        "login",
        "logout",
        "api_rodar_alertas_cron",
    }:
        return None
    if "usuario" not in session:
        return redirect(url_for("login"))
    usuario_atual = next(
        (
            usuario for usuario in mod_usuarios.carregar_usuarios()
            if usuario.get("usuario", "").casefold()
            == str(session.get("usuario", "")).casefold()
        ),
        None,
    )
    if not usuario_atual:
        session.clear()
        return redirect(url_for("login"))
    if (
        session.get("tipo") != usuario_atual.get("tipo")
        or session.get("nome") != usuario_atual.get("nome")
    ):
        session["tipo"] = usuario_atual.get("tipo", "")
        session["nome"] = usuario_atual.get("nome", "")
    perfil_id = session.get("tipo", "")
    if (
        request.endpoint != "recepcao_view"
        and permissoes.tem_permissao(perfil_id, "*")
    ):
        return None
    recurso = RECURSO_POR_ENDPOINT.get(request.endpoint or "")
    if recurso:
        if request.endpoint in {"bens_exportar", "movimentacoes_exportar"}:
            acao = "exportar"
        elif request.method in {"GET", "HEAD"}:
            acao = "ver"
        else:
            acao = "editar"
        if permissoes.tem_permissao(perfil_id, f"{recurso}.{acao}"):
            return None
    return _negar_acesso()


ARQ_BENS = os.path.join(DADOS, "bens.json")
ARQ_FUNC = os.path.join(DADOS, "funcionarios.json")
ARQ_DEP = os.path.join(DADOS, "departamentos.json")
ARQ_MOV = os.path.join(DADOS, "movimentacoes.csv")
ARQ_FER = os.path.join(DADOS, "ferias.json")
ARQ_PROJ = os.path.join(DADOS, "projetos.json")
ARQ_ALERTAS_FUNC = os.path.join(DADOS, "alertas_funcionarios.json")
ARQ_STATUS_BENS = os.path.join(DADOS, "status_bens.json")

DELIMITER = ";"
BACKUP_DIR = os.path.join(BASE_DIR, "_backup_csv")
CSV_LOCK_PATH = os.path.join(DADOS, ".csv-write.lock")
os.makedirs(BACKUP_DIR, exist_ok=True)

COLS = [
    ("Categoria", "categoria"), ("Modelo", "modelo"), ("Hostname", "hostname"),
    ("Patrimônio", "patrimonio"), ("Departamento",
                                   "departamento"), ("Responsável", "responsavel"),
    ("Marca", "marca"), ("Serial", "serial"), ("Ramal", "ramal"), ("IP", "ip"),
    ("Observação", "observacao"), ("CPU",
                                   "cpu"), ("Disco", "disco"), ("RAM", "ram"),
    ("ISO", "iso"), ("Status", "status"), ("Chave de auditoria", "_auditoria"),
    ("VERIFICAÇÃO", "_verificacao"), ("Departamento", "_depto_extra"),
]

CAMPOS_BEM_EDITAVEIS = {
    "categoria", "modelo", "hostname", "patrimonio", "departamento",
    "responsavel", "marca", "serial", "ramal", "ip", "observacao",
    "cpu", "disco", "ram", "iso", "status",
}


# ============================================================
# CACHES GLOBAIS
# ============================================================

_cache_bens = {"timestamp": 0, "dados": None}
CACHE_BENS_TTL = 60

_cache_idx_funcs = {"timestamp": 0, "dados": None}
CACHE_IDX_TTL = 60

_cache_pessoas = {"timestamp": 0, "dados": None}
CACHE_PESSOAS_TTL = 60
_CSV_THREAD_LOCK = threading.RLock()
_CSV_LOCK_STATE = threading.local()


@contextmanager
def _travar_csv():
    with _CSV_THREAD_LOCK:
        profundidade = getattr(_CSV_LOCK_STATE, "profundidade", 0)
        arquivo_lock = None
        if profundidade == 0:
            arquivo_lock = open(CSV_LOCK_PATH, "a+b")
            try:
                if os.name == "nt":
                    import msvcrt
                    arquivo_lock.seek(0, os.SEEK_END)
                    if arquivo_lock.tell() == 0:
                        arquivo_lock.write(b"\0")
                        arquivo_lock.flush()
                    arquivo_lock.seek(0)
                    msvcrt.locking(arquivo_lock.fileno(), msvcrt.LK_LOCK, 1)
                else:
                    import fcntl
                    fcntl.flock(arquivo_lock.fileno(), fcntl.LOCK_EX)
            except Exception:
                arquivo_lock.close()
                raise
        _CSV_LOCK_STATE.profundidade = profundidade + 1
        try:
            yield
        finally:
            _CSV_LOCK_STATE.profundidade -= 1
            if arquivo_lock is not None:
                try:
                    if os.name == "nt":
                        import msvcrt
                        arquivo_lock.seek(0)
                        msvcrt.locking(arquivo_lock.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(arquivo_lock.fileno(), fcntl.LOCK_UN)
                finally:
                    arquivo_lock.close()


def _com_csv_travado(funcao):
    @wraps(funcao)
    def wrapper(*args, **kwargs):
        with _travar_csv():
            return funcao(*args, **kwargs)
    return wrapper


def _invalidar_tudo():
    """Invalida TODOS os caches. Chamado em qualquer save."""
    _cache_bens["timestamp"] = 0
    _cache_bens["dados"] = None
    _cache_idx_funcs["timestamp"] = 0
    _cache_idx_funcs["dados"] = None
    _cache_pessoas["timestamp"] = 0
    _cache_pessoas["dados"] = None


# ============================================================
# CSV / LEITURA / ESCRITA
# ============================================================

def _achar_csv():
    for p in [os.path.join(BASE_DIR, "Levantamento*.csv"),
              os.path.join(BASE_DIR, "..", "Levantamento*.csv")]:
        achados = sorted(glob.glob(p))
        if achados:
            return os.path.abspath(achados[0])
    return None


CSV_PATH = _achar_csv()


def caminho_csv(): return CSV_PATH


def _detectar_encoding(path):
    if not os.path.exists(path):
        return "utf-8"
    with open(path, "rb") as f:
        raw = f.read(4)
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    try:
        with open(path, "r", encoding="utf-8") as f:
            f.read(4096)
        return "utf-8"
    except UnicodeDecodeError:
        return "cp1252"


def _backup_csv():
    if not CSV_PATH or not os.path.exists(CSV_PATH):
        raise RuntimeError("CSV do inventário ausente; o backup não foi criado.")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    nome = os.path.basename(CSV_PATH)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    shutil.copy2(CSV_PATH, os.path.join(BACKUP_DIR, ts + "__" + nome))


def _csv_carregar_raw():
    """Lê o CSV do disco SEM cache (usada internamente)."""
    global CSV_PATH
    if not CSV_PATH:
        CSV_PATH = _achar_csv()
    if not CSV_PATH or not os.path.exists(CSV_PATH):
        return []
    enc = _detectar_encoding(CSV_PATH)
    bens = []
    with open(CSV_PATH, "r", encoding=enc, newline="") as f:
        reader = csv.reader(f, delimiter=DELIMITER)
        try:
            cabecalho = next(reader)
        except StopIteration:
            return []
        indice_id = next(
            (
                i for i, nome in enumerate(cabecalho)
                if (nome or "").strip().casefold() == "id interno"
            ),
            None,
        )
        linhas = list(reader)

    ids_validos = set()
    if indice_id is not None:
        for raw in linhas:
            if indice_id < len(raw):
                try:
                    valor_id = int(raw[indice_id])
                except (TypeError, ValueError):
                    continue
                if valor_id > 0:
                    ids_validos.add(valor_id)
    proximo_id = max(ids_validos, default=0) + 1
    ids_utilizados = set()
    for raw in linhas:
        if not any((c or "").strip() for c in raw):
            continue
        raw = list(raw) + [""] * (len(COLS) - len(raw))
        item = {}
        for i, (_, campo) in enumerate(COLS):
            item[campo] = (raw[i] or "").strip()
        valor_id = None
        if indice_id is not None and indice_id < len(raw):
            try:
                candidato = int(raw[indice_id])
                if candidato > 0 and candidato not in ids_utilizados:
                    valor_id = candidato
            except (TypeError, ValueError):
                pass
        if valor_id is None:
            while proximo_id in ids_utilizados:
                proximo_id += 1
            valor_id = proximo_id
            proximo_id += 1
        item["id"] = valor_id
        ids_utilizados.add(valor_id)
        bens.append(item)
    return bens


def _csv_salvar(bens):
    if not CSV_PATH:
        raise RuntimeError("CSV do Levantamento não encontrado.")
    enc = _detectar_encoding(CSV_PATH)
    _backup_csv()
    fd, temporario = tempfile.mkstemp(
        prefix=".inventario-", suffix=".csv.tmp", dir=os.path.dirname(CSV_PATH)
    )
    try:
        with os.fdopen(fd, "w", encoding=enc, newline="") as arquivo:
            escritor = csv.writer(arquivo, delimiter=DELIMITER)
            escritor.writerow([c[0] for c in COLS] + ["ID interno"])
            for bem in bens:
                escritor.writerow(
                    [bem.get(campo, "") or "" for _, campo in COLS]
                    + [bem.get("id", "")]
                )
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, CSV_PATH)
    except Exception:
        if os.path.exists(temporario):
            os.unlink(temporario)
        raise


def _load(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8-sig") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as erro:
            raise ValueError(f"Arquivo de dados inválido: {os.path.basename(path)}") from erro


def _save(path, data):
    pasta = os.path.dirname(path)
    os.makedirs(pasta, exist_ok=True)
    fd, temporario = tempfile.mkstemp(
        prefix=".json-", suffix=".tmp", dir=pasta
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as arquivo:
            json.dump(data, arquivo, ensure_ascii=False, indent=2)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, path)
    except Exception:
        if os.path.exists(temporario):
            os.unlink(temporario)
        raise


# ============================================================
# LOADERS COM CACHE
# ============================================================

def load_bens():
    """Leitura COM cache (60s) — não relê CSV a cada request."""
    global _cache_bens
    agora = time.time()
    if (_cache_bens["dados"] is not None and
            agora - _cache_bens["timestamp"] < CACHE_BENS_TTL):
        return _cache_bens["dados"]

    dados = _csv_carregar_raw()
    _cache_bens = {"timestamp": agora, "dados": dados}
    return dados


def save_bens(lista):
    with _travar_csv():
        _csv_salvar(lista)
        try:
            _save(ARQ_BENS, lista)
        except OSError as erro:
            app.logger.exception("Não foi possível atualizar o espelho JSON dos bens: %s", erro)
        _invalidar_tudo()


def _versao_bem(bem):
    valores = [str(bem.get(campo) or "") for _, campo in COLS]
    valores.insert(0, str(bem.get("id", "")))
    conteudo = json.dumps(valores, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()


def load_funcs():
    """Carrega funcionários e garante IDs sequenciais."""
    funcs = _load(ARQ_FUNC, [])
    mudou = False
    maior_id = 0
    for f in funcs:
        try:
            fid = int(f.get("id") or 0)
        except (ValueError, TypeError):
            fid = 0
        if fid > maior_id:
            maior_id = fid
    for f in funcs:
        if not f.get("id"):
            maior_id += 1
            f["id"] = maior_id
            mudou = True
    if mudou and funcs:
        _save(ARQ_FUNC, funcs)
    return funcs


def load_deps(): return _load(ARQ_DEP, [])
def save_funcs(d):
    _save(ARQ_FUNC, d)
    _invalidar_tudo()
def load_ferias(): return _load(ARQ_FER, [])
def save_ferias(d):
    _save(ARQ_FER, d)
    _invalidar_tudo()
def load_projetos(): return _load(ARQ_PROJ, [])
def save_projetos(d): _save(ARQ_PROJ, d)


def load_alertas_funcionarios():
    alertas = _load(ARQ_ALERTAS_FUNC, [])
    return alertas if isinstance(alertas, list) else []


def save_alertas_funcionarios(alertas):
    _save(ARQ_ALERTAS_FUNC, alertas)


def carregar_status_bens():
    configurados = _load(ARQ_STATUS_BENS, [])
    if not isinstance(configurados, list):
        raise ValueError("A lista de status precisa ser uma lista JSON.")
    atuais = {
        normalizar(b.get("status"))
        for b in _csv_carregar_raw()
        if normalizar(b.get("status"))
    }
    return sorted(
        atuais | {
            normalizar(status) for status in configurados
            if isinstance(status, str) and normalizar(status)
        },
        key=str.casefold,
    )


def validar_status_bem(status):
    return not status or status in carregar_status_bens()


def next_id(lista):
    return (max([int(x.get("id", 0) or 0) for x in lista]) + 1) if lista else 1


# ============================================================
# NORMALIZAÇÃO
# ============================================================

def normalizar(s):
    return re.sub(r"\s+", " ", (s or "").strip())


def norm_nome(s):
    s = normalizar(s or "").upper()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return s


DEPTO_SINONIMOS = {
    "administracao": "administrativo",
    "admin": "administrativo",
    "adm": "administrativo",
    "administrativa": "administrativo",
    "operacoes": "operacional",
    "operacao": "operacional",
    "rh": "recursos humanos",
    "recursos humanos": "recursos humanos",
    "tecnico": "tecnica",
    "tecnica": "tecnica",
    "contabil": "contabilidade",
    "juridica": "juridico",
    "juridico": "juridico",
}

NOMES_COLETIVOS = {
    "ti", "t.i", "t i", "tecnologia da informacao", "tecnologia",
    "livre", "livres", "disponivel", "disponiveis", "estoque", "reserva",
    "sem responsavel", "sem resp", "vago", "vaga",
    "diretor", "diretoria", "diretoria executiva", "diretoria comercial",
    "diretoria institucional", "diretoria administrativa",
    "diretoria de programacao", "presidencia",
    "comercial", "marketing", "financeiro", "rh",
    "operacional", "operacoes", "operacoes comerciais", "opec",
    "jornalismo", "programacao", "transporte", "transportes",
    "administracao", "administrativo", "contabilidade", "controladoria",
    "recepcao", "copa", "portaria", "sala de reuniao", "auditorio",
    "gerencia", "coordenacao", "supervisao", "engenharia",
    "manutencao", "limpeza", "seguranca",
    "almoxarifado", "deposito", "deposito rh",
    "sala vip", "frente do switcher", "frente do swicher", "comutador",
    "switcher", "swicher", "sala de audio", "central tecnica", "geracao",
    "usuario frente swicher", "usuario frente switcher",
    "usuario ilha 1", "usuario ilha 2", "usuario ilha 3", "usuario ilha 4",
    "usuario sala de audio", "usuario sala de reuniao",
    "usuario cabine off", "usuario camarim", "usuario master",
    "usuario almoxarifado", "usuario portaria",
    "usuario prog/mark", "usuario progmark",
    "sala do t.i", "sala do ti", "sala tecnica",
    "pc geracao", "play aot", "tp", "audio hibrida",
    "diretoria de camera", "diretor de camera",
}

PREFIXOS_COLETIVOS = ("usuario ", "usuário ", "user ", "pc ", "play ", "sala ")


def _e_coletivo(nome):
    if not nome:
        return True
    n = norm_nome(nome).lower().strip()
    if n in NOMES_COLETIVOS:
        return True
    for prefixo in PREFIXOS_COLETIVOS:
        if n.startswith(prefixo):
            return True
    return False


def norm_depto(s):
    if not s:
        return ""
    n = norm_nome(s).lower().strip()
    return DEPTO_SINONIMOS.get(n, n)


def _partes_nome(nome):
    p = norm_nome(nome).split()
    if not p:
        return None, None
    return p[0], (p[-1] if len(p) > 1 else p[0])


def _similaridade_nomes(a, b):
    return SequenceMatcher(None, norm_nome(a), norm_nome(b)).ratio()


def _tokens_nome(nome):
    return set(norm_nome(nome).split())


# ============================================================
# ÍNDICES DE FUNCIONÁRIOS (busca O(1))
# ============================================================

def _construir_indices_funcs(funcs):
    """Constrói índices O(1) para busca de funcionário por nome."""
    idx = {
        "por_norm": {},
        "por_p1_pu": {},
        "por_p1": defaultdict(list),
    }
    for f in funcs:
        nome = f.get("nome", "")
        nn = norm_nome(nome)
        if not nn:
            continue
        idx["por_norm"][nn] = f

        partes = nn.split()
        if partes:
            p1 = partes[0]
            pu = partes[-1] if len(partes) > 1 else partes[0]
            idx["por_p1_pu"].setdefault((p1, pu), f)
            idx["por_p1"][p1].append(f)
    return idx


def _get_indices_funcs():
    """Retorna índices em cache."""
    global _cache_idx_funcs
    agora = time.time()
    if (_cache_idx_funcs["dados"] is not None and
            agora - _cache_idx_funcs["timestamp"] < CACHE_IDX_TTL):
        return _cache_idx_funcs["dados"]

    idx = _construir_indices_funcs(load_funcs())
    _cache_idx_funcs = {"timestamp": agora, "dados": idx}
    return idx


def _achar_funcionario(nome_bem):
    """
    Busca RÁPIDA usando índices. O(1) em 95% dos casos.
    Ordem: exato → 1º+últ → subconjunto → fuzzy.
    """
    if not nome_bem:
        return None
    nn = norm_nome(nome_bem)
    if not nn:
        return None

    idx = _get_indices_funcs()

    # 1. Exato — O(1)
    f = idx["por_norm"].get(nn)
    if f:
        return f

    partes = nn.split()
    if not partes:
        return None
    p1 = partes[0]
    pu = partes[-1] if len(partes) > 1 else partes[0]

    # 2. Primeiro + último — O(1)
    f = idx["por_p1_pu"].get((p1, pu))
    if f:
        return f

    # 3. Subconjunto — só com candidatos do mesmo 1º nome
    candidatos = idx["por_p1"].get(p1, [])
    tok_bem = set(partes)
    for cand in candidatos:
        tok_c = _tokens_nome(cand.get("nome", ""))
        if tok_bem <= tok_c or tok_c <= tok_bem:
            return cand

    # 4. Fuzzy — só com candidatos do mesmo 1º nome (rápido)
    if candidatos:
        melhor = None
        melhor_sim = 0
        for cand in candidatos:
            sim = SequenceMatcher(None, nn, norm_nome(cand.get("nome", ""))).ratio()
            if sim > melhor_sim:
                melhor_sim = sim
                melhor = cand

        if melhor_sim >= 0.85:
            return melhor
        if melhor_sim >= 0.70 and melhor:
            return melhor

    return None


# ============================================================
# FÉRIAS
# ============================================================

def ferias_ativas_set():
    ferias = load_ferias()
    ativos = set()
    hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    for f in ferias:
        status = (f.get("status") or "").strip()
        if status in ("Concluído", "Cancelado", ""):
            continue
        try:
            ini = datetime.strptime(f.get("inicio", ""), "%Y-%m-%d")
            fim = datetime.strptime(f.get("fim", ""), "%Y-%m-%d")
            if ini <= hoje <= fim:
                ativos.add(norm_nome(f.get("nome", "")))
        except Exception:
            pass
    return ativos


def ferias_ativas_chaves():
    ferias = load_ferias()
    chaves = set()
    hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    for f in ferias:
        status = (f.get("status") or "").strip()
        if status in ("Concluído", "Cancelado", ""):
            continue
        try:
            ini = datetime.strptime(f.get("inicio", ""), "%Y-%m-%d")
            fim = datetime.strptime(f.get("fim", ""), "%Y-%m-%d")
        except Exception:
            continue
        if not (ini <= hoje <= fim):
            continue
        partes = norm_nome(f.get("nome", "")).split()
        if not partes:
            continue
        primeiro = partes[0]
        ultimo = partes[-1] if len(partes) > 1 else partes[0]
        chaves.add((primeiro, ultimo))
    return chaves


def _nome_em_ferias(nome, chaves):
    if not nome:
        return False
    partes = norm_nome(nome).split()
    if not partes:
        return False
    primeiro = partes[0]
    ultimo = partes[-1] if len(partes) > 1 else partes[0]
    return (primeiro, ultimo) in chaves


def _listar_ramais(bens, chaves_ferias):
    por_pessoa = {}
    for bem in bens:
        ramal = normalizar(bem.get("ramal") or "")
        nome = normalizar(bem.get("responsavel") or "")
        if not ramal or not nome:
            continue

        chave = norm_nome(nome)
        pessoa = por_pessoa.setdefault(chave, {
            "nome": nome,
            "ramais": set(),
            "departamentos": set(),
            "em_ferias": _nome_em_ferias(nome, chaves_ferias),
        })
        pessoa["ramais"].add(ramal)
        departamento = normalizar(bem.get("departamento") or "")
        if departamento:
            pessoa["departamentos"].add(departamento)

    lista = []
    for pessoa in por_pessoa.values():
        ramais = sorted(pessoa["ramais"], key=lambda valor: (valor.casefold(), valor))
        departamentos = sorted(
            pessoa["departamentos"], key=lambda valor: (valor.casefold(), valor)
        )
        lista.append({
            "nome": pessoa["nome"],
            "ramais": ramais,
            "conflito": len(ramais) > 1,
            "departamento": ", ".join(departamentos) or "",
            "em_ferias": pessoa["em_ferias"],
        })

    return sorted(lista, key=lambda item: (norm_nome(item["nome"]), item["nome"]))


def ferias_em_andamento_lista():
    ferias = load_ferias()
    hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    lista = []
    for i, f in enumerate(ferias):
        try:
            ini = datetime.strptime(f.get("inicio", ""), "%Y-%m-%d")
            fim = datetime.strptime(f.get("fim", ""), "%Y-%m-%d")
        except Exception:
            continue
        if not (ini <= hoje <= fim):
            continue
        total = (fim - ini).days or 1
        progresso = round(((hoje - ini).days / total) * 100)
        lista.append({
            "idx": i,
            "nome": f.get("nome", ""),
            "inicio": ini.strftime("%d/%m/%Y"),
            "fim": fim.strftime("%d/%m/%Y"),
            "inicio_iso": f.get("inicio", ""),
            "fim_iso": f.get("fim", ""),
            "obs": f.get("obs", ""),
            "progresso": progresso,
            "dias_restantes": (fim - hoje).days,
        })
    lista.sort(key=lambda x: x["dias_restantes"])
    return lista


# ============================================================
# AGRUPAMENTO OTIMIZADO (usa índices + cache)
# ============================================================

def _pessoas_agrupadas():
    """
    Agrupa usando FUNCIONÁRIOS como base oficial.
    OTIMIZADO: O(n) em vez de O(n²). Usa índices pré-calculados.
    """
    global _cache_pessoas

    agora = time.time()
    if (_cache_pessoas["dados"] is not None and
            agora - _cache_pessoas["timestamp"] < CACHE_PESSOAS_TTL):
        return _cache_pessoas["dados"]

    bens = load_bens()
    funcs = load_funcs()
    chaves_ferias = ferias_ativas_chaves()

    # Base: 1 entrada por funcionário
    por_func = {}
    for f in funcs:
        try:
            fid = int(f.get("id"))
        except (ValueError, TypeError):
            continue
        por_func[fid] = {
            "funcionario_id": fid,
            "nome": f.get("nome", ""),
            "cargo": f.get("cargo", ""),
            "departamento": f.get("setor", ""),
            "ramal": "",
            "bens": [],
            "vinculado": True,
        }

    # Órfãos agrupados por nome normalizado
    orfaos = {}

    for b in bens:
        nome_bem = normalizar(b.get("responsavel") or "")
        if not nome_bem or _e_coletivo(nome_bem):
            continue

        func = _achar_funcionario(nome_bem)
        if func:
            try:
                fid = int(func["id"])
            except (ValueError, TypeError):
                fid = None
            if fid and fid in por_func:
                por_func[fid]["bens"].append(b)
                if not por_func[fid]["ramal"] and b.get("ramal"):
                    por_func[fid]["ramal"] = b.get("ramal").strip()
                continue

        chave = norm_nome(nome_bem)
        if chave not in orfaos:
            orfaos[chave] = {
                "funcionario_id": None,
                "nome": nome_bem,
                "cargo": "",
                "departamento": (b.get("departamento") or "").strip(),
                "ramal": (b.get("ramal") or "").strip(),
                "bens": [],
                "vinculado": False,
            }
        orfaos[chave]["bens"].append(b)

    resultado = []
    for p in por_func.values():
        p["em_ferias"] = _nome_em_ferias(p["nome"], chaves_ferias)
        resultado.append(p)

    for p in orfaos.values():
        p["em_ferias"] = _nome_em_ferias(p["nome"], chaves_ferias)
        resultado.append(p)

    _cache_pessoas = {"timestamp": agora, "dados": resultado}
    return resultado


# ============================================================
# MOVIMENTAÇÕES
# ============================================================

CABECALHO_MOV = ["data", "bem_id", "categoria", "patrimonio", "hostname",
                 "de_responsavel", "para_responsavel", "de_departamento",
                 "para_departamento", "obs", "realizado_por"]


def _garantir_cabecalho_movimentacoes():
    if not os.path.exists(ARQ_MOV) or os.path.getsize(ARQ_MOV) == 0:
        with open(ARQ_MOV, "w", newline="", encoding="utf-8-sig") as arquivo:
            csv.DictWriter(arquivo, fieldnames=CABECALHO_MOV).writeheader()
        return

    with open(ARQ_MOV, encoding="utf-8-sig", newline="") as arquivo:
        leitor = csv.DictReader(arquivo)
        fieldnames = leitor.fieldnames or []
        if "realizado_por" in fieldnames:
            return
        movimentos = list(leitor)

    os.makedirs(BACKUP_DIR, exist_ok=True)
    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    shutil.copy2(
        ARQ_MOV,
        os.path.join(BACKUP_DIR, f"{carimbo}__{os.path.basename(ARQ_MOV)}"),
    )
    fieldnames.append("realizado_por")
    temporario = ARQ_MOV + ".tmp"
    with open(temporario, "w", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.DictWriter(
            arquivo, fieldnames=fieldnames, extrasaction="ignore"
        )
        escritor.writeheader()
        escritor.writerows(movimentos)
    os.replace(temporario, ARQ_MOV)


def registrar_movimento(b, de_resp, de_dep, para_resp, para_dep, obs,
                        realizado_por):
    _garantir_cabecalho_movimentacoes()
    with open(ARQ_MOV, "a", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=CABECALHO_MOV)
        escritor.writerow({
            "data": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "bem_id": b.get("id"),
            "categoria": b.get("categoria"),
            "patrimonio": b.get("patrimonio"),
            "hostname": b.get("hostname"),
            "de_responsavel": de_resp,
            "para_responsavel": para_resp,
            "de_departamento": de_dep,
            "para_departamento": para_dep,
            "obs": obs,
            "realizado_por": realizado_por,
        })

def _dados_graficos():
    bens = load_bens()
    por_cat = defaultdict(int)
    por_dep = defaultdict(int)
    for b in bens:
        por_cat[b.get("categoria") or "Outros"] += 1
        por_dep[b.get("departamento") or "Sem depto"] += 1
    mov_mes = defaultdict(int)
    if os.path.exists(ARQ_MOV):
        with open(ARQ_MOV, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                try:
                    d = datetime.strptime(row["data"], "%Y-%m-%d %H:%M")
                    mov_mes[d.strftime("%Y-%m")] += 1
                except Exception:
                    pass
    hoje = datetime.now()
    eixo = []
    for i in range(11, -1, -1):
        ano, mes = hoje.year, hoje.month - i
        while mes <= 0:
            mes += 12
            ano -= 1
        eixo.append(f"{ano:04d}-{mes:02d}")
    mov_series = [mov_mes.get(m, 0) for m in eixo]
    return {
        "cat_labels": [k for k, _ in sorted(por_cat.items(), key=lambda x: -x[1])[:10]],
        "cat_values": [v for _, v in sorted(por_cat.items(), key=lambda x: -x[1])[:10]],
        "dep_labels": [k for k, _ in sorted(por_dep.items(), key=lambda x: -x[1])[:10]],
        "dep_values": [v for _, v in sorted(por_dep.items(), key=lambda x: -x[1])[:10]],
        "mov_labels": eixo, "mov_values": mov_series,
    }


@app.template_filter("to_date")
def to_date_filter(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except Exception:
        return None


@app.context_processor
def utility_processor():
    def progresso_ferias(inicio, fim):
        try:
            di = datetime.strptime(inicio, "%Y-%m-%d")
            df = datetime.strptime(fim, "%Y-%m-%d")
            hoje = datetime.now()
            if hoje < di:
                return 0
            if hoje > df:
                return 100
            total = (df - di).days
            passado = (hoje - di).days
            return round((passado / total) * 100) if total else 100
        except Exception:
            return 0
    nomes_perfis = {
        perfil["id"]: perfil["nome"]
        for perfil in permissoes.listar_perfis()
    }
    return dict(
        progresso_ferias=progresso_ferias,
        tem_permissao=tem_permissao,
        nome_perfil=nomes_perfis.get(session.get("tipo"), "Perfil sem acesso"),
    )


# ============================================================
# ROTAS
# ============================================================

@app.route("/")
def dashboard():
    if not tem_permissao("dashboard.ver"):
        return perfil_home()
    bens = load_bens()
    funcs = load_funcs()
    deps = load_deps()
    por_status = defaultdict(int)
    com_resp = sem_resp = 0
    sem_resp_departamento = sem_resp_sem_alocacao = 0
    for b in bens:
        por_status[b.get("status") or "Nao informado"] += 1
        if normalizar(b.get("responsavel")):
            com_resp += 1
        else:
            sem_resp += 1
            if normalizar(b.get("departamento")):
                sem_resp_departamento += 1
            else:
                sem_resp_sem_alocacao += 1
    tot_mov = 0
    if os.path.exists(ARQ_MOV):
        with open(ARQ_MOV, encoding="utf-8") as f:
            tot_mov = max(0, sum(1 for _ in f) - 1)
    graf = _dados_graficos()
    return render_template(
        "dashboard.html",
        total=len(bens),
        total_func=len(funcs),
        total_dep=len(deps),
        com_responsavel=com_resp,
        sem_responsavel=sem_resp,
        sem_resp_departamento=sem_resp_departamento,
        sem_resp_sem_alocacao=sem_resp_sem_alocacao,
        total_mov=tot_mov,
        por_status=dict(por_status),
        graf=graf,
        alertas_funcionarios=[
            alerta for alerta in load_alertas_funcionarios()
            if not alerta.get("resolvido")
        ] if tem_permissao("alertas.ver") else [],
    )


@app.route("/bens")
def bens_view():
    inventario_completo = load_bens()
    todos = list(inventario_completo)
    q = (request.args.get("q") or "").lower()
    cat = request.args.get("cat") or ""
    dep = request.args.get("dep") or ""
    resp = request.args.get("resp") or ""
    if q:
        todos = [b for b in todos if q in json.dumps(b, ensure_ascii=False).lower()]
    if cat:
        todos = [b for b in todos if (b.get("categoria") or "") == cat]
    if dep:
        todos = [b for b in todos if (b.get("departamento") or "") == dep]
    if resp:
        todos = [b for b in todos if normalizar(b.get("responsavel")) == resp]

    try:
        pagina = max(1, int(request.args.get("pagina", "1")))
    except ValueError:
        pagina = 1
    por_pagina = 50
    total_filtrado = len(todos)
    total_paginas = max(1, (total_filtrado + por_pagina - 1) // por_pagina)
    pagina = min(pagina, total_paginas)
    inicio = (pagina - 1) * por_pagina
    bens = todos[inicio:inicio + por_pagina]
    versoes = {str(b.get("id")): _versao_bem(b) for b in bens}
    movimentacoes_por_bem = defaultdict(int)
    if os.path.exists(ARQ_MOV):
        with open(ARQ_MOV, encoding="utf-8-sig", newline="") as arquivo:
            for movimento in csv.DictReader(arquivo):
                movimentacoes_por_bem[str(movimento.get("bem_id", ""))] += 1
    return render_template(
        "bens.html",
        bens=bens,
        versoes=versoes,
        movimentacoes_por_bem=movimentacoes_por_bem,
        categorias=sorted({b.get("categoria") for b in inventario_completo if b.get("categoria")}),
        departamentos=sorted({b.get("departamento") for b in inventario_completo if b.get("departamento")}),
        responsaveis=sorted({normalizar(b.get("responsavel")) for b in inventario_completo if b.get("responsavel")}),
        filtros={"q": q, "cat": cat, "dep": dep, "resp": resp},
        total_filtrado=total_filtrado,
        pagina=pagina,
        total_paginas=total_paginas,
        inicio_resultados=inicio + 1 if total_filtrado else 0,
        fim_resultados=min(inicio + por_pagina, total_filtrado),
        status_bens=carregar_status_bens(),
    )


@app.route("/bens/salvar", methods=["POST"])
@_com_csv_travado
def bens_salvar():
    d = request.get_json(silent=True)
    if not isinstance(d, dict):
        return jsonify({"ok": False, "msg": "Dados do bem inválidos."}), 400
    bens = _csv_carregar_raw()
    campos = ["categoria", "modelo", "hostname", "patrimonio", "departamento",
              "responsavel", "marca", "serial", "ramal", "ip", "observacao",
              "cpu", "disco", "ram", "iso", "status"]
    if any(campo in d and not isinstance(d[campo], str) for campo in campos):
        return jsonify({"ok": False, "msg": "Os campos do bem devem ser textos."}), 400
    item = {k: normalizar(d.get(k)) for k in campos}
    if not validar_status_bem(item["status"]):
        return jsonify({
            "ok": False,
            "msg": "Status não configurado. Atualize a lista de status nas configurações.",
        }), 400
    bid = d.get("id")
    if bid:
        try:
            bid = int(bid)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "msg": "ID do bem inválido."}), 400
        bem_atual = next((b for b in bens if b.get("id") == bid), None)
        if not bem_atual:
            return jsonify({"ok": False, "msg": "Bem não encontrado."}), 404
        versao = d.get("versao")
        if not isinstance(versao, str) or not secrets.compare_digest(
            versao, _versao_bem(bem_atual)
        ):
            return jsonify({
                "ok": False,
                "conflito": True,
                "msg": "Este bem foi alterado por outra pessoa. Recarregue a página antes de salvar.",
            }), 409
        for i, b in enumerate(bens):
            if b.get("id") == bid:
                bens[i] = {**b, **item, "atualizado_em": datetime.now().isoformat()}
                break
        msg = "Bem atualizado!"
    else:
        item["id"] = next_id(bens)
        item["criado_em"] = datetime.now().isoformat()
        bens.append(item)
        msg = "Bem cadastrado!"
    save_bens(bens)
    atualizado = next(b for b in bens if b.get("id") == bid) if bid else None
    return jsonify({
        "ok": True,
        "msg": msg,
        "versao": _versao_bem(atualizado) if atualizado else None,
    })

@app.route("/bens/transferir", methods=["POST"])
@_com_csv_travado
def bens_transferir():
    """Transfere um bem para outro responsável/departamento e registra no histórico."""
    d = request.get_json(silent=True)
    if not isinstance(d, dict):
        return jsonify({"ok": False, "msg": "Dados da transferência inválidos."}), 400
    bid = d.get("id")
    versao = d.get("versao")
    if not isinstance(bid, int) or isinstance(bid, bool) or not isinstance(versao, str):
        return jsonify({"ok": False, "msg": "ID e versão do bem são obrigatórios."}), 400
    if any(
        not isinstance(d.get(campo, ""), str)
        for campo in ("novo_responsavel", "novo_departamento", "obs")
    ):
        return jsonify({"ok": False, "msg": "Os dados da transferência devem ser textos."}), 400
    novo_resp = normalizar(d.get("novo_responsavel") or "")
    novo_dep = normalizar(d.get("novo_departamento") or "")
    obs = normalizar(d.get("obs") or "")
    if not novo_resp:
        return jsonify({"ok": False, "msg": "Informe o novo responsável"})

    bens = _csv_carregar_raw()
    bem = next((item for item in bens if item.get("id") == bid), None)
    if not bem:
        return jsonify({"ok": False, "msg": "Bem não encontrado"}), 404
    if not secrets.compare_digest(versao, _versao_bem(bem)):
        return jsonify({
            "ok": False,
            "conflito": True,
            "msg": "Este bem foi alterado por outra pessoa. Recarregue a página antes de transferir.",
        }), 409
    ar = bem.get("responsavel") or ""
    ad = bem.get("departamento") or ""
    bem["responsavel"] = novo_resp
    if novo_dep:
        bem["departamento"] = novo_dep
    registrar_movimento(
        bem, ar, ad, bem["responsavel"], bem["departamento"], obs,
        session.get("usuario", ""),
    )

    save_bens(bens)
    return jsonify({"ok": True, "msg": f"Bem transferido para {novo_resp}!"})

@app.route("/bens/excluir/<int:bid>", methods=["POST"])
@_com_csv_travado
def bens_excluir(bid):
    bens = _csv_carregar_raw()
    bem = next((item for item in bens if item.get("id") == bid), None)
    if not bem:
        return jsonify({"ok": False, "msg": "Bem não encontrado."}), 404
    d = request.get_json(silent=True)
    if not isinstance(d, dict):
        return jsonify({"ok": False, "msg": "Versão do bem inválida."}), 400
    versao = d.get("versao")
    if not isinstance(versao, str) or not secrets.compare_digest(
        versao, _versao_bem(bem)
    ):
        return jsonify({
            "ok": False,
            "conflito": True,
            "msg": "Este bem foi alterado desde que a página foi aberta. Recarregue antes de excluir.",
        }), 409

    movimentos = []
    fieldnames = CABECALHO_MOV
    if os.path.exists(ARQ_MOV):
        with open(ARQ_MOV, encoding="utf-8-sig", newline="") as arquivo:
            leitor = csv.DictReader(arquivo)
            fieldnames = leitor.fieldnames or CABECALHO_MOV
            movimentos = list(leitor)
    relacionados = [
        movimento for movimento in movimentos
        if str(movimento.get("bem_id", "")) == str(bid)
    ]

    os.makedirs(BACKUP_DIR, exist_ok=True)
    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    try:
        shutil.copy2(CSV_PATH, os.path.join(
            BACKUP_DIR, f"{carimbo}__{os.path.basename(CSV_PATH)}"
        ))
        if os.path.exists(ARQ_MOV):
            shutil.copy2(ARQ_MOV, os.path.join(
                BACKUP_DIR, f"{carimbo}__{os.path.basename(ARQ_MOV)}"
            ))
    except OSError:
        app.logger.exception("Falha ao criar backup antes de excluir o bem %s", bid)
        return jsonify({
            "ok": False,
            "msg": "Não foi possível criar o backup. O bem e o histórico não foram excluídos.",
        }), 500

    restantes = [b for b in bens if b.get("id") != bid]
    if relacionados and os.path.exists(ARQ_MOV):
        restantes_mov = [
            movimento for movimento in movimentos
            if str(movimento.get("bem_id", "")) != str(bid)
        ]
        caminho_temporario = ARQ_MOV + ".tmp"
        with open(caminho_temporario, "w", encoding="utf-8-sig", newline="") as arquivo:
            escritor = csv.DictWriter(
                arquivo, fieldnames=fieldnames, extrasaction="ignore"
            )
            escritor.writeheader()
            escritor.writerows(restantes_mov)
        os.replace(caminho_temporario, ARQ_MOV)
    save_bens(restantes)
    return jsonify({
        "ok": True,
        "msg": f"Bem excluído; {len(relacionados)} movimentação(ões) removida(s).",
    })


@app.route("/bens/exportar.csv")
def bens_exportar():
    if not CSV_PATH or not os.path.exists(CSV_PATH):
        return "CSV não encontrado", 404
    return send_file(CSV_PATH, mimetype="text/csv", as_attachment=True,
                     download_name="Levantamento_Geral1_controle.csv")


@app.route("/planilha")
def planilha_view():
    bens = load_bens()
    cats = sorted({(b.get("categoria") or "").strip()
                   for b in bens if (b.get("categoria") or "").strip()})
    deps = sorted({(b.get("departamento") or "").strip()
                   for b in bens if (b.get("departamento") or "").strip()})
    versoes = {str(b.get("id")): _versao_bem(b) for b in bens}
    return render_template("planilha.html", bens=bens, cats=cats, deps=deps,
                           total=len(bens), versoes=versoes)


@app.route("/api/bens/celula", methods=["POST"])
@_com_csv_travado
def api_bens_celula():
    d = request.get_json(silent=True)
    if not isinstance(d, dict):
        return jsonify({"ok": False, "msg": "Dados de edição inválidos."}), 400
    bid = d.get("id")
    campo = d.get("campo")
    valor = d.get("valor")
    if (
        not isinstance(bid, int)
        or isinstance(bid, bool)
        or not isinstance(campo, str)
        or not isinstance(valor, str)
    ):
        return jsonify({"ok": False, "msg": "ID, campo ou valor inválido."}), 400
    campo = campo.strip()
    valor = valor.strip()
    if campo not in CAMPOS_BEM_EDITAVEIS:
        return jsonify({"ok": False, "msg": "Campo não editável."}), 400
    if campo == "status" and not validar_status_bem(valor):
        return jsonify({"ok": False, "msg": "Status não configurado."}), 400
    versao = d.get("versao")
    if not isinstance(versao, str) or not versao:
        return jsonify({"ok": False, "msg": "Recarregue a Planilha antes de editar."}), 400
    bens = _csv_carregar_raw()
    achou = False
    for b in bens:
        if b.get("id") == bid:
            if not secrets.compare_digest(versao, _versao_bem(b)):
                return jsonify({
                    "ok": False,
                    "conflito": True,
                    "msg": "Este bem foi alterado por outra pessoa. Recarregue a Planilha antes de editar.",
                }), 409
            b[campo] = valor
            achou = True
            break
    if not achou:
        return jsonify({"ok": False, "msg": "Bem nao encontrado"})
    save_bens(bens)
    atualizado = next(b for b in bens if b.get("id") == bid)
    return jsonify({
        "ok": True,
        "valor": valor,
        "versao": _versao_bem(atualizado),
    })


@app.route("/api/bens/planilha_lote", methods=["POST"])
@_com_csv_travado
def api_bens_planilha_lote():
    d = request.get_json(silent=True)
    if not isinstance(d, dict):
        return jsonify({"ok": False, "msg": "Dados de edição inválidos."}), 400
    edicoes = d.get("edicoes")
    if not isinstance(edicoes, list):
        return jsonify({"ok": False, "msg": "Lista de edições inválida."}), 400
    if not edicoes:
        return jsonify({"ok": True, "aplicadas": 0})
    bens = _csv_carregar_raw()
    por_id = {b.get("id"): b for b in bens}
    validadas = []
    for e in edicoes:
        if not isinstance(e, dict):
            return jsonify({"ok": False, "msg": "Edição inválida."}), 400
        bid = e.get("id")
        campo = e.get("campo")
        valor = e.get("valor")
        versao = e.get("versao")
        if (
            not isinstance(bid, int)
            or isinstance(bid, bool)
            or not isinstance(campo, str)
            or campo not in CAMPOS_BEM_EDITAVEIS
            or not isinstance(valor, str)
            or not isinstance(versao, str)
        ):
            return jsonify({"ok": False, "msg": "Dados de edição inválidos."}), 400
        b = por_id.get(bid)
        if not b:
            return jsonify({"ok": False, "msg": "Bem não encontrado."}), 404
        if not secrets.compare_digest(versao, _versao_bem(b)):
            return jsonify({
                "ok": False,
                "conflito": True,
                "msg": "Um ou mais bens foram alterados. Recarregue a Planilha antes de editar.",
            }), 409
        validadas.append((b, campo, valor.strip()))
    for b, campo, valor in validadas:
        if campo == "status" and not validar_status_bem(valor):
            return jsonify({"ok": False, "msg": "Status não configurado."}), 400
    for b, campo, valor in validadas:
        b[campo] = valor
    save_bens(bens)
    return jsonify({
        "ok": True,
        "aplicadas": len(validadas),
        "versoes": {str(b["id"]): _versao_bem(b) for b, _, _ in validadas},
    })


@app.route("/funcionarios")
def funcionarios_view():
    funcs = load_funcs()
    bens = load_bens()

    # Mapa: id → qtd bens
    cont_bens = defaultdict(int)
    for b in bens:
        nome_bem = normalizar(b.get("responsavel") or "")
        if not nome_bem or _e_coletivo(nome_bem):
            continue
        f = _achar_funcionario(nome_bem)
        if f:
            try:
                cont_bens[int(f["id"])] += 1
            except (ValueError, TypeError):
                pass

    resultado = []
    for f in funcs:
        try:
            fid = int(f.get("id"))
        except (ValueError, TypeError):
            continue
        resultado.append({
            "id": fid,
            "nome": f.get("nome", ""),
            "cargo": f.get("cargo", ""),
            "setor": f.get("setor", ""),
            "total_bens": cont_bens.get(fid, 0),
        })

    resultado.sort(key=lambda x: x["nome"].lower())
    return render_template("funcionarios.html", funcionarios=resultado)


@app.route("/funcionarios/salvar", methods=["POST"])
def funcionarios_salvar():
    d = request.get_json(silent=True)
    if not isinstance(d, dict):
        return jsonify({"ok": False, "msg": "Dados do funcionário inválidos."}), 400
    funcs = load_funcs()
    campos = ["nome", "cargo", "setor"]
    if any(campo in d and not isinstance(d[campo], str) for campo in campos):
        return jsonify({"ok": False, "msg": "Os campos do funcionário devem ser textos."}), 400
    item = {k: normalizar(d.get(k)) for k in campos}
    if not item["nome"]:
        return jsonify({"ok": False, "msg": "Nome obrigatório."}), 400

    fid = d.get("id")
    if fid:
        try:
            fid = int(fid)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "msg": "ID do funcionário inválido."}), 400
        funcionario = next((f for f in funcs if int(f.get("id") or 0) == fid), None)
        if not funcionario:
            return jsonify({"ok": False, "msg": "Funcionário não encontrado."}), 404
    duplicado = next(
        (
            f for f in funcs
            if norm_nome(f.get("nome", "")) == norm_nome(item["nome"])
            and str(f.get("id")) != str(fid)
        ),
        None,
    )
    if duplicado:
        return jsonify({"ok": False, "msg": "Já existe um funcionário com esse nome."}), 400

    if fid:
        for f in funcs:
            if str(f.get("id")) == str(fid):
                f.update(item)
                break
        msg = "Funcionário atualizado!"
    else:
        item["id"] = next_id(funcs)
        funcs.append(item)
        msg = "Funcionário cadastrado!"

    save_funcs(funcs)
    return jsonify({"ok": True, "msg": msg})


@app.route("/funcionarios/excluir/<int:fid>", methods=["POST"])
def funcionarios_excluir(fid):
    """Exclui funcionário por ID (mais confiável que índice)."""
    funcs = load_funcs()
    funcionario = next(
        (f for f in funcs if str(f.get("id")) == str(fid)),
        None,
    )
    if not funcionario:
        return jsonify({"ok": False, "msg": "Funcionário não encontrado"})

    bens_pendentes = []
    for bem in load_bens():
        nome_responsavel = normalizar(bem.get("responsavel") or "")
        if not nome_responsavel or _e_coletivo(nome_responsavel):
            continue
        vinculado = _achar_funcionario(nome_responsavel)
        if vinculado and str(vinculado.get("id")) == str(fid):
            bens_pendentes.append({
                "id": bem.get("id"),
                "patrimonio": bem.get("patrimonio") or "",
                "hostname": bem.get("hostname") or "",
                "categoria": bem.get("categoria") or "",
            })

    if bens_pendentes:
        alertas = load_alertas_funcionarios()
        alertas.append({
            "id": next_id(alertas),
            "funcionario": funcionario.get("nome", ""),
            "criado_em": datetime.now().isoformat(timespec="seconds"),
            "resolvido": False,
            "resolvido_em": "",
            "resolvido_por": "",
            "bens": bens_pendentes,
        })
        save_alertas_funcionarios(alertas)

    funcs = [f for f in funcs if str(f.get("id")) != str(fid)]
    save_funcs(funcs)
    return jsonify({
        "ok": True,
        "msg": "Funcionário excluído!",
        "bens_pendentes": len(bens_pendentes),
    })


@app.route("/funcionario/<int:fid>")
def funcionario_detalhe(fid):
    funcs = load_funcs()
    func = next((f for f in funcs if int(f.get("id") or 0) == fid), None)
    if not func:
        return "Funcionário não encontrado", 404

    bens = load_bens()
    bens_do_func = []
    for b in bens:
        nome_bem = normalizar(b.get("responsavel") or "")
        if not nome_bem or _e_coletivo(nome_bem):
            continue
        f = _achar_funcionario(nome_bem)
        if f and int(f.get("id") or 0) == fid:
            bens_do_func.append(b)

    return render_template("funcionario_detalhe.html",
                           func=func,
                           bens=bens_do_func,
                           total=len(bens_do_func))


@app.route("/bem/<int:bid>")
def bem_detalhe(bid):
    bem = next((b for b in load_bens() if str(b.get("id")) == str(bid)), None)
    if not bem:
        return "Bem não encontrado", 404

    historico = []
    if os.path.exists(ARQ_MOV):
        with open(ARQ_MOV, encoding="utf-8-sig", newline="") as arquivo:
            historico = [
                movimento
                for movimento in csv.DictReader(arquivo)
                if str(movimento.get("bem_id", "")) == str(bid)
            ]
    historico.sort(key=lambda movimento: movimento.get("data", ""), reverse=True)
    return render_template("bem_detalhe.html", bem=bem, historico=historico)


@app.route("/alertas-funcionarios/<int:alerta_id>/resolver", methods=["POST"])
def alerta_funcionario_resolver(alerta_id):
    if not tem_permissao("alertas.editar"):
        return jsonify({"ok": False, "msg": "Acesso negado"}), 403

    alertas = load_alertas_funcionarios()
    alerta = next(
        (item for item in alertas if str(item.get("id")) == str(alerta_id)),
        None,
    )
    if not alerta:
        return jsonify({"ok": False, "msg": "Alerta não encontrado"}), 404
    if not alerta.get("resolvido"):
        alerta["resolvido"] = True
        alerta["resolvido_em"] = datetime.now().isoformat(timespec="seconds")
        alerta["resolvido_por"] = session.get("nome", session.get("usuario", ""))
        save_alertas_funcionarios(alertas)
    return jsonify({"ok": True, "msg": "Alerta marcado como resolvido."})


@app.route("/api/funcionarios/orfaos")
def api_funcionarios_orfaos():
    bens = load_bens()
    orfaos = defaultdict(list)

    for b in bens:
        nome_bem = normalizar(b.get("responsavel") or "")
        if not nome_bem or _e_coletivo(nome_bem):
            continue
        f = _achar_funcionario(nome_bem)
        if not f:
            orfaos[nome_bem].append({
                "id": b.get("id"),
                "patrimonio": b.get("patrimonio", ""),
                "departamento": b.get("departamento", ""),
            })

    return jsonify({
        "ok": True,
        "orfaos": [{"nome": k, "qtd": len(v), "bens": v} for k, v in orfaos.items()],
        "total": sum(len(v) for v in orfaos.values()),
    })


@app.route("/organograma")
def organograma_view():
    return render_template("organograma.html")


@app.route("/movimentar")
def movimentar_view():
    bens = load_bens()
    funcs = load_funcs()
    deps = load_deps()
    por_resp = defaultdict(list)
    for b in bens:
        r = normalizar(b.get("responsavel") or "") or "SEM RESPONSAVEL"
        por_resp[r].append({**b, "versao": _versao_bem(b)})
    versoes = {str(b.get("id")): _versao_bem(b) for b in bens}
    return render_template("movimentar.html", bens=bens, versoes=versoes, funcionarios=funcs,
                           departamentos=deps,
                           por_resp={k: v for k, v in por_resp.items()})


@app.route("/movimentar/registrar", methods=["POST"])
@_com_csv_travado
def movimentar_registrar():
    d = request.get_json(silent=True)
    if not isinstance(d, dict):
        return jsonify({"ok": False, "msg": "Dados da movimentação inválidos."}), 400
    if not all(isinstance(d.get(campo), str) for campo in ("origem", "destino")):
        return jsonify({"ok": False, "msg": "Origem ou destino inválido."}), 400
    if not isinstance(d.get("obs", ""), str) or not isinstance(
        d.get("departamento_destino", ""), str
    ):
        return jsonify({"ok": False, "msg": "Observação ou departamento inválido."}), 400
    origem = normalizar(d.get("origem"))
    destino = normalizar(d.get("destino"))
    dep_dest = normalizar(d.get("departamento_destino"))
    obs = normalizar(d.get("obs"))
    ids = d.get("ids") or []
    versoes = d.get("versoes")
    if not origem or not destino or not ids:
        return jsonify({"ok": False, "msg": "Preencha origem, destino e selecione ao menos 1 bem."})
    if not isinstance(ids, list) or not isinstance(versoes, dict):
        return jsonify({"ok": False, "msg": "Lista de bens ou versões inválida."}), 400
    bens = _csv_carregar_raw()
    por_id = {b.get("id"): b for b in bens}
    selecionados = []
    ids_vistos = set()
    for bid in ids:
        if not isinstance(bid, int) or isinstance(bid, bool):
            return jsonify({"ok": False, "msg": "ID de bem inválido."}), 400
        if bid in ids_vistos:
            return jsonify({"ok": False, "msg": "A lista contém bens repetidos."}), 400
        ids_vistos.add(bid)
        bem = por_id.get(bid)
        if not bem:
            return jsonify({"ok": False, "msg": "Um dos bens não existe mais. Recarregue a página."}), 404
        versao = versoes.get(str(bid))
        if not isinstance(versao, str) or not secrets.compare_digest(
            versao, _versao_bem(bem)
        ):
            return jsonify({
                "ok": False,
                "conflito": True,
                "msg": "Um ou mais bens foram alterados. Recarregue a página antes de movimentar.",
            }), 409
        selecionados.append(bem)
    registrados = 0
    for b in selecionados:
        ar, ad = b.get("responsavel"), b.get("departamento")
        b["responsavel"] = destino
        if dep_dest:
            b["departamento"] = dep_dest
        registrar_movimento(
            b, ar, ad, b["responsavel"], b["departamento"], obs,
            session.get("usuario", ""),
        )
        registrados += 1
    save_bens(bens)
    return jsonify({"ok": True, "total": registrados,
                    "msg": f"{registrados} movimentacao(oes) registrada(s)!"})


@app.route("/movimentacoes")
def movimentacoes_view():
    linhas = []
    if os.path.exists(ARQ_MOV):
        with open(ARQ_MOV, encoding="utf-8-sig") as f:
            linhas = list(csv.DictReader(f))
    q = (request.args.get("q") or "").lower()
    if q:
        linhas = [l for l in linhas if q in json.dumps(l, ensure_ascii=False).lower()]
    return render_template("movimentacoes.html",
                           movimentacoes=list(reversed(linhas)),
                           total=len(linhas), filtros={"q": q})


@app.route("/movimentacoes/exportar.csv")
def movimentacoes_exportar():
    if not os.path.exists(ARQ_MOV):
        return "Sem dados", 404
    return send_file(ARQ_MOV, mimetype="text/csv", as_attachment=True,
                     download_name="movimentacoes.csv")


@app.route("/ferias")
def ferias_view():
    ferias = load_ferias()
    funcs = load_funcs()
    hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    enriquecidas = []
    for i, f in enumerate(ferias):
        status_manual = (f.get("status") or "").strip()
        try:
            ini = datetime.strptime(f.get("inicio", ""), "%Y-%m-%d")
            fim = datetime.strptime(f.get("fim", ""), "%Y-%m-%d")
        except Exception:
            ini = fim = None

        if status_manual in ("Concluído", "Cancelado"):
            status_calc = status_manual
        elif ini and fim:
            if hoje < ini:
                status_calc = "Futura"
            elif ini <= hoje <= fim:
                status_calc = "Em andamento"
            else:
                status_calc = "Encerrada"
        else:
            status_calc = status_manual or "—"

        progresso = 0
        if ini and fim:
            if hoje < ini:
                progresso = 0
            elif hoje > fim:
                progresso = 100
            else:
                total = (fim - ini).days or 1
                progresso = round(((hoje - ini).days / total) * 100)

        dias_restantes = None
        if status_calc == "Em andamento" and fim:
            dias_restantes = (fim - hoje).days

        enriquecidas.append({
            "idx": i,
            "nome": f.get("nome", ""),
            "inicio": f.get("inicio", ""),
            "fim": f.get("fim", ""),
            "status": status_calc,
            "status_manual": status_manual,
            "obs": f.get("obs", ""),
            "progresso": progresso,
            "dias_restantes": dias_restantes,
        })

    enriquecidas.sort(key=lambda x: x["inicio"] or "", reverse=True)

    em_andamento = [f for f in enriquecidas if f["status"] == "Em andamento"]
    futuras = [f for f in enriquecidas if f["status"] == "Futura"]
    encerradas = [f for f in enriquecidas
                  if f["status"] in ("Encerrada", "Concluído", "Cancelado")]

    return render_template(
        "ferias.html",
        todas=enriquecidas,
        em_andamento=em_andamento,
        futuras=futuras,
        encerradas=encerradas,
        funcionarios=funcs,
        hoje=hoje,
    )


@app.route("/ferias/salvar", methods=["POST"])
def ferias_salvar():
    d = request.get_json(silent=True)
    if not isinstance(d, dict):
        return jsonify({"ok": False, "msg": "Dados de férias inválidos."}), 400
    campos_texto = ("nome", "inicio", "fim", "status", "obs")
    if any(campo in d and not isinstance(d[campo], str) for campo in campos_texto):
        return jsonify({"ok": False, "msg": "Os campos de férias devem ser textos."}), 400
    ferias = load_ferias()
    idx = d.get("idx")
    if idx is not None and (
        not isinstance(idx, int) or isinstance(idx, bool) or not 0 <= idx < len(ferias)
    ):
        return jsonify({"ok": False, "msg": "Registro de férias não encontrado."}), 404
    status_informado = d.get("status")
    if status_informado is None and idx is not None:
        status_informado = ferias[idx].get("status", "")
    item = {
        "nome": normalizar(d.get("nome")),
        "inicio": normalizar(d.get("inicio")),
        "fim": normalizar(d.get("fim")),
        "status": normalizar(status_informado) or "Férias não iniciada",
        "obs": normalizar(d.get("obs")),
    }
    if not item["nome"] or not item["inicio"] or not item["fim"]:
        return jsonify({"ok": False, "msg": "Preencha nome, início e fim."}), 400
    try:
        inicio = datetime.strptime(item["inicio"], "%Y-%m-%d").date()
        fim = datetime.strptime(item["fim"], "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"ok": False, "msg": "Informe datas válidas no formato AAAA-MM-DD."}), 400
    if fim < inicio:
        return jsonify({"ok": False, "msg": "A data de fim não pode ser anterior à data de início."}), 400
    status_permitidos = {
        "Férias não iniciada", "Férias iniciada", "Concluído", "Cancelado",
        "Em andamento", ""
    }
    if item["status"] not in status_permitidos:
        return jsonify({"ok": False, "msg": "Status de férias inválido."}), 400
    if idx is not None:
        duplicada = any(
            norm_nome(registro.get("nome", "")) == norm_nome(item["nome"])
            and registro.get("inicio") == item["inicio"]
            and registro.get("fim") == item["fim"]
            and indice != idx
            for indice, registro in enumerate(ferias)
        )
        if duplicada:
            return jsonify({"ok": False, "msg": "Esse período já está cadastrado."}), 400
        ferias[idx] = {**ferias[idx], **item}
        msg = "Férias atualizadas!"
    else:
        if any(
            norm_nome(registro.get("nome", "")) == norm_nome(item["nome"])
            and registro.get("inicio") == item["inicio"]
            and registro.get("fim") == item["fim"]
            for registro in ferias
        ):
            return jsonify({"ok": False, "msg": "Esse período já está cadastrado."}), 400
        ferias.append(item)
        msg = "Férias cadastradas!"
    save_ferias(ferias)
    return jsonify({"ok": True, "msg": msg})


@app.route("/ferias/excluir/<int:idx>", methods=["POST"])
def ferias_excluir(idx):
    ferias = load_ferias()
    if 0 <= idx < len(ferias):
        ferias.pop(idx)
        save_ferias(ferias)
        return jsonify({"ok": True})
    return jsonify({"ok": False, "msg": "Registro de férias não encontrado."}), 404


@app.route("/ramais")
def ramais_view():
    bens = load_bens()
    chaves_ferias = ferias_ativas_chaves()
    ramais = _listar_ramais(bens, chaves_ferias)
    por_departamento = defaultdict(list)
    for pessoa in ramais:
        departamentos = [
            departamento.strip()
            for departamento in pessoa["departamento"].split(",")
            if departamento.strip()
        ] or ["Sem departamento"]
        for departamento in departamentos:
            por_departamento[departamento].append(pessoa)

    prioridades = (
        "SECRETARIA DE DIRETORIA",
        "RECEPCAO",
        "COPA",
        "PORTARIA",
        "SALA DE REUNIAO",
    )

    def prioridade_departamento(nome):
        chave = norm_nome(nome)
        for posicao, prioritario in enumerate(
            ("DIRETOR EXECUTIVO", "DIRETOR ADMINISTRATIVO")
        ):
            if prioritario in chave:
                return (0, posicao, chave)
        if "DIRETOR" in chave or "DIRETORIA" in chave:
            return (0, 2, chave)
        for posicao, prioritario in enumerate(prioridades, start=1):
            if prioritario in chave:
                return (posicao, 0, chave)
        return (len(prioridades) + 1, 0, chave)

    grupos_ramais = [
        {
            "nome": departamento,
            "pessoas": sorted(
                pessoas, key=lambda pessoa: (norm_nome(pessoa["nome"]), pessoa["nome"])
            ),
        }
        for departamento, pessoas in sorted(
            por_departamento.items(),
            key=lambda item: prioridade_departamento(item[0]),
        )
    ]
    return render_template(
        "ramais.html",
        ramais=ramais,
        grupos_ramais=grupos_ramais,
        data_atual=datetime.now().strftime("%d/%m/%Y"),
        total=len(ramais),
        total_conflitos=sum(pessoa["conflito"] for pessoa in ramais),
    )


@app.route("/projetos")
def projetos_view():
    projetos = load_projetos()
    return render_template("projetos.html", projetos=projetos)


@app.route("/projetos/salvar", methods=["POST"])
def projetos_salvar():
    d = request.get_json(silent=True)
    if not isinstance(d, dict):
        return jsonify({"ok": False, "msg": "Dados do projeto inválidos."}), 400
    projetos = load_projetos()
    campos_texto = ("nome", "responsavel", "prioridade", "status", "prazo")
    if any(campo in d and not isinstance(d[campo], str) for campo in campos_texto):
        return jsonify({"ok": False, "msg": "Os campos do projeto devem ser textos."}), 400
    try:
        progresso = int(d.get("progresso") or 0)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "msg": "Progresso inválido."}), 400
    if not 0 <= progresso <= 100:
        return jsonify({"ok": False, "msg": "Progresso deve estar entre 0 e 100."}), 400
    prazo = normalizar(d.get("prazo"))
    if prazo:
        try:
            datetime.strptime(prazo, "%Y-%m-%d")
        except ValueError:
            return jsonify({"ok": False, "msg": "Prazo deve usar o formato AAAA-MM-DD."}), 400
    item = {
        "nome": normalizar(d.get("nome")),
        "responsavel": normalizar(d.get("responsavel")),
        "prioridade": normalizar(d.get("prioridade")) or "Média",
        "progresso": progresso,
        "status": normalizar(d.get("status")) or "Em Andamento",
        "prazo": prazo,
    }
    if not item["nome"]:
        return jsonify({"ok": False, "msg": "Informe o nome do projeto."}), 400
    idx = d.get("idx")
    if idx is not None:
        if not isinstance(idx, int) or isinstance(idx, bool) or not 0 <= idx < len(projetos):
            return jsonify({"ok": False, "msg": "Projeto não encontrado."}), 404
        projetos[idx] = {**projetos[idx], **item}
        msg = "Projeto atualizado!"
    else:
        if any(norm_nome(p.get("nome", "")) == norm_nome(item["nome"]) for p in projetos):
            return jsonify({"ok": False, "msg": "Já existe um projeto com esse nome."}), 400
        projetos.append(item)
        msg = "Projeto cadastrado!"
    save_projetos(projetos)
    return jsonify({"ok": True, "msg": msg})


@app.route("/projetos/excluir/<int:idx>", methods=["POST"])
def projetos_excluir(idx):
    projetos = load_projetos()
    if 0 <= idx < len(projetos):
        projetos.pop(idx)
        save_projetos(projetos)
        return jsonify({"ok": True})
    return jsonify({"ok": False, "msg": "Projeto não encontrado."}), 404


@app.route("/ponto")
def ponto_view():
    return render_template("ponto.html")


@app.route("/api/csv_info")
def api_csv_info():
    if not CSV_PATH:
        return jsonify({"ok": False, "msg": "CSV não encontrado."})
    bens = load_bens()
    try:
        st = os.stat(CSV_PATH)
        mod = datetime.fromtimestamp(st.st_mtime).strftime("%d/%m/%Y %H:%M:%S")
        tam = round(st.st_size / 1024, 1)
    except OSError:
        app.logger.exception("Não foi possível consultar os metadados do CSV do inventário.")
        return jsonify({"ok": False, "msg": "Não foi possível ler os metadados do CSV."}), 500
    return jsonify({"ok": True, "caminho": CSV_PATH, "registros": len(bens),
                    "tamanho_kb": tam, "modificado_em": mod})


@app.route("/api/alertas_ferias")
def api_alertas_ferias():
    ferias = load_ferias()
    hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    alertas_retorno = []
    alertas_bloqueio = []

    for f in ferias:
        status = (f.get("status") or "").strip()
        if status in ("Concluído", "Cancelado"):
            continue

        try:
            ini = datetime.strptime(f.get("inicio", ""), "%Y-%m-%d")
            fim = datetime.strptime(f.get("fim", ""), "%Y-%m-%d")
        except Exception:
            continue

        nome = f.get("nome", "—")

        if ini <= hoje <= fim:
            dias = (fim - hoje).days
            if dias <= 7:
                alertas_retorno.append({
                    "nome": nome,
                    "data": fim.strftime("%d/%m/%Y"),
                    "dias": dias,
                })

        if status == "Férias não iniciada" or (hoje < ini):
            dias = (ini - hoje).days
            if dias == 1:
                alertas_bloqueio.append({
                    "nome": nome,
                    "data": ini.strftime("%d/%m/%Y"),
                })

    conflitos_ramais = [
        {
            "nome": pessoa["nome"],
            "ramais": pessoa["ramais"],
            "departamento": pessoa["departamento"],
        }
        for pessoa in _listar_ramais(load_bens(), set())
        if pessoa["conflito"]
    ]

    return jsonify({
        "ok": True,
        "retorno": alertas_retorno,
        "bloqueio": alertas_bloqueio,
        "conflitos_ramais": conflitos_ramais,
        "total": (
            len(alertas_retorno)
            + len(alertas_bloqueio)
            + len(conflitos_ramais)
        ),
    })


@app.route("/api/rodar_alertas/<token>", methods=["GET"])
def api_rodar_alertas_cron(token):
    token_configurado = os.environ.get("ALERTAS_CRON_TOKEN", "").strip()
    if not token_configurado:
        caminho_token = os.path.join(DADOS, "alertas_cron_token")
        try:
            with open(caminho_token, encoding="utf-8") as arquivo:
                token_configurado = arquivo.read().strip()
        except FileNotFoundError:
            app.logger.error(
                "Execução do cron de alertas recusada: token não configurado."
            )
            return jsonify({
                "ok": False,
                "msg": "Execução automática indisponível: token não configurado.",
            }), 503
        except OSError:
            app.logger.exception(
                "Não foi possível ler o token local do cron de alertas."
            )
            return jsonify({
                "ok": False,
                "msg": "Execução automática indisponível.",
            }), 500

    if not token_configurado or not secrets.compare_digest(token, token_configurado):
        app.logger.warning("Tentativa não autorizada de executar o cron de alertas.")
        return jsonify({"ok": False, "msg": "Token inválido."}), 403

    try:
        import enviar_alertas

        enviar_alertas.main()
    except Exception:
        app.logger.exception("Falha ao executar a rotina automática de alertas.")
        return jsonify({
            "ok": False,
            "msg": "Falha ao executar os alertas automáticos.",
        }), 500

    return jsonify({"ok": True, "msg": "Rotina de alertas executada."})


@app.route("/configuracoes")
def configuracoes_view():
    cfg = email_sender.carregar_config()
    return render_template(
        "configuracoes.html",
        cfg=cfg,
        status_bens=carregar_status_bens(),
        status_em_uso=sorted({
            normalizar(b.get("status"))
            for b in _csv_carregar_raw()
            if normalizar(b.get("status"))
        }, key=str.casefold),
    )


@app.route("/api/admin/status/salvar", methods=["POST"])
def api_admin_status_salvar():
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict) or not isinstance(dados.get("status"), list):
        return jsonify({"ok": False, "msg": "Informe uma lista de status válida."}), 400
    status = dados["status"]
    if any(not isinstance(valor, str) for valor in status):
        return jsonify({"ok": False, "msg": "Cada status deve ser texto."}), 400
    normalizados = [normalizar(valor) for valor in status]
    normalizados = [valor for valor in normalizados if valor]
    if any(len(valor) > 40 for valor in normalizados) or len(normalizados) > 50:
        return jsonify({"ok": False, "msg": "Limite de 50 status, com até 40 caracteres cada."}), 400
    unicos = {}
    for valor in normalizados:
        unicos.setdefault(valor.casefold(), valor)
    status_salvos = list(unicos.values())
    em_uso = {
        normalizar(b.get("status")).casefold(): normalizar(b.get("status"))
        for b in _csv_carregar_raw()
        if normalizar(b.get("status"))
    }
    removidos_em_uso = [nome for chave, nome in em_uso.items() if chave not in unicos]
    if removidos_em_uso:
        return jsonify({
            "ok": False,
            "msg": "Não é possível remover status ainda usado por bens: "
                   + ", ".join(sorted(removidos_em_uso, key=str.casefold)),
        }), 400
    _save(ARQ_STATUS_BENS, status_salvos)
    return jsonify({"ok": True, "msg": "Lista de status salva."})


@app.route("/api/configuracoes_email/salvar", methods=["POST"])
def api_config_email_salvar():
    d = request.get_json(silent=True)
    if not isinstance(d, dict):
        return jsonify({"ok": False, "msg": "Configuração inválida."}), 400
    booleanos = (
        "ativo", "smtp_tls", "enviar_ferias",
        "enviar_inicio_ferias", "enviar_relatorio",
    )
    textos = (
        "smtp_host", "smtp_user", "smtp_pass", "remetente_nome",
        "destinatarios_ferias", "destinatarios_relatorio",
    )
    if any(not isinstance(d.get(campo), bool) for campo in booleanos):
        return jsonify({"ok": False, "msg": "Opções de e-mail inválidas."}), 400
    if any(
        campo in d and not isinstance(d[campo], str)
        for campo in textos
    ):
        return jsonify({"ok": False, "msg": "Campos de configuração inválidos."}), 400
    try:
        porta = int(d.get("smtp_port") or 587)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "msg": "A porta SMTP deve ser um número."}), 400
    if not 1 <= porta <= 65535:
        return jsonify({"ok": False, "msg": "A porta SMTP deve estar entre 1 e 65535."}), 400

    destinatarios_ferias = [
        item.strip() for item in d.get("destinatarios_ferias", "").split(",")
        if item.strip()
    ]
    destinatarios_relatorio = [
        item.strip() for item in d.get("destinatarios_relatorio", "").split(",")
        if item.strip()
    ]
    for destinatarios in (destinatarios_ferias, destinatarios_relatorio):
        if destinatarios and not email_sender.destinatarios_validos(destinatarios):
            return jsonify({"ok": False, "msg": "Revise os endereços de e-mail informados."}), 400
    if d["ativo"] and not d.get("smtp_host", "").strip():
        return jsonify({"ok": False, "msg": "Informe o servidor SMTP."}), 400
    if d.get("smtp_pass") and not isinstance(d.get("smtp_pass"), str):
        return jsonify({"ok": False, "msg": "Senha SMTP inválida."}), 400

    cfg = email_sender.carregar_config()
    cfg.update({
        "ativo": d["ativo"],
        "smtp_host": d.get("smtp_host", "").strip(),
        "smtp_port": porta,
        "smtp_user": d.get("smtp_user", "").strip(),
        "smtp_tls": d["smtp_tls"],
        "remetente_nome": d.get("remetente_nome", "").strip(),
        "destinatarios_ferias": destinatarios_ferias,
        "destinatarios_relatorio": destinatarios_relatorio,
        "enviar_ferias": d["enviar_ferias"],
        "enviar_inicio_ferias": d["enviar_inicio_ferias"],
        "enviar_relatorio": d["enviar_relatorio"],
    })
    if d.get("smtp_pass"):
        cfg["smtp_pass"] = email_sender.limpar_senha(d["smtp_pass"])
    email_sender.salvar_config(cfg)
    return jsonify({"ok": True, "msg": "Configurações salvas!"})


@app.route("/api/configuracoes_email/testar", methods=["POST"])
def api_config_email_testar():
    d = request.get_json(silent=True)
    if not isinstance(d, dict):
        return jsonify({"ok": False, "msg": "Solicitação inválida."}), 400
    cfg = email_sender.carregar_config()
    destinatarios = d.get("destinatarios") or cfg.get("destinatarios_ferias") or []
    if isinstance(destinatarios, str):
        destinatarios = [x.strip() for x in destinatarios.split(",") if x.strip()]
    if not email_sender.destinatarios_validos(destinatarios):
        return jsonify({"ok": False, "msg": "Informe endereços de e-mail válidos."}), 400
    corpo = """
    <div style="font-family:Arial,sans-serif; max-width:600px; margin:0 auto;">
        <div style="background:#1a2a4a; color:white; padding:20px; border-radius:8px 8px 0 0;">
            <h2 style="margin:0;">Teste de E-mail</h2>
        </div>
        <div style="padding:20px; background:#fff; border:1px solid #e2e8f0; border-top:none;">
            <p>Se você recebeu este e-mail, o SMTP está configurado corretamente!</p>
            <p style="color:#64748b; font-size:13px;">Enviado em: {}</p>
        </div>
    </div>
    """.format(datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    ok, msg = email_sender.enviar_email(
        destinatarios, "[TI] Teste de configuração", corpo, tipo="teste")
    return jsonify({"ok": ok, "msg": msg})


@app.route("/api/ramais_agrupados")
def api_ramais_agrupados():
    bens = load_bens()
    chaves_ferias = ferias_ativas_chaves()

    grupos = defaultdict(lambda: {})
    vistos = defaultdict(set)
    for b in bens:
        ramal = (b.get("ramal") or "").strip()
        dep = (b.get("departamento") or "Sem Departamento").strip()
        resp = normalizar(b.get("responsavel") or "")
        if not ramal or not resp:
            continue
        chave = norm_nome(resp)
        if chave in vistos[(dep, ramal)]:
            continue
        vistos[(dep, ramal)].add(chave)

        if ramal not in grupos[dep]:
            grupos[dep][ramal] = []
        grupos[dep][ramal].append(resp)

    PRIORIDADE = [
        "Diretor Executivo", "Diretor Administrativo", "Secretaria de Diretoria",
        "Recepção", "Copa", "Portaria", "Sala de Reunião",
    ]

    def _ordem(dep):
        try:
            return PRIORIDADE.index(dep)
        except ValueError:
            return 999

    departamentos = []
    for dep, ramais_dict in grupos.items():
        lista = []
        for ramal, responsaveis in sorted(ramais_dict.items(), key=lambda x: x[0]):
            nomes = []
            em_ferias = False
            for r in responsaveis:
                ferias_flag = _nome_em_ferias(r, chaves_ferias)
                if ferias_flag:
                    em_ferias = True
                nomes.append({"nome": r, "ferias": ferias_flag})
            lista.append({"ramal": ramal, "responsaveis": nomes,
                          "em_ferias": em_ferias})
        departamentos.append({
            "nome": dep,
            "prioridade": _ordem(dep),
            "ramais": lista,
            "total": len(lista),
        })

    departamentos.sort(key=lambda x: (x["prioridade"], x["nome"]))
    return jsonify({
        "ok": True,
        "departamentos": departamentos,
        "total": sum(d["total"] for d in departamentos),
    })


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = (request.form.get("usuario") or "").strip()
        senha = request.form.get("senha") or ""
        u = mod_usuarios.autenticar(usuario, senha)
        if u:
            session.clear()
            session["usuario"] = u["usuario"]
            session["nome"] = u["nome"]
            session["tipo"] = u["tipo"]
            return perfil_home()
        return render_template("login.html", erro="Usuário ou senha incorretos.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/recepcao")
def recepcao_view():
    pessoas = _pessoas_agrupadas()
    registros = []
    for p in pessoas:
        r = {
            "nome": p["nome"],
            "cargo": p["cargo"],
            "departamento": p["departamento"],
            "ramal": p["ramal"],
            "em_ferias": p["em_ferias"],
        }
        r["busca"] = f'{r["nome"]} {r["cargo"]} {r["departamento"]} {r["ramal"]}'
        registros.append(r)
    registros.sort(key=lambda x: x["nome"].lower())

    ferias_ativas = ferias_em_andamento_lista()

    return render_template("recepcao.html",
                           registros=registros,
                           total=len(registros),
                           ferias_ativas=ferias_ativas,
                           total_ferias=len(ferias_ativas))


@app.route("/usuarios")
def usuarios_view():
    if not tem_permissao("usuarios.ver"):
        return _negar_acesso()
    lista = mod_usuarios.listar()
    return render_template(
        "usuarios.html",
        usuarios=lista,
        usuario_atual=session.get("usuario", ""),
        perfis=permissoes.listar_perfis(),
        permissoes_disponiveis=permissoes.PERMISSOES,
        acoes_por_recurso=permissoes.ACOES_POR_RECURSO,
    )


@app.route("/api/admin/trocar_senha", methods=["POST"])
def api_admin_trocar_senha():
    if not tem_permissao("usuarios.editar"):
        return jsonify({"ok": False, "msg": "Acesso negado"}), 403
    d = request.get_json(force=True, silent=True) or {}
    usuario = (d.get("usuario") or "").strip()
    nova = (d.get("nova_senha") or "").strip()
    if not usuario or not nova:
        return jsonify({"ok": False, "msg": "Preencha usuário e nova senha"})
    if len(nova) < 6:
        return jsonify({"ok": False, "msg": "Senha deve ter ao menos 6 caracteres"})
    ok = mod_usuarios.resetar_senha(usuario, nova)
    if not ok:
        return jsonify({"ok": False, "msg": "Usuário não encontrado"})
    return jsonify({"ok": True,
                    "msg": f"Senha de '{usuario}' alterada com sucesso!"})


@app.route("/api/admin/usuarios/criar", methods=["POST"])
def api_admin_usuario_criar():
    if not tem_permissao("usuarios.editar"):
        return jsonify({"ok": False, "msg": "Acesso negado"}), 403
    d = request.get_json(silent=True)
    if not isinstance(d, dict):
        return jsonify({"ok": False, "msg": "Dados de usuário inválidos."}), 400
    usuario = d.get("usuario") if isinstance(d.get("usuario"), str) else ""
    nome = d.get("nome") if isinstance(d.get("nome"), str) else ""
    tipo = d.get("tipo") if isinstance(d.get("tipo"), str) else ""
    senha = d.get("senha") if isinstance(d.get("senha"), str) else ""
    ok, msg = mod_usuarios.criar_usuario(usuario, nome, tipo, senha)
    return jsonify({"ok": ok, "msg": msg}), (200 if ok else 400)


@app.route("/api/admin/usuarios/excluir", methods=["POST"])
def api_admin_usuario_excluir():
    if not tem_permissao("usuarios.editar"):
        return jsonify({"ok": False, "msg": "Acesso negado"}), 403
    d = request.get_json(silent=True)
    if not isinstance(d, dict):
        return jsonify({"ok": False, "msg": "Dados de usuário inválidos."}), 400
    usuario = d.get("usuario") if isinstance(d.get("usuario"), str) else ""
    usuario = usuario.strip()
    if usuario.casefold() == str(session.get("usuario", "")).casefold():
        return jsonify({"ok": False, "msg": "Não é possível excluir a própria conta em uso."}), 400
    ok, msg = mod_usuarios.excluir_usuario(usuario)
    return jsonify({"ok": ok, "msg": msg}), (200 if ok else 400)


@app.route("/api/admin/usuarios/perfil", methods=["POST"])
def api_admin_usuario_perfil():
    if not tem_permissao("usuarios.editar"):
        return jsonify({"ok": False, "msg": "Acesso negado"}), 403
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        return jsonify({"ok": False, "msg": "Dados inválidos."}), 400
    usuario = dados.get("usuario")
    perfil_id = dados.get("perfil")
    if not isinstance(usuario, str) or not isinstance(perfil_id, str):
        return jsonify({"ok": False, "msg": "Usuário ou perfil inválido."}), 400
    if usuario.casefold() == str(session.get("usuario", "")).casefold():
        return jsonify({"ok": False, "msg": "Não é possível alterar o próprio perfil em uso."}), 400
    ok, msg = mod_usuarios.alterar_perfil_usuario(usuario, perfil_id)
    return jsonify({"ok": ok, "msg": msg}), (200 if ok else 400)


@app.route("/api/admin/perfis/salvar", methods=["POST"])
def api_admin_perfil_salvar():
    if not tem_permissao("usuarios.editar"):
        return jsonify({"ok": False, "msg": "Acesso negado"}), 403
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        return jsonify({"ok": False, "msg": "Dados de perfil inválidos."}), 400
    perfil_id = dados.get("id")
    nome = dados.get("nome")
    lista_permissoes = dados.get("permissoes")
    if (
        (perfil_id is not None and not isinstance(perfil_id, str))
        or not isinstance(nome, str)
        or not isinstance(lista_permissoes, list)
    ):
        return jsonify({"ok": False, "msg": "Dados de perfil inválidos."}), 400
    ok, msg = permissoes.salvar_perfil(perfil_id or "", nome, lista_permissoes)
    return jsonify({"ok": ok, "msg": msg}), (200 if ok else 400)


@app.route("/api/admin/perfis/excluir", methods=["POST"])
def api_admin_perfil_excluir():
    if not tem_permissao("usuarios.editar"):
        return jsonify({"ok": False, "msg": "Acesso negado"}), 403
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict) or not isinstance(dados.get("id"), str):
        return jsonify({"ok": False, "msg": "Perfil inválido."}), 400
    perfis_em_uso = {
        usuario.get("tipo") for usuario in mod_usuarios.carregar_usuarios()
    }
    ok, msg = permissoes.excluir_perfil(dados["id"], perfis_em_uso)
    return jsonify({"ok": ok, "msg": msg}), (200 if ok else 400)


if __name__ == "__main__":
    print("\n" + "=" * 60)
    if CSV_PATH:
        print("  CSV fonte: " + CSV_PATH)
    else:
        print("  AVISO: CSV nao encontrado. Coloque Levantamento*.csv em:\n     " +
              BASE_DIR + "  ou  " + os.path.dirname(BASE_DIR))
    print("=" * 60)
    print("\n  Servidor rodando em: http://localhost:5000\n")
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)