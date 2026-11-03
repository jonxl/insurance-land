const {test}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const vm=require('node:vm');
const html=readFileSync('experiments/diagnostics.html','utf8');
const source=html.slice(html.indexOf("let view = 'map'"),html.indexOf("let chartView ="));
function setup(fetch){
 const nodes=new Map();
 function element(){
  return {hidden:false,disabled:false,children:[],attributes:{},dataset:{},value:'',textContent:'',
   append(...nodes){this.children.push(...nodes);},
   replaceChildren(...nodes){this.children=nodes;},
   insertBefore(node){this.children.splice(-1,0,node);},
   setAttribute(k,v){this.attributes[k]=v;},
   showModal(){this.open=true;},close(){this.open=false;},focus(){this.focused=true;},
   get lastChild(){return this.children.at(-1);}
  };
 }
 const $=id=>{if(!nodes.has(id))nodes.set(id,element());return nodes.get(id);};
 $('experimentForm').elements={namedItem:name=>$('input:'+name)};
 const config={name:'Standard',seed:42,rows:8,columns:8,periods:120,rate:.1};
 const location={protocol:'http:',pathname:'/diagnostics.html',search:'',replace(url){this.replaced=url;}};
 const context=vm.createContext({
  $,bundle:{},document:{createElement:element},worlds:{Standard:{configuration:config}},worldName:'Standard',
  window:{addEventListener(){}},location,history:{pushState(a,b,url){location.search=url.startsWith('?')?url:'';},replaceState(a,b,url){location.search=url.startsWith('?')?url:'';}},
  hideTip(){},stopPlay(){},renderResearch(){},render(){},setWorld(){},
  fetch,clearTimeout(){},setTimeout(){return 1;},URLSearchParams,encodeURIComponent,
  FormData:class{constructor(form){return Object.entries(form.values);}}
 });
 vm.runInContext(source,context);
 return {context,$,location,config};
}
const response=body=>({ok:true,json:async()=>body});
const flush=()=>new Promise(resolve=>setImmediate(resolve));

test('library is the landing view and the new-world tile opens a native modal',async()=>{
 const app=setup(async url=>response(url==='/api/health'?{ready:true}:{runs:[]}));
 await app.context.initializeLibrary();
 assert.equal(app.$('experimentView').hidden,false);
 assert.equal(app.$('snapshotView').hidden,true);
 assert.equal(app.$('worldLibrary').children.length,4);
 app.$('worldLibrary').children.at(-1).onclick();
 assert.equal(app.$('experimentDialog').open,true);
 app.$('cancelExperiment').onclick();
 assert.equal(app.$('experimentDialog').open,false);
});

test('create opens progress immediately, persists the run URL, and opens completed snapshots',async()=>{
 let complete=false,payload;
 const app=setup(async(url,options)=>{
  if(url==='/api/health')return response({ready:true});
  if(options){payload=JSON.parse(options.body);return response(job);}
  if(url==='/api/runs/new')return response({...job,state:complete?'complete':'running',completed_periods:1});
  return response({runs:[]});
 });
 const job={id:'new',title:'My world',configuration:app.config,state:'queued',completed_periods:0,url:'/runs/new/diagnostics.html?view=map'};
 await app.context.initializeLibrary();
 app.context.openExperiment();
 await app.$('experimentForm').onsubmit({preventDefault(){},currentTarget:{values:{title:'My world',name:'Standard',periods:'120',rate:'0.1'}}});
 assert.equal(payload.title,'My world');assert.equal(payload.periods,120);
 assert.equal(app.$('experimentDialog').open,false);
 assert.equal(app.$('loadingView').hidden,false);
 assert.equal(app.$('snapshotView').hidden,true);
 assert.equal(app.location.search,'?run=new');
 await flush();
 assert.equal(app.$('runProgress').value,1);
 complete=true;await app.context.pollRun('new');
 assert.equal(app.location.replaced,job.url);
});

test('leaving a running world prevents late polling from navigating away from the library',async()=>{
 let resolvePoll;
 const app=setup(url=>url==='/api/runs/job'?new Promise(resolve=>{resolvePoll=resolve;}):Promise.resolve(response({runs:[]})));
 const job={id:'job',title:'Running world',configuration:app.config,state:'running',completed_periods:0,url:'/done'};
 app.context.openRun(job);
 app.context.openLibrary();
 resolvePoll(response({...job,state:'complete'}));await flush();
 assert.equal(app.$('experimentView').hidden,false);
 assert.equal(app.location.replaced,undefined);
});

test('disconnection offers reconnection, while a failed run can reuse its settings',async()=>{
 let disconnected=true;
 const app=setup(async()=>{
  if(disconnected)throw new Error('Connection lost');
  return response({...job,state:'failed',error:'Simulation failed'});
 });
 const job={id:'job',title:'Saved title',configuration:app.config,state:'running',completed_periods:3};
 app.context.openRun(job);await flush();
 assert.equal(app.$('retryStatus').hidden,false);
 disconnected=false;await app.context.pollRun('job');
 assert.equal(app.$('retryWorld').hidden,false);
 assert.equal(app.$('loadingStatus').textContent,'Simulation failed');
 app.$('retryWorld').onclick();
 assert.equal(app.$('input:title').value,'Saved title');
 assert.equal(app.$('experimentDialog').open,true);
});

test('reloading a running-world URL reconnects to that job',async()=>{
 const app=setup(async url=>response(url==='/api/health'?{ready:true}:job));
 const job={id:'saved',title:'Reloaded',configuration:app.config,state:'running',completed_periods:9};
 app.location.search='?run=saved';
 await app.context.initializeLibrary();await flush();
 assert.equal(app.$('loadingTitle').textContent,'Reloaded');
 assert.equal(app.$('runProgress').value,9);
});

test('Dev experiments have separate names and types and open from the library',()=>{
 const app=setup(async()=>response({runs:[]}));
 app.context.worlds.Peace={configuration:app.config};
 app.context.worlds.Chaos={configuration:app.config};
 app.context.renderLibrary();
 const standard=app.$('worldLibrary').children[1];
 assert.equal(standard.children[1].textContent,'Dev Standard');
 assert.match(standard.children[2].textContent,/Type: Standard/);
 standard.onclick();
 assert.equal(app.$('workspaceTitle').textContent,'Dev Standard');
 assert.equal(app.$('experimentType').textContent,'Type: Standard');
 assert.equal(app.$('experimentTabs').hidden,false);
 assert.match(app.location.search,/view=map/);
});

test('contextual tabs preserve experiment identity and restore research on navigation',()=>{
 const app=setup(async()=>response({runs:[]}));
 app.context.bundle.title='Low risk study';
 app.context.showView('start');
 assert.equal(app.$('experimentTabs').hidden,true);
 app.context.navigateView('research');
 assert.equal(app.$('workspaceTitle').textContent,'Low risk study');
 assert.equal(app.$('experimentType').textContent,'Type: Standard');
 assert.equal(app.$('researchView').hidden,false);
 assert.match(app.location.search,/view=research/);
 app.context.showView('map');
 app.context.restoreRoute();
 assert.equal(app.$('researchView').hidden,false);
 app.context.openLibrary();
 assert.equal(app.$('experimentTabs').hidden,true);
 assert.equal(app.$('experimentIdentity').hidden,true);
});

test('Dev Standard opens the built-in rather than a saved Standard experiment',()=>{
 const app=setup(async()=>response({runs:[]}));
 app.context.bundle.title='Custom Standard';
 app.context.renderLibrary();
 app.$('worldLibrary').children[1].onclick();
 assert.equal(app.location.href,'/diagnostics.html?world=Standard&view=map');
});

test('Chaos growth controls only apply to Chaos experiments',()=>{
 const app=setup(async()=>response({runs:[]}));
 assert.equal(app.$('chaosRateControl').hidden,true);
 app.$('input:name').value='Chaos';app.context.syncExperimentType();
 assert.equal(app.$('chaosRateControl').hidden,false);
 assert.equal(app.$('input:chaos_rate_ratio').disabled,false);
});
