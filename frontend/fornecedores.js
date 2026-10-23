'use strict';
(() => {
  const root=document.getElementById('live-content'), status=document.getElementById('connection-status');
  const el=(tag,text,cls)=>Object.assign(document.createElement(tag),{textContent:text??'',className:cls||''});
  const money=n=>n==null?'Pendente':Number(n).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
  const num=n=>Number(n).toLocaleString('pt-BR',{maximumFractionDigits:3});
  const day=s=>s?new Date(s+'T12:00:00').toLocaleDateString('pt-BR'):'Não confirmada';
  const today=()=>new Date().toLocaleDateString('en-CA',{timeZone:'America/Sao_Paulo'});
  const errors={FORNECEDOR_DUPLICADO:'Já existe fornecedor com esse nome.',ESCRITA_LOCAL_INDISPONIVEL:'Cadastro permitido somente neste computador.',CADASTRO_NAO_ENCONTRADO:'Atualize a página e selecione um cadastro válido.'};
  function section(title,subtitle){const s=el('section',null,'panel live-panel');const h=el('div',null,'panel-head');const t=el('div');t.append(el('h2',title),el('p',subtitle));h.append(t);s.append(h);return s;}
  function table(headers,rows){const wrap=el('div',null,'table-scroll'),t=el('table'),head=el('thead'),tr=el('tr');headers.forEach(x=>tr.append(el('th',x)));head.append(tr);const body=el('tbody');for(const row of rows){const r=el('tr');row.forEach(x=>{const c=el('td');c.append(x instanceof Node?x:document.createTextNode(x??''));r.append(c);});body.append(r);}if(!rows.length){const r=el('tr'),c=el('td','Nenhum cadastro. Aguardando dados reais.');c.colSpan=headers.length;r.append(c);body.append(r);}t.append(head,body);wrap.append(t);return wrap;}
  function control(form,name,label,type='text',required=true){const l=el('label',label),i=el('input');i.name=name;i.type=type;i.required=required;if(type==='number'){i.min='0';i.step='0.01';}l.append(i);form.append(l);return i;}
  function select(form,name,label,options){const l=el('label',label),i=el('select');i.name=name;i.required=true;i.append(new Option('Selecione…',''));options.forEach(([v,t])=>i.append(new Option(t,v)));l.append(i);form.append(l);return i;}
  const expanded=new Set();
  function fold(title,content){const d=el('details',null,'content-fold');d.open=expanded.has(title);d.append(el('summary',title),content);d.addEventListener('toggle',()=>{if(d.open)expanded.add(title);else expanded.delete(title);});return d;}
  let data,ingredients=[],saving=false,selectedIngredient="";
  async function send(path,payload,method='POST'){
    const r=await fetch(path,{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const d=await r.json().catch(()=>({}));
    if(!r.ok)throw new Error(errors[d.detail?.codigo]||(r.status===422?'Confira campos, datas, valores e unidades.':`Não foi possível salvar (HTTP ${r.status}).`));return d;
  }
  function action(form,text,handler){const b=el('button',text,'button primary');b.type='submit';const msg=el('p',null,'wide');msg.setAttribute('role','status');form.append(b,msg);form.addEventListener('submit',async e=>{e.preventDefault();if(saving)return;saving=true;b.disabled=true;try{await handler(new FormData(form));msg.textContent='Salvo. Atualizando comparativo…';window.dispatchEvent(new Event('okto:cadastro'));await refresh();}catch(err){msg.textContent=err.message;}finally{saving=false;b.disabled=false;}});}
  function renderForms(){
    const supplier=section('Fornecedores','Cadastre pelo menos três fornecedores reais. Contatos não são enviados ao modelo de IA.');
    const f=el('form',null,'purchase-form');control(f,'nome','Nome');control(f,'contato','Contato (opcional)','text',false);
    action(f,'Cadastrar fornecedor',v=>send('/demo/fornecedores',{nome:v.get('nome'),contato:v.get('contato')}));supplier.append(f);
    const quotes=section('Nova cotação','Quantidade da embalagem na unidade-base do insumo (g, ml ou un). Deixe frete/prazo vazios se desconhecidos; isso impede indicar uma melhor oferta.');
    const q=el('form',null,'purchase-form');
    const suppliers=select(q,'fornecedor_id','Fornecedor',data.fornecedores.filter(f=>f.ativo).map(f=>[f.id,f.nome]));suppliers.dataset.suppliers='true';
    const ingredient=select(q,'insumo_id','Insumo / unidade',ingredients.map(i=>[i.id,`${i.nome} (${i.unidade})`]));
    const quantity=control(q,'quantidade_embalagem','Quantidade por embalagem','number');quantity.min='0.001';quantity.step='0.001';
    const price=control(q,'preco_embalagem','Preço por embalagem (R$)','number');price.min='0.01';
    const minimum=control(q,'minimo_embalagens','Pedido mínimo (embalagens)','number');minimum.step='1';minimum.min='1';
    control(q,'frete','Frete deste insumo (R$)','number',false);
    const lead=control(q,'prazo_dias','Prazo de entrega (dias)','number',false);lead.step='1';
    control(q,'cotado_em','Data da cotação','date').value=today();control(q,'valido_ate','Válida até','date');
    action(q,'Salvar cotação',v=>send('/demo/cotacoes',{
      fornecedor_id:v.get('fornecedor_id'),insumo_id:v.get('insumo_id'),quantidade_embalagem:v.get('quantidade_embalagem'),
      preco_embalagem:v.get('preco_embalagem'),minimo_embalagens:Number(v.get('minimo_embalagens')),
      frete:v.get('frete')===''?null:v.get('frete'),prazo_dias:v.get('prazo_dias')===''?null:Number(v.get('prazo_dias')),
      cotado_em:v.get('cotado_em'),valido_ate:v.get('valido_ate')
    }));quotes.append(q);
    const item=section('Cadastrar insumo real','O mínimo será calculado pelas fichas: metas de 250/1.000 porções prontas por sabor, somando ingredientes compartilhados e descontando os prontos.');
    const g=el('form',null,'purchase-form');control(g,'nome','Nome do insumo');select(g,'unidade','Unidade-base',[['g','Gramas (g)'],['ml','Mililitros (ml)'],['un','Unidades (un)']]);
    action(g,'Cadastrar insumo',async v=>{await send('/demo/insumos',{nome:v.get('nome'),unidade:v.get('unidade'),estoque_minimo:'0'});const r=await fetch('/demo/dados');if(r.ok){ingredients=(await r.json()).estoque;ingredient.replaceChildren(new Option('Selecione…',''));ingredients.forEach(i=>ingredient.append(new Option(`${i.nome} (${i.unidade})`,i.id)));}});
    item.append(g);root.append(fold('Cadastrar fornecedor',supplier),fold('Cadastrar cotação',quotes),fold('Cadastrar insumo',item));
  }
  const results=el('div');
  function renderResults(){
    const restoreFocus=document.activeElement?.id==='comparison-ingredient';
    results.replaceChildren();const n=data.fornecedores.filter(f=>f.ativo).length;
    status.textContent=`${n} fornecedor(es) ativo(s). ${n<3?`Faltam ${3-n} cadastros reais para comparar pelo menos três fornecedores.`:'Compare propostas válidas de cada insumo.'}`;
    const catalog=section('Fornecedores cadastrados','Desativar remove o fornecedor do comparativo sem apagar seu histórico.');
    catalog.append(table(['Fornecedor','Contato','Situação','Ação'],data.fornecedores.map(f=>{
      const button=el('button',f.ativo?'Desativar':'Reativar','button');button.type='button';button.onclick=async()=>{button.disabled=true;try{await send('/demo/fornecedores/'+f.id,{nome:f.nome,contato:f.contato,ativo:!f.ativo,simulado:f.simulado},'PUT');window.dispatchEvent(new Event('okto:cadastro'));await refresh();}catch(e){status.textContent=e.message;}finally{button.disabled=false;}};
      return[f.nome+(f.simulado?' • SIMULADO':''),f.contato||'Não informado',f.ativo?'Ativo':'Inativo',button];
    })));results.append(catalog);
    const compare=section(`Insumos para completar ${data.meta_por_sabor} porções de cada sabor`,data.criterio);
    compare.append(table(['Insumo','Saldo / mínimo conjunto','Falta','Menor total entregue','Fornecedor / prazo'],data.alertas.map(a=>{
      const q=a.melhor_oferta;return[a.nome,`${window.oktoQuantidade(a.saldo,a.unidade)} / ${window.oktoQuantidade(a.minimo,a.unidade)}`,`${window.oktoQuantidade(a.necessidade,a.unidade)}`,q?`${money(q.total_entregue)} · ${q.embalagens} embalagens`:'Sem proposta completa',q?`${q.fornecedor} · ${q.prazo_dias} dia(s)${q.simulado||q.fornecedor_simulado?' · SIMULADO':''}`:'Cadastrar cotação válida'];
    })));
    if(data.pendencias_fichas.length)compare.append(el('p','Fichas pendentes: '+data.pendencias_fichas.join(', ')+'. A cobertura só considera fichas validadas.','panel-body'));
    compare.append(el('p','Antes de comprar, confirme prazo, capacidade e validade. O frete é comparado por insumo; uma compra conjunta pode ter outro custo.','panel-body'));results.append(fold('Lista de reposição',compare));
    const detail=section('Comparativo de fornecedores','Selecione o insumo. A quantidade a pedir acompanha a necessidade atual do estoque.');
    detail.id='supplier-comparison';
    const controls=el('div',null,'purchase-form');
    const options=data.estoque || data.alertas;
    if(!options.some(a=>a.insumo_id===selectedIngredient))selectedIngredient=([...options].sort((a,b)=>(b.comparativo?.length||0)-(a.comparativo?.length||0))[0])?.insumo_id||'';
    const picker=select(controls,'comparativo_insumo','Insumo',options.map(a=>[a.insumo_id,a.nome]));
    picker.id='comparison-ingredient';picker.value=selectedIngredient;
    const needed=control(controls,'quantidade_pedido','Quantidade necessária a pedir','text',false);needed.readOnly=true;
    const offers=el('div');
    function showOffers(){
      selectedIngredient=picker.value;offers.replaceChildren();
      const a=options.find(a=>a.insumo_id===selectedIngredient);
      needed.value=a?window.oktoQuantidade(a.necessidade,a.unidade):'';
      if(!a)return;
      if(!a.comparativo?.length){offers.append(el('p',Number(a.necessidade)<=0?'Sem necessidade de reposição neste momento.':'Ainda não há preços cadastrados para este insumo.','panel-body'));return;}
      offers.append(table(['Fornecedor','Embalagem','Preço por embalagem','Preço por kg/L ou un','Embalagens a pedir','Quantidade entregue','Subtotal sem frete','Frete','Total entregue','Condição'],a.comparativo.filter(q=>q.ativo&&q.fornecedor_ativo).map(q=>[
        q.fornecedor,window.oktoQuantidade(q.quantidade_embalagem,a.unidade),money(q.preco_embalagem),
        money(Number(q.preco_por_unidade)*(a.unidade==='un'?1:1000)),num(q.embalagens),window.oktoQuantidade(q.quantidade_total,a.unidade),
        money(Number(q.embalagens)*Number(q.preco_embalagem)),money(q.frete),money(q.total_entregue),q.pendencias.join('; ')||'Elegível até '+day(q.valido_ate)
      ])));
      offers.append(el('p','As embalagens são arredondadas para atender à quantidade necessária. Referências públicas dependem de confirmação na loja; o subtotal não inclui frete.','panel-body'));
    }
    picker.addEventListener('change',showOffers);detail.append(controls,offers);results.prepend(detail);showOffers();if(restoreFocus)picker.focus({preventScroll:true});
    const refs=data.cotacoes.filter(q=>q.referencia_publica&&q.ativo&&q.fornecedor_ativo);
    if(refs.length){const ref=section('Preços públicos de referência','Redes presentes em Blumenau. Preço da loja/CEP, frete, mínimo e validade ainda não confirmados; não é cotação local aprovada.');
      ref.append(table(['Fornecedor','Produto/insumo','Embalagem','Preço publicado','Por kg/L','Consultado','Fonte'],refs.map(q=>{const a=el('a','Ver preço na fonte');a.href=q.fonte_url;a.target='_blank';a.rel='noopener noreferrer';return[q.fornecedor,q.insumo,`${window.oktoQuantidade(q.quantidade_embalagem,q.unidade)}`,money(q.preco_embalagem),money(Number(q.preco_embalagem)/Number(q.quantidade_embalagem)*(q.unidade==='un'?1:1000)),day(q.cotado_em),a];})));results.append(fold('Fontes e referências públicas',ref));}
    const history=section('Cotações registradas','Uma nova cotação para o mesmo fornecedor e insumo substitui a anterior; o histórico é preservado.');
    history.append(table(['Insumo','Fornecedor','Embalagem','Preço','Mínimo','Frete','Prazo','Validade','Situação'],data.cotacoes.map(q=>[q.insumo,q.fornecedor,`${window.oktoQuantidade(q.quantidade_embalagem,q.unidade)}`,money(q.preco_embalagem),q.minimo_embalagens??'Pendente',money(q.frete),q.prazo_dias==null?'Pendente':q.prazo_dias+' dia(s)',day(q.valido_ate),!q.ativo?'Substituída/inativa':q.referencia_publica?'Referência · confirmar loja e condições':!q.valido_ate?'Validade pendente':q.valido_ate<today()?'Vencida':q.cotado_em>today()?'Futura':'Ativa'])));results.append(fold('Histórico de cotações',history));
    const selectEl=root.querySelector('[data-suppliers]');if(selectEl){const value=selectEl.value;selectEl.replaceChildren(new Option('Selecione…',''));data.fornecedores.filter(f=>f.ativo).forEach(f=>selectEl.append(new Option(f.nome,f.id)));selectEl.value=value;}
  }
  async function refresh(){const r=await fetch('/demo/reposicao',{cache:'no-store'});if(!r.ok)throw new Error('Não foi possível consultar fornecedores.');data=await r.json();renderResults();}
  async function start(){try{
    const [r,d]=await Promise.all([fetch('/demo/reposicao'),fetch('/demo/dados')]);if(!r.ok||!d.ok)throw new Error('Não foi possível consultar a operação.');data=await r.json();const dashboard=await d.json();ingredients=dashboard.estoque;
    document.querySelector('.workspace strong').textContent=dashboard.operacao.nome;
    document.querySelector('.demo-badge').textContent=dashboard.contexto.parametros.natureza_dados==='simulados'?'DADOS SIMULADOS':'CADASTROS REAIS · OPERAÇÃO LOCAL';
    root.replaceChildren(results);renderForms();renderResults();
    window.addEventListener('okto:reposicao',e=>{data=e.detail;renderResults();});
  }catch(e){status.textContent=e.message;}}
  start();
})();
