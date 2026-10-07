# -*- coding: utf-8 -*-
import os, json, csv, smtplib, ssl, logging, time
import tempfile
from datetime import datetime
from email.utils import parseaddr
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DADOS = os.path.join(BASE_DIR, "dados")
os.makedirs(DADOS, exist_ok=True)

ARQ_CONFIG = os.path.join(DADOS, "config_email.local.json")
ARQ_CONFIG_LEGADO = os.path.join(DADOS, "config_email.json")
ARQ_LOG = os.path.join(DADOS, "email_log.csv")
logger = logging.getLogger(__name__)

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
    "enviar_inicio_ferias": True,
    "enviar_relatorio": True,
}

def carregar_config():
    cfg = dict(DEFAULT_CONFIG)
    caminho_config = (
        ARQ_CONFIG if os.path.exists(ARQ_CONFIG)
        else ARQ_CONFIG_LEGADO if os.path.exists(ARQ_CONFIG_LEGADO)
        else None
    )
    if caminho_config:
        if caminho_config == ARQ_CONFIG_LEGADO:
            logger.warning(
                "Usando configuração SMTP legada; migre-a para "
                "dados/config_email.local.json ou variáveis de ambiente."
            )
        with open(caminho_config, "r", encoding="utf-8") as f:
            configuracao = json.load(f)
        if not isinstance(configuracao, dict):
            raise ValueError("A configuração de e-mail precisa ser um objeto JSON.")
        cfg.update(configuracao)

    if os.environ.get("SMTP_USER"):
        cfg["smtp_user"] = os.environ["SMTP_USER"]
    if os.environ.get("SMTP_PASSWORD"):
        cfg["smtp_pass"] = os.environ["SMTP_PASSWORD"]
    cfg["smtp_password_from_env"] = bool(os.environ.get("SMTP_PASSWORD"))
    return cfg

def salvar_config(cfg):
    cfg = dict(cfg)
    cfg.pop("smtp_password_from_env", None)
    if os.environ.get("SMTP_PASSWORD"):
        cfg.pop("smtp_pass", None)
    fd, temporario = tempfile.mkstemp(
        prefix=".email-config-", suffix=".tmp", dir=DADOS
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as arquivo:
            json.dump(cfg, arquivo, ensure_ascii=False, indent=2)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, ARQ_CONFIG)
    except Exception:
        if os.path.exists(temporario):
            os.unlink(temporario)
        raise

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


def _ja_enviado_hoje(tipo):
    if not os.path.exists(ARQ_LOG):
        return False
    hoje = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(ARQ_LOG, encoding="utf-8-sig", newline="") as arquivo:
            for linha in csv.DictReader(arquivo):
                if (
                    linha.get("data", "").startswith(hoje)
                    and linha.get("tipo") == tipo
                    and linha.get("status") == "OK"
                ):
                    return True
    except (OSError, csv.Error):
        logger.exception("Não foi possível verificar duplicidade do e-mail %s.", tipo)
        raise
    return False


def _destinatarios_validos(destinatarios):
    if not isinstance(destinatarios, (list, tuple)) or not destinatarios:
        return False
    for destinatario in destinatarios:
        if not isinstance(destinatario, str):
            return False
        nome, endereco = parseaddr(destinatario)
        if nome or endereco != destinatario.strip() or endereco.count("@") != 1:
            return False
        local, dominio = endereco.rsplit("@", 1)
        if not local or "." not in dominio or any(c.isspace() for c in endereco):
            return False
        if any(c in endereco for c in "\r\n,;<>"):
            return False
    return True


def destinatarios_validos(destinatarios):
    return _destinatarios_validos(destinatarios)


def enviar_email(destinatarios, assunto, corpo_html, tipo="geral"):
    cfg = carregar_config()
    if not cfg.get("ativo"):
        return False, "E-mail desativado nas configurações."
    if not cfg.get("smtp_user") or not cfg.get("smtp_pass"):
        return False, "SMTP user/password não configurados."
    if not _destinatarios_validos(destinatarios):
        return False, "Informe endereços de e-mail válidos."
    if not isinstance(assunto, str) or any(c in assunto for c in "\r\n"):
        return False, "Assunto inválido."
    if not isinstance(corpo_html, str):
        return False, "Conteúdo do e-mail inválido."
    if tipo in {"ferias", "ferias_inicio", "relatorio_trimestral"} and _ja_enviado_hoje(tipo):
        return True, "Este e-mail já foi enviado hoje."

    mensagem = MIMEMultipart("alternative")
    mensagem["Subject"] = assunto
    mensagem["From"] = f'{cfg["remetente_nome"]} <{cfg["smtp_user"]}>'
    mensagem["To"] = ", ".join(destinatarios)
    mensagem.attach(MIMEText(corpo_html, "html", "utf-8"))
    conteudo = mensagem.as_string()
    erro_final = None

    for tentativa in range(3):
        try:
            if cfg.get("smtp_tls"):
                context = ssl.create_default_context()
                with smtplib.SMTP(
                    cfg["smtp_host"], int(cfg["smtp_port"]), timeout=20
                ) as servidor:
                    servidor.starttls(context=context)
                    servidor.login(cfg["smtp_user"], cfg["smtp_pass"])
                    servidor.sendmail(cfg["smtp_user"], destinatarios, conteudo)
            else:
                with smtplib.SMTP_SSL(
                    cfg["smtp_host"], int(cfg["smtp_port"]), timeout=20
                ) as servidor:
                    servidor.login(cfg["smtp_user"], cfg["smtp_pass"])
                    servidor.sendmail(cfg["smtp_user"], destinatarios, conteudo)
            _registrar_log(tipo, destinatarios, assunto, "OK")
            return True, "E-mail enviado!"
        except smtplib.SMTPResponseException as erro:
            erro_final = erro
            if not 400 <= erro.smtp_code < 500 or tentativa == 2:
                break
        except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError,
                TimeoutError, ConnectionError, OSError) as erro:
            erro_final = erro
            if tentativa == 2:
                break
        if tentativa < 2:
            time.sleep(0.5 * (2 ** tentativa))

    logger.error("Falha ao enviar e-mail tipo %s após tentativas: %s", tipo, erro_final)
    _registrar_log(tipo, destinatarios, assunto, "ERRO", str(erro_final))
    return False, f"Erro ao enviar e-mail após 3 tentativas: {erro_final}"

def limpar_senha(s):
    return (s or "").replace(" ", "").strip()