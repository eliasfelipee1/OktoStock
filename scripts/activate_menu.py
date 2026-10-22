"""Importa as receitas já fornecidas pelo usuário; não cria saldos ou preços de venda."""
import json,os
from decimal import Decimal as D
from pathlib import Path
from psycopg.types.json import Jsonb
from app.db import connect

META={
 'LIN':{'foto':'linguica-blumenau.jpg','credito':'Nossas Receitas · YouTube','foto_fonte':'https://www.youtube.com/watch?v=UN5KNwvNXIs',
        'preparo':'Preparar a batata; refogar linguiça, cebola, pimentão e tomate com azeite; incorporar molho e temperos. Rechear, adicionar requeijão e muçarela e finalizar conforme o processo da cozinha.',
        'alergenicos':'Leite e derivados; verificar glúten no rótulo da linguiça.','atributos':'Contém lactose.'},
 'STR':{'foto':'strogonoff-frango.jpg','credito':'Chesini','foto_fonte':'https://www.chesini.com.br/receita/batata-recheada-com-strogonoff-de-frango-chesini',
        'preparo':'Preparar a batata; refogar cebola e alho, incorporar o frango já cozido, molho, ketchup, mostarda e cogumelo. Adicionar creme de leite e temperos, rechear com muçarela e finalizar com batata palha.',
        'alergenicos':'Leite; verificar soja e glúten conforme marca dos ingredientes.','atributos':'Contém lactose; verificar glúten por marca.'},
 'BOL':{'foto':'bolonhesa.png','credito':'Vokare / Folha de Notícias','foto_fonte':'https://vokare.com.br/receita-de-batata-recheada-a-bolonhesa/',
        'preparo':'Preparar a batata; refogar carne moída, cebola e alho em azeite. Adicionar tomate, molho, extrato, cenoura e temperos; cozinhar conforme processo da cozinha. Rechear e finalizar com muçarela, parmesão e salsinha.',
        'alergenicos':'Leite e derivados; verificar glúten no rótulo do molho.','atributos':'Contém lactose.'},
 'VEG':{'foto':'vegetariana.png','credito':'Yatna Yoga','foto_fonte':'https://yatnamarayoga.blogspot.com/2018/09/batata-recheada-com-creme-de-brocolis.html',
        'preparo':'Preparar a batata; combinar brócolis cozido, milho escorrido, tomate-cereja e temperos. Rechear com requeijão e muçarela e finalizar com azeite e cheiro-verde.',
        'alergenicos':'Leite e derivados.','atributos':'Vegetariana, não vegana; contém lactose.'}
}


def activate(op):
 catalog=json.loads((Path(__file__).parent/'data/catalogo_okto.json').read_text())
 vendors=json.loads((Path(__file__).parent/'data/fornecedores_blumenau.json').read_text())
 with connect() as db:
  db.execute('SELECT id FROM operacoes WHERE id=%s FOR UPDATE',(op,))
  ids={}
  for code,name,unit,*_ in catalog['insumos']:
   base={'kg':'g','l':'ml','un':'un'}[unit]
   row=db.execute('SELECT id FROM insumos WHERE operacao_id=%s AND nome=%s AND unidade=%s',(op,name,base)).fetchone()
   if not row:row=db.execute('INSERT INTO insumos(operacao_id,nome,unidade,estoque_minimo) VALUES(%s,%s,%s,0) RETURNING id',(op,name,base)).fetchone()
   ids[code]=row['id']
  for code,name,*_ in catalog['produtos']:
   product=db.execute('SELECT * FROM produtos WHERE operacao_id=%s AND nome=%s AND ficha_detalhes->>\'cardapio_atual\'=\'true\' ORDER BY versao DESC LIMIT 1',(op,name)).fetchone()
   if not product:raise RuntimeError('Prepare primeiro os quatro sabores')
   if product['ficha_detalhes'].get('origem')=='Receitas fornecidas pelo usuário em docs/OTTO_REQUISITOS.md':continue
   if db.execute('SELECT 1 FROM venda_itens WHERE produto_id=%s LIMIT 1',(product['id'],)).fetchone():raise RuntimeError('Ficha já usada; crie revisão')
   db.execute('DELETE FROM ingredientes WHERE operacao_id=%s AND produto_id=%s',(op,product['id']))
   for flavor,ing,amount in catalog['receita_ingredientes']:
    if flavor==code:db.execute('INSERT INTO ingredientes VALUES(%s,%s,%s,%s)',(op,product['id'],ids[ing],D(amount)*1000))
   details={**META[code],'codigo':code,'status':'receita_fornecida','cardapio_atual':True,'controle_prontos':True,
       'origem':'Receitas fornecidas pelo usuário em docs/OTTO_REQUISITOS.md','rendimento_porcoes':1,
       'batata_bruta_g':450,'batata_liquida_g':380,'perda_limpeza_percentual':'15.56','fator_correcao_batata':'1.184211',
       'observacoes':'450 g de batata bruta rendem 380 g utilizáveis. A perda de limpeza já está na quantidade bruta: não baixar novamente. Foto ilustrativa de referência; não representa necessariamente a ficha exata. Preparo resumido proposto para revisão pela cozinha. Adicionais não estão incluídos.',
       'simulada':False}
   db.execute('UPDATE produtos SET ativo=true,ficha_detalhes=%s WHERE id=%s',(Jsonb(details),product['id']))
  db.execute('''INSERT INTO configuracao_reposicao(operacao_id,porcoes_por_sabor,controle_prontos) VALUES(%s,50,true)
    ON CONFLICT(operacao_id) DO UPDATE SET controle_prontos=true,meta_calmo=250,meta_movimento=1000,
    percentual_alerta=30,dias_movimento=ARRAY[4,5,6,7]''',(op,))
  for f in vendors['fornecedores']:
   row=db.execute('''INSERT INTO fornecedores(operacao_id,nome,contato,cidade,fonte_url)
      VALUES(%s,%s,%s,%s,%s) ON CONFLICT(operacao_id,nome) DO UPDATE SET cidade=EXCLUDED.cidade,fonte_url=EXCLUDED.fonte_url RETURNING id''',
      (op,f['nome'],f['contato'],f['cidade'],f['fonte_url'])).fetchone()
   if not db.execute('SELECT 1 FROM cotacoes WHERE operacao_id=%s AND fornecedor_id=%s AND fonte_url=%s AND cotado_em=%s',(op,row['id'],f['url'],vendors['consultado_em'])).fetchone():
    db.execute('''INSERT INTO cotacoes(operacao_id,fornecedor_id,insumo_id,quantidade_embalagem,preco_embalagem,
       minimo_embalagens,frete,prazo_dias,cotado_em,valido_ate,fonte_url,observacoes,referencia_publica,local_confirmado)
       VALUES(%s,%s,%s,%s,%s,NULL,NULL,NULL,%s,NULL,%s,%s,true,false)''',
       (op,row['id'],ids['BAT'],D(f['quantidade']),D(f['preco']),vendors['consultado_em'],f['url'],f['produto']+'. '+f['metodo']+'. '+vendors['observacao']))
  config=db.execute('SELECT parametros FROM contextos_operacionais WHERE operacao_id=%s',(op,)).fetchone()['parametros']
  config.update(cardapio_em_validacao=False,meta_por_sabor=None,dias_maior_movimento_iso=[4,5,6,7],
    regra_prontos={'dias_calmos':250,'dias_movimento':1000,'alerta_abaixo_percentual':30},
    nota_cardapio='Receitas fornecidas pelo usuário; saldos físicos ainda devem ser contados. Referências públicas de fornecedores exigem confirmação local.')
  db.execute('UPDATE contextos_operacionais SET parametros=%s WHERE operacao_id=%s',(Jsonb(config),op))
  db.execute('SELECT atualizar_alertas_prontos(%s)',(op,));db.execute('SELECT atualizar_alertas_reposicao(%s)',(op,))
 print('Receitas importadas; política 250/1000 e 30% aplicada; 3 fornecedores com referências públicas. Nenhum saldo físico foi inventado.')

if __name__=='__main__':activate(os.environ['LOCAL_DEMO_OPERATION_ID'])
