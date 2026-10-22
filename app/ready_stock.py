"""Porções prontas: contagem física, produção com baixa única e venda FEFO."""
import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID
from fastapi import HTTPException
from pydantic import Field, AwareDatetime, model_validator
from app.schemas import Model


class Entry(Model):
    produto_id: UUID
    idempotency_key: UUID
    codigo: str = Field(min_length=1,max_length=120)
    origem: Literal['saldo_inicial','producao']
    quantidade: int = Field(ge=0,le=100000)
    validade: AwareDatetime
    custo_unitario: Optional[Decimal] = Field(default=None,ge=0,max_digits=18,decimal_places=6)

    @model_validator(mode='after')
    def valid(self):
        if self.origem=='saldo_inicial' and self.custo_unitario is None:
            raise ValueError('Informe o custo por porção da contagem inicial')
        if self.origem=='producao' and (self.quantidade==0 or self.custo_unitario is not None):
            raise ValueError('Produção exige quantidade positiva; custo é calculado pelos lotes')
        return self


class Waste(Model):
    lote_id: UUID
    idempotency_key: UUID
    quantidade: int = Field(gt=0,le=100000)
    motivo: str = Field(min_length=3,max_length=300)


def fail(code,status=409):
    raise HTTPException(status,detail={'codigo':code})


def snapshot(db,op):
    rows=db.execute('SELECT * FROM estoque_prontos WHERE operacao_id=%s ORDER BY nome',(op,)).fetchall()
    alerts={r['produto_id']:r for r in db.execute('SELECT id,produto_id,aberto_em FROM alertas_prontos WHERE operacao_id=%s AND resolvido_em IS NULL',(op,)).fetchall()}
    for r in rows:
        r['limite_alerta']=r['meta']*r['percentual_alerta']/100
        r['percentual_disponivel']=Decimal(r['saldo'])*100/r['meta'] if r['contagem_informada'] else None
        r['abaixo_limite']=r['contagem_informada'] and r['saldo']<r['limite_alerta']
        r['repor_ate_meta']=max(0,r['meta']-r['saldo']) if r['contagem_informada'] else None
        r['alerta']=alerts.get(r['produto_id'])
    lots=db.execute('''SELECT l.id,l.produto_id,p.nome,l.codigo,l.saldo,l.validade,l.origem
      FROM lotes_prontos l JOIN produtos p ON p.id=l.produto_id
      WHERE l.operacao_id=%s AND l.saldo>0 ORDER BY l.validade,l.id''',(op,)).fetchall()
    return {'sabores':rows,'lotes':lots,'alertas':[r for r in rows if r['abaixo_limite']],
            'contagens_pendentes':[r['nome'] for r in rows if not r['contagem_informada']]}


def register(db,u,body):
    op=u['operacao_id']
    db.execute('SELECT id FROM operacoes WHERE id=%s FOR UPDATE',(op,))
    fingerprint=hashlib.sha256(json.dumps(body.model_dump(mode='json'),sort_keys=True).encode()).hexdigest()
    old=db.execute('SELECT * FROM lotes_prontos WHERE operacao_id=%s AND chave=%s',(op,body.idempotency_key)).fetchone()
    if old:
        if old['payload_hash']!=fingerprint:fail('CHAVE_REUTILIZADA_COM_OUTRO_CONTEUDO')
        return old
    product=db.execute('SELECT * FROM produtos WHERE id=%s AND operacao_id=%s AND ativo',(body.produto_id,op)).fetchone()
    if not product or not product['ficha_detalhes'].get('controle_prontos'):fail('PRODUTO_SEM_CONTROLE_PRONTOS')
    now=db.execute('SELECT now() AS t').fetchone()['t']
    if body.validade<=now:fail('LOTE_VENCIDO',422)
    if body.origem=='saldo_inicial' and db.execute('SELECT 1 FROM lotes_prontos WHERE operacao_id=%s AND produto_id=%s LIMIT 1',(op,body.produto_id)).fetchone():
        fail('SALDO_INICIAL_JA_REGISTRADO')
    allocations=[];cost=Decimal(0)
    if body.origem=='producao':
        recipe=db.execute('SELECT * FROM ingredientes WHERE produto_id=%s AND operacao_id=%s ORDER BY insumo_id',(body.produto_id,op)).fetchall()
        if not recipe:fail('RECEITA_VAZIA')
        for item in recipe:
            remaining=item['quantidade']*body.quantidade
            lots=db.execute('''SELECT * FROM lotes WHERE operacao_id=%s AND insumo_id=%s AND saldo>0
               AND validade>=CURRENT_DATE ORDER BY validade,criado_em,id FOR UPDATE''',(op,item['insumo_id'])).fetchall()
            for lot in lots:
                take=min(remaining,lot['saldo']);remaining-=take
                allocations.append((lot,take));cost+=take*lot['custo_unitario']
                if remaining==0:break
            if remaining>0:fail('INSUMOS_INSUFICIENTES_PARA_PRODUZIR')
    unit=cost/body.quantidade if body.origem=='producao' else body.custo_unitario
    row=db.execute('''INSERT INTO lotes_prontos(operacao_id,produto_id,chave,payload_hash,codigo,origem,
        quantidade,saldo,custo_unitario,validade,usuario_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *''',
        (op,body.produto_id,body.idempotency_key,fingerprint,body.codigo,body.origem,body.quantidade,body.quantidade,unit,body.validade,u['id'])).fetchone()
    for lot,take in allocations:
        db.execute('UPDATE lotes SET saldo=saldo-%s WHERE id=%s',(take,lot['id']))
        db.execute('''INSERT INTO movimentacoes(operacao_id,lote_id,usuario_id,tipo,quantidade,custo_unitario,producao_lote_id,motivo)
           VALUES(%s,%s,%s,'producao',%s,%s,%s,'Produção de porções prontas')''',(op,lot['id'],u['id'],-take,lot['custo_unitario'],row['id']))
    return row


def consume_sale(db,u,product_id,quantity,sale_id):
    lots=db.execute('''SELECT * FROM lotes_prontos WHERE operacao_id=%s AND produto_id=%s
       AND saldo>0 AND validade>now() ORDER BY validade,criado_em,id FOR UPDATE''',(u['operacao_id'],product_id)).fetchall()
    remaining=quantity;cost=Decimal(0)
    for lot in lots:
        take=min(remaining,lot['saldo']);remaining-=take
        db.execute('UPDATE lotes_prontos SET saldo=saldo-%s WHERE id=%s',(take,lot['id']))
        db.execute('''INSERT INTO movimentos_prontos(operacao_id,lote_id,venda_id,usuario_id,quantidade,tipo)
          VALUES(%s,%s,%s,%s,%s,'venda')''',(u['operacao_id'],lot['id'],sale_id,u['id'],-take))
        cost+=take*lot['custo_unitario']
        if remaining==0:break
    if remaining:fail('PORCOES_PRONTAS_INSUFICIENTES')
    return cost


def discard(db,u,body):
    op=u['operacao_id'];db.execute('SELECT id FROM operacoes WHERE id=%s FOR UPDATE',(op,))
    old=db.execute('SELECT * FROM movimentos_prontos WHERE operacao_id=%s AND chave=%s',(op,body.idempotency_key)).fetchone()
    if old:
        if old['lote_id']!=body.lote_id or -old['quantidade']!=body.quantidade or old['motivo']!=body.motivo:fail('CHAVE_REUTILIZADA_COM_OUTRO_CONTEUDO')
        return old
    lot=db.execute('SELECT * FROM lotes_prontos WHERE operacao_id=%s AND id=%s FOR UPDATE',(op,body.lote_id)).fetchone()
    if not lot:fail('LOTE_NAO_ENCONTRADO',404)
    if lot['saldo']<body.quantidade:fail('SALDO_PRONTO_INSUFICIENTE')
    db.execute('UPDATE lotes_prontos SET saldo=saldo-%s WHERE id=%s',(body.quantidade,lot['id']))
    return db.execute('''INSERT INTO movimentos_prontos(operacao_id,lote_id,usuario_id,quantidade,tipo,motivo,chave)
       VALUES(%s,%s,%s,%s,'perda',%s,%s) RETURNING *''',(op,lot['id'],u['id'],-body.quantidade,body.motivo,body.idempotency_key)).fetchone()
