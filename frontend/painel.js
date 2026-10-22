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
      const s=panel('Histórico de vendas',`${number(r.vendas)} vendas encontradas • página ${data.pagina} de ${data.paginas} • 50 por página`);
      s.append(table(['Data','Hora','Itens','Pagamento','Valor','Status'],data.vendas.map(v=>[date(v.criado_em),hour(v.criado_em),v.itens,(v.pagamento||'').split(', ').map(f=>PAYMENTS[f]||f).join(', '),money(v.total),v.status])));
      const nav=node('div',null,'panel-body');
      [['Anterior',data.pagina-1],['Próxima',data.pagina+1]].forEach(([title,p])=>{const b=node('button',title,'button'); b.disabled=p<1||p>data.paginas;b.addEventListener('click',()=>load(p));nav.append(b);});s.append(nav);root.append(s);
    }
  }
  if(page==='estoque') {
    const rows=filteredStock(data.estoque);
    root.append(metrics([['Insumos',number(data.estoque.length),'Ingredientes cadastrados'],['Abaixo do mínimo',number(data.estoque.filter(i=>Number(i.saldo)<Number(i.estoque_minimo)).length),'Considera apenas saldo utilizável']]));
    const s=panel('Estoque por ingrediente',`${rows.length} de ${data.estoque.length} ingredientes • quantidades em g, ml ou un • lotes vencidos separados do saldo utilizável`);s.append(stockTable(rows));root.append(s);
  }
  if(page==='receitas') {
    const cards=node('div',null,'cards live-recipes');
    const recipes=data.produtos.filter(p=>(!filters.produto||p.id===filters.produto)&&(!filters.ingrediente||p.ingredientes.some(i=>matches(i.nome,filters.ingrediente))));
    recipes.forEach(p=>{
      const s=panel(p.nome,`Versão ${p.versao} • ${p.ativo?'Ativo':'Inativo'}`);
      const body=node('div',null,'panel-body');body.append(node('p','Preço de venda: '+money(p.preco)));
      body.append(node('p','Custo estimado dos ingredientes: '+money(p.custo_estimado)));
      body.append(node('p','Estimativa pelo último custo cadastrado; exclui mão de obra, impostos e embalagem.','subtext'));
      s.append(body,table(['Ingrediente','Quantidade por porção'],p.ingredientes.map(i=>[i.nome,number(i.quantidade)+' '+i.unidade])));cards.append(s);
    });
    if(!recipes.length)cards.append(node('p',data.produtos.length?'Nenhuma ficha corresponde aos filtros.':'Nenhuma ficha cadastrada.'));root.append(cards);
  }
  if(page==='perdas') {
    const l=data.perdas;
    root.append(metrics([['Custo total das perdas',money(l.custo_total_perdas),'Custos históricos dos lotes'],['Sobre a receita',number(l.percentual_sobre_receita_confirmada)+'%','Perdas ÷ receita confirmada'],['Porções descartadas',number(l.porcoes_perdidas_registradas),'Descarte de insumos não é contado como porção']]));
    const byRecipe=panel('Perdas por receita','Descartes sem receita não são atribuídos a sabores');byRecipe.id='perdas-por-receita';
    byRecipe.append(table(['Receita','Porções','Custo'],l.por_receita.map(i=>[i.nome,number(i.porcoes_registradas),money(i.custo)])));
    const lossItems=l.por_insumo.filter(i=>!filters.insumo||i.nome===filters.insumo), lossRows=l.registros.filter(i=>!filters.insumo||i.insumo===filters.insumo);
    const byItem=panel('Perdas por ingrediente'); byItem.append(table(['Ingrediente','Quantidade','Custo'],lossItems.map(i=>[i.nome,number(i.quantidade)+' '+i.unidade,money(i.custo)])));
    const history=panel('Histórico de perdas',`${lossRows.length} movimentos no período`);history.append(table(['Data','Ingrediente','Quantidade','Motivo','Custo'],lossRows.map(i=>[date(i.criado_em),i.insumo,number(i.quantidade)+' '+i.unidade,i.motivo,money(i.custo)])));
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
// Filtros: os do servidor recarregam os dados; os do navegador só redesenham a tela.
const SERVER_FILTERS=['inicio','fim','dia_semana','produto_id','forma'];
const PAGE_FILTERS={
  index:['inicio','fim','dia_semana','produto_id','forma'],
  vendas:['inicio','fim','dia_semana','produto_id','forma'],
  producao:['inicio','fim','dia_semana','produto_id'],
  perdas:['inicio','fim','insumo'],
  estoque:['busca','situacao'],
  receitas:['produto','ingrediente'],
};
const PAYMENTS={pix:'Pix',cartao:'Cartão',dinheiro:'Dinheiro'};
const WEEKDAYS=['Segunda-feira','Terça-feira','Quarta-feira','Quinta-feira','Sexta-feira','Sábado','Domingo'];
const filters=Object.fromEntries(new URLSearchParams(location.search));
const status=document.getElementById('connection-status');
let lastData=null;
const plain=(t)=>String(t||'').normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase();
const matches=(text,term)=>plain(text).includes(plain(term).trim());
function hour(s){return new Date(s).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit',timeZone:'America/Sao_Paulo'});}
function isoDay(offset){return new Date(Date.now()+offset*864e5).toLocaleDateString('en-CA',{timeZone:'America/Sao_Paulo'});}
function filteredStock(rows){
  const today=isoDay(0), soon=isoDay(2);
  return rows.filter(i=>(!filters.busca||matches(i.nome,filters.busca))&&(
    !filters.situacao||(filters.situacao==='abaixo'&&Number(i.saldo)<Number(i.estoque_minimo))
    ||(filters.situacao==='ok'&&Number(i.saldo)>=Number(i.estoque_minimo))
    ||(filters.situacao==='vencido'&&Number(i.vencido)>0)
    ||(filters.situacao==='vence'&&i.validade&&i.validade>=today&&i.validade<=soon)));
}
function field(label,control){const wrap=node('label',null,'filter-field');wrap.append(node('span',label),control);return wrap;}
function select(name,options,empty){
  const el=node('select');el.name=name;el.append(new Option(empty,''));
  options.forEach(([value,text])=>el.append(new Option(text,value)));el.value=filters[name]||'';return el;
}
function input(type,name,placeholder,data){
  const el=node('input');el.type=type;el.name=name;el.value=filters[name]||'';
  if(placeholder)el.placeholder=placeholder;
  if(type==='date'){el.min=data.periodo_total.inicio;el.max=data.periodo_total.fim;}
  return el;
}
function buildFilters(data){
  const keys=PAGE_FILTERS[page]; if(!keys||document.querySelector('.filters')) return;
  const form=node('form',null,'filters panel');form.setAttribute('aria-label','Filtros');
  const controls={
    inicio:()=>field('De',input('date','inicio',null,data)),
    fim:()=>field('Até',input('date','fim',null,data)),
    dia_semana:()=>field('Dia da semana',select('dia_semana',WEEKDAYS.map((d,i)=>[String(i+1),d]),'Todos os dias')),
    produto_id:()=>field('Sabor',select('produto_id',data.produtos.map(p=>[p.id,p.nome]),'Todos os sabores')),
    produto:()=>field('Sabor',select('produto',data.produtos.map(p=>[p.id,p.nome]),'Todos os sabores')),
    forma:()=>field('Pagamento',select('forma',data.formas_pagamento.map(f=>[f,PAYMENTS[f]||f]),'Todas as formas')),
    insumo:()=>field('Ingrediente',select('insumo',data.estoque.map(i=>[i.nome,i.nome]),'Todos os ingredientes')),
    situacao:()=>field('Situação',select('situacao',[['abaixo','Abaixo do mínimo'],['ok','No mínimo ou acima'],['vencido','Com lote vencido'],['vence','Vence em até 2 dias']],'Todas as situações')),
    busca:()=>field('Buscar',input('search','busca','Nome do ingrediente')),
    ingrediente:()=>field('Contém ingrediente',input('search','ingrediente','Ex.: muçarela')),
  };
  keys.forEach(k=>form.append(controls[k]()));
  const clear=node('button','Limpar filtros','button');clear.type='button';
  clear.addEventListener('click',()=>{
    const server=keys.some(k=>SERVER_FILTERS.includes(k)&&filters[k]);
    keys.forEach(k=>delete filters[k]);form.querySelectorAll('input,select').forEach(e=>{e.value='';});sync(server);
  });
  form.append(clear);
  form.addEventListener('submit',e=>e.preventDefault());
  form.addEventListener('change',e=>{if(e.target.type!=='search')update(e.target);});
  form.addEventListener('input',e=>{if(e.target.type==='search')update(e.target);});
  status.after(form);
}
function update(target){
  if(!target.name)return;
  if(target.value)filters[target.name]=target.value;else delete filters[target.name];
  if(filters.inicio&&filters.fim&&filters.inicio>filters.fim){status.textContent='A data inicial deve ser anterior ou igual à final.';return;}
  sync(SERVER_FILTERS.includes(target.name));
}
function sync(reload){
  const query=new URLSearchParams(Object.entries(filters).filter(([,v])=>v)).toString();
  history.replaceState(null,'',query?'?'+query:location.pathname);
  if(reload) load(1); else if(lastData) render(lastData);
}
async function load(pagina=1) {
  status.textContent='Consultando registros…';
  const query=new URLSearchParams({pagina});
  SERVER_FILTERS.forEach(k=>{if(filters[k]&&(PAGE_FILTERS[page]||[]).includes(k))query.set(k,filters[k]);});
  try {
    const response=await fetch('/demo/dados?'+query,{cache:'no-store'});
    if(response.status===422) throw new Error('Filtro inválido: confira as datas selecionadas.');
    if(!response.ok) throw new Error(response.status===403?'Os dados não estão disponíveis para este computador. No servidor, confira LOCAL_DEMO_OPERATION_ID e DEMO_ACESSO_REMOTO.':`Não foi possível consultar os dados (HTTP ${response.status}).`);
    const data=await response.json(); lastData=data;
    document.querySelector('.workspace strong').textContent=data.operacao.nome;
    document.querySelector('.demo-badge').textContent=data.contexto.parametros.natureza_dados==='simulados'?'DEMONSTRAÇÃO • DADOS SIMULADOS':'DADOS DA OPERAÇÃO';
    const active=(PAGE_FILTERS[page]||[]).filter(k=>filters[k]).length;
    status.textContent=`Período: ${date(data.periodo.inicio)} a ${date(data.periodo.fim)}${active?` • ${active} filtro(s) ativo(s)`:''}. Estoque: saldo atual. ${data.contexto.parametros.natureza_dados==='simulados'?'Registros simulados para demonstração.':''}`;
    const periodLabel=document.querySelector('.actions span.button');
    if(periodLabel) periodLabel.textContent=`${date(data.periodo.inicio)} – ${date(data.periodo.fim)}`;
    buildFilters(data);
    render(data);
  } catch(error) {root.replaceChildren();status.textContent=error.message;}
}
load();
