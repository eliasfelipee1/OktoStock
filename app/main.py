"""API do MVP: nenhuma credencial PostgreSQL deve ir para o frontend."""
import hashlib
import os
import threading
import time

import anyio
import psycopg
import json
from collections import defaultdict
from datetime import date
from typing import Optional
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg.types.json import Jsonb

from app import ai, inventory, losses, planning, purchasing, ready_stock, price_proposals
from app.monitor import lifespan
from app.recipes import Recipe
from app.db import connect
from app.schemas import Contagem, Insumo, Motivo, Perda, PerdaReceita, Produto, Recebimento, Venda

app = FastAPI(title='OktoStock', version='0.2.0', lifespan=lifespan)
bearer = HTTPBearer()


@app.middleware('http')
async def refresh_panel_assets(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(('/painel/', '/demo/', '/reposicao', '/fornecedores')) or request.url.path == '/dashboard':
        response.headers['Cache-Control'] = 'no-store'
    return response



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
            if product['preco'] is None:
                fail('PRECO_DE_VENDA_PENDENTE')
            total += product['preco'] * item.quantidade
            if not product['ficha_detalhes'].get('controle_prontos'):
                for ingredient in recipe:
                    needs[ingredient['insumo_id']] += ingredient['quantidade'] * item.quantidade
            snapshots.append((product, item.quantidade, [{'insumo_id': str(i['insumo_id']), 'quantidade': str(i['quantidade'])} for i in recipe]))
        if sum(p.valor for p in body.pagamentos) != total:
            fail('PAGAMENTO_DIVERGENTE')
        sale = db.execute('''INSERT INTO vendas(operacao_id,turno_id,usuario_id,chave,payload_hash,total)
            VALUES(%s,%s,%s,%s,%s,%s) RETURNING *''',
            (u['operacao_id'], body.turno_id, u['id'], body.idempotency_key, fingerprint, total)).fetchone()
        for product, quantity, recipe in snapshots:
            if product['ficha_detalhes'].get('controle_prontos'):
                cost += ready_stock.consume_sale(db, u, product['id'], quantity, sale['id'])
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
        sale['consumos_prontos'] = db.execute('SELECT * FROM movimentos_prontos WHERE venda_id=%s AND operacao_id=%s', (sale_id,u['operacao_id'])).fetchall()
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
            SELECT p.id AS produto_id,p.nome,CASE WHEN p.ficha_detalhes->>'controle_prontos'='true'
            THEN (SELECT coalesce(sum(lp.saldo),0) FROM lotes_prontos lp WHERE lp.operacao_id=p.operacao_id AND lp.produto_id=p.id AND lp.validade>now())
            ELSE min(floor(COALESCE(s.saldo,0)/i.quantidade)) END AS porcoes
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


class PreferenciaRelatorio(ai.Model):
    deseja_receber: bool


@app.put('/ia/preferencias/relatorio-semanal')
def report_preference(body: PreferenciaRelatorio, u=Depends(user)):
    roles(u, 'gerente')
    with connect() as db:
        db.execute("""INSERT INTO contextos_operacionais(operacao_id,deseja_relatorio_domingo)
            VALUES(%s,%s) ON CONFLICT(operacao_id) DO UPDATE
            SET deseja_relatorio_domingo=EXCLUDED.deseja_relatorio_domingo, atualizado_em=now()""",
            (u['operacao_id'], body.deseja_receber))
        audit(db, u, 'PREFERENCIA_RELATORIO', {'deseja_receber': body.deseja_receber})
    return {'deseja_receber': body.deseja_receber, 'envio_automatico_ativo': False,
            'mensagem': 'Preferência salva. Horário, canal e serviço de envio ainda precisam ser configurados.'}


@app.get('/ia/contexto')
def ai_context(dias_historico: int = Query(14, ge=1, le=90),
               dias_cobertura: int = Query(3, ge=1, le=30), u=Depends(user)):
    roles(u, 'gerente', 'ia')
    return ai.build_context(u['operacao_id'], dias_historico, dias_cobertura)


@app.post('/ia/perguntar')
def ai_question(body: ai.Question, u=Depends(user)):
    roles(u, 'gerente', 'ia')
    if not ai.configuration()['configurado']:
        fail('IA_NAO_CONFIGURADA', 503)
    context = ai.build_context(u['operacao_id'], body.dias_historico, body.dias_cobertura)
    return price_proposals.attach(ai.answer(body.pergunta, context), u['operacao_id'], context)


def panel_filters(inicio: Optional[date] = None, fim: Optional[date] = None,
                  produto_id: Optional[UUID] = None, forma: Optional[str] = Query(None, max_length=30),
                  dia_semana: Optional[int] = Query(None, ge=1, le=7)):
    """Filtros do painel: período inclusivo, sabor, forma de pagamento e dia da semana ISO."""
    return {'start': inicio, 'end': fim, 'product': produto_id, 'payment': forma, 'weekday': dia_semana}


@app.get('/dashboard')
def dashboard_data(pagina: int = Query(1, ge=1), filters=Depends(panel_filters), u=Depends(user)):
    roles(u, 'gerente', 'ia')
    from app.dashboard import load
    return load(u['operacao_id'], pagina, **filters)


def remote_demo_enabled():
    return os.getenv('DEMO_ACESSO_REMOTO', '').strip().lower() in ('1', 'true', 'sim')


def local_demo_operation(request: Request):
    """Operação simulada configurada no servidor, sem token no navegador.

    Por padrão só atende o próprio computador; DEMO_ACESSO_REMOTO=1 libera outros
    computadores, mas continua restrito à operação marcada como simulada."""
    local_hosts = {'127.0.0.1', 'localhost', '::1'}
    origin = request.headers.get('origin')
    configured = os.getenv('LOCAL_DEMO_OPERATION_ID')
    local = (request.client and request.client.host in local_hosts
             and request.url.hostname in local_hosts)
    if (not configured or not request.client or not (local or remote_demo_enabled())
            or (origin and origin != str(request.base_url).rstrip('/'))
            or request.headers.get('sec-fetch-site') == 'cross-site'):
        fail('DEMONSTRACAO_LOCAL_INDISPONIVEL', 403)
    try:
        operation_id = UUID(configured)
    except ValueError:
        fail('DEMONSTRACAO_LOCAL_INDISPONIVEL', 403)
    with connect() as db:
        config = db.execute("SELECT parametros FROM contextos_operacionais WHERE operacao_id=%s", (operation_id,)).fetchone()
        if not config or not (config['parametros'].get('natureza_dados') == 'simulados'
                              or (local and config['parametros'].get('natureza_dados') == 'cadastro_real_local')):
            fail('DEMONSTRACAO_LOCAL_INDISPONIVEL', 403)
    return operation_id


@app.get('/demo/dados', include_in_schema=False)
def local_demo_data(response: Response, pagina: int = Query(1, ge=1), filters=Depends(panel_filters),
                    operation_id: UUID = Depends(local_demo_operation)):
    # Apenas leitura da operação explicitamente simulada, na instalação local.
    from app.dashboard import load
    response.headers['Cache-Control'] = 'no-store'
    return load(operation_id, pagina, **filters)


_question_times = defaultdict(list)
_question_lock = threading.Lock()


def limit_questions(request: Request):
    """Cada pergunta consome a chave Anthropic do servidor: limite por computador."""
    limit = int(os.getenv('DEMO_PERGUNTAS_POR_MINUTO', '6'))
    now = time.monotonic()
    with _question_lock:
        recent = [t for t in _question_times[request.client.host] if now - t < 60]
        if len(recent) >= limit:
            _question_times[request.client.host] = recent
            fail('IA_LIMITE_DE_PERGUNTAS', 429)
        _question_times[request.client.host] = recent + [now]


_listeners = {'ativos': 0}
MAX_LISTENERS = 20


def _listen():
    conn = psycopg.connect(os.environ['DATABASE_URL'], autocommit=True)
    conn.execute('LISTEN okto_mudancas')
    return conn


def _wait_change(conn, operation_id, timeout):
    """Bloqueia até um aviso da operação ou o tempo esgotar; agrupa rajadas de avisos."""
    target = str(operation_id)
    changed = any(n.payload == target for n in conn.notifies(timeout=timeout, stop_after=1))
    if changed:  # Uma venda gera vários avisos; espera a rajada terminar antes de avisar a página.
        list(conn.notifies(timeout=0.5))
    return changed


@app.get('/demo/eventos', include_in_schema=False)
async def local_demo_events(operation_id: UUID = Depends(local_demo_operation)):
    """Server-Sent Events: avisa a dashboard quando a operação muda no banco."""
    async def stream():
        if _listeners['ativos'] >= MAX_LISTENERS:  # Cada ouvinte usa uma conexão do banco.
            yield 'event: lotado\ndata: {}\n\n'
            return
        _listeners['ativos'] += 1
        conn = None
        try:
            conn = await anyio.to_thread.run_sync(_listen)
            yield 'retry: 3000\nevent: pronto\ndata: {}\n\n'
            while True:
                changed = await anyio.to_thread.run_sync(_wait_change, conn, operation_id, 15)
                yield 'event: mudanca\ndata: {}\n\n' if changed else ': ping\n\n'
        finally:
            _listeners['ativos'] -= 1
            if conn is not None:
                conn.close()

    return StreamingResponse(stream(), media_type='text/event-stream',
                             headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})


@app.post('/demo/ia/perguntar', include_in_schema=False)
def local_demo_question(body: ai.Question, operation_id: UUID = Depends(local_demo_operation),
                        _=Depends(limit_questions)):
    # Otto somente leitura sobre a operação simulada; a chave Anthropic fica no servidor.
    if not ai.configuration()['configurado']:
        fail('IA_NAO_CONFIGURADA', 503)
    context = ai.build_context(operation_id, body.dias_historico, body.dias_cobertura)
    return price_proposals.attach(ai.answer(body.pergunta, context), operation_id, context)


app.mount('/painel', StaticFiles(directory=Path(__file__).resolve().parents[1] / 'frontend', html=True), name='painel')


@app.post('/planejamento/pre-assadas')
def plan_pre_baked(body: planning.PlanoPreAssadas, u=Depends(user)):
    roles(u, 'gerente', 'ia')
    return planning.calculate(body)


# Reposição e fornecedores: leitura por operação, escrita auditada pelo gerente.
def purchasing_snapshot(operation_id):
    with connect() as db:
        db.commit()
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        return purchasing.snapshot(db, operation_id)


@app.get('/reposicao')
def replenishment(u=Depends(user)):
    roles(u, 'gerente', 'estoquista', 'ia')
    return purchasing_snapshot(u['operacao_id'])


@app.get('/demo/reposicao', include_in_schema=False)
def demo_replenishment(operation_id: UUID = Depends(local_demo_operation)):
    return purchasing_snapshot(operation_id)


def demo_manager(request: Request, operation_id: UUID = Depends(local_demo_operation)):
    # Escrita de demonstração exclusivamente local e JSON; nunca usa DEMO_ACESSO_REMOTO.
    if (request.client.host not in {'127.0.0.1', '::1'}
        or request.url.hostname not in {'127.0.0.1', 'localhost', '::1'}
        or request.headers.get('content-type', '').split(';')[0] != 'application/json'):
        fail('ESCRITA_LOCAL_INDISPONIVEL', 403)
    with connect() as db:
        row = db.execute("SELECT * FROM usuarios WHERE operacao_id=%s AND papel='gerente' AND ativo ORDER BY id LIMIT 1", (operation_id,)).fetchone()
    if not row: fail('SEM_GERENTE_LOCAL', 403)
    return row


def supplier_write(body, u, supplier_id=None):
    roles(u, 'gerente')
    try:
        with connect() as db:
            lock_operation(db, u)
            row = purchasing.save_supplier(db, u['operacao_id'], body, supplier_id)
            audit(db, u, 'salvar_fornecedor', {'id': str(row['id'])})
            return row
    except psycopg.errors.UniqueViolation:
        fail('FORNECEDOR_DUPLICADO', 409)


@app.post('/fornecedores', status_code=201)
def create_supplier(body: purchasing.Supplier, u=Depends(user)):
    return supplier_write(body, u)


@app.put('/fornecedores/{supplier_id}')
def update_supplier(supplier_id: UUID, body: purchasing.Supplier, u=Depends(user)):
    return supplier_write(body, u, supplier_id)


@app.post('/demo/fornecedores', status_code=201, include_in_schema=False)
def demo_create_supplier(body: purchasing.Supplier, u=Depends(demo_manager)):
    return supplier_write(body, u)


@app.put('/demo/fornecedores/{supplier_id}', include_in_schema=False)
def demo_update_supplier(supplier_id: UUID, body: purchasing.Supplier, u=Depends(demo_manager)):
    return supplier_write(body, u, supplier_id)


def quote_write(body, u):
    roles(u, 'gerente')
    with connect() as db:
        row = purchasing.save_quote(db, u['operacao_id'], body)
        audit(db, u, 'salvar_cotacao', {'id': str(row['id'])})
        return row


@app.post('/cotacoes', status_code=201)
def create_quote(body: purchasing.Quote, u=Depends(user)):
    return quote_write(body, u)


@app.post('/demo/cotacoes', status_code=201, include_in_schema=False)
def demo_create_quote(body: purchasing.Quote, u=Depends(demo_manager)):
    return quote_write(body, u)


@app.post('/demo/insumos', status_code=201, include_in_schema=False)
def demo_create_ingredient(body: Insumo, u=Depends(demo_manager)):
    return create_ingredient(body, u)


def recipe_write(product_id, body, u):
    roles(u, 'gerente')
    with connect() as db:
        lock_operation(db, u)
        product = db.execute('SELECT * FROM produtos WHERE id=%s AND operacao_id=%s FOR UPDATE',
                             (product_id,u['operacao_id'])).fetchone()
        if not product: fail('PRODUTO_NAO_ENCONTRADO',404)
        if product['ativo'] or db.execute('SELECT 1 FROM venda_itens WHERE produto_id=%s LIMIT 1', (product_id,)).fetchone():
            fail('FICHA_IMUTAVEL_CRIAR_NOVA_VERSAO',409)
        for item in body.ingredientes:
            if not db.execute('SELECT 1 FROM insumos WHERE id=%s AND operacao_id=%s', (item.insumo_id,u['operacao_id'])).fetchone():
                fail('INSUMO_NAO_ENCONTRADO',404)
        db.execute('DELETE FROM ingredientes WHERE produto_id=%s AND operacao_id=%s', (product_id,u['operacao_id']))
        for item in body.ingredientes:
            db.execute('INSERT INTO ingredientes VALUES(%s,%s,%s,%s)', (u['operacao_id'],product_id,item.insumo_id,item.quantidade))
        details = {**product['ficha_detalhes'], 'status': 'validada' if body.validada else 'rascunho',
                   'rendimento_porcoes': 1, 'preparo': body.preparo, 'observacoes': body.observacoes,
                   'origem': 'Informada pelo responsável no cadastro', 'simulada': False}
        row = db.execute('UPDATE produtos SET preco=%s,ativo=%s,ficha_detalhes=%s WHERE id=%s RETURNING *',
                         (body.preco,body.validada,Jsonb(details),product_id)).fetchone()
        audit(db,u,'salvar_ficha',{'produto_id':str(product_id),'validada':body.validada})
        return row


@app.put('/fichas/{product_id}')
def update_recipe(product_id: UUID, body: Recipe, u=Depends(user)):
    return recipe_write(product_id,body,u)


@app.put('/demo/fichas/{product_id}', include_in_schema=False)
def demo_update_recipe(product_id: UUID, body: Recipe, u=Depends(demo_manager)):
    return recipe_write(product_id,body,u)


@app.post('/demo/estoque/recebimentos', status_code=201, include_in_schema=False)
def demo_receive(body: Recebimento, u=Depends(demo_manager)):
    return receive(body, u)


@app.get('/prontos')
def get_ready(u=Depends(user)):
    with connect() as db:
        return ready_stock.snapshot(db,u['operacao_id'])


@app.get('/demo/prontos', include_in_schema=False)
def demo_get_ready(operation_id: UUID = Depends(local_demo_operation)):
    with connect() as db:
        return ready_stock.snapshot(db,operation_id)


def ready_entry(body,u):
    roles(u,'gerente','estoquista')
    with connect() as db:
        row=ready_stock.register(db,u,body)
        audit(db,u,'registrar_porcoes_prontas',{'lote_id':str(row['id']),'origem':body.origem})
        return row


@app.post('/prontos/entradas',status_code=201)
def ready_register(body:ready_stock.Entry,u=Depends(user)):
    return ready_entry(body,u)


@app.post('/demo/prontos/entradas',status_code=201,include_in_schema=False)
def demo_ready_register(body:ready_stock.Entry,u=Depends(demo_manager)):
    return ready_entry(body,u)


def ready_waste(body,u):
    roles(u,'gerente','estoquista')
    with connect() as db:
        row=ready_stock.discard(db,u,body)
        audit(db,u,'descartar_porcoes_prontas',{'movimento_id':str(row['id'])})
        return row


@app.post('/prontos/perdas',status_code=201)
def ready_discard(body:ready_stock.Waste,u=Depends(user)):
    return ready_waste(body,u)


@app.post('/demo/prontos/perdas',status_code=201,include_in_schema=False)
def demo_ready_discard(body:ready_stock.Waste,u=Depends(demo_manager)):
    return ready_waste(body,u)


def apply_price_proposal(proposal_id, u, cancel=False):
    roles(u, 'gerente')
    with connect() as db:
        return price_proposals.apply(db, u, proposal_id, cancel=cancel)


@app.post('/ia/propostas-precos/{proposal_id}/confirmar')
def confirm_price_proposal(proposal_id: UUID, body: price_proposals.Confirmation, u=Depends(user)):
    return apply_price_proposal(proposal_id,u)


@app.post('/demo/ia/propostas-precos/{proposal_id}/confirmar', include_in_schema=False)
def demo_confirm_price_proposal(proposal_id: UUID, body: price_proposals.Confirmation, u=Depends(demo_manager)):
    return apply_price_proposal(proposal_id,u)


@app.post('/ia/propostas-precos/{proposal_id}/cancelar')
def cancel_price_proposal(proposal_id: UUID, u=Depends(user)):
    return apply_price_proposal(proposal_id,u,cancel=True)


@app.post('/demo/ia/propostas-precos/{proposal_id}/cancelar', include_in_schema=False)
def demo_cancel_price_proposal(proposal_id: UUID, u=Depends(demo_manager)):
    return apply_price_proposal(proposal_id,u,cancel=True)
