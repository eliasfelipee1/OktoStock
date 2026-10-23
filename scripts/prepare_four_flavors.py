"""Cria operação local dos quatro sabores sem misturar o histórico simulado anterior.

Não inventa fichas, estoque, fornecedores, cotações ou vendas. O .env é atualizado
somente após o commit. A operação anterior e suas credenciais ficam preservadas.
"""
import hashlib
import os
import secrets
from pathlib import Path
from uuid import UUID
from dotenv import set_key
from psycopg.types.json import Jsonb
from app.db import connect

FLAVORS = ['Linguiça Blumenau', 'Strogonoff de frango', 'Bolonhesa', 'Vegetariana']
OPERATION = UUID('c04f1a40-5050-4040-8050-000000000004')


def prepare():
    token = None
    with connect() as db:
        db.execute('SELECT pg_advisory_xact_lock(728195)')
        existing=db.execute('SELECT id FROM operacoes WHERE id=%s', (OPERATION,)).fetchone()
        if not existing:
            token=secrets.token_urlsafe(40)
            db.execute("INSERT INTO operacoes(id,nome) VALUES(%s,'OktoStock — quatro sabores')", (OPERATION,))
            db.execute("INSERT INTO usuarios(operacao_id,nome,papel,token_hash) VALUES(%s,'Responsável local','gerente',%s)",
                       (OPERATION,hashlib.sha256(token.encode()).hexdigest()))
            db.execute('INSERT INTO contextos_operacionais(operacao_id,parametros) VALUES(%s,%s)',
                       (OPERATION,Jsonb({'natureza_dados':'cadastro_real_local','sabores':FLAVORS,'meta_por_sabor':50,
                       'cardapio_em_validacao':True,'nota_cardapio':'Receitas, saldos e cotações reais aguardam cadastro. Histórico simulado anterior preservado em outra operação.'})))
        else:
            config=db.execute('SELECT parametros FROM contextos_operacionais WHERE operacao_id=%s',(OPERATION,)).fetchone()
            if not config or config['parametros'].get('natureza_dados')!='cadastro_real_local':
                raise RuntimeError('ID reservado já utilizado; nenhum dado foi alterado')
        for name in FLAVORS:
            if not db.execute("SELECT 1 FROM produtos WHERE operacao_id=%s AND nome=%s AND ficha_detalhes @> '{\"cardapio_atual\":true}'", (OPERATION,name)).fetchone():
                db.execute('INSERT INTO produtos(operacao_id,nome,preco,ativo,ficha_detalhes) VALUES(%s,%s,NULL,false,%s)',
                           (OPERATION,name,Jsonb({'cardapio_atual':True,'status':'aguardando_receita_real',
                            'rendimento_porcoes':1,'simulada':False,'pendencias':['Ingredientes e quantidades por porção','Preparo','Preço de venda']})))
        db.execute('INSERT INTO configuracao_reposicao(operacao_id,porcoes_por_sabor) VALUES(%s,50) ON CONFLICT(operacao_id) DO NOTHING', (OPERATION,))
        db.execute('SELECT atualizar_alertas_reposicao(%s)', (OPERATION,))
    env=Path(__file__).resolve().parents[1]/'.env'
    set_key(str(env),'LOCAL_DEMO_OPERATION_ID',str(OPERATION))
    if token: set_key(str(env),'OKTO_DEMO_TOKEN',token)
    env.chmod(0o600)
    print('Quatro sabores preparados; receitas, estoque e cotações reais pendentes. Histórico anterior preservado em outra operação.')


if __name__ == '__main__':
    prepare()
