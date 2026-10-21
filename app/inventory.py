"""Contagem ciclica: compara o saldo fisico com o do sistema e corrige a diferenca por movimento de ajuste."""
import hashlib
import json
from datetime import timedelta
from fastapi import HTTPException
from app.db import connect


def fail(code, status=409):
    raise HTTPException(status, detail={'codigo': code})


def register(u, body):
    fingerprint = hashlib.sha256(json.dumps(body.model_dump(mode='json'), sort_keys=True).encode()).hexdigest()
    with connect() as db:
        db.execute('SELECT id FROM operacoes WHERE id=%s FOR UPDATE', (u['operacao_id'],))
        old = db.execute('SELECT * FROM contagens WHERE operacao_id=%s AND chave=%s',
                         (u['operacao_id'], body.idempotency_key)).fetchone()
        if old:
            if old['payload_hash'] != fingerprint:
                fail('CHAVE_REUTILIZADA_COM_OUTRO_CONTEUDO')
            return result(db, old['id'])
        lot = db.execute('SELECT * FROM lotes WHERE id=%s AND operacao_id=%s FOR UPDATE',
                         (body.lote_id, u['operacao_id'])).fetchone()
        if not lot:
            fail('LOTE_NAO_ENCONTRADO', 404)
        difference = body.saldo_contado - lot['saldo']
        record = db.execute('''INSERT INTO contagens(operacao_id,lote_id,usuario_id,chave,payload_hash,saldo_sistema,
            saldo_contado,diferenca,custo_unitario,motivo) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
            (u['operacao_id'], lot['id'], u['id'], body.idempotency_key, fingerprint, lot['saldo'],
             body.saldo_contado, difference, lot['custo_unitario'], body.motivo)).fetchone()
        if difference:
            db.execute('UPDATE lotes SET saldo=%s WHERE id=%s', (body.saldo_contado, lot['id']))
            db.execute('''INSERT INTO movimentacoes(operacao_id,lote_id,usuario_id,tipo,quantidade,
                custo_unitario,motivo,contagem_id) VALUES(%s,%s,%s,'ajuste',%s,%s,%s,%s)''',
                (u['operacao_id'], lot['id'], u['id'], difference, lot['custo_unitario'], body.motivo, record['id']))
        return result(db, record['id'])


def result(db, count_id):
    record = db.execute('SELECT * FROM contagens WHERE id=%s', (count_id,)).fetchone()
    record.pop('payload_hash')
    record['custo_diferenca'] = record['diferenca'] * record['custo_unitario']
    return record


def history(db, operation_id, lot_id=None, start=None, end=None):
    if start and end and (start > end or (end-start).days > 365):
        fail('PERIODO_INVALIDO', 422)
    until = end + timedelta(days=1) if end else None
    rows = db.execute('''SELECT c.id,c.lote_id,l.codigo,l.insumo_id,i.nome AS insumo,i.unidade,c.usuario_id,
        c.saldo_sistema,c.saldo_contado,c.diferenca,c.custo_unitario,c.diferenca*c.custo_unitario AS custo_diferenca,
        c.motivo,c.criado_em FROM contagens c JOIN lotes l ON l.id=c.lote_id JOIN insumos i ON i.id=l.insumo_id
        WHERE c.operacao_id=%s AND (%s::uuid IS NULL OR c.lote_id=%s::uuid)
        AND (%s::date IS NULL OR c.criado_em>=%s::date) AND (%s::date IS NULL OR c.criado_em<%s::date)
        ORDER BY c.criado_em DESC,c.id''', (operation_id, lot_id, lot_id, start, start, until, until)).fetchall()
    return {'custo_total_diferencas': sum((r['custo_diferenca'] for r in rows), 0), 'contagens': rows}


def suggestions(db, operation_id):
    # Contagem ciclica: lotes com saldo, os nunca contados ou contados ha mais tempo primeiro.
    return db.execute('''SELECT l.id AS lote_id,l.codigo,l.insumo_id,i.nome AS insumo,i.unidade,l.saldo,l.validade,
        max(c.criado_em) AS ultima_contagem FROM lotes l JOIN insumos i ON i.id=l.insumo_id
        LEFT JOIN contagens c ON c.lote_id=l.id WHERE l.operacao_id=%s AND l.saldo>0
        GROUP BY l.id,i.id ORDER BY max(c.criado_em) NULLS FIRST,l.validade,l.id''', (operation_id,)).fetchall()
