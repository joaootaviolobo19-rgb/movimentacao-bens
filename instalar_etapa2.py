# -*- coding: utf-8 -*-
from pathlib import Path

BASE = Path(__file__).parent
(BASE / "templates").mkdir(exist_ok=True)

arquivos = {}

arquivos["app.py"] = r'''from flask import Flask, render_template, request, redirect, url_for, flash, Response
import json, csv, os, io
from datetime import datetime

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
    "senha_app": ""
}


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
        return json.load(f)


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
    app.run(debug=True)
'''

arquivos["templates/base.html"] = r'''<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>{% block titulo %}Sistema de Bens{% endblock %}</title>
<style>
  * { box-sizing: border-box; font-family: 'Segoe UI', Arial, sans-serif; }
  body { background: #f0f2f5; margin: 0; }
  .container { max-width: 1100px; margin: 0 auto; padding: 30px 20px; }
  h1 { color: #1a3d6d; margin: 0 0 5px; }
  .subtitulo { color: #666; margin-bottom: 25px; }
  .topbar { background: #1a3d6d; }
  .topbar-inner { max-width: 1100px; margin: 0 auto; padding: 0 20px;
                  display: flex; align-items: center; }
  .topbar .logo { color: #fff; font-weight: 700; padding: 18px 20px 18px 0; font-size: 16px; }
  .topbar a { color: #cfe0f5; text-decoration: none; padding: 18px 20px;
              font-weight: 600; font-size: 14px; border-bottom: 3px solid transparent;
              display: inline-block; }
  .topbar a:hover { color: #fff; background: rgba(255,255,255,.06); }
  .topbar a.ativo { color: #fff; border-bottom-color: #4ea1ff; }
  .flash { padding: 12px 16px; border-radius: 8px; margin-bottom: 18px;
           font-weight: 600; font-size: 14px; }
  .flash.ok   { background: #d5f4dd; color: #186c36; border: 1px solid #a7ddb6; }
  .flash.erro { background: #fbe0e0; color: #a11a1a; border: 1px solid #f0b4b4; }
  .card { background: #fff; padding: 28px; border-radius: 12px;
          box-shadow: 0 4px 16px rgba(0,0,0,.08); margin-bottom: 25px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
  .campo { display: flex; flex-direction: column; }
  .campo.full { grid-column: 1 / -1; }
  label { font-weight: 600; color: #333; margin-bottom: 6px; font-size: 14px; }
  select, input, textarea { padding: 11px 14px; border: 1px solid #d0d7de;
    border-radius: 8px; font-size: 14px; background: #fff; outline: none; }
  select:focus, input:focus, textarea:focus { border-color: #1a73e8;
    box-shadow: 0 0 0 3px rgba(26,115,232,.15); }
  button, .botao { padding: 12px 20px; background: #1a73e8; color: #fff; border: none;
    border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer;
    text-decoration: none; display: inline-block; }
  button:hover, .botao:hover { background: #1558b0; }
  .botao.secundario { background: #6b7280; }
  .botao.secundario:hover { background: #4b5563; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { padding: 10px; border-bottom: 1px solid #eee; text-align: left;
           vertical-align: top; }
  th { background: #1a3d6d; color: #fff; font-weight: 600; }
  tr:hover td { background: #f9fbff; }
  .acoes { display: flex; gap: 6px; }
  .acoes a, .acoes button { padding: 5px 10px; font-size: 12px; border-radius: 6px;
    background: #eef2f7; color: #1a3d6d; border: none; text-decoration: none;
    cursor: pointer; font-weight: 600; }
  .acoes a:hover { background: #dbe6f3; }
  .acoes button.perigo { background: #fbe0e0; color: #a11a1a; }
  .acoes button.perigo:hover { background: #f0b4b4; }
  .filtros { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; align-items: end; }
  .filtros .botoes { grid-column: 1 / -1; display: flex; gap: 10px; margin-top: 5px; flex-wrap: wrap; }
  .contador { font-weight: 700; color: #1a3d6d; margin: 0 0 14px; font-size: 15px; }
  @media (max-width: 700px) {
    .grid, .filtros { grid-template-columns: 1fr; }
    .topbar-inner { flex-wrap: wrap; }
  }
</style>
</head>
<body>
<div class="topbar">
  <div class="topbar-inner">
    <span class="logo">Sistema de Bens</span>
    <a href="/" class="{% if ativo == 'registrar' %}ativo{% endif %}">Registrar</a>
    <a href="/historico" class="{% if ativo == 'historico' %}ativo{% endif %}">Historico</a>
    <a href="/configuracoes" class="{% if ativo == 'config' %}ativo{% endif %}">Configuracoes</a>
  </div>
</div>
<div class="container">
  {% with mensagens = get_flashed_messages(with_categories=true) %}
    {% for categoria, msg in mensagens %}
      <div class="flash {{ categoria }}">{{ msg }}</div>
    {% endfor %}
  {% endwith %}
  {% block conteudo %}{% endblock %}
</div>
</body>
</html>
'''

arquivos["templates/index.html"] = r'''{% extends "base.html" %}
{% block titulo %}Registrar Movimentacao{% endblock %}
{% block conteudo %}

<h1>Movimentacao de Bens</h1>
<p class="subtitulo">Registre a movimentacao de itens entre setores</p>

<form class="card grid" action="/registrar" method="POST">
  <div class="campo">
    <label>Funcionario responsavel</label>
    <select name="funcionario" required>
      <option value="">-- Selecione --</option>
      {% for f in funcionarios %}
        <option value="{{ f }}">{{ f }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="campo">
    <label>Bem / Item</label>
    <select name="bem" required>
      <option value="">-- Selecione --</option>
      {% for b in bens %}
        <option value="{{ b }}">{{ b }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="campo">
    <label>Local de origem</label>
    <select name="origem" required>
      <option value="">-- Selecione --</option>
      {% for l in locais %}
        <option value="{{ l }}">{{ l }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="campo">
    <label>Destino</label>
    <select name="destino" required>
      <option value="">-- Selecione --</option>
      {% for l in locais %}
        <option value="{{ l }}">{{ l }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="campo full">
    <label>Observacao (opcional)</label>
    <textarea name="observacao" rows="3"></textarea>
  </div>
  <div class="campo full">
    <button type="submit">Registrar Movimentacao</button>
  </div>
</form>

<div class="card">
  <h2 style="color:#1a3d6d;font-size:18px;margin-top:0;">Ultimas 10 movimentacoes</h2>
  {% if historico %}
    <table>
      <tr>
        <th>Data/Hora</th><th>Funcionario</th><th>Bem</th>
        <th>Origem</th><th>Destino</th><th>Obs.</th>
      </tr>
      {% for m in historico %}
        <tr>
          <td>{{ m.data_hora }}</td>
          <td>{{ m.funcionario }}</td>
          <td>{{ m.bem }}</td>
          <td>{{ m.origem }}</td>
          <td>{{ m.destino }}</td>
          <td>{{ m.observacao }}</td>
        </tr>
      {% endfor %}
    </table>
    <p style="margin-top:14px;">
      <a href="/historico" class="botao secundario">Ver historico completo</a>
    </p>
  {% else %}
    <p>Nenhuma movimentacao registrada ainda.</p>
  {% endif %}
</div>

{% endblock %}
'''

arquivos["templates/historico.html"] = r'''{% extends "base.html" %}
{% block titulo %}Historico de Movimentacoes{% endblock %}
{% block conteudo %}

<h1>Historico de Movimentacoes</h1>
<p class="subtitulo">Filtre, edite ou exclua movimentacoes registradas</p>

<form class="card filtros" method="GET" action="/historico">
  <div class="campo">
    <label>Data inicial</label>
    <input type="date" name="data_ini" value="{{ filtros.data_ini }}">
  </div>
  <div class="campo">
    <label>Data final</label>
    <input type="date" name="data_fim" value="{{ filtros.data_fim }}">
  </div>
  <div class="campo">
    <label>Funcionario</label>
    <select name="funcionario">
      <option value="">-- Todos --</option>
      {% for f in funcionarios %}
        <option value="{{ f }}" {% if filtros.funcionario == f %}selected{% endif %}>{{ f }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="campo">
    <label>Bem</label>
    <select name="bem">
      <option value="">-- Todos --</option>
      {% for b in bens %}
        <option value="{{ b }}" {% if filtros.bem == b %}selected{% endif %}>{{ b }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="campo">
    <label>Origem</label>
    <select name="origem">
      <option value="">-- Todas --</option>
      {% for l in locais %}
        <option value="{{ l }}" {% if filtros.origem == l %}selected{% endif %}>{{ l }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="campo">
    <label>Destino</label>
    <select name="destino">
      <option value="">-- Todos --</option>
      {% for l in locais %}
        <option value="{{ l }}" {% if filtros.destino == l %}selected{% endif %}>{{ l }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="botoes">
    <button type="submit">Filtrar</button>
    <a href="/historico" class="botao secundario">Limpar</a>
    <a href="/exportar?data_ini={{ filtros.data_ini }}&data_fim={{ filtros.data_fim }}&funcionario={{ filtros.funcionario }}&bem={{ filtros.bem }}&origem={{ filtros.origem }}&destino={{ filtros.destino }}" class="botao secundario">Baixar CSV</a>
  </div>
</form>

<div class="card">
  <p class="contador">Mostrando {{ total }} movimentacao(oes)</p>
  {% if movimentacoes %}
    <table>
      <tr>
        <th>Data/Hora</th><th>Funcionario</th><th>Bem</th>
        <th>Origem</th><th>Destino</th><th>Obs.</th><th>Acoes</th>
      </tr>
      {% for m in movimentacoes %}
        <tr>
          <td>{{ m.data_hora }}</td>
          <td>{{ m.funcionario }}</td>
          <td>{{ m.bem }}</td>
          <td>{{ m.origem }}</td>
          <td>{{ m.destino }}</td>
          <td>{{ m.observacao }}</td>
          <td>
            <div class="acoes">
              <a href="/editar/{{ m.id }}">Editar</a>
              <form method="POST" action="/excluir/{{ m.id }}"
                    onsubmit="return confirm('Tem certeza que deseja excluir esta movimentacao?');"
                    style="display:inline;">
                <button type="submit" class="perigo">Excluir</button>
              </form>
            </div>
          </td>
        </tr>
      {% endfor %}
    </table>
  {% else %}
    <p>Nenhuma movimentacao encontrada com esses filtros.</p>
  {% endif %}
</div>

{% endblock %}
'''

arquivos["templates/editar.html"] = r'''{% extends "base.html" %}
{% block titulo %}Editar Movimentacao{% endblock %}
{% block conteudo %}

<h1>Editar Movimentacao</h1>
<p class="subtitulo">ID #{{ mov.id }} — registrada em {{ mov.data_hora }}</p>

<form class="card grid" action="/editar/{{ mov.id }}" method="POST">
  <div class="campo">
    <label>Funcionario responsavel</label>
    <select name="funcionario" required>
      {% for f in funcionarios %}
        <option value="{{ f }}" {% if mov.funcionario == f %}selected{% endif %}>{{ f }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="campo">
    <label>Bem / Item</label>
    <select name="bem" required>
      {% for b in bens %}
        <option value="{{ b }}" {% if mov.bem == b %}selected{% endif %}>{{ b }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="campo">
    <label>Local de origem</label>
    <select name="origem" required>
      {% for l in locais %}
        <option value="{{ l }}" {% if mov.origem == l %}selected{% endif %}>{{ l }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="campo">
    <label>Destino</label>
    <select name="destino" required>
      {% for l in locais %}
        <option value="{{ l }}" {% if mov.destino == l %}selected{% endif %}>{{ l }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="campo full">
    <label>Observacao</label>
    <textarea name="observacao" rows="3">{{ mov.observacao }}</textarea>
  </div>
  <div class="campo full" style="display:flex;gap:10px;">
    <button type="submit">Salvar alteracoes</button>
    <a href="/historico" class="botao secundario">Cancelar</a>
  </div>
</form>

{% endblock %}
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
    <label>Senha de app (do Gmail/Outlook)</label>
    <input type="password" name="senha_app"
           placeholder="{% if cfg.senha_app %}(deixe vazio para manter){% else %}cole aqui{% endif %}">
  </div>

  <div class="campo full">
    <button type="submit">Salvar configuracoes</button>
  </div>
</form>

<div class="card">
  <h2 style="color:#1a3d6d;font-size:18px;margin-top:0;">Como funciona</h2>
  <ul style="line-height:1.7;color:#444;">
    <li><b>Frequencia</b>: de quanto em quanto tempo o resumo vai por e-mail.</li>
    <li><b>Dia</b>: para mensal/trimestral, o dia do mes em que o envio acontece (ex: 1 = primeiro dia).</li>
    <li><b>Destinatarios</b>: quem recebe o resumo. Separe varios por virgula.</li>
    <li><b>E-mail remetente</b>: uma conta criada para o sistema (recomendado Gmail com senha de app).</li>
    <li><b>Assunto</b>: use <code>{periodo}</code> para inserir automaticamente o periodo.</li>
  </ul>
  <p style="color:#a11a1a;font-size:13px;background:#fbe0e0;padding:10px;border-radius:6px;">
    <b>Importante:</b> esta tela salva as configuracoes, mas o envio de e-mail sera ativado na proxima etapa.
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