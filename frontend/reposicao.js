'use strict';
// Alertas determinísticos persistidos no servidor. Uma conexão SSE por página.
(() => {
  const el = (tag, text, cls) => Object.assign(document.createElement(tag), {textContent:text || '', className:cls || ''});
  const fmt = n => Number(n).toLocaleString('pt-BR',{maximumFractionDigits:3});
  const brl = n => Number(n).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
  const nav = document.querySelector('nav[aria-label="Menu principal"]');
  if (nav && !nav.querySelector('[href="fornecedores.html"]')) {
    const a=el('a','Fornecedores e compras'); a.href='fornecedores.html';
    if(location.pathname.endsWith('/fornecedores.html')) a.setAttribute('aria-current','page'); nav.append(a);
  }
  const notice=el('section',null,'replenishment-notice'); notice.setAttribute('aria-label','Alertas automáticos do Otto');
  const title=el('strong','Otto · reposição automática');
  const state=el('p','Conectando ao monitor de estoque…'); state.setAttribute('role','status');
  const details=el('details'); const summary=el('summary','Ver mensagens'); const list=el('div');details.append(summary,list);
  const link=el('a','Consultar fornecedores e cotações →');link.href='fornecedores.html';
  notice.append(title,state,details,link);
  const anchor=document.querySelector('.heading'); if(anchor)anchor.after(notice);
  let loading=false, pending=false;
  let seen=new Set();
  try {seen=new Set(JSON.parse(sessionStorage.getItem('okto-alertas-vistos')||'[]'));}catch{}
  async function refresh() {
    if(loading){pending=true;return;} loading=true;
    try {
      const response=await fetch('/demo/reposicao',{cache:'no-store'});
      if(!response.ok)throw new Error(`HTTP ${response.status}`);
      const data=await response.json();list.replaceChildren();
      const ready=data.prontos;const controlled=data.politica?.controle_prontos;
      const missing=controlled?ready.contagens_pendentes:data.pendencias_fichas;
      const alerts=controlled?ready.alertas:data.alertas;
      state.textContent=controlled?`${alerts.length} sabor(es) abaixo de 30%. Meta hoje: ${data.meta_por_sabor} por sabor; alerta abaixo de ${data.meta_por_sabor*.3}.`:`${alerts.length} insumo(s) com necessidade de reposição.`;
      if(controlled&&missing.length===ready.sabores.length&&missing.length)state.textContent=`Aguardando contagem física dos ${missing.length} sabores. Meta hoje: ${data.meta_por_sabor} por sabor; alerta abaixo de ${data.meta_por_sabor*.3}.`;
      state.textContent+=` Atualizado às ${new Date(data.gerado_em).toLocaleTimeString('pt-BR',{timeZone:'America/Sao_Paulo'})}.`;
      if(missing.length){state.textContent+=` ${missing.length} ${controlled?'contagem(ns) física(s)':'ficha(s)'} pendente(s).`;list.append(el('p',`Aguardando ${controlled?'contagem de porções realmente prontas':'fichas'}: ${missing.join(', ')}.`));}
      for(const a of alerts){
        let text;
        if(controlled) text=`${a.nome}: ${fmt(a.saldo)} porções prontas (${fmt(a.percentual_disponivel)}% da meta de ${a.meta}). Abaixo de ${fmt(a.limite_alerta)}. Faltam ${fmt(a.repor_ate_meta)} para completar a meta. Confira ingredientes e capacidade antes de produzir.`;
        else text=`${a.nome}: saldo ${window.oktoQuantidade(a.saldo,a.unidade)}; falta ${window.oktoQuantidade(a.necessidade,a.unidade)} para completar a meta.`;
        list.append(el('p',text,'replenishment-message'));
        if(a.alerta&&!seen.has(a.alerta.id)){seen.add(a.alerta.id);details.open=true;}
      }
      if(controlled) list.append(el('p',`Planejamento de compras: ${data.alertas.length} insumo(s) sem saldo suficiente para completar as metas. Consulte preços e condições em Fornecedores.`));
      if(!alerts.length&&!missing.length)list.append(el('p','Nenhum sabor está abaixo do limite de alerta de 30%.'));
      summary.textContent=`Mensagens do Otto (${alerts.length+missing.length})`;
      try{sessionStorage.setItem('okto-alertas-vistos',JSON.stringify([...seen].slice(-500)));}catch{}
      window.dispatchEvent(new CustomEvent('okto:reposicao',{detail:data}));
    }catch{state.textContent='Monitor indisponível: os dados exibidos podem estar desatualizados. Reconectando automaticamente…';}
    finally{loading=false;if(pending){pending=false;refresh();}}
  }
  function update(){refresh();window.dispatchEvent(new Event('okto:estoque'));}
  if('EventSource' in window){
    const events=new EventSource('/demo/eventos');
    events.addEventListener('pronto',update);
    events.addEventListener('mudanca',update);
    events.addEventListener('lotado',()=>events.close());
    events.onerror=()=>{state.textContent='Conexão ao vivo interrompida; tentando reconectar e consultando a cada 15 segundos.';};
    window.addEventListener('pagehide',()=>events.close(),{once:true});
  }
  window.addEventListener('okto:cadastro',update);
  setInterval(update,15000);refresh();
})();
