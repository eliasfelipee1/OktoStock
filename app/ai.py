"""Assistente consultivo: contexto autorizado, calculos locais e provedor isolado."""
import json
import os
from datetime import timedelta
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

import httpx
from fastapi import HTTPException
from pydantic import Field

from app.db import connect
from app.losses import report as loss_report
from app.schemas import Model


class Question(Model):
    pergunta: str = Field(min_length=3, max_length=2000)
    dias_historico: int = Field(default=7, ge=1, le=90)
    dias_cobertura: int = Field(default=3, ge=1, le=30)


SYSTEM_PROMPT = (Path(__file__).parent / 'prompts' / 'otto.txt').read_text(encoding='utf-8')


def error(code, status):
    raise HTTPException(status_code=status, detail={'codigo': code})


def configuration():
    return {'nome': 'Otto', 'configurado': bool(os.getenv('OPENAI_API_KEY', '').strip()),
            'provedor': 'openai', 'modelo': os.getenv('AI_MODEL', 'gpt-4.1-mini'),
            'modo': 'somente_leitura'}


def build_context(operation_id, history_days=7, horizon=3):
    """Uma fotografia consistente, sem usuarios, pagamentos individuais ou tokens."""
    with connect() as db:
        db.commit()  # connect configura TimeZone; inicia agora uma transacao somente leitura.
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        clock = db.execute('SELECT CURRENT_DATE AS dia, now() AS instante').fetchone()
        today = clock['dia']
        start = today - timedelta(days=history_days)
        summary = db.execute('''SELECT count(*) FILTER(WHERE status='confirmada') AS vendas_confirmadas,
            count(*) FILTER(WHERE status='estornada') AS vendas_estornadas,
            COALESCE(sum(total) FILTER(WHERE status='confirmada'),0) AS receita,
            COALESCE(sum(custo),0) AS custo_ingredientes_consumidos
            FROM vendas WHERE operacao_id=%s AND criado_em>=%s::date AND criado_em<%s::date''',
            (operation_id, start, today)).fetchone()
        losses = db.execute('''SELECT COALESCE(-sum(quantidade*custo_unitario),0) AS custo
            FROM movimentacoes WHERE operacao_id=%s AND tipo='perda'
            AND criado_em>=%s::date AND criado_em<%s::date''', (operation_id, start, today)).fetchone()['custo']
        rows = db.execute('''WITH saldos AS (
            SELECT insumo_id, count(*) AS lotes_cadastrados, sum(saldo) FILTER(WHERE validade>=CURRENT_DATE) AS utilizavel,
            sum(saldo) FILTER(WHERE validade<CURRENT_DATE) AS vencido,
            min(validade) FILTER(WHERE saldo>0 AND validade>=CURRENT_DATE) AS proxima_validade
            FROM lotes WHERE operacao_id=%s GROUP BY insumo_id), consumo AS (
            SELECT l.insumo_id,count(*) AS registros,-sum(m.quantidade) AS quantidade FROM movimentacoes m
            JOIN lotes l ON l.id=m.lote_id WHERE m.operacao_id=%s AND m.tipo='venda'
            AND m.criado_em>=%s::date AND m.criado_em<%s::date GROUP BY l.insumo_id)
            SELECT i.id,i.nome,i.unidade,i.estoque_minimo,COALESCE(s.utilizavel,0) AS saldo_utilizavel,
            COALESCE(s.vencido,0) AS saldo_vencido,s.proxima_validade,
            COALESCE(s.lotes_cadastrados,0) AS lotes_cadastrados, COALESCE(c.registros,0) AS registros_consumo,
            COALESCE(c.quantidade,0) AS consumo_periodo
            FROM insumos i LEFT JOIN saldos s ON s.insumo_id=i.id LEFT JOIN consumo c ON c.insumo_id=i.id
            WHERE i.operacao_id=%s ORDER BY i.nome,i.id LIMIT 101''',
            (operation_id, operation_id, start, today, operation_id)).fetchall()
        products = db.execute('''SELECT id,nome,preco,versao,ativo FROM produtos
            WHERE operacao_id=%s ORDER BY nome,id LIMIT 101''', (operation_id,)).fetchall()
        recipes = []
        if products:
            recipes = db.execute('''SELECT r.produto_id,r.insumo_id,i.nome,i.unidade,r.quantidade
                FROM ingredientes r JOIN insumos i ON i.id=r.insumo_id
                WHERE r.operacao_id=%s AND r.produto_id=ANY(%s) ORDER BY r.produto_id,i.nome''',
                (operation_id, [p['id'] for p in products[:100]])).fetchall()
        counts = db.execute('''SELECT
            (SELECT count(*) FROM insumos WHERE operacao_id=%s) AS insumos,
            (SELECT count(*) FROM produtos WHERE operacao_id=%s) AS produtos,
            (SELECT count(*) FROM lotes WHERE operacao_id=%s) AS lotes,
            (SELECT count(*) FROM vendas WHERE operacao_id=%s) AS vendas''', (operation_id,) * 4).fetchone()
        loss_data = loss_report(db, operation_id, start, today - timedelta(days=1))
        loss_data.pop('registros')  # Nao enviar nomes/IDs de responsaveis nem movimentos individuais.
    truncated = len(rows) > 100
    ingredients = []
    for row in rows[:100]:
        average = row['consumo_periodo'] / history_days if row['registros_consumo'] else None
        purchase = max(Decimal(0), average * horizon + row['estoque_minimo'] - row['saldo_utilizavel']) if average is not None else None
        ingredients.append({**row, 'media_diaria': average.quantize(Decimal('0.001')) if average is not None else None,
            'necessidade_teorica': purchase.quantize(Decimal('0.001'), rounding=ROUND_CEILING) if purchase is not None else None,
            'compra_sugerida': None,
            'pendencias_compra': ['Demanda validada', 'Perda media', 'Capacidade de armazenamento',
                'Minimo de compra do fornecedor', 'Validade durante a cobertura'],
            'abaixo_minimo': row['saldo_utilizavel'] < row['estoque_minimo']})
    summary['margem_ingredientes'] = summary['receita'] - summary['custo_ingredientes_consumidos']
    summary['custo_perdas_independentes'] = losses
    return {'agente': 'Otto', 'cadastros': counts,
            'estado_dados': 'sem_cadastros' if not any(counts.values()) else 'com_cadastros',
            'sem_vendas_no_periodo': summary['vendas_confirmadas'] + summary['vendas_estornadas'] == 0,
            'produtos': products[:100], 'fichas': recipes, 'produtos_truncados': len(products) > 100,
            'pendencias': [name for key, name in [('insumos', 'Cadastrar insumos'),
                ('produtos', 'Cadastrar produtos e fichas tecnicas'), ('lotes', 'Registrar recebimentos, custos e validades'),
                ('vendas', 'Registrar vendas para construir historico')] if counts[key] == 0],
            'campos_ainda_nao_suportados': ['Custos adicionais e margem alvo', 
                'Capacidade de armazenamento e minimo de compra', 'Alergenicos e fatores de correcao estruturados'],
            'gerado_em': clock['instante'], 'periodo': {'inicio': start, 'fim_exclusivo': today,
            'dias_completos': history_days, 'dias_cobertura': horizon},
            'resumo': summary, 'perdas': loss_data, 'insumos': ingredients, 'insumos_truncados': truncated,
            'limite_insumos': 100,
            'metodo': 'Media de consumo por dias corridos completos, incluindo zeros. Estoque atual.',
            'limitacoes': ['Margem sobre ingredientes nao e lucro liquido.',
                'Necessidade teorica nao autoriza compra; faltam restricoes de reposicao.',
                'Historico ausente nao distingue falta de dados de demanda zero.']}


def answer(question, context):
    key = os.getenv('OPENAI_API_KEY', '').strip()
    if not key:
        error('IA_NAO_CONFIGURADA', 503)
    payload = {'model': configuration()['modelo'], 'instructions': SYSTEM_PROMPT,
               'input': json.dumps({'pergunta': question, 'contexto': context}, default=str, ensure_ascii=False),
               'max_output_tokens': 1200, 'store': False}
    if len(payload['input']) > 80000:
        error('CONTEXTO_IA_MUITO_GRANDE', 422)
    try:
        # URL fixa: a chave nunca e enviada a um host indicado pelo cliente.
        with httpx.Client(timeout=httpx.Timeout(30.0, connect=5.0), follow_redirects=False) as client:
            response = client.post('https://api.openai.com/v1/responses',
                headers={'Authorization': f'Bearer {key}'}, json=payload)
    except httpx.TimeoutException:
        error('IA_TEMPO_ESGOTADO', 504)
    except httpx.RequestError:
        error('IA_INDISPONIVEL', 502)
    if response.status_code in (401, 403):
        error('IA_CREDENCIAL_RECUSADA', 503)
    if response.status_code == 429:
        error('IA_LIMITE_DO_PROVEDOR', 503)
    if not response.is_success:
        error('IA_INDISPONIVEL', 502)
    try:
        data = response.json()
        if data.get('status') != 'completed':
            error('IA_RESPOSTA_INCOMPLETA', 502)
        text = '\n'.join(part['text'] for item in data.get('output', [])
            if item.get('type') == 'message' for part in item.get('content', [])
            if part.get('type') == 'output_text' and isinstance(part.get('text'), str)).strip()
    except (ValueError, TypeError, KeyError, AttributeError):
        error('IA_RESPOSTA_INVALIDA', 502)
    if not text:
        error('IA_RESPOSTA_VAZIA', 502)
    return {'agente': 'Otto', 'resposta': text, 'modelo': configuration()['modelo'], 'modo': 'somente_leitura',
            'periodo': context['periodo'], 'gerado_em': context['gerado_em'],
            'fontes': ['vendas agregadas', 'lotes por insumo', 'movimentacoes agregadas'],
            'insumos_truncados': context['insumos_truncados']}
