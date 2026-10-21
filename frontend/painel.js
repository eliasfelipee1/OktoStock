'use strict';
const root = document.getElementById('live-content');
const page = location.pathname.split('/').pop().replace('.html', '') || 'index';
const money = (n) => n == null ? 'Não informado' : Number(n).toLocaleString('pt-BR', {style:'currency', currency:'BRL'});
const number = (n) => n == null ? 'Não informado' : Number(n).toLocaleString('pt-BR', {maximumFractionDigits:3});
const date = (s) => s ? new Date(s.length === 10 ? s+'T12:00:00' : s).toLocaleDateString('pt-BR', {timeZone:'America/Sao_Paulo'}) : 'Sem lote utilizável';
function node(tag, text, cls) {
  const e = document.createElement(tag);
  if (text != null) e.textContent = text;
  if (cls) e.className = cls;
  return e;
}
function panel(title, subtitle) {
  const section = node('section', null, 'panel live-panel');
  const head = node('div', null, 'panel-head');
  const titles = node('div'); titles.append(node('h2',title));
  if (subtitle) titles.append(node('p',subtitle));
  head.append(titles); section.append(head); return section;
}
function table(headers, rows) {
  const wrap = node('div', null, 'table-scroll'); const t = node('table');
  const head = node('thead'); const hr = node('tr');
  headers.forEach(h => hr.append(node('th', h))); head.append(hr);
  const body = node('tbody');
  rows.forEach(row => { const tr = node('tr'); row.forEach(v => tr.append(node('td',v))); body.append(tr); });
  if (!rows.length) {const td = node('td','Nenhum registro encontrado.'); td.colSpan=headers.length; const tr=node('tr');tr.append(td);body.append(tr);}
  t.append(head,body); wrap.append(t); return wrap;
}
function metrics(items) {
  const wrap=node('div',null,'metrics');
  items.forEach(([label,value,foot]) => {const item=node('article',null,'metric');
    item.append(node('div',label,'metric-top'),node('div',value,'metric-value'),node('p',foot,'metric-foot'));wrap.append(item);});
  return wrap;
}
function stockTable(rows) {
  return table(['Ingrediente','Saldo utilizável','Vencido','Mínimo','Validade mais próxima'],rows.map(i => [i.nome,number(i.saldo)+' '+i.unidade,number(i.vencido)+' '+i.unidade,number(i.estoque_minimo)+' '+i.unidade,date(i.validade)]));
}
function ranking(data) {
  const s=panel('Desempenho por sabor','Porções efetivamente vendidas');
  s.append(table(['Sabor','Porções','Receita'],data.contexto.ranking_sabores.map(r=>[r.nome,number(r.porcoes),money(r.receita)])));return s;
}
function daily(data) {
  const s=panel('Vendas por dia','Histórico cadastrado • dias de maior movimento identificados');
  s.append(table(['Data','Dia','Vendas','Receita','Custo de ingredientes'],data.contexto.vendas_por_dia.map(r=>[date(r.dia),r.dia_semana+(r.dia_forte?' • dia forte':''),number(r.vendas),money(r.receita),money(r.custo_ingredientes)])));return s;
}
function render(data) {
  root.replaceChildren();
  const r=data.resumo, c=data.contexto;
  if (page==='index' || page==='vendas') {
    root.append(metrics([['Receita de vendas',money(r.receita),'Vendas confirmadas'],['Custo de ingredientes',money(r.custo),'Custo histórico, não custo total'],['Margem sobre ingredientes',money(Number(r.receita)-Number(r.custo)),'Não representa lucro líquido'],['Porções vendidas',number(r.porcoes),number(r.vendas)+' vendas cadastradas']]));
    root.append(daily(data),ranking(data));
    if(page==='index') {
      const s=panel('Estoque em foco','Saldo atual por ingrediente');s.append(stockTable(data.estoque));root.append(s);
    } else {
      const s=panel('Histórico de vendas',`Página ${data.pagina} de ${data.paginas} • 50 registros por página`);
      s.append(table(['Data','Itens','Pagamento','Valor','Status'],data.vendas.map(v=>[date(v.criado_em),v.itens,v.pagamento,money(v.total),v.status])));
      const nav=node('div',null,'panel-body');
      [['Anterior',data.pagina-1],['Próxima',data.pagina+1]].forEach(([title,p])=>{const b=node('button',title,'button'); b.disabled=p<1||p>data.paginas;b.addEventListener('click',()=>load(p));nav.append(b);});s.append(nav);root.append(s);
    }
  }
  if(page==='estoque') {
    root.append(metrics([['Insumos',number(data.estoque.length),'Ingredientes cadastrados'],['Abaixo do mínimo',number(data.estoque.filter(i=>Number(i.saldo)<Number(i.estoque_minimo)).length),'Considera apenas saldo utilizável']]));
    const s=panel('Estoque por ingrediente','Quantidades em g, ml ou un • lotes vencidos separados do saldo utilizável');s.append(stockTable(data.estoque));root.append(s);
  }
  if(page==='receitas') {
    const cards=node('div',null,'cards live-recipes');
    data.produtos.forEach(p=>{
      const s=panel(p.nome,`Versão ${p.versao} • ${p.ativo?'Ativo':'Inativo'}`);
      const body=node('div',null,'panel-body');body.append(node('p','Preço de venda: '+money(p.preco)));
      body.append(node('p','Custo estimado dos ingredientes: '+money(p.custo_estimado)));
      body.append(node('p','Estimativa pelo último custo cadastrado; exclui mão de obra, impostos e embalagem.','subtext'));
      s.append(body,table(['Ingrediente','Quantidade por porção'],p.ingredientes.map(i=>[i.nome,number(i.quantidade)+' '+i.unidade])));cards.append(s);
    });
    if(!data.produtos.length)cards.append(node('p','Nenhuma ficha cadastrada.'));root.append(cards);
  }
  if(page==='perdas') {
    const l=data.perdas;
    root.append(metrics([['Custo total das perdas',money(l.custo_total_perdas),'Custos históricos dos lotes'],['Sobre a receita',number(l.percentual_sobre_receita_confirmada)+'%','Perdas ÷ receita confirmada'],['Porções descartadas',number(l.porcoes_perdidas_registradas),'Descarte de insumos não é contado como porção']]));
    const byRecipe=panel('Perdas por receita','Descartes sem receita não são atribuídos a sabores');byRecipe.id='perdas-por-receita';
    byRecipe.append(table(['Receita','Porções','Custo'],l.por_receita.map(i=>[i.nome,number(i.porcoes_registradas),money(i.custo)])));
    const byItem=panel('Perdas por ingrediente'); byItem.append(table(['Ingrediente','Quantidade','Custo'],l.por_insumo.map(i=>[i.nome,number(i.quantidade)+' '+i.unidade,money(i.custo)])));
    const history=panel('Histórico de perdas',`${l.registros.length} movimentos no período`);history.append(table(['Data','Ingrediente','Quantidade','Motivo','Custo'],l.registros.map(i=>[date(i.criado_em),i.insumo,number(i.quantidade)+' '+i.unidade,i.motivo,money(i.custo)])));
    root.append(byRecipe,byItem,history);
  }
  if(page==='producao') {
    const p=c.parametros; const prep=p.pre_preparo;
    root.append(metrics([['Prazo de pré-preparo',prep?'Quarta à noite':'Não informado','Regra cadastrada pelo dono'],['Público total da festa',number(p.publico_total_festa),'Não é a clientela da barraca'],['Receita de quinta a domingo',number(c.percentual_receita_quinta_a_domingo)+'%','Percentual medido no histórico']]));
    const s=panel('Planejamento de pré-preparo','Parâmetros da operação');const body=node('div',null,'panel-body');
    body.append(node('p',prep?.regra || 'Cadastre as regras de pré-preparo.'));
    body.append(node('p',p.feriado?.regra || 'Sem regra de feriado cadastrada.'));
    body.append(node('p','Ainda não há registro de execução de produção, capacidade do forno ou validade por preparo. O estoque de ingredientes não representa batatas já pré-assadas.'));
    body.append(node('p','Preparar até quarta não garante conservação até domingo; a quantidade depende das restrições de cada preparo.'));
    s.append(body);root.append(s,ranking(data));
  }
}
async function load(pagina=1) {
  const status=document.getElementById('connection-status');status.textContent='Consultando registros…';
  const token=sessionStorage.getItem('okto-panel-token');
  try {
    const response=await fetch((token?'/dashboard':'/demo/dados')+'?pagina='+pagina,{headers:token?{Authorization:'Bearer '+token}:{},cache:'no-store'});
    if(!response.ok) {
      document.getElementById('panel-login').hidden=false;
      throw new Error(response.status===401||response.status===403?'Conecte com um token de gerente ou IA para visualizar os registros.':`Não foi possível consultar os dados (HTTP ${response.status}).`);
    }
    const data=await response.json(); document.getElementById('panel-login').hidden=true;
    document.querySelector('.workspace strong').textContent=data.operacao.nome;
    document.querySelector('.demo-badge').textContent=data.contexto.parametros.natureza_dados==='simulados'?'DEMONSTRAÇÃO • DADOS SIMULADOS':'DADOS DA OPERAÇÃO';
    status.textContent=`Histórico: ${date(data.periodo.inicio)} a ${date(data.periodo.fim)}. Estoque: saldo atual. ${data.contexto.parametros.natureza_dados==='simulados'?'Registros simulados para demonstração.':''}`;
    const periodLabel=document.querySelector('.actions span.button');
    if(periodLabel) periodLabel.textContent=`${date(data.periodo.inicio)} – ${date(data.periodo.fim)}`;
    render(data);
  } catch(error) {root.replaceChildren();status.textContent=error.message;}
}
document.getElementById('panel-login').addEventListener('submit',event=>{event.preventDefault();sessionStorage.setItem('okto-panel-token',document.getElementById('panel-token').value.trim());load();});
load();
