# -*- coding: utf-8 -*-
import os
import json
import tempfile
from datetime import datetime
from html import escape
from flask import Blueprint, render_template, request, jsonify, session
import email_sender

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DADOS = os.path.join(BASE_DIR, "dados")
ARQ_SOLICITACOES = os.path.join(DADOS, "solicitacoes_reuniao.json")
ARQ_CONFIG_REUNIOES = os.path.join(DADOS, "config_reunioes.json")

reunioes_bp = Blueprint('reunioes', __name__)


def _carregar_config():
    if not os.path.exists(ARQ_CONFIG_REUNIOES):
        return {"destinatarios": []}
    with open(ARQ_CONFIG_REUNIOES, "r", encoding="utf-8") as f:
        return json.load(f)


def _carregar_solicitacoes():
    if not os.path.exists(ARQ_SOLICITACOES):
        return []
    with open(ARQ_SOLICITACOES, "r", encoding="utf-8-sig") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def _salvar_solicitacoes(lista):
    os.makedirs(DADOS, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".reuniao-", suffix=".tmp", dir=DADOS)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(lista, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, ARQ_SOLICITACOES)
    except Exception:
        if os.path.exists(temp):
            os.unlink(temp)
        raise


# ============================================================
# VALIDAÇÃO DE DATA E HORA
# ============================================================

def _validar_data_hora(data_str, hora_inicio, hora_fim):
    """
    Valida se a data/hora fazem sentido.
    Retorna (ok, mensagem_erro).
    """
    # 1. Data não pode estar no passado
    try:
        data_solicitada = datetime.strptime(data_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return False, "Data inválida. Use o formato dd/mm/aaaa no campo."

    hoje = datetime.now().date()
    if data_solicitada < hoje:
        return False, "Não é possível agendar uma reunião para uma data que já passou."

    # 2. Se a data for hoje, a hora de início não pode ser no passado
    if data_solicitada == hoje:
        try:
            hora_ini = datetime.strptime(hora_inicio, "%H:%M").time()
        except (ValueError, TypeError):
            return False, "Hora de início inválida."

        agora = datetime.now()
        # Compara a hora solicitada com a hora atual
        hora_agora = agora.time()
        # Só bloqueia se a hora de início já passou (com margem de 1 minuto)
        if (hora_ini.hour, hora_ini.minute) < (hora_agora.hour, hora_agora.minute):
            return False, "Para o dia de hoje, o horário de início já passou. Escolha um horário futuro."

    # 3. Se hora fim foi informada, ela precisa ser MAIOR que hora início
    if hora_fim and hora_fim != 'Não informado':
        try:
            h_ini = datetime.strptime(hora_inicio, "%H:%M")
            h_fim = datetime.strptime(hora_fim, "%H:%M")
        except (ValueError, TypeError):
            return False, "Horário inválido. Use o formato HH:MM."

        if h_fim <= h_ini:
            return False, "O horário de término deve ser depois do horário de início."

    return True, None


# ============================================================
# HELPERS DE E-MAIL
# ============================================================

def _texto_horario(sol):
    inicio = sol.get('hora_inicio', '')
    fim = sol.get('hora_fim', '')
    if not fim or fim == 'Não informado':
        return f"A partir das {inicio}"
    return f"{inicio} às {fim}"


def _lista_recursos_html(sol):
    recursos = []
    if sol.get("cafe"):
        recursos.append(f"Café para {sol.get('cafe_qtd')} pessoa(s)")
    if sol.get("agua"):
        recursos.append(f"Água ({sol.get('agua_qtd')} garrafa(s))")
    if sol.get("refrigerante"):
        recursos.append(f"Refrigerante ({sol.get('refrigerante_qtd')} unidade(s))")
    if recursos:
        return "".join(
            f'<li style="padding:4px 0; font-size:14px;">{escape(r)}</li>'
            for r in recursos
        )
    return '<li style="color:#94a3b8; font-size:13px;">Nenhum recurso adicional solicitado</li>'


def _bloco_obs_html(sol):
    if not sol.get("observacao"):
        return ""
    return f"""
    <h3 style="margin-top:20px; color:#1a2a4a; font-size:14px;">Observação do Solicitante</h3>
    <p style="background:#f8fafc; padding:12px; border-left:3px solid #1a2a4a; font-size:14px; margin:0;">
        {escape(sol['observacao'])}
    </p>
    """


def _tabela_dados_html(sol):
    if sol.get("importancia") == "IMPORTANTE":
        cor_imp = "#dc2626"
        txt_imp = "IMPORTANTE"
    else:
        cor_imp = "#0d6efd"
        txt_imp = "NORMAL"

    data_br = sol.get('data', '')
    if data_br and '-' in data_br:
        try:
            ano, mes, dia = data_br.split('-')
            data_br = f"{dia}/{mes}/{ano}"
        except ValueError:
            pass

    return f"""
    <table style="width:100%; border-collapse:collapse; margin-top:15px;">
        <tr>
            <td style="padding:10px; background:#f8fafc; font-weight:600; width:35%; font-size:14px;">Solicitante</td>
            <td style="padding:10px; font-size:14px;">{escape(sol.get('solicitante',''))}</td>
        </tr>
        <tr>
            <td style="padding:10px; background:#f8fafc; font-weight:600; font-size:14px;">Sala</td>
            <td style="padding:10px; font-size:14px;"><strong>{escape(sol.get('sala',''))}</strong></td>
        </tr>
        <tr>
            <td style="padding:10px; background:#f8fafc; font-weight:600; font-size:14px;">Data</td>
            <td style="padding:10px; font-size:14px;">{escape(data_br)}</td>
        </tr>
        <tr>
            <td style="padding:10px; background:#f8fafc; font-weight:600; font-size:14px;">Horário</td>
            <td style="padding:10px; font-size:14px;">
                {escape(_texto_horario(sol))}
                <em style="color:#64748b; font-size:12px;">(aproximado para ciência de todos)</em>
            </td>
        </tr>
        <tr>
            <td style="padding:10px; background:#f8fafc; font-weight:600; font-size:14px;">Importância</td>
            <td style="padding:10px; font-size:14px; color:{cor_imp}; font-weight:700;">{txt_imp}</td>
        </tr>
        <tr>
            <td style="padding:10px; background:#f8fafc; font-weight:600; font-size:14px;">Limpeza</td>
            <td style="padding:10px; font-size:14px;">{escape(sol.get('limpeza','Não precisa'))}</td>
        </tr>
    </table>
    """


def _montar_corpo_email(sol):
    return f"""
    <div style="font-family:Arial,sans-serif; max-width:620px; margin:0 auto;">
        <div style="background:#1a2a4a; color:white; padding:20px; border-radius:8px 8px 0 0;">
            <h2 style="margin:0;">Solicitação de Reserva de Sala</h2>
            <p style="margin:5px 0 0; opacity:0.8; font-size:13px;">
                Enviada em {datetime.now().strftime('%d/%m/%Y às %H:%M')}
            </p>
        </div>
        <div style="padding:20px; background:#fff; border:1px solid #e2e8f0; border-top:none; border-radius:0 0 8px 8px;">
            <p style="margin-top:0;">Olá, time!</p>
            <p>Uma nova solicitação de reserva de sala foi registrada:</p>
            {_tabela_dados_html(sol)}
            <h3 style="margin-top:20px; color:#1a2a4a; font-size:14px;">Recursos Solicitados</h3>
            <ul style="padding-left:20px; margin:0;">{_lista_recursos_html(sol)}</ul>
            {_bloco_obs_html(sol)}
            <p style="margin-top:24px; color:#64748b; font-size:12px; border-top:1px solid #e2e8f0; padding-top:12px;">
                Este é um e-mail automático do Sistema de Movimentação de Bens. Por favor, não responda diretamente.
            </p>
        </div>
    </div>
    """


def _montar_email_cancelamento(sol):
    motivo = sol.get('motivo_cancelamento') or 'Não informado'
    return f"""
    <div style="font-family:Arial,sans-serif; max-width:620px; margin:0 auto;">
        <div style="background:#dc2626; color:white; padding:20px; border-radius:8px 8px 0 0;">
            <h2 style="margin:0;">REUNIÃO CANCELADA</h2>
            <p style="margin:5px 0 0; opacity:0.9; font-size:13px;">
                Cancelada em {datetime.now().strftime('%d/%m/%Y às %H:%M')} por {escape(sol.get('cancelada_por','—'))}
            </p>
        </div>
        <div style="padding:20px; background:#fff; border:1px solid #e2e8f0; border-top:none; border-radius:0 0 8px 8px;">
            <p style="margin-top:0;">Olá, time!</p>
            <p>A seguinte reserva foi <strong style="color:#dc2626;">cancelada</strong>. Favor desconsiderar a preparação.</p>
            {_tabela_dados_html(sol)}
            <h3 style="margin-top:20px; color:#1a2a4a; font-size:14px;">Recursos que seriam solicitados</h3>
            <ul style="padding-left:20px; margin:0;">{_lista_recursos_html(sol)}</ul>
            <h3 style="margin-top:20px; color:#dc2626; font-size:14px;">Motivo do Cancelamento</h3>
            <p style="background:#fef2f2; padding:12px; border-left:3px solid #dc2626; font-size:14px; margin:0;">
                {escape(motivo)}
            </p>
            <p style="margin-top:24px; color:#64748b; font-size:12px; border-top:1px solid #e2e8f0; padding-top:12px;">
                Este é um e-mail automático do Sistema de Movimentação de Bens. Por favor, não responda diretamente.
            </p>
        </div>
    </div>
    """


def _montar_email_alteracao(sol, alteracoes):
    linhas = ""
    for alt in alteracoes:
        linhas += f"""
        <tr>
            <td style="padding:10px; background:#f8fafc; font-weight:600; font-size:14px; width:30%;">{escape(alt['campo'])}</td>
            <td style="padding:10px; font-size:14px; color:#991b1b; text-decoration:line-through;">{escape(str(alt['antes']))}</td>
            <td style="padding:10px; font-size:14px; color:#15803d; font-weight:600;">{escape(str(alt['depois']))}</td>
        </tr>
        """

    return f"""
    <div style="font-family:Arial,sans-serif; max-width:620px; margin:0 auto;">
        <div style="background:#d97706; color:white; padding:20px; border-radius:8px 8px 0 0;">
            <h2 style="margin:0;">REUNIÃO ALTERADA</h2>
            <p style="margin:5px 0 0; opacity:0.9; font-size:13px;">
                Alterada em {datetime.now().strftime('%d/%m/%Y às %H:%M')} por {escape(sol.get('alterada_por','—'))}
            </p>
        </div>
        <div style="padding:20px; background:#fff; border:1px solid #e2e8f0; border-top:none; border-radius:0 0 8px 8px;">
            <p style="margin-top:0;">Olá, time!</p>
            <p>A seguinte reserva sofreu <strong style="color:#d97706;">alterações</strong>. Favor atualizar a preparação.</p>

            <h3 style="margin-top:20px; color:#d97706; font-size:14px;">O que mudou</h3>
            <table style="width:100%; border-collapse:collapse;">
                <tr style="background:#f8fafc;">
                    <th style="padding:10px; text-align:left; font-size:13px;">Campo</th>
                    <th style="padding:10px; text-align:left; font-size:13px;">Antes</th>
                    <th style="padding:10px; text-align:left; font-size:13px;">Depois</th>
                </tr>
                {linhas}
            </table>

            <h3 style="margin-top:24px; color:#1a2a4a; font-size:14px;">Dados Atualizados</h3>
            {_tabela_dados_html(sol)}

            <h3 style="margin-top:20px; color:#1a2a4a; font-size:14px;">Recursos Solicitados (atualizado)</h3>
            <ul style="padding-left:20px; margin:0;">{_lista_recursos_html(sol)}</ul>

            {_bloco_obs_html(sol)}

            <p style="margin-top:24px; color:#64748b; font-size:12px; border-top:1px solid #e2e8f0; padding-top:12px;">
                Este é um e-mail automático do Sistema de Movimentação de Bens. Por favor, não responda diretamente.
            </p>
        </div>
    </div>
    """


# ============================================================
# ROTAS
# ============================================================

@reunioes_bp.route('/reunioes')
def reunioes_view():
    todas = _carregar_solicitacoes()
    agora = datetime.now()

    import permissoes
    usuario_logado = session.get('usuario', '')
    eh_admin = permissoes.tem_permissao(session.get('tipo', ''), '*')

    proximas = []
    historico = []

    for s in todas:
        s['pode_editar'] = eh_admin or (s.get('usuario') == usuario_logado)
        status = s.get('status', 'ATIVA')
        if status == 'CANCELADA':
            historico.append(s)
            continue

        hora_fim_para_ordenacao = s.get('hora_fim') or '23:59'
        if hora_fim_para_ordenacao == 'Não informado':
            hora_fim_para_ordenacao = '23:59'

        try:
            data_hora = datetime.strptime(
                f"{s['data']} {hora_fim_para_ordenacao}",
                "%Y-%m-%d %H:%M"
            )
            if data_hora >= agora:
                proximas.append(s)
            else:
                historico.append(s)
        except (ValueError, KeyError):
            historico.append(s)

    proximas.sort(key=lambda x: f"{x.get('data', '')} {x.get('hora_inicio', '')}")
    historico = list(reversed(historico))[:50]

    return render_template(
        'reunioes.html',
        proximas=proximas,
        historico=historico,
        total_proximas=len(proximas),
        total_historico=len(historico),
    )


@reunioes_bp.route('/reunioes/solicitar', methods=['POST'])
def solicitar():
    dados = request.get_json(silent=True)
    if not dados:
        return jsonify({"ok": False, "msg": "Dados inválidos."}), 400

    if not dados.get('sala'):
        return jsonify({"ok": False, "msg": "Selecione uma sala."}), 400
    if not dados.get('data'):
        return jsonify({"ok": False, "msg": "Informe a data."}), 400
    if not dados.get('hora_inicio'):
        return jsonify({"ok": False, "msg": "Informe o horário de início."}), 400
    if not dados.get('limpeza'):
        return jsonify({"ok": False, "msg": "Informe se precisa de limpeza."}), 400

    hora_fim = (dados.get('hora_fim') or '').strip()
    if not hora_fim:
        hora_fim = 'Não informado'

    ok_data, msg_data = _validar_data_hora(
        dados.get('data'), dados.get('hora_inicio'), hora_fim
    )
    if not ok_data:
        return jsonify({"ok": False, "msg": msg_data}), 400

    try:
        cafe_qtd = int(dados.get('cafe_qtd') or 0)
        agua_qtd = int(dados.get('agua_qtd') or 0)
        refri_qtd = int(dados.get('refrigerante_qtd') or 0)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "msg": "Quantidades inválidas."}), 400

    lista = _carregar_solicitacoes()

    solicitacao = {
        "id": (max([s.get("id", 0) for s in lista]) + 1) if lista else 1,
        "solicitante": session.get('nome', session.get('usuario', '')),
        "usuario": session.get('usuario', ''),
        "sala": dados.get('sala'),
        "data": dados.get('data'),
        "hora_inicio": dados.get('hora_inicio'),
        "hora_fim": hora_fim,
        "limpeza": dados.get('limpeza'),
        "cafe": bool(dados.get('cafe')),
        "cafe_qtd": cafe_qtd,
        "agua": bool(dados.get('agua')),
        "agua_qtd": agua_qtd,
        "refrigerante": bool(dados.get('refrigerante')),
        "refrigerante_qtd": refri_qtd,
        "importancia": dados.get('importancia', 'NORMAL'),
        "observacao": (dados.get('observacao') or '').strip()[:1000],
        "criado_em": datetime.now().isoformat(timespec='seconds'),
        "status": "ATIVA",
    }

    # 1. SALVA PRIMEIRO
    lista.append(solicitacao)
    _salvar_solicitacoes(lista)

    # 2. Tenta enviar o e-mail
    cfg = _carregar_config()
    destinatarios = cfg.get('destinatarios', [])

    if not destinatarios:
        return jsonify({
            "ok": True,
            "msg": "Solicitação registrada, mas nenhum destinatário está configurado.",
            "aviso": "⚠️ O e-mail não foi enviado porque não há destinatários configurados."
        })

    assunto = (
        f"[Reunião] {solicitacao['sala']} - {solicitacao['data']} "
        f"{solicitacao['hora_inicio']} - {solicitacao['solicitante']}"
    )
    corpo = _montar_corpo_email(solicitacao)
    ok, msg = email_sender.enviar_email(
        destinatarios, assunto, corpo, tipo="reuniao"
    )

    if not ok:
        return jsonify({
            "ok": True,
            "msg": "Solicitação registrada com sucesso!",
            "aviso": f"⚠️ O e-mail de aviso falhou ({msg}). Avise a Copa/Recepção manualmente."
        })

    return jsonify({"ok": True, "msg": "Solicitação enviada com sucesso!"})


@reunioes_bp.route('/reunioes/cancelar', methods=['POST'])
def cancelar():
    dados = request.get_json(silent=True)
    if not dados or not dados.get('id'):
        return jsonify({"ok": False, "msg": "ID inválido."}), 400

    lista = _carregar_solicitacoes()
    alvo = next((s for s in lista if s.get('id') == dados['id']), None)
    if not alvo:
        return jsonify({"ok": False, "msg": "Solicitação não encontrada."}), 404

    if alvo.get('status') == 'CANCELADA':
        return jsonify({"ok": False, "msg": "Esta solicitação já está cancelada."}), 400

    motivo = (dados.get('motivo') or '').strip()[:500]
    alvo['status'] = 'CANCELADA'
    alvo['cancelada_em'] = datetime.now().isoformat(timespec='seconds')
    alvo['cancelada_por'] = session.get('nome', session.get('usuario', ''))
    alvo['motivo_cancelamento'] = motivo

    # 1. SALVA PRIMEIRO
    _salvar_solicitacoes(lista)

    # 2. Tenta enviar e-mail
    cfg = _carregar_config()
    destinatarios = cfg.get('destinatarios', [])

    if not destinatarios:
        return jsonify({
            "ok": True,
            "msg": "Reunião cancelada.",
            "aviso": "⚠️ E-mail não enviado: nenhum destinatário configurado."
        })

    assunto = f"[Reunião CANCELADA] {alvo['sala']} - {alvo['data']} {alvo['hora_inicio']}"
    corpo = _montar_email_cancelamento(alvo)
    ok, msg = email_sender.enviar_email(destinatarios, assunto, corpo, tipo="reuniao_cancel")

    if not ok:
        return jsonify({
            "ok": True,
            "msg": "Reunião cancelada com sucesso!",
            "aviso": f"⚠️ O e-mail de aviso falhou ({msg}). Avise a Copa/Recepção manualmente."
        })

    return jsonify({"ok": True, "msg": "Reunião cancelada e e-mail enviado."})


@reunioes_bp.route('/reunioes/reagendar', methods=['POST'])
def reagendar():
    dados = request.get_json(silent=True)
    if not dados or not dados.get('id'):
        return jsonify({"ok": False, "msg": "ID inválido."}), 400

    lista = _carregar_solicitacoes()
    alvo = next((s for s in lista if s.get('id') == dados['id']), None)
    if not alvo:
        return jsonify({"ok": False, "msg": "Solicitação não encontrada."}), 404

    if alvo.get('status') == 'CANCELADA':
        return jsonify({"ok": False, "msg": "Não é possível alterar uma solicitação cancelada."}), 400

    if not dados.get('sala') or not dados.get('data') or not dados.get('hora_inicio') or not dados.get('limpeza'):
        return jsonify({"ok": False, "msg": "Preencha todos os campos obrigatórios."}), 400

    hora_fim = (dados.get('hora_fim') or '').strip()
    if not hora_fim:
        hora_fim = 'Não informado'

    ok_data, msg_data = _validar_data_hora(
        dados.get('data'), dados.get('hora_inicio'), hora_fim
    )
    if not ok_data:
        return jsonify({"ok": False, "msg": msg_data}), 400

    antigo = {k: v for k, v in alvo.items()}

    try:
        cafe_qtd = int(dados.get('cafe_qtd') or 0)
        agua_qtd = int(dados.get('agua_qtd') or 0)
        refri_qtd = int(dados.get('refrigerante_qtd') or 0)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "msg": "Quantidades inválidas."}), 400

    alvo['sala'] = dados.get('sala')
    alvo['data'] = dados.get('data')
    alvo['hora_inicio'] = dados.get('hora_inicio')
    alvo['hora_fim'] = hora_fim
    alvo['limpeza'] = dados.get('limpeza')
    alvo['cafe'] = bool(dados.get('cafe'))
    alvo['cafe_qtd'] = cafe_qtd
    alvo['agua'] = bool(dados.get('agua'))
    alvo['agua_qtd'] = agua_qtd
    alvo['refrigerante'] = bool(dados.get('refrigerante'))
    alvo['refrigerante_qtd'] = refri_qtd
    alvo['importancia'] = dados.get('importancia', alvo.get('importancia'))
    alvo['observacao'] = (dados.get('observacao') or '').strip()[:1000]

    alvo['status'] = 'REAGENDADA'
    alvo['alterada_em'] = datetime.now().isoformat(timespec='seconds')
    alvo['alterada_por'] = session.get('nome', session.get('usuario', ''))

    rotulos = {
        'sala': 'Sala', 'data': 'Data', 'hora_inicio': 'Hora Início', 'hora_fim': 'Hora Fim',
        'limpeza': 'Limpeza', 'importancia': 'Importância', 'observacao': 'Observação',
        'cafe': 'Café', 'agua': 'Água', 'refrigerante': 'Refrigerante',
    }
    alteracoes = []
    for campo, rotulo in rotulos.items():
        antes = antigo.get(campo)
        depois = alvo.get(campo)
        if campo in ('cafe', 'agua', 'refrigerante'):
            antes_txt = 'Sim' if antes else 'Não'
            depois_txt = 'Sim' if depois else 'Não'
        else:
            antes_txt = str(antes or '—')
            depois_txt = str(depois or '—')
        if antes_txt != depois_txt:
            alteracoes.append({'campo': rotulo, 'antes': antes_txt, 'depois': depois_txt})

    if not alteracoes:
        return jsonify({"ok": False, "msg": "Nenhuma alteração detectada."}), 400

    # 1. SALVA PRIMEIRO
    _salvar_solicitacoes(lista)

    # 2. Tenta enviar e-mail
    cfg = _carregar_config()
    destinatarios = cfg.get('destinatarios', [])

    if not destinatarios:
        return jsonify({
            "ok": True,
            "msg": "Reunião alterada.",
            "aviso": "⚠️ E-mail não enviado: nenhum destinatário configurado."
        })

    assunto = f"[Reunião ALTERADA] {alvo['sala']} - {alvo['data']} {alvo['hora_inicio']}"
    corpo = _montar_email_alteracao(alvo, alteracoes)
    ok, msg = email_sender.enviar_email(destinatarios, assunto, corpo, tipo="reuniao_alt")

    if not ok:
        return jsonify({
            "ok": True,
            "msg": "Reunião alterada com sucesso!",
            "aviso": f"⚠️ O e-mail de aviso falhou ({msg}). Avise a Copa/Recepção manualmente."
        })

    return jsonify({"ok": True, "msg": "Reunião alterada e e-mail de aviso enviado."})