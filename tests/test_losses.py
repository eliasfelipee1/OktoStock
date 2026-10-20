from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from app.db import connect
from test_api import build


def test_recipe_loss_fefo_idempotency_and_report(setup):
    c = setup
    insumo, lot, sale = build(c)
    product = sale['itens'][0]['produto_id']
    c.post('/estoque/recebimentos', json={'insumo_id': insumo, 'codigo': 'FIRST', 'fornecedor': 'Teste',
        'validade': str(date.today()+timedelta(days=1)), 'quantidade': '100', 'custo_unitario': '0.02'})
    body = {'produto_id': product, 'porcoes': '1', 'motivo': 'Queima no preparo',
            'turno_id': sale['turno_id'], 'idempotency_key': str(uuid4())}
    response = c.post('/estoque/perdas/receita', json=body)
    assert response.status_code == 201, response.text
    loss = response.json()
    assert Decimal(str(loss['custo_total'])) == Decimal('5.50')
    assert len(loss['consumos']) == 2
    assert c.post('/estoque/perdas/receita', json=body).json()['id'] == loss['id']
    report = c.get('/relatorios/perdas', params={'turno_id': sale['turno_id']}).json()
    assert Decimal(str(report['custo_total_perdas'])) == Decimal('5.50')
    assert report['por_receita'][0]['porcoes_registradas'] == 1
    assert report['quantidades_por_unidade'] == {'g': 450}
    assert report['percentual_sobre_faturamento_bruto'] is None
    with connect() as db:
        assert db.execute('SELECT saldo FROM lotes WHERE id=%s', (lot,)).fetchone()['saldo'] == 550
        db.execute('UPDATE lotes SET custo_unitario=99 WHERE id=%s', (lot,))
    assert Decimal(str(c.get('/relatorios/perdas').json()['custo_total_perdas'])) == Decimal('5.50')
    body['porcoes'] = '2'
    assert c.post('/estoque/perdas/receita', json=body).status_code == 409


def test_ingredient_loss_and_legacy_unassigned_totals(setup):
    c = setup
    _, lot, sale = build(c)
    body = {'lote_id': lot, 'quantidade': '100', 'motivo': 'Sobra de preparo',
            'produto_id': sale['itens'][0]['produto_id'], 'idempotency_key': str(uuid4())}
    assert c.post('/estoque/perdas', json=body).status_code == 200
    assert c.post('/estoque/perdas', json=body).status_code == 200
    with connect() as db:
        u = db.execute("SELECT * FROM usuarios WHERE nome='gerente'").fetchone()
        db.execute('UPDATE lotes SET saldo=saldo-50 WHERE id=%s', (lot,))
        db.execute('''INSERT INTO movimentacoes(operacao_id,lote_id,usuario_id,tipo,quantidade,custo_unitario,motivo)
            VALUES(%s,%s,%s,'perda',-50,0.01,'Registro legado')''', (u['operacao_id'],lot,u['id']))
    assert c.post('/vendas', json=sale).status_code == 201
    r = c.get('/relatorios/perdas').json()
    assert Decimal(str(r['custo_total_perdas'])) == Decimal('1.5')
    assert len(r['por_receita']) == 2
    assert any(x['produto_id'] is None for x in r['por_receita'])
    assert r['percentual_sobre_faturamento_bruto'] == 5
    assert r['quantidades_por_unidade'] == {'g': 150}


def test_recipe_shortage_rolls_back(setup):
    c = setup
    _, lot, sale = build(c, amount='100')
    body = {'produto_id': sale['itens'][0]['produto_id'], 'porcoes': '1',
            'motivo': 'Erro no preparo', 'idempotency_key': str(uuid4())}
    assert c.post('/estoque/perdas/receita', json=body).status_code == 409
    with connect() as db:
        assert db.execute('SELECT count(*) AS n FROM perdas').fetchone()['n'] == 0
        assert db.execute('SELECT saldo FROM lotes WHERE id=%s', (lot,)).fetchone()['saldo'] == 100


def test_loss_scoping_permissions_period_and_unknown_recipe(setup):
    c = setup
    _, lot, sale = build(c)
    product = sale['itens'][0]['produto_id']
    other = c.post('/insumos', json={'nome': 'Outro', 'unidade': 'ml'}).json()['id']
    other_product = c.post('/produtos', json={'nome': 'Outro', 'preco': '10',
        'ingredientes': [{'insumo_id': other, 'quantidade': '1'}]}).json()['id']
    body = {'lote_id': lot, 'quantidade': '10', 'motivo': 'Sobra no preparo', 'produto_id': other_product}
    assert c.post('/estoque/perdas', json=body).status_code == 422
    body['produto_id'] = str(uuid4())
    assert c.post('/estoque/perdas', json=body).status_code == 404
    body['produto_id'] = product
    with connect() as db:
        other_op = db.execute("INSERT INTO operacoes(nome) VALUES('Outra') RETURNING id").fetchone()['id']
        foreign = db.execute("INSERT INTO produtos(operacao_id,nome,preco) VALUES(%s,'Segredo',10) RETURNING id", (other_op,)).fetchone()['id']
    body['produto_id'] = str(foreign)
    assert c.post('/estoque/perdas', json=body).status_code == 404
    assert c.get('/relatorios/perdas?inicio=2026-10-20&fim=2026-10-01').status_code == 422
    c.headers['Authorization'] = 'Bearer caixa'
    assert c.get('/relatorios/perdas').status_code == 403
    c.headers['Authorization'] = 'Bearer ia'
    assert c.get('/relatorios/perdas').status_code == 200
    assert c.post('/estoque/perdas', json=body).status_code == 403


def test_otto_receives_losses_without_operator_ids(setup):
    c = setup
    _, lot, sale = build(c)
    c.post('/estoque/perdas', json={'lote_id': lot, 'produto_id': sale['itens'][0]['produto_id'],
        'quantidade': '100', 'motivo': 'Queima no forno'})
    with connect() as db:
        db.execute("UPDATE movimentacoes SET criado_em=CURRENT_DATE-1 WHERE tipo='perda'")
    ctx = c.get('/ia/contexto').json()
    assert ctx['perdas']['custo_total_perdas'] == 1
    assert ctx['perdas']['por_receita'][0]['nome'] == 'Batata exemplo'
    assert 'registros' not in ctx['perdas']
