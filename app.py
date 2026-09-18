from flask import Flask, render_template, request, redirect, url_for, flash, Response
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
