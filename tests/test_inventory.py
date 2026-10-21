from decimal import Decimal
from uuid import uuid4

from app.db import connect
from test_api import build


def test_count_adjusts_balance_and_is_idempotent(setup):
    c = setup
    _, lot, _ = build(c, amount='900', cost='0.01')
    body = {'lote_id': lot, 'saldo_contado': '850', 'motivo': 'Contagem do fim do turno', 'idempotency_key': str(uuid4())}
    response = c.post('/estoque/contagens', json=body)
    assert response.status_code == 201, response.text
    count = response.json()
    assert Decimal(str(count['saldo_sistema'])) == 900 and Decimal(str(count['diferenca'])) == -50
    assert Decimal(str(count['custo_diferenca'])) == Decimal('-0.5')
    assert c.post('/estoque/contagens', json=body).json()['id'] == count['id']
    with connect() as db:
        assert db.execute('SELECT saldo FROM lotes WHERE id=%s', (lot,)).fetchone()['saldo'] == 850
        moves = db.execute("SELECT * FROM movimentacoes WHERE tipo='ajuste'").fetchall()
        assert len(moves) == 1 and moves[0]['quantidade'] == -50 and str(moves[0]['contagem_id']) == count['id']
    body['saldo_contado'] = '800'
    assert c.post('/estoque/contagens', json=body).status_code == 409


def test_count_without_difference_creates_no_adjustment(setup):
    c = setup
    _, lot, _ = build(c, amount='900')
    body = {'lote_id': lot, 'saldo_contado': '900', 'motivo': 'Conferencia sem sobra', 'idempotency_key': str(uuid4())}
    assert c.post('/estoque/contagens', json=body).status_code == 201
    with connect() as db:
        assert db.execute("SELECT count(*) AS n FROM movimentacoes WHERE tipo='ajuste'").fetchone()['n'] == 0
        assert db.execute('SELECT count(*) AS n FROM contagens').fetchone()['n'] == 1


def test_count_can_raise_balance_or_zero_it(setup):
    c = setup
    _, lot, _ = build(c, amount='900')
    up = {'lote_id': lot, 'saldo_contado': '1000', 'motivo': 'Achei uma caixa', 'idempotency_key': str(uuid4())}
    assert Decimal(str(c.post('/estoque/contagens', json=up).json()['diferenca'])) == 100
    zero = {'lote_id': lot, 'saldo_contado': '0', 'motivo': 'Lote acabou', 'idempotency_key': str(uuid4())}
    assert c.post('/estoque/contagens', json=zero).status_code == 201
    with connect() as db:
        assert db.execute('SELECT saldo FROM lotes WHERE id=%s', (lot,)).fetchone()['saldo'] == 0
    history = c.get('/estoque/contagens', params={'lote_id': lot}).json()
    assert len(history['contagens']) == 2
    assert Decimal(str(history['custo_total_diferencas'])) == Decimal('-9')


def test_count_validation_scoping_and_permissions(setup):
    c = setup
    _, lot, _ = build(c)
    body = {'lote_id': str(uuid4()), 'saldo_contado': '10', 'motivo': 'Lote que nao existe', 'idempotency_key': str(uuid4())}
    assert c.post('/estoque/contagens', json=body).status_code == 404
    with connect() as db:
        other_op = db.execute("INSERT INTO operacoes(nome) VALUES('Outra') RETURNING id").fetchone()['id']
        foreign = db.execute("INSERT INTO insumos(operacao_id,nome,unidade) VALUES(%s,'X','g') RETURNING id", (other_op,)).fetchone()['id']
        foreign_lot = db.execute('''INSERT INTO lotes(operacao_id,insumo_id,codigo,fornecedor,validade,saldo,custo_unitario)
            VALUES(%s,%s,'F','F',CURRENT_DATE+5,10,1) RETURNING id''', (other_op, foreign)).fetchone()['id']
    body['lote_id'] = str(foreign_lot)
    assert c.post('/estoque/contagens', json=body).status_code == 404
    body.update(lote_id=lot, saldo_contado='-1')
    assert c.post('/estoque/contagens', json=body).status_code == 422
    body.update(saldo_contado='10')
    assert c.get('/estoque/contagens?inicio=2026-10-20&fim=2026-10-01').status_code == 422
    c.headers['Authorization'] = 'Bearer caixa'
    assert c.post('/estoque/contagens', json=body).status_code == 403
    assert c.get('/estoque/contagens').status_code == 403
    c.headers['Authorization'] = 'Bearer ia'
    assert c.get('/estoque/contagens').status_code == 200
    assert c.post('/estoque/contagens', json=body).status_code == 403


def test_suggestions_put_never_counted_lots_first(setup):
    c = setup
    ingredient, counted, _ = build(c)
    pending = c.post('/estoque/recebimentos', json={'insumo_id': ingredient, 'codigo': 'B', 'fornecedor': 'Teste',
        'validade': '2099-01-01', 'quantidade': '100', 'custo_unitario': '0.01'}).json()['id']
    c.post('/estoque/contagens', json={'lote_id': counted, 'saldo_contado': '900', 'motivo': 'Conferencia',
                                       'idempotency_key': str(uuid4())})
    order = [r['lote_id'] for r in c.get('/estoque/contagens/sugestoes').json()]
    assert order == [pending, counted]
