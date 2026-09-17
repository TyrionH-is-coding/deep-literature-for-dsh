import assert from 'node:assert/strict';
import fs from 'node:fs';
const source=fs.readFileSync(new URL('../client/client.js',import.meta.url),'utf8');
function fn(name){const start=source.indexOf(`function ${name}(`);assert.ok(start>=0,name);let depth=0;const b=source.indexOf('{',start);for(let i=b;i<source.length;i++){if(source[i]==='{')depth++;if(source[i]==='}')depth--;if(!depth)return source.slice(start,i+1);}throw Error(name);}
class Node {constructor(tag){this.tag=tag;this.children=[];this.text='';this.attrs={};} set textContent(v){this.text=String(v);this.children=[];} get textContent(){return this.text+this.children.map(n=>n.textContent).join('');} set innerHTML(v){throw Error('Unsafe HTML');} appendChild(n){this.children.push(n);return n;} setAttribute(k,v){this.attrs[k]=v;} addEventListener(){} }
const document={createElement:t=>new Node(t),createTextNode:t=>{const n=new Node('#text');n.textContent=t;return n;}};
const el=Function('document',`return (${fn('el')})`)(document);
const controls={drawerBody:new Node('div')};
const dependencies={document,el,controls,drawerSessions:{isCurrent:()=>true},pairAbstractParagraphs:()=>[],paperEntryModel:()=>({}),isSafeHttpUrl:()=>false,entryLink:(t)=>el('a','',t),btn:t=>el('button','',t)};
const extra=source.includes('function renderXlsxPending(')?fn('renderXlsxPending'):'';
const render=Function(...Object.keys(dependencies),`${extra};return (${fn('renderDrawer')});`)(...Object.values(dependencies));
const paper={paper_id:'title_d8b339a0356f',title:'Fixture',tags:[]};
const conflict={status:'waiting_user',detail:{reason_code:'xlsx_user_fields_conflict',required_input:{status:'pending',updated:0,conflicts:1,error:{code:'xlsx_user_fields_conflict',detail:'已保留原工作簿和数据库，整批未导入'},conflict_details:[{paper_id:paper.paper_id,field:'user_notes',code:'user_field_conflict'}]}}};
function draw(job,item={}){render(paper,{detail:{item,job},abstract:{}},1);return controls.drawerBody.textContent;}
let count=0;function test(name,body){body();count++;console.log('PASS '+name);}
test('003C real HTTP shape renders in drawer',()=>{const t=draw(conflict);for(const s of ['Excel 同步已暂停','用户笔记',paper.paper_id,'整批未导入','原工作簿和数据库','备份'])assert.ok(t.includes(s),s);});
test('all personal fields',()=>{for(const [field,label] of Object.entries({personal_thoughts:'个人思考',understanding_level:'个人理解程度',user_notes:'用户笔记'})){const j=structuredClone(conflict);j.detail.required_input.conflict_details[0].field=field;assert.ok(draw(j).includes(label));}});
test('other paper is not attributed to current paper',()=>{const j=structuredClone(conflict);j.detail.required_input.conflict_details[0].paper_id='other_paper';const t=draw(j);assert.ok(t.includes('同批其他文献'));assert.ok(t.includes('other_paper'));});
test('normal success clears warning',()=>assert.ok(!draw({status:'success',detail:conflict.detail}).includes('Excel 同步已暂停')));
test('PDF gate retained',()=>{const t=draw({status:'waiting_user',detail:{reason_code:'pdf_required'}});assert.ok(t.includes('挂接本地 PDF'));assert.ok(t.includes('重试 OA 获取'));assert.ok(!t.includes('Excel 同步已暂停'));});
test('missing optional details and unknown xlsx reason',()=>{for(const j of [{status:'waiting_user',detail:{reason_code:'xlsx_user_fields_conflict'}},{status:'waiting_user',detail:{reason_code:'xlsx_future_reason'}},{status:'waiting_user'}])assert.ok(draw(j).includes('暂停'));});
test('identity and baseline explanations',()=>{assert.ok(draw({status:'waiting_user',detail:{reason_code:'xlsx_identity_conflict'}}).includes('身份'));for(const code of ['baseline_invalid','baseline_missing_difference']){const j=structuredClone(conflict);j.detail.required_input.conflict_details[0].code=code;assert.ok(draw(j).includes('基线'));}});
test('hostile values are text and personal values are omitted',()=>{const j=structuredClone(conflict);j.detail.required_input.conflict_details=[{paper_id:'<img src=x onerror=alert(1)>',field:'<script>alert(1)</script>',code:'user_field_conflict',value:'PRIVATE_VALUE'}];j.detail.reason_code='xlsx_<svg onload=alert(1)>';const t=draw(j);assert.ok(t.includes('<img'));assert.ok(!t.includes('PRIVATE_VALUE'));const walk=n=>{assert.ok(!['img','script','svg'].includes(n.tag));n.children.forEach(walk);};walk(controls.drawerBody);});
test('malformed detail does not crash',()=>{for(const rows of [null,{},[null,3,{}, {field:'__proto__'}]]){const j=structuredClone(conflict);j.detail.required_input.conflict_details=rows;assert.ok(draw(j).includes('暂停'));}});
test('refresh and reopen rerender persistent state without accumulation',()=>{const before=draw(conflict);controls.drawerBody.textContent='';assert.equal(draw(structuredClone(conflict)),before);assert.equal(draw(structuredClone(conflict)),before);});
console.log(`${count} drawer rendering checks passed`);
