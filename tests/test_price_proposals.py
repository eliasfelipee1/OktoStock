from copy import deepcopy
from datetime import date,timedelta
from uuid import uuid4
import pytest
from app.db import connect
from app import ai, price_proposals as pp


def prepare(c):
    ing=c.post('/insumos',json={'nome':'Batata','unidade':'g','estoque_minimo':'0'}).json()['id']
    supplier=c.post('/fornecedores',json={'nome':'Fornecedor'}).json()['id']
    quote={'fornecedor_id':supplier,'insumo_id':ing,'quantidade_embalagem':'1000','preco_embalagem':'9.99',
        'minimo_embalagens':1,'frete':'0','prazo_dias':1,'cotado_em':str(date.today()),'valido_ate':str(date.today()+timedelta(days=3))}
    old=c.post('/cotacoes',json=quote).json()
    with connect() as db:u=db.execute("SELECT * FROM usuarios WHERE nome='gerente'").fetchone()
    context=ai.build_context(u['operacao_id'])
    candidate={k:v for k,v in quote.items() if k in ('fornecedor_id','insumo_id','quantidade_embalagem')}
    candidate.update(preco_embalagem='7.49',unidade='g',fonte_url='https://example.com/batata',produto_pesquisado='Batata 1kg')
    result={'_candidatos_precos':[candidate],'pesquisa_web_utilizada':True,'fontes_web':[{'url':candidate['fonte_url']} ]}
    return u,context,result,old,quote


def test_confirmation_only_updates_after_explicit_approval_and_is_idempotent(setup):
    c=setup;u,context,result,old,_=prepare(c)
    draft=pp.attach(result,u['operacao_id'],context)['propostas_precos'][0]
    with connect() as db:assert db.execute('SELECT ativo FROM cotacoes WHERE id=%s',(old['id'],)).fetchone()['ativo']
    path=f"/ia/propostas-precos/{draft['id']}/confirmar"
    assert c.post(path,json={}).status_code==422
    assert c.post(path,json={'confirmar':False}).status_code==422
    r=c.post(path,json={'confirmar':True});assert r.status_code==200,r.text
    again=c.post(path,json={'confirmar':True}).json()
    assert again['cotacao_id']==r.json()['cotacao_id'] and again['ja_confirmada']
    with connect() as db:
        rows=db.execute('SELECT * FROM cotacoes WHERE operacao_id=%s ORDER BY ativo',(u['operacao_id'],)).fetchall()
        assert len(rows)==2 and not rows[0]['ativo'] and rows[1]['ativo']
        q=rows[1];assert str(q['preco_embalagem'])=='7.49' and q['referencia_publica'] and not q['local_confirmado']
        assert q['frete'] is None and q['valido_ate'] is None
        assert db.execute("SELECT count(*) AS n FROM auditoria WHERE acao='confirmar_preco_pesquisado'").fetchone()['n']==1
    assert any(str(q['preco_embalagem'])=='7.49' for q in c.get('/reposicao').json()['cotacoes'])


def test_cancellation_never_changes_quote(setup):
    c=setup;u,ctx,result,old,_=prepare(c)
    draft=pp.attach(result,u['operacao_id'],ctx)['propostas_precos'][0]
    prefix=f"/ia/propostas-precos/{draft['id']}"
    assert c.post(prefix+'/cancelar').status_code==200
    assert c.post(prefix+'/confirmar',json={'confirmar':True}).status_code==409
    with connect() as db:assert db.execute('SELECT ativo FROM cotacoes WHERE id=%s',(old['id'],)).fetchone()['ativo']


def test_stale_and_expired_proposals_rejected(setup):
    c=setup;u,ctx,result,_,quote=prepare(c)
    drafts=[pp.attach(deepcopy(result),u['operacao_id'],ctx)['propostas_precos'][0] for _ in range(2)]
    with connect() as db:db.execute("UPDATE propostas_precos_otto SET expira_em=now()-interval '1 hour' WHERE id=%s",(drafts[0]['id'],))
    assert c.post(f"/ia/propostas-precos/{drafts[0]['id']}/confirmar",json={'confirmar':True}).json()['detail']['codigo']=='PROPOSTA_EXPIRADA'
    c.post('/cotacoes',json={**quote,'preco_embalagem':'8.00'})
    assert c.post(f"/ia/propostas-precos/{drafts[1]['id']}/confirmar",json={'confirmar':True}).json()['detail']['codigo']=='COTACAO_ALTERADA_PESQUISE_NOVAMENTE'


def test_source_unit_identity_permissions_and_tenant_are_checked(setup):
    c=setup;u,ctx,result,_,_=prepare(c)
    for key,value in [('fonte_url','https://not-cited.example'),('unidade','ml'),('fornecedor_id',str(uuid4())),('preco_embalagem','-1')]:
        invalid=deepcopy(result);invalid['_candidatos_precos'][0][key]=value
        assert pp.attach(invalid,u['operacao_id'],ctx)['propostas_precos']==[]
    draft=pp.attach(deepcopy(result),u['operacao_id'],ctx)['propostas_precos'][0]
    path=f"/ia/propostas-precos/{draft['id']}/confirmar"
    c.headers['Authorization']='Bearer ia';assert c.post(path,json={'confirmar':True}).status_code==403
    with connect() as db:
        other=db.execute("INSERT INTO operacoes(nome) VALUES('Outra') RETURNING id").fetchone()['id']
        db.execute('UPDATE propostas_precos_otto SET operacao_id=%s WHERE id=%s',(other,draft['id']))
    c.headers['Authorization']='Bearer gerente';assert c.post(path,json={'confirmar':True}).status_code==404


def test_candidate_block_split_and_invalid_json():
    research={'blocos':[{'texto':'Preço encontrado.','fontes':[1]},{'texto':'```propostas_','fontes':[]},{'texto':'precos\n[{"preco_embalagem":"7.49"}]\n```','fontes':[]}]}
    assert pp.split_candidates(research)==[{'preco_embalagem':'7.49'}]
    assert research['blocos']==[{'texto':'Preço encontrado.','fontes':[1]}]
    broken={'blocos':[{'texto':'Confira a fonte.```propostas_precos INVALID','fontes':[1]}]}
    assert pp.split_candidates(broken)==[] and broken['blocos'][0]['texto']=='Confira a fonte.'
