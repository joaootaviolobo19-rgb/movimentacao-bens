# -*- coding: utf-8 -*-
import json
import os
import re
import tempfile
import unicodedata

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DADOS = os.path.join(BASE_DIR, "dados")
ARQ_PERFIS = os.path.join(DADOS, "perfis.json")

PERMISSOES = (
    ("dashboard", "Dashboard"),
    ("bens", "Bens"),
    ("planilha", "Planilha"),
    ("funcionarios", "Funcionários"),
    ("alertas", "Alertas de funcionários"),
    ("movimentacoes", "Movimentações"),
    ("ferias", "Férias"),
    ("ramais", "Ramais"),
    ("projetos", "Projetos"),
    ("organograma", "Organograma"),
    ("ponto", "Ponto"),
    ("configuracoes", "Configurações"),
    ("usuarios", "Usuários e perfis"),
    ("recepcao", "Central da Recepção"),
    ("reunioes", "Reuniões"),
)
ACOES_POR_RECURSO = {
    "dashboard": {"ver"},
    "bens": {"ver", "editar", "exportar"},
    "planilha": {"ver", "editar", "exportar"},
    "funcionarios": {"ver", "editar"},
    "alertas": {"ver", "editar"},
    "movimentacoes": {"ver", "exportar"},
    "ferias": {"ver", "editar"},
    "ramais": {"ver"},
    "projetos": {"ver", "editar"},
    "organograma": {"ver"},
    "ponto": {"ver"},
    "configuracoes": {"ver", "editar"},
    "usuarios": {"ver", "editar"},
    "recepcao": {"ver"},
    "reunioes": {"ver"},
}

PERFIS_PADRAO = [
    {"id": "admin", "nome": "TI", "permissoes": ["*"], "sistema": True},
    {
        "id": "recepcao",
        "nome": "Recepção",
        "permissoes": [
            "recepcao.ver",
            "ramais.ver",
            "reunioes.ver",
        ],
        "sistema": True,
    },
]


def _ler_perfis():
    if not os.path.exists(ARQ_PERFIS):
        return [dict(perfil) for perfil in PERFIS_PADRAO]
    with open(ARQ_PERFIS, "r", encoding="utf-8") as arquivo:
        perfis = json.load(arquivo)
    if not isinstance(perfis, list):
        raise ValueError("O arquivo de perfis precisa conter uma lista JSON.")
    por_id = {
        p.get("id"): p for p in perfis
        if isinstance(p, dict) and isinstance(p.get("id"), str)
    }
    for perfil in por_id.values():
        if (
            not isinstance(perfil.get("nome"), str)
            or not isinstance(perfil.get("permissoes"), list)
        ):
            raise ValueError("O arquivo de perfis contém dados inválidos.")
    for perfil_padrao in PERFIS_PADRAO:
        por_id.setdefault(perfil_padrao["id"], dict(perfil_padrao))
    return list(por_id.values())


def listar_perfis():
    return [dict(perfil) for perfil in _ler_perfis()]


def obter_perfil(perfil_id):
    return next(
        (perfil for perfil in _ler_perfis() if perfil["id"] == perfil_id),
        None,
    )


def tem_permissao(perfil_id, permissao):
    perfil = obter_perfil(perfil_id)
    if not perfil:
        return False
    permissoes_perfil = perfil.get("permissoes", [])
    if permissao == "recepcao.ver":
        return permissao in permissoes_perfil
    if "*" in permissoes_perfil:
        return True
    try:
        area, acao = permissao.rsplit(".", 1)
    except ValueError:
        return False
    return (
        acao in ACOES_POR_RECURSO.get(area, set())
        and permissao in permissoes_perfil
    )


def salvar_perfil(perfil_id, nome, permissoes):
    nome = nome.strip()
    if not nome:
        return False, "Informe o nome do perfil."
    if not isinstance(permissoes, list) or any(
        not isinstance(permissao, str) for permissao in permissoes
    ):
        return False, "Lista de permissões inválida."
    permitidas = {
        f"{area}.{acao}" for area, acoes in ACOES_POR_RECURSO.items()
        for acao in acoes
    }
    if any(permissao not in permitidas for permissao in permissoes):
        return False, "O perfil contém permissões não reconhecidas."
    permissoes_unicas = set(permissoes)
    for area, _ in PERMISSOES:
        if (
            f"{area}.editar" in permissoes_unicas
            or f"{area}.exportar" in permissoes_unicas
        ) and f"{area}.ver" not in permissoes_unicas:
            return False, "Permissões de edição ou exportação também exigem acesso de consulta."
    if not permissoes_unicas:
        return False, "O perfil precisa ter ao menos uma permissão de consulta."

    perfis = _ler_perfis()
    if perfil_id == "admin":
        return False, "O perfil TI mantém acesso total e não pode ser alterado."
    if not perfil_id:
        identificador = unicodedata.normalize("NFKD", nome)
        identificador = "".join(
            caractere for caractere in identificador
            if not unicodedata.combining(caractere)
        )
        identificador = re.sub(r"[^a-zA-Z0-9]+", "-", identificador.lower()).strip("-")
        perfil_id = identificador[:40]
        if not perfil_id or any(p["id"] == perfil_id for p in perfis):
            return False, "Já existe um perfil com esse nome."
        perfis.append({
            "id": perfil_id,
            "nome": nome,
            "permissoes": sorted(permissoes_unicas),
            "sistema": False,
        })
    else:
        perfil = next((p for p in perfis if p["id"] == perfil_id), None)
        if not perfil:
            return False, "Perfil não encontrado."
        perfil["nome"] = nome
        perfil["permissoes"] = sorted(permissoes_unicas)
    os.makedirs(DADOS, exist_ok=True)
    _salvar(perfis)
    return True, "Perfil salvo."


def excluir_perfil(perfil_id, perfis_em_uso):
    if perfil_id in {"admin", "recepcao"}:
        return False, "Os perfis padrão não podem ser excluídos."
    perfis = _ler_perfis()
    if perfil_id not in {perfil["id"] for perfil in perfis}:
        return False, "Perfil não encontrado."
    if perfil_id in perfis_em_uso:
        return False, "Reatribua os usuários antes de excluir este perfil."
    perfis = [perfil for perfil in perfis if perfil["id"] != perfil_id]
    _salvar(perfis)
    return True, "Perfil excluído."


def _salvar(perfis):
    os.makedirs(DADOS, exist_ok=True)
    fd, temporario = tempfile.mkstemp(
        prefix=".perfis-", suffix=".tmp", dir=DADOS
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as arquivo:
            json.dump(perfis, arquivo, ensure_ascii=False, indent=2)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, ARQ_PERFIS)
    except Exception:
        if os.path.exists(temporario):
            os.unlink(temporario)
        raise