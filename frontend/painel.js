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
function fold(title,content){const d=node('details',null,'content-fold');d.append(node('summary',title),content);return d;}
function stockTable(rows) {
  return table(['Ingrediente','Saldo utilizável','Vencido','Insumos para completar a meta','Validade mais próxima'],rows.map(i => [i.nome,window.oktoQuantidade(i.saldo,i.unidade),window.oktoQuantidade(i.vencido,i.unidade),i.minimo_50_por_sabor==null?'Aguardando ficha':window.oktoQuantidade(i.minimo_50_por_sabor,i.unidade),date(i.validade)]));
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
  if(['index','producao'].includes(page)&&data.prontos?.sabores.length&&window.oktoReadyPanel)root.append(window.oktoReadyPanel(data.prontos));
  if(page==='index') {
    const shortcuts=node('div',null,'operation-shortcuts');
    [['producao.html','Produção','Prontos e novos lotes'],['fornecedores.html','Compras','Reposição e fornecedores'],['perdas.html','Perdas','Descarte e custo'],['dashboard.html','Resultados','Indicadores da operação']].forEach(([href,title,description])=>{const link=node('a',null,'operation-shortcut');link.href=href;link.append(node('strong',title),node('span',description));shortcuts.append(link);});
    root.append(shortcuts);
  }
  if(page==='vendas') {
    root.append(metrics([['Receita',money(r.receita),'Vendas confirmadas'],['Porções vendidas',number(r.porcoes),number(r.vendas)+' vendas']]));
    const sales=panel('Vendas registradas',`Página ${data.pagina} de ${data.paginas}`);
    sales.append(table(['Data','Hora','Itens','Pagamento','Valor','Status'],data.vendas.map(v=>[date(v.criado_em),hour(v.criado_em),v.itens,(v.pagamento||'').split(', ').map(f=>PAYMENTS[f]||f).join(', '),money(v.total),v.status])));
    const nav=node('div',null,'panel-body');[['Anterior',data.pagina-1],['Próxima',data.pagina+1]].forEach(([title,p])=>{const b=node('button',title,'button');b.disabled=p<1||p>data.paginas;b.onclick=()=>load(p);nav.append(b);});sales.append(nav);root.append(sales);
    root.append(fold('Vendas por dia',daily(data)),fold('Desempenho por sabor',ranking(data)));
  }
  if(page==='estoque') {
    if(window.oktoReceiptEditor)root.append(window.oktoReceiptEditor(data.estoque));
    const rows=filteredStock(data.estoque);
    root.append(metrics([['Insumos',number(data.estoque.length),'Ingredientes cadastrados'],['Abaixo do mínimo',number(data.estoque.filter(i=>i.minimo_50_por_sabor!=null&&Number(i.saldo)<Number(i.minimo_50_por_sabor)).length),'Planejamento de insumos para completar a meta de porções prontas']]));
    const s=panel('Estoque por ingrediente',`${rows.length} de ${data.estoque.length} ingredientes • quantidades em g/kg, ml/L ou un • lotes vencidos separados do saldo utilizável`);s.append(stockTable(rows));root.append(s);
  }
  if(page==='receitas') {
    const cards=node('div',null,'cards live-recipes');
    const recipes=data.produtos.filter(p=>(!filters.produto||p.id===filters.produto)&&(!filters.ingrediente||p.ingredientes.some(i=>matches(i.nome,filters.ingrediente))));
    recipes.forEach(p=>{
      const s=panel(p.nome,`Versão ${p.versao} • ${p.ativo?'Ficha validada':'Aguardando receita real / validação'}`);
      const details=p.ficha_detalhes||{};
      if(details.foto){
        const figure=node('figure',null,'recipe-photo');const img=document.createElement('img');
        img.src='assets/batatas/'+details.foto;img.alt='Foto ilustrativa de batata recheada: '+p.nome;img.loading='lazy';
        const caption=node('figcaption','Foto de referência · ');const credit=node('a',details.credito||'Fonte');credit.href=details.foto_fonte;credit.target='_blank';credit.rel='noopener noreferrer';caption.append(credit);figure.append(img,caption);s.prepend(figure);
      }
      const body=node('div',null,'panel-body');body.append(node('p','Rendimento: 1 porção · ficha fornecida pelo responsável.'));
      body.append(node('p','Preço de venda: '+money(p.preco)));
      body.append(node('p','Custo estimado dos ingredientes: '+money(p.custo_estimado)));
      body.append(node('p','Estimativa pelo último custo cadastrado; exclui mão de obra, impostos e embalagem.','subtext'));
      if(details.batata_bruta_g)body.append(node('p','Batata: 450 g bruta → 380 g utilizável · perda de limpeza 15,56% · fator de correção 1,184211.'));
      if(details.alergenicos)body.append(node('p','Alergênicos: '+details.alergenicos));
      if(details.atributos)body.append(node('p',details.atributos));
      if(p.ficha_detalhes?.preparo) body.append(node('p','Preparo: '+p.ficha_detalhes.preparo));
      if(p.ficha_detalhes?.observacoes) body.append(node('p',p.ficha_detalhes.observacoes));
      if(!p.ingredientes.length)body.append(node('p','Quantidades, rendimento e preparo aguardam informação do responsável. Nenhum ingrediente foi presumido.'));
      const detailBody=node('div');detailBody.append(body,table(['Ingrediente','Quantidade por porção'],p.ingredientes.map(i=>[i.nome,window.oktoQuantidade(i.quantidade,i.unidade)+(i.nome==='Batata inglesa'?' bruta / 380 g líquida':'')])));s.append(fold('Ver ficha técnica',detailBody));if(details.foto){const download=node('a','Baixar imagem com a ficha técnica','button recipe-download');download.href='assets/fichas/'+details.foto.replace(/\.[^.]+$/,'.png');download.download='Ficha-'+p.nome+'.png';s.append(download);}
      if(!p.ativo && window.oktoRecipeEditor)s.append(window.oktoRecipeEditor(p,data.estoque));cards.append(s);
    });
    if(!recipes.length)cards.append(node('p',data.produtos.length?'Nenhuma ficha corresponde aos filtros.':'Nenhuma ficha cadastrada.'));root.append(cards);
  }
  if(page==='perdas') {
    const l=data.perdas;
    root.append(metrics([['Custo total das perdas',money(l.custo_total_perdas),'Custos históricos dos lotes'],['Sobre a receita',l.percentual_sobre_receita_confirmada==null?'—':number(l.percentual_sobre_receita_confirmada)+'%','Perdas ÷ receita confirmada'],['Porções descartadas',number(l.porcoes_perdidas_registradas),'Descarte de insumos não é contado como porção']]));
    const byRecipe=panel('Perdas por receita','Descartes sem receita não são atribuídos a sabores');byRecipe.id='perdas-por-receita';
    byRecipe.append(table(['Receita','Porções','Custo'],l.por_receita.map(i=>[i.nome,number(i.porcoes_registradas),money(i.custo)])));
    const lossItems=l.por_insumo.filter(i=>!filters.insumo||i.nome===filters.insumo), lossRows=l.registros.filter(i=>!filters.insumo||i.insumo===filters.insumo);
    const byItem=panel('Perdas por ingrediente'); byItem.append(table(['Ingrediente','Quantidade','Custo'],lossItems.map(i=>[i.nome,window.oktoQuantidade(i.quantidade,i.unidade),money(i.custo)])));
    const history=panel('Histórico de perdas',`${lossRows.length} movimentos no período`);history.append(table(['Data','Ingrediente','Quantidade','Motivo','Custo'],lossRows.map(i=>[date(i.criado_em),i.insumo,window.oktoQuantidade(i.quantidade,i.unidade),i.motivo,money(i.custo)])));
    if(window.oktoReadyForms)root.append(window.oktoReadyForms(data.prontos,data.produtos,{onlyDiscard:true}));
    root.append(byRecipe,fold('Detalhar ingredientes',byItem),fold('Histórico de perdas',history));
    if(l.perdas_prontas?.length){const ready=panel('Descarte de porções prontas','Custo do lote pronto; sem repetir baixa de ingredientes');ready.append(table(['Data','Sabor','Porções','Motivo','Custo'],l.perdas_prontas.map(x=>[date(x.criado_em),x.produto_nome,number(x.porcoes),x.motivo,money(x.custo)])));root.append(ready);}
  }
  if(page==='producao') {
    if(window.oktoReadyForms)root.append(window.oktoReadyForms(data.prontos,data.produtos));
    const s=panel('Lotes prontos');
    s.append(table(['Sabor','Lote','Saldo pronto','Validade'],data.prontos.lotes.map(l=>[l.nome,l.codigo,number(l.saldo),date(l.validade)+' '+hour(l.validade)])));if(data.prontos.lotes.length)root.append(fold(`Lotes registrados (${data.prontos.lotes.length})`,s));
  }
}
// Filtros: os do servidor recarregam os dados; os do navegador só redesenham a tela.
const SERVER_FILTERS=['inicio','fim','dia_semana','produto_id','forma'];
const PAGE_FILTERS={
  index:[],
  vendas:['inicio','fim','dia_semana','produto_id','forma'],
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
    !filters.situacao||(filters.situacao==='abaixo'&&i.minimo_50_por_sabor!=null&&Number(i.saldo)<Number(i.minimo_50_por_sabor))
    ||(filters.situacao==='ok'&&i.minimo_50_por_sabor!=null&&Number(i.saldo)>=Number(i.minimo_50_por_sabor))
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
  const keys=PAGE_FILTERS[page]; if(!keys?.length||document.querySelector('.filters')) return;
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
  // Barra recolhível: abre sozinha quando a página já chega com filtros ativos.
  const toggle=node('details',null,'filters-toggle');
  toggle.append(node('summary'),form);
  toggle.open=keys.some(k=>filters[k]);
  status.after(toggle);
  filterSummary();
}
function filterSummary(){
  const summary=document.querySelector('.filters-toggle > summary'); if(!summary)return;
  const active=(PAGE_FILTERS[page]||[]).filter(k=>filters[k]).length;
  summary.textContent=active?`Filtros (${active} ativo${active>1?'s':''})`:'Filtros';
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
  filterSummary();
  if(reload) load(1); else if(lastData) render(lastData);
}
function editingForm(){return document.querySelector('.recipe-editor[open], .stock-editor[open], .ready-editor form[data-dirty="true"]') || document.activeElement?.closest('.recipe-editor');}
async function load(pagina=1,automatic=false) {
  if(automatic&&editingForm())return;
  status.textContent='Consultando registros…';
  const query=new URLSearchParams({pagina});
  SERVER_FILTERS.forEach(k=>{if(filters[k]&&(PAGE_FILTERS[page]||[]).includes(k))query.set(k,filters[k]);});
  try {
    const response=await fetch('/demo/dados?'+query,{cache:'no-store'});
    if(response.status===422) throw new Error('Filtro inválido: confira as datas selecionadas.');
    if(!response.ok) throw new Error(response.status===403?'Os dados não estão disponíveis para este computador. No servidor, confira LOCAL_DEMO_OPERATION_ID e DEMO_ACESSO_REMOTO.':`Não foi possível consultar os dados (HTTP ${response.status}).`);
    const data=await response.json();
    if(automatic&&editingForm())return;
    lastData=data;
    document.querySelector('.workspace strong').textContent=data.operacao.nome;
    document.querySelector('.demo-badge').textContent=data.contexto.parametros.natureza_dados==='simulados'?'DEMONSTRAÇÃO • DADOS SIMULADOS':'DADOS DA OPERAÇÃO';
    const active=(PAGE_FILTERS[page]||[]).filter(k=>filters[k]).length;
    status.textContent=['vendas','perdas'].includes(page)?`${date(data.periodo.inicio)} a ${date(data.periodo.fim)}${active?` · ${active} filtro(s)`:''}`:'Atualizado às '+new Date().toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'});
    const periodLabel=document.querySelector('.actions span.button');
    if(periodLabel) periodLabel.textContent=`${date(data.periodo.inicio)} – ${date(data.periodo.fim)}`;
    buildFilters(data);
    render(data);
  } catch(error) {if(automatic&&editingForm())return;root.replaceChildren();status.textContent=error.message;}
}
load();

// Um evento do PostgreSQL atualiza estoque e fichas; não interrompe formulários em edição.
let liveReload;
window.addEventListener('okto:estoque',()=>{
  if(document.querySelector('.recipe-editor[open], .stock-editor[open], .ready-editor form[data-dirty="true"]') || document.activeElement?.closest('.recipe-editor'))return;
  clearTimeout(liveReload);liveReload=setTimeout(()=>load(lastData?.pagina||1,true),250);
});
