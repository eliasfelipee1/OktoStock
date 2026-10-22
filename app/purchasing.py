"""Reposição determinística; comparação de propostas cadastradas, sem compras automáticas."""
from datetime import date
from decimal import Decimal, ROUND_CEILING
from typing import Optional
from uuid import UUID
from pydantic import Field, model_validator
from fastapi import HTTPException
from app.schemas import Model
from app.ready_stock import snapshot as ready_snapshot


class Supplier(Model):
    nome: str = Field(min_length=1, max_length=120)
    contato: str = Field(default='', max_length=300)
    ativo: bool = True
    simulado: bool = False


class Quote(Model):
    fornecedor_id: UUID
    insumo_id: UUID
    quantidade_embalagem: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    preco_embalagem: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    minimo_embalagens: int = Field(ge=1, le=100000)
    frete: Optional[Decimal] = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    prazo_dias: Optional[int] = Field(default=None, ge=0, le=365)
    cotado_em: date
    valido_ate: date
    ativo: bool = True
    simulado: bool = False

    @model_validator(mode='after')
    def dates(self):
        if self.valido_ate < self.cotado_em:
            raise ValueError('Validade anterior à cotação')
        return self


def compare(offers, need, today):
    """Compara o custo total entregue para cobrir um insumo, não otimiza uma cesta."""
    rows = []
    if need <= 0:
        return rows
    for source in offers:
        q = dict(source)
        count = max(q['minimo_embalagens'] or 1, int((need / q['quantidade_embalagem']).to_integral_value(rounding=ROUND_CEILING)))
        q.update(embalagens=count, quantidade_total=count*q['quantidade_embalagem'],
                 preco_por_unidade=q['preco_embalagem']/q['quantidade_embalagem'],
                 total_entregue=(count*q['preco_embalagem']+q['frete']) if q['frete'] is not None else None)
        pending = []
        if not q['ativo'] or not q['fornecedor_ativo']: pending.append('Inativo')
        if q['valido_ate'] is None or not q['cotado_em'] <= today <= q['valido_ate']: pending.append('Cotação fora da validade')
        if q['frete'] is None: pending.append('Frete não informado')
        if q['prazo_dias'] is None: pending.append('Prazo não informado')
        if q['minimo_embalagens'] is None: pending.append('Pedido mínimo não informado')
        if not q.get('local_confirmado', True): pending.append('Preço da loja de Blumenau não confirmado')
        if q.get('referencia_publica'): pending.append('Referência pública; confirmar proposta comercial')
        q['pendencias'] = pending
        q['elegivel'] = not pending
        rows.append(q)
    return sorted(rows, key=lambda q: (not q['elegivel'], q['total_entregue'] if q['total_entregue'] is not None else Decimal('Infinity'), q['prazo_dias'] or 0, str(q['id'])))


def snapshot(db, operation_id):
    today = db.execute('SELECT CURRENT_DATE AS dia, now() AS instante').fetchone()
    suppliers = db.execute('SELECT * FROM fornecedores WHERE operacao_id=%s ORDER BY nome', (operation_id,)).fetchall()
    offers = db.execute('''SELECT c.*, f.nome AS fornecedor,f.ativo AS fornecedor_ativo,
        f.simulado AS fornecedor_simulado,i.nome AS insumo,i.unidade
        FROM cotacoes c JOIN fornecedores f ON f.id=c.fornecedor_id AND f.operacao_id=c.operacao_id
        JOIN insumos i ON i.id=c.insumo_id AND i.operacao_id=c.operacao_id
        WHERE c.operacao_id=%s ORDER BY i.nome,f.nome,c.cotado_em DESC''', (operation_id,)).fetchall()
    stocks = db.execute('SELECT * FROM estoque_reposicao WHERE operacao_id=%s ORDER BY nome', (operation_id,)).fetchall()
    alerts = db.execute('''SELECT a.id,a.insumo_id,a.aberto_em FROM alertas_reposicao a
        WHERE a.operacao_id=%s AND a.resolvido_em IS NULL''', (operation_id,)).fetchall()
    ids = {a['insumo_id']: a for a in alerts}
    for item in stocks:
        need = max(Decimal(0), item['minimo']-item['saldo'])
        item['necessidade'] = need
        item['comparativo'] = compare([q for q in offers if q['insumo_id']==item['insumo_id']], need, today['dia'])
        eligible = [q for q in item['comparativo'] if q['elegivel']]
        # Não mistura cotações didáticas com cotações reais no ranking.
        real = [q for q in eligible if not q['simulado'] and not q['fornecedor_simulado']]
        item['melhor_oferta'] = (real or eligible or [None])[0]
        item['alerta'] = ids.get(item['insumo_id'])
    target = db.execute('SELECT * FROM configuracao_reposicao WHERE operacao_id=%s', (operation_id,)).fetchone()
    products = db.execute('''SELECT p.id,p.nome,p.ativo,p.ficha_detalhes,
        min(floor(coalesce(s.saldo,0)/r.quantidade)) AS porcoes_individuais
        FROM produtos p LEFT JOIN ingredientes r ON r.produto_id=p.id AND r.operacao_id=p.operacao_id
        LEFT JOIN estoque_reposicao s ON s.insumo_id=r.insumo_id AND s.operacao_id=r.operacao_id
        WHERE p.operacao_id=%s AND (p.ativo OR p.ficha_detalhes->>'cardapio_atual'='true')
        GROUP BY p.id ORDER BY p.nome''', (operation_id,)).fetchall()
    ready = ready_snapshot(db, operation_id)
    policy = target or {}
    movement = today['dia'].isoweekday() in policy.get('dias_movimento', [4,5,6,7])
    target_today = policy.get('meta_movimento',1000) if movement else policy.get('meta_calmo',250)
    return {'prontos': ready, 'politica': {'controle_prontos': policy.get('controle_prontos',False), 'meta_calmo':policy.get('meta_calmo',250), 'meta_movimento':policy.get('meta_movimento',1000), 'percentual_alerta':policy.get('percentual_alerta',30), 'dias_movimento':policy.get('dias_movimento',[4,5,6,7]), 'dia_movimento':movement},
            'gerado_em': today['instante'], 'meta_por_sabor': target_today if policy.get('controle_prontos') else policy.get('porcoes_por_sabor',50),
            'fornecedores': suppliers, 'cotacoes': offers, 'estoque': stocks, 'sabores': products,
            'alertas': [s for s in stocks if s['necessidade']>0],
            'pendencias_fichas': [p['nome'] for p in products if not p['ativo'] or p['porcoes_individuais'] is None],
            'criterio': 'Menor total entregue por insumo para recompor a meta: embalagens inteiras, mínimo e frete. Entre cotações válidas e completas cadastradas. Não é preço de mercado nem compra aprovada.',
            'limites': 'Disponibilidade por sabor é individual; o mínimo dos insumos soma todas as fichas. Validar prazo, armazenamento e validade antes de comprar.'}


def save_supplier(db, operation, body, supplier_id=None):
    if supplier_id:
        result = db.execute('''UPDATE fornecedores SET nome=%s,contato=%s,ativo=%s,simulado=%s
            WHERE operacao_id=%s AND id=%s RETURNING *''',
            (body.nome,body.contato,body.ativo,body.simulado,operation,supplier_id)).fetchone()
        if not result: raise HTTPException(404, detail={'codigo':'FORNECEDOR_NAO_ENCONTRADO'})
        return result
    return db.execute('''INSERT INTO fornecedores(operacao_id,nome,contato,ativo,simulado)
        VALUES(%s,%s,%s,%s,%s) RETURNING *''', (operation,body.nome,body.contato,body.ativo,body.simulado)).fetchone()


def save_quote(db, operation, body):
    for table, uid in [('fornecedores',body.fornecedor_id),('insumos',body.insumo_id)]:
        if not db.execute(f'SELECT 1 FROM {table} WHERE operacao_id=%s AND id=%s', (operation,uid)).fetchone():
            raise HTTPException(404, detail={'codigo':'CADASTRO_NAO_ENCONTRADO'})
    # Uma nova proposta substitui a anterior do mesmo fornecedor/insumo, preservando o histórico.
    db.execute('SELECT id FROM operacoes WHERE id=%s FOR UPDATE', (operation,))
    db.execute('UPDATE cotacoes SET ativo=false WHERE operacao_id=%s AND fornecedor_id=%s AND insumo_id=%s AND ativo',
               (operation,body.fornecedor_id,body.insumo_id))
    fields = body.model_dump()
    return db.execute('INSERT INTO cotacoes(operacao_id,'+','.join(fields)+') VALUES('+','.join(['%s']*(len(fields)+1))+') RETURNING *',
                      [operation]+list(fields.values())).fetchone()
