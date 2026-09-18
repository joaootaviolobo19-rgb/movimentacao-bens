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
MESES = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']

PADRAO = {
    'funcionarios.json': [
        {"nome": "João Silva", "cargo": "Analista de TI", "setor": "TI", "matricula": "001", "email": "joao@empresa.com"},
        {"nome": "Maria Souza", "cargo": "Assistente Administrativo", "setor": "Administrativo", "matricula": "002", "email": "maria@empresa.com"},
        {"nome": "Carlos Andrade", "cargo": "Gerente", "setor": "Financeiro", "matricula": "003", "email": "carlos@empresa.com"},
        {"nome": "Ana Paula", "cargo": "Recepcionista", "setor": "Recepção", "matricula": "004", "email": "ana@empresa.com"}
    ],
    'bens.json': [
        {"patrimonio": "PAT0001", "nome": "Notebook Dell Latitude 3420", "categoria": "Informática", "estado": "Bom", "configuracao": "i5 11ª geração, 8GB RAM, SSD 256GB", "valor": "3500.00"},
        {"patrimonio": "PAT0002", "nome": "Monitor LG 24\"", "categoria": "Informática", "estado": "Bom", "configuracao": "Full HD, IPS, HDMI", "valor": "800.00"},
        {"patrimonio": "PAT0003", "nome": "Impressora HP LaserJet", "categoria": "Informática", "estado": "Regular", "configuracao": "Laser mono, rede", "valor": "1500.00"},
        {"patrimonio": "PAT0004", "nome": "Cadeira Gamer", "categoria": "Mobiliário", "estado": "Novo", "configuracao": "Reclinável, apoio de braço", "valor": "1200.00"},
        {"patrimonio": "PAT0005", "nome": "Celular Samsung A54", "categoria": "Telefonia", "estado": "Bom", "configuracao": "128GB, 5G, Android", "valor": "2000.00"}
    ],
    'locais.json': [
        {"nome": "Almoxarifado Central", "bloco": "A", "andar": "Térreo", "responsavel": ""},
        {"nome": "TI - 2º andar", "bloco": "A", "andar": "2", "responsavel": ""},
        {"nome": "Financeiro", "bloco": "B", "andar": "1", "responsavel": ""},
        {"nome": "RH", "bloco": "B", "andar": "1", "responsavel": ""},
        {"nome": "Recepção", "bloco": "A", "andar": "Térreo", "responsavel": ""},
        {"nome": "Sala de Reuniões", "bloco": "A", "andar": "2", "responsavel": ""}
    ]
}

CONFIG_PADRAO = {
    "email_ativo": False,
    "frequencia": "mensal",
    "dia_do_mes": 1,
    "horario": "08:00",
    "destinatarios": [],
    "assunto": "Relatório de Movimentações - {periodo}",
    "email_remetente": "",
    "senha_app": "",
    "ultimo_envio": ""
}

CAMPOS_CADASTRO = {
    'funcionarios': ['nome', 'cargo', 'setor', 'matricula', 'email'],
    'bens': ['patrimonio', 'nome', 'categoria', 'estado', 'configuracao', 'valor'],
    'locais': ['nome', 'bloco', 'andar', 'responsavel']
}

ROTULOS = {
    'funcionarios': {'nome': 'Nome', 'cargo': 'Cargo', 'setor': 'Setor', 'matricula': 'Matrícula', 'email': 'E-mail'},
    'bens': {'patrimonio': 'Patrimônio', 'nome': 'Nome do bem', 'categoria': 'Categoria', 'estado': 'Estado', 'configuracao': 'Configuração', 'valor': 'Valor (R$)'},
    'locais': {'nome': 'Nome do local', 'bloco': 'Bloco', 'andar': 'Andar', 'responsavel': 'Responsável'}
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


def salvar_json(nome, dados):
    caminho = os.path.join(DADOS, nome)
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


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


def migrar_jsons():
    """Converte formato antigo (lista de strings) para objetos."""
    # Funcionarios
    try:
        funcs = carregar('funcionarios.json')
        if funcs and isinstance(funcs[0], str):
            novos = [{"nome": n, "cargo": "", "setor": "", "matricula": "", "email": ""} for n in funcs]
            salvar_json('funcionarios.json', novos)
            print("[migracao] funcionarios.json convertido.")
    except Exception as e:
        print("[migracao] funcionarios:", e)

    # Bens
    try:
        bens = carregar('bens.json')
        if bens and isinstance(bens[0], str):
            novos = []
            for i, s in enumerate(bens, start=1):
                if ' - PAT' in s:
                    nome, pat = s.rsplit(' - ', 1)
                elif ' - ' in s:
                    nome, pat = s.rsplit(' - ', 1)
                else:
                    nome, pat = s, f"PAT{i:04d}"
                novos.append({
                    "patrimonio": pat.strip(),
                    "nome": nome.strip(),
                    "categoria": "",
                    "estado": "Bom",
                    "configuracao": "",
                    "valor": ""
                })
            salvar_json('bens.json', novos)
            print("[migracao] bens.json convertido.")
    except Exception as e:
        print("[migracao] bens:", e)

    # Locais
    try:
        locais = carregar('locais.json')
        if locais and isinstance(locais[0], str):
            novos = [{"nome": n, "bloco": "", "andar": "", "responsavel": ""} for n in locais]
            salvar_json('locais.json', novos)
            print("[migracao] locais.json convertido.")
    except Exception as e:
        print("[migracao] locais:", e)


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


def enriquecer(linhas):
    """Adiciona campo bem_display e bem_estado às linhas."""
    bens = carregar('bens.json')
    por_pat = {b.get('patrimonio', ''): b for b in bens}
    for l in linhas:
        b = por_pat.get(l.get('bem', ''))
        if b:
            l['bem_display'] = f"{b.get('patrimonio','')} — {b.get('nome','')}"
            l['bem_estado'] = b.get('estado', '')
            l['bem_categoria'] = b.get('categoria', '')
        else:
            l['bem_display'] = l.get('bem', '')
            l['bem_estado'] = ''
            l['bem_categoria'] = ''
    return linhas


def dados_grafico():
    linhas = ler_movimentacoes()
    contagem = {}
    for l in linhas:
        d = _data(l.get('data_hora', ''))
        if d:
            key = f"{d.year}-{d.month:02d}"
            contagem[key] = contagem.get(key, 0) + 1
    hoje = datetime.now()
    labels, valores = [], []
    for i in range(11, -1, -1):
        m = hoje.month - i
        y = hoje.year
        while m <= 0:
            m += 12
            y -= 1
        key = f"{y}-{m:02d}"
        labels.append(f"{MESES[m-1]}/{str(y)[2:]}")
        valores.append(contagem.get(key, 0))
    return labels, valores


# ==================== E-MAIL ====================

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
  <div style="background:#0B1220;color:#fff;padding:22px 28px;">
    <h1 style="margin:0;font-size:20px;">Relatório de Movimentações</h1>
    <p style="margin:6px 0 0;color:#94A3B8;font-size:14px;">Período: {ini_str} a {fim_str}</p>
  </div>
  <div style="padding:24px 28px;">
    <p style="font-size:32px;font-weight:700;color:#2563EB;margin:0 0 4px;">{total}</p>
    <p style="margin:0;color:#666;font-size:14px;">movimentação(ões) no período</p>
    {bloco('Por funcionário', por_func)}
    {bloco('Bens mais movimentados', por_bem)}
    {bloco('Setores que mais receberam', por_dest)}
    <hr style="border:none;border-top:1px solid #eee;margin:26px 0;">
    <p style="color:#888;font-size:12px;margin:0;">Enviado automaticamente pelo Sistema de Patrimônio.</p>
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


# ==================== ROTAS ====================

@app.route('/')
def index():
    linhas = ler_movimentacoes()
    ultimas = enriquecer(list(reversed(linhas[-10:])))
    labels, valores = dados_grafico()
    return render_template(
        'registrar.html',
        funcionarios=carregar('funcionarios.json'),
        bens=carregar('bens.json'),
        locais=carregar('locais.json'),
        historico=ultimas,
        total_geral=len(linhas),
        chart_labels=json.dumps(labels),
        chart_valores=json.dumps(valores),
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
        flash('Origem e destino são iguais. Escolha lugares diferentes.', 'erro')
        return redirect(url_for('index'))
    salvar_movimentacao(registro)
    flash('Movimentação registrada com sucesso!', 'ok')
    return redirect(url_for('index'))


@app.route('/planilha')
def planilha():
    linhas = enriquecer(ler_movimentacoes())
    return render_template(
        'planilha.html',
        movimentacoes=linhas,
        total=len(linhas),
        caminho_csv=HISTORICO,
        ativo='planilha'
    )


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
    filtradas = enriquecer(filtrar(linhas, **filtros))
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
        flash('Movimentação não encontrada.', 'erro')
        return redirect(url_for('historico'))
    if request.method == 'POST':
        alvo['funcionario'] = request.form['funcionario']
        alvo['bem'] = request.form['bem']
        alvo['origem'] = request.form['origem']
        alvo['destino'] = request.form['destino']
        alvo['observacao'] = request.form.get('observacao', '').strip()
        if alvo['origem'] == alvo['destino']:
            flash('Origem e destino são iguais.', 'erro')
            return redirect(url_for('editar', id=id))
        escrever_movimentacoes(linhas)
        flash('Movimentação atualizada!', 'ok')
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
        flash('Movimentação não encontrada.', 'erro')
    else:
        escrever_movimentacoes(novas)
        flash('Movimentação excluída.', 'ok')
    return redirect(url_for('historico'))


# ==================== CADASTROS ====================

@app.route('/cadastros')
def cadastros():
    return redirect(url_for('cadastro', tipo='funcionarios'))


@app.route('/cadastros/<tipo>')
def cadastro(tipo):
    if tipo not in CAMPOS_CADASTRO:
        flash('Tipo de cadastro inválido.', 'erro')
        return redirect(url_for('cadastros'))
    itens = carregar(f'{tipo}.json')
    editar_idx = request.args.get('editar')
    em_edicao = None
    if editar_idx is not None:
        try:
            em_edicao = int(editar_idx)
            if not (0 <= em_edicao < len(itens)):
                em_edicao = None
        except ValueError:
            em_edicao = None
    return render_template(
        'cadastros.html',
        tipo=tipo,
        itens=itens,
        campos=CAMPOS_CADASTRO[tipo],
        rotulos=ROTULOS[tipo],
        em_edicao=em_edicao,
        ativo='cadastros'
    )


@app.route('/cadastros/<tipo>/salvar', methods=['POST'])
def cadastro_salvar(tipo):
    if tipo not in CAMPOS_CADASTRO:
        return redirect(url_for('cadastros'))
    itens = carregar(f'{tipo}.json')
    novo = {}
    for c in CAMPOS_CADASTRO[tipo]:
        novo[c] = request.form.get(c, '').strip()
    idx = request.form.get('editar_idx', '').strip()
    if idx.isdigit() and 0 <= int(idx) < len(itens):
        itens[int(idx)] = novo
        flash(f'Registro atualizado!', 'ok')
    else:
        itens.append(novo)
        flash(f'Registro adicionado!', 'ok')
    salvar_json(f'{tipo}.json', itens)
    return redirect(url_for('cadastro', tipo=tipo))


@app.route('/cadastros/<tipo>/excluir/<int:idx>', methods=['POST'])
def cadastro_excluir(tipo, idx):
    if tipo not in CAMPOS_CADASTRO:
        return redirect(url_for('cadastros'))
    itens = carregar(f'{tipo}.json')
    if 0 <= idx < len(itens):
        itens.pop(idx)
        salvar_json(f'{tipo}.json', itens)
        flash('Registro excluído.', 'ok')
    return redirect(url_for('cadastro', tipo=tipo))


# ==================== CONFIG ====================

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
        cfg['assunto'] = request.form.get('assunto', 'Relatório de Movimentações - {periodo}')
        cfg['email_remetente'] = request.form.get('email_remetente', '').strip()
        senha = request.form.get('senha_app', '').strip()
        if senha:
            cfg['senha_app'] = senha
        salvar_config(cfg)
        flash('Configurações salvas!', 'ok')
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
    migrar_jsons()
    migrar_csv()
    t = threading.Thread(target=loop_agendador, daemon=True)
    t.start()
    app.run(debug=True, host='0.0.0.0', port=5000)
'''

arquivos["templates/base.html"] = r'''<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{% block titulo %}Sistema de Patrimônio{% endblock %}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #F1F5F9;
    --card: #FFFFFF;
    --border: #E2E8F0;
    --border-strong: #CBD5E1;
    --text: #0F172A;
    --text-muted: #64748B;
    --primary: #2563EB;
    --primary-hover: #1D4ED8;
    --success: #059669;
    --danger: #DC2626;
    --warning: #D97706;
    --sidebar: #0B1220;
    --sidebar-hover: #1E293B;
    --sidebar-active: #1E293B;
    --sidebar-text: #94A3B8;
    --sidebar-text-active: #FFFFFF;
  }
  html, body { height: 100%; }
  body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg);
    color: var(--text);
    font-size: 14px;
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
  }
  .layout { display: flex; min-height: 100vh; }

  /* ============ SIDEBAR ============ */
  .sidebar {
    width: 240px; flex-shrink: 0;
    background: var(--sidebar); color: var(--sidebar-text);
    display: flex; flex-direction: column;
    position: sticky; top: 0; height: 100vh; overflow-y: auto;
  }
  .brand {
    display: flex; align-items: center; gap: 12px;
    padding: 20px; border-bottom: 1px solid rgba(255,255,255,0.06);
  }
  .brand-icon {
    width: 36px; height: 36px; border-radius: 9px;
    background: linear-gradient(135deg, #3B82F6, #2563EB);
    display: flex; align-items: center; justify-content: center;
    color: #fff; font-weight: 800; font-size: 14px;
    box-shadow: 0 4px 12px rgba(59,130,246,.35);
  }
  .brand-text { display: flex; flex-direction: column; }
  .brand-name { color: #fff; font-weight: 700; font-size: 14px; }
  .brand-sub { color: var(--sidebar-text); font-size: 11px; }
  .nav { padding: 16px 12px; flex: 1; }
  .nav-label {
    display: block; color: #475569; font-size: 11px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.05em;
    padding: 12px 12px 6px;
  }
  .nav-item {
    display: flex; align-items: center; gap: 10px;
    padding: 10px 12px; border-radius: 8px;
    color: var(--sidebar-text); text-decoration: none;
    font-weight: 500; font-size: 13px;
    transition: background .15s, color .15s;
    margin-bottom: 2px;
  }
  .nav-item:hover { background: var(--sidebar-hover); color: #fff; }
  .nav-item.active { background: var(--sidebar-active); color: #fff; }
  .nav-item.active::before {
    content: ''; position: absolute;
  }
  .nav-item svg { width: 16px; height: 16px; opacity: .8; flex-shrink: 0; }
  .nav-item.active svg { opacity: 1; }

  /* ============ MAIN ============ */
  .main { flex: 1; min-width: 0; padding: 28px 32px; }
  .page-header { display: flex; justify-content: space-between; align-items: flex-start;
                 margin-bottom: 24px; flex-wrap: wrap; gap: 14px; }
  .page-title { font-size: 22px; font-weight: 700; color: var(--text); }
  .page-sub { color: var(--text-muted); font-size: 13px; margin-top: 3px; }

  .flash {
    padding: 12px 16px; border-radius: 9px; margin-bottom: 18px;
    font-weight: 500; font-size: 13px; display: flex; align-items: center; gap: 8px;
  }
  .flash.ok   { background: #ECFDF5; color: #065F46; border: 1px solid #A7F3D0; }
  .flash.erro { background: #FEF2F2; color: #991B1B; border: 1px solid #FECACA; }

  .card {
    background: var(--card); border-radius: 12px;
    border: 1px solid var(--border);
    padding: 24px; margin-bottom: 20px;
    box-shadow: 0 1px 2px rgba(15,23,42,.04);
  }
  .card-title {
    font-size: 15px; font-weight: 700; color: var(--text);
    margin-bottom: 18px; display: flex; align-items: center; gap: 8px;
  }

  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .campo { display: flex; flex-direction: column; }
  .campo.full { grid-column: 1 / -1; }
  label { font-weight: 600; color: var(--text); margin-bottom: 6px; font-size: 13px; }
  select, input, textarea {
    padding: 10px 12px; border: 1px solid var(--border-strong);
    border-radius: 8px; font-size: 14px; background: #fff;
    font-family: inherit; color: var(--text);
    transition: border-color .15s, box-shadow .15s; outline: none;
  }
  select:focus, input:focus, textarea:focus {
    border-color: var(--primary);
    box-shadow: 0 0 0 3px rgba(37,99,235,.12);
  }
  textarea { resize: vertical; font-family: inherit; }

  button, .botao {
    padding: 10px 16px; background: var(--primary); color: #fff;
    border: none; border-radius: 8px; font-size: 13px; font-weight: 600;
    cursor: pointer; text-decoration: none; display: inline-flex;
    align-items: center; gap: 6px; font-family: inherit;
    transition: background .15s;
  }
  button:hover, .botao:hover { background: var(--primary-hover); }
  .botao.secundario {
    background: #fff; color: var(--text); border: 1px solid var(--border-strong);
  }
  .botao.secundario:hover { background: #F8FAFC; }
  .botao.sucesso { background: var(--success); }
  .botao.sucesso:hover { background: #047857; }
  .botao.perigo { background: var(--danger); }
  .botao.perigo:hover { background: #B91C1C; }
  .botao.pequeno { padding: 6px 10px; font-size: 12px; }

  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  thead th {
    background: #F8FAFC; color: var(--text-muted);
    font-weight: 600; font-size: 11px; text-transform: uppercase;
    letter-spacing: 0.03em; padding: 12px;
    border-bottom: 1px solid var(--border); text-align: left;
  }
  tbody td {
    padding: 12px; border-bottom: 1px solid var(--border);
    color: var(--text); vertical-align: middle;
  }
  tbody tr:last-child td { border-bottom: none; }
  tbody tr:hover td { background: #F8FAFC; }

  .badge {
    display: inline-block; padding: 3px 9px; border-radius: 999px;
    font-size: 11px; font-weight: 600;
  }
  .badge.novo    { background: #DBEAFE; color: #1E40AF; }
  .badge.bom     { background: #D1FAE5; color: #065F46; }
  .badge.regular { background: #FEF3C7; color: #92400E; }
  .badge.ruim    { background: #FEE2E2; color: #991B1B; }
  .badge.cat     { background: #E0E7FF; color: #3730A3; }

  .stat-card {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 12px; padding: 20px;
    box-shadow: 0 1px 2px rgba(15,23,42,.04);
  }
  .stat-label { color: var(--text-muted); font-size: 12px; font-weight: 500;
                text-transform: uppercase; letter-spacing: 0.03em; }
  .stat-value { color: var(--text); font-size: 28px; font-weight: 700; margin-top: 6px; }

  .acoes-cell { display: flex; gap: 6px; justify-content: flex-end; }
  .acoes-cell button, .acoes-cell a {
    padding: 6px 10px; font-size: 12px; border-radius: 6px;
    background: #fff; color: var(--text); border: 1px solid var(--border-strong);
    text-decoration: none; cursor: pointer; font-weight: 600;
  }
  .acoes-cell button.perigo { color: var(--danger); border-color: #FECACA; }
  .acoes-cell button.perigo:hover { background: #FEF2F2; }

  .tabs {
    display: flex; gap: 4px; margin-bottom: 20px;
    background: #F1F5F9; padding: 4px; border-radius: 10px;
    border: 1px solid var(--border); width: fit-content;
  }
  .tabs a {
    padding: 8px 18px; border-radius: 7px; color: var(--text-muted);
    text-decoration: none; font-weight: 600; font-size: 13px;
    transition: background .15s, color .15s;
  }
  .tabs a:hover { color: var(--text); }
  .tabs a.ativo { background: #fff; color: var(--primary); box-shadow: 0 1px 3px rgba(0,0,0,.06); }

  @media (max-width: 768px) {
    .layout { flex-direction: column; }
    .sidebar { width: 100%; height: auto; position: static; }
    .brand { padding: 16px; }
    .nav { display: flex; overflow-x: auto; padding: 8px; gap: 4px; }
    .nav-label { display: none; }
    .nav-item { white-space: nowrap; margin: 0; }
    .main { padding: 20px 16px; }
    .grid { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>
<div class="layout">
  <aside class="sidebar">
    <div class="brand">
      <div class="brand-icon">SP</div>
      <div class="brand-text">
        <span class="brand-name">Patrimônio</span>
        <span class="brand-sub">Gestão de Bens</span>
      </div>
    </div>
    <nav class="nav">
      <span class="nav-label">Operação</span>
      <a href="/" class="nav-item {% if ativo=='registrar' %}active{% endif %}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
        Registrar
      </a>
      <a href="/planilha" class="nav-item {% if ativo=='planilha' %}active{% endif %}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg>
        Planilha
      </a>
      <a href="/historico" class="nav-item {% if ativo=='historico' %}active{% endif %}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 8v4l3 3"/><circle cx="12" cy="12" r="9"/></svg>
        Histórico
      </a>
      <span class="nav-label">Gerenciar</span>
      <a href="/cadastros" class="nav-item {% if ativo=='cadastros' %}active{% endif %}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg>
        Cadastros
      </a>
      <span class="nav-label">Sistema</span>
      <a href="/configuracoes" class="nav-item {% if ativo=='config' %}active{% endif %}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
        Configurações
      </a>
    </nav>
  </aside>
  <main class="main">
    {% with mensagens = get_flashed_messages(with_categories=true) %}
      {% for categoria, msg in mensagens %}
        <div class="flash {{ categoria }}">{{ msg }}</div>
      {% endfor %}
    {% endwith %}
    {% block conteudo %}{% endblock %}
  </main>
</div>
</body>
</html>
'''

arquivos["templates/registrar.html"] = r'''{% extends "base.html" %}
{% block titulo %}Registrar Movimentação{% endblock %}
{% block conteudo %}

<div class="page-header">
  <div>
    <h1 class="page-title">Registrar Movimentação</h1>
    <p class="page-sub">Cadastre a movimentação de um bem entre setores</p>
  </div>
</div>

<form class="card grid" action="/registrar" method="POST">
  <div class="campo">
    <label>Funcionário responsável</label>
    <select name="funcionario" required>
      <option value="">Selecione um funcionário</option>
      {% for f in funcionarios %}
        <option value="{{ f.nome }}">{{ f.nome }}{% if f.cargo %} — {{ f.cargo }}{% endif %}</option>
      {% endfor %}
    </select>
  </div>
  <div class="campo">
    <label>Bem / Item</label>
    <select name="bem" required>
      <option value="">Selecione um bem</option>
      {% for b in bens %}
        <option value="{{ b.patrimonio }}">{{ b.patrimonio }} — {{ b.nome }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="campo">
    <label>Local de origem</label>
    <select name="origem" required>
      <option value="">Selecione o local de origem</option>
      {% for l in locais %}
        <option value="{{ l.nome }}">{{ l.nome }}{% if l.andar %} — {{ l.andar }}{% endif %}</option>
      {% endfor %}
    </select>
  </div>
  <div class="campo">
    <label>Destino</label>
    <select name="destino" required>
      <option value="">Selecione o destino</option>
      {% for l in locais %}
        <option value="{{ l.nome }}">{{ l.nome }}{% if l.andar %} — {{ l.andar }}{% endif %}</option>
      {% endfor %}
    </select>
  </div>
  <div class="campo full">
    <label>Observação (opcional)</label>
    <textarea name="observacao" rows="2" placeholder="Ex: item com avaria, troca de setor, etc."></textarea>
  </div>
  <div class="campo full">
    <button type="submit">Registrar movimentação</button>
  </div>
</form>

<div class="card">
  <div class="card-title">Movimentações por mês</div>
  <canvas id="graficoMes" height="70"></canvas>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px;">
  <div class="stat-card">
    <div class="stat-label">Total registrado</div>
    <div class="stat-value">{{ total_geral }}</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Acesso rápido</div>
    <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap;">
      <a href="/planilha" class="botao secundario pequeno">Ver planilha</a>
      <a href="/historico" class="botao secundario pequeno">Histórico</a>
      <a href="/cadastros" class="botao secundario pequeno">Cadastros</a>
    </div>
  </div>
</div>

<div class="card">
  <div class="card-title">Últimas 10 movimentações</div>
  {% if historico %}
    <table>
      <thead>
        <tr>
          <th>Data/Hora</th><th>Funcionário</th><th>Bem</th>
          <th>Origem</th><th>Destino</th><th>Obs.</th>
        </tr>
      </thead>
      <tbody>
        {% for m in historico %}
          <tr>
            <td>{{ m.data_hora }}</td>
            <td>{{ m.funcionario }}</td>
            <td>{{ m.bem_display }}</td>
            <td>{{ m.origem }}</td>
            <td>{{ m.destino }}</td>
            <td>{{ m.observacao }}</td>
          </tr>
        {% endfor %}
      </tbody>
    </table>
  {% else %}
    <p style="color:#64748B;">Nenhuma movimentação registrada ainda.</p>
  {% endif %}
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>
  const labels = {{ chart_labels|safe }};
  const valores = {{ chart_valores|safe }};
  const ctx = document.getElementById('graficoMes').getContext('2d');
  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Movimentações',
        data: valores,
        backgroundColor: '#2563EB',
        hoverBackgroundColor: '#1D4ED8',
        borderRadius: 6,
        maxBarThickness: 44
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#0F172A',
          padding: 10,
          cornerRadius: 8,
          displayColors: false,
          callbacks: {
            label: (ctx) => ctx.parsed.y + ' movimentação(ões)'
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: '#64748B', font: { family: 'Inter', size: 12 } }
        },
        y: {
          beginAtZero: true,
          grid: { color: '#E2E8F0', drawBorder: false },
          ticks: { color: '#64748B', stepSize: 1, font: { family: 'Inter', size: 12 } }
        }
      }
    }
  });
</script>

{% endblock %}
'''

arquivos["templates/planilha.html"] = r'''{% extends "base.html" %}
{% block titulo %}Planilha{% endblock %}
{% block conteudo %}

<div class="page-header">
  <div>
    <h1 class="page-title">Planilha de Movimentações</h1>
    <p class="page-sub">Visualização completa do arquivo CSV</p>
  </div>
  <div style="display:flex;gap:8px;">
    <a href="/planilha" class="botao secundario">Atualizar</a>
    <a href="/exportar" class="botao">Baixar CSV</a>
  </div>
</div>

<div class="card" style="padding:0;overflow:hidden;">
  <div style="padding:16px 20px;background:#F8FAFC;border-bottom:1px solid var(--border);
              display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">
    <span style="font-weight:700;color:var(--text);">{{ total }} registro(s)</span>
    <span style="font-size:12px;color:var(--text-muted);font-family:monospace;">{{ caminho_csv }}</span>
  </div>
  {% if movimentacoes %}
    <div style="max-height:600px;overflow:auto;">
      <table style="font-family:'SF Mono',Consolas,monospace;font-size:12px;">
        <thead>
          <tr>
            <th style="position:sticky;top:0;background:#F8FAFC;text-align:right;width:50px;">#</th>
            <th style="position:sticky;top:0;background:#F8FAFC;">ID</th>
            <th style="position:sticky;top:0;background:#F8FAFC;">Data/Hora</th>
            <th style="position:sticky;top:0;background:#F8FAFC;">Funcionário</th>
            <th style="position:sticky;top:0;background:#F8FAFC;">Bem</th>
            <th style="position:sticky;top:0;background:#F8FAFC;">Origem</th>
            <th style="position:sticky;top:0;background:#F8FAFC;">Destino</th>
            <th style="position:sticky;top:0;background:#F8FAFC;">Observação</th>
          </tr>
        </thead>
        <tbody>
          {% for m in movimentacoes %}
            <tr>
              <td style="background:#F8FAFC;color:#64748B;text-align:right;font-weight:600;">{{ loop.index }}</td>
              <td>{{ m.id }}</td>
              <td>{{ m.data_hora }}</td>
              <td>{{ m.funcionario }}</td>
              <td>{{ m.bem_display }}</td>
              <td>{{ m.origem }}</td>
              <td>{{ m.destino }}</td>
              <td>{{ m.observacao }}</td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  {% else %}
    <div style="padding:60px;text-align:center;color:var(--text-muted);">
      Nenhuma movimentação registrada ainda.
    </div>
  {% endif %}
</div>

{% endblock %}
'''

arquivos["templates/historico.html"] = r'''{% extends "base.html" %}
{% block titulo %}Histórico{% endblock %}
{% block conteudo %}

<div class="page-header">
  <div>
    <h1 class="page-title">Histórico de Movimentações</h1>
    <p class="page-sub">Filtre, edite ou exclua registros</p>
  </div>
</div>

<form class="card" method="GET" action="/historico">
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:14px;">
    <div class="campo">
      <label>Data inicial</label>
      <input type="date" name="data_ini" value="{{ filtros.data_ini }}">
    </div>
    <div class="campo">
      <label>Data final</label>
      <input type="date" name="data_fim" value="{{ filtros.data_fim }}">
    </div>
    <div class="campo">
      <label>Funcionário</label>
      <select name="funcionario">
        <option value="">Todos</option>
        {% for f in funcionarios %}
          <option value="{{ f.nome }}" {% if filtros.funcionario == f.nome %}selected{% endif %}>{{ f.nome }}</option>
        {% endfor %}
      </select>
    </div>
    <div class="campo">
      <label>Bem</label>
      <select name="bem">
        <option value="">Todos</option>
        {% for b in bens %}
          <option value="{{ b.patrimonio }}" {% if filtros.bem == b.patrimonio %}selected{% endif %}>{{ b.patrimonio }} — {{ b.nome }}</option>
        {% endfor %}
      </select>
    </div>
    <div class="campo">
      <label>Origem</label>
      <select name="origem">
        <option value="">Todas</option>
        {% for l in locais %}
          <option value="{{ l.nome }}" {% if filtros.origem == l.nome %}selected{% endif %}>{{ l.nome }}</option>
        {% endfor %}
      </select>
    </div>
    <div class="campo">
      <label>Destino</label>
      <select name="destino">
        <option value="">Todos</option>
        {% for l in locais %}
          <option value="{{ l.nome }}" {% if filtros.destino == l.nome %}selected{% endif %}>{{ l.nome }}</option>
        {% endfor %}
      </select>
    </div>
    <div style="grid-column:1/-1;display:flex;gap:10px;flex-wrap:wrap;">
      <button type="submit">Filtrar</button>
      <a href="/historico" class="botao secundario">Limpar</a>
      <a href="/exportar?data_ini={{ filtros.data_ini }}&data_fim={{ filtros.data_fim }}&funcionario={{ filtros.funcionario }}&bem={{ filtros.bem }}&origem={{ filtros.origem }}&destino={{ filtros.destino }}" class="botao secundario">Baixar CSV</a>
    </div>
  </div>
</form>

<div class="card" style="padding:0;overflow:hidden;">
  <div style="padding:16px 20px;border-bottom:1px solid var(--border);">
    <span style="font-weight:700;color:var(--text);">{{ total }} movimentação(ões)</span>
  </div>
  {% if movimentacoes %}
    <table>
      <thead>
        <tr>
          <th>Data/Hora</th><th>Funcionário</th><th>Bem</th>
          <th>Origem</th><th>Destino</th><th>Obs.</th><th style="text-align:right;">Ações</th>
        </tr>
      </thead>
      <tbody>
        {% for m in movimentacoes %}
          <tr>
            <td>{{ m.data_hora }}</td>
            <td>{{ m.funcionario }}</td>
            <td>
              {{ m.bem_display }}
              {% if m.bem_estado %}
                <span class="badge {{ m.bem_estado|lower }}">{{ m.bem_estado }}</span>
              {% endif %}
            </td>
            <td>{{ m.origem }}</td>
            <td>{{ m.destino }}</td>
            <td>{{ m.observacao }}</td>
            <td>
              <div class="acoes-cell">
                <a href="/editar/{{ m.id }}" class="botao secundario pequeno">Editar</a>
                <form method="POST" action="/excluir/{{ m.id }}"
                      onsubmit="return confirm('Excluir esta movimentação?');"
                      style="display:inline;">
                  <button type="submit" class="perigo">Excluir</button>
                </form>
              </div>
            </td>
          </tr>
        {% endfor %}
      </tbody>
    </table>
  {% else %}
    <div style="padding:60px;text-align:center;color:var(--text-muted);">
      Nenhuma movimentação encontrada com esses filtros.
    </div>
  {% endif %}
</div>

{% endblock %}
'''

arquivos["templates/editar.html"] = r'''{% extends "base.html" %}
{% block titulo %}Editar Movimentação{% endblock %}
{% block conteudo %}

<div class="page-header">
  <div>
    <h1 class="page-title">Editar Movimentação</h1>
    <p class="page-sub">ID #{{ mov.id }} — registrada em {{ mov.data_hora }}</p>
  </div>
</div>

<form class="card grid" action="/editar/{{ mov.id }}" method="POST">
  <div class="campo">
    <label>Funcionário responsável</label>
    <select name="funcionario" required>
      {% for f in funcionarios %}
        <option value="{{ f.nome }}" {% if mov.funcionario == f.nome %}selected{% endif %}>{{ f.nome }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="campo">
    <label>Bem / Item</label>
    <select name="bem" required>
      {% for b in bens %}
        <option value="{{ b.patrimonio }}" {% if mov.bem == b.patrimonio %}selected{% endif %}>{{ b.patrimonio }} — {{ b.nome }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="campo">
    <label>Local de origem</label>
    <select name="origem" required>
      {% for l in locais %}
        <option value="{{ l.nome }}" {% if mov.origem == l.nome %}selected{% endif %}>{{ l.nome }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="campo">
    <label>Destino</label>
    <select name="destino" required>
      {% for l in locais %}
        <option value="{{ l.nome }}" {% if mov.destino == l.nome %}selected{% endif %}>{{ l.nome }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="campo full">
    <label>Observação</label>
    <textarea name="observacao" rows="3">{{ mov.observacao }}</textarea>
  </div>
  <div class="campo full" style="display:flex;gap:10px;">
    <button type="submit">Salvar alterações</button>
    <a href="/historico" class="botao secundario">Cancelar</a>
  </div>
</form>

{% endblock %}
'''

arquivos["templates/cadastros.html"] = r'''{% extends "base.html" %}
{% block titulo %}Cadastros{% endblock %}
{% block conteudo %}

<div class="page-header">
  <div>
    <h1 class="page-title">Cadastros</h1>
    <p class="page-sub">Gerencie funcionários, bens e locais do sistema</p>
  </div>
</div>

<div class="tabs">
  <a href="/cadastros/funcionarios" class="{% if tipo=='funcionarios' %}ativo{% endif %}">Funcionários</a>
  <a href="/cadastros/bens" class="{% if tipo=='bens' %}ativo{% endif %}">Bens</a>
  <a href="/cadastros/locais" class="{% if tipo=='locais' %}ativo{% endif %}">Locais</a>
</div>

<form class="card" method="POST" action="/cadastros/{{ tipo }}/salvar">
  {% if em_edicao is not none %}
    <input type="hidden" name="editar_idx" value="{{ em_edicao }}">
  {% endif %}

  <div class="card-title">
    {% if em_edicao is not none %}Editar registro{% else %}Adicionar novo registro{% endif %}
  </div>

  <div class="grid">
    {% for c in campos %}
      <div class="campo {% if c in ('configuracao','observacao') %}full{% endif %}">
        <label>{{ rotulos[c] }}</label>
        {% if c == 'configuracao' %}
          <textarea name="{{ c }}" rows="2">{% if em_edicao is not none %}{{ itens[em_edicao].get(c, '') }}{% endif %}</textarea>
        {% elif c == 'estado' %}
          <select name="{{ c }}">
            {% set val = itens[em_edicao].get(c, '') if em_edicao is not none else '' %}
            <option value="Novo" {% if val=='Novo' %}selected{% endif %}>Novo</option>
            <option value="Bom" {% if val=='Bom' %}selected{% endif %}>Bom</option>
            <option value="Regular" {% if val=='Regular' %}selected{% endif %}>Regular</option>
            <option value="Ruim" {% if val=='Ruim' %}selected{% endif %}>Ruim</option>
          </select>
        {% elif c == 'categoria' %}
          <select name="{{ c }}">
            {% set val = itens[em_edicao].get(c, '') if em_edicao is not none else '' %}
            <option value="">Selecione uma categoria</option>
            <option value="Informática" {% if val=='Informática' %}selected{% endif %}>Informática</option>
            <option value="Mobiliário" {% if val=='Mobiliário' %}selected{% endif %}>Mobiliário</option>
            <option value="Telefonia" {% if val=='Telefonia' %}selected{% endif %}>Telefonia</option>
            <option value="Eletrodoméstico" {% if val=='Eletrodoméstico' %}selected{% endif %}>Eletrodoméstico</option>
            <option value="Veículo" {% if val=='Veículo' %}selected{% endif %}>Veículo</option>
            <option value="Ferramenta" {% if val=='Ferramenta' %}selected{% endif %}>Ferramenta</option>
            <option value="Outros" {% if val=='Outros' %}selected{% endif %}>Outros</option>
          </select>
        {% else %}
          <input type="text" name="{{ c }}"
                 value="{% if em_edicao is not none %}{{ itens[em_edicao].get(c, '') }}{% endif %}"
                 {% if c in ('nome','patrimonio') %}required{% endif %}>
        {% endif %}
      </div>
    {% endfor %}
  </div>

  <div style="display:flex;gap:10px;margin-top:16px;">
    <button type="submit">{% if em_edicao is not none %}Salvar alterações{% else %}Adicionar{% endif %}</button>
    {% if em_edicao is not none %}
      <a href="/cadastros/{{ tipo }}" class="botao secundario">Cancelar</a>
    {% endif %}
  </div>
</form>

<div class="card" style="padding:0;overflow:hidden;">
  <div style="padding:16px 20px;border-bottom:1px solid var(--border);">
    <span style="font-weight:700;">{{ itens|length }} registro(s)</span>
  </div>
  {% if itens %}
    <table>
      <thead>
        <tr>
          {% for c in campos %}<th>{{ rotulos[c] }}</th>{% endfor %}
          <th style="text-align:right;">Ações</th>
        </tr>
      </thead>
      <tbody>
        {% for item in itens %}
          <tr>
            {% for c in campos %}
              <td>
                {% if c == 'estado' %}
                  <span class="badge {{ item.get(c,'')|lower }}">{{ item.get(c,'') }}</span>
                {% elif c == 'categoria' and item.get(c) %}
                  <span class="badge cat">{{ item.get(c,'') }}</span>
                {% else %}
                  {{ item.get(c, '') }}
                {% endif %}
              </td>
            {% endfor %}
            <td>
              <div class="acoes-cell">
                <a href="/cadastros/{{ tipo }}?editar={{ loop.index0 }}" class="botao secundario pequeno">Editar</a>
                <form method="POST" action="/cadastros/{{ tipo }}/excluir/{{ loop.index0 }}"
                      onsubmit="return confirm('Excluir este registro?');"
                      style="display:inline;">
                  <button type="submit" class="perigo">Excluir</button>
                </form>
              </div>
            </td>
          </tr>
        {% endfor %}
      </tbody>
    </table>
  {% else %}
    <div style="padding:60px;text-align:center;color:var(--text-muted);">
      Nenhum registro ainda. Use o formulário acima para adicionar.
    </div>
  {% endif %}
</div>

{% endblock %}
'''

arquivos["templates/configuracoes.html"] = r'''{% extends "base.html" %}
{% block titulo %}Configurações{% endblock %}
{% block conteudo %}

<div class="page-header">
  <div>
    <h1 class="page-title">Configurações de E-mail</h1>
    <p class="page-sub">Defina como e quando os relatórios serão enviados</p>
  </div>
</div>

<form class="card grid" action="/configuracoes" method="POST">

  <div class="campo full" style="flex-direction:row;align-items:center;gap:10px;">
    <input type="checkbox" name="email_ativo" id="email_ativo"
           {% if cfg.email_ativo %}checked{% endif %} style="width:auto;">
    <label for="email_ativo" style="margin:0;">Ativar envio automático de relatórios</label>
  </div>

  <div class="campo">
    <label>Frequência</label>
    <select name="frequencia">
      <option value="diario" {% if cfg.frequencia == 'diario' %}selected{% endif %}>Diário</option>
      <option value="semanal" {% if cfg.frequencia == 'semanal' %}selected{% endif %}>Semanal</option>
      <option value="mensal" {% if cfg.frequencia == 'mensal' %}selected{% endif %}>Mensal</option>
      <option value="trimestral" {% if cfg.frequencia == 'trimestral' %}selected{% endif %}>Trimestral</option>
    </select>
  </div>

  <div class="campo">
    <label>Dia do envio (mensal/trimestral)</label>
    <input type="number" name="dia_do_mes" min="1" max="28" value="{{ cfg.dia_do_mes }}">
  </div>

  <div class="campo">
    <label>Horário do envio</label>
    <input type="time" name="horario" value="{{ cfg.horario }}">
  </div>

  <div class="campo">
    <label>Assunto do e-mail</label>
    <input type="text" name="assunto" value="{{ cfg.assunto }}">
  </div>

  <div class="campo full">
    <label>Destinatários (separe por vírgula)</label>
    <input type="text" name="destinatarios"
           value="{{ cfg.destinatarios|join(', ') }}"
           placeholder="chefe@empresa.com, ti@empresa.com">
  </div>

  <div class="campo">
    <label>E-mail remetente</label>
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
    <button type="submit">Salvar configurações</button>
    <a href="/testar-email" class="botao secundario">Enviar e-mail de teste agora</a>
  </div>
</form>

<div class="card">
  <div class="card-title">Como funciona</div>
  <ul style="line-height:1.8;color:#334155;padding-left:20px;">
    <li><b>Frequência</b> — de quanto em quanto tempo o resumo vai por e-mail.</li>
    <li><b>Dia</b> — para mensal/trimestral, o dia do mês em que o envio acontece.</li>
    <li><b>Horário</b> — a hora exata do envio (o sistema verifica a cada minuto).</li>
    <li><b>Destinatários</b> — quem recebe. Separe vários por vírgula.</li>
    <li><b>E-mail remetente</b> — conta do Gmail criada para o sistema.</li>
    <li><b>Senha de app</b> — gerada em <code>myaccount.google.com/apppasswords</code>.</li>
    <li><b>Assunto</b> — use <code>{periodo}</code> para inserir o período automaticamente.</li>
  </ul>
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