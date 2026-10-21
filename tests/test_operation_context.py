from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import httpx

from app import ai
from app.db import connect
from app.operation_context import REPORT_QUESTION
from scripts.seed_okto import OPERATION_ID, seed


def test_report_preference_is_tenant_scoped_and_not_scheduling(setup):
    c = setup
    data = c.get('/ia/contexto').json()['operacao']
    assert data['relatorio_semanal']['pergunta'] == REPORT_QUESTION
    c.headers['Authorization'] = 'Bearer ia'
    assert c.put('/ia/preferencias/relatorio-semanal', json={'deseja_receber': True}).status_code == 403
    c.headers['Authorization'] = 'Bearer gerente'
    for choice in (True, False):
        response = c.put('/ia/preferencias/relatorio-semanal', json={'deseja_receber': choice})
        assert response.status_code == 200
        assert response.json()['envio_automatico_ativo'] is False
        data = c.get('/ia/contexto').json()['operacao']
        assert data['relatorio_semanal']['deseja_receber'] is choice
        assert data['relatorio_semanal']['pergunta'] is None
    with connect() as db:
        other = db.execute("INSERT INTO operacoes(nome) VALUES('Other') RETURNING id").fetchone()['id']
    assert ai.build_context(other)['operacao']['relatorio_semanal']['pergunta'] == REPORT_QUESTION


def test_answer_includes_report_question_only_when_pending(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-only')
    client = MagicMock()
    client.__enter__.return_value = client
    client.post.return_value = httpx.Response(200, json={'stop_reason': 'end_turn',
        'content': [{'type': 'text', 'text': 'Dados simulados.'}]})
    monkeypatch.setattr(ai.httpx, 'Client', MagicMock(return_value=client))
    context = {'periodo': {}, 'gerado_em': '', 'insumos_truncados': False,
               'operacao': {'relatorio_semanal': {'pergunta': REPORT_QUESTION}}}
    assert REPORT_QUESTION in ai.answer('Como estamos?', context)['resposta']
    context['operacao']['relatorio_semanal']['pergunta'] = None
    assert REPORT_QUESTION not in ai.answer('Como estamos?', context)['resposta']


def test_demo_seed_reconciles_sales_stock_and_seasonality(setup):
    # O fixture cria só uma operação vazia para autenticação; removê-la neste schema de teste.
    with connect() as db:
        db.execute('DELETE FROM usuarios')
        db.execute('DELETE FROM operacoes')
    assert seed('test-seed-token')['estado'] == 'criado'
    assert seed('test-seed-token')['estado'] == 'ja_carregado'
    with connect() as db:
        totals = db.execute('''SELECT sum(total) AS receita,
            sum(total) FILTER(WHERE extract(isodow FROM criado_em)>=4) AS fortes,
            count(*) AS vendas FROM vendas''').fetchone()
        assert totals['vendas'] == 1280
        assert totals['receita'] == Decimal('111680')
        assert totals['fortes'] / totals['receita'] == Decimal('.75')
        assert db.execute('SELECT sum(quantidade) AS n FROM venda_itens').fetchone()['n'] == 3200
        assert not db.execute('''SELECT l.id FROM lotes l JOIN movimentacoes m ON m.lote_id=l.id
            GROUP BY l.id HAVING l.saldo<>sum(m.quantidade)''').fetchall()
        assert not db.execute('''SELECT v.id FROM vendas v JOIN pagamentos p ON p.venda_id=v.id
            GROUP BY v.id HAVING v.total<>sum(p.valor)''').fetchall()
        assert not db.execute('''SELECT v.id FROM vendas v JOIN movimentacoes m ON m.venda_id=v.id
            GROUP BY v.id HAVING v.custo<>-sum(m.quantidade*m.custo_unitario)''').fetchall()
        assert not db.execute('''SELECT m.id FROM movimentacoes m JOIN lotes l ON l.id=m.lote_id
            WHERE m.tipo='venda' AND (m.criado_em<l.criado_em OR m.criado_em::date>l.validade)''').fetchall()
        daily = db.execute('SELECT criado_em::date AS dia,sum(total) AS receita FROM vendas GROUP BY 1').fetchall()
        revenues = {r['dia']: r['receita'] for r in daily}
        for day in (9, 10, 11):
            assert revenues[date(2026, 10, day)] > revenues[date(2026, 10, day+7)]
        assert db.execute('SELECT parametros FROM contextos_operacionais WHERE operacao_id=%s',
                          (OPERATION_ID,)).fetchone()['parametros']['publico_total_festa'] == 500000
        names = [r['nome'] for r in db.execute('SELECT nome FROM produtos ORDER BY nome').fetchall()]
        assert names == ['Bolonhesa', 'Linguiça Blumenau', 'Strogonoff de frango', 'Vegetariana']
    assert seed('test-seed-token', recreate=True)['estado'] == 'recriado'
    with connect() as db:
        assert db.execute('SELECT count(*) AS n FROM produtos').fetchone()['n'] == 4
        assert db.execute('SELECT count(*) AS n FROM vendas').fetchone()['n'] == 1280


def test_dashboard_requires_auth_and_scopes_operation(setup):
    c = setup
    c.post('/insumos', json={'nome': 'Ingrediente do gerente', 'unidade': 'g'})
    with connect() as db:
        other = db.execute("INSERT INTO operacoes(nome) VALUES('Outra barraca') RETURNING id").fetchone()['id']
        db.execute("INSERT INTO insumos(operacao_id,nome,unidade) VALUES(%s,'NAO_EXIBIR','g')", (other,))
    response = c.get('/dashboard')
    assert response.status_code == 200
    assert response.json()['estoque'][0]['nome'] == 'Ingrediente do gerente'
    assert 'NAO_EXIBIR' not in response.text
    c.headers['Authorization'] = 'Bearer caixa'
    assert c.get('/dashboard').status_code == 403
    c.headers.clear()
    assert c.get('/dashboard').status_code in (401,403)


def test_demo_requires_loopback_opt_in_and_simulated_data(setup, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from psycopg.types.json import Jsonb
    with connect() as db:
        op = db.execute('SELECT id FROM operacoes').fetchone()['id']
        db.execute('INSERT INTO contextos_operacionais(operacao_id,parametros) VALUES(%s,%s)',
                   (op, Jsonb({'natureza_dados': 'simulados'})))
    monkeypatch.setenv('LOCAL_DEMO_OPERATION_ID', str(op))
    assert setup.get('/demo/dados').status_code == 403
    with TestClient(app, base_url='http://localhost', client=('127.0.0.1',12345)) as local:
        assert local.get('/demo/dados').status_code == 200
        assert local.get('/demo/dados',headers={'Origin':'https://other.example'}).status_code == 403
        assert local.get('/demo/dados',headers={'Host':'other.example'}).status_code == 403
        assert local.get('/demo/dados',headers={'Sec-Fetch-Site':'cross-site'}).status_code == 403
        monkeypatch.delenv('LOCAL_DEMO_OPERATION_ID')
        assert local.get('/demo/dados').status_code == 403
        monkeypatch.setenv('LOCAL_DEMO_OPERATION_ID',str(op))
        with connect() as db:
            db.execute("UPDATE contextos_operacionais SET parametros='{}' WHERE operacao_id=%s",(op,))
        assert local.get('/demo/dados').status_code == 403
