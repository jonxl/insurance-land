const {test,beforeAll}=require('bun:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const vm=require('node:vm');
const appSource=readFileSync('experiments/ui/dist/app.js','utf8');
const context=vm.createContext({});
let distribution,metricValues,ranks;
beforeAll(async()=>{
 const metrics=await import('../experiments/ui/dist/metrics.js');
 const {createEventHelpers}=await import('../experiments/ui/dist/events.js');
 Object.assign(context,metrics,createEventHelpers({money:n=>"$"+Number(n),firmName:id=>"Firm "+id}));
 ({distribution,metricValues,ranks}=metrics);
});

test('treemap sizes blocks by home count, fills the map and keeps grid order',()=>{
 const items=[[0,0,6],[0,1,2],[1,0,1],[1,1,7]].map(([row,col,count])=>({row,col,count}));
 const blocks=context.treemap(items,0,0,2,2);
 const area=blocks.reduce((n,b)=>n+b.w*b.h,0);
 assert.ok(Math.abs(area-4)<1e-9);
 for(const b of blocks)assert.ok(Math.abs(b.w*b.h-4*b.count/16)<1e-9);
 const at=(r,c)=>blocks.find(b=>b.row===r&&b.col===c);
 assert.ok(at(0,0).x<at(0,1).x&&at(1,0).x<at(1,1).x);
 assert.ok(at(0,0).y<at(1,0).y&&at(0,1).y<at(1,1).y);
});
test('Lorenz and Gini handle equality, concentration, and zero totals',()=>{
 assert.equal(distribution([{value:5},{value:5}]).gini,0);
 const concentrated=distribution([{value:0},{value:10}]);
 assert.equal(concentrated.gini,.5);
 assert.equal(JSON.stringify(concentrated.curve),'[0,0,1]');
 assert.equal(distribution([{value:0},{value:0}]).gini,null);
});
test('destroyed titles count as ownership but have no property value',()=>{
 const frame={people:[{id:1,cash:'20',annual_income:'50'},{id:2,cash:'30',annual_income:'100'}],homes:[{owner:1,value:'100'},{owner:1,value:'0',destroyed:true}]};
 assert.equal(JSON.stringify(metricValues(frame,'homes')),'[{"id":1,"value":2},{"id":2,"value":0}]');
 assert.equal(metricValues(frame,'net')[0].value,120);
 assert.equal(metricValues(frame,'property')[1].value,0);
});
test('equal values share leaderboard rank',()=>{
 const result=ranks([{id:2,value:10},{id:1,value:10},{id:3,value:5}]);
 assert.equal(result.get(1),1);assert.equal(result.get(2),1);assert.equal(result.get(3),3);
});


test('outcomes deduplicate coverage, exclude destroyed homes, and accumulate claims',()=>{
 const history=[
  {period:0,homes:[{id:1,resident:1,destroyed:false},{id:2,resident:2,destroyed:false}],events:[],transfers:[]},
  {period:1,homes:[{id:1,resident:null,destroyed:true},{id:2,resident:2,destroyed:false}],events:[{}],transfers:[{kind:'claim',due:'100',amount:'60'}]},
  {period:2,homes:[{id:1,resident:null,destroyed:true},{id:2,resident:2,destroyed:false}],events:[],transfers:[]}
 ];
 const contracts=[{home:1,starts:1,ends:1},{home:1,starts:1,ends:1},{home:2,starts:1,ends:1}];
 const result=context.summarizeOutcomes(history,contracts);
 assert.equal(result[0].insured,2);assert.equal(result[1].insured,1);assert.equal(result[2].insured,0);
 assert.equal(result[1].displaced,1);assert.equal(result[1].intact,1);
 assert.equal(result[2].due,100);assert.equal(result[2].paid,60);
 assert.equal(result[0].events,0);assert.equal(result[1].events,1);
});
test('histogram preserves all observations including the maximum and zero-only samples',()=>{
 const bins=context.histogramBins([0,0,5,10]);
 assert.equal(bins.counts.reduce((a,b)=>a+b),4);
 assert.equal(bins.counts[0],2);assert.equal(bins.counts.at(-1),1);
 assert.equal(context.histogramBins([0,0,0]).counts[0],3);
});

vm.runInContext(appSource.slice(appSource.indexOf('const personColors ='),appSource.indexOf('const shape =')),context);
test('person colors are stable, colorful, unique, and separated from firm colors',()=>{
 const colors=Array.from({length:1024},(_,i)=>context.ownerColor(i+1));
 assert.equal(new Set(colors).size,1024);
 const firmColors=['#f5b7b5','#ccebc5','#b3cde3','#e53935','#00a651','#007aff'].map(h=>[1,3,5].map(i=>parseInt(h.slice(i,i+2),16)));
 for(const color of colors){
  const rgb=[1,3,5].map(i=>parseInt(color.slice(i,i+2),16));
  assert.ok(Math.max(...rgb)-Math.min(...rgb)>35);
  for(const firm of firmColors)assert.ok(Math.hypot(...rgb.map((v,i)=>v-firm[i]))>=40);
 }
 assert.equal(context.ownerColor(17),colors[16]);
});
test('person colors stay out of the purple hues reserved for disasters',()=>{
 for(let id=1;id<=1024;id++){
  const hex=context.ownerColor(id),[r,g,b]=[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)/255);
  const max=Math.max(r,g,b),delta=max-Math.min(r,g,b);
  const hue=(max===r?((g-b)/delta+6)%6:max===g?(b-r)/delta+2:(r-g)/delta+4)*60;
  assert.ok(hue<250||hue>320,`person ${id} has purple hue ${hue}`);
 }
});

test('console log records collapses, disasters, claims, and unpaid rent',()=>{
 const firm=capital=>[{id:1,capital}];
 const log=context.buildLog([
  {firms:firm('10'),events:[],transfers:[{kind:'premium',amount:'10'}]},
  {firms:firm('0'),events:[{id:1,cells:[[1,2],[2,2]],losses:[7,8],displaced:[3]}],transfers:[{kind:'claim',home:7,firm:1,person:3,due:'50',amount:'10',shortfall:'40'},{kind:'rent',paid:true,amount:'5',requested:'5'},{kind:'rent',paid:false,amount:'0',requested:'5'}]},
  {firms:firm('0'),events:[{id:1,cells:[[1,2]],losses:[],displaced:[]}],transfers:[]}
 ]);
 assert.equal(log.insurance.filter(row=>row.title.includes('ran out')).length,1);
 assert.equal(log.disasters[0].title,'Disaster at rows 1 to 2, columns 2');
 assert.equal(log.disasters[0].lost,2);
 assert.equal(log.disasters[1].lost,0);
 assert.equal(log.insurance.find(row=>row.due).short,40);
});
test('ledger keeps every transfer in period order and filters unpaid rent',()=>{
 const income={kind:'income',person:1,amount:'9'},paid={kind:'rent',person:1,recipient:2,home:3,paid:true,amount:'5',requested:'5'},missed={kind:'rent',person:1,recipient:2,home:3,paid:false,amount:'0',requested:'5'};
 const rows=context.ledgerRows([{transfers:[income]},{transfers:[paid,income]},{transfers:[missed]}]);
 assert.equal(rows.length,4);
 assert.equal(context.countThrough(rows,0),1);assert.equal(context.countThrough(rows,1),3);assert.equal(context.countThrough(rows,2),4);
 assert.equal(rows.filter(row=>context.matchesKind(row.transfer,'unpaid')).length,1);
 assert.equal(rows.filter(row=>context.matchesKind(row.transfer,'rent')).length,2);
 const text=context.describeTransfer(missed);
 assert.equal(text.alert,true);assert.equal(text.amount,'5');
});
test('disasters thread their own losses and claims, and insurers group claims',()=>{
 const claim=(home,firm,due,paid)=>({kind:'claim',home,firm,person:home,due,amount:paid,shortfall:String(due-paid)});
 const log=context.buildLog([{firms:[{id:1,capital:'9'},{id:2,capital:'9'}],events:[{id:1,cells:[[0,0]],losses:[7],displaced:[3]},{id:2,cells:[[5,5]],losses:[8],displaced:[]}],transfers:[claim(7,1,50,50),claim(8,1,20,10),claim(8,2,5,5)]}]);
 assert.equal(log.disasters[0].claims,1);assert.equal(log.disasters[1].claims,2);
 assert.equal(log.disasters[0].replies[0].title,'Homes lost: 7');
 const red=log.insurance.find(row=>row.key==='claims:0:1');
 assert.equal(red.count,2);assert.equal(red.due,70);assert.equal(red.short,10);assert.equal(red.alert,true);
 assert.equal(log.insurance.find(row=>row.key==='claims:0:2').alert,false);
});
test('ledger groups collapse repeats, keep every row, and split missed rent',()=>{
 const income={kind:'income',person:1,amount:'9'},paid={kind:'rent',person:1,recipient:2,home:3,paid:true,amount:'5',requested:'5'},missed={kind:'rent',person:2,recipient:2,home:4,paid:false,amount:'0',requested:'6'};
 const groups=context.ledgerGroups({transfers:[income,income,paid,missed]},4);
 assert.equal(groups.map(g=>g.kind).join(),'income,rent,unpaid');
 assert.equal(groups[0].amount,18);assert.equal(groups[0].rows.length,2);
 assert.equal(groups[2].amount,6);assert.equal(groups[2].alert,true);
 assert.equal(groups.reduce((n,g)=>n+g.rows.length,0),4);
});
test('claim wording says when an insurer paid nothing or only part',()=>{
 const claim=(amount,shortfall)=>context.describeTransfer({kind:'claim',firm:1,person:2,home:3,due:'10',amount,shortfall}).title;
 assert.match(claim('10','0'),/^Firm 1 paid a claim/);
 assert.match(claim('4','6'),/^Firm 1 partly paid/);
 assert.match(claim('0','10'),/^Firm 1 could not pay/);
});

test('combined timeline puts payments before disasters and keeps claims under their event',()=>{
 const frames=[
  {firms:[{id:1,capital:'100'}],events:[],transfers:[{kind:'premium',person:1,firm:1,home:1,amount:'10'}]},
  {firms:[{id:1,capital:'0'}],events:[{id:1,cells:[[0,0]],losses:[1],displaced:[1]}],transfers:[
   {kind:'income',person:1,amount:'20'},
   {kind:'rent',person:1,recipient:2,home:1,paid:true,amount:'5'},
   {kind:'claim',firm:1,person:1,home:1,due:'100',amount:'100',shortfall:'0'}
  ]}
 ];
 const events=context.timelineEvents(frames);
 assert.deepEqual(Array.from(events,e=>e.key),['ledger:0:premium','ledger:1:income','ledger:1:rent','disaster:1:1','capital:1:1']);
 const claims=events.flatMap(e=>e.replies||[]).filter(r=>r.title.includes('paid a claim'));
 assert.equal(claims.length,1);
});

test('timeline preserves claims without a linked disaster',()=>{
 const events=context.timelineEvents([{firms:[],events:[],transfers:[
  {kind:'claim',firm:1,person:1,home:1,due:'10',amount:'10',shortfall:'0'}
 ]}]);
 assert.equal(events.length,1);
 assert.equal(events[0].key,'other-claims:0');
 assert.equal(events[0].replies.length,1);
});

test('full timeline contains every recorded stop and stays unchanged when the period moves',()=>{
 const timeline=vm.createContext({period:0,messageHtml:m=>m.key});
 vm.runInContext(appSource.slice(appSource.indexOf('function sectionsHtml('),appSource.indexOf('const timelineCache =')),timeline);
 const messages=[{period:5,key:'last'},{period:0,key:'first'},{period:2,key:'income'},{period:2,key:'disaster'}];
 const result=timeline.sectionsHtml(messages,true,8);
 assert.equal(result.total,8);
 assert.ok(result.html.indexOf('Period 0')<result.html.indexOf('Period 2'));
 assert.ok(result.html.indexOf('>income<')<result.html.indexOf('>disaster<'));
 assert.match(result.html,/Period 5/);
 assert.match(result.html,/Period 7/);
 assert.match(result.html,/No disasters this period/);
 timeline.period=5;
 assert.equal(timeline.sectionsHtml(messages,true,8).html,result.html);
 assert.equal(timeline.sectionsHtml([],true,3).total,3);
 assert.equal(timeline.sectionsHtml([],true,0).html,'');
});

test('playhead moves one persistent marker and honors reduced-motion scrolling',()=>{
 const marker={style:{},hidden:true},note={hidden:true},attrs={};
 const node={getBoundingClientRect:()=>({top:600,bottom:614})};
 const stop={dataset:{jump:'3'},setAttribute:(k,v)=>attrs[k]=v,removeAttribute:k=>delete attrs[k],querySelector:selector=>selector==='.period-node'?node:note};
 const route={getBoundingClientRect:()=>({top:100}),querySelector:()=>marker,querySelectorAll:selector=>selector==='[data-jump]'?[stop]:[]};
 const feed={querySelector:selector=>selector==='.timeline-route'?route:stop};
 const body={scrollTop:0,getBoundingClientRect:()=>({top:0,bottom:400}),scrollTo:options=>body.scrolled=options};
 const elements={feed,panelBody:body,feedPanel:{hidden:false},snapshotView:{hidden:false},snapshotMap:{hidden:false},followTimeline:{checked:true}};
 const timeline=vm.createContext({
  period:3,focusEvent:null,$:id=>elements[id],
  requestAnimationFrame:callback=>{callback();return 1;},cancelAnimationFrame(){},
  document:{querySelector:()=>({offsetHeight:100})},matchMedia:()=>({matches:true})
 });
 vm.runInContext(appSource.slice(appSource.indexOf('let mountedTimelineKey ='),appSource.indexOf('const timelineCache =')),timeline);
 timeline.syncPlayhead();
 assert.equal(marker.style.transform,'translateY(500px)');
 assert.equal(marker.hidden,false);
 assert.equal(attrs['aria-current'],'step');
 assert.equal(note.hidden,false);
 assert.equal(body.scrolled.behavior,'instant');
 elements.followTimeline.checked=false;body.scrolled=null;
 timeline.period=2;timeline.syncPlayhead();
 assert.equal(body.scrolled,null);
 assert.equal(attrs['aria-current'],undefined);
});

function selectionContext() {
 const homes=[
  {id:1,owner:7,resident:9,destroyed:false},
  {id:2,owner:7,resident:null,destroyed:true},
  {id:3,owner:9,resident:7,destroyed:false},
 ];
 const c=vm.createContext({
  frames:[{homes}],period:0,homeId:null,selectedKind:'person',selectedId:null,
  panelTab:'overview',worldName:'Standard',shape:[1,3],blocks:[],
  spots:new Map(homes.map((h,i)=>[h.id,{x:i,y:0,w:1,h:1}])),
  render(){},stopPlay(){},hideTip(){},$(){return {scrollTop:0};}
 });
 for(const [start,end] of [
  ['function clearSelection(', 'document\n'],
  ['function setTab(', 'const worldBlurbs ='],
  ['function miniMap(', 'atlasPlates.forEach('],
 ]) {
  const offset=appSource.indexOf(start);
  vm.runInContext(appSource.slice(offset,appSource.indexOf(end,offset)),c);
 }
 return c;
}

test('home selection follows its owner, including rented and destroyed homes, from any tab',()=>{
 const c=selectionContext();
 for(const tab of ['overview','timeline','people']){
  c.panelTab=tab;c.selectHome(1);
  assert.equal(c.homeId,1);assert.equal(c.selectedId,7);assert.equal(c.panelTab,'people');
 }
 c.selectHome(2);
 assert.equal(c.selectedId,7);assert.equal(c.homeId,2);
 c.selectHome(999);
 assert.equal(c.homeId,2);
});

test('selection survives panel changes and highlights all owned homes in research previews',()=>{
 const c=selectionContext();c.selectHome(1);c.setTab('timeline');
 assert.equal(c.selectedId,7);assert.equal(c.homeId,1);
 const html=c.miniMap(c.frames[0].homes,()=>({bg:'#fff'}));
 assert.equal((html.match(/class="mini-owned"/g)||[]).length,2);
 assert.ok(html.includes('data-home="2"'));
 assert.equal((c.miniMap(c.frames[0].homes,()=>({bg:'#fff'}),'Chaos').match(/class="mini-owned"/g)||[]).length,0);
 c.clearSelection();
 assert.equal(c.homeId,null);assert.equal(c.selectedId,null);
 assert.equal((c.miniMap(c.frames[0].homes,()=>({bg:'#fff'})).match(/class="mini-owned"/g)||[]).length,0);
});
