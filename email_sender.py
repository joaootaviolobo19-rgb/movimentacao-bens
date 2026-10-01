# -*- coding: utf-8 -*-
"""Motor de envio de e-mails agendados (background thread)."""
import os, json, csv, smtplib, threading, time, re
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
DADOS = os.path.join(BASE, "dados")
ARQ_CONFIG = os.path.join(DADOS, "config_email.json")
ARQ_MOV = os.path.join(DADOS, "movimentacoes.csv")
ARQ_BENS = os.path.join(DADOS, "bens.json")
ARQ_LOG = os.path.join(DADOS, "emails_enviados.csv")

DEFAULT_CONFIG = {
    "ativo": False, "frequencia": "trimestral",
    "dia": 1, "hora": 9, "minuto": 0,
    "destinatarios": [],
    "assunto": "[Inventario T.I.] Resumo de Movimentacoes",
    "smtp_host": "smtp.gmail.com", "smtp_port": 465,
    "smtp_user": "", "smtp_pass": "", "smtp_tls": True,
    "remetente_nome": "Inventario TI",
    "ultimo_envio": None,
    "incluir_movimentacoes": True, "incluir_estoque": True,
    "incluir_sem_responsavel": True, "incluir_ranking": True,
    "incluir_alertas": True,
}
DIAS_POR_FREQ = {"mensal": 30, "trimestral": 90, "semestral": 180, "anual": 365}

def limpar_senha(s):
    """Remove TODOS os espaços - Gmail App Password vem com espaços."""
    return re.sub(r"\s+", "", s or "")

def _load(path, default):
    if not os.path.exists(path): return default
    with open(path, "r", encoding="utf-8-sig") as f:
        try: return json.load(f)
        except Exception: return default

def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def carregar_config():
    cfg = DEFAULT_CONFIG.copy()
    cfg.update(_load(ARQ_CONFIG, {}))
    cfg["smtp_pass"] = limpar_senha(cfg.get("smtp_pass", ""))
    return cfg

def salvar_config(cfg):
    if "smtp_pass" in cfg:
        cfg["smtp_pass"] = limpar_senha(cfg["smtp_pass"])
    _save(ARQ_CONFIG, cfg)

def _ler_movimentacoes():
    if not os.path.exists(ARQ_MOV): return []
    with open(ARQ_MOV, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def _filtrar_periodo(movs, dias):
    limite = datetime.now() - timedelta(days=dias)
    out = []
    for m in movs:
        try:
            d = datetime.strptime(m["data"], "%Y-%m-%d %H:%M")
            if d >= limite: out.append(m)
        except Exception: pass
    return out

def _bloco_movimentacoes(movs):
    if not movs:
        return "<p><em>Nenhuma movimentacao no periodo.</em></p>"
    linhas = "".join(
        f"<tr><td style='padding:6px;border-bottom:1px solid #eee'>{m['data']}</td>"
        f"<td style='padding:6px;border-bottom:1px solid #eee'>{m.get('categoria','')} - "
        f"{m.get('hostname','') or m.get('patrimonio','')}</td>"
        f"<td style='padding:6px;border-bottom:1px solid #eee'>{m.get('de_responsavel','')}</td>"
        f"<td style='padding:6px;border-bottom:1px solid #eee'><strong>"
        f"{m.get('para_responsavel','')}</strong></td></tr>" for m in movs[:50])
    extra = f"<p style='font-size:12px;color:#888'>... e mais {len(movs)-50} no CSV.</p>" if len(movs)>50 else ""
    return f"""
    <h3 style="color:#1e40af;margin-top:24px">Movimentacoes no periodo ({len(movs)})</h3>
    <table style="width:100%;border-collapse:collapse;font-size:14px">
      <tr style="background:#eef2ff">
        <th style='padding:6px;text-align:left'>Data</th>
        <th style='padding:6px;text-align:left'>Bem</th>
        <th style='padding:6px;text-align:left'>De</th>
        <th style='padding:6px;text-align:left'>Para</th>
      </tr>{linhas}</table>{extra}"""

def _bloco_ranking(movs):
    if not movs: return ""
    para = Counter(m.get("para_responsavel","") for m in movs if m.get("para_responsavel"))
    de = Counter(m.get("de_responsavel","") for m in movs if m.get("de_responsavel"))
    def li(items):
        return "".join(f"<li>{n} - <strong>{c}</strong></li>" for n,c in items) or "<li>-</li>"
    return f"""
    <h3 style="color:#1e40af;margin-top:24px">Ranking do periodo</h3>
    <table style="width:100%;font-size:14px;border-collapse:collapse"><tr>
      <td style="vertical-align:top;padding:8px"><strong>Mais receberam bens:</strong>
        <ul style="padding-left:18px;margin:6px 0">{li(para.most_common(5))}</ul></td>
      <td style="vertical-align:top;padding:8px"><strong>Mais devolveram bens:</strong>
        <ul style="padding-left:18px;margin:6px 0">{li(de.most_common(5))}</ul></td>
    </tr></table>"""

def _bloco_estoque():
    bens = _load(ARQ_BENS, [])
    if not bens: return ""
    cat = Counter(b.get("categoria") or "Outros" for b in bens)
    st = Counter((b.get("status") or "N/I")[:40] for b in bens)
    lc = "".join(f"<li>{c} - <strong>{q}</strong></li>" for c,q in cat.most_common())
    ls = "".join(f"<li>{s} - <strong>{q}</strong></li>" for s,q in st.most_common(8))
    return f"""
    <h3 style="color:#1e40af;margin-top:24px">Panorama do estoque ({len(bens)} bens)</h3>
    <table style="width:100%;font-size:14px;border-collapse:collapse"><tr>
      <td style="vertical-align:top;padding:8px"><strong>Por categoria:</strong>
        <ul style="padding-left:18px;margin:6px 0">{lc}</ul></td>
      <td style="vertical-align:top;padding:8px"><strong>Por status:</strong>
        <ul style="padding-left:18px;margin:6px 0">{ls}</ul></td>
    </tr></table>"""

def _bloco_sem_responsavel():
    bens = _load(ARQ_BENS, [])
    sem = [b for b in bens if not (b.get("responsavel") or "").strip()]
    if not sem: return ""
    linhas = "".join(
        f"<li>{b.get('categoria','')} {b.get('marca','')} {b.get('modelo','')} - "
        f"{b.get('hostname','') or b.get('patrimonio','')}</li>" for b in sem[:30])
    extra = f"<p style='font-size:12px;color:#888'>... e mais {len(sem)-30}</p>" if len(sem)>30 else ""
    return f"""
    <h3 style="color:#dc2626;margin-top:24px">Bens sem responsavel ({len(sem)})</h3>
    <ul style="padding-left:18px;font-size:14px">{linhas}</ul>{extra}"""

def _bloco_alertas():
    bens = _load(ARQ_BENS, [])
    ruins = [b for b in bens if "RUIM" in (b.get("status") or "").upper()]
    desc = [b for b in bens if "DESCARTE" in (b.get("status") or "").upper()
            or "DESCARTE" in (b.get("observacao") or "").upper()]
    if not ruins and not desc: return ""
    return f"""
    <h3 style="color:#ea580c;margin-top:24px">Alertas</h3>
    <ul style="padding-left:18px;font-size:14px">
      <li>Bens com status <strong>RUIM</strong>: {len(ruins)}</li>
      <li>Marcados para <strong>DESCARTE</strong>: {len(desc)}</li>
    </ul>"""

def montar_email(cfg):
    dias = DIAS_POR_FREQ.get(cfg.get("frequencia","trimestral"), 90)
    movs = _filtrar_periodo(_ler_movimentacoes(), dias)
    p = [f"""
    <div style="font-family:Segoe UI,Arial,sans-serif;max-width:720px;margin:auto;color:#222">
      <div style="background:linear-gradient(135deg,#4f46e5,#06b6d4);color:#fff;padding:24px;border-radius:8px 8px 0 0">
        <h1 style="margin:0;font-size:22px">Resumo do Inventario T.I.</h1>
        <p style="margin:4px 0 0 0;opacity:.9;font-size:14px">
          Periodo: ultimos {dias} dias - gerado em {datetime.now():%d/%m/%Y %H:%M}</p>
      </div>
      <div style="border:1px solid #e5e7eb;border-top:none;padding:24px;border-radius:0 0 8px 8px">
        <p style="margin-top:0"><strong>{len(movs)}</strong> movimentacao(oes) no periodo.</p>
    """]
    if cfg.get("incluir_movimentacoes"):   p.append(_bloco_movimentacoes(movs))
    if cfg.get("incluir_ranking"):         p.append(_bloco_ranking(movs))
    if cfg.get("incluir_estoque"):         p.append(_bloco_estoque())
    if cfg.get("incluir_sem_responsavel"): p.append(_bloco_sem_responsavel())
    if cfg.get("incluir_alertas"):         p.append(_bloco_alertas())
    p.append("""
        <p style="color:#6b7280;font-size:12px;margin-top:32px;border-top:1px solid #e5e7eb;padding-top:12px">
          Este email foi enviado automaticamente pelo sistema Inventario T.I.</p>
      </div></div>""")
    return "".join(p)

def enviar_email(cfg=None):
    cfg = cfg or carregar_config()
    cfg["smtp_pass"] = limpar_senha(cfg.get("smtp_pass",""))

    if not cfg.get("destinatarios"):
        return False, "Nenhum destinatario configurado."
    if not cfg.get("smtp_user") or not cfg.get("smtp_pass"):
        return False, "Usuario/senha SMTP nao configurados."

    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(cfg.get("assunto") or DEFAULT_CONFIG["assunto"], "utf-8")
    nome_rem = cfg.get("remetente_nome") or "Inventario TI"
    msg["From"] = formataddr((str(Header(nome_rem, "utf-8")), cfg["smtp_user"]))
    msg["To"] = ", ".join(cfg["destinatarios"])
    msg.attach(MIMEText(montar_email(cfg), "html", "utf-8"))

    host = cfg["smtp_host"]
    port = int(cfg["smtp_port"])
    timeout = 30

    try:
        print(f"[EMAIL] Conectando em {host}:{port}...")
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=timeout)
        else:
            server = smtplib.SMTP(host, port, timeout=timeout)
            server.ehlo()
            if cfg.get("smtp_tls", True):
                server.starttls()
                server.ehlo()

        print(f"[EMAIL] Conectado. Autenticando como {cfg['smtp_user']}...")
        server.login(cfg["smtp_user"], cfg["smtp_pass"])
        print("[EMAIL] Autenticado. Enviando...")
        server.sendmail(cfg["smtp_user"], cfg["destinatarios"], msg.as_string())
        server.quit()
        print("[EMAIL] Enviado com sucesso!")

        _log(cfg["destinatarios"], cfg["assunto"], "OK")
        cfg["ultimo_envio"] = datetime.now().isoformat()
        salvar_config(cfg)
        return True, "E-mail enviado com sucesso!"
    except smtplib.SMTPAuthenticationError as e:
        err = f"Autenticacao falhou (535). Verifique se a senha e uma 'Senha de App' do Gmail (16 letras). Detalhe: {e}"
        print(f"[EMAIL] {err}")
        _log(cfg["destinatarios"], cfg["assunto"], f"ERRO AUTH: {e}")
        return False, err
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        print(f"[EMAIL] {err}")
        _log(cfg["destinatarios"], cfg["assunto"], f"ERRO: {err}")
        return False, f"Erro ao enviar: {err}"

def _log(dest, assunto, status):
    existe = os.path.exists(ARQ_LOG)
    with open(ARQ_LOG, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if not existe: w.writerow(["data","destinatarios","assunto","status"])
        w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M"), "; ".join(dest), assunto, status])

def proximo_disparo(cfg):
    if not cfg.get("ativo"): return None
    agora = datetime.now()
    dia = int(cfg.get("dia",1)); hora = int(cfg.get("hora",9)); mi = int(cfg.get("minuto",0))
    try: cand = agora.replace(day=dia, hour=hora, minute=mi, second=0, microsecond=0)
    except ValueError: cand = agora.replace(day=28, hour=hora, minute=mi, second=0, microsecond=0)
    if cand <= agora:
        cand = (agora.replace(day=1) + timedelta(days=32)).replace(
            day=dia, hour=hora, minute=mi, second=0, microsecond=0)
    return cand

def _deve_enviar_agora(cfg):
    if not cfg.get("ativo"): return False
    a = datetime.now()
    if a.day != int(cfg.get("dia",1)): return False
    if a.hour != int(cfg.get("hora",9)): return False
    if abs(a.minute - int(cfg.get("minuto",0))) > 5: return False
    u = cfg.get("ultimo_envio")
    if u:
        try:
            d = datetime.fromisoformat(u)
            if (a - d).days < DIAS_POR_FREQ.get(cfg.get("frequencia","trimestral"),90) - 5:
                return False
        except Exception: pass
    return True

def _loop():
    while True:
        try:
            cfg = carregar_config()
            if _deve_enviar_agora(cfg):
                ok, msg = enviar_email(cfg)
                print(f"[EMAIL] {msg}")
        except Exception as e:
            print(f"[EMAIL] erro: {e}")
        time.sleep(180)

_iniciado = False
def iniciar_scheduler():
    global _iniciado
    if _iniciado: return
    _iniciado = True
    threading.Thread(target=_loop, daemon=True).start()
    print("[EMAIL] scheduler iniciado em background")