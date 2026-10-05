# -*- coding: utf-8 -*-
import os, json, csv, re, glob, shutil
from datetime import datetime
from collections import defaultdict
from flask import Flask, render_template, request, jsonify, send_file

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DADOS = os.path.join(BASE_DIR, "dados")
os.makedirs(DADOS, exist_ok=True)

app = Flask(__name__)
app.secret_key = "ti-inventario-2026"

ARQ_BENS = os.path.join(DADOS, "bens.json")
ARQ_FUNC = os.path.join(DADOS, "funcionarios.json")
ARQ_DEP  = os.path.join(DADOS, "departamentos.json")
ARQ_MOV  = os.path.join(DADOS, "movimentacoes.csv")

DELIMITER = ";"
BACKUP_DIR = os.path.join(BASE_DIR, "_backup_csv")
os.makedirs(BACKUP_DIR, exist_ok=True)

COLS = [
    ("Categoria", "categoria"), ("Modelo", "modelo"), ("Hostname", "hostname"),
    ("Patrimônio", "patrimonio"), ("Departamento", "departamento"), ("Responsável", "responsavel"),
    ("Marca", "marca"), ("Serial", "serial"), ("Ramal", "ramal"), ("IP", "ip"),
    ("Observação", "observacao"), ("CPU", "cpu"), ("Disco", "disco"), ("RAM", "ram"),
    ("ISO", "iso"), ("Status", "status"), ("Chave de auditoria", "_auditoria"),
    ("VERIFICAÇÃO", "_verificacao"), ("Departamento", "_depto_extra"),
]

def _achar_csv():
    for p in [os.path.join(BASE_DIR, "Levantamento*.csv"), os.path.join(BASE_DIR, "..", "Levantamento*.csv")]:
        achados = sorted(glob.glob(p))
        if achados: return os.path.abspath(achados[0])
    return None

CSV_PATH = _achar_csv()

def caminho_csv(): return CSV_PATH

def _detectar_encoding(path):
    if not os.path.exists(path): return "utf-8"
    with open(path, "rb") as f: raw = f.read(4)
    if raw.startswith(b"\xef\xbb\xbf"): return "utf-8-sig"
    try:
        with open(path, "r", encoding="utf-8") as f: f.read(4096)
        return "utf-8"
    except UnicodeDecodeError: return "cp1252"

def _backup_csv():
    if not CSV_PATH or not os.path.exists(CSV_PATH): return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome = os.path.basename(CSV_PATH)
    try: shutil.copy2(CSV_PATH, os.path.join(BACKUP_DIR, ts + "__" + nome))
    except Exception as e: print("[csv] Aviso backup:", e)

def _csv_carregar():
    global CSV_PATH
    if not CSV_PATH: CSV_PATH = _achar_csv()
    if not CSV_PATH or not os.path.exists(CSV_PATH): return []
    enc = _detectar_encoding(CSV_PATH)
    bens = []
    with open(CSV_PATH, "r", encoding=enc, newline="") as f:
        reader = csv.reader(f, delimiter=DELIMITER)
        try: next(reader)
        except StopIteration: return []
        for raw in reader:
            if not any((c or "").strip() for c in raw): continue
            raw = list(raw) + [""] * (len(COLS) - len(raw))
            raw = raw[:len(COLS)]
            item = {}
            for i, (_, campo) in enumerate(COLS): item[campo] = (raw[i] or "").strip()
            bens.append(item)
    for i, b in enumerate(bens, start=1): b["id"] = i
    return bens

def _csv_salvar(bens):
    if not CSV_PATH: raise RuntimeError("CSV do Levantamento não encontrado.")
    enc = _detectar_encoding(CSV_PATH)
    _backup_csv()
    with open(CSV_PATH, "w", encoding=enc, newline="") as f:
        w = csv.writer(f, delimiter=DELIMITER)
        w.writerow([c[0] for c in COLS])
        for b in bens: w.writerow([b.get(campo, "") or "" for _, campo in COLS])

def _load(path, default):
    if not os.path.exists(path): return default
    with open(path, "r", encoding="utf-8-sig") as f:
        try: return json.load(f)
        except Exception: return default

def _save(path, data):
    with open(path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)

def load_bens(): return _csv_carregar()
def save_bens(lista):
    _csv_salvar(lista)
    try: _save(ARQ_BENS, lista)
    except Exception: pass

def load_funcs(): return _load(ARQ_FUNC, [])
def load_deps(): return _load(ARQ_DEP, [])
def save_funcs(d): _save(ARQ_FUNC, d)

def next_id(lista): return (max([x.get("id", 0) for x in lista]) + 1) if lista else 1
def normalizar(s): return re.sub(r"\s+", " ", (s or "").strip())

CABECALHO_MOV = ["data", "bem_id", "categoria", "patrimonio", "hostname", "de_responsavel", "para_responsavel", "de_departamento", "para_departamento", "obs"]

def registrar_movimento(b, de_resp, de_dep, para_resp, para_dep, obs):
    existe = os.path.exists(ARQ_MOV)
    with open(ARQ_MOV, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if not existe: w.writerow(CABECALHO_MOV)
        w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M"), b.get("id"), b.get("categoria"), b.get("patrimonio"), b.get("hostname"), de_resp, para_resp, de_dep, para_dep, obs])

def agrupar_por_funcionario():
    bens = load_bens(); funcs = load_funcs()
    mapa = defaultdict(list)
    for b in bens:
        resp = normalizar(b.get("responsavel") or "") or "SEM RESPONSAVEL"
        mapa[resp].append(b)
    info = {normalizar(f["nome"]).upper(): f for f in funcs}
    teia = []
    for nome, itens in mapa.items():
        meta = info.get(nome.upper(), {})
        cats = defaultdict(int)
        for it in itens: cats[it.get("categoria") or "Outros"] += 1
        teia.append({"nome": nome, "cargo": meta.get("cargo", ""), "setor": meta.get("setor", ""), "total": len(itens), "por_categoria": dict(sorted(cats.items(), key=lambda x: -x[1])), "bens": itens})
    teia.sort(key=lambda x: (-x["total"], x["nome"]))
    return teia

def _dados_graficos():
    bens = load_bens()
    por_cat = defaultdict(int); por_dep = defaultdict(int)
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
                except Exception: pass
    hoje = datetime.now(); eixo = []
    for i in range(11, -1, -1):
        ano, mes = hoje.year, hoje.month - i
        while mes <= 0: mes += 12; ano -= 1
        eixo.append(f"{ano:04d}-{mes:02d}")
    mov_series = [mov_mes.get(m, 0) for m in eixo]
    return {
        "cat_labels": [k for k, _ in sorted(por_cat.items(), key=lambda x: -x[1])[:10]],
        "cat_values": [v for _, v in sorted(por_cat.items(), key=lambda x: -x[1])[:10]],
        "dep_labels": [k for k, _ in sorted(por_dep.items(), key=lambda x: -x[1])[:10]],
        "dep_values": [v for _, v in sorted(por_dep.items(), key=lambda x: -x[1])[:10]],
        "mov_labels": eixo, "mov_values": mov_series,
    }

@app.route("/")
def dashboard():
    bens = load_bens(); funcs = load_funcs(); deps = load_deps()
    por_status = defaultdict(int); com_resp = sem_resp = 0
    for b in bens:
        por_status[b.get("status") or "Nao informado"] += 1
        if normalizar(b.get("responsavel")): com_resp += 1
        else: sem_resp += 1
    tot_mov = 0
    if os.path.exists(ARQ_MOV):
        with open(ARQ_MOV, encoding="utf-8") as f: tot_mov = max(0, sum(1 for _ in f) - 1)
    graf = _dados_graficos()
    return render_template("dashboard.html", total=len(bens), total_func=len(funcs), total_dep=len(deps), com_responsavel=com_resp, sem_responsavel=sem_resp, total_mov=tot_mov, por_status=dict(por_status), graf=graf)

@app.route("/bens")
def bens_view():
    bens = load_bens(); todos = load_bens()
    q = (request.args.get("q") or "").lower(); cat = request.args.get("cat") or ""; dep = request.args.get("dep") or ""; resp = request.args.get("resp") or ""
    if q: bens = [b for b in bens if q in json.dumps(b, ensure_ascii=False).lower()]
    if cat: bens = [b for b in bens if (b.get("categoria") or "") == cat]
    if dep: bens = [b for b in bens if (b.get("departamento") or "") == dep]
    if resp: bens = [b for b in bens if normalizar(b.get("responsavel")) == resp]
    return render_template("bens.html", bens=bens, categorias=sorted({b.get("categoria") for b in todos if b.get("categoria")}), departamentos=sorted({b.get("departamento") for b in todos if b.get("departamento")}), responsaveis=sorted({normalizar(b.get("responsavel")) for b in todos if b.get("responsavel")}), filtros={"q": q, "cat": cat, "dep": dep, "resp": resp})

@app.route("/bens/salvar", methods=["POST"])
def bens_salvar():
    d = request.json or {}; bens = load_bens()
    campos = ["categoria", "modelo", "hostname", "patrimonio", "departamento", "responsavel", "marca", "serial", "ramal", "ip", "observacao", "cpu", "disco", "ram", "iso", "status"]
    item = {k: normalizar(d.get(k)) for k in campos}
    bid = d.get("id")
    if bid:
        for i, b in enumerate(bens):
            if b.get("id") == bid:
                bens[i] = {**b, **item, "atualizado_em": datetime.now().isoformat()}
                break
        msg = "Bem atualizado!"
    else:
        item["id"] = next_id(bens); item["criado_em"] = datetime.now().isoformat(); bens.append(item); msg = "Bem cadastrado!"
    save_bens(bens)
    return jsonify({"ok": True, "msg": msg})

@app.route("/bens/excluir/<int:bid>", methods=["POST"])
def bens_excluir(bid):
    save_bens([b for b in load_bens() if b.get("id") != bid])
    return jsonify({"ok": True})

@app.route("/bens/exportar.csv")
def bens_exportar():
    if not CSV_PATH or not os.path.exists(CSV_PATH): return "CSV não encontrado", 404
    return send_file(CSV_PATH, mimetype="text/csv", as_attachment=True, download_name="Levantamento_Geral1_controle.csv")

@app.route("/planilha")
def planilha_view():
    bens = load_bens()
    cats = sorted({(b.get("categoria") or "").strip() for b in bens if (b.get("categoria") or "").strip()})
    deps = sorted({(b.get("departamento") or "").strip() for b in bens if (b.get("departamento") or "").strip()})
    return render_template("planilha.html", bens=bens, cats=cats, deps=deps, total=len(bens))

@app.route("/api/bens/celula", methods=["POST"])
def api_bens_celula():
    d = request.get_json(force=True, silent=True) or {}
    bid = d.get("id"); campo = (d.get("campo") or "").strip(); valor = (d.get("valor") or "").strip()
    if bid is None or not campo: return jsonify({"ok": False, "msg": "Faltando id/campo"})
    CAMPOS_PERMITIDOS = {"categoria", "modelo", "hostname", "patrimonio", "departamento", "responsavel", "marca", "serial", "ramal", "ip", "observacao", "cpu", "disco", "ram", "iso", "status"}
    if campo not in CAMPOS_PERMITIDOS: return jsonify({"ok": False, "msg": "Campo nao editavel"})
    bens = load_bens(); achou = False
    for b in bens:
        if b.get("id") == bid:
            b[campo] = valor; b["atualizado_em"] = datetime.now().isoformat(); achou = True
            break
    if not achou: return jsonify({"ok": False, "msg": "Bem nao encontrado"})
    save_bens(bens)
    return jsonify({"ok": True, "valor": valor})

@app.route("/api/bens/planilha_lote", methods=["POST"])
def api_bens_planilha_lote():
    d = request.get_json(force=True, silent=True) or {}
    edicoes = d.get("edicoes") or []
    if not edicoes: return jsonify({"ok": True, "aplicadas": 0})
    bens = load_bens(); por_id = {b.get("id"): b for b in bens}; aplicadas = 0
    for e in edicoes:
        b = por_id.get(e.get("id"))
        if not b: continue
        b[e.get("campo")] = (e.get("valor") or "").strip(); b["atualizado_em"] = datetime.now().isoformat(); aplicadas += 1
    save_bens(bens)
    return jsonify({"ok": True, "aplicadas": aplicadas})

@app.route("/funcionarios")
def funcionarios_view():
    funcs = load_funcs(); bens = load_bens()
    cont = defaultdict(int)
    for b in bens:
        r = normalizar(b.get("responsavel"))
        if r: cont[r.upper()] += 1
    for f in funcs: f["total_bens"] = cont.get(normalizar(f["nome"]).upper(), 0)
    return render_template("funcionarios.html", funcionarios=funcs)

@app.route("/funcionarios/salvar", methods=["POST"])
def funcionarios_salvar():
    d = request.json or {}; funcs = load_funcs()
    campos = ["nome", "cargo", "setor"]
    item = {k: normalizar(d.get(k)) for k in campos}
    if not item["nome"]: return jsonify({"ok": False, "msg": "Nome obrigatorio"})
    idx = d.get("idx")
    if idx is not None and 0 <= idx < len(funcs):
        funcs[idx] = {**funcs[idx], **item}; msg = "Atualizado!"
    else:
        funcs.append(item); msg = "Cadastrado!"
    save_funcs(funcs)
    return jsonify({"ok": True, "msg": msg})

@app.route("/funcionarios/excluir/<int:idx>", methods=["POST"])
def funcionarios_excluir(idx):
    funcs = load_funcs()
    if 0 <= idx < len(funcs):
        funcs.pop(idx); save_funcs(funcs)
    return jsonify({"ok": True})

@app.route("/teia")
def teia_view():
    return render_template("teia.html", teia=agrupar_por_funcionario())

@app.route("/movimentar")
def movimentar_view():
    bens = load_bens(); funcs = load_funcs(); deps = load_deps()
    por_resp = defaultdict(list)
    for b in bens:
        r = normalizar(b.get("responsavel")) or "SEM RESPONSAVEL"
        por_resp[r].append(b)
    return render_template("movimentar.html", bens=bens, funcionarios=funcs, departamentos=deps, por_resp={k: v for k, v in por_resp.items()})

@app.route("/movimentar/registrar", methods=["POST"])
def movimentar_registrar():
    d = request.json or {}
    origem = normalizar(d.get("origem")); destino = normalizar(d.get("destino"))
    dep_dest = normalizar(d.get("departamento_destino")); obs = normalizar(d.get("obs"))
    ids = d.get("ids") or []
    if not origem or not destino or not ids: return jsonify({"ok": False, "msg": "Preencha origem, destino e selecione ao menos 1 bem."})
    bens = load_bens(); registrados = 0
    for b in bens:
        if b.get("id") in ids:
            ar, ad = b.get("responsavel"), b.get("departamento")
            b["responsavel"] = destino
            if dep_dest: b["departamento"] = dep_dest
            b["atualizado_em"] = datetime.now().isoformat()
            registrar_movimento(b, ar, ad, b["responsavel"], b["departamento"], obs)
            registrados += 1
    save_bens(bens)
    return jsonify({"ok": True, "total": registrados, "msg": f"{registrados} movimentacao(oes) registrada(s)!"})

@app.route("/movimentacoes")
def movimentacoes_view():
    linhas = []
    if os.path.exists(ARQ_MOV):
        with open(ARQ_MOV, encoding="utf-8-sig") as f: linhas = list(csv.DictReader(f))
    q = (request.args.get("q") or "").lower()
    if q: linhas = [l for l in linhas if q in json.dumps(l, ensure_ascii=False).lower()]
    return render_template("movimentacoes.html", movimentacoes=list(reversed(linhas)), total=len(linhas), filtros={"q": q})

@app.route("/movimentacoes/exportar.csv")
def movimentacoes_exportar():
    if not os.path.exists(ARQ_MOV): return "Sem dados", 404
    return send_file(ARQ_MOV, mimetype="text/csv", as_attachment=True, download_name="movimentacoes.csv")

@app.route("/api/csv_info")
def api_csv_info():
    if not CSV_PATH: return jsonify({"ok": False, "msg": "CSV não encontrado."})
    bens = load_bens()
    try:
        st = os.stat(CSV_PATH)
        mod = datetime.fromtimestamp(st.st_mtime).strftime("%d/%m/%Y %H:%M:%S")
        tam = round(st.st_size / 1024, 1)
    except Exception: mod, tam = "?", 0
    return jsonify({"ok": True, "caminho": CSV_PATH, "registros": len(bens), "tamanho_kb": tam, "modificado_em": mod})

if __name__ == "__main__":
    print("\n" + "=" * 60)
    if CSV_PATH: print("  CSV fonte: " + CSV_PATH)
    else: print("  AVISO: CSV nao encontrado. Coloque Levantamento*.csv em:\n     " + BASE_DIR + "  ou  " + os.path.dirname(BASE_DIR))
    print("=" * 60)
    print("\n  Servidor rodando em: http://localhost:5000\n")
    app.run(debug=False, host="0.0.0.0", port=5000)