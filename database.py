# -*- coding: utf-8 -*-
import os
import json
from flask_sqlalchemy import SQLAlchemy

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARQ_CONFIG_DB = os.path.join(BASE_DIR, "dados", "config_db.json")

# Cria a instância do SQLAlchemy que será usada em todo o sistema
db = SQLAlchemy()

def init_db(app):
    """Lê o config_db.json e conecta o Flask ao PostgreSQL."""
    if not os.path.exists(ARQ_CONFIG_DB):
        raise FileNotFoundError(
            "Arquivo dados/config_db.json não encontrado. "
            "Crie-o com as credenciais do PostgreSQL."
        )
    
    with open(ARQ_CONFIG_DB, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    
    app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"postgresql+psycopg2://{cfg['user']}:{cfg['password']}@"
    f"{cfg['host']}:{cfg['port']}/{cfg['database']}"
)
    
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    # Inicializa a conexão com o Flask
    db.init_app(app)