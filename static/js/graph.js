const PROVIDER_COLORS={aws:'#FF9900',azure:'#0078D4',gcp:'#4285F4'};
const ENV_COLORS={prd:'#22c55e',stg:'#eab308',dev:'#3b82f6',global:'#a855f7',other:'#64748b'};
// Maps both long names (from resource_type) and short icon keys (from builder)
const TYPE_COLORS={
  vnet:'#3b82f6',virtual_network:'#3b82f6',
  firewall:'#ef4444',
  nsg:'#ef4444',security_group:'#ef4444',
  lb:'#06b6d4',load_balancer:'#06b6d4',
  nat:'#f59e0b',nat_gateway:'#f59e0b',
  vpngw:'#f97316',vpn_gateway:'#f97316',
  pe:'#a855f7',private_endpoint:'#a855f7',
  pip:'#14b8a6',public_ip:'#14b8a6',
  dns:'#8b5cf6',dns_zone:'#8b5cf6',
  bastion:'#64748b',
  er:'#eab308',express_route:'#eab308',
  waf:'#ec4899',
  nic:'#6366f1',network_interface:'#6366f1'
};
const TYPE_LABELS={
  vnet:'Network',virtual_network:'Network',
  firewall:'Firewall',
  nsg:'Security Group',security_group:'Security Group',
  lb:'Load Balancer',load_balancer:'Load Balancer',
  nat:'NAT Gateway',nat_gateway:'NAT Gateway',
  vpngw:'VPN Gateway',vpn_gateway:'VPN Gateway',
  pe:'Private Endpoint',private_endpoint:'Private Endpoint',
  pip:'Public IP',public_ip:'Public IP',
  dns:'DNS Zone',dns_zone:'DNS Zone',
  bastion:'Bastion',
  er:'Express Route',express_route:'Express Route',
  waf:'WAF',
  nic:'NIC',network_interface:'NIC'
};
const KEY_TYPES=new Set(['firewall','lb','load_balancer','vpngw','vpn_gateway','bastion','er','express_route','nat','nat_gateway','waf','dns','dns_zone']);

let D=null,simulation=null,svg=null,g=null,curEnv='all',searchQ='',isDark=true,_incSev='high';
const esc=s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

function buildGraph(data){
  const nodes=[],links=[],nodeMap={};
  const products=[...new Set((data.networks||[]).map(v=>v.product||'other'))].sort();
  const pidx={};products.forEach((p,i)=>pidx[p]=i);
  const PCOLS=['#3b82f6','#22c55e','#f59e0b','#ef4444','#a855f7','#06b6d4','#ec4899','#f97316','#14b8a6','#8b5cf6'];

  for(const v of (data.networks||[])){
    const rc=(v.resources||[]).length+(v.securityGroups||[]).length;
    const prod=v.product||'other';
    const pcol=PCOLS[(pidx[prod]||0)%PCOLS.length];
    const provCol=PROVIDER_COLORS[v.provider]||pcol;
    const n={id:v.id,type:'network',label:v.name,env:v.env||'other',icon:'vnet',
      radius:Math.max(28,Math.min(50,20+rc*2)),product:prod,productColor:pcol,providerColor:provCol,
      provider:v.provider||'',isExternal:v.isExternal||false,meta:v,
      searchText:(v.name+' '+v.env+' '+(v.region||'')+' '+(v.provider||'')+' '+(v.addressSpace||[]).join(' ')+' '+prod).toLowerCase()};
    nodes.push(n);nodeMap[v.id]=n;

    const allRes=[...(v.resources||[]),...(v.securityGroups||[]).map(s=>({...s,resource_type:'security_group'}))];
    const keyRes=allRes.filter(r=>KEY_TYPES.has(r.resource_type||r.icon));
    for(const r of keyRes){
      const rid=r.id||`${v.id}_${r.name}`;
      const rn={id:rid,type:'resource',label:r.name,env:r.env||v.env,icon:r.resource_type||r.icon||'other',
        radius:16,parentNet:v.id,product:prod,productColor:pcol,providerColor:provCol,
        provider:r.provider||v.provider,typeName:TYPE_LABELS[r.resource_type]||r.resource_type,meta:r,
        searchText:(r.name+' '+(r.resource_type||'')+' '+prod).toLowerCase()};
      nodes.push(rn);nodeMap[rid]=rn;
      links.push({source:v.id,target:rid,type:'contains',label:r.subnet||''});
    }
    const minor={};
    allRes.filter(r=>!KEY_TYPES.has(r.resource_type||r.icon)).forEach(r=>{
      const k=r.resource_type||r.icon||'other';
      if(!minor[k])minor[k]={icon:k,label:TYPE_LABELS[k]||k,count:0,names:[]};
      minor[k].count++;minor[k].names.push(r.name);
    });
    for(const[k,grp] of Object.entries(minor)){
      const gid=`${v.id}_grp_${k}`;
      nodes.push({id:gid,type:'group',label:`${grp.count} ${grp.label}`,env:v.env,icon:k,radius:12,
        parentNet:v.id,product:prod,productColor:pcol,providerColor:provCol,count:grp.count,names:grp.names,
        searchText:(grp.names.join(' ')+' '+prod).toLowerCase()});
      nodeMap[gid]={id:gid};
      links.push({source:v.id,target:gid,type:'contains'});
    }
  }
  for(const p of (data.peerings||[])){
    if(nodeMap[p.source_network||p.fromId]&&nodeMap[p.target_network||p.toId])
      links.push({source:p.source_network||p.fromId,target:p.target_network||p.toId,type:'peering',
        label:p.name,state:p.state,id:p.id});
  }
  return {nodes,links,products};
}

function renderGraph(gd){
  const wrap=document.getElementById('graph-wrap');
  const W=wrap.clientWidth,H=wrap.clientHeight,CX=W/2,CY=H/2;
  d3.select('#graph-wrap svg').remove();
  svg=d3.select('#graph-wrap').append('svg').attr('width',W).attr('height',H);
  const defs=svg.append('defs');
  [['arrow-ok','#22c55e'],['arrow-bad','#ef4444']].forEach(([id,col])=>{
    defs.append('marker').attr('id',id).attr('viewBox','0 0 10 7').attr('refX',10).attr('refY',3.5)
      .attr('markerWidth',7).attr('markerHeight',5).attr('orient','auto')
      .append('path').attr('d','M0,0 L10,3.5 L0,7 Z').attr('fill',col).attr('opacity',.7);
  });
  const glow=defs.append('filter').attr('id','glow').attr('x','-50%').attr('y','-50%').attr('width','200%').attr('height','200%');
  glow.append('feGaussianBlur').attr('stdDeviation','4').attr('result','blur');
  glow.append('feMerge').selectAll('feMergeNode').data(['blur','SourceGraphic']).join('feMergeNode').attr('in',d=>d);
  const zoom=d3.zoom().scaleExtent([0.05,5]).on('zoom',e=>g.attr('transform',e.transform));
  svg.call(zoom);g=svg.append('g');

  const prods=gd.products||[];
  const prodPos={};const cr=Math.min(W,H)*0.35;
  prods.forEach((p,i)=>{const a=(2*Math.PI*i/prods.length)-Math.PI/2;prodPos[p]={x:CX+cr*Math.cos(a),y:CY+cr*Math.sin(a)};});

  const link=g.append('g').selectAll('path').data(gd.links).join('path').attr('fill','none')
    .attr('stroke',d=>d.type==='peering'?(d.state==='connected'||d.state==='Connected'||d.state==='active'?'#22c55e':'#ef4444'):'#2e3348')
    .attr('stroke-width',d=>d.type==='peering'?2.5:1).attr('stroke-opacity',d=>d.type==='peering'?.6:.15)
    .attr('stroke-dasharray',d=>(d.type==='peering'&&d.state!=='connected'&&d.state!=='Connected'&&d.state!=='active')?'6 3':null)
    .attr('marker-end',d=>d.type==='peering'?(d.state==='connected'||d.state==='Connected'||d.state==='active'?'url(#arrow-ok)':'url(#arrow-bad)'):null);

  const node=g.append('g').selectAll('g').data(gd.nodes).join('g').attr('cursor','pointer')
    .call(d3.drag().on('start',(e,d)=>{if(!e.active)simulation.alphaTarget(.1).restart();d.fx=d.x;d.fy=d.y;})
      .on('drag',(e,d)=>{d.fx=e.x;d.fy=e.y;}).on('end',(e,d)=>{if(!e.active)simulation.alphaTarget(0);d.fx=d.x;d.fy=d.y;}));

  node.append('circle').attr('class','node-outer').attr('r',d=>d.radius)
    .attr('fill',d=>((d.providerColor||d.productColor||'#3b82f6')+'18'))
    .attr('stroke',d=>d.providerColor||d.productColor||'#3b82f6')
    .attr('stroke-width',d=>d.type==='network'?2.5:1.5).attr('filter',d=>d.type==='network'?'url(#glow)':null);
  const icons={
    vnet:'\u25C8',virtual_network:'\u25C8',
    firewall:'\u2737',
    nsg:'\u26D4',security_group:'\u26D4',
    lb:'\u2696',load_balancer:'\u2696',
    nat:'\u27A1',nat_gateway:'\u27A1',
    vpngw:'\u25B2',vpn_gateway:'\u25B2',
    pe:'\u26BF',private_endpoint:'\u26BF',
    pip:'IP',public_ip:'IP',
    dns:'D',dns_zone:'D',
    bastion:'\u2616',
    er:'\u26A1',express_route:'\u26A1',
    waf:'\u2694',
    nic:'\u2630',network_interface:'\u2630'
  };
  node.append('text').text(d=>icons[d.icon]||'?').attr('text-anchor','middle').attr('dy',d=>d.type==='network'?5:3)
    .attr('font-size',d=>d.type==='network'?16:11).attr('fill',d=>TYPE_COLORS[d.icon]||'#94a3b8').attr('font-weight',700).attr('pointer-events','none');
  node.append('text').attr('class','node-label').attr('dy',d=>d.radius+12).attr('text-anchor','middle')
    .attr('font-size',d=>d.type==='network'?10:8).attr('font-weight',d=>d.type==='network'?700:500)
    .attr('fill',isDark?'#e2e8f0':'#1e293b').attr('font-family','Inter,sans-serif')
    .text(d=>d.label&&d.label.length>24?d.label.slice(0,23)+'\u2026':d.label||'').attr('pointer-events','none');
  // Provider badge
  node.filter(d=>d.type==='network'&&d.provider).append('circle').attr('cx',d=>d.radius*.7).attr('cy',d=>-d.radius*.7)
    .attr('r',6).attr('fill',d=>PROVIDER_COLORS[d.provider]||'#64748b');
  node.filter(d=>d.type==='network'&&d.provider).append('text').attr('x',d=>d.radius*.7).attr('y',d=>-d.radius*.7+3)
    .attr('text-anchor','middle').attr('font-size',6).attr('font-weight',800).attr('fill','#fff')
    .text(d=>(d.provider||'')[0]?.toUpperCase()||'').attr('pointer-events','none');

  node.on('click',(e,d)=>{
    const det=document.getElementById('details');
    let h=`<h3>${esc(d.label)}</h3>`;
    if(d.meta){
      for(const[l,v]of Object.entries({Provider:d.provider,Env:(d.env||'').toUpperCase(),Region:d.meta.region,Address:(d.meta.addressSpace||[]).join(', ')}))
        if(v)h+=`<div class="df"><div class="dl">${esc(l)}</div><div class="dv">${esc(String(v))}</div></div>`;
    }
    det.innerHTML=h;showSidePanel('legend-panel',document.querySelector('.stab[data-panel="legend-panel"]'));
  });

  simulation=d3.forceSimulation(gd.nodes)
    .force('link',d3.forceLink(gd.links).id(d=>d.id).distance(d=>d.type==='peering'?280:70).strength(d=>d.type==='peering'?.15:.9))
    .force('charge',d3.forceManyBody().strength(d=>d.type==='network'?-600:-80).distanceMax(600))
    .force('collision',d3.forceCollide().radius(d=>d.radius+6).strength(.9))
    .force('cx',d3.forceX(d=>{const p=prodPos[d.product];return p?p.x:CX;}).strength(d=>d.type==='network'?.15:.12))
    .force('cy',d3.forceY(d=>{const p=prodPos[d.product];return p?p.y:CY;}).strength(d=>d.type==='network'?.15:.12))
    .alphaDecay(.018).velocityDecay(.4)
    .on('tick',()=>{
      link.attr('d',d=>{const dx=d.target.x-d.source.x,dy=d.target.y-d.source.y,dr=Math.sqrt(dx*dx+dy*dy)*(d.type==='peering'?1.5:3);
        return `M${d.source.x},${d.source.y}A${dr},${dr} 0 0,1 ${d.target.x},${d.target.y}`;});
      node.attr('transform',d=>`translate(${d.x},${d.y})`);
    });
  setTimeout(()=>{const b=g.node().getBBox();if(b.width>0){const pad=80,sc=Math.min(W/(b.width+pad*2),H/(b.height+pad*2),1.5),
    tx=W/2-sc*(b.x+b.width/2),ty=H/2-sc*(b.y+b.height/2);svg.transition().duration(1000).call(zoom.transform,d3.zoomIdentity.translate(tx,ty).scale(sc));}},2500);
  window._d3={node,link,gd,zoom};
}

function setEnv(e,btn){curEnv=e;document.querySelectorAll('.ebtn').forEach(b=>b.classList.remove('on'));btn.classList.add('on');applyFilter();}
function applySearch(){searchQ=document.getElementById('search').value.toLowerCase();applyFilter();}
function applyFilter(){if(!window._d3)return;
  window._d3.node.attr('display',d=>{const eo=curEnv==='all'||d.env===curEnv;const so=!searchQ||(d.searchText||'').includes(searchQ);return(eo&&so)?null:'none';});
  const vis=new Set();window._d3.node.each(function(d){if(d3.select(this).attr('display')!=='none')vis.add(d.id);});
  window._d3.link.attr('display',d=>{const s=typeof d.source==='object'?d.source.id:d.source;const t=typeof d.target==='object'?d.target.id:d.target;return(vis.has(s)&&vis.has(t))?null:'none';});}
function resetView(){if(!window._d3)return;const W=document.getElementById('graph-wrap').clientWidth,H=document.getElementById('graph-wrap').clientHeight,b=g.node().getBBox();
  if(b.width>0){const p=80,s=Math.min(W/(b.width+p*2),H/(b.height+p*2),1.5),tx=W/2-s*(b.x+b.width/2),ty=H/2-s*(b.y+b.height/2);
    svg.transition().duration(600).call(window._d3.zoom.transform,d3.zoomIdentity.translate(tx,ty).scale(s));}}
function toggleTheme(){isDark=!isDark;document.body.classList.toggle('light',!isDark);document.getElementById('theme-btn').textContent=isDark?'Light':'Dark';if(D){renderGraph(buildGraph(D));}}
function showSidePanel(id,tab){document.querySelectorAll('.side-panel').forEach(p=>p.classList.remove('active'));document.querySelectorAll('.stab').forEach(t=>t.classList.remove('active'));
  const p=document.getElementById(id);if(p)p.classList.add('active');if(tab)tab.classList.add('active');}

// Load
async function loadScope(s){if(!s)return;showLoad('Loading...');
  try{const r=await fetch(`/api/topology/${s}/structured`);
    if(!r.ok){const b=await r.json().catch(()=>({}));if(r.status===503){showAuthError(b.error||'Auth failed');return;}throw new Error(b.error||`HTTP ${r.status}`);}
    D=await r.json();renderGraph(buildGraph(D));
    const st=D.stats||{};document.getElementById('stats').innerHTML=`<span><strong>${st.networks||0}</strong> Networks</span><span><strong>${st.resources||0}</strong> Resources</span><span><strong>${st.peerings||0}</strong> Peerings</span>`;
    const cnt={};buildGraph(D).nodes.forEach(n=>{cnt[n.icon]=(cnt[n.icon]||0)+(n.type==='group'?n.count:1);});
    document.getElementById('legend').innerHTML=Object.entries(cnt).sort((a,b)=>b[1]-a[1]).map(([k,v])=>`<div class="li"><div class="dot" style="background:${TYPE_COLORS[k]||'#64748b'}"></div>${TYPE_LABELS[k]||k}<span class="lc">${v}</span></div>`).join('');
    document.getElementById('last-ref').textContent=`Refreshed ${new Date().toLocaleTimeString()}`;hideLoad();
    Promise.allSettled([loadHealth(s),loadChanges(s),loadIncidents()]);
  }catch(e){document.getElementById('load-msg').textContent=`Error: ${e.message}`;setTimeout(hideLoad,3000);}}

function refresh(){loadScope(document.getElementById('psel').value);}
function exportSvg(){const s=document.getElementById('psel').value;if(s)window.open(`/api/svg/${s}`,'_blank');}
function showLoad(t){document.getElementById('loading').classList.remove('off');document.getElementById('load-msg').textContent=t;}
function hideLoad(){document.getElementById('loading').classList.add('off');}

function showAuthError(msg){hideLoad();const el=document.getElementById('loading');el.classList.remove('off');
  el.innerHTML=`<div style="max-width:480px;text-align:center"><div style="font-size:48px;margin-bottom:12px">&#x1F512;</div>
    <div style="font-size:16px;font-weight:700;color:#ef4444;margin-bottom:8px">Authentication Required</div>
    <div style="font-size:12px;color:#94a3b8;margin-bottom:20px">${esc(msg)}</div>
    <button onclick="document.getElementById('loading').innerHTML='<div class=spin></div><div id=load-msg>Retrying...</div>';loadScope(document.getElementById('psel').value)"
      style="background:#3b82f6;border:none;color:#fff;padding:10px 28px;border-radius:6px;cursor:pointer;font-size:13px;font-weight:700">Retry</button></div>`;}

// Health
async function loadHealth(s){try{const r=await fetch(`/api/health/${s}`);if(!r.ok)return;const d=await r.json();
  const sc=d.score||{};document.getElementById('health-score-display').innerHTML=`<div class="score-value">${sc.score??'--'}</div><div style="margin-left:auto;font-size:10px"><div style="color:#ef4444">${sc.critical||0} critical</div><div style="color:#eab308">${sc.warnings||0} warnings</div></div>`;
  const badge=document.getElementById('health-badge');badge.textContent=`${sc.grade||'-'} ${sc.score??''}`;badge.style.color=sc.critical>0?'#ef4444':sc.warnings>0?'#eab308':'#22c55e';
  const issues=(d.checks||[]).filter(c=>c.status!=='healthy');
  document.getElementById('health-issues').innerHTML=issues.length?issues.slice(0,20).map(c=>`<div class="health-item ${c.status}">${esc(c.message)}</div>`).join(''):'<div class="dtip">All checks passed.</div>';
}catch(e){}}

// Changes
async function loadChanges(s){try{const r=await fetch(`/api/changes/${s}`);if(!r.ok)return;const d=await r.json();
  const changes=d.changes||[];document.getElementById('change-list').innerHTML=changes.length?changes.slice(0,20).map(c=>
    `<div class="change-item"><span class="badge ${c.change_type}">${c.change_type}</span><span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(c.resource_name)}</span></div>`
  ).join(''):'<div class="dtip">No changes yet.</div>';}catch(e){}}

// Incidents
async function loadIncidents(){try{const s=document.getElementById('psel').value;const r=await fetch(`/api/incidents?scope=${s}`);if(!r.ok)return;const d=await r.json();
  const list=document.getElementById('incident-list');const incs=d.incidents||[];
  list.innerHTML=incs.length?incs.slice(0,10).map(i=>`<div class="incident-item" onclick="showInc(${i.id})"><div style="display:flex;align-items:center;gap:6px"><span class="inc-status ${i.status}">${i.status}</span><div class="inc-title">${esc(i.title)}</div></div><div class="inc-meta">${new Date(i.created_at).toLocaleString()}</div></div>`).join(''):'<div class="dtip">No incidents.</div>';}catch(e){}}

function showIncidentForm(){document.getElementById('incident-form').style.display='block';document.getElementById('inc-title').focus();}
function hideIncidentForm(){document.getElementById('incident-form').style.display='none';}
function pickSev(s,btn){_incSev=s;document.querySelectorAll('.sev-btn').forEach(b=>b.classList.remove('sev-active'));btn.classList.add('sev-active');}
async function submitIncident(){const t=document.getElementById('inc-title').value.trim();if(!t)return;
  const s=document.getElementById('psel').value;
  try{await fetch('/api/incidents',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:t,description:document.getElementById('inc-desc').value,severity:_incSev,scope:s})});
    hideIncidentForm();loadIncidents();}catch(e){}}
async function showInc(id){try{const r=await fetch(`/api/incidents/${id}`);const inc=await r.json();
  document.getElementById('incident-detail').innerHTML=`<div class="ss"><h4>#${id}</h4><div class="inc-title">${esc(inc.title)}</div><span class="inc-status ${inc.status}">${inc.status}</span>
    ${(inc.annotations||[]).map(a=>`<div class="annotation ${a.author}"><div style="font-size:9px;color:var(--text3)">${a.author}</div>${esc(a.content)}</div>`).join('')}</div>`;}catch(e){}}

// AI
function toggleAI(){document.getElementById('ai-panel').classList.toggle('off');document.querySelector('.ai-btn').classList.toggle('on');if(!document.getElementById('ai-panel').classList.contains('off'))document.getElementById('ai-input').focus();}
async function sendAI(){const inp=document.getElementById('ai-input'),q=inp.value.trim();if(!q)return;inp.value='';
  const msgs=document.getElementById('ai-messages');msgs.innerHTML+=`<div class="ai-msg user">${esc(q)}</div><div class="ai-msg assistant" style="opacity:.5">Thinking...</div>`;msgs.scrollTop=msgs.scrollHeight;
  try{const r=await fetch('/api/ai/query',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q,scope:document.getElementById('psel').value})});
    const d=await r.json();msgs.lastChild.remove();msgs.innerHTML+=`<div class="ai-msg assistant">${esc(d.answer||'No response.')}</div>`;msgs.scrollTop=msgs.scrollHeight;
  }catch(e){msgs.lastChild.remove();msgs.innerHTML+=`<div class="ai-msg assistant">Error: ${esc(e.message)}</div>`;}}

// SSE
function connectSSE(){const es=new EventSource('/api/events');
  es.addEventListener('update',()=>{const s=document.getElementById('psel').value;if(s)loadScope(s);});
  es.addEventListener('auth_error',e=>{showAuthError(e.data||'Credentials expired');});
  es.onerror=()=>{es.close();setTimeout(connectSSE,5000);};}

document.addEventListener('DOMContentLoaded',()=>{document.getElementById('psel').value='all';loadScope('all');connectSSE();});
document.addEventListener('keydown',e=>{if(e.target.tagName==='INPUT')return;if(e.ctrlKey&&e.key==='k'){e.preventDefault();toggleAI();}});
