"""Adiciona referências públicas consultadas; não cria condições comerciais locais."""
import os
from app.db import connect

PRICES = [
 ('Cebola', '1000', '8.99', 'Cebola Kg', 'https://super.angeloni.com.br/cebola-kg-302/p'),
 ('Tomate', '1000', '15.39', 'Tomate Italiano Kg', 'https://super.angeloni.com.br/tomate-italiano-kg-786934/p'),
 ('Extrato de tomate', '300', '7.99', 'Extrato de Tomate ELEFANTE Só Tomate Pote 300g', 'https://super.angeloni.com.br/4952229-extrato-de-tomate-elefante-so-tomate-300g/p'),
]

def main():
 with connect() as db:
  op=os.environ['LOCAL_DEMO_OPERATION_ID']
  supplier=db.execute('SELECT id FROM fornecedores WHERE operacao_id=%s AND nome=%s',(op,'Angeloni — Blumenau')).fetchone()
  if not supplier:raise RuntimeError('Fornecedor não cadastrado')
  for name,quantity,price,product,url in PRICES:
   ingredient=db.execute("SELECT id FROM insumos WHERE operacao_id=%s AND nome=%s AND unidade='g'",(op,name)).fetchone()
   if not ingredient:raise RuntimeError('Insumo não cadastrado: '+name)
   if db.execute("SELECT 1 FROM cotacoes WHERE operacao_id=%s AND fornecedor_id=%s AND fonte_url=%s AND cotado_em='2026-10-22'",(op,supplier['id'],url)).fetchone():continue
   db.execute('''INSERT INTO cotacoes(operacao_id,fornecedor_id,insumo_id,quantidade_embalagem,preco_embalagem,
     minimo_embalagens,frete,prazo_dias,cotado_em,valido_ate,fonte_url,observacoes,referencia_publica,local_confirmado)
     VALUES(%s,%s,%s,%s,%s,NULL,NULL,NULL,'2026-10-22',NULL,%s,%s,true,false)''',
     (op,supplier['id'],ingredient['id'],quantity,price,url,
      product+'. Preço consultado no catálogo público Angeloni em 22/10/2026. Hortifruti por kg; extrato por pote de 300 g. Preço por CEP/loja de Blumenau, frete, mínimo, prazo e validade precisam de confirmação.'))
  print('Banco:',db.execute('SELECT current_database() AS nome').fetchone()['nome'])
  print('Referências cadastradas:',len(PRICES))

if __name__=='__main__':main()
