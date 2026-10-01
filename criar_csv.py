# -*- coding: utf-8 -*-
"""
criar_csv.py — Gera 'Levantamento Geral1(controle).csv' a partir do .xlsx
Coloca o CSV na pasta-mãe (python-script/), que é onde o csv_store procura.
"""
import os
import csv
import glob
from openpyxl import load_workbook

BASE = os.path.dirname(os.path.abspath(__file__))
PASTA_MAE = os.path.dirname(BASE)

# Onde salvar o CSV (mesma pasta que o app.py do projeto pai)
DESTINO_CSV = os.path.join(BASE, "Levantamento Geral1(controle).csv")

# Colunas esperadas (o cabeçalho que o csv_store usa)
CABECALHO = [
    "Categoria", "Modelo", "Hostname", "Patrimônio", "Departamento",
    "Responsável", "Marca", "Serial", "Ramal", "IP", "Observação",
    "CPU", "Disco", "RAM", "ISO", "Status",
    "Chave de auditoria", "VERIFICAÇÃO", "Departamento",
]

# Procura o xlsx na pasta atual ou na pasta-mãe
xlsx = None
for padrao in [
    os.path.join(BASE, "Levantamento*.xlsx"),
    os.path.join(PASTA_MAE, "Levantamento*.xlsx"),
]:
    achados = sorted(glob.glob(padrao))
    if achados:
        xlsx = achados[0]
        break

if not xlsx:
    print("ERRO: Nenhum .xlsx encontrado.")
    raise SystemExit(1)

print(f"Lendo: {xlsx}")

wb = load_workbook(xlsx, data_only=True)
# Pega a aba 'controle' (é onde estão os bens)
ws = wb["controle"]

# Lê cabeçalho da linha 1
header_raw = [c.value for c in ws[1]]
print(f"Cabeçalho encontrado: {header_raw[:8]} ...")

# Como o cabeçalho do xlsx tem nomes com acento/encoding variado,
# usamos POSICIONAL: as primeiras 19 colunas seguem a ordem esperada.
linhas = []
for row in ws.iter_rows(min_row=2, values_only=True):
    if not row:
        continue
    # Pula linha totalmente vazia
    if not any((c is not None and str(c).strip()) for c in row):
        continue
    # Pula linha que não tem categoria E não tem hostname E não tem patrimônio
    # (as centenas de ;;;;; no fim do CSV antigo)
    cat = row[0] if len(row) > 0 else None
    host = row[2] if len(row) > 2 else None
    patr = row[3] if len(row) > 3 else None
    if not cat and not host and not patr:
        continue

    # Normaliza a linha pro tamanho do cabeçalho
    linha = []
    for i in range(len(CABECALHO)):
        v = row[i] if i < len(row) else None
        linha.append("" if v is None else str(v).strip())
    linhas.append(linha)

# Escreve o CSV em UTF-8 com BOM (pra abrir no Excel sem perder acento)
with open(DESTINO_CSV, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f, delimiter=";")
    w.writerow(CABECALHO)
    w.writerows(linhas)

print(f"\n✅ CSV gerado com sucesso!")
print(f"   Arquivo: {DESTINO_CSV}")
print(f"   Registros: {len(linhas)}")
print(f"\nAgora roda: python app.py")