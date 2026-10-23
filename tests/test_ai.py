import hashlib
import json
from decimal import Decimal
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import ai
from app.db import connect
from app.main import app


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-placeholder-never-real')
    monkeypatch.setenv('OTTO_WEB_SEARCH', '0')
    client = MagicMock()
    monkeypatch.setattr(ai.httpx, 'Client', MagicMock(return_value=client))
    client.__enter__.return_value = client
    return client


def context():
    return {'periodo': {'inicio': '2026-10-01'}, 'gerado_em': '2026-10-08', 'insumos_truncados': False}


def test_missing_key_never_calls_provider(monkeypatch):
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    client = MagicMock()
    monkeypatch.setattr(ai.httpx, 'Client', client)
    with pytest.raises(HTTPException) as exc:
        ai.answer('Como estamos?', context())
    assert exc.value.status_code == 503
    client.assert_not_called()


def test_provider_request_and_text_extraction(provider):
    provider.post.return_value = httpx.Response(200, json={'stop_reason': 'end_turn', 'content': [
        {'type': 'thinking', 'thinking': 'internal'},
        {'type': 'text', 'text': 'Estoque suficiente.'}]})
    result = ai.answer('O que comprar?', context())
    assert result['resposta'] == 'Estoque suficiente.'
    args, kwargs = provider.post.call_args
    assert args[0] == 'https://api.anthropic.com/v1/messages'
    assert kwargs['headers'] == {'x-api-key': 'test-placeholder-never-real', 'anthropic-version': '2023-06-01'}
    assert kwargs['json']['system'] == ai.SYSTEM_PROMPT
    assert kwargs['json']['max_tokens'] == 1200
    assert json.loads(kwargs['json']['messages'][0]['content'])['pergunta'] == 'O que comprar?'
    assert 'tools' not in kwargs['json']
    assert 'test-placeholder-never-real' not in json.dumps(kwargs['json'])


@pytest.mark.parametrize('status,code', [(401, 'IA_CREDENCIAL_RECUSADA'), (403, 'IA_CREDENCIAL_RECUSADA'),
    (429, 'IA_LIMITE_DO_PROVEDOR'), (500, 'IA_INDISPONIVEL')])
def test_provider_errors_are_sanitized(provider, status, code):
    provider.post.return_value = httpx.Response(status, text='private upstream debug')
    with pytest.raises(HTTPException) as exc:
        ai.answer('O que comprar?', context())
    assert exc.value.detail == {'codigo': code}


def test_timeout(provider):
    provider.post.side_effect = httpx.ReadTimeout('private request detail')
    with pytest.raises(HTTPException) as exc:
        ai.answer('O que comprar?', context())
    assert exc.value.status_code == 504


@pytest.mark.parametrize('body,code', [
    ({'stop_reason': 'max_tokens'}, 'IA_RESPOSTA_INCOMPLETA'),
    ({'stop_reason': 'end_turn', 'content': []}, 'IA_RESPOSTA_VAZIA'),
    (['wrong format'], 'IA_RESPOSTA_INVALIDA')])
def test_invalid_output(provider, body, code):
    provider.post.return_value = httpx.Response(200, json=body)
    with pytest.raises(HTTPException) as exc:
        ai.answer('O que comprar?', context())
    assert exc.value.detail['codigo'] == code


def test_ai_auth_configuration_and_validation(setup, monkeypatch):
    c = setup
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    assert c.get('/ia/status').json()['configurado'] is False
    assert c.post('/ia/perguntar', json={'pergunta': 'O que comprar?'}).status_code == 503
    assert c.post('/ia/perguntar', json={'pergunta': 'oi'}).status_code == 422
    assert c.get('/ia/contexto?dias_historico=999').status_code == 422
    c.headers['Authorization'] = 'Bearer caixa'
    for path in ['/ia/status', '/ia/contexto']:
        assert c.get(path).status_code == 403
    assert c.post('/ia/perguntar', json={'pergunta': 'O que comprar?'}).status_code == 403
    c.headers.pop('Authorization')
    assert c.get('/ia/status').status_code in (401, 403)


def test_context_tenant_isolation_decimal_and_empty_days(setup):
    c = setup
    item = c.post('/insumos', json={'nome': 'Teste', 'unidade': 'g', 'estoque_minimo': '10'}).json()
    with connect() as db:
        u = db.execute("SELECT * FROM usuarios WHERE nome='gerente'").fetchone()
        lot = db.execute('''INSERT INTO lotes(operacao_id,insumo_id,codigo,fornecedor,validade,saldo,custo_unitario)
            VALUES(%s,%s,'T','T',CURRENT_DATE+3,30,0.01) RETURNING id''', (u['operacao_id'], item['id'])).fetchone()['id']
        db.execute('''INSERT INTO movimentacoes(operacao_id,lote_id,usuario_id,tipo,quantidade,custo_unitario,criado_em)
            VALUES(%s,%s,%s,'venda',-100,0.01,CURRENT_DATE-1)''', (u['operacao_id'], lot, u['id']))
        other = db.execute("INSERT INTO operacoes(nome) VALUES('Other') RETURNING id").fetchone()['id']
        db.execute("INSERT INTO insumos(operacao_id,nome,unidade) VALUES(%s,'SECRET_OTHER','g')", (other,))
        db.execute('INSERT INTO usuarios(operacao_id,nome,papel,token_hash) VALUES(%s,%s,%s,%s)',
            (other, 'other', 'ia', hashlib.sha256(b'other').hexdigest()))
    result = c.get('/ia/contexto?dias_historico=2&dias_cobertura=3')
    assert result.status_code == 200, result.text
    assert 'SECRET_OTHER' not in result.text
    ingredient = result.json()['insumos'][0]
    assert Decimal(str(ingredient['media_diaria'])) == 50
    assert Decimal(str(ingredient['necessidade_teorica'])) == 130
    assert ingredient['compra_sugerida'] is None
    assert ingredient['pendencias_compra']
    c.headers['Authorization'] = 'Bearer other'
    other_result = c.get('/ia/contexto').json()
    assert len(other_result['insumos']) == 1
    assert other_result['insumos'][0]['nome'] == 'SECRET_OTHER'
    assert other_result['resumo']['receita'] == 0


def test_question_passes_only_authorized_context(setup, monkeypatch):
    c = setup
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-only')
    captured = {}
    def fake_answer(question, data):
        captured.update(data)
        return {'resposta': 'Sem vendas no periodo.'}
    monkeypatch.setattr(ai, 'answer', fake_answer)
    c.headers['Authorization'] = 'Bearer ia'
    response = c.post('/ia/perguntar', json={'pergunta': 'Como está minha margem?'})
    assert response.status_code == 200
    assert captured['resumo']['receita'] == 0
    assert 'token_hash' not in captured


def test_frontend_served_without_database():
    with TestClient(app) as c:
        assert c.get('/').status_code == 200
        for page in ['index', 'estoque', 'vendas', 'receitas', 'perdas', 'producao']:
            r = c.get(f'/painel/{page}.html')
            assert r.status_code == 200
            assert 'painel.js' in r.text and 'otto.js' in r.text
            assert 'agente.html' not in r.text
        assert c.get('/painel/agente.html').status_code == 404
        r = c.get('/painel/dashboard.html')
        assert r.status_code == 200 and 'dashboard.js' in r.text and 'otto.js' in r.text
        assert c.get('/painel/styles.css').status_code == 200
        assert c.get('/painel/.env').status_code == 404


def test_otto_empty_and_new_ingredient_have_no_invented_forecast(setup):
    c = setup
    result = c.get('/ia/contexto').json()
    assert result['agente'] == 'Otto'
    assert result['estado_dados'] == 'sem_cadastros'
    assert result['sem_vendas_no_periodo'] is True
    assert result['pendencias']
    assert result['produtos'] == [] and result['fichas'] == []
    c.post('/insumos', json={'nome': 'Insumo real', 'unidade': 'g', 'estoque_minimo': '50'})
    result = c.get('/ia/contexto').json()
    assert result['estado_dados'] == 'com_cadastros'
    item = result['insumos'][0]
    assert item['media_diaria'] is None
    assert item['necessidade_teorica'] is None
    assert item['compra_sugerida'] is None
    assert item['lotes_cadastrados'] == 0
    assert c.get('/ia/status').json()['nome'] == 'Otto'


def test_web_search_citations_and_safe_output(provider, monkeypatch):
    monkeypatch.setenv('OTTO_WEB_SEARCH', '1')
    provider.post.return_value = httpx.Response(200, json={'stop_reason':'end_turn', 'content':[
        {'type':'server_tool_use','name':'web_search','input':{'query':'batata Blumenau'}},
        {'type':'web_search_tool_result','content':[{'encrypted_content':'PRIVATE_ENCRYPTED'}]},
        {'type':'text','text':'Preço público, sujeito à confirmação.', 'citations':[
            {'type':'web_search_result_location','url':'https://example.com/preco','title':'Fonte','encrypted_index':'PRIVATE_INDEX'},
            {'type':'web_search_result_location','url':'javascript:alert(1)','title':'Ruim'}]},
        {'type':'text','text':'Outra afirmação.', 'citations':[
            {'type':'web_search_result_location','url':'https://example.com/preco','title':'Fonte'}]}]})
    result=ai.answer('Pesquise preços',context())
    assert provider.post.call_args.kwargs['json']['tools'][0]['max_uses']==3
    assert result['pesquisa_web_utilizada'] is True
    assert result['fontes_web']==[{'id':1,'url':'https://example.com/preco','titulo':'Fonte'}]
    assert result['blocos'][0]['fontes']==[1]
    assert result['blocos'][1]['fontes']==[1]
    assert 'PRIVATE_' not in json.dumps(result)


def test_web_error_in_success_response_is_visible(provider, monkeypatch):
    monkeypatch.setenv('OTTO_WEB_SEARCH','1')
    provider.post.return_value=httpx.Response(200,json={'stop_reason':'end_turn','content':[
        {'type':'web_search_tool_result','content':{'type':'web_search_tool_result_error','error_code':'unavailable'}},
        {'type':'text','text':'Não consegui confirmar o preço.'}]})
    result=ai.answer('Pesquise preço',context())
    assert result['avisos'] and result['fontes_web']==[]
    assert result['pesquisa_web_utilizada'] is True


def test_web_pause_continues_with_unchanged_content(provider, monkeypatch):
    monkeypatch.setenv('OTTO_WEB_SEARCH','1')
    blocks=[{'type':'web_search_tool_result','content':[{'encrypted_content':'encrypted'}]}]
    provider.post.side_effect=[httpx.Response(200,json={'stop_reason':'pause_turn','content':blocks}),
        httpx.Response(200,json={'stop_reason':'end_turn','content':[{'type':'text','text':'Concluído.'}]})]
    assert ai.answer('Pesquise',context())['resposta']=='Concluído.'
    assert provider.post.call_count==2
    assert provider.post.call_args.kwargs['json']['messages'][-1]['content']==blocks


def test_web_pause_is_bounded(provider, monkeypatch):
    monkeypatch.setenv('OTTO_WEB_SEARCH','1')
    provider.post.return_value=httpx.Response(200,json={'stop_reason':'pause_turn','content':[]})
    with pytest.raises(HTTPException) as exc:ai.answer('Pesquise',context())
    assert exc.value.detail['codigo']=='IA_RESPOSTA_INCOMPLETA'
    assert provider.post.call_count==2


def test_web_bad_configuration_is_sanitized(provider, monkeypatch):
    monkeypatch.setenv('OTTO_WEB_SEARCH','1')
    provider.post.return_value=httpx.Response(400,text='private details')
    with pytest.raises(HTTPException) as exc:ai.answer('Pesquise',context())
    assert exc.value.detail['codigo']=='IA_PESQUISA_CONFIGURACAO'


def test_web_enabled_does_not_claim_search_when_not_used(provider, monkeypatch):
    monkeypatch.setenv('OTTO_WEB_SEARCH','1')
    provider.post.return_value=httpx.Response(200,json={'stop_reason':'end_turn','content':[{'type':'text','text':'Saldo atual.'}]})
    result=ai.answer('Qual saldo?',context())
    assert result['pesquisa_web_utilizada'] is False
    assert result['fontes_web']==[]
