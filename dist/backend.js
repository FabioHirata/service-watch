/** Same-origin API transport. Never accepts destinations or credentials from the UI. */
export class ApiError extends Error {
 constructor(code='unavailable'){super(code);this.code=code;}
}
export function isApiMode(search=''){return new URLSearchParams(search).get('mode')==='api';}
export function validateSnapshot(data){
 if(!data||data.mode!=='api'||!Number.isFinite(data.now)||!Array.isArray(data.services)||!Array.isArray(data.observations)||!Array.isArray(data.incidents)||!data.metrics)throw new ApiError('unavailable');
 const ids=['api','checkout','queue','database'];
 if(data.services.length!==4||!ids.every(id=>data.services.some(s=>s.id===id)))throw new ApiError('unavailable');
 for(const id of ids){const m=data.metrics[id];if(!m||!Number.isInteger(m.samples)||m.samples<0||(m.uptime!==null&&(!Number.isFinite(m.uptime)||m.uptime<0||m.uptime>100))||(m.latency!==null&&(!Number.isFinite(m.latency)||m.latency<0)))throw new ApiError('unavailable');}
 const status=['investigating','identified','monitoring','resolved'];
 if(data.observations.some(o=>!o||!ids.includes(o.serviceId)||!Number.isFinite(o.at)||typeof o.ok!=='boolean'||(o.ok&&!Number.isFinite(o.latency))))throw new ApiError('unavailable');
 if(data.incidents.some(i=>!i||!/^INC-\d+$/.test(i.id)||!ids.includes(i.serviceId)||typeof i.title!=='string'||!['degraded','outage'].includes(i.severity)||!status.includes(i.status)||!Number.isFinite(i.createdAt)||!Array.isArray(i.updates)||i.updates.some(u=>!u||!Number.isFinite(u.at)||!status.includes(u.status)||typeof u.message!=='string')))throw new ApiError('unavailable');
 return data;
}
export function makeApiClient(fetcher=globalThis.fetch){
 async function request(path,body){const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),30000);try{const response=await fetcher(path,{method:body===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal:controller.signal});const data=await response.json();if(!response.ok)throw new ApiError(typeof data.error==='string'?data.error:'unavailable');return validateSnapshot(data);}catch(error){if(error instanceof ApiError)throw error;throw new ApiError('unavailable');}finally{clearTimeout(timer);}}
 const suffix=hours=>`?hours=${[1,6,24].includes(Number(hours))?Number(hours):24}`;
 return {state:hours=>request('/api/state'+suffix(hours)),collect:hours=>request('/api/collect'+suffix(hours),{}),create:(input,hours)=>request('/api/incidents'+suffix(hours),input),update:(id,input,hours)=>{if(!/^INC-\d+$/.test(id))return Promise.reject(new ApiError('not_found'));return request('/api/incidents/'+encodeURIComponent(id)+'/updates'+suffix(hours),input);}};
}
export function observedStatus(state,id){
 const active=state.incidents.filter(i=>i.serviceId===id&&i.status!=='resolved');
 if(active.some(i=>i.severity==='outage'))return 'outage';
 const latest=state.observations.filter(o=>o.serviceId===id).sort((a,b)=>b.at-a.at)[0];
 if(latest&&!latest.ok)return 'outage';
 if(active.length)return 'degraded';
 return latest?'operational':'unknown';
}
