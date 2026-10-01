import os
from pathlib import Path

exts = ('.py', '.html', '.css', '.json', '.txt', '.md', '.js', '.csv')
exclude_dirs = {'__pycache__', '.vscode', 'Microsoft VS Code', '.git', 'node_modules', 'venv', 'env', '_templates_antigos_NAO_USAR'}

saida = Path('../dump_projeto.txt')

with saida.open('w', encoding='utf-8') as out:
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for file in sorted(files):
            if file.endswith(exts):
                caminho = os.path.join(root, file)
                # pula arquivos grandes (>200KB, tipo o Excel)
                if os.path.getsize(caminho) > 200_000:
                    continue
                out.write(f"\n\n===== {caminho} =====\n\n")
                try:
                    with open(caminho, 'r', encoding='utf-8') as f:
                        out.write(f.read())
                except UnicodeDecodeError:
                    out.write("[arquivo binário, ignorado]")

print(f"✅ Pronto! Arquivo gerado em: {saida.resolve()}")