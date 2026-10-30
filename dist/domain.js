export const ANCHOR = Date.parse('2026-10-30T12:00:00Z');
export const STATUSES = { investigating:'Investigando', identified:'Identificado', monitoring:'Em observação', resolved:'Resolvido' };
export const SERVICES = [
 {id:'api',name:'API de pedidos',group:'Aplicação',icon:'↗'},
 {id:'checkout',name:'Checkout',group:'Aplicação',icon:'▣'},
 {id:'queue',name:'Fila de notificações',group:'Infraestrutura',icon:'≋'},
 {id:'database',name:'Banco de dados',group:'Infraestrutura',icon:'▤'}
];
export function seed(){
 const observations=SERVICES.flatMap((s,j)=>Array.from({length:288},(_,i)=>({serviceId:s.id,at:ANCHOR-(287-i)*300000,ok:!(s.id==='checkout'&&i>=276||s.id==='queue'&&i>=140&&i<145),latency:85+j*22+(i*17%43)})));
 return {version:1, observations, incidents:[{id:'INC-1002',serviceId:'checkout',titleKey:'seedTitle2',title:'Lentidão na confirmação de compras',severity:'degraded',status:'investigating',createdAt:ANCHOR-3600000,updates:[{at:ANCHOR-3600000,status:'investigating',messageKey:'seedMessage3',message:'Tempo de resposta acima do esperado no cenário simulado.'}]},{id:'INC-1001',serviceId:'queue',titleKey:'seedTitle1',title:'Atraso no envio de notificações',severity:'outage',status:'resolved',createdAt:ANCHOR-44100000,updates:[{at:ANCHOR-44100000,status:'investigating',messageKey:'seedMessage1',message:'Acúmulo de mensagens detectado no cenário simulado.'},{at:ANCHOR-42600000,status:'resolved',messageKey:'seedMessage2',message:'Processamento normalizado. Fila de demonstração esvaziada.'}]}]};
}
export function metrics(observations,serviceId,hours=24,now=ANCHOR){
 const rows=observations.filter(o=>o.serviceId===serviceId&&o.at>now-hours*3600000&&o.at<=now).sort((a,b)=>a.at-b.at);
 const success=rows.filter(o=>o.ok);return {samples:rows.length, uptime:rows.length?success.length/rows.length*100:null,latency:success.length?Math.round(success.reduce((sum,o)=>sum+o.latency,0)/success.length):null, rows};
}
export function serviceStatus(state,id){const active=state.incidents.filter(i=>i.serviceId===id&&i.status!=='resolved');return active.some(i=>i.severity==='outage')?'outage':active.length?'degraded':'operational';}
export function createIncident(state,input,now=Date.now()){
 if(!SERVICES.some(s=>s.id===input.serviceId))throw new Error('Selecione um serviço válido.');
 if(!['degraded','outage'].includes(input.severity))throw new Error('Selecione um impacto válido.');
 const title=String(input.title||'').trim(),message=String(input.message||'').trim();
 if(title.length<5||title.length>100)throw new Error('O título precisa ter entre 5 e 100 caracteres.');
 if(message.length<10||message.length>600)throw new Error('A descrição precisa ter entre 10 e 600 caracteres.');
 if(state.incidents.some(i=>i.serviceId===input.serviceId&&i.status!=='resolved'))throw new Error('Este serviço já tem um incidente aberto. Atualize o incidente existente.');
 const id=`INC-${Math.max(1000,...state.incidents.map(i=>Number(i.id.slice(4))||0))+1}`;
 return {...state,incidents:[{id,serviceId:input.serviceId,title,severity:input.severity,status:'investigating',createdAt:now,updates:[{at:now,status:'investigating',message}]},...state.incidents]};
}
export function updateIncident(state,id,status,message,now=Date.now()){
 const incident=state.incidents.find(i=>i.id===id);if(!incident)throw new Error('Incidente não encontrado.');
 if(incident.status==='resolved')throw new Error('Um incidente resolvido não pode ser alterado.');
 if(!Object.hasOwn(STATUSES,status))throw new Error('Status inválido.');
 message=String(message||'').trim();if(message.length<10||message.length>600)throw new Error('A atualização precisa ter entre 10 e 600 caracteres.');
 if(now<incident.updates.at(-1).at)throw new Error('A atualização não pode anteceder a anterior.');
 return {...state,incidents:state.incidents.map(i=>i.id===id?{...i,status,updates:[...i.updates,{at:now,status,message}]}:i)};
}
export function validState(s){
 const timestamp=v=>Number.isFinite(v)&&Math.abs(v)<=8640000000000000;
 return !!s&&s.version===1&&Array.isArray(s.observations)&&s.observations.length===1152&&s.observations.every(o=>o&&SERVICES.some(x=>x.id===o.serviceId)&&timestamp(o.at)&&typeof o.ok==='boolean'&&Number.isFinite(o.latency)&&o.latency>=0)&&Array.isArray(s.incidents)&&new Set(s.incidents.map(i=>i?.id)).size===s.incidents.length&&s.incidents.every(i=>i&&typeof i.id==='string'&&/^INC-\d+$/.test(i.id)&&typeof i.title==='string'&&i.title.length>=5&&i.title.length<=100&&SERVICES.some(x=>x.id===i.serviceId)&&['degraded','outage'].includes(i.severity)&&Object.hasOwn(STATUSES,i.status)&&timestamp(i.createdAt)&&Array.isArray(i.updates)&&i.updates.length&&i.updates.every((u,n)=>u&&timestamp(u.at)&&u.at>=i.createdAt&&(n===0||u.at>=i.updates[n-1].at)&&typeof u.message==='string'&&u.message.length>=10&&u.message.length<=600&&Object.hasOwn(STATUSES,u.status))&&i.updates.at(-1).status===i.status);
}
