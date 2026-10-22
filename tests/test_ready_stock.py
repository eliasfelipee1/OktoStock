from datetime import date,datetime,timedelta,timezone
from decimal import Decimal as D
from uuid import uuid4
import pytest
from app.db import connect
from app.monitor import refresh_all


def setup_ready(c,high=False):
    item=c.post('/insumos',json={'nome':'Batata','unidade':'g'}).json()['id']
    product=c.post('/produtos',json={'nome':'Sabor pronto','preco':'20','ingredientes':[{'insumo_id':item,'quantidade':'10'}]}).json()['id']
    with connect() as db:
        op=db.execute('SELECT operacao_id FROM produtos WHERE id=%s',(product,)).fetchone()['operacao_id']
        db.execute("UPDATE produtos SET ficha_detalhes='{\"controle_prontos\":true}' WHERE id=%s",(product,))
        db.execute('INSERT INTO configuracao_reposicao(operacao_id,controle_prontos,dias_movimento) VALUES(%s,true,%s)',(op,[1,2,3,4,5,6,7] if high else []))
    return item,product,op


def entry(product,amount,origin='saldo_inicial'):
    return {'produto_id':product,'idempotency_key':str(uuid4()),'codigo':'Teste','origem':origin,
        'quantidade':amount,'validade':(datetime.now(timezone.utc)+timedelta(hours=4)).isoformat(),
        'custo_unitario':'0.10' if origin=='saldo_inicial' else None}


@pytest.mark.parametrize('high,threshold',[(False,75),(True,300)])
def test_threshold_strict_30_percent_and_no_fabricated_count(setup,high,threshold):
    c=setup;_,p,op=setup_ready(c,high)
    before=c.get('/prontos').json();assert before['contagens_pendentes']==['Sabor pronto'] and before['alertas']==[]
    body=entry(p,threshold)
    r=c.post('/prontos/entradas',json=body);assert r.status_code==201,r.text
    assert c.post('/prontos/entradas',json=body).json()['id']==r.json()['id']
    assert c.get('/prontos').json()['alertas']==[]
    waste={'lote_id':r.json()['id'],'idempotency_key':str(uuid4()),'quantidade':1,'motivo':'Teste descarte'}
    assert c.post('/prontos/perdas',json=waste).status_code==201
    assert c.post('/prontos/perdas',json=waste).status_code==201
    a=c.get('/prontos').json()['alertas'][0]
    assert a['saldo']==threshold-1 and a['limite_alerta']==threshold
    same=a['alerta']['id'];refresh_all();assert c.get('/prontos').json()['alertas'][0]['alerta']['id']==same
    assert c.post('/prontos/entradas',json=entry(p,threshold)).status_code==409
    with connect() as db:db.execute('UPDATE lotes_prontos SET validade=now()-interval \'1 minute\' WHERE produto_id=%s',(p,))
    assert c.get('/prontos').json()['alertas'][0]['saldo']==0


def test_production_sale_no_double_ingredient_debit_and_atomic_shortage(setup):
    c=setup;item,p,op=setup_ready(c)
    receive=c.post('/estoque/recebimentos',json={'insumo_id':item,'codigo':'R','fornecedor':'Teste',
        'validade':str(date.today()+timedelta(days=3)),'quantidade':'1000','custo_unitario':'0.01'})
    assert receive.status_code==201
    body=entry(p,10,'producao');r=c.post('/prontos/entradas',json=body);assert r.status_code==201,r.text
    assert c.post('/prontos/entradas',json=body).json()['id']==r.json()['id']
    assert D(str(c.get('/estoque/lotes').json()[0]['saldo']))==900
    shift=c.post('/turnos').json()['id']
    sale={'idempotency_key':str(uuid4()),'turno_id':shift,'itens':[{'produto_id':p,'quantidade':2}], 'pagamentos':[{'forma':'pix','valor':'40'}]}
    sold=c.post('/vendas',json=sale);assert sold.status_code==201,sold.text
    assert D(str(sold.json()['custo']))==D('.2')
    assert c.get('/prontos').json()['sabores'][0]['saldo']==8
    assert D(str(c.get('/estoque/lotes').json()[0]['saldo']))==900
    assert c.post('/vendas',json=sale).json()['id']==sold.json()['id']
    bad={**sale,'idempotency_key':str(uuid4()),'itens':[{'produto_id':p,'quantidade':9}],'pagamentos':[{'forma':'pix','valor':'180'}]}
    assert c.post('/vendas',json=bad).status_code==409
    assert c.get('/prontos').json()['sabores'][0]['saldo']==8
    assert c.post('/prontos/entradas',json=entry(p,100,'producao')).status_code==409
    assert D(str(c.get('/estoque/lotes').json()[0]['saldo']))==900


def test_calendar_and_ingredient_plan_discount_ready_stock(setup):
    c=setup;item,p,op=setup_ready(c)
    c.post('/prontos/entradas',json=entry(p,250))
    assert c.get('/reposicao').json()['alertas']==[] # Meta calma completa: não compra ingredientes novamente.
    with connect() as db:db.execute('UPDATE configuracao_reposicao SET dias_movimento=ARRAY[1,2,3,4,5,6,7] WHERE operacao_id=%s',(op,))
    data=c.get('/reposicao').json()
    assert data['meta_por_sabor']==1000
    assert data['prontos']['alertas'][0]['saldo']==250
    assert D(str(data['alertas'][0]['necessidade']))==7500 # 750 faltantes * 10g, não 1000*10g


def test_foreign_product_and_public_reference_not_recommended(setup):
    c=setup;item,p,op=setup_ready(c)
    with connect() as db:
        other=db.execute("INSERT INTO operacoes(nome) VALUES('Outra') RETURNING id").fetchone()['id']
        foreign=db.execute("INSERT INTO produtos(operacao_id,nome,preco,ficha_detalhes) VALUES(%s,'Outra',20,'{\"controle_prontos\":true}') RETURNING id",(other,)).fetchone()['id']
        f=db.execute("INSERT INTO fornecedores(operacao_id,nome) VALUES(%s,'Rede real') RETURNING id",(op,)).fetchone()['id']
        db.execute('''INSERT INTO cotacoes(operacao_id,fornecedor_id,insumo_id,quantidade_embalagem,preco_embalagem,
          minimo_embalagens,frete,prazo_dias,cotado_em,valido_ate,referencia_publica,local_confirmado)
          VALUES(%s,%s,%s,1000,5,NULL,NULL,NULL,CURRENT_DATE,NULL,true,false)''',(op,f,item))
    assert c.post('/prontos/entradas',json=entry(str(foreign),10)).status_code==409
    a=c.get('/reposicao').json()['alertas'][0]
    assert a['melhor_oferta'] is None and 'Preço da loja de Blumenau não confirmado' in a['comparativo'][0]['pendencias']
    c.headers['Authorization']='Bearer ia'
    assert c.post('/prontos/entradas',json=entry(p,10)).status_code==403
