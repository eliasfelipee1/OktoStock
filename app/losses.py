"""Perdas fisicas nao vendidas: registro, baixa e custo historico atomicos."""
import hashlib
import json
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
from fastapi import HTTPException
from app.db import connect


def fail(code, status=409):
    raise HTTPException(status, detail={'codigo': code})


def register(u, body, recipe=False):
    payload = body.model_dump(mode='json')
    fingerprint = hashlib.sha256(json.dumps({'receita': recipe, 'dados': payload}, sort_keys=True).encode()).hexdigest()
    with connect() as db:
        db.execute('SELECT id FROM operacoes WHERE id=%s FOR UPDATE', (u['operacao_id'],))
        if body.idempotency_key:
            old = db.execute('SELECT * FROM perdas WHERE operacao_id=%s AND chave=%s',
                             (u['operacao_id'], body.idempotency_key)).fetchone()
            if old:
                if old['payload_hash'] != fingerprint:
                    fail('CHAVE_REUTILIZADA_COM_OUTRO_CONTEUDO')
                output = result(db, old['id'])
                if not recipe:
                    current = db.execute('SELECT saldo FROM lotes WHERE id=%s AND operacao_id=%s',
                        (body.lote_id, u['operacao_id'])).fetchone()
                    output.update(lote_id=body.lote_id, saldo=current['saldo'])
                return output
        product = None
        if body.produto_id:
            product = db.execute('SELECT * FROM produtos WHERE id=%s AND operacao_id=%s',
                                 (body.produto_id, u['operacao_id'])).fetchone()
            if not product:
                fail('PRODUTO_NAO_ENCONTRADO', 404)
        if body.turno_id:
            if not db.execute('SELECT id FROM turnos WHERE id=%s AND operacao_id=%s',
                              (body.turno_id, u['operacao_id'])).fetchone():
                fail('TURNO_NAO_ENCONTRADO', 404)
        selected = []
        if recipe:
            ingredients = db.execute('SELECT * FROM ingredientes WHERE produto_id=%s ORDER BY insumo_id',
                                     (body.produto_id,)).fetchall()
            if not ingredients:
                fail('RECEITA_VAZIA')
            for ingredient in ingredients:
                need = ingredient['quantidade'] * body.porcoes
                if need != need.quantize(Decimal('0.001')):
                    fail('QUANTIDADE_FORA_DA_PRECISAO', 422)
                lots = db.execute('''SELECT * FROM lotes WHERE operacao_id=%s AND insumo_id=%s
                    AND saldo>0 AND validade>=CURRENT_DATE ORDER BY validade,criado_em,id FOR UPDATE''',
                    (u['operacao_id'], ingredient['insumo_id'])).fetchall()
                for lot in lots:
                    take = min(need, lot['saldo'])
                    selected.append((lot, take))
                    need -= take
                    if need == 0:
                        break
                if need:
                    fail('ESTOQUE_INSUFICIENTE')
        else:
            lot = db.execute('SELECT * FROM lotes WHERE id=%s AND operacao_id=%s FOR UPDATE',
                             (body.lote_id, u['operacao_id'])).fetchone()
            if not lot:
                fail('LOTE_NAO_ENCONTRADO', 404)
            if body.produto_id and not db.execute('SELECT 1 FROM ingredientes WHERE produto_id=%s AND insumo_id=%s',
                                                 (body.produto_id, lot['insumo_id'])).fetchone():
                fail('INSUMO_FORA_DA_RECEITA', 422)
            if lot['saldo'] < body.quantidade:
                fail('ESTOQUE_INSUFICIENTE')
            selected.append((lot, body.quantidade))
        record = db.execute('''INSERT INTO perdas(operacao_id,produto_id,turno_id,usuario_id,chave,payload_hash,
            motivo,porcoes,produto_nome,produto_versao) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
            (u['operacao_id'], body.produto_id, body.turno_id, u['id'], body.idempotency_key or uuid4(), fingerprint,
             body.motivo, body.porcoes if recipe else None,
             product['nome'] if product else None, product['versao'] if product else None)).fetchone()
        for lot, take in selected:
            db.execute('UPDATE lotes SET saldo=saldo-%s WHERE id=%s', (take, lot['id']))
            db.execute('''INSERT INTO movimentacoes(operacao_id,lote_id,usuario_id,tipo,quantidade,
                custo_unitario,motivo,perda_id) VALUES(%s,%s,%s,'perda',%s,%s,%s,%s)''',
                (u['operacao_id'], lot['id'], u['id'], -take, lot['custo_unitario'], body.motivo, record['id']))
        output = result(db, record['id'])
        if not recipe:
            output.update(lote_id=body.lote_id, saldo=selected[0][0]['saldo'] - body.quantidade)
        return output


def result(db, loss_id):
    record = db.execute('SELECT * FROM perdas WHERE id=%s', (loss_id,)).fetchone()
    record.pop('payload_hash')
    record['consumos'] = db.execute('''SELECT m.lote_id,-m.quantidade AS quantidade,m.custo_unitario,
        -m.quantidade*m.custo_unitario AS custo FROM movimentacoes m WHERE perda_id=%s ORDER BY m.id''', (loss_id,)).fetchall()
    record['custo_total'] = sum((r['custo'] for r in record['consumos']), Decimal(0))
    return record


def report(db, operation_id, start=None, end=None, shift_id=None):
    today = db.execute('SELECT CURRENT_DATE AS dia').fetchone()['dia']
    start, end = start or today, end or today
    if start > end or (end-start).days > 365:
        fail('PERIODO_INVALIDO', 422)
    until = end + timedelta(days=1)
    if shift_id and not db.execute('SELECT 1 FROM turnos WHERE id=%s AND operacao_id=%s', (shift_id, operation_id)).fetchone():
        fail('TURNO_NAO_ENCONTRADO', 404)
    rows = db.execute('''SELECT p.id AS perda_id,p.produto_id,p.produto_nome,p.produto_versao,p.porcoes,
        p.turno_id,m.id AS movimento_id,m.criado_em,m.motivo,m.usuario_id,
        l.insumo_id,i.nome AS insumo,i.unidade,m.lote_id,-m.quantidade AS quantidade,
        -m.quantidade*m.custo_unitario AS custo
        FROM movimentacoes m JOIN lotes l ON l.id=m.lote_id JOIN insumos i ON i.id=l.insumo_id
        LEFT JOIN perdas p ON p.id=m.perda_id
        WHERE m.operacao_id=%s AND m.tipo='perda' AND m.criado_em>=%s::date AND m.criado_em<%s::date
        AND (%s::uuid IS NULL OR p.turno_id=%s::uuid) ORDER BY m.criado_em,m.id''',
        (operation_id, start, until, shift_id, shift_id)).fetchall()
    sales = db.execute('''SELECT COALESCE(sum(total),0) AS faturamento_bruto,
        COALESCE(sum(total) FILTER(WHERE status='confirmada'),0) AS receita_confirmada,
        COALESCE(sum(custo),0) AS custo_ingredientes_vendidos FROM vendas
        WHERE operacao_id=%s AND criado_em>=%s::date AND criado_em<%s::date
        AND (%s::uuid IS NULL OR turno_id=%s::uuid)''', (operation_id,start,until,shift_id,shift_id)).fetchone()
    groups, ingredients, reasons = {}, {}, defaultdict(Decimal)
    units = defaultdict(Decimal)
    seen = set()
    for row in rows:
        key = row['produto_id']
        if key not in groups:
            groups[key] = {'produto_id': key, 'nome': row['produto_nome'] or 'Sem receita vinculada',
                'versao': row['produto_versao'], 'custo': Decimal(0), 'porcoes_registradas': Decimal(0), 'quantidades': defaultdict(Decimal)}
        g = groups[key]
        g['custo'] += row['custo']
        g['quantidades'][row['unidade']] += row['quantidade']
        if row['perda_id'] and row['perda_id'] not in seen:
            g['porcoes_registradas'] += row['porcoes'] or 0
            seen.add(row['perda_id'])
        k = row['insumo_id']
        if k not in ingredients:
            ingredients[k] = {'insumo_id': k, 'nome': row['insumo'], 'unidade': row['unidade'], 'quantidade': Decimal(0), 'custo': Decimal(0)}
        ingredients[k]['quantidade'] += row['quantidade']
        ingredients[k]['custo'] += row['custo']
        units[row['unidade']] += row['quantidade']
        reasons[row['motivo']] += row['custo']
    total = sum((r['custo'] for r in rows), Decimal(0))
    def percent(value):
        return (total/value*100).quantize(Decimal('0.01')) if value else None
    return {'periodo': {'inicio': start, 'fim_inclusivo': end}, 'turno_id': shift_id,
        'sem_registros': not rows, 'custo_total_perdas': total,
        'porcoes_perdidas_registradas': sum((g['porcoes_registradas'] for g in groups.values()), Decimal(0)), 'quantidades_por_unidade': dict(units),
        **sales, 'percentual_sobre_faturamento_bruto': percent(sales['faturamento_bruto']),
        'percentual_sobre_receita_confirmada': percent(sales['receita_confirmada']),
        'percentual_sobre_custo_ingredientes_vendidos': percent(sales['custo_ingredientes_vendidos']),
        'por_receita': sorted(groups.values(), key=lambda r: r['custo'], reverse=True),
        'por_insumo': sorted(ingredients.values(), key=lambda r: r['custo'], reverse=True),
        'por_motivo': [{'motivo': k, 'custo': v} for k,v in reasons.items()], 'registros': rows}
