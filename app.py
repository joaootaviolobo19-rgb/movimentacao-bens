# -*- coding: utf-8 -*-
import email_sender
import usuarios as mod_usuarios
import unicodedata
import os
import json
import csv
import re
import glob
import shutil
from datetime import datetime
from collections import defaultdict, Counter
from flask import (Flask, render_template, request, jsonify, send_file,
                   session, redirect, url_for)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DADOS = os.path.join(BASE_DIR, "dados")
os.makedirs(DADOS, exist_ok=True)

app = Flask(__name__)
app.secret_key = "ti-inventario-2026"


ROTAS_RECEPCAO = {
    "/recepcao",
    "/logout",
    "/api/alertas_ferias",
}


@app.before_request
def verificar_acesso():
    # Rotas livres (sem login)
    if request.path.startswith("/static") or request.path in ("/login", "/logout"):
        return None

    # Rota do cron — protegida por token na URL, não precisa de sessão
    if request.path.startswith("/api/rodar_alertas/"):
        return None

    if "usuario" not in session:
        return redirect(url_for("login"))

    if session.get("tipo") == "recepcao":
        if request.path not in ROTAS_RECEPCAO and not request.path.startswith("/api/"):
            return redirect(url_for("recepcao_view"))

    return None


ARQ_BENS = os.path.join(DADOS, "bens.json")
ARQ_FUNC = os.path.join(DADOS, "funcionarios.json")
ARQ_DEP = os.path.join(DADOS, "departamentos.json")
ARQ_MOV = os.path.join(DADOS, "movimentacoes.csv")
ARQ_FER = os.path.join(DADOS, "ferias.json")
ARQ_PROJ = os.path.join(DADOS, "projetos.json")

DELIMITER = ";"
BACKUP_DIR = os.path.join(BASE_DIR, "_backup_csv")
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
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome = os.path.basename(CSV_PATH)
    try:
        shutil.copy2(CSV_PATH, os.path.join(BACKUP_DIR, ts + "__" + nome))
    except Exception as e:
        print("[csv] Aviso backup:", e)


def _csv_carregar():
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
            next(reader)
        except StopIteration:
            return []
        for raw in reader:
            if not any((c or "").strip() for c in raw):
                continue
            raw = list(raw) + [""] * (len(COLS) - len(raw))
            raw = raw[:len(COLS)]
            item = {}
            for i, (_, campo) in enumerate(COLS):
                item[campo] = (raw[i] or "").strip()
            bens.append(item)
    for i, b in enumerate(bens, start=1):
        b["id"] = i
    return bens


def _csv_salvar(bens):
    if not CSV_PATH:
        raise RuntimeError("CSV do Levantamento não encontrado.")
    enc = _detectar_encoding(CSV_PATH)
    _backup_csv()
    with open(CSV_PATH, "w", encoding=enc, newline="") as f:
        w = csv.writer(f, delimiter=DELIMITER)
        w.writerow([c[0] for c in COLS])
        for b in bens:
            w.writerow([b.get(campo, "") or "" for _, campo in COLS])


def _load(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8-sig") as f:
        try:
            return json.load(f)
        except Exception:
            return default


def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_bens(): return _csv_carregar()


def save_bens(lista):
    _csv_salvar(lista)
    try:
        _save(ARQ_BENS, lista)
    except Exception:
        pass


def load_funcs(): return _load(ARQ_FUNC, [])
def load_deps(): return _load(ARQ_DEP, [])
def save_funcs(d): _save(ARQ_FUNC, d)
def load_ferias(): return _load(ARQ_FER, [])
def save_ferias(d): _save(ARQ_FER, d)
def load_projetos(): return _load(ARQ_PROJ, [])
def save_projetos(d): _save(ARQ_PROJ, d)


def next_id(lista):
    return (max([x.get("id", 0) for x in lista]) + 1) if lista else 1


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


def norm_depto(s):
    if not s:
        return ""
    n = norm_nome(s).lower().strip()
    return DEPTO_SINONIMOS.get(n, n)


def _partes_nome(nome):
    """Retorna (primeiro, ultimo) normalizados."""
    p = norm_nome(nome).split()
    if not p:
        return None, None
    return p[0], (p[-1] if len(p) > 1 else p[0])


# ============================================================
# FÉRIAS
# ============================================================

def ferias_ativas_set():
    """Set de nomes completos normalizados em férias hoje."""
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
    """Set de (1º nome, último nome) de quem está de férias hoje."""
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
    """Verifica se 'nome' bate com alguma chave (1º + último) de férias."""
    if not nome:
        return False
    partes = norm_nome(nome).split()
    if not partes:
        return False
    primeiro = partes[0]
    ultimo = partes[-1] if len(partes) > 1 else partes[0]
    return (primeiro, ultimo) in chaves


def ferias_em_andamento_lista():
    """Retorna lista enriquecida SÓ das férias em andamento hoje (lê ferias.json).
       Usada na aba 'Em férias' da Recepção."""
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
# AGRUPAMENTO AUTOMÁTICO DE PESSOAS
# ============================================================

def _pessoas_agrupadas():
    """
    Une bens + funcionários por pessoa aplicando 2 regras (a Regra 3 foi REMOVIDA):
      1) nome completo exato igual
      2) mesmo (1º + último) e (um sem depto OU mesmo depto)
    """
    bens = load_bens()
    funcs = load_funcs()

    registros = []
    for b in bens:
        nome = normalizar(b.get("responsavel") or "")
        if not nome:
            continue
        registros.append({
            "nome": nome,
            "departamento": (b.get("departamento") or "").strip(),
            "ramal": (b.get("ramal") or "").strip(),
            "cargo": "",
            "bens": [b],
        })
    for f in funcs:
        nome = normalizar(f.get("nome") or "")
        if not nome:
            continue
        registros.append({
            "nome": nome,
            "departamento": (f.get("setor") or "").strip(),
            "ramal": "",
            "cargo": (f.get("cargo") or "").strip(),
            "bens": [],
        })

    n = len(registros)
    if n == 0:
        return []

    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    def dep_norm(r):
        return norm_depto(r.get("departamento") or "")

    # -------- Regra 1: nome completo EXATO igual --------
    por_nome = defaultdict(list)
    for i, r in enumerate(registros):
        por_nome[norm_nome(r["nome"])].append(i)
    for idxs in por_nome.values():
        for i in idxs[1:]:
            union(idxs[0], i)

    # -------- Regra 2: (1º + último) iguais + depto compatível --------
    por_1o_ult = defaultdict(list)
    for i, r in enumerate(registros):
        p1, pu = _partes_nome(r["nome"])
        if p1:
            por_1o_ult[(p1, pu)].append(i)

    for idxs in por_1o_ult.values():
        if len(idxs) < 2:
            continue
        por_dep = defaultdict(list)
        sem_dep = []
        for i in idxs:
            d = dep_norm(registros[i])
            if d:
                por_dep[d].append(i)
            else:
                sem_dep.append(i)

        if len(por_dep) <= 1:
            for i in idxs[1:]:
                union(idxs[0], i)
        else:
            if sem_dep and por_dep:
                maior = max(por_dep.items(), key=lambda x: len(x[1]))[0]
                por_dep[maior].extend(sem_dep)
            for grupo in por_dep.values():
                for i in grupo[1:]:
                    union(grupo[0], i)

    # (Regra 3 REMOVIDA — causava falsos positivos como Gerson)

    # -------- Consolida --------
    grupos = defaultdict(list)
    for i in range(n):
        grupos[find(i)].append(registros[i])

    chaves_ferias = ferias_ativas_chaves()
    resultado = []

    for grupo in grupos.values():
        nome_final = max((g["nome"] for g in grupo), key=len, default="")

        cargo_final = ""
        for g in sorted(grupo, key=lambda x: -len(x["nome"])):
            if g["cargo"]:
                cargo_final = g["cargo"]
                break

        deps = Counter()
        for g in grupo:
            d = (g["departamento"] or "").strip()
            if d:
                deps[d] += 1
        depto_final = deps.most_common(1)[0][0] if deps else ""

        ramal_final = ""
        for g in grupo:
            if g["ramal"]:
                ramal_final = g["ramal"]
                break

        todos_bens = []
        for g in grupo:
            todos_bens.extend(g["bens"])

        em_ferias = False
        for g in grupo:
            if _nome_em_ferias(g["nome"], chaves_ferias):
                em_ferias = True
                break

        resultado.append({
            "nome": nome_final,
            "cargo": cargo_final,
            "departamento": depto_final,
            "ramal": ramal_final,
            "em_ferias": em_ferias,
            "bens": todos_bens,
        })

    return resultado


CABECALHO_MOV = ["data", "bem_id", "categoria", "patrimonio", "hostname",
                 "de_responsavel", "para_responsavel", "de_departamento",
                 "para_departamento", "obs"]


def registrar_movimento(b, de_resp, de_dep, para_resp, para_dep, obs):
    existe = os.path.exists(ARQ_MOV)
    with open(ARQ_MOV, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if not existe:
            w.writerow(CABECALHO_MOV)
        w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M"), b.get("id"),
                    b.get("categoria"), b.get("patrimonio"), b.get("hostname"),
                    de_resp, para_resp, de_dep, para_dep, obs])


def agrupar_por_funcionario():
    pessoas = _pessoas_agrupadas()
    teia = []
    for p in pessoas:
        if not p["bens"]:
            continue
        cats = defaultdict(int)
        for it in p["bens"]:
            cats[it.get("categoria") or "Outros"] += 1
        teia.append({
            "nome": p["nome"],
            "cargo": p["cargo"],
            "setor": p["departamento"],
            "total": len(p["bens"]),
            "por_categoria": dict(sorted(cats.items(), key=lambda x: -x[1])),
            "bens": p["bens"],
        })
    teia.sort(key=lambda x: (-x["total"], x["nome"]))
    return teia


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
    return dict(progresso_ferias=progresso_ferias)


# ============================================================
# ROTAS
# ============================================================

@app.route("/")
def dashboard():
    if session.get("tipo") == "recepcao":
        return redirect(url_for("recepcao_view"))
    bens = load_bens()
    funcs = load_funcs()
    deps = load_deps()
    por_status = defaultdict(int)
    com_resp = sem_resp = 0
    for b in bens:
        por_status[b.get("status") or "Nao informado"] += 1
        if normalizar(b.get("responsavel")):
            com_resp += 1
        else:
            sem_resp += 1
    tot_mov = 0
    if os.path.exists(ARQ_MOV):
        with open(ARQ_MOV, encoding="utf-8") as f:
            tot_mov = max(0, sum(1 for _ in f) - 1)
    graf = _dados_graficos()
    return render_template(
        "dashboard.html",
        total=len(bens),
        total_func=len(_pessoas_agrupadas()),
        total_dep=len(deps),
        com_responsavel=com_resp,
        sem_responsavel=sem_resp,
        total_mov=tot_mov,
        por_status=dict(por_status),
        graf=graf,
    )


@app.route("/bens")
def bens_view():
    bens = load_bens()
    todos = load_bens()
    q = (request.args.get("q") or "").lower()
    cat = request.args.get("cat") or ""
    dep = request.args.get("dep") or ""
    resp = request.args.get("resp") or ""
    if q:
        bens = [b for b in bens if q in json.dumps(
            b, ensure_ascii=False).lower()]
    if cat:
        bens = [b for b in bens if (b.get("categoria") or "") == cat]
    if dep:
        bens = [b for b in bens if (b.get("departamento") or "") == dep]
    if resp:
        bens = [b for b in bens if normalizar(b.get("responsavel")) == resp]
    return render_template(
        "bens.html",
        bens=bens,
        categorias=sorted({b.get("categoria")
                          for b in todos if b.get("categoria")}),
        departamentos=sorted({b.get("departamento")
                             for b in todos if b.get("departamento")}),
        responsaveis=sorted({normalizar(b.get("responsavel"))
                            for b in todos if b.get("responsavel")}),
        filtros={"q": q, "cat": cat, "dep": dep, "resp": resp},
    )


@app.route("/bens/salvar", methods=["POST"])
def bens_salvar():
    d = request.json or {}
    bens = load_bens()
    campos = ["categoria", "modelo", "hostname", "patrimonio", "departamento",
              "responsavel", "marca", "serial", "ramal", "ip", "observacao",
              "cpu", "disco", "ram", "iso", "status"]
    item = {k: normalizar(d.get(k)) for k in campos}
    bid = d.get("id")
    if bid:
        for i, b in enumerate(bens):
            if b.get("id") == bid:
                bens[i] = {**b, **item,
                           "atualizado_em": datetime.now().isoformat()}
                break
        msg = "Bem atualizado!"
    else:
        item["id"] = next_id(bens)
        item["criado_em"] = datetime.now().isoformat()
        bens.append(item)
        msg = "Bem cadastrado!"
    save_bens(bens)
    return jsonify({"ok": True, "msg": msg})


@app.route("/bens/excluir/<int:bid>", methods=["POST"])
def bens_excluir(bid):
    save_bens([b for b in load_bens() if b.get("id") != bid])
    return jsonify({"ok": True})


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
    return render_template("planilha.html", bens=bens, cats=cats, deps=deps,
                           total=len(bens))


@app.route("/api/bens/celula", methods=["POST"])
def api_bens_celula():
    d = request.get_json(force=True, silent=True) or {}
    bid = d.get("id")
    campo = (d.get("campo") or "").strip()
    valor = (d.get("valor") or "").strip()
    if bid is None or not campo:
        return jsonify({"ok": False, "msg": "Faltando id/campo"})
    CAMPOS_PERMITIDOS = {"categoria", "modelo", "hostname", "patrimonio",
                         "departamento", "responsavel", "marca", "serial",
                         "ramal", "ip", "observacao", "cpu", "disco", "ram",
                         "iso", "status"}
    if campo not in CAMPOS_PERMITIDOS:
        return jsonify({"ok": False, "msg": "Campo nao editavel"})
    bens = load_bens()
    achou = False
    for b in bens:
        if b.get("id") == bid:
            b[campo] = valor
            b["atualizado_em"] = datetime.now().isoformat()
            achou = True
            break
    if not achou:
        return jsonify({"ok": False, "msg": "Bem nao encontrado"})
    save_bens(bens)
    return jsonify({"ok": True, "valor": valor})


@app.route("/api/bens/planilha_lote", methods=["POST"])
def api_bens_planilha_lote():
    d = request.get_json(force=True, silent=True) or {}
    edicoes = d.get("edicoes") or []
    if not edicoes:
        return jsonify({"ok": True, "aplicadas": 0})
    bens = load_bens()
    por_id = {b.get("id"): b for b in bens}
    aplicadas = 0
    for e in edicoes:
        b = por_id.get(e.get("id"))
        if not b:
            continue
        b[e.get("campo")] = (e.get("valor") or "").strip()
        b["atualizado_em"] = datetime.now().isoformat()
        aplicadas += 1
    save_bens(bens)
    return jsonify({"ok": True, "aplicadas": aplicadas})


@app.route("/funcionarios")
def funcionarios_view():
    pessoas = _pessoas_agrupadas()
    funcs_nomes = {norm_nome(f.get("nome") or "") for f in load_funcs()}
    resultado = []
    for p in pessoas:
        if norm_nome(p["nome"]) in funcs_nomes or any(
            norm_nome(g) in funcs_nomes for g in [p["nome"]]
        ):
            resultado.append({
                "nome": p["nome"],
                "cargo": p["cargo"],
                "setor": p["departamento"],
                "total_bens": len(p["bens"]),
            })
    resultado.sort(key=lambda x: x["nome"].lower())
    return render_template("funcionarios.html", funcionarios=resultado)


@app.route("/funcionarios/salvar", methods=["POST"])
def funcionarios_salvar():
    d = request.json or {}
    funcs = load_funcs()
    campos = ["nome", "cargo", "setor"]
    item = {k: normalizar(d.get(k)) for k in campos}
    if not item["nome"]:
        return jsonify({"ok": False, "msg": "Nome obrigatorio"})
    idx = d.get("idx")
    if idx is not None and 0 <= idx < len(funcs):
        funcs[idx] = {**funcs[idx], **item}
        msg = "Atualizado!"
    else:
        funcs.append(item)
        msg = "Cadastrado!"
    save_funcs(funcs)
    return jsonify({"ok": True, "msg": msg})


@app.route("/funcionarios/excluir/<int:idx>", methods=["POST"])
def funcionarios_excluir(idx):
    funcs = load_funcs()
    if 0 <= idx < len(funcs):
        funcs.pop(idx)
        save_funcs(funcs)
    return jsonify({"ok": True})


@app.route("/teia")
def teia_view():
    return render_template("teia.html", teia=agrupar_por_funcionario())


@app.route("/movimentar")
def movimentar_view():
    bens = load_bens()
    funcs = load_funcs()
    deps = load_deps()
    por_resp = defaultdict(list)
    for b in bens:
        r = normalizar(b.get("responsavel") or "") or "SEM RESPONSAVEL"
        por_resp[r].append(b)
    return render_template("movimentar.html", bens=bens, funcionarios=funcs,
                           departamentos=deps,
                           por_resp={k: v for k, v in por_resp.items()})


@app.route("/movimentar/registrar", methods=["POST"])
def movimentar_registrar():
    d = request.json or {}
    origem = normalizar(d.get("origem"))
    destino = normalizar(d.get("destino"))
    dep_dest = normalizar(d.get("departamento_destino"))
    obs = normalizar(d.get("obs"))
    ids = d.get("ids") or []
    if not origem or not destino or not ids:
        return jsonify({"ok": False, "msg": "Preencha origem, destino e selecione ao menos 1 bem."})
    bens = load_bens()
    registrados = 0
    for b in bens:
        if b.get("id") in ids:
            ar, ad = b.get("responsavel"), b.get("departamento")
            b["responsavel"] = destino
            if dep_dest:
                b["departamento"] = dep_dest
            b["atualizado_em"] = datetime.now().isoformat()
            registrar_movimento(b, ar, ad, b["responsavel"],
                                b["departamento"], obs)
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
        linhas = [l for l in linhas
                  if q in json.dumps(l, ensure_ascii=False).lower()]
    return render_template("movimentacoes.html",
                           movimentacoes=list(reversed(linhas)),
                           total=len(linhas), filtros={"q": q})


@app.route("/movimentacoes/exportar.csv")
def movimentacoes_exportar():
    if not os.path.exists(ARQ_MOV):
        return "Sem dados", 404
    return send_file(ARQ_MOV, mimetype="text/csv", as_attachment=True,
                     download_name="movimentacoes.csv")


# ============================================================
# FÉRIAS - VIEW COM STATUS CALCULADO
# ============================================================

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
    d = request.json or {}
    ferias = load_ferias()
    item = {
        "nome": normalizar(d.get("nome")),
        "inicio": normalizar(d.get("inicio")),
        "fim": normalizar(d.get("fim")),
        "status": normalizar(d.get("status")) or "Férias não iniciada",
        "obs": normalizar(d.get("obs")),
    }
    if not item["nome"] or not item["inicio"] or not item["fim"]:
        return jsonify({"ok": False, "msg": "Preencha nome, início e fim."})
    idx = d.get("idx")
    if idx is not None and 0 <= idx < len(ferias):
        ferias[idx] = {**ferias[idx], **item}
        msg = "Férias atualizadas!"
    else:
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


# ============================================================
# RAMAIS - CORRIGIDO (responsaveis como lista)
# ============================================================

@app.route("/ramais")
def ramais_view():
    """Monta lista de ramais a partir dos BENS brutos (não agrupados)."""
    bens = load_bens()
    chaves_ferias = ferias_ativas_chaves()

    mapa = {}
    for b in bens:
        ramal = (b.get("ramal") or "").strip()
        if not ramal:
            continue
        nome = normalizar(b.get("responsavel") or "")
        if not nome:
            continue
        dept = (b.get("departamento") or "").strip()
        chave = f"{norm_nome(nome)}|{ramal}"
        if chave in mapa:
            continue
        mapa[chave] = {
            "nome": nome,
            "ramal": ramal,
            "departamento": dept,
            "em_ferias": _nome_em_ferias(nome, chaves_ferias),
        }

    por_ramal = defaultdict(list)
    for item in mapa.values():
        por_ramal[item["ramal"]].append(item)

    ramais_lista = []
    for ramal, pessoas in sorted(por_ramal.items()):
        pessoas.sort(key=lambda x: x["nome"])
        departamento = pessoas[0]["departamento"] if pessoas else ""
        em_ferias = any(p["em_ferias"] for p in pessoas)
        ramais_lista.append({
            "ramal": ramal,
            "responsaveis": pessoas,
            "departamento": departamento,
            "em_ferias": em_ferias,
        })

    return render_template("ramais.html", ramais=ramais_lista,
                           total=len(ramais_lista))


@app.route("/projetos")
def projetos_view():
    projetos = load_projetos()
    return render_template("projetos.html", projetos=projetos)


@app.route("/projetos/salvar", methods=["POST"])
def projetos_salvar():
    d = request.json or {}
    projetos = load_projetos()
    item = {
        "nome": normalizar(d.get("nome")),
        "responsavel": normalizar(d.get("responsavel")),
        "prioridade": normalizar(d.get("prioridade")) or "Média",
        "progresso": int(d.get("progresso") or 0),
        "status": normalizar(d.get("status")) or "Em Andamento",
        "prazo": normalizar(d.get("prazo")),
    }
    if not item["nome"]:
        return jsonify({"ok": False, "msg": "Informe o nome do projeto."})
    idx = d.get("idx")
    if idx is not None and 0 <= idx < len(projetos):
        projetos[idx] = {**projetos[idx], **item}
        msg = "Projeto atualizado!"
    else:
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
    except Exception:
        mod, tam = "?", 0
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

    return jsonify({
        "ok": True,
        "retorno": alertas_retorno,
        "bloqueio": alertas_bloqueio,
        "total": len(alertas_retorno) + len(alertas_bloqueio),
    })


@app.route("/configuracoes")
def configuracoes_view():
    cfg = email_sender.carregar_config()
    return render_template("configuracoes.html", cfg=cfg)


@app.route("/api/configuracoes_email/salvar", methods=["POST"])
def api_config_email_salvar():
    d = request.get_json(force=True, silent=True) or {}
    cfg = email_sender.carregar_config()
    cfg.update({
        "ativo": bool(d.get("ativo")),
        "smtp_host": (d.get("smtp_host") or "").strip(),
        "smtp_port": int(d.get("smtp_port") or 587),
        "smtp_user": (d.get("smtp_user") or "").strip(),
        "smtp_tls": bool(d.get("smtp_tls")),
        "remetente_nome": (d.get("remetente_nome") or "").strip(),
        "destinatarios_ferias": [x.strip() for x in
                                 (d.get("destinatarios_ferias") or "").split(",") if x.strip()],
        "destinatarios_relatorio": [x.strip() for x in
                                    (d.get("destinatarios_relatorio") or "").split(",") if x.strip()],
        "enviar_ferias": bool(d.get("enviar_ferias")),
        "enviar_relatorio": bool(d.get("enviar_relatorio")),
    })
    if d.get("smtp_pass"):
        cfg["smtp_pass"] = email_sender.limpar_senha(d["smtp_pass"])
    email_sender.salvar_config(cfg)
    return jsonify({"ok": True, "msg": "Configurações salvas!"})


@app.route("/api/configuracoes_email/testar", methods=["POST"])
def api_config_email_testar():
    d = request.get_json(force=True, silent=True) or {}
    cfg = email_sender.carregar_config()
    destinatarios = d.get("destinatarios") or cfg.get(
        "destinatarios_ferias") or []
    if isinstance(destinatarios, str):
        destinatarios = [x.strip()
                         for x in destinatarios.split(",") if x.strip()]
    if not destinatarios:
        return jsonify({"ok": False, "msg": "Informe pelo menos 1 destinatário."})
    corpo = """
    <div style="font-family:Arial,sans-serif; max-width:600px; margin:0 auto;">
        <div style="background:#1a2a4a; color:white; padding:20px; border-radius:8px 8px 0 0;">
            <h2 style="margin:0;">✅ Teste de E-mail</h2>
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


@app.route("/api/rodar_alertas/<token>")
def api_rodar_alertas(token):
    TOKEN_SECRETO = "record-ti-2026-movimentacao-secreto"
    if token != TOKEN_SECRETO:
        return jsonify({"ok": False, "msg": "Token inválido"}), 403

    try:
        import enviar_alertas
        enviar_alertas.main()
        return jsonify({"ok": True, "msg": "Alertas executados!",
                        "hora": datetime.now().isoformat()})
    except Exception as e:
        return jsonify({"ok": False, "msg": f"Erro: {e}"}), 500


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
        chave = f"{norm_nome(resp)}"
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
            session["usuario"] = u["usuario"]
            session["nome"] = u["nome"]
            session["tipo"] = u["tipo"]
            if u["tipo"] == "recepcao":
                return redirect(url_for("recepcao_view"))
            return redirect(url_for("dashboard"))
        return render_template("login.html", erro="Usuário ou senha incorretos.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/api/trocar_senha", methods=["POST"])
def api_trocar_senha():
    if "usuario" not in session:
        return jsonify({"ok": False, "msg": "Não autenticado"}), 401
    d = request.get_json(force=True, silent=True) or {}
    senha_atual = (d.get("senha_atual") or "").strip()
    senha_nova = (d.get("senha_nova") or "").strip()
    confirmar = (d.get("confirmar") or "").strip()

    if not senha_atual or not senha_nova:
        return jsonify({"ok": False, "msg": "Preencha todos os campos"})
    if senha_nova != confirmar:
        return jsonify({"ok": False, "msg": "As senhas não coincidem"})
    if len(senha_nova) < 6:
        return jsonify({"ok": False, "msg": "Senha deve ter ao menos 6 caracteres"})

    usuario = session["usuario"]
    u = mod_usuarios.autenticar(usuario, senha_atual)
    if not u:
        return jsonify({"ok": False, "msg": "Senha atual incorreta"})

    mod_usuarios.trocar_senha(usuario, senha_nova)
    return jsonify({"ok": True, "msg": "Senha alterada com sucesso!"})


@app.route("/recepcao")
def recepcao_view():
    """Rende duas abas: Colaboradores (agrupados) e Em férias (lê ferias.json)."""
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
    if session.get("tipo") != "admin":
        return redirect(url_for("dashboard"))
    lista = mod_usuarios.listar()
    return render_template("usuarios.html", usuarios=lista)


@app.route("/api/admin/trocar_senha", methods=["POST"])
def api_admin_trocar_senha():
    if session.get("tipo") != "admin":
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
