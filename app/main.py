"""API do MVP: nenhuma credencial PostgreSQL deve ir para o frontend."""
import hashlib
import json
from collections import defaultdict
from datetime import date
from typing import Optional
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg.types.json import Jsonb

from app import ai, inventory, losses
from app.db import connect
from app.schemas import Contagem, Insumo, Motivo, Perda, PerdaReceita, Produto, Recebimento, Venda

app = FastAPI(title='OktoStock', version='0.1.0')
bearer = HTTPBearer()


def fail(code, status=409):
    raise HTTPException(status, detail={'codigo': code})


def user(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    digest = hashlib.sha256(credentials.credentials.encode()).hexdigest()
    with connect() as db:
        row = db.execute('SELECT * FROM usuarios WHERE token_hash=%s AND ativo', (digest,)).fetchone()
    if not row:
        fail('CREDENCIAL_INVALIDA', 401)
    return row


def roles(u, *allowed):
    if u['papel'] not in allowed:
        fail('SEM_PERMISSAO', 403)


def lock_operation(db, u):
    # Serializacao por barraca simplifica concorrencia do MVP, inclusive idempotencia.
    db.execute('SELECT id FROM operacoes WHERE id=%s FOR UPDATE', (u['operacao_id'],))


def audit(db, u, action, data):
    db.execute('INSERT INTO auditoria(operacao_id,usuario_id,acao,dados) VALUES(%s,%s,%s,%s)',
               (u['operacao_id'], u['id'], action, Jsonb(data)))


def movement(db, u, lot, kind, quantity, sale=None, reason=None):
    db.execute('''INSERT INTO movimentacoes(operacao_id,lote_id,venda_id,usuario_id,tipo,quantidade,custo_unitario,motivo)
                  VALUES(%s,%s,%s,%s,%s,%s,%s,%s)''',
               (u['operacao_id'], lot['id'], sale, u['id'], kind, quantity, lot['custo_unitario'], reason))


@app.get('/health')
def health():
    with connect() as db:
        db.execute('SELECT 1')
    return {'status': 'ok'}


@app.post('/insumos', status_code=201)
def create_ingredient(body: Insumo, u=Depends(user)):
    roles(u, 'gerente', 'estoquista')
    with connect() as db:
        result = db.execute('''INSERT INTO insumos(operacao_id,nome,unidade,estoque_minimo)
            VALUES(%s,%s,%s,%s) RETURNING *''',
            (u['operacao_id'], body.nome, body.unidade, body.estoque_minimo)).fetchone()
        audit(db, u, 'criar_insumo', {'id': str(result['id'])})
        return result


@app.get('/insumos')
def ingredients(u=Depends(user)):
    with connect() as db:
        return db.execute('SELECT * FROM insumos WHERE operacao_id=%s ORDER BY nome', (u['operacao_id'],)).fetchall()


@app.post('/produtos', status_code=201)
def create_product(body: Produto, u=Depends(user)):
    roles(u, 'gerente')
    ids = [i.insumo_id for i in body.ingredientes]
    if len(ids) != len(set(ids)):
        fail('INGREDIENTE_DUPLICADO', 422)
    with connect() as db:
        for ingredient in body.ingredientes:
            if not db.execute('SELECT id FROM insumos WHERE id=%s AND operacao_id=%s',
                              (ingredient.insumo_id, u['operacao_id'])).fetchone():
                fail('INSUMO_NAO_ENCONTRADO', 404)
        p = db.execute('INSERT INTO produtos(operacao_id,nome,preco,versao) VALUES(%s,%s,%s,%s) RETURNING *',
                       (u['operacao_id'], body.nome, body.preco, body.versao)).fetchone()
        for ingredient in body.ingredientes:
            db.execute('INSERT INTO ingredientes VALUES(%s,%s,%s,%s)',
                       (u['operacao_id'], p['id'], ingredient.insumo_id, ingredient.quantidade))
        audit(db, u, 'criar_produto', {'id': str(p['id'])})
        return p


@app.get('/produtos')
def products(u=Depends(user)):
    with connect() as db:
        return db.execute('SELECT * FROM produtos WHERE operacao_id=%s AND ativo ORDER BY nome', (u['operacao_id'],)).fetchall()


@app.post('/produtos/{product_id}/desativar')
def deactivate(product_id: UUID, u=Depends(user)):
    roles(u, 'gerente')
    with connect() as db:
        lock_operation(db, u)
        row = db.execute('UPDATE produtos SET ativo=false WHERE id=%s AND operacao_id=%s RETURNING *',
                         (product_id, u['operacao_id'])).fetchone()
        if not row:
            fail('PRODUTO_NAO_ENCONTRADO', 404)
        audit(db, u, 'desativar_produto', {'id': str(product_id)})
        return row


@app.post('/estoque/recebimentos', status_code=201)
def receive(body: Recebimento, u=Depends(user)):
    roles(u, 'gerente', 'estoquista')
    with connect() as db:
        lock_operation(db, u)
        if body.validade < db.execute('SELECT CURRENT_DATE AS dia').fetchone()['dia']:
            fail('LOTE_VENCIDO', 422)
        if not db.execute('SELECT id FROM insumos WHERE id=%s AND operacao_id=%s',
                          (body.insumo_id, u['operacao_id'])).fetchone():
            fail('INSUMO_NAO_ENCONTRADO', 404)
        lot = db.execute('''INSERT INTO lotes(operacao_id,insumo_id,codigo,fornecedor,validade,saldo,custo_unitario)
            VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *''',
            (u['operacao_id'], body.insumo_id, body.codigo, body.fornecedor, body.validade, body.quantidade, body.custo_unitario)).fetchone()
        movement(db, u, lot, 'entrada', body.quantidade)
        return lot


@app.get('/estoque/lotes')
def lots(u=Depends(user)):
    roles(u, 'gerente', 'estoquista', 'ia')
    with connect() as db:
        return db.execute('SELECT *, validade>=CURRENT_DATE AS utilizavel FROM lotes WHERE operacao_id=%s ORDER BY validade,id',
                          (u['operacao_id'],)).fetchall()


@app.post('/estoque/perdas')
def loss(body: Perda, u=Depends(user)):
    roles(u, 'gerente', 'estoquista')
    return losses.register(u, body)


@app.post('/estoque/perdas/receita', status_code=201)
def recipe_loss(body: PerdaReceita, u=Depends(user)):
    roles(u, 'gerente', 'estoquista')
    return losses.register(u, body, recipe=True)


@app.post('/estoque/contagens', status_code=201)
def count_lot(body: Contagem, u=Depends(user)):
    roles(u, 'gerente', 'estoquista')
    return inventory.register(u, body)


@app.get('/estoque/contagens')
def counts(lote_id: Optional[UUID] = None, inicio: Optional[date] = None,
           fim: Optional[date] = None, u=Depends(user)):
    roles(u, 'gerente', 'estoquista', 'ia')
    with connect() as db:
        return inventory.history(db, u['operacao_id'], lote_id, inicio, fim)


@app.get('/estoque/contagens/sugestoes')
def count_suggestions(u=Depends(user)):
    roles(u, 'gerente', 'estoquista')
    with connect() as db:
        return inventory.suggestions(db, u['operacao_id'])


@app.get('/relatorios/perdas')
def losses_report(inicio: Optional[date] = None, fim: Optional[date] = None,
                  turno_id: Optional[UUID] = None, u=Depends(user)):
    roles(u, 'gerente', 'estoquista', 'ia')
    with connect() as db:
        db.commit()
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        return losses.report(db, u['operacao_id'], inicio, fim, turno_id)


@app.post('/turnos', status_code=201)
def open_shift(u=Depends(user)):
    roles(u, 'gerente', 'caixa')
    with connect() as db:
        return db.execute('INSERT INTO turnos(operacao_id,usuario_id) VALUES(%s,%s) RETURNING *',
                          (u['operacao_id'], u['id'])).fetchone()


@app.post('/turnos/{shift_id}/fechar')
def close_shift(shift_id: UUID, u=Depends(user)):
    roles(u, 'gerente', 'caixa')
    with connect() as db:
        lock_operation(db, u)
        shift = db.execute('SELECT * FROM turnos WHERE id=%s AND operacao_id=%s FOR UPDATE', (shift_id, u['operacao_id'])).fetchone()
        if not shift:
            fail('TURNO_NAO_ENCONTRADO', 404)
        if u['papel'] != 'gerente' and shift['usuario_id'] != u['id']:
            fail('SEM_PERMISSAO', 403)
        db.execute('UPDATE turnos SET fechado_em=COALESCE(fechado_em,now()) WHERE id=%s', (shift_id,))
        audit(db, u, 'fechar_turno', {'id': str(shift_id)})
        return db.execute('''SELECT count(*) AS vendas, COALESCE(sum(total),0) AS receita,
            COALESCE(sum(custo),0) AS custo_ingredientes FROM vendas WHERE turno_id=%s AND status='confirmada' ''', (shift_id,)).fetchone()


@app.post('/vendas', status_code=201)
def sell(body: Venda, u=Depends(user)):
    roles(u, 'gerente', 'caixa')
    fingerprint = hashlib.sha256(json.dumps(body.model_dump(mode='json'), sort_keys=True).encode()).hexdigest()
    with connect() as db:
        lock_operation(db, u)
        old = db.execute('SELECT * FROM vendas WHERE operacao_id=%s AND chave=%s', (u['operacao_id'], body.idempotency_key)).fetchone()
        if old:
            if old['usuario_id'] != u['id'] and u['papel'] != 'gerente':
                fail('SEM_PERMISSAO', 403)
            if old['payload_hash'] != fingerprint:
                fail('CHAVE_REUTILIZADA_COM_OUTRO_CONTEUDO')
            return old
        shift = db.execute('SELECT * FROM turnos WHERE id=%s AND operacao_id=%s FOR UPDATE', (body.turno_id, u['operacao_id'])).fetchone()
        if not shift or shift['fechado_em']:
            fail('TURNO_FECHADO')
        if shift['usuario_id'] != u['id'] and u['papel'] != 'gerente':
            fail('SEM_PERMISSAO', 403)
        total, cost = Decimal(0), Decimal(0)
        needs = defaultdict(Decimal)
        snapshots = []
        for item in body.itens:
            product = db.execute('SELECT * FROM produtos WHERE id=%s AND operacao_id=%s AND ativo',
                                 (item.produto_id, u['operacao_id'])).fetchone()
            if not product:
                fail('PRODUTO_INDISPONIVEL')
            recipe = db.execute('SELECT insumo_id,quantidade FROM ingredientes WHERE produto_id=%s', (product['id'],)).fetchall()
            if not recipe:
                fail('RECEITA_VAZIA')
            total += product['preco'] * item.quantidade
            for ingredient in recipe:
                needs[ingredient['insumo_id']] += ingredient['quantidade'] * item.quantidade
            snapshots.append((product, item.quantidade, [{'insumo_id': str(i['insumo_id']), 'quantidade': str(i['quantidade'])} for i in recipe]))
        if sum(p.valor for p in body.pagamentos) != total:
            fail('PAGAMENTO_DIVERGENTE')
        sale = db.execute('''INSERT INTO vendas(operacao_id,turno_id,usuario_id,chave,payload_hash,total)
            VALUES(%s,%s,%s,%s,%s,%s) RETURNING *''',
            (u['operacao_id'], body.turno_id, u['id'], body.idempotency_key, fingerprint, total)).fetchone()
        for ingredient_id in sorted(needs, key=str):
            remaining = needs[ingredient_id]
            available = db.execute('''SELECT * FROM lotes WHERE operacao_id=%s AND insumo_id=%s
                AND saldo>0 AND validade>=CURRENT_DATE ORDER BY validade,criado_em,id FOR UPDATE''',
                (u['operacao_id'], ingredient_id)).fetchall()
            for lot in available:
                take = min(remaining, lot['saldo'])
                db.execute('UPDATE lotes SET saldo=saldo-%s WHERE id=%s', (take, lot['id']))
                movement(db, u, lot, 'venda', -take, sale['id'])
                cost += take * lot['custo_unitario']
                remaining -= take
                if remaining == 0:
                    break
            if remaining > 0:
                fail('ESTOQUE_INSUFICIENTE')  # Excecao desfaz a transacao inteira.
        for product, quantity, recipe in snapshots:
            db.execute('''INSERT INTO venda_itens(venda_id,produto_id,nome,versao,quantidade,preco,ficha)
                VALUES(%s,%s,%s,%s,%s,%s,%s)''',
                (sale['id'], product['id'], product['nome'], product['versao'], quantity, product['preco'], Jsonb(recipe)))
        for payment in body.pagamentos:
            db.execute('INSERT INTO pagamentos(venda_id,forma,valor) VALUES(%s,%s,%s)', (sale['id'], payment.forma, payment.valor))
        audit(db, u, 'registrar_venda', {'id': str(sale['id'])})
        return db.execute('UPDATE vendas SET custo=%s WHERE id=%s RETURNING *', (cost, sale['id'])).fetchone()


@app.get('/vendas/{sale_id}')
def get_sale(sale_id: UUID, u=Depends(user)):
    roles(u, 'gerente', 'caixa', 'ia')
    with connect() as db:
        sale = db.execute('SELECT * FROM vendas WHERE id=%s AND operacao_id=%s', (sale_id, u['operacao_id'])).fetchone()
        if not sale:
            fail('VENDA_NAO_ENCONTRADA', 404)
        if u['papel'] == 'caixa' and sale['usuario_id'] != u['id']:
            fail('SEM_PERMISSAO', 403)
        sale['itens'] = db.execute('SELECT * FROM venda_itens WHERE venda_id=%s', (sale_id,)).fetchall()
        sale['consumos'] = db.execute('SELECT * FROM movimentacoes WHERE venda_id=%s', (sale_id,)).fetchall()
        sale['pagamentos'] = db.execute('SELECT * FROM pagamentos WHERE venda_id=%s', (sale_id,)).fetchall()
        return sale


@app.post('/vendas/{sale_id}/estornar')
def refund(sale_id: UUID, body: Motivo, u=Depends(user)):
    roles(u, 'gerente')
    with connect() as db:
        lock_operation(db, u)
        sale = db.execute('SELECT * FROM vendas WHERE id=%s AND operacao_id=%s FOR UPDATE', (sale_id, u['operacao_id'])).fetchone()
        if not sale:
            fail('VENDA_NAO_ENCONTRADA', 404)
        if sale['status'] != 'estornada':
            db.execute("UPDATE vendas SET status='estornada' WHERE id=%s", (sale_id,))
            audit(db, u, 'estornar_venda', {'id': str(sale_id), 'motivo': body.motivo})
        return {'id': sale_id, 'status': 'estornada', 'estoque_reposto': False,
                'observacao': 'Registro interno; devolucao do pagamento deve ser realizada no provedor/caixa.'}


@app.get('/relatorios/estoque')
def stock_report(u=Depends(user)):
    roles(u, 'gerente', 'estoquista', 'ia')
    with connect() as db:
        return db.execute('''SELECT i.id AS insumo_id,i.nome,i.unidade,i.estoque_minimo,
            COALESCE(sum(l.saldo) FILTER(WHERE l.validade>=CURRENT_DATE),0) AS saldo_utilizavel,
            COALESCE(sum(l.saldo) FILTER(WHERE l.validade<CURRENT_DATE),0) AS saldo_vencido,
            min(l.validade) FILTER(WHERE l.saldo>0 AND l.validade>=CURRENT_DATE) AS proxima_validade
            FROM insumos i LEFT JOIN lotes l ON l.insumo_id=i.id
            WHERE i.operacao_id=%s GROUP BY i.id ORDER BY i.nome''', (u['operacao_id'],)).fetchall()


@app.get('/disponibilidade')
def availability(u=Depends(user)):
    with connect() as db:
        return db.execute('''WITH saldos AS (
            SELECT insumo_id,sum(saldo) AS saldo FROM lotes
            WHERE operacao_id=%s AND validade>=CURRENT_DATE GROUP BY insumo_id)
            SELECT p.id AS produto_id,p.nome,min(floor(COALESCE(s.saldo,0)/i.quantidade)) AS porcoes
            FROM produtos p JOIN ingredientes i ON i.produto_id=p.id LEFT JOIN saldos s ON s.insumo_id=i.insumo_id
            WHERE p.operacao_id=%s AND p.ativo GROUP BY p.id ORDER BY p.nome''', (u['operacao_id'], u['operacao_id'])).fetchall()


@app.get('/relatorios/vendas')
def sales_report(u=Depends(user)):
    roles(u, 'gerente', 'ia')
    with connect() as db:
        return db.execute('''SELECT date_trunc('hour',criado_em) AS hora,status,count(*) AS quantidade_vendas,
            sum(total) AS total,sum(custo) AS custo_ingredientes,
            sum(CASE WHEN status='confirmada' THEN total ELSE 0 END)-sum(custo) AS margem_ingredientes
            FROM vendas WHERE operacao_id=%s GROUP BY 1,2 ORDER BY 1''', (u['operacao_id'],)).fetchall()


@app.get('/relatorios/produtos')
def product_report(u=Depends(user)):
    roles(u, 'gerente', 'ia')
    with connect() as db:
        return db.execute('''SELECT v.criado_em::date AS dia,i.produto_id,i.nome,sum(i.quantidade) AS quantidade,
            sum(i.quantidade*i.preco) AS receita FROM venda_itens i JOIN vendas v ON v.id=i.venda_id
            WHERE v.operacao_id=%s AND v.status='confirmada' GROUP BY 1,2,3 ORDER BY 1,3''', (u['operacao_id'],)).fetchall()


@app.get('/relatorios/consumo')
def consumption(u=Depends(user)):
    roles(u, 'gerente', 'ia')
    with connect() as db:
        return db.execute('''SELECT m.criado_em::date AS dia,l.insumo_id,i.nome,m.tipo,m.motivo,
            -sum(m.quantidade) AS quantidade,-sum(m.quantidade*m.custo_unitario) AS custo
            FROM movimentacoes m JOIN lotes l ON l.id=m.lote_id JOIN insumos i ON i.id=l.insumo_id
            WHERE m.operacao_id=%s AND m.tipo IN ('venda','perda') GROUP BY 1,2,3,4,5 ORDER BY 1''', (u['operacao_id'],)).fetchall()


# Frontend estatico e assistente consultivo. Arquivos publicos nunca contem dados reais.
@app.get('/', include_in_schema=False)
def homepage():
    return RedirectResponse('/painel/')


@app.get('/ia/status')
def ai_status(u=Depends(user)):
    roles(u, 'gerente', 'ia')
    return ai.configuration()


@app.get('/ia/contexto')
def ai_context(dias_historico: int = Query(7, ge=1, le=90),
               dias_cobertura: int = Query(3, ge=1, le=30), u=Depends(user)):
    roles(u, 'gerente', 'ia')
    return ai.build_context(u['operacao_id'], dias_historico, dias_cobertura)


@app.post('/ia/perguntar')
def ai_question(body: ai.Question, u=Depends(user)):
    roles(u, 'gerente', 'ia')
    if not ai.configuration()['configurado']:
        fail('IA_NAO_CONFIGURADA', 503)
    context = ai.build_context(u['operacao_id'], body.dias_historico, body.dias_cobertura)
    return ai.answer(body.pergunta, context)


app.mount('/painel', StaticFiles(directory=Path(__file__).resolve().parents[1] / 'frontend', html=True), name='painel')
