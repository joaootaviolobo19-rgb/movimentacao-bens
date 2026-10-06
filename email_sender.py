# -*- coding: utf-8 -*-
import os, json, csv, smtplib, ssl
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DADOS = os.path.join(BASE_DIR, "dados")
os.makedirs(DADOS, exist_ok=True)

ARQ_CONFIG = os.path.join(DADOS, "config_email.json")
ARQ_LOG = os.path.join(DADOS, "email_log.csv")

DEFAULT_CONFIG = {
    "ativo": False,
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "smtp_user": "",
    "smtp_pass": "",
    "smtp_tls": True,
    "remetente_nome": "Sistema de Movimentação - TI",
    "destinatarios_ferias": [],
    "destinatarios_relatorio": [],
    "assunto_ferias": "[TI] Alerta: Férias terminam amanhã",
    "assunto_relatorio": "[TI] Relatório Trimestral de Movimentações",
    "enviar_ferias": True,
    "enviar_relatorio": True,
}

def carregar_config():
    if not os.path.exists(ARQ_CONFIG):
        return dict(DEFAULT_CONFIG)
    try:
        with open(ARQ_CONFIG, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        for k, v in DEFAULT_CONFIG.items():
            cfg.setdefault(k, v)
        return cfg
    except Exception:
        return dict(DEFAULT_CONFIG)

def salvar_config(cfg):
    with open(ARQ_CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def _registrar_log(tipo, destinatarios, assunto, status, msg=""):
    existe = os.path.exists(ARQ_LOG)
    with open(ARQ_LOG, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if not existe:
            w.writerow(["data", "tipo", "destinatarios", "assunto", "status", "msg"])
        w.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            tipo, ";".join(destinatarios), assunto, status, msg,
        ])

def enviar_email(destinatarios, assunto, corpo_html, tipo="geral"):
    cfg = carregar_config()
    if not cfg.get("ativo"):
        return False, "E-mail desativado nas configurações."
    if not cfg.get("smtp_user") or not cfg.get("smtp_pass"):
        return False, "SMTP user/password não configurados."
    if not destinatarios:
        return False, "Nenhum destinatário informado."

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = assunto
        msg["From"] = f'{cfg["remetente_nome"]} <{cfg["smtp_user"]}>'
        msg["To"] = ", ".join(destinatarios)
        msg.attach(MIMEText(corpo_html, "html", "utf-8"))

        if cfg.get("smtp_tls"):
            context = ssl.create_default_context()
            with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"], timeout=20) as server:
                server.starttls(context=context)
                server.login(cfg["smtp_user"], cfg["smtp_pass"])
                server.sendmail(cfg["smtp_user"], destinatarios, msg.as_string())
        else:
            with smtplib.SMTP_SSL(cfg["smtp_host"], cfg["smtp_port"], timeout=20) as server:
                server.login(cfg["smtp_user"], cfg["smtp_pass"])
                server.sendmail(cfg["smtp_user"], destinatarios, msg.as_string())

        _registrar_log(tipo, destinatarios, assunto, "OK")
        return True, "E-mail enviado!"
    except Exception as e:
        _registrar_log(tipo, destinatarios, assunto, "ERRO", str(e))
        return False, f"Erro: {e}"

def limpar_senha(s):
    return (s or "").replace(" ", "").strip()