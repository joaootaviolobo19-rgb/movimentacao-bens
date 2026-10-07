# -*- coding: utf-8 -*-
"""Task automática - roda 1x por dia.
1) Se há férias terminando amanhã, envia e-mail de alerta.
2) No primeiro dia dos meses 1,4,7,10, envia relatório trimestral.
"""
import os, csv, json
from datetime import datetime, timedelta
from collections import defaultdict
from html import escape

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DADOS = os.path.join(BASE_DIR, "dados")
ARQ_MOV = os.path.join(DADOS, "movimentacoes.csv")
ARQ_FER = os.path.join(DADOS, "ferias.json")
ARQ_BENS = os.path.join(DADOS, "bens.json")

import email_sender

def _load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8-sig") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as erro:
            raise ValueError(f"Arquivo JSON inválido: {os.path.basename(path)}") from erro

def enviar_alertas_ferias(cfg):
    ferias = _load_json(ARQ_FER, [])
    hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    amanha = hoje + timedelta(days=1)

    alertas = []
    for f in ferias:
        status = (f.get("status") or "").strip()
        if status in ("Concluído", "Cancelado"):
            continue
        try:
            fim = datetime.strptime(f.get("fim", ""), "%Y-%m-%d")
        except (TypeError, ValueError):
            continue
        if fim.date() == amanha.date():
            alertas.append(f)

    if not alertas:
        print(f"[{datetime.now()}] Nenhuma férias terminando amanhã.")
        return

    linhas = "".join(f"""
        <tr>
            <td style="padding:10px; border-bottom:1px solid #eee;"><strong>{escape(str(a.get('nome') or '—'))}</strong></td>
            <td style="padding:10px; border-bottom:1px solid #eee;">{escape(str(a.get('fim') or '—'))}</td>
            <td style="padding:10px; border-bottom:1px solid #eee;">{escape(str(a.get('obs') or '—'))}</td>
        </tr>
    """ for a in alertas)

    corpo = f"""
    <div style="font-family:Arial,sans-serif; max-width:600px; margin:0 auto;">
        <div style="background:#1a2a4a; color:white; padding:20px; border-radius:8px 8px 0 0;">
            <h2 style="margin:0;">Alerta de Férias — Retorno Amanhã</h2>
        </div>
        <div style="padding:20px; background:#fff; border:1px solid #e2e8f0; border-top:none;">
            <p>Olá, time de TI!</p>
            <p>Os funcionários abaixo <strong>retornam das férias amanhã</strong> ({amanha.strftime('%d/%m/%Y')}). Por favor, efetuar o <strong>desbloqueio de senhas no AD e Microsoft 365</strong>.</p>
            <table style="width:100%; border-collapse:collapse; margin-top:15px;">
                <thead>
                    <tr style="background:#f8f9fc;">
                        <th style="padding:10px; text-align:left;">Nome</th>
                        <th style="padding:10px; text-align:left;">Data de Retorno</th>
                        <th style="padding:10px; text-align:left;">Observação</th>
                    </tr>
                </thead>
                <tbody>{linhas}</tbody>
            </table>
            <p style="margin-top:20px; color:#64748b; font-size:13px;">
                Este é um e-mail automático do Sistema de Movimentação de Bens.
            </p>
        </div>
    </div>
    """
    ok, msg = email_sender.enviar_email(
        cfg["destinatarios_ferias"],
        cfg["assunto_ferias"],
        corpo,
        tipo="ferias",
    )
    print(f"[{datetime.now()}] Alerta de férias: {msg}")


def enviar_inicio_ferias(cfg):
    hoje = datetime.now().date()
    ferias = _load_json(ARQ_FER, [])
    iniciadas = []
    for registro in ferias:
        if not isinstance(registro, dict):
            continue
        if (registro.get("status") or "").strip() in ("Concluído", "Cancelado"):
            continue
        try:
            inicio = datetime.strptime(registro.get("inicio", ""), "%Y-%m-%d").date()
        except (TypeError, ValueError):
            continue
        if inicio == hoje:
            iniciadas.append(registro)
    if not iniciadas:
        print(f"[{datetime.now()}] Nenhuma férias começa hoje.")
        return

    linhas = "".join(
        "<tr><td style='padding:10px;border-bottom:1px solid #eee;'>"
        f"<strong>{escape(str(registro.get('nome') or '—'))}</strong></td>"
        f"<td style='padding:10px;border-bottom:1px solid #eee;'>{escape(str(registro.get('inicio') or '—'))}</td>"
        f"<td style='padding:10px;border-bottom:1px solid #eee;'>{escape(str(registro.get('fim') or '—'))}</td></tr>"
        for registro in iniciadas
    )
    corpo = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
      <div style="background:#1a2a4a;color:white;padding:20px;">
        <h2 style="margin:0;">Início de férias hoje</h2>
      </div>
      <div style="padding:20px;background:#fff;border:1px solid #e2e8f0;">
        <p>Os períodos de férias abaixo começam hoje ({hoje.strftime('%d/%m/%Y')}):</p>
        <table style="width:100%;border-collapse:collapse;">
          <thead><tr><th align="left">Funcionário</th><th align="left">Início</th><th align="left">Retorno</th></tr></thead>
          <tbody>{linhas}</tbody>
        </table>
      </div>
    </div>
    """
    ok, msg = email_sender.enviar_email(
        cfg["destinatarios_ferias"],
        "[TI] Alerta: início de férias hoje",
        corpo,
        tipo="ferias_inicio",
    )
    print(f"[{datetime.now()}] Alerta de início de férias: {msg}")


def enviar_relatorio_trimestral(cfg):
    hoje = datetime.now()
    if not (hoje.day == 1 and hoje.month in (1, 4, 7, 10)):
        print(f"[{hoje}] Não é dia de relatório trimestral.")
        return

    fim_periodo = datetime(hoje.year, hoje.month, 1)
    ano_inicio = hoje.year
    mes_inicio = hoje.month - 3
    while mes_inicio <= 0:
        mes_inicio += 12
        ano_inicio -= 1
    inicio_periodo = datetime(ano_inicio, mes_inicio, 1)

    movimentos = []
    if os.path.exists(ARQ_MOV):
        with open(ARQ_MOV, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                try:
                    d = datetime.strptime(row["data"], "%Y-%m-%d %H:%M")
                except Exception:
                    continue
                if inicio_periodo <= d < fim_periodo:
                    movimentos.append(row)

    if not movimentos:
        print(f"[{hoje}] Sem movimentações nos últimos 90 dias.")
        return

    total = len(movimentos)
    por_resp = defaultdict(int)
    por_dep = defaultdict(int)
    for m in movimentos:
        if m.get("para_responsavel"):
            por_resp[m["para_responsavel"]] += 1
        if m.get("para_departamento"):
            por_dep[m["para_departamento"]] += 1

    top_resp = sorted(por_resp.items(), key=lambda x: -x[1])[:5]
    top_dep = sorted(por_dep.items(), key=lambda x: -x[1])[:5]

    tabela_mov = "".join(f"""
        <tr>
            <td style="padding:8px; border-bottom:1px solid #eee; font-size:12px;">{escape(str(m.get('data') or ''))}</td>
            <td style="padding:8px; border-bottom:1px solid #eee; font-size:12px;">{escape(str(m.get('patrimonio') or m.get('hostname') or '—'))}</td>
            <td style="padding:8px; border-bottom:1px solid #eee; font-size:12px;">{escape(str(m.get('de_responsavel') or '—'))} → <strong>{escape(str(m.get('para_responsavel') or '—'))}</strong></td>
            <td style="padding:8px; border-bottom:1px solid #eee; font-size:12px;">{escape(str(m.get('de_departamento') or '—'))} → <strong>{escape(str(m.get('para_departamento') or '—'))}</strong></td>
        </tr>
    """ for m in movimentos[-50:])

    linhas_resp = "".join(f'<li><strong>{escape(str(n))}</strong> — {c} movimentação(ões)</li>' for n, c in top_resp)
    linhas_dep = "".join(f'<li><strong>{escape(str(n))}</strong> — {c} movimentação(ões)</li>' for n, c in top_dep)

    corpo = f"""
    <div style="font-family:Arial,sans-serif; max-width:750px; margin:0 auto;">
        <div style="background:#1a2a4a; color:white; padding:20px; border-radius:8px 8px 0 0;">
            <h2 style="margin:0;">Relatório Trimestral de Movimentações</h2>
            <p style="margin:5px 0 0; opacity:0.8; font-size:13px;">Período: {inicio_periodo.strftime('%d/%m/%Y')} até {(fim_periodo - timedelta(days=1)).strftime('%d/%m/%Y')}</p>
        </div>
        <div style="padding:20px; background:#fff; border:1px solid #e2e8f0; border-top:none;">
            <div style="background:#f0f9ff; border-left:4px solid #0ea5e9; padding:15px; margin-bottom:20px;">
                <div style="font-size:13px; color:#64748b; text-transform:uppercase;">Total de Movimentações</div>
                <div style="font-size:32px; font-weight:700; color:#1a2a4a;">{total}</div>
            </div>
            
            <h3 style="color:#1a2a4a;">Top 5 Responsáveis (receberam bens)</h3>
            <ul>{linhas_resp or '<li>—</li>'}</ul>
            
            <h3 style="color:#1a2a4a;">Top 5 Departamentos (receberam bens)</h3>
            <ul>{linhas_dep or '<li>—</li>'}</ul>
            
            <h3 style="color:#1a2a4a; margin-top:25px;">Últimas movimentações</h3>
            <table style="width:100%; border-collapse:collapse;">
                <thead>
                    <tr style="background:#f8f9fc;">
                        <th style="padding:8px; text-align:left; font-size:12px;">Data</th>
                        <th style="padding:8px; text-align:left; font-size:12px;">Bem</th>
                        <th style="padding:8px; text-align:left; font-size:12px;">De → Para (responsável)</th>
                        <th style="padding:8px; text-align:left; font-size:12px;">De → Para (depto)</th>
                    </tr>
                </thead>
                <tbody>{tabela_mov}</tbody>
            </table>
            
            <p style="margin-top:20px; color:#64748b; font-size:13px;">
                Relatório automático do Sistema de Movimentação de Bens.
            </p>
        </div>
    </div>
    """
    ok, msg = email_sender.enviar_email(
        cfg["destinatarios_relatorio"],
        cfg["assunto_relatorio"],
        corpo,
        tipo="relatorio_trimestral",
    )
    print(f"[{hoje}] Relatório trimestral: {msg}")

def main():
    cfg = email_sender.carregar_config()
    if not cfg.get("ativo"):
        print(f"[{datetime.now()}] E-mail desativado. Abortando.")
        return
    if cfg.get("enviar_inicio_ferias"):
        enviar_inicio_ferias(cfg)
    if cfg.get("enviar_ferias"):
        enviar_alertas_ferias(cfg)
    if cfg.get("enviar_relatorio"):
        enviar_relatorio_trimestral(cfg)

if __name__ == "__main__":
    main()