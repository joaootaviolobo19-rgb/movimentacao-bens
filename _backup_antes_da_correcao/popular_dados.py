import json
from pathlib import Path

Path("dados").mkdir(exist_ok=True)

funcionarios = [
    "João Silva",
    "Maria Souza",
    "Carlos Andrade",
    "Ana Paula"
]

bens = [
    "Notebook Dell Latitude 3420 - PAT0001",
    "Monitor LG 24 - PAT0002",
    "Impressora HP LaserJet - PAT0003",
    "Cadeira Gamer - PAT0004",
    "Celular Samsung A54 - PAT0005"
]

locais = [
    "Almoxarifado Central",
    "TI - 2 andar",
    "Financeiro",
    "RH",
    "Recepcao",
    "Sala de Reunioes"
]

with open("dados/funcionarios.json", "w", encoding="utf-8") as f:
    json.dump(funcionarios, f, ensure_ascii=False, indent=2)

with open("dados/bens.json", "w", encoding="utf-8") as f:
    json.dump(bens, f, ensure_ascii=False, indent=2)

with open("dados/locais.json", "w", encoding="utf-8") as f:
    json.dump(locais, f, ensure_ascii=False, indent=2)

print("Arquivos criados com sucesso!")
print("funcionarios.json:", len(funcionarios), "itens")
print("bens.json:", len(bens), "itens")
print("locais.json:", len(locais), "itens")