"""Propostas de preço pesquisado: revisão humana, confirmação idempotente e histórico."""
import hashlib
import json
import re
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import Field, ValidationError
from psycopg.types.json import Jsonb
from fastapi import HTTPException
from app.schemas import Model
from app.db import connect

FIELDS = ('id','quantidade_embalagem','preco_embalagem','frete','minimo_embalagens','prazo_dias','cotado_em','valido_ate','referencia_publica','local_confirmado')


class Candidate(Model):
    fornecedor_id: UUID
    insumo_id: UUID
    quantidade_embalagem: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    preco_embalagem: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    unidade: Literal['g','ml','un']
    fonte_url: str = Field(min_length=8, max_length=2048)
    produto_pesquisado: str = Field(min_length=1, max_length=300)


class Confirmation(Model):
    confirmar: Literal[True]


def signature(rows):
    numeric = {'quantidade_embalagem','preco_embalagem','frete','minimo_embalagens','prazo_dias'}
    normalized = [{k: (str(Decimal(str(q[k])).normalize()) if k in numeric else str(q[k])) if q.get(k) is not None else None for k in FIELDS} for q in sorted(rows,key=lambda q:str(q['id']))]
    return hashlib.sha256(json.dumps(normalized,sort_keys=True).encode()).hexdigest()


def active_quotes(db, op, supplier, ingredient):
    return db.execute('''SELECT * FROM cotacoes WHERE operacao_id=%s AND fornecedor_id=%s AND insumo_id=%s AND ativo ORDER BY id''', (op,supplier,ingredient)).fetchall()


def split_candidates(research):
    """Um bloco inválido jamais vira uma escrita; nem é exibido como comando no chat."""
    candidates = []
    def remove(match):
        try:
            parsed=json.loads(match.group(1))
            if isinstance(parsed,list):candidates.extend(parsed[:5])
        except ValueError:pass
        return ''
    # O modelo pode fragmentar um bloco entre segmentos com citações.
    joined=''.join(b['texto'] for b in research['blocos'])
    pattern=r'```propostas_precos\s*([\s\S]*?)(?:```|\Z)'
    clean=re.sub(pattern,remove,joined)
    if candidates or clean!=joined:
        # Preserva as citações por segmento de texto visível antes do bloco final.
        position=joined.find('```propostas_precos')
        remaining=position
        visible=[]
        for block in research['blocos']:
            if remaining<=0:break
            part=block['texto'][:remaining]
            visible.append({**block,'texto':part})
            remaining-=len(block['texto'])
        research['blocos']=visible
    return candidates


def attach(result, op, context):
    raw=result.pop('_candidatos_precos', [])
    result['propostas_precos']=[]
    if not raw or not result.get('pesquisa_web_utilizada'):return result
    sources={s['url'] for s in result.get('fontes_web',[])}
    catalog=context.get('catalogo_precos',{})
    supplier_ids={str(s['id']) for s in catalog.get('fornecedores',[])}
    ingredient_ids={str(i['id']) for i in catalog.get('insumos',[])}
    seen=set()
    with connect() as db:
        for value in raw[:5]:
            try:c=Candidate.model_validate(value)
            except (ValidationError,TypeError):continue
            pair=(str(c.fornecedor_id),str(c.insumo_id))
            if pair in seen or c.fonte_url not in sources or pair[0] not in supplier_ids or pair[1] not in ingredient_ids:continue
            supplier=db.execute('SELECT nome FROM fornecedores WHERE operacao_id=%s AND id=%s AND ativo',(op,c.fornecedor_id)).fetchone()
            ingredient=db.execute('SELECT nome,unidade FROM insumos WHERE operacao_id=%s AND id=%s',(op,c.insumo_id)).fetchone()
            if not supplier or not ingredient or ingredient['unidade']!=c.unidade:continue
            old=[q for q in catalog.get('cotacoes',[]) if str(q['fornecedor_id'])==pair[0] and str(q['insumo_id'])==pair[1]]
            values=c.model_dump(mode='json')
            values.update(fornecedor=supplier['nome'],insumo=ingredient['nome'],
                precos_anteriores=[{'preco_embalagem':str(q['preco_embalagem']),'quantidade_embalagem':str(q['quantidade_embalagem'])} for q in old])
            row=db.execute('''INSERT INTO propostas_precos_otto(operacao_id,dados,assinatura_anterior)
                VALUES(%s,%s,%s) RETURNING id,criado_em,expira_em''',(op,Jsonb(values),signature(old))).fetchone()
            result['propostas_precos'].append({**values,**row})
            seen.add(pair)
    return result


def apply(db, user, proposal_id, cancel=False):
    op=user['operacao_id']
    db.execute('SELECT id FROM operacoes WHERE id=%s FOR UPDATE',(op,))
    row=db.execute('''SELECT *,expira_em<now() AS expirada FROM propostas_precos_otto
        WHERE operacao_id=%s AND id=%s FOR UPDATE''',(op,proposal_id)).fetchone()
    def fail(code,status=409):raise HTTPException(status,detail={'codigo':code})
    if not row:fail('PROPOSTA_NAO_ENCONTRADA',404)
    if row['status']=='confirmada':
        if cancel:fail('PROPOSTA_JA_CONFIRMADA')
        return {'status':'confirmada','cotacao_id':row['cotacao_id'],'ja_confirmada':True}
    if cancel:
        db.execute("UPDATE propostas_precos_otto SET status='cancelada' WHERE id=%s",(proposal_id,))
        return {'status':'cancelada'}
    if row['status']!='pendente':fail('PROPOSTA_CANCELADA')
    if row['expirada']:fail('PROPOSTA_EXPIRADA')
    data=row['dados']
    if not db.execute('SELECT 1 FROM fornecedores WHERE operacao_id=%s AND id=%s AND ativo',(op,data['fornecedor_id'])).fetchone():fail('FORNECEDOR_INATIVO')
    previous=active_quotes(db,op,data['fornecedor_id'],data['insumo_id'])
    if signature(previous)!=row['assinatura_anterior']:fail('COTACAO_ALTERADA_PESQUISE_NOVAMENTE')
    db.execute('UPDATE cotacoes SET ativo=false WHERE operacao_id=%s AND fornecedor_id=%s AND insumo_id=%s AND ativo',(op,data['fornecedor_id'],data['insumo_id']))
    quote=db.execute('''INSERT INTO cotacoes(operacao_id,fornecedor_id,insumo_id,quantidade_embalagem,preco_embalagem,
      minimo_embalagens,frete,prazo_dias,cotado_em,valido_ate,fonte_url,observacoes,referencia_publica,local_confirmado)
      VALUES(%s,%s,%s,%s,%s,NULL,NULL,NULL,%s::timestamptz::date,NULL,%s,%s,true,false) RETURNING id''',
      (op,data['fornecedor_id'],data['insumo_id'],data['quantidade_embalagem'],data['preco_embalagem'],row['criado_em'],data['fonte_url'],
       'Preço pesquisado pelo Otto e confirmado para cadastro pelo usuário. Produto: '+data['produto_pesquisado']+'. Condições comerciais locais pendentes.')).fetchone()
    db.execute("UPDATE propostas_precos_otto SET status='confirmada',cotacao_id=%s,confirmado_por=%s,confirmado_em=now() WHERE id=%s",(quote['id'],user['id'],proposal_id))
    db.execute('INSERT INTO auditoria(operacao_id,usuario_id,acao,dados) VALUES(%s,%s,%s,%s)',
        (op,user['id'],'confirmar_preco_pesquisado',Jsonb({'proposta_id':str(proposal_id),'cotacao_id':str(quote['id']),'anteriores':[str(q['id']) for q in previous],'preco':data['preco_embalagem'],'fonte':data['fonte_url']})))
    return {'status':'confirmada','cotacao_id':quote['id'],'ja_confirmada':False}
