# -*- coding: utf-8 -*-
import os, json, csv, io, re
from datetime import datetime, timedelta
from collections import defaultdict
from difflib import SequenceMatcher
from flask import (Flask, render_template, request, jsonify,
                   send_file, redirect, url_for, flash)

import email_sender as mailer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DADOS = os.path.join(BASE_DIR, "dados")
os.makedirs(DADOS, exist_ok=True)

app = Flask(__name__)
app.secret_key = "ti-inventario-2026"

ARQ_BENS = os.path.join(DADOS, "bens.json")
ARQ_FUNC = os.path.join(DADOS, "funcionarios.json")
ARQ_DEP  = os.path.join(DADOS, "departamentos.json")
ARQ_MOV  = os.path.join(DADOS, "movimentacoes.csv")

def _load(path, default):
    if not os.path.exists(path): return default
    with open(path, "r", encoding="utf-8-sig") as f:
        try: return json.load(f)
        except Exception: return default

def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_bens():   return _load(ARQ_BENS, [])
def load_funcs():  return _load(ARQ_FUNC, [])
def load_deps():   return _load(ARQ_DEP, [])
def save_bens(d):  _save(ARQ_BENS, d)
def save_funcs(d): _save(ARQ_FUNC, d)

def next_id(lista):
    return (max([x.get("id", 0) for x in lista]) + 1) if lista else 1

def normalizar(s):
    return re.sub(r"\s+", " ", (s or "").strip())

CABECALHO_MOV = ["data","bem_id","categoria","patrimonio","hostname",
                 "de_responsavel","para_responsavel","de_departamento",
                 "para_departamento","obs"]

def registrar_movimento(b, de_resp, de_dep, para_resp, para_dep, obs):
    existe = os.path.exists(ARQ_MOV)
    with open(ARQ_MOV, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if not existe: w.writerow(CABECALHO_MOV)
        w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M"),
                    b.get("id"), b.get("categoria"), b.get("patrimonio"),
                    b.get("hostname"), de_resp, para_resp,
                    de_dep, para_dep, obs])

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
        teia.append({"nome": nome, "cargo": meta.get("cargo",""),
                     "setor": meta.get("setor",""), "total": len(itens),
                     "por_categoria": dict(sorted(cats.items(), key=lambda x:-x[1])),
                     "bens": itens})
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
        "cat_labels": [k for k,_ in sorted(por_cat.items(), key=lambda x:-x[1])[:10]],
        "cat_values": [v for _,v in sorted(por_cat.items(), key=lambda x:-x[1])[:10]],
        "dep_labels": [k for k,_ in sorted(por_dep.items(), key=lambda x:-x[1])[:10]],
        "dep_values": [v for _,v in sorted(por_dep.items(), key=lambda x:-x[1])[:10]],
        "mov_labels": eixo,
        "mov_values": mov_series,
    }

# ============ DASHBOARD ============
@app.route("/")
def dashboard():
    bens = load_bens(); funcs = load_funcs(); deps = load_deps()
    por_status = defaultdict(int)
    com_resp = sem_resp = 0
    for b in bens:
        por_status[b.get("status") or "Nao informado"] += 1
        if normalizar(b.get("responsavel")): com_resp += 1
        else: sem_resp += 1
    tot_mov = 0
    if os.path.exists(ARQ_MOV):
        with open(ARQ_MOV, encoding="utf-8") as f:
            tot_mov = max(0, sum(1 for _ in f) - 1)
    graf = _dados_graficos()
    return render_template("dashboard.html",
        total=len(bens), total_func=len(funcs), total_dep=len(deps),
        com_responsavel=com_resp, sem_responsavel=sem_resp,
        total_mov=tot_mov, por_status=dict(por_status),
        graf=graf)

# ============ BENS ============
@app.route("/bens")
def bens_view():
    bens = load_bens(); todos = load_bens()
    q = (request.args.get("q") or "").lower()
    cat = request.args.get("cat") or ""
    dep = request.args.get("dep") or ""
    resp = request.args.get("resp") or ""
    if q: bens = [b for b in bens if q in json.dumps(b, ensure_ascii=False).lower()]
    if cat: bens = [b for b in bens if (b.get("categoria") or "") == cat]
    if dep: bens = [b for b in bens if (b.get("departamento") or "") == dep]
    if resp: bens = [b for b in bens if normalizar(b.get("responsavel")) == resp]
    return render_template("bens.html", bens=bens,
        categorias=sorted({b.get("categoria") for b in todos if b.get("categoria")}),
        departamentos=sorted({b.get("departamento") for b in todos if b.get("departamento")}),
        responsaveis=sorted({normalizar(b.get("responsavel")) for b in todos if b.get("responsavel")}),
        filtros={"q":q,"cat":cat,"dep":dep,"resp":resp})

@app.route("/bens/salvar", methods=["POST"])
def bens_salvar():
    d = request.json or {}
    bens = load_bens()
    campos = ["categoria","modelo","hostname","patrimonio","departamento",
              "responsavel","marca","serial","ramal","ip","observacao",
              "cpu","disco","ram","iso","status"]
    item = {k: normalizar(d.get(k)) for k in campos}
    bid = d.get("id")
    if bid:
        for i,b in enumerate(bens):
            if b.get("id") == bid:
                bens[i] = {**b, **item, "atualizado_em": datetime.now().isoformat()}
                break
        msg = "Bem atualizado!"
    else:
        item["id"] = next_id(bens); item["criado_em"] = datetime.now().isoformat()
        bens.append(item); msg = "Bem cadastrado!"
    save_bens(bens)
    return jsonify({"ok":True,"msg":msg})

@app.route("/bens/excluir/<int:bid>", methods=["POST"])
def bens_excluir(bid):
    save_bens([b for b in load_bens() if b.get("id") != bid])
    return jsonify({"ok":True})

@app.route("/bens/exportar.csv")
def bens_exportar():
    bens = load_bens()
    if not bens: return "Sem dados", 404
    campos = ["id","categoria","modelo","marca","hostname","patrimonio",
              "departamento","responsavel","serial","ramal","ip",
              "cpu","disco","ram","iso","status","observacao"]
    sio = io.StringIO()
    w = csv.DictWriter(sio, fieldnames=campos, extrasaction="ignore")
    w.writeheader()
    for b in bens: w.writerow(b)
    mem = io.BytesIO(sio.getvalue().encode("utf-8-sig"))
    return send_file(mem, mimetype="text/csv", as_attachment=True,
                     download_name="bens.csv")

# ============ FUNCIONARIOS ============
@app.route("/funcionarios")
def funcionarios_view():
    funcs = load_funcs(); bens = load_bens()
    cont = defaultdict(int)
    for b in bens:
        r = normalizar(b.get("responsavel"))
        if r: cont[r.upper()] += 1
    for f in funcs:
        f["total_bens"] = cont.get(normalizar(f["nome"]).upper(), 0)
    return render_template("funcionarios.html", funcionarios=funcs)

@app.route("/funcionarios/salvar", methods=["POST"])
def funcionarios_salvar():
    d = request.json or {}
    funcs = load_funcs()
    campos = ["nome","cargo","setor"]
    item = {k: normalizar(d.get(k)) for k in campos}
    if not item["nome"]: return jsonify({"ok":False,"msg":"Nome obrigatorio"})
    idx = d.get("idx")
    if idx is not None and 0 <= idx < len(funcs):
        funcs[idx] = {**funcs[idx], **item}; msg = "Atualizado!"
    else:
        funcs.append(item); msg = "Cadastrado!"
    save_funcs(funcs)
    return jsonify({"ok":True,"msg":msg})

@app.route("/funcionarios/excluir/<int:idx>", methods=["POST"])
def funcionarios_excluir(idx):
    funcs = load_funcs()
    if 0 <= idx < len(funcs): funcs.pop(idx); save_funcs(funcs)
    return jsonify({"ok":True})

# ============ TEIA ============
@app.route("/teia")
def teia_view():
    return render_template("teia.html", teia=agrupar_por_funcionario())

# ============ MOVIMENTAR ============
@app.route("/movimentar")
def movimentar_view():
    bens = load_bens(); funcs = load_funcs(); deps = load_deps()
    por_resp = defaultdict(list)
    for b in bens:
        r = normalizar(b.get("responsavel")) or "SEM RESPONSAVEL"
        por_resp[r].append(b)
    return render_template("movimentar.html",
                           bens=bens, funcionarios=funcs, departamentos=deps,
                           por_resp={k: v for k,v in por_resp.items()})

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
            if dep_dest: b["departamento"] = dep_dest
            b["atualizado_em"] = datetime.now().isoformat()
            registrar_movimento(b, ar, ad, b["responsavel"], b["departamento"], obs)
            registrados += 1
    save_bens(bens)
    return jsonify({"ok": True, "total": registrados,
                    "msg": f"{registrados} movimentacao(oes) registrada(s)!"})

# ============ MOVIMENTACOES ============
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
    if not os.path.exists(ARQ_MOV): return "Sem dados", 404
    return send_file(ARQ_MOV, mimetype="text/csv", as_attachment=True,
                     download_name="movimentacoes.csv")

# ============ CONFIGURACOES / EMAIL ============
def _split_emails(s):
    return [e.strip() for e in re.split(r"[,;\n]+", s or "") if e.strip()]

@app.route("/configuracoes")
def configuracoes_view():
    cfg = mailer.carregar_config()
    prox = mailer.proximo_disparo(cfg)
    log = []
    if os.path.exists(mailer.ARQ_LOG):
        with open(mailer.ARQ_LOG, encoding="utf-8-sig") as f:
            log = list(csv.DictReader(f))[-10:]
    return render_template("configuracoes.html",
                           cfg=cfg,
                           proximo=prox.strftime("%d/%m/%Y %H:%M") if prox else "—",
                           log=list(reversed(log)))

@app.route("/configuracoes/salvar", methods=["POST"])
def configuracoes_salvar():
    d = request.get_json(force=True, silent=True) or {}
    cfg = mailer.carregar_config()
    cfg.update({
        "ativo": bool(d.get("ativo")),
        "frequencia": str(d.get("frequencia") or "trimestral"),
        "dia": int(d.get("dia") or 1),
        "hora": int(d.get("hora") or 9),
        "minuto": int(d.get("minuto") or 0),
        "destinatarios": _split_emails(d.get("destinatarios")),
        "assunto": str(d.get("assunto") or "").strip() or mailer.DEFAULT_CONFIG["assunto"],
        "smtp_host": str(d.get("smtp_host") or "").strip(),
        "smtp_port": int(d.get("smtp_port") or 465),
        "smtp_user": str(d.get("smtp_user") or "").strip(),
        "smtp_pass": (
            mailer.limpar_senha(d.get("smtp_pass"))
            if d.get("smtp_pass")
            else cfg.get("smtp_pass", "")
        ),
        "smtp_tls": bool(d.get("smtp_tls")),
        "remetente_nome": str(d.get("remetente_nome") or "").strip() or "Inventario TI",
        "incluir_movimentacoes": bool(d.get("incluir_movimentacoes")),
        "incluir_estoque": bool(d.get("incluir_estoque")),
        "incluir_sem_responsavel": bool(d.get("incluir_sem_responsavel")),
        "incluir_ranking": bool(d.get("incluir_ranking")),
        "incluir_alertas": bool(d.get("incluir_alertas")),
    })
    mailer.salvar_config(cfg)
    return jsonify({"ok": True, "msg": "Configuracoes salvas!"})

@app.route("/configuracoes/testar", methods=["POST"])
def configuracoes_testar():
    d = request.get_json(force=True, silent=True) or {}
    cfg = mailer.carregar_config()
    if d.get("smtp_host"):      cfg["smtp_host"] = str(d["smtp_host"]).strip()
    if d.get("smtp_port"):      cfg["smtp_port"] = int(d["smtp_port"])
    if d.get("smtp_user"):      cfg["smtp_user"] = str(d["smtp_user"]).strip()
    if d.get("smtp_pass"):      cfg["smtp_pass"] = mailer.limpar_senha(d["smtp_pass"])
    if "smtp_tls" in d:         cfg["smtp_tls"] = bool(d["smtp_tls"])
    if d.get("remetente_nome"): cfg["remetente_nome"] = str(d["remetente_nome"]).strip()
    if d.get("assunto"):        cfg["assunto"] = str(d["assunto"]).strip()
    if d.get("destinatarios"):  cfg["destinatarios"] = _split_emails(d["destinatarios"])
    ok, msg = mailer.enviar_email(cfg)
    return jsonify({"ok": ok, "msg": msg})

@app.route("/configuracoes/enviar_agora", methods=["POST"])
def configuracoes_enviar_agora():
    cfg = mailer.carregar_config()
    ok, msg = mailer.enviar_email(cfg)
    return jsonify({"ok": ok, "msg": msg})

@app.route("/configuracoes/preview")
def configuracoes_preview():
    cfg = mailer.carregar_config()
    return mailer.montar_email(cfg)

@app.route("/configuracoes/diagnostico")
def configuracoes_diagnostico():
    cfg = mailer.carregar_config()
    senha = cfg.get("smtp_pass") or ""
    return jsonify({
        "smtp_host": cfg.get("smtp_host"),
        "smtp_port": cfg.get("smtp_port"),
        "smtp_user": cfg.get("smtp_user"),
        "smtp_tls": cfg.get("smtp_tls"),
        "senha_tamanho": len(senha),
        "senha_tem_espaco": " " in senha,
        "senha_primeiros4": senha[:4] + "..." if senha else "(vazia)",
        "destinatarios": cfg.get("destinatarios"),
        "remetente_nome": cfg.get("remetente_nome"),
        "assunto": cfg.get("assunto"),
    })

# ============ QR CODE / ETIQUETAS ============
import socket as _socket
try:
    import segno
    TEM_SEGNO = True
except ImportError:
    TEM_SEGNO = False

def get_lan_ip():
    """Descobre o IP da maquina na rede local."""
    s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

def base_url_publica():
    """URL base dos QR codes (ex: http://10.28.67.22:5000)."""
    return "http://%s:5000" % get_lan_ip()

def encontrar_bem(ident):
    """Acha bem por ID, patrimonio ou hostname."""
    bens = load_bens()
    ident_s = str(ident).strip()
    if ident_s.isdigit():
        for b in bens:
            if b.get("id") == int(ident_s):
                return b
    for b in bens:
        if (b.get("patrimonio") or "").strip().upper() == ident_s.upper():
            return b
    for b in bens:
        if (b.get("hostname") or "").strip().upper() == ident_s.upper():
            return b
    return None

@app.route("/etiquetas")
def etiquetas_view():
    bens = load_bens()
    q = (request.args.get("q") or "").lower()
    cat = request.args.get("cat") or ""
    if q:
        bens = [b for b in bens if q in json.dumps(b, ensure_ascii=False).lower()]
    if cat:
        bens = [b for b in bens if (b.get("categoria") or "") == cat]
    todas_cats = sorted({b.get("categoria") for b in load_bens() if b.get("categoria")})
    return render_template("etiquetas.html",
        bens=bens[:500], total=len(bens),
        categorias=todas_cats,
        filtros={"q": q, "cat": cat},
        base_url=base_url_publica(),
        tem_segno=TEM_SEGNO)

@app.route("/etiquetas/imprimir", methods=["POST"])
def etiquetas_imprimir():
    d = request.json or {}
    ids = d.get("ids") or []
    bens = load_bens()
    selecionados = [b for b in bens if b.get("id") in ids]
    return render_template("etiquetas_imprimir.html",
        bens=selecionados,
        base_url=base_url_publica())

@app.route("/b/<ident>")
def bem_detalhe_publico(ident):
    bem = encontrar_bem(ident)
    if not bem:
        return render_template("bem_404.html", ident=ident), 404
    historico = []
    if os.path.exists(ARQ_MOV):
        with open(ARQ_MOV, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if str(row.get("bem_id")) == str(bem.get("id")):
                    historico.append(row)
    historico = list(reversed(historico))
    return render_template("bem_detalhe.html", bem=bem, historico=historico)

@app.route("/b/<ident>/qrcode.png")
def bem_qrcode(ident):
    if not TEM_SEGNO:
        return "Instale segno: pip install segno", 500
    bem = encontrar_bem(ident)
    if not bem:
        return "Bem nao encontrado", 404
    url = "%s/b/%s" % (base_url_publica(), ident)
    qr = segno.make(url, error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=10, border=2)
    buf.seek(0)
    return send_file(buf, mimetype="image/png")

# ============ ESCANEAR ETIQUETA (OCR) + BUSCA ============
@app.route("/escanear")
def escanear_view():
    return render_template("escanear.html")

@app.route("/api/sugerir")
def api_sugerir():
    """Retorna bens que casam com o texto (hostname, patrimonio, id, modelo)."""
    q = (request.args.get("q") or "").strip().upper()
    if not q or len(q) < 2:
        return jsonify({"bens": []})
    bens = load_bens()
    out = []
    for b in bens:
        h = (b.get("hostname") or "").upper()
        p = (b.get("patrimonio") or "").upper()
        m = (b.get("modelo") or "").upper()
        r = (b.get("responsavel") or "").upper()
        if q in h or q in p or q in m or q in r or str(b.get("id")) == q:
            out.append({
                "id": b.get("id"),
                "hostname": b.get("hostname") or "",
                "patrimonio": b.get("patrimonio") or "",
                "categoria": b.get("categoria") or "",
                "modelo": b.get("modelo") or "",
                "responsavel": b.get("responsavel") or "",
                "departamento": b.get("departamento") or "",
                "status": b.get("status") or "",
            })
    # Prioriza quem começa com q, depois quem contém
    def _rank(x):
        h = x["hostname"].upper()
        p = x["patrimonio"].upper()
        if h.startswith(q) or p.startswith(q): return (0, h)
        return (1, h)
    out.sort(key=_rank)
    return jsonify({"bens": out[:15]})

@app.route("/api/buscar_por_tag", methods=["POST"])
def api_buscar_tag():
    """
    Recebe texto lido pelo OCR e tenta casar com um bem.
    Usa SequenceMatcher com exigência de 90% de similaridade para
    evitar falsos positivos (ex: 7RH31H4 vs 7RH31H5).
    """
    d = request.get_json(force=True, silent=True) or {}
    texto = (d.get("texto") or "").upper()
    if not texto:
        return jsonify({"ok": False, "msg": "Texto vazio"})

    # Extrai candidatos: sequências alfanuméricas de 3 a 16 chars (com hífen)
    candidatos_raw = re.findall(r"[A-Z0-9][A-Z0-9\-]{2,15}", texto)
    vistos = set()
    candidatos = []
    for c in candidatos_raw:
        # Ignora palavras comuns do OCR
        if c in ("THE", "AND", "FOR", "COM", "WWW"):
            continue
        if c not in vistos:
            vistos.add(c)
            candidatos.append(c)

    bens = load_bens()
    achados = []

    for b in bens:
        h = (b.get("hostname") or "").upper().strip()
        p = (b.get("patrimonio") or "").upper().strip()

        # 1) Match exato — prioridade máxima
        if h and len(h) >= 3 and h in texto:
            achados.append((100, b))
            continue
        if p and len(p) >= 3 and p in texto:
            achados.append((95, b))
            continue

        # 2) Match aproximado — só contra candidatos, exigindo 90%+
        melhor_ratio = 0
        for alvo in (h, p):
            if not alvo or len(alvo) < 4:
                continue
            for cand in candidatos:
                if len(cand) < 4:
                    continue
                # Diferença de tamanho máx 1 caractere
                if abs(len(cand) - len(alvo)) > 1:
                    continue
                ratio = SequenceMatcher(None, cand, alvo).ratio()
                if ratio > melhor_ratio:
                    melhor_ratio = ratio

        if melhor_ratio >= 0.90:
            achados.append((int(melhor_ratio * 70), b))

    if not achados:
        return jsonify({
            "ok": False,
            "msg": "Não consegui identificar um bem. Aproxime mais a câmera ou digite o código manualmente.",
            "texto_lido": texto,
            "candidatos": candidatos[:8]
        })

    achados.sort(key=lambda x: -x[0])
    melhor = achados[0][1]

    # Log de debug no terminal
    print(f"[OCR] Texto: {texto[:120]}")
    print(f"[OCR] Candidatos: {candidatos[:8]}")
    print(f"[OCR] Top 3: {[(score, (b.get('hostname') or b.get('patrimonio'))) for score, b in achados[:3]]}")

    return jsonify({
        "ok": True,
        "id": melhor.get("id"),
        "hostname": melhor.get("hostname") or melhor.get("patrimonio"),
        "redirect": "/b/%s" % (melhor.get("hostname") or melhor.get("patrimonio") or melhor.get("id"))
    })

# ============ START ============
if __name__ == "__main__":
    mailer.iniciar_scheduler()
    print("\n  Servidor rodando em: http://localhost:5000\n")
    app.run(debug=False, host="0.0.0.0", port=5000)