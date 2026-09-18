# -*- coding: utf-8 -*-
from pathlib import Path

BASE = Path(__file__).parent
(BASE / "templates").mkdir(exist_ok=True)

arquivos = {}

arquivos["app.py"] = r'''from flask import Flask, render_template, request, redirect, url_for, flash, Response
import json, csv, os, io, smtplib, threading, time
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.secret_key = 'troque-esta-chave-depois'
BASE = os.path.dirname(os.path.abspath(__file__))
DADOS = os.path.join(BASE, 'dados')
HISTORICO = os.path.join(BASE, 'movimentacoes.csv')
CONFIG = os.path.join(BASE, 'config.json')

CAMPOS = ['id', 'data_hora', 'funcionario', 'bem', 'origem', 'destino', 'observacao']

PADRAO = {
    'funcionarios.json': ["Joao Silva", "Maria Souza", "Carlos Andrade", "Ana Paula"],
    'bens.json': [
        "Notebook Dell Latitude 3420 - PAT0001",
        "Monitor LG 24 - PAT0002",
        "Impressora HP LaserJet - PAT0003",
        "Cadeira Gamer - PAT0004",
        "Celular Samsung A54 - PAT0005"
    ],
    'locais.json': [
        "Almoxarifado Central", "TI - 2 andar", "Financeiro",
        "RH", "Recepcao", "Sala de Reunioes"
    ]
}

CONFIG_PADRAO = {
    "email_ativo": False,
    "frequencia": "mensal",
    "dia_do_mes": 1,
    "horario": "08:00",
    "destinatarios": [],
    "assunto": "Relatorio de Movimentacoes - {periodo}",
    "email_remetente": "",
    "senha_app": "",
    "ultimo_envio": ""
}


# ===================== DADOS =====================

def garantir_dados():
    os.makedirs(DADOS, exist_ok=True)
    for nome, conteudo in PADRAO.items():
        caminho = os.path.join(DADOS, nome)
        if not os.path.exists(caminho):
            with open(caminho, 'w', encoding='utf-8') as f:
                json.dump(conteudo, f, ensure_ascii=False, indent=2)
            print("[auto] Criado:", caminho)
    if not os.path.exists(CONFIG):
        with open(CONFIG, 'w', encoding='utf-8') as f:
            json.dump(CONFIG_PADRAO, f, ensure_ascii=False, indent=2)
        print("[auto] Criado:", CONFIG)


def carregar(nome_arquivo):
    garantir_dados()
    caminho = os.path.join(DADOS, nome_arquivo)
    with open(caminho, encoding='utf-8-sig') as f:
        return json.load(f)


def carregar_config():
    garantir_dados()
    with open(CONFIG, encoding='utf-8-sig') as f:
        cfg = json.load(f)
    for k, v in CONFIG_PADRAO.items():
        cfg.setdefault(k, v)
    return cfg


def salvar_config(cfg):
    with open(CONFIG, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def migrar_csv():
    if not os.path.exists(HISTORICO) or os.path.getsize(HISTORICO) == 0:
        return
    with open(HISTORICO, encoding='utf-8') as f:
        linhas = list(csv.DictReader(f))
    if not linhas or 'id' in linhas[0]:
        return
    for i, linha in enumerate(linhas, start=1):
        linha['id'] = str(i)
    with open(HISTORICO, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS)
        writer.writeheader()
        writer.writerows(linhas)
    print("[migracao] CSV atualizado com coluna ID.")


def ler_movimentacoes():
    if not os.path.exists(HISTORICO) or os.path.getsize(HISTORICO) == 0:
        return []
    with open(HISTORICO, encoding='utf-8') as f:
        return list(csv.DictReader(f))


def escrever_movimentacoes(linhas):
    with open(HISTORICO, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS)
        writer.writeheader()
        writer.writerows(linhas)


def proximo_id(linhas):
    ids = [int(l['id']) for l in linhas if l.get('id', '').isdigit()]
    return str(max(ids, default=0) + 1)


def salvar_movimentacao(registro):
    linhas = ler_movimentacoes()
    registro['id'] = proximo_id(linhas)
    novo = len(linhas) == 0
    with open(HISTORICO, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS)
        if novo:
            writer.writeheader()
        writer.writerow(registro)


def _data(s):
    try:
        return datetime.strptime(s.split(' ')[0], '%d/%m/%Y')
    except Exception:
        return None


def filtrar(linhas, data_ini='', data_fim='', funcionario='', bem='', origem='', destino=''):
    ini = _data(data_ini) if data_ini else None
    fim = _data(data_fim) if data_fim else None

    def bate(l):
        d = _data(l.get('data_hora', ''))
        if ini and (not d or d < ini):
            return False
        if fim and (not d or d > fim):
            return False
        if funcionario and l.get('funcionario') != funcionario:
            return False
        if bem and l.get('bem') != bem:
            return False
        if origem and l.get('origem') != origem:
            return False
        if destino and l.get('destino') != destino:
            return False
        return True

    return [l for l in linhas if bate(l)]


# ===================== E-MAIL =====================

def enviar_email(destinatarios, assunto, corpo_html):
    cfg = carregar_config()
    remetente = cfg.get('email_remetente', '').strip()
    senha = cfg.get('senha_app', '').strip()

    if not remetente or not senha:
        return False, "Configure o e-mail remetente e a senha de app primeiro."
    if not destinatarios:
        return False, "Nenhum destinatario configurado."

    msg = MIMEMultipart('alternative')
    msg['Subject'] = assunto
    msg['From'] = remetente
    msg['To'] = ', '.join(destinatarios)
    msg.attach(MIMEText(corpo_html, 'html', 'utf-8'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=20) as smtp:
            smtp.login(remetente, senha)
            smtp.send_message(msg)
        return True, "E-mail enviado com sucesso!"
    except smtplib.SMTPAuthenticationError:
        return False, "Falha na autenticacao. Verifique e-mail e senha de app."
    except Exception as e:
        return False, f"Erro ao enviar: {e}"


def calcular_periodo(cfg, ultimo_envio):
    agora = datetime.now()
    if ultimo_envio:
        try:
            return datetime.fromisoformat(ultimo_envio), agora
        except Exception:
            pass
    dias = {'diario': 1, 'semanal': 7, 'mensal': 30, 'trimestral': 90}
    d = dias.get(cfg.get('frequencia', 'mensal'), 30)
    return agora - timedelta(days=d), agora


def montar_resumo(cfg, ultimo_envio=None):
    ini, fim = calcular_periodo(cfg, ultimo_envio)
    ini_str = ini.strftime('%d/%m/%Y')
    fim_str = fim.strftime('%d/%m/%Y')

    linhas = ler_movimentacoes()
    filtradas = []
    for l in linhas:
        d = _data(l.get('data_hora', ''))
        if d and ini.date() <= d.date() <= fim.date():
            filtradas.append(l)

    total = len(filtradas)

    def contar(campo):
        c = {}
        for l in filtradas:
            v = l.get(campo, '(vazio)')
            c[v] = c.get(v, 0) + 1
        return sorted(c.items(), key=lambda x: -x[1])

    por_func = contar('funcionario')
    por_bem = contar('bem')
    por_dest = contar('destino')

    nome_mes = ['janeiro', 'fevereiro', 'marco', 'abril', 'maio', 'junho',
                'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
    periodo_nome = f"{nome_mes[fim.month-1].capitalize()} de {fim.year}"

    assunto = cfg.get('assunto', 'Relatorio de Movimentacoes - {periodo}')
    assunto = assunto.replace('{periodo}', periodo_nome)

    def bloco(titulo, itens):
        if not itens:
            return ''
        lis = ''.join(f'<li>{k} — <b>{v}</b></li>' for k, v in itens)
        return f'<h3 style="color:#1a3d6d;margin:22px 0 8px;">{titulo}</h3><ul style="margin:0;padding-left:20px;line-height:1.6;color:#333;">{lis}</ul>'

    corpo = f"""<!DOCTYPE html>
<html><body style="font-family:Segoe UI,Arial,sans-serif;background:#f0f2f5;margin:0;padding:24px;">
<div style="max-width:620px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,.08);">
  <div style="background:#1a3d6d;color:#fff;padding:22px 28px;">
    <h1 style="margin:0;font-size:20px;">Relatorio de Movimentacoes</h1>
    <p style="margin:6px 0 0;color:#cfe0f5;font-size:14px;">Periodo: {ini_str} a {fim_str}</p>
  </div>
  <div style="padding:24px 28px;">
    <p style="font-size:32px;font-weight:700;color:#1a3d6d;margin:0 0 4px;">{total}</p>
    <p style="margin:0;color:#666;font-size:14px;">movimentacao(oes) no periodo</p>
    {bloco('Por funcionario', por_func)}
    {bloco('Bens mais movimentados', por_bem)}
    {bloco('Setores que mais receberam', por_dest)}
    <hr style="border:none;border-top:1px solid #eee;margin:26px 0;">
    <p style="color:#888;font-size:12px;margin:0;">Enviado automaticamente pelo Sistema de Movimentacao de Bens.</p>
  </div>
</div>
</body></html>"""

    return assunto, corpo


def verificar_envio():
    cfg = carregar_config()
    if not cfg.get('email_ativo'):
        return
    agora = datetime.now()
    hh, mm = cfg.get('horario', '08:00').split(':')
    if agora.hour != int(hh) or agora.minute != int(mm):
        return

    freq = cfg.get('frequencia', 'mensal')
    ultimo = cfg.get('ultimo_envio', '')

    if ultimo:
        try:
            ult = datetime.fromisoformat(ultimo)
        except Exception:
            ult = None
    else:
        ult = None

    if ult and (agora - ult).total_seconds() < 60 * 60 * 20:
        return

    if freq in ('mensal', 'trimestral'):
        if agora.day != int(cfg.get('dia_do_mes', 1)):
            return
    if freq == 'mensal' and ult and (agora - ult).days < 25:
        return
    if freq == 'trimestral' and ult and (agora - ult).days < 80:
        return

    assunto, corpo = montar_resumo(cfg, ultimo)
    ok, msg = enviar_email(cfg.get('destinatarios', []), assunto, corpo)
    print(f"[agendador] Envio: {ok} — {msg}")
    if ok:
        cfg['ultimo_envio'] = agora.isoformat()
        salvar_config(cfg)


def loop_agendador():
    print("[agendador] Iniciado.")
    while True:
        try:
            verificar_envio()
        except Exception as e:
            print(f"[agendador] Erro: {e}")
        time.sleep(60)


# ===================== ROTAS =====================

@app.route('/')
def index():
    linhas = ler_movimentacoes()
    ultimas = list(reversed(linhas[-10:]))
    return render_template(
        'index.html',
        funcionarios=carregar('funcionarios.json'),
        bens=carregar('bens.json'),
        locais=carregar('locais.json'),
        historico=ultimas,
        ativo='registrar'
    )


@app.route('/registrar', methods=['POST'])
def registrar():
    registro = {
        'data_hora':   datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
        'funcionario': request.form['funcionario'],
        'bem':         request.form['bem'],
        'origem':      request.form['origem'],
        'destino':     request.form['destino'],
        'observacao':  request.form.get('observacao', '').strip()
    }
    if registro['origem'] == registro['destino']:
        flash('Origem e destino sao iguais. Escolha lugares diferentes.', 'erro')
        return redirect(url_for('index'))
    salvar_movimentacao(registro)
    flash('Movimentacao registrada com sucesso!', 'ok')
    return redirect(url_for('index'))


@app.route('/historico')
def historico():
    linhas = list(reversed(ler_movimentacoes()))
    filtros = {
        'data_ini':    request.args.get('data_ini', ''),
        'data_fim':    request.args.get('data_fim', ''),
        'funcionario': request.args.get('funcionario', ''),
        'bem':         request.args.get('bem', ''),
        'origem':      request.args.get('origem', ''),
        'destino':     request.args.get('destino', '')
    }
    filtradas = filtrar(linhas, **filtros)
    return render_template(
        'historico.html',
        movimentacoes=filtradas,
        total=len(filtradas),
        funcionarios=carregar('funcionarios.json'),
        bens=carregar('bens.json'),
        locais=carregar('locais.json'),
        filtros=filtros,
        ativo='historico'
    )


@app.route('/editar/<id>', methods=['GET', 'POST'])
def editar(id):
    linhas = ler_movimentacoes()
    alvo = next((l for l in linhas if l['id'] == id), None)
    if not alvo:
        flash('Movimentacao nao encontrada.', 'erro')
        return redirect(url_for('historico'))

    if request.method == 'POST':
        alvo['funcionario'] = request.form['funcionario']
        alvo['bem'] = request.form['bem']
        alvo['origem'] = request.form['origem']
        alvo['destino'] = request.form['destino']
        alvo['observacao'] = request.form.get('observacao', '').strip()
        if alvo['origem'] == alvo['destino']:
            flash('Origem e destino sao iguais.', 'erro')
            return redirect(url_for('editar', id=id))
        escrever_movimentacoes(linhas)
        flash('Movimentacao atualizada!', 'ok')
        return redirect(url_for('historico'))

    return render_template(
        'editar.html',
        mov=alvo,
        funcionarios=carregar('funcionarios.json'),
        bens=carregar('bens.json'),
        locais=carregar('locais.json'),
        ativo='historico'
    )


@app.route('/excluir/<id>', methods=['POST'])
def excluir(id):
    linhas = ler_movimentacoes()
    novas = [l for l in linhas if l['id'] != id]
    if len(novas) == len(linhas):
        flash('Movimentacao nao encontrada.', 'erro')
    else:
        escrever_movimentacoes(novas)
        flash('Movimentacao excluida.', 'ok')
    return redirect(url_for('historico'))


@app.route('/configuracoes', methods=['GET', 'POST'])
def configuracoes():
    cfg = carregar_config()
    if request.method == 'POST':
        cfg['email_ativo'] = 'email_ativo' in request.form
        cfg['frequencia'] = request.form.get('frequencia', 'mensal')
        cfg['dia_do_mes'] = int(request.form.get('dia_do_mes', 1) or 1)
        cfg['horario'] = request.form.get('horario', '08:00')
        lista = request.form.get('destinatarios', '')
        cfg['destinatarios'] = [d.strip() for d in lista.split(',') if d.strip()]
        cfg['assunto'] = request.form.get('assunto', 'Relatorio de Movimentacoes - {periodo}')
        cfg['email_remetente'] = request.form.get('email_remetente', '').strip()
        senha = request.form.get('senha_app', '').strip()
        if senha:
            cfg['senha_app'] = senha
        salvar_config(cfg)
        flash('Configuracoes salvas!', 'ok')
        return redirect(url_for('configuracoes'))
    return render_template('configuracoes.html', cfg=cfg, ativo='config')


@app.route('/testar-email')
def testar_email():
    cfg = carregar_config()
    assunto, corpo = montar_resumo(cfg, cfg.get('ultimo_envio', ''))
    assunto = "[TESTE] " + assunto
    ok, msg = enviar_email(cfg.get('destinatarios', []), assunto, corpo)
    flash(msg, 'ok' if ok else 'erro')
    return redirect(url_for('configuracoes'))


@app.route('/exportar')
def exportar():
    linhas = list(reversed(ler_movimentacoes()))
    filtros = {
        'data_ini':    request.args.get('data_ini', ''),
        'data_fim':    request.args.get('data_fim', ''),
        'funcionario': request.args.get('funcionario', ''),
        'bem':         request.args.get('bem', ''),
        'origem':      request.args.get('origem', ''),
        'destino':     request.args.get('destino', '')
    }
    filtradas = filtrar(linhas, **filtros)
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CAMPOS)
    writer.writeheader()
    writer.writerows(filtradas)
    return Response(
        out.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=movimentacoes.csv'}
    )


if __name__ == '__main__':
    garantir_dados()
    migrar_csv()
    t = threading.Thread(target=loop_agendador, daemon=True)
    t.start()
    app.run(debug=True, host='0.0.0.0', port=5000)
'''

arquivos["templates/configuracoes.html"] = r'''{% extends "base.html" %}
{% block titulo %}Configuracoes{% endblock %}
{% block conteudo %}

<h1>Configuracoes de E-mail</h1>
<p class="subtitulo">Defina como e quando os relatorios serao enviados</p>

<form class="card grid" action="/configuracoes" method="POST">

  <div class="campo full" style="flex-direction:row;align-items:center;gap:8px;">
    <input type="checkbox" name="email_ativo" id="email_ativo"
           {% if cfg.email_ativo %}checked{% endif %} style="width:auto;">
    <label for="email_ativo" style="margin:0;">Ativar envio automatico de relatorios</label>
  </div>

  <div class="campo">
    <label>Frequencia</label>
    <select name="frequencia">
      <option value="diario" {% if cfg.frequencia == 'diario' %}selected{% endif %}>Diario</option>
      <option value="semanal" {% if cfg.frequencia == 'semanal' %}selected{% endif %}>Semanal</option>
      <option value="mensal" {% if cfg.frequencia == 'mensal' %}selected{% endif %}>Mensal</option>
      <option value="trimestral" {% if cfg.frequencia == 'trimestral' %}selected{% endif %}>Trimestral</option>
    </select>
  </div>

  <div class="campo">
    <label>Dia (mensal/trimestral)</label>
    <input type="number" name="dia_do_mes" min="1" max="28" value="{{ cfg.dia_do_mes }}">
  </div>

  <div class="campo">
    <label>Horario do envio</label>
    <input type="time" name="horario" value="{{ cfg.horario }}">
  </div>

  <div class="campo">
    <label>Assunto do e-mail</label>
    <input type="text" name="assunto" value="{{ cfg.assunto }}">
  </div>

  <div class="campo full">
    <label>Destinatarios (separe por virgula)</label>
    <input type="text" name="destinatarios"
           value="{{ cfg.destinatarios|join(', ') }}"
           placeholder="chefe@empresa.com, ti@empresa.com">
  </div>

  <div class="campo">
    <label>E-mail remetente (quem envia)</label>
    <input type="email" name="email_remetente"
           value="{{ cfg.email_remetente }}"
           placeholder="sistema.bens@gmail.com">
  </div>

  <div class="campo">
    <label>Senha de app (do Gmail)</label>
    <input type="password" name="senha_app"
           placeholder="{% if cfg.senha_app %}(deixe vazio para manter){% else %}cole aqui{% endif %}">
  </div>

  <div class="campo full" style="display:flex;gap:10px;flex-wrap:wrap;">
    <button type="submit">Salvar configuracoes</button>
    <a href="/testar-email" class="botao secundario">Enviar e-mail de teste agora</a>
  </div>
</form>

<div class="card">
  <h2 style="color:#1a3d6d;font-size:18px;margin-top:0;">Como funciona</h2>
  <ul style="line-height:1.7;color:#444;">
    <li><b>Frequencia</b>: de quanto em quanto tempo o resumo vai por e-mail.</li>
    <li><b>Dia</b>: para mensal/trimestral, o dia do mes em que o envio acontece.</li>
    <li><b>Horario</b>: a hora exata do envio (o sistema verifica a cada minuto).</li>
    <li><b>Destinatarios</b>: quem recebe o resumo. Separe varios por virgula.</li>
    <li><b>E-mail remetente</b>: conta do Gmail criada para o sistema.</li>
    <li><b>Senha de app</b>: gerada em myaccount.google.com/apppasswords (16 letras).</li>
    <li><b>Assunto</b>: use <code>{periodo}</code> para inserir o periodo automaticamente.</li>
  </ul>
  <p style="color:#186c36;font-size:13px;background:#d5f4dd;padding:10px;border-radius:6px;">
    <b>Dica:</b> preencha os dados, clique em <b>Salvar</b> e depois em
    <b>Enviar e-mail de teste agora</b> para validar.
  </p>
</div>

{% endblock %}
'''

for nome, conteudo in arquivos.items():
    caminho = BASE / nome
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(conteudo, encoding="utf-8")
    print("[ok]", caminho)

print()
print("=" * 50)
print("Instalacao concluida!")
print("=" * 50)