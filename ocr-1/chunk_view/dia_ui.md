参考仓库里的 ‎`chunk_studio_target.html`——这是设计定稿。请把它的布局、样式、交互原样搬到我们的 chunk-studio 页面,然后把里面的假数据(FILES / SAMPLE)换成真实接口数据:文件清单来自现有接口、chunk 来自真实切片、来源和 title_path 来自 chunk 元数据、原图/结构化来自 artifact_path。布局、CSS、交互结构一律不许改,只替换数据来源。

<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>切片工作台 目标稿</title>
<style>
  :root{
    --bg:#ffffff; --surface:#faf7f1; --surface-2:#f5f1ea;
    --accent:#e8631a; --accent-weak:#fbe9dd;
    --ink:#1f2328; --ink-2:#6b7280; --ink-3:#9aa0a6;
    --border:#e7e2d9; --border-strong:#d8d1c4;
    --q-good:#2fb344; --q-mid:#e8a400; --q-bad:#d64545;
    --mono:ui-monospace,"SFMono-Regular",Menlo,Consolas,monospace;
    --sans:-apple-system,"Segoe UI","Hiragino Kaku Gothic ProN","Microsoft YaHei",sans-serif;
  }
  *{box-sizing:border-box;}
  html,body{height:100%;}
  body{margin:0;font-family:var(--sans);color:var(--ink);background:var(--surface-2);font-size:13px;line-height:1.5;}
  button{font-family:inherit;cursor:pointer;}
  .app{display:grid;grid-template-rows:48px 1fr;height:100vh;}
  .topbar{display:flex;align-items:center;gap:16px;background:var(--bg);border-bottom:1px solid var(--border);padding:0 16px;}
  .brand{font-weight:600;font-size:14px;letter-spacing:.2px;}
  .brand .dot{color:var(--accent);}
  .crumb{color:var(--ink-2);font-size:12px;}
  .crumb b{color:var(--ink);font-weight:600;}
  .top-actions{margin-left:auto;display:flex;gap:8px;}
  .body{display:grid;grid-template-columns:260px 1fr;min-height:0;}
  .side{background:var(--bg);border-right:1px solid var(--border);display:flex;flex-direction:column;min-height:0;}
  .nav{padding:8px;border-bottom:1px solid var(--border);}
  .nav-item{display:flex;align-items:center;gap:9px;padding:8px 10px;border-radius:5px;color:var(--ink-2);font-size:12.5px;}
  .nav-item .ic{width:15px;height:15px;opacity:.75;}
  .nav-item.active{background:var(--accent-weak);color:var(--accent);font-weight:600;}
  .nav-item.active .ic{opacity:1;}
  .nav-item:not(.active):hover{background:var(--surface-2);}
  .filehdr{display:flex;align-items:center;justify-content:space-between;padding:12px 12px 8px;}
  .filehdr .t{font-size:11px;font-weight:600;letter-spacing:.6px;color:var(--ink-3);text-transform:uppercase;}
  .search{margin:0 10px 8px;position:relative;}
  .search input{width:100%;padding:6px 9px;border:1px solid var(--border);border-radius:5px;font-size:12px;background:var(--surface);color:var(--ink);}
  .search input:focus{outline:none;border-color:var(--accent);background:#fff;}
  .filelist{overflow:auto;flex:1;min-height:0;}
  .frow{display:flex;align-items:center;gap:9px;padding:9px 12px;border-left:2px solid transparent;cursor:pointer;}
  .frow:hover{background:var(--surface-2);}
  .frow.active{background:var(--accent-weak);border-left-color:var(--accent);}
  .fname{font-size:12.5px;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
  .fmeta{display:flex;gap:6px;align-items:center;margin-top:2px;}
  .badge{font-size:10px;padding:1px 6px;border-radius:3px;background:var(--surface-2);color:var(--ink-2);border:1px solid var(--border);}
  .frow.active .badge{background:#fff;}
  .cnt{font-size:11px;color:var(--ink-3);}
  .main{display:flex;flex-direction:column;min-width:0;min-height:0;}
  .toolbar{background:var(--bg);border-bottom:1px solid var(--border);padding:10px 16px;display:flex;align-items:center;gap:18px;flex-wrap:wrap;}
  .ctrl{display:flex;align-items:center;gap:8px;}
  .ctrl label{font-size:11.5px;color:var(--ink-2);}
  .ctrl input[type=range]{width:120px;accent-color:var(--accent);}
  .ctrl .val{font-family:var(--mono);font-size:12px;color:var(--ink);min-width:30px;}
  select{padding:5px 8px;border:1px solid var(--border);border-radius:5px;font-size:12px;background:#fff;color:var(--ink);}
  .btn{padding:6px 13px;border-radius:5px;font-size:12.5px;border:1px solid var(--border-strong);background:#fff;color:var(--ink);}
  .btn:hover{background:var(--surface-2);}
  .btn.primary{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600;}
  .btn.primary:hover{background:#d2560f;}
  .btn.ghost{border-color:transparent;color:var(--ink-2);}
  .spacer{margin-left:auto;}
  .compare{flex:1;display:grid;grid-template-columns:1fr 1fr;gap:0;min-height:0;}
  .col{display:flex;flex-direction:column;min-height:0;border-right:1px solid var(--border);}
  .col:last-child{border-right:none;}
  .colhdr{padding:9px 16px;background:var(--surface);border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px;position:sticky;top:0;}
  .colhdr .lab{font-size:12px;font-weight:600;}
  .colhdr .sub{font-family:var(--mono);font-size:11px;color:var(--ink-2);}
  .colhdr .pill{margin-left:auto;font-size:11px;color:var(--ink-2);}
  .chunks{overflow:auto;padding:12px;flex:1;min-height:0;}
  .chunk{display:grid;grid-template-columns:3px 1fr;gap:0;background:#fff;border:1px solid var(--border);border-radius:5px;margin-bottom:9px;overflow:hidden;cursor:pointer;transition:border-color .12s;}
  .chunk:hover{border-color:var(--border-strong);}
  .chunk.sel{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent);}
  .qbar{width:3px;}
  .qbar.good{background:var(--q-good);} .qbar.mid{background:var(--q-mid);} .qbar.bad{background:var(--q-bad);}
  .cbody{padding:9px 11px;min-width:0;}
  .cmeta{display:flex;align-items:center;gap:8px;margin-bottom:5px;}
  .cidx{font-family:var(--mono);font-size:11px;color:var(--ink-3);}
  .csrc{font-size:11px;color:var(--ink-2);}
  .ctok{margin-left:auto;font-family:var(--mono);font-size:10.5px;padding:1px 6px;border-radius:3px;background:var(--surface-2);color:var(--ink-2);}
  .ctok.over{background:#fbe3e3;color:var(--q-bad);}
  .ctext{font-size:12px;color:var(--ink);display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;}
  .chunk.diff-added{background:#f1faf3;border-color:#bfe6c9;}
  .chunk.diff-changed{background:#fff8ec;border-color:#f0d79a;}
  .chunk.diff-same{opacity:.45;}
  .ctag{font-size:10px;padding:1px 6px;border-radius:3px;}
  .ctag.added{background:#e6f6ea;color:#1c7d35;} .ctag.changed{background:#fbf1d8;color:#9a6c00;}
  .scrim{position:fixed;inset:0;background:rgba(31,35,40,.28);opacity:0;pointer-events:none;transition:opacity .18s;z-index:40;}
  .scrim.open{opacity:1;pointer-events:auto;}
  .panel{position:fixed;top:0;right:0;height:100vh;width:52%;max-width:760px;background:#fff;border-left:1px solid var(--border);transform:translateX(100%);transition:transform .2s ease;z-index:50;display:flex;flex-direction:column;box-shadow:-8px 0 24px rgba(31,35,40,.08);}
  .panel.open{transform:translateX(0);}
  .phdr{display:flex;align-items:center;gap:12px;padding:13px 18px;border-bottom:1px solid var(--border);}
  .phdr .pt{font-size:13.5px;font-weight:600;}
  .phdr .pq{font-size:11px;padding:2px 8px;border-radius:3px;}
  .pq.good{background:#e6f6ea;color:#1c7d35;} .pq.mid{background:#fbf1d8;color:#9a6c00;} .pq.bad{background:#fbe3e3;color:#9a2b2b;}
  .pclose{margin-left:auto;border:none;background:none;font-size:20px;color:var(--ink-2);line-height:1;padding:2px 6px;}
  .ptabs{display:flex;gap:2px;padding:0 18px;border-bottom:1px solid var(--border);}
  .ptab{padding:9px 12px;font-size:12.5px;color:var(--ink-2);border-bottom:2px solid transparent;}
  .ptab.active{color:var(--accent);border-bottom-color:var(--accent);font-weight:600;}
  .pbody{overflow:auto;padding:18px;flex:1;min-height:0;}
  .ptitle-path{font-size:11.5px;color:var(--ink-2);margin-bottom:12px;}
  .ptitle-path b{color:var(--ink);}
  .ptext{font-family:var(--mono);font-size:12.5px;line-height:1.7;white-space:pre-wrap;color:var(--ink);background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:14px;}
  .meta-grid{display:grid;grid-template-columns:120px 1fr;gap:8px 14px;margin-top:16px;font-size:12.5px;}
  .meta-grid .k{color:var(--ink-2);}
  .meta-grid .v{font-family:var(--mono);color:var(--ink);}
  .pane{display:none;} .pane.active{display:block;}
  .ocr-img{width:100%;border:1px solid var(--border);border-radius:6px;background:var(--surface-2);height:300px;display:flex;align-items:center;justify-content:center;color:var(--ink-3);font-size:12px;}
  .struct{font-family:var(--mono);font-size:12px;white-space:pre-wrap;background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:14px;color:var(--ink);}
  .legend{display:flex;gap:14px;align-items:center;font-size:11px;color:var(--ink-2);}
  .legend .d{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:4px;vertical-align:middle;}
  .hint{padding:3px 10px;background:var(--accent-weak);color:#9a4310;border-radius:4px;font-size:11px;}
</style>
</head>
<body>
<div class="app">
  <div class="topbar">
    <span class="brand">切片工作台<span class="dot">.</span></span>
    <span class="crumb">对比 / <b id="crumbFile">新契約手続きガイド.pptx</b></span>
    <div class="top-actions">
      <button class="btn ghost">刷新</button>
      <button class="btn">草稿版本</button>
    </div>
  </div>
  <div class="body">
    <aside class="side">
      <nav class="nav">
        <div class="nav-item active"><svg class="ic" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><rect x="1.5" y="2.5" width="5" height="11"/><rect x="9.5" y="2.5" width="5" height="11"/></svg>切块对比</div>
        <div class="nav-item"><svg class="ic" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M2 4h12M2 8h12M2 12h8"/></svg>草稿版本</div>
        <div class="nav-item"><svg class="ic" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M8 2l5 3v6l-5 3-5-3V5z"/></svg>文件结构</div>
      </nav>
      <div class="filehdr"><span class="t">文档清单</span><span class="cnt" id="fcount">4 个文件</span></div>
      <div class="search"><input placeholder="搜索文件名…"></div>
      <div class="filelist" id="filelist"></div>
    </aside>
    <main class="main">
      <div class="toolbar">
        <div class="ctrl"><label>chunk_size</label><input type="range" min="120" max="1200" value="520" id="szRange"><span class="val" id="szVal">520</span></div>
        <div class="ctrl"><label>overlap</label><input type="range" min="0" max="300" value="80" id="ovRange"><span class="val" id="ovVal">80</span></div>
        <div class="ctrl"><label>类型</label>
          <select><option>默认</option><option selected>PPT</option><option>OCR 图块</option><option>PDF 文本</option></select>
        </div>
        <button class="btn primary" id="genBtn">生成预览</button>
        <div class="spacer"></div>
        <div class="legend"><span><i class="d" style="background:var(--q-good)"></i>干净</span><span><i class="d" style="background:var(--q-mid)"></i>半截</span><span><i class="d" style="background:var(--q-bad)"></i>硬切</span></div>
        <button class="btn">保存为草稿</button>
        <button class="btn primary" style="background:#1f2328;border-color:#1f2328;">应用到知识库</button>
      </div>
      <div class="compare">
        <section class="col">
          <div class="colhdr"><span class="lab">当前切法</span><span class="sub">size 520 · overlap 80</span><span class="pill" id="curCount">— 块</span></div>
          <div class="chunks" id="colCur"></div>
        </section>
        <section class="col">
          <div class="colhdr"><span class="lab">新参数预览</span><span class="sub" id="newParams">size 520 · overlap 80</span><span class="pill" id="diffSummary"></span><span class="pill" id="newCount">点生成预览</span></div>
          <div class="chunks" id="colNew"></div>
        </section>
      </div>
    </main>
  </div>
</div>
<div class="scrim" id="scrim"></div>
<aside class="panel" id="panel">
  <div class="phdr"><span class="pt" id="pTitle">Chunk #3</span><span class="pq good" id="pQual">干净</span><button class="pclose" id="pClose">×</button></div>
  <div class="ptabs">
    <div class="ptab active" data-pane="text">文本</div>
    <div class="ptab" data-pane="meta">元数据</div>
    <div class="ptab" data-pane="img">原图 (OCR)</div>
    <div class="ptab" data-pane="struct">结构化</div>
  </div>
  <div class="pbody">
    <div class="ptitle-path" id="pPath"></div>
    <div class="pane active" data-pane="text"><div class="ptext" id="pText"></div></div>
    <div class="pane" data-pane="meta">
      <div class="meta-grid">
        <span class="k">来源</span><span class="v" id="mSrc"></span>
        <span class="k">block_type</span><span class="v" id="mType"></span>
        <span class="k">token 数</span><span class="v" id="mTok"></span>
        <span class="k">字符数</span><span class="v" id="mChar"></span>
        <span class="k">切片质量</span><span class="v" id="mQual"></span>
        <span class="k">artifact</span><span class="v" id="mArt"></span>
      </div>
    </div>
    <div class="pane" data-pane="img"><div class="ocr-img">［ 这里显示该 chunk 对应的 OCR 原图 ］</div></div>
    <div class="pane" data-pane="struct"><div class="struct" id="pStruct"></div></div>
  </div>
</aside>
<script>
const FILES=[
  {name:"新契約手続きガイド.pptx",type:"PPTX",chunks:34},
  {name:"商品仕様書_医療保険.xlsx",type:"XLSX",chunks:58},
  {name:"約款_がん保険2026.pdf",type:"PDF",chunks:112},
  {name:"募集人向けFAQ.pptx",type:"PPTX",chunks:21},
];
const SAMPLE=[
  {src:"スライド 3",type:"heading",q:"good",tok:142,text:"第1章 新契約の手続き概要\n本章では、新規契約の申込みから成立までの流れを説明します。"},
  {src:"スライド 4",type:"body",q:"good",tok:386,text:"申込書の受付にあたっては、記入漏れ・押印漏れがないことを確認してください。告知事項は正確に記入する必要があります。"},
  {src:"スライド 5 (図)",type:"ocr-block",q:"mid",tok:512,text:"［図: 審査フロー］ 告知内容の確認 → 医的審査 → 査定 → 承諾可否の判定。"},
  {src:"スライド 6 (表)",type:"table",q:"bad",tok:874,text:"保障内容一覧(抜粋): 入院給付金 日額5,000円 / 手術給付金 10・20・40倍 / 死亡保険金 300万円 …(表が途中で切れています)"},
  {src:"スライド 7",type:"body",q:"good",tok:298,text:"成立後は、契約者へ証券を送付します。クーリングオフの対象となる場合は書面を同封してください。"},
  {src:"スライド 8",type:"body",q:"mid",tok:455,text:"保険料の払込方法には、口座振替・クレジットカード・団体扱いがあります。払込猶予期間を過ぎると失効します。"},
];
const QLABEL={good:"干净",mid:"半截",bad:"硬切"};
function renderFiles(){
  const el=document.getElementById('filelist');
  el.innerHTML=FILES.map((f,i)=>`
    <div class="frow ${i===0?'active':''}" data-i="${i}">
      <div style="min-width:0;flex:1">
        <div class="fname">${f.name}</div>
        <div class="fmeta"><span class="badge">${f.type}</span><span class="cnt">${f.chunks} chunks</span></div>
      </div>
    </div>`).join('');
  el.querySelectorAll('.frow').forEach(r=>r.onclick=()=>{
    el.querySelectorAll('.frow').forEach(x=>x.classList.remove('active'));
    r.classList.add('active');
    document.getElementById('crumbFile').textContent=FILES[r.dataset.i].name;
  });
}
function chunkCard(c,idx,status){
  const tag = status==='added'?'<span class="ctag added">新增</span>':status==='changed'?'<span class="ctag changed">边界调整</span>':'';
  const cls = status?('diff-'+status):'';
  return `<div class="chunk ${cls}" data-i="${idx}">
    <div class="qbar ${c.q}"></div>
    <div class="cbody">
      <div class="cmeta"><span class="cidx">#${idx+1}</span><span class="csrc">${c.src}</span>${tag}<span class="ctok ${c.tok>800?'over':''}">${c.tok} tok</span></div>
      <div class="ctext">${c.text}</div>
    </div>
  </div>`;
}
function renderCol(id,data,statuses){
  const el=document.getElementById(id);
  el.innerHTML=data.map((c,i)=>chunkCard(c,i,statuses?statuses[i]:null)).join('');
  el.querySelectorAll('.chunk').forEach(ch=>ch.onclick=()=>openPanel(data[ch.dataset.i],ch.dataset.i,el));
}
function openPanel(c,i,scopeEl){
  document.querySelectorAll('.chunk.sel').forEach(x=>x.classList.remove('sel'));
  scopeEl.querySelectorAll('.chunk')[i].classList.add('sel');
  document.getElementById('pTitle').textContent='Chunk #'+(Number(i)+1);
  const pq=document.getElementById('pQual'); pq.className='pq '+c.q; pq.textContent=QLABEL[c.q];
  document.getElementById('pPath').innerHTML='<b>'+FILES[0].name+'</b> › '+c.src;
  document.getElementById('pText').textContent=c.text;
  document.getElementById('mSrc').textContent=c.src;
  document.getElementById('mType').textContent=c.type;
  document.getElementById('mTok').textContent=c.tok+(c.tok>800?'  超长':'');
  document.getElementById('mChar').textContent=c.text.length;
  document.getElementById('mQual').textContent=QLABEL[c.q];
  document.getElementById('mArt').textContent='data/artifacts/slide-'+c.src.replace(/\D/g,'')+'.json';
  document.getElementById('pStruct').textContent=JSON.stringify({source:c.src,block_type:c.type,tokens:c.tok,title_path:[FILES[0].name,c.src]},null,2);
  document.getElementById('panel').classList.add('open');
  document.getElementById('scrim').classList.add('open');
}
function closePanel(){document.getElementById('panel').classList.remove('open');document.getElementById('scrim').classList.remove('open');document.querySelectorAll('.chunk.sel').forEach(x=>x.classList.remove('sel'));}
document.getElementById('scrim').onclick=closePanel;
document.getElementById('pClose').onclick=closePanel;
document.querySelectorAll('.ptab').forEach(t=>t.onclick=()=>{
  document.querySelectorAll('.ptab').forEach(x=>x.classList.remove('active'));t.classList.add('active');
  document.querySelectorAll('.pane').forEach(p=>p.classList.toggle('active',p.dataset.pane===t.dataset.pane));
});
const sz=document.getElementById('szRange'),ov=document.getElementById('ovRange');
sz.oninput=()=>document.getElementById('szVal').textContent=sz.value;
ov.oninput=()=>document.getElementById('ovVal').textContent=ov.value;
document.getElementById('genBtn').onclick=()=>{
  document.getElementById('newParams').textContent=`size ${sz.value} · overlap ${ov.value}`;
  const smaller=sz.value<520;
  let data=JSON.parse(JSON.stringify(SAMPLE));
  let statuses=data.map(()=>'same');
  if(smaller){
    data[3]={...data[3],q:"mid",tok:620,text:data[3].text.replace("(表が途中で切れています)","")};
    statuses[3]='changed';
    data.splice(4,0,{src:"スライド 6 (表 続)",type:"table",q:"good",tok:410,text:"…死亡保険金 300万円 / 入院一時金 10万円 (前のチャンクから分割)"});
    statuses.splice(4,0,'added');
  }else{ data[5]={...data[5],tok:505}; statuses[5]='changed'; }
  renderCol('colNew',data,statuses);
  document.getElementById('newCount').textContent=data.length+' 块';
  const nAdd=statuses.filter(s=>s==='added').length, nChg=statuses.filter(s=>s==='changed').length;
  document.getElementById('diffSummary').textContent=`新增 ${nAdd} · 调整 ${nChg}`;
};
renderFiles();
renderCol('colCur',SAMPLE);
document.getElementById('curCount').textContent=SAMPLE.length+' 块';
</script>
</body>
</html>