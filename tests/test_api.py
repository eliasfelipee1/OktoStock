"""Integracao real com PostgreSQL; cada teste usa um schema temporario isolado."""
import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
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


def build(c, amount='900', cost='0.01'):
    ingredient = c.post('/insumos', json={'nome': 'Batata', 'unidade': 'g'}).json()['id']
    p = c.post('/produtos', json={'nome': 'Batata exemplo', 'preco': '30.00',
        'ingredientes': [{'insumo_id': ingredient, 'quantidade': '450'}]}).json()['id']
    lot = c.post('/estoque/recebimentos', json={'insumo_id': ingredient, 'codigo': 'A', 'fornecedor': 'Teste',
        'validade': str(date.today() + timedelta(days=10)), 'quantidade': amount, 'custo_unitario': cost}).json()['id']
    shift = c.post('/turnos').json()['id']
    sale = {'idempotency_key': str(uuid4()), 'turno_id': shift,
            'itens': [{'produto_id': p, 'quantidade': 1}], 'pagamentos': [{'forma': 'pix', 'valor': '30.00'}]}
    return ingredient, lot, sale


def test_sale_fefo_idempotency_history(setup):
    c = setup
    ingredient, lot, body = build(c)
    earlier = c.post('/estoque/recebimentos', json={'insumo_id': ingredient, 'codigo': 'B', 'fornecedor': 'Teste',
        'validade': str(date.today() + timedelta(days=2)), 'quantidade': '200', 'custo_unitario': '0.02'}).json()['id']
    first = c.post('/vendas', json=body)
    assert first.status_code == 201, first.text
    sale = first.json()
    assert Decimal(str(sale['custo'])) == Decimal('6.50')
    assert c.post('/vendas', json=body).json()['id'] == sale['id']
    balances = {r['id']: Decimal(str(r['saldo'])) for r in c.get('/estoque/lotes').json()}
    assert balances[earlier] == 0 and balances[lot] == 650
    c.post(f"/produtos/{body['itens'][0]['produto_id']}/desativar")
    history = c.get('/vendas/' + sale['id']).json()
    assert history['itens'][0]['versao'] == 1 and len(history['consumos']) == 2
    assert Decimal(str(history['itens'][0]['preco'])) == 30


def test_shortage_rolls_back_everything(setup):
    c = setup
    _, lot, body = build(c, amount='100')
    assert c.post('/vendas', json=body).json()['detail']['codigo'] == 'ESTOQUE_INSUFICIENTE'
    with connect() as db:
        assert db.execute('SELECT count(*) AS n FROM vendas').fetchone()['n'] == 0
        assert db.execute("SELECT count(*) AS n FROM movimentacoes WHERE tipo='venda'").fetchone()['n'] == 0
        assert db.execute('SELECT saldo FROM lotes WHERE id=%s', (lot,)).fetchone()['saldo'] == 100


def test_concurrent_last_portion(setup):
    c = setup
    _, _, body = build(c, amount='450')
    other = dict(body, idempotency_key=str(uuid4()))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda b: c.post('/vendas', json=b), [body, other]))
    assert sorted(r.status_code for r in results) == [201, 409]
    assert Decimal(str(c.get('/estoque/lotes').json()[0]['saldo'])) == 0


def test_concurrent_duplicate(setup):
    c = setup
    _, _, body = build(c, amount='450')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: c.post('/vendas', json=body), range(2)))
    assert [r.status_code for r in results] == [201, 201]
    assert results[0].json()['id'] == results[1].json()['id']


def test_expired_lot_not_used(setup):
    c = setup
    _, lot, body = build(c)
    with connect() as db:
        db.execute("UPDATE lotes SET validade=CURRENT_DATE-1 WHERE id=%s", (lot,))
    assert c.post('/vendas', json=body).status_code == 409
    assert c.get('/disponibilidade').json()[0]['porcoes'] == 0


def test_permissions_and_other_operation(setup):
    c = setup
    _, _, body = build(c)
    c.headers['Authorization'] = 'Bearer ia'
    assert c.get('/relatorios/estoque').status_code == 200
    assert c.post('/vendas', json=body).status_code == 403
    c.headers['Authorization'] = 'Bearer caixa'
    assert c.post('/vendas', json=body).status_code == 403
    with connect() as db:
        op = db.execute("INSERT INTO operacoes(nome) VALUES('Outra') RETURNING id").fetchone()['id']
        db.execute('INSERT INTO usuarios(operacao_id,nome,papel,token_hash) VALUES(%s,%s,%s,%s)',
                   (op, 'outro', 'gerente', hashlib.sha256(b'outro').hexdigest()))
    c.headers['Authorization'] = 'Bearer outro'
    assert c.get('/produtos').json() == []
    assert c.get('/relatorios/estoque').json() == []
    assert c.post('/vendas', json=body).status_code == 409


def test_payment_key_conflict_and_closed_shift(setup):
    c = setup
    _, _, body = build(c)
    wrong = dict(body, pagamentos=[{'forma': 'pix', 'valor': '1.00'}])
    assert c.post('/vendas', json=wrong).json()['detail']['codigo'] == 'PAGAMENTO_DIVERGENTE'
    assert c.post('/vendas', json=body).status_code == 201
    assert c.post('/vendas', json=wrong).json()['detail']['codigo'] == 'CHAVE_REUTILIZADA_COM_OUTRO_CONTEUDO'
    assert c.post('/turnos/' + body['turno_id'] + '/fechar').status_code == 200
    assert c.post('/vendas', json=dict(body, idempotency_key=str(uuid4()))).json()['detail']['codigo'] == 'TURNO_FECHADO'
    assert c.post('/vendas', json=body).status_code == 201


def test_loss_refund_and_reports(setup):
    c = setup
    _, lot, body = build(c)
    sale = c.post('/vendas', json=body).json()
    assert c.post('/vendas/' + sale['id'] + '/estornar', json={'motivo': 'Cliente desistiu'}).status_code == 200
    assert Decimal(str(c.get('/estoque/lotes').json()[0]['saldo'])) == 450
    assert c.post('/estoque/perdas', json={'lote_id': lot, 'quantidade': '50', 'motivo': 'Derramado'}).status_code == 200
    assert c.post('/estoque/perdas', json={'lote_id': lot, 'quantidade': '999', 'motivo': 'Derramado'}).status_code == 409
    for route in ['vendas', 'produtos', 'consumo', 'estoque']:
        assert c.get('/relatorios/' + route).status_code == 200
    report = c.get('/relatorios/vendas').json()[0]
    assert Decimal(str(report['margem_ingredientes'])) == Decimal('-4.5')


def test_invalid_precision_and_duplicate_recipe(setup):
    c = setup
    ingredient, _, _ = build(c)
    assert c.post('/insumos', json={'nome': 'X', 'unidade': 'g', 'estoque_minimo': '0.0001'}).status_code == 422
    i = {'insumo_id': ingredient, 'quantidade': '1'}
    assert c.post('/produtos', json={'nome': 'X', 'preco': '10', 'ingredientes': [i, i]}).status_code == 422


def test_second_ingredient_shortage_restores_first(setup):
    c = setup
    first, lot, body = build(c)
    second = c.post('/insumos', json={'nome': 'Queijo', 'unidade': 'g'}).json()['id']
    product = c.post('/produtos', json={'nome': 'Duas baixas', 'preco': '30', 'ingredientes': [
        {'insumo_id': first, 'quantidade': '450'}, {'insumo_id': second, 'quantidade': '100'}]}).json()['id']
    body['itens'][0]['produto_id'] = product
    assert c.post('/vendas', json=body).status_code == 409
    with connect() as db:
        assert db.execute('SELECT saldo FROM lotes WHERE id=%s', (lot,)).fetchone()['saldo'] == 900
        assert db.execute('SELECT count(*) AS n FROM vendas').fetchone()['n'] == 0
