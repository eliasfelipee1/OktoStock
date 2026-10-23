from datetime import date, timedelta
from decimal import Decimal as D
from uuid import uuid4
import pytest
from app.db import connect
from app.purchasing import compare
from app.monitor import refresh_all


def offer(**kwargs):
    return {'id':str(uuid4()),'quantidade_embalagem':D('1000'),'preco_embalagem':D('10'),
            'minimo_embalagens':1,'frete':D('0'),'prazo_dias':1,'ativo':True,'fornecedor_ativo':True,
            'cotado_em':date.today(),'valido_ate':date.today()+timedelta(days=2),**kwargs}


def test_price_comparison_rounds_packages_and_includes_minimum_shipping_expiry():
    cheap=offer(preco_embalagem=D('8'),frete=D('50'))
    best=offer(preco_embalagem=D('12'))
    minimum=offer(preco_embalagem=D('7'),minimo_embalagens=10)
    expired=offer(preco_embalagem=D('1'),valido_ate=date.today()-timedelta(days=1))
    incomplete=offer(preco_embalagem=D('1'),frete=None)
    rows=compare([cheap,best,minimum,expired,incomplete],D('1500'),date.today())
    assert rows[0]['id']==best['id'] and rows[0]['total_entregue']==24
    assert rows[0]['embalagens']==2 and rows[0]['quantidade_total']==2000
    assert next(r for r in rows if r['id']==minimum['id'])['embalagens']==10
    assert not next(r for r in rows if r['id']==expired['id'])['elegivel']
    assert not next(r for r in rows if r['id']==incomplete['id'])['elegivel']
    assert compare([best],D(0),date.today())==[]


def recipe(c,item,qty='10',name='Sabor'):
    return c.post('/produtos',json={'nome':name,'preco':'20','ingredientes':[{'insumo_id':item,'quantidade':qty}]}).json()


def ingredient(c):
    return c.post('/insumos',json={'nome':'Batata','unidade':'g','estoque_minimo':'0'}).json()['id']


def receive(c,item,amount):
    r=c.post('/estoque/recebimentos',json={'insumo_id':item,'codigo':str(uuid4()),'fornecedor':'Teste',
          'validade':str(date.today()+timedelta(days=2)),'quantidade':str(amount),'custo_unitario':'0.01'})
    assert r.status_code==201,r.text
    return r.json()


def test_shared_ingredients_50_each_threshold_resolution_reopen_and_expiry(setup):
    c=setup; item=ingredient(c)
    recipe(c,item,'10','A');recipe(c,item,'20','B')
    data=c.get('/reposicao').json();a=data['alertas'][0]
    assert D(str(a['minimo']))==1500 # 50*10 + 50*20, não o máximo individual.
    first=a['alerta']['id']
    assert c.get('/reposicao').json()['alertas'][0]['alerta']['id']==first
    receive(c,item,1499)
    assert len(c.get('/reposicao').json()['alertas'])==1
    receive(c,item,1)
    assert c.get('/reposicao').json()['alertas']==[] # igualdade não dispara
    with connect() as db:
        db.execute('UPDATE lotes SET validade=CURRENT_DATE-1 WHERE insumo_id=%s',(item,))
    a=c.get('/reposicao').json()['alertas'][0]
    assert a['alerta']['id']!=first and D(str(a['saldo']))==0
    with connect() as db:
        assert db.execute('SELECT count(*) AS n FROM alertas_reposicao WHERE resolvido_em IS NULL').fetchone()['n']==1
    refresh_all()
    assert c.get('/reposicao').json()['alertas'][0]['alerta']['id']==a['alerta']['id']


def test_supplier_quotes_permissions_isolation_and_missing_data(setup):
    c=setup;item=ingredient(c);recipe(c,item)
    supplier=c.post('/fornecedores',json={'nome':'Fornecedor real'}).json()
    assert c.post('/fornecedores',json={'nome':'Fornecedor real'}).status_code==409
    payload={'fornecedor_id':supplier['id'],'insumo_id':item,'quantidade_embalagem':'1000',
             'preco_embalagem':'10','minimo_embalagens':1,'cotado_em':str(date.today()),'valido_ate':str(date.today()+timedelta(days=2))}
    assert c.post('/cotacoes',json=payload).status_code==201
    assert c.get('/reposicao').json()['alertas'][0]['melhor_oferta'] is None
    payload.update(frete='0',prazo_dias=1)
    assert c.post('/cotacoes',json=payload).status_code==201
    data=c.get('/reposicao').json();assert D(str(data['alertas'][0]['melhor_oferta']['total_entregue']))==10
    assert sum(q['ativo'] for q in data['cotacoes'])==1
    with connect() as db:
        other=db.execute("INSERT INTO operacoes(nome) VALUES('Outra') RETURNING id").fetchone()['id']
        foreign=db.execute("INSERT INTO fornecedores(operacao_id,nome) VALUES(%s,'SEGREDO') RETURNING id",(other,)).fetchone()['id']
    assert 'SEGREDO' not in c.get('/reposicao').text
    assert c.post('/cotacoes',json={**payload,'fornecedor_id':str(foreign)}).status_code==404
    c.headers['Authorization']='Bearer ia'
    assert c.get('/reposicao').status_code==200
    assert c.post('/fornecedores',json={'nome':'Bloqueado'}).status_code==403
    assert c.post('/cotacoes',json=payload).status_code==403


def test_draft_recipe_requires_real_details_and_activated_recipe_is_immutable(setup):
    c=setup;item=ingredient(c)
    with connect() as db:
        op=db.execute('SELECT id FROM operacoes LIMIT 1').fetchone()['id']
        product=db.execute("INSERT INTO produtos(operacao_id,nome,preco,ativo,ficha_detalhes) VALUES(%s,'Vegetariana',NULL,false,'{\"cardapio_atual\":true}') RETURNING id",(op,)).fetchone()['id']
    data=c.get('/reposicao').json();assert data['pendencias_fichas']==['Vegetariana']
    assert data['alertas']==[]
    body={'ingredientes':[{'insumo_id':item,'quantidade':'10'}],'preparo':'Receita informada','validada':True}
    assert c.put('/fichas/'+str(product),json=body).status_code==422
    body['preco']='20'
    assert c.put('/fichas/'+str(product),json=body).status_code==200
    assert c.get('/reposicao').json()['pendencias_fichas']==[]
    assert c.get('/reposicao').json()['alertas'][0]['minimo']==500
    assert c.put('/fichas/'+str(product),json=body).status_code==409


def test_local_write_cannot_bypass_remote_or_cross_origin(setup,monkeypatch):
    c=setup
    with connect() as db:
        op=db.execute('SELECT id FROM operacoes LIMIT 1').fetchone()['id']
        db.execute("INSERT INTO contextos_operacionais(operacao_id,parametros) VALUES(%s,'{\"natureza_dados\":\"simulados\"}')",(op,))
    monkeypatch.setenv('LOCAL_DEMO_OPERATION_ID',str(op));monkeypatch.setenv('DEMO_ACESSO_REMOTO','1')
    assert c.post('/demo/fornecedores',json={'nome':'Forbidden'}).status_code==403
    assert c.post('/demo/fornecedores',headers={'origin':'https://other.example'},json={'nome':'Forbidden'}).status_code==403


def test_real_local_operation_accepts_panel_writes_but_never_remote(setup, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    with connect() as db:
        op=db.execute('SELECT id FROM operacoes LIMIT 1').fetchone()['id']
        db.execute("INSERT INTO contextos_operacionais(operacao_id,parametros) VALUES(%s,'{\"natureza_dados\":\"cadastro_real_local\"}')",(op,))
    monkeypatch.setenv('LOCAL_DEMO_OPERATION_ID',str(op))
    monkeypatch.setenv('DEMO_ACESSO_REMOTO','1')
    with TestClient(app,base_url='http://localhost',client=('127.0.0.1',50000)) as c:
        assert c.get('/demo/reposicao').status_code==200
        assert c.post('/demo/fornecedores',json={'nome':'Real local'}).status_code==201
        assert c.post('/demo/fornecedores',json={'nome':'Cross-site'},headers={'origin':'https://evil.example'}).status_code==403
        item=c.post('/demo/insumos',json={'nome':'Real','unidade':'g'}).json()['id']
        assert c.post('/demo/estoque/recebimentos',json={'insumo_id':item,'codigo':'Real',
            'fornecedor':'Real local','validade':str(date.today()+timedelta(days=1)),
            'quantidade':'10','custo_unitario':'0.01'}).status_code==201
    with TestClient(app,base_url='http://localhost',client=('192.168.1.8',50000)) as remote:
        assert remote.get('/demo/reposicao').status_code==403
        assert remote.post('/demo/fornecedores',json={'nome':'Forbidden'}).status_code==403
