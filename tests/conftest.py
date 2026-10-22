import hashlib
import os
from uuid import uuid4
import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo
from app.db import connect
from app.main import app
from scripts.migrate import migrate


@pytest.fixture
def setup(monkeypatch):
    url = os.getenv('TEST_DATABASE_URL')
    if not url:
        pytest.skip('Defina TEST_DATABASE_URL para executar testes PostgreSQL reais')
    # Testes partem do padrão seguro, independente do .env local.
    monkeypatch.delenv('DEMO_ACESSO_REMOTO', raising=False)
    schema = 'test_' + uuid4().hex
    with psycopg.connect(url) as db:
        db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    monkeypatch.setenv('DATABASE_URL', make_conninfo(url, options=f'-csearch_path={schema},public'))
    try:
        migrate()
        with connect() as db:
            operation = db.execute("INSERT INTO operacoes(nome) VALUES('Teste') RETURNING id").fetchone()['id']
            for token, role in [('gerente', 'gerente'), ('caixa', 'caixa'), ('ia', 'ia')]:
                db.execute('INSERT INTO usuarios(operacao_id,nome,papel,token_hash) VALUES(%s,%s,%s,%s)',
                           (operation, token, role, hashlib.sha256(token.encode()).hexdigest()))
        with TestClient(app) as client:
            client.headers['Authorization'] = 'Bearer gerente'
            yield client
    finally:
        with psycopg.connect(url) as db:
            db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))

