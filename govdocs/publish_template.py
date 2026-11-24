"""HTML template for the static search page (imported by govdocs.py publish)."""

SEARCH_PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>German Government documents index</title>
<style>
  :root{
    --paper:#fbfbf8; --ink:#24291f; --meta:#6b7062;
    --rule:#d9dad2; --navy:#1f3a5f; --navy-soft:#eef1f4;
    --cols:minmax(260px,1.1fr) 1.25fr 150px 92px 132px;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--paper);color:var(--ink);
       font:15px/1.5 "Avenir Next","Segoe UI",system-ui,sans-serif}
  .wrap{max-width:1200px;margin:0 auto;padding:28px 20px 80px}
  header{display:flex;justify-content:space-between;align-items:flex-end;
       gap:24px}
  header h1{font-family:"Iowan Old Style",Georgia,"Times New Roman",serif;
       font-weight:600;font-size:34px;line-height:1.15;margin:0;
       letter-spacing:.2px}
  header h1{flex:1 1 auto;min-width:0}
  header .meta-block{flex:0 0 auto;text-align:right;font-size:12.5px;
       line-height:1.6;white-space:nowrap}
  header p{margin:0;color:var(--meta)}
  .controls{display:flex;gap:10px;align-items:center;flex-wrap:wrap;
       padding:16px 0 10px;border-top:1px solid var(--rule);margin-top:16px}
  .controls input[type=search]{flex:1 1 200px;min-width:170px;
       padding:9px 12px;font:inherit;
       border:1px solid var(--rule);border-radius:3px;background:#fff;color:var(--ink)}
  .controls input:focus,.controls button:focus,.controls select:focus{
       outline:2px solid var(--navy);outline-offset:1px}
  .controls .dates{display:flex;gap:6px;align-items:center;color:var(--meta);
       flex:0 0 auto;font-size:13px}
  .controls input[type=date]{padding:8px;font:inherit;font-size:13px;
       border:1px solid var(--rule);border-radius:3px;background:#fff;color:var(--ink)}
  .controls select{flex:0 1 140px;padding:9px 8px;font:inherit;
       border:1px solid var(--rule);border-radius:3px;background:#fff;color:var(--ink)}
  .info{flex:0 0 auto;display:inline-flex;align-items:center;
       justify-content:center;width:22px;height:22px;border-radius:50%;
       border:1px solid var(--rule);color:var(--meta);font-size:13px;
       cursor:help;user-select:none}
  .info:hover{border-color:var(--navy);color:var(--navy)}
  .switcher{display:flex;gap:8px;justify-content:flex-end;margin:0 0 4px}
  .ctry{font-size:12px;padding:2px 7px;border:1px solid var(--rule);
       border-radius:11px;color:var(--meta);text-decoration:none;white-space:nowrap}
  .ctry.other:hover{border-color:var(--navy);color:var(--navy)}
  .ctry.soon{opacity:.5}
  .langtog{display:inline-flex;border:1px solid var(--rule);border-radius:3px;
       overflow:hidden;vertical-align:middle}
  .langtog button{font:inherit;font-size:11px;padding:2px 8px;border:0;
       background:#fff;color:var(--meta);cursor:pointer}
  .langtog button.on{background:var(--navy);color:#fff}
  .altlang{display:block;font-size:12.5px;color:var(--meta);
       font-style:italic;margin-top:1px}
  /* multiselect */
  .ms{position:relative;flex:0 0 auto}
  .ms > button{font:inherit;padding:9px 12px;border:1px solid var(--rule);
       border-radius:3px;background:#fff;color:var(--ink);cursor:pointer;
       min-width:130px;text-align:left}
  .ms.open > button{border-color:var(--navy)}
  .ms .panel{display:none;position:absolute;z-index:10;top:calc(100% + 4px);
       left:0;min-width:240px;max-height:320px;overflow:auto;background:#fff;
       border:1px solid var(--rule);border-radius:3px;
       box-shadow:0 2px 8px rgba(36,41,31,.12);padding:6px 0}
  .ms.open .panel{display:block}
  .ms label{display:block;padding:5px 12px;font-size:13.5px;cursor:pointer;
       white-space:nowrap}
  .ms label:hover{background:var(--navy-soft)}
  .ms input{margin-right:8px}
  .ms .clear{display:block;width:100%;text-align:left;font:inherit;
       font-size:13px;color:var(--navy);background:none;border:none;
       border-bottom:1px solid var(--rule);padding:6px 12px 8px;cursor:pointer}
  .ms .filter{display:block;width:calc(100% - 24px);margin:8px 12px 4px;
       padding:6px 8px;font:inherit;font-size:13px;
       border:1px solid var(--rule);border-radius:3px}
  ul.docs li.year-sep{display:block;font-family:"Iowan Old Style",Georgia,serif;
       font-size:20px;font-weight:600;color:var(--ink);
       background:#efefe8;border-top:2px solid var(--ink);
       border-bottom:2px solid var(--ink);
       padding:8px 12px;margin-top:22px}
  ul.docs li.day-sep{display:block;background:#f4f4ee;
       border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);
       padding:6px 12px;margin-top:8px}
  ul.docs li.day-sep button{font:inherit;font-size:13px;font-weight:600;
       color:var(--ink);background:none;border:none;cursor:pointer;padding:0;
       text-align:left;width:100%}
  ul.docs li.day-sep button:hover{color:var(--navy)}
  ul.docs li.day-sep .n{color:var(--meta);font-weight:400}
  .toolbar #count{color:var(--meta);font-size:13.5px}
  .pager{display:flex;gap:10px;align-items:center;justify-content:flex-end;
       margin:14px 0;color:var(--meta)}
  .toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;
       margin:14px 0;color:var(--meta)}
  .toolbar .grow{flex:1 1 auto}
  .toolbar select,.toolbar button{font:inherit;font-size:13.5px;
       padding:7px 10px;border:1px solid var(--rule);border-radius:3px;
       background:#fff;color:var(--ink)}
  .toolbar button{color:var(--navy);cursor:pointer}
  .toolbar button:hover{border-color:var(--navy)}
  .toolbar button.on{background:var(--navy-soft);border-color:var(--navy);
       font-weight:600}
  .banner{margin:10px 0;padding:8px 12px;background:var(--navy-soft);
       color:var(--navy);font-size:13.5px;border-radius:3px;
       display:flex;gap:12px;align-items:center}
  .banner a{color:var(--navy)}
  .banner button{font:inherit;font-size:12.5px;color:var(--navy);
       background:#fff;border:1px solid var(--navy);border-radius:3px;
       padding:2px 9px;cursor:pointer}
  .pager button{font:inherit;padding:6px 14px;border:1px solid var(--rule);
       border-radius:3px;background:#fff;color:var(--navy);cursor:pointer}
  .pager button:disabled{color:var(--rule);cursor:default}
  .pager button:not(:disabled):hover{border-color:var(--navy)}
  .head{display:grid;grid-template-columns:var(--cols);gap:6px 16px;
       padding:8px 0 6px;border-bottom:2px solid var(--ink);
       color:var(--meta);font-size:12px;letter-spacing:.3px}
  .head .h-date{text-align:right}
  ul.docs{list-style:none;margin:0;padding:0}
  ul.docs li{display:grid;grid-template-columns:var(--cols);
       gap:6px 16px;align-items:baseline;
       padding:9px 0;border-bottom:1px solid var(--rule)}
  ul.docs li.newday{border-top:2px solid var(--ink);
       margin-top:18px;padding-top:14px}
  ul.docs li.grp{border-top:2px solid #c8c9bd}
  ul.docs li:first-child.newday{border-top:none;margin-top:0;padding-top:9px}
  .title{min-width:0}
  ul.docs a{color:var(--navy);text-decoration:none}
  ul.docs a:hover,ul.docs a:focus{text-decoration:underline}
  .att{color:var(--meta);font-size:13px}
  .summ strong{color:var(--ink);font-weight:600}
  .summ{color:var(--meta);font-size:12.5px;line-height:1.45;
       display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;
       overflow:hidden}
  .summ.clipped{cursor:pointer}
  .summ.clipped:hover{color:var(--ink)}
  .summ.expanded{display:block;-webkit-line-clamp:unset;overflow:visible;
       cursor:pointer}
  .agency{justify-self:start;background:var(--navy-soft);color:var(--navy);
       cursor:pointer;
       padding:1px 7px;border-radius:3px;font-size:12.5px;line-height:1.35;
       max-width:100%}
  .type{color:var(--meta);font-size:13px;white-space:nowrap;
       overflow:hidden;text-overflow:ellipsis}
  .date{text-align:right;color:var(--meta);font-size:13px;
       font-variant-numeric:tabular-nums;white-space:nowrap}
  .empty{padding:40px 0;color:var(--meta)}
  .quick{position:fixed;top:130px;left:calc(50% + 612px);width:185px;
       border-left:2px solid var(--ink);padding:2px 0 2px 14px}
  .quick h3{font-family:"Iowan Old Style",Georgia,serif;font-weight:600;
       font-size:15px;margin:0 0 8px;color:var(--ink)}
  .quick button{display:block;width:100%;text-align:left;font:inherit;
       font-size:13.5px;color:var(--navy);background:none;border:none;
       cursor:pointer;padding:3px 0}
  .quick button:hover{text-decoration:underline}
  .quick button.active{font-weight:700}
  .quick .rm{color:var(--meta);margin-left:7px;font-weight:400;cursor:pointer}
  .quick .rm:hover{color:#8a3b2e}
  .quick .add{margin-top:8px;color:var(--meta);font-size:12.5px;
       border-top:1px solid var(--rule);padding-top:8px}
  .quick .add:hover{color:var(--navy)}
  .newsrail{position:fixed;top:130px;right:calc(50% + 616px);width:205px;
       border-right:2px solid var(--ink);padding:2px 14px 2px 0;
       max-height:76vh;overflow-y:auto}
  .newsrail h3{font-family:"Iowan Old Style",Georgia,serif;font-weight:600;
       font-size:15px;margin:0 0 2px;color:var(--ink)}
  .newsrail .since{color:var(--meta);font-size:12px;margin:0 0 10px}
  .newsrail h4{margin:12px 0 3px}
  .newsrail h4 button{font:inherit;font-size:13px;font-weight:700;
       color:var(--navy);background:none;border:none;cursor:pointer;padding:0}
  .newsrail h4 button:hover{text-decoration:underline}
  .newsrail h4 .n{color:var(--meta);font-weight:400}
  .newsrail a{display:block;color:var(--navy);text-decoration:none;
       font-size:12.5px;line-height:1.4;margin:3px 0;white-space:nowrap;
       overflow:hidden;text-overflow:ellipsis}
  .newsrail a:hover{text-decoration:underline}
  .newsrail .none{color:var(--meta);font-size:12.5px}
  @media (max-width:1640px){
    .newsrail{display:none}
    .quick{position:static;width:auto;border-left:none;
       border-bottom:1px solid var(--rule);padding:6px 0 8px;margin:0}
    .quick #quickList{display:flex;flex-wrap:wrap;gap:2px 16px;
       align-items:baseline}
    .quick h3{display:inline;font-size:13px;margin:0 14px 0 0}
    .quick button{display:inline;width:auto;padding:2px 0}
    .quick .add{margin:0;border-top:none;padding-top:2px}
  }
  ul.docs li.more-row{display:block;padding:7px 14px;margin:4px 0 4px -34px;
       background:var(--navy-soft);border-left:3px solid var(--navy);
       border-radius:0 3px 3px 0}
  ul.docs li.more-row button{font:inherit;font-size:13px;font-weight:600;
       color:var(--navy);background:none;border:none;cursor:pointer;
       padding:0;text-align:left;width:100%;white-space:nowrap;
       overflow:hidden;text-overflow:ellipsis}
  ul.docs li.more-row button:hover{text-decoration:underline}
  .ms .mode{display:block;padding:6px 12px;border-bottom:1px solid var(--rule);
       font-size:13px;color:var(--meta)}
  @media (max-width:900px){
    .controls{flex-wrap:wrap}
  }
  @media (max-width:760px){
    header{flex-direction:column;align-items:flex-start}
    header .meta-block{text-align:left;white-space:normal}
    header h1{font-size:27px}
    ul.docs li.more-row{margin-left:-14px}
    .head{display:none}
    ul.docs li{grid-template-columns:1fr 88px;grid-auto-flow:dense}
    .title{grid-column:1 / -1}
    .summ{grid-column:1 / -1}
    .date{text-align:right}
  }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>German Government documents index</h1>
    <div class="meta-block">
      <p class="switcher">
        <span class="ctry" title="This index">🇩🇪 Germany</span>
        <a class="ctry other" href="../au/" title="Australian index">🇦🇺 Australia</a>
        <span class="ctry soon" title="More countries coming">+</span>
      </p>
      <p id="sub1">Loading&hellip;</p>
      <p id="sub2"></p>
      <p>
        <span class="langtog" title="Which language leads each title">
          <button id="langEN" class="on">EN</button><button id="langDE">DE</button>
        </span>
        &nbsp;<a href="coverage.html" style="color:var(--navy)">Coverage register &rarr;</a>
      </p>
    </div>
  </header>
  <div class="controls">
    <input id="q" type="search"
           placeholder="Search titles, summaries, links, agencies"
           aria-label="Search documents">
    <span class="info" tabindex="0"
      title="Search matches exact text: every word you type must appear somewhere in the title, summary, link or agency. No fuzzy matching — try shorter word stems (&quot;consult&quot; matches &quot;consultation&quot;).">?</span>
    <div class="ms" id="msAgency"></div>
    <div class="ms" id="msType"></div>
    <select id="rel" aria-label="Filter by relevance"><option value="">All relevance</option></select>
    <span class="dates">
      <label for="from">from</label><input id="from" type="date">
      <label for="to">to</label><input id="to" type="date">
    </span>
  </div>
  <aside class="quick" aria-label="Common searches">
    <div id="quickList"><h3>Common searches</h3></div>
  </aside>
  <aside class="newsrail" id="newsRail" style="display:none"
         aria-label="New in your topics"></aside>
  <div class="toolbar">
    <span id="count"></span>
    <button id="newSince" style="display:none"></button>
    <button id="digest">Last 7 days</button>
    <label for="sort">Sort</label>
    <select id="sort">
      <option value="date-desc">Newest first</option>
      <option value="date-asc">Oldest first</option>
      <option value="agency">Agency</option>
      <option value="title">Title</option>
    </select>
    <button id="csv" type="button">Export CSV</button>
    <button id="share" type="button">Copy link to this search</button>
    <span class="grow"></span>
    <span class="pager" style="margin:0">
      <button id="prevT">&larr; Previous</button>
      <span id="pageT"></span><button id="nextT">Next &rarr;</button></span>
  </div>
  <div class="banner" id="agBanner" style="display:none"></div>
  <div class="head"><span>Title</span><span>Summary</span><span>Agency</span>
    <span>Type</span><span class="h-date">Date</span></div>
  <div id="results"></div>
  <div class="pager"><button id="prevB">&larr; Previous</button>
    <span id="pageB"></span><button id="nextB">Next &rarr;</button></div>
</div>
<script>
(function(){
  "use strict";
  var DATA=[], CAP=400, PAGE=0, EXPANDED={}, DAYCOL={};
  var LANG="en"; // page title language: "en" lead (default) or "de"
  var NEWONLY=false, DIGEST=false, PREV_VISIT=null;
  var q=document.getElementById("q"),
      relSel=document.getElementById("rel"),
      fromIn=document.getElementById("from"),
      toIn=document.getElementById("to"),
      out=document.getElementById("results"),
      count=document.getElementById("count");

  function esc(s){var d=document.createElement("div");d.textContent=s==null?"":s;return d.innerHTML;}
  var HL=null;
  function hl(s){
    if(s==null) s="";
    if(!HL) return esc(s);
    var out="",last=0,m;
    HL.lastIndex=0;
    while((m=HL.exec(s))!==null){
      out+=esc(s.slice(last,m.index))+"<strong>"+esc(m[0])+"</strong>";
      last=m.index+m[0].length;
      if(m[0].length===0){HL.lastIndex++;}
    }
    return out+esc(s.slice(last));
  }
  var MONTHS=["January","February","March","April","May","June","July",
    "August","September","October","November","December"];
  function fmtDate(s){
    if(!s) return "";
    if(s.length===4) return s;
    var p=s.split("-");
    return parseInt(p[2],10)+" "+MONTHS[parseInt(p[1],10)-1]+" "+p[0];
  }
  function labelDE(d){
    if(d.title) return d.title;
    var seg=d.url.replace(/\/+$/,"").split("/").pop()||d.url;
    try{seg=decodeURIComponent(seg);}catch(e){}
    return seg.replace(/[-_]+/g," ").replace(/\.(pdf|docx?|xlsx?|pptx?|csv|rtf|odt)$/i," ($1)");
  }
  // English translation when present, else fall back to the German.
  function labelEN(d){ return d.title_en || labelDE(d); }
  // Primary label follows the page language toggle (default: English lead).
  function label(d){ return LANG==="de" ? labelDE(d) : labelEN(d); }
  // The secondary line under the title shows the OTHER language.
  function labelAlt(d){
    var en=d.title_en, de=(d.title||"");
    if(LANG==="de"){ return en && en!==de ? en : ""; }
    return de && de!==(d.title_en||"") ? de : "";
  }
  // Fold umlauts + ß so "wasser" matches "Wärme", "grusse" matches "Grüße".
  // Normalise German for search: strip umlauts to their base vowel and ß->ss,
  // so a plain-keyboard "warme"/"grusse" matches "Wärme"/"Grüße", and the
  // "ae/oe/ue" spellings match too (both reduce to the same base here).
  function fold(s){ return (s||"").toLowerCase()
      .replace(/ä/g,"a").replace(/ö/g,"o").replace(/ü/g,"u")
      .replace(/ß/g,"ss").replace(/ae/g,"a").replace(/oe/g,"o").replace(/ue/g,"u"); }

  // compact checkbox multiselect
  function multiSelect(elId, labelAll, noun, withExclude){
    var root=document.getElementById(elId),
        chosen=new Set(),
        btn=document.createElement("button"),
        panel=document.createElement("div"),
        countEls={}, exclude=false;
    btn.type="button"; btn.textContent=labelAll;
    btn.setAttribute("aria-haspopup","true");
    panel.className="panel";
    root.appendChild(btn); root.appendChild(panel);
    btn.addEventListener("click",function(e){
      e.stopPropagation();
      root.classList.toggle("open");
    });
    document.addEventListener("click",function(e){
      if(!root.contains(e.target)) root.classList.remove("open");
    });
    function refreshBtn(){
      btn.textContent = chosen.size
        ? chosen.size+" "+noun+(chosen.size===1?"":"s")
          +(exclude?" excluded":"")
        : labelAll;
    }
    var api={
      set: chosen,
      isExclude: function(){return exclude;},
      setOnly: function(v){
        chosen.clear(); if(v!=null) chosen.add(v);
        exclude=false;
        panel.querySelectorAll("input[type=checkbox]").forEach(function(c){
          c.checked = chosen.has(c.value);
        });
        refreshBtn();
      },
      setExclude: function(v){exclude=!!v;refreshBtn();},
      setCounts: function(map){
        Object.keys(countEls).forEach(function(v){
          countEls[v].textContent=" ("+(map[v]||0)+")";
        });
      },
      fill: function(values, preset){
        (preset||[]).forEach(function(v){chosen.add(v);});
        panel.innerHTML="";
        countEls={};
        if(withExclude){
          var mode=document.createElement("label");
          mode.className="mode";
          var mc=document.createElement("input");
          mc.type="checkbox"; mc.checked=exclude;
          mc.addEventListener("change",function(){
            exclude=mc.checked; refreshBtn(); PAGE=0; render();
          });
          mode.appendChild(mc);
          mode.appendChild(document.createTextNode(
            "Exclude ticked "+noun+"s (hide instead of show)"));
          panel.appendChild(mode);
        }
        if(values.length>15){
          var f=document.createElement("input");
          f.type="search"; f.className="filter";
          f.placeholder="Type to filter "+noun+" list\u2026";
          f.addEventListener("input",function(){
            var n=f.value.toLowerCase();
            panel.querySelectorAll("label:not(.mode)").forEach(function(l){
              l.style.display =
                l.textContent.toLowerCase().indexOf(n)>-1 ? "" : "none";
            });
          });
          panel.appendChild(f);
        }
        var clear=document.createElement("button");
        clear.type="button"; clear.className="clear";
        clear.textContent="Clear selection";
        clear.addEventListener("click",function(){
          chosen.clear();
          panel.querySelectorAll("input").forEach(function(c){c.checked=false;});
          refreshBtn(); PAGE=0; render();
        });
        panel.appendChild(clear);
        values.sort().forEach(function(v){
          var lab=document.createElement("label"),
              cb=document.createElement("input");
          cb.type="checkbox"; cb.value=v;
          cb.checked=chosen.has(v);
          cb.addEventListener("change",function(){
            if(cb.checked) chosen.add(v); else chosen.delete(v);
            refreshBtn(); PAGE=0; render();
          });
          lab.appendChild(cb);
          lab.appendChild(document.createTextNode(v));
          var cnt=document.createElement("span");
          cnt.style.color="var(--meta)";
          countEls[v]=cnt;
          lab.appendChild(cnt);
          panel.appendChild(lab);
        });
        refreshBtn();
      }
    };
    return api;
  }
  var msAgency=multiSelect("msAgency","All agencies","agency",true),
      msType=multiSelect("msType","All types","type",false),
      sortSel=document.getElementById("sort");

  function stateToHash(){
    var p=[];
    function add(k,v){if(v)p.push(k+"="+encodeURIComponent(v));}
    add("q",q.value.trim());
    add("agency",Array.from(msAgency.set).join("|"));
    if(msAgency.isExclude()&&msAgency.set.size) add("agmode","ex");
    add("type",Array.from(msType.set).join("|"));
    add("rel",relSel.value);
    add("from",fromIn.value); add("to",toIn.value);
    if(sortSel.value!=="date-desc") add("sort",sortSel.value);
    if(PAGE>0) add("page",String(PAGE+1));
    history.replaceState(null,"",p.length?"#"+p.join("&"):location.pathname+location.search);
  }
  function hashState(){
    var out={};
    location.hash.replace(/^#/,"").split("&").forEach(function(kv){
      if(!kv) return;
      var i=kv.indexOf("="),k=kv.slice(0,i),v=decodeURIComponent(kv.slice(i+1));
      out[k]=v;
    });
    return out;
  }

  function fillSelect(sel,values){
    values.sort().forEach(function(v){
      var o=document.createElement("option");o.value=v;o.textContent=v;sel.appendChild(o);
    });
  }
  function isoDaysAgo(n){
    var x=new Date(Date.now()-n*86400000);
    return x.toISOString().slice(0,10);
  }
  function spanOf(d){
    return d.date.length===4
      ? [d.date+"-01-01", d.date+"-12-31"]
      : [d.date, d.date];
  }
  function sortHits(hits){
    var mode=sortSel.value;
    function key(d){return ((d.date||"")+(d.date&&d.date.length===4?"-01-01":"")); }
    if(mode==="date-asc"){
      hits.sort(function(a,b){return key(a)<key(b)?-1:key(a)>key(b)?1:0;});
    }else if(mode==="agency"){
      hits.sort(function(a,b){
        return a.agency<b.agency?-1:a.agency>b.agency?1:
               key(a)>key(b)?-1:key(a)<key(b)?1:0;});
    }else if(mode==="title"){
      hits.sort(function(a,b){
        var x=label(a).toLowerCase(),y=label(b).toLowerCase();
        return x<y?-1:x>y?1:0;});
    } // date-desc: DATA arrives in that order already
    return hits;
  }
  var LASTHITS=[];
  function render(){
    stateToHash();
    var needle=fold(q.value.trim()),
        rl=relSel.value, from=fromIn.value, to=toIn.value, shown=0;
    var toks=needle?needle.split(/\s+/).filter(function(w){return w;}):[];
    HL=toks.length?new RegExp("("+toks.map(function(w){
      return w.replace(/[.*+?^${}()|[\]\\]/g,"\\$&");
    }).join("|")+")","gi"):null;
    var agCounts={}, tyCounts={}, hits=[];
    var digestFloor = DIGEST ? isoDaysAgo(7) : null;
    DATA.forEach(function(d){
      // conditions shared by every view
      if(rl && (d.relevance||"unscored")!==rl) return;
      if(from||to){
        if(!d.date) return;
        var span=spanOf(d);
        if(from && span[1]<from) return;
        if(to && span[0]>to) return;
      }
      if(NEWONLY && PREV_VISIT && !(d.indexed && d.indexed>PREV_VISIT)) return;
      if(digestFloor && !(d.indexed && d.indexed>=digestFloor)) return;
      if(toks.length){
        var hay=fold(labelEN(d)+" "+labelDE(d)+" "+d.url+" "+d.agency+" "+(d.type||"")+" "+(d.summary||"")+" "+(d.summary_en||""));
        if(!toks.every(function(w){return hay.indexOf(w)>-1;})) return;
      }
      var ty=d.type||"page";
      var okType = !msType.set.size || msType.set.has(ty);
      var picked = msAgency.set.has(d.agency);
      var okAg = !msAgency.set.size ||
                 (msAgency.isExclude() ? !picked : picked);
      if(okType) agCounts[d.agency]=(agCounts[d.agency]||0)+1;
      if(okAg)   tyCounts[ty]=(tyCounts[ty]||0)+1;
      if(okType && okAg) hits.push(d);
    });
    msAgency.setCounts(agCounts);
    msType.setCounts(tyCounts);
    hits=sortHits(hits);
    LASTHITS=hits;
    var GROUP_MAX=10, rows=[];
    if(sortSel.value.indexOf("date")===0){
      // within each day, cluster by agency (first-appearance order); clusters
      // beyond GROUP_MAX collapse behind an expander
      var i2=0, prevYear=null;
      while(i2<hits.length){
        var day=hits[i2].date, dayItems=[];
        while(i2<hits.length && hits[i2].date===day){dayItems.push(hits[i2]);i2++;}
        var yr=day?day.slice(0,4):"Undated";
        if(yr!==prevYear){rows.push({yearsep:yr});prevYear=yr;}
        rows.push({daysep:day, count:dayItems.length});
        if(DAYCOL[day||"undated"]) continue;
        var order=[], byAg={};
        dayItems.forEach(function(d){
          if(!byAg[d.agency]){byAg[d.agency]=[];order.push(d.agency);}
          byAg[d.agency].push(d);
        });
        // quiet voices first: within a day, agencies rank by how little
        // they published — one DFAT item outranks a 500-item Health flood
        order.sort(function(a,b){
          return byAg[a].length-byAg[b].length || (a<b?-1:a>b?1:0);
        });
        order.forEach(function(ag, gi){
          var g=byAg[ag], key=day+"|"+ag;
          g.forEach(function(d, idx){ d._g = (idx===0 && gi>0); });
          if(g.length>GROUP_MAX && !EXPANDED[key]){
            g.slice(0,GROUP_MAX).forEach(function(d){rows.push(d);});
            rows.push({more:g.length-GROUP_MAX, agency:ag, date:day, key:key});
          }else{
            g.forEach(function(d){rows.push(d);});
            if(g.length>GROUP_MAX)
              rows.push({less:true, agency:ag, date:day, key:key});
          }
        });
      }
    }else{
      rows=hits;
    }
    var totalPages=Math.max(1,Math.ceil(rows.length/CAP));
    if(PAGE>=totalPages) PAGE=totalPages-1;
    var start=PAGE*CAP;
    var html=["<ul class='docs'>"], prevDate=null, afterSep=false;
    // a page that opens mid-year still announces its year
    if(rows[start] && !rows[start].yearsep &&
       sortSel.value.indexOf("date")===0){
      var d0=rows[start];
      html.push("<li class='year-sep'>"+
        esc(d0.date?d0.date.slice(0,4):"Undated")+"</li>");
      afterSep=true;
    }
    for(var i=start;i<rows.length && shown<CAP;i++){
      var d=rows[i];
      if(d.yearsep){
        html.push("<li class='year-sep'>"+esc(d.yearsep)+"</li>");
        shown++; afterSep=true;
        continue;
      }
      if(d.daysep!==undefined){
        var dk=d.daysep||"undated",
            col=!!DAYCOL[dk];
        html.push("<li class='day-sep'><button data-day='"+esc(dk)+"'>"+
          (d.daysep?esc(fmtDate(d.daysep)):"Undated")+
          " <span class='n'>("+d.count+(col?" \u2014 collapsed, click to expand":"")+
          ")</span></button></li>");
        shown++; afterSep=true;
        continue;
      }
      if(d.more || d.less){
        var txt=d.more
          ? "+ "+d.more+" more from "+esc(d.agency)+", "+
            (fmtDate(d.date)||"undated")
          : "show fewer from "+esc(d.agency);
        html.push("<li class='more-row'><button data-key='"+esc(d.key)+
          "'>"+txt+"</button></li>");
        shown++;
        prevDate=d.date;
        continue;
      }
      var dayCls=(d._g && !afterSep)?" class='grp'":"";
      prevDate=d.date; afterSep=false;
      var extra="";
      if(d.parent) extra=" <span class='att'>(attachment on <a href='"+esc(d.parent)+
        "' target='_blank' rel='noopener'>page</a>)</span>";
      if(d.relevance==="high") extra+=" <span class='att'>high interest"+
        (d.topic?": "+esc(d.topic):"")+"</span>";
      var alt=labelAlt(d);
      var altHtml=alt?"<span class='altlang'>"+hl(alt)+"</span>":"";
      html.push("<li"+dayCls+">"+
        "<span class='title'><a href='"+esc(d.url)+"' target='_blank' rel='noopener'>"+
          hl(label(d))+"</a>"+extra+altHtml+"</span>"+
        "<span class='summ'>"+hl((LANG==="de"?d.summary:(d.summary_en||d.summary))||"")+"</span>"+
        "<span class='agency' data-ag='"+esc(d.agency)+"' "+
          "title='Show only this agency'>"+esc(d.agency)+"</span>"+
        "<span class='type'>"+esc(d.type||"page")+"</span>"+
        "<span class='date'>"+(d.date?((d.approx?"~":"")+esc(fmtDate(d.date))):"undated")+"</span>"+
      "</li>");
      shown++;
    }
    html.push("</ul>");
    out.innerHTML = hits.length ? html.join("")
      : "<p class='empty'>No documents match. Clear the search or widen the filters.</p>";
    out.querySelectorAll(".summ").forEach(function(s){
      if(s.scrollHeight > s.clientHeight + 2) s.classList.add("clipped");
      s.addEventListener("click",function(){
        if(s.classList.contains("expanded")){
          s.classList.remove("expanded");
        }else if(s.classList.contains("clipped")){
          s.classList.add("expanded");
        }
      });
    });
    out.querySelectorAll(".agency[data-ag]").forEach(function(s){
      s.addEventListener("click",function(){
        var ag=s.getAttribute("data-ag");
        if(msAgency.set.size===1 && msAgency.set.has(ag) && !msAgency.isExclude()){
          msAgency.setOnly(null);
        }else{
          msAgency.setOnly(ag);
        }
        PAGE=0; EXPANDED={}; DAYCOL={}; render();
      });
    });
    out.querySelectorAll(".day-sep button").forEach(function(b){
      b.addEventListener("click",function(){
        var k=b.getAttribute("data-day");
        if(DAYCOL[k]) delete DAYCOL[k]; else DAYCOL[k]=true;
        render();
      });
    });
    out.querySelectorAll(".more-row button").forEach(function(b){
      b.addEventListener("click",function(){
        var k=b.getAttribute("data-key");
        if(EXPANDED[k]) delete EXPANDED[k]; else EXPANDED[k]=true;
        render();
      });
    });
    count.textContent = hits.length+" document"+(hits.length===1?"":"s")
      + (totalPages>1 ? " — showing "+(start+1)+"\u2013"+(start+shown) : "");
    markQuick();
    refreshViewButtons();
    refreshBanner();
    ["T","B"].forEach(function(k){
      document.getElementById("page"+k).textContent =
        "Page "+(PAGE+1)+" of "+totalPages;
      document.getElementById("prev"+k).disabled = PAGE<=0;
      document.getElementById("next"+k).disabled = PAGE>=totalPages-1;
    });
  }
  function go(delta){
    PAGE+=delta; render();
    window.scrollTo({top:0});
  }
  document.getElementById("prevT").addEventListener("click",function(){go(-1);});
  document.getElementById("nextT").addEventListener("click",function(){go(1);});
  document.getElementById("prevB").addEventListener("click",function(){go(-1);});
  document.getElementById("nextB").addEventListener("click",function(){go(1);});

  function csvField(v){
    v=v==null?"":String(v);
    return '"'+v.replace(/"/g,'""')+'"';
  }
  document.getElementById("csv").addEventListener("click",function(){
    var lines=["title_en,title_de,summary,agency,type,date,url"];
    LASTHITS.forEach(function(d){
      lines.push([csvField(labelEN(d)),csvField(labelDE(d)),csvField(d.summary_en||d.summary),csvField(d.agency),
        csvField(d.type||"page"),csvField(d.date||"undated"),
        csvField(d.url)].join(","));
    });
    var blob=new Blob(["\ufeff"+lines.join("\r\n")],{type:"text/csv;charset=utf-8"});
    var a=document.createElement("a");
    a.href=URL.createObjectURL(blob);
    a.download="govdocs-export-"+new Date().toISOString().slice(0,10)+".csv";
    document.body.appendChild(a); a.click();
    URL.revokeObjectURL(a.href); a.remove();
  });
  document.getElementById("share").addEventListener("click",function(){
    var btn=this;
    navigator.clipboard.writeText(location.href).then(function(){
      btn.textContent="Link copied";
      setTimeout(function(){btn.textContent="Copy link to this search";},1500);
    });
  });
  sortSel.addEventListener("change",function(){PAGE=0;render();});
  // last-visit tracking: remember the previous distinct day this page
  // was opened, so "new since" survives same-day reloads
  (function(){
    try{
      var today=new Date().toISOString().slice(0,10),
          last=localStorage.getItem("govdocs-lastvisit"),
          prev=localStorage.getItem("govdocs-prevvisit");
      if(last && last!==today){
        localStorage.setItem("govdocs-prevvisit", last);
        prev=last;
      }
      localStorage.setItem("govdocs-lastvisit", today);
      PREV_VISIT=prev||null;
    }catch(e){}
  })();
  var newBtn=document.getElementById("newSince"),
      digBtn=document.getElementById("digest");
  newBtn.addEventListener("click",function(){
    NEWONLY=!NEWONLY; if(NEWONLY) DIGEST=false;
    PAGE=0; EXPANDED={}; DAYCOL={}; render();
  });
  digBtn.addEventListener("click",function(){
    DIGEST=!DIGEST; if(DIGEST) NEWONLY=false;
    PAGE=0; EXPANDED={}; DAYCOL={}; render();
  });
  function refreshViewButtons(){
    if(PREV_VISIT){
      var n=DATA.reduce(function(acc,d){
        return acc+((d.indexed && d.indexed>PREV_VISIT)?1:0);},0);
      newBtn.style.display="";
      newBtn.textContent=(NEWONLY?"Showing new since ":"New since ")
        + fmtDate(PREV_VISIT)+" ("+n.toLocaleString()+")";
    }
    newBtn.classList.toggle("on",NEWONLY);
    digBtn.classList.toggle("on",DIGEST);
    digBtn.textContent = DIGEST ? "Showing last 7 days" : "Last 7 days";
  }
  function refreshBanner(){
    var el=document.getElementById("agBanner");
    var one = msAgency.set.size===1 && !msAgency.isExclude();
    if(!one){el.style.display="none";return;}
    var ag=Array.from(msAgency.set)[0];
    el.style.display="";
    el.innerHTML="Filtered to <strong>"+esc(ag)+"</strong>"
      +" &middot; <a href='coverage.html'>coverage notes</a>";
    var clr=document.createElement("button");
    clr.textContent="show all agencies";
    clr.addEventListener("click",function(){
      msAgency.setOnly(null); PAGE=0; render();
    });
    el.appendChild(clr);
  }
  var QUICK=["risk","resilience","catastrophe","pandemic","nuclear",
             "artificial intelligence","preparedness"];
  function myQuick(){
    try{return JSON.parse(localStorage.getItem("govdocs-quick")||"[]");}
    catch(e){return [];}
  }
  function saveQuick(list){
    try{localStorage.setItem("govdocs-quick",JSON.stringify(list));}catch(e){}
  }
  function buildQuick(){
    var box=document.getElementById("quickList");
    box.innerHTML="<h3>Common searches</h3>";
    function addBtn(term, removable){
      var b=document.createElement("button");
      b.setAttribute("data-term",term);
      b.appendChild(document.createTextNode(term));
      if(removable){
        var x=document.createElement("span");
        x.className="rm"; x.textContent="\u00d7";
        x.title="Remove from your list";
        x.addEventListener("click",function(e){
          e.stopPropagation();
          saveQuick(myQuick().filter(function(t){return t!==term;}));
          buildQuick(); markQuick(); buildNewsRail();
        });
        b.appendChild(x);
      }
      b.addEventListener("click",function(){
        q.value = (q.value.trim().toLowerCase()===term) ? "" : term;
        PAGE=0; EXPANDED={}; DAYCOL={};
        render();
      });
      box.appendChild(b);
    }
    QUICK.forEach(function(t){addBtn(t,false);});
    myQuick().forEach(function(t){addBtn(t,true);});
    var add=document.createElement("button");
    add.className="add";
    add.textContent="+ save current search";
    add.title="Adds whatever is in the search box to your personal list "
      + "(stored in this browser only)";
    add.addEventListener("click",function(){
      var term=q.value.trim().toLowerCase();
      if(!term) return;
      var mine=myQuick();
      if(QUICK.indexOf(term)>-1 || mine.indexOf(term)>-1) return;
      mine.push(term); saveQuick(mine);
      buildQuick(); markQuick(); buildNewsRail();
    });
    box.appendChild(add);
  }
  buildQuick();
  function buildNewsRail(){
    var rail=document.getElementById("newsRail");
    if(!PREV_VISIT || !DATA.length){rail.style.display="none";return;}
    var terms=QUICK.concat(myQuick());
    var html=["<h3>New in your topics</h3>",
      "<p class='since'>since "+esc(fmtDate(PREV_VISIT))+"</p>"];
    var any=false;
    terms.forEach(function(term){
      var toks=fold(term).split(/\s+/);
      var matches=[];
      for(var i=0;i<DATA.length && matches.length<60;i++){
        var d=DATA[i];
        if(!(d.indexed && d.indexed>PREV_VISIT)) continue;
        var hay=fold(labelEN(d)+" "+labelDE(d)+" "+d.url+" "+d.agency+" "+(d.type||"")+" "
                 +(d.summary||"")+" "+(d.summary_en||""));
        if(toks.every(function(w){return hay.indexOf(w)>-1;}))
          matches.push(d);
      }
      if(!matches.length) return;
      any=true;
      html.push("<h4><button data-nrterm='"+esc(term)+"'>"+esc(term)
        +" <span class='n'>("+matches.length+")</span></button></h4>");
      matches.slice(0,5).forEach(function(d){
        html.push("<a href='"+esc(d.url)+"' target='_blank' rel='noopener' "
          +"title='"+esc(label(d))+"'>"+esc(label(d))+"</a>");
      });
    });
    if(!any) html.push("<p class='none'>Nothing new matching your terms.</p>");
    rail.innerHTML=html.join("");
    rail.style.display="";
    rail.querySelectorAll("button[data-nrterm]").forEach(function(b){
      b.addEventListener("click",function(){
        q.value=b.getAttribute("data-nrterm");
        NEWONLY=true; DIGEST=false;
        PAGE=0; EXPANDED={}; DAYCOL={};
        render();
      });
    });
  }
  function markQuick(){
    var cur=q.value.trim().toLowerCase();
    document.querySelectorAll(".quick button[data-term]").forEach(function(b){
      b.classList.toggle("active", b.getAttribute("data-term")===cur);
    });
  }
  var t=null;
  function schedule(){clearTimeout(t);t=setTimeout(function(){PAGE=0;EXPANDED={};DAYCOL={};render();},120);}
  q.addEventListener("input",schedule);
  [relSel,fromIn,toIn].forEach(function(el){
    el.addEventListener("change",function(){PAGE=0;render();});
  });

  (function(){
    var be=document.getElementById("langEN"), bd=document.getElementById("langDE");
    function setLang(l){
      LANG=l;
      be.classList.toggle("on", l==="en");
      bd.classList.toggle("on", l==="de");
      if(typeof render==="function") render();
      if(typeof buildNewsRail==="function") buildNewsRail();
    }
    be.addEventListener("click",function(){setLang("en");});
    bd.addEventListener("click",function(){setLang("de");});
  })();

  fetch("docs.json").then(function(r){
    if(!r.ok) throw new Error("HTTP "+r.status);
    return r.json();
  }).then(function(rows){
    DATA=rows;
    var agencies={}, types={}, rels={};
    rows.forEach(function(d){agencies[d.agency]=1;types[d.type||"page"]=1;rels[d.relevance||"unscored"]=1;});
    var st=hashState();
    msAgency.fill(Object.keys(agencies), st.agency?st.agency.split("|"):[]);
    msType.fill(Object.keys(types), st.type?st.type.split("|"):[]);
    if(Object.keys(rels).length>1) fillSelect(relSel,Object.keys(rels));
    else relSel.style.display="none";
    if(st.agmode==="ex") msAgency.setExclude(true);
    if(st.q) q.value=st.q;
    if(st.rel) relSel.value=st.rel;
    if(st.from) fromIn.value=st.from;
    if(st.to) toIn.value=st.to;
    if(st.sort) sortSel.value=st.sort;
    if(st.page) PAGE=Math.max(0,parseInt(st.page,10)-1)||0;
    buildNewsRail();
    document.getElementById("sub1").textContent =
      rows.length.toLocaleString()+" documents \u00b7 newest "+
      (rows[0]?fmtDate(rows[0].date):"\u2014");
    document.getElementById("sub2").textContent =
      "dates marked ~ are approximate (page last-modified)";
    render();
  }).catch(function(e){
    document.getElementById("sub1").textContent =
      "Couldn't load docs.json ("+e.message+"). It must sit in the same folder as this page, served over HTTP.";
  });
})();
</script>
</body>
</html>
"""


# ============================================================================
# Coverage register: every tracked entity, its status, and honest confidence.
# Maintained by hand alongside the registry — update when sources change.
# status: covered | partial | blocked | pending | not
# conf:   high | medium | pending | none
# ============================================================================
COVERAGE = [
  # ===== LIVE: 11 sources baselined and collecting (probes #1-#6, init 2026-09-07) =====
  # --- Ministries (11 of 16 live) ---
  ("Finanzen (BMF)", "Ministries", "covered", "high", "Plain sitemap, 2,287 URLs. Migration-stamp dating pathology detected and defended (one 2024 stamp ignored)."),
  ("Inneres (BMI)", "Ministries", "covered", "high", "GSB Sitemap_Index, ~3,900 URLs, 100% lastmod. Occasional transient TLS drop \u2014 watched."),
  ("Verteidigung (BMVg)", "Ministries", "covered", "high", "Gzipped sitemap, 4,216 URLs. No lastmod; dates from URL signals."),
  ("Forschung, Technologie & Raumfahrt (BMFTR)", "Ministries", "covered", "medium", "Sitemap declared inside a robots-disallowed path; fetched as a machine interface. Small estate (site relaunched 2025). Whole catalogue wears one migration stamp \u2014 undated."),
  ("Justiz & Verbraucherschutz (BMJV)", "Ministries", "covered", "high", "GSB Sitemap_Index, 1,325 URLs, 100% lastmod."),
  ("Arbeit & Soziales (BMAS)", "Ministries", "covered", "high", "Sitemap, ~3,730 URLs, 100% lastmod. Attachment watch on (first-scan suppression active)."),
  ("Digitales & Staatsmodernisierung (BMDS)", "Ministries", "covered", "medium", "Young ministry (est. 2025), 200 URLs. Occasional transient TLS drop \u2014 watched."),
  ("Gesundheit (BMG)", "Ministries", "covered", "high", "Sitemap index, ~3,880 URLs, 100% lastmod."),
  ("Landwirtschaft, Ern\u00e4hrung & Heimat (BMLEH)", "Ministries", "covered", "medium", "Sitemap index; most entries are image assets (excluded). ~300 real documents. Occasional transient TLS drop."),
  ("Umwelt, Klimaschutz, Naturschutz & nukleare Sicherheit (BMUKN)", "Ministries", "covered", "high", "38-child sitemap index, 4,965 URLs, 100% lastmod."),
  ("Wohnen, Stadtentwicklung & Bauwesen (BMWSB)", "Ministries", "covered", "high", "GSB Sitemap_Index, 687 URLs, 100% lastmod."),

  # ===== BLOCKED: behind the Enodia anti-bot gate (respected, not circumvented) =====
  ("Ausw\u00e4rtiges Amt (AA)", "Ministries", "blocked", "none", "Enodia gate, domain-wide. 15,984 URLs out of reach by any polite path (sitemap AND RSS feeds both gated). Largest single coverage gap. Recovery attempts logged: DIP API (also gated), GovData (spending data only), republishers (wrong data). Route-1 email to AA webmaster is the remaining option."),
  ("Bundesregierung / BPA", "Chancellery & Press", "blocked", "none", "Enodia gate, domain-wide. Sitemap (708 URLs) and all three RSS feeds gated. Clean on early probes, then gated during baseline."),
  ("Bundeskanzler", "Chancellery & Press", "blocked", "none", "Enodia gate. 81 URLs; small, and the Chancellor's substance largely flows through the BPA and the parliamentary record."),
  ("Wirtschaftliche Zusammenarbeit & Entwicklung (BMZ)", "Ministries", "blocked", "none", "Enodia gate, domain-wide. 2,603 URLs. Development-spending datasets available separately on GovData (niche, not the newsroom)."),

  # ===== BLOCKED: TLS handshake refused for plain clients =====
  ("Verkehr (BMV)", "Ministries", "blocked", "none", "TLS handshake terminated (SSL EOF) for non-browser clients. Retry path: rendered escalation (Playwright)."),
  ("Bildung, Familie, Senioren, Frauen & Jugend (BMBFSFJ)", "Ministries", "blocked", "none", "TLS handshake terminated (SSL EOF), same signature as BMV. Retry path: rendered escalation."),

  # ===== BLOCKED: content behind a JS render that returns empty against the gate =====
  ("Wirtschaft & Energie (BMWE)", "Ministries", "blocked", "none", "No sitemap on any known path; press listings are JS-hydrated and returned an empty render (0 links). Retry path: deeper render work post-launch."),

  # ===== PENDING: the next expansion tier (not yet attempted) =====
  ("Nachgeordnete Beh\u00f6rden (BSI, RKI, UBA, BKA \u2026)", "Agencies", "pending", "none", "Subordinate federal agencies. Phase 2: probe portfolio-by-portfolio; gate status is independent of the parent ministry and must be tested per agency."),
  ("Bundestag / Bundesrat", "Parliament", "pending", "none", "Parliamentary layer. DIP API is Enodia-gated; open republishers (Open Discourse, abgeordnetenwatch) hold the wrong data shape. Deferred."),
]

STATUS_LABEL = {"covered": "Covered", "partial": "Partial", "blocked": "Blocked",
                "pending": "Pending probe", "not": "Not covered"}
CONF_LABEL = {"high": "High", "medium": "Medium", "pending": "TBD", "none": "\u2014"}


def render_coverage():
    import html as _h
    cats = []
    for row in COVERAGE:
        if row[1] not in cats:
            cats.append(row[1])
    body = []
    for cat in cats:
        body.append(f"<h2>{_h.escape(cat)}</h2>")
        body.append("<table><thead><tr><th>Entity</th><th>Status</th>"
                    "<th>Confidence</th><th>Notes</th></tr></thead><tbody>")
        for name, c, status, conf, note in COVERAGE:
            if c != cat:
                continue
            body.append(
                f"<tr><td>{_h.escape(name)}</td>"
                f"<td><span class='chip {status}'>{STATUS_LABEL[status]}</span></td>"
                f"<td class='conf-{conf}'>{CONF_LABEL[conf]}</td>"
                f"<td>{_h.escape(note)}</td></tr>")
        body.append("</tbody></table>")
    return COVERAGE_PAGE.replace("__BODY__", "\n".join(body))


COVERAGE_PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Coverage register — German Government documents index</title>
<style>
  :root{--paper:#fbfbf8;--ink:#24291f;--meta:#6b7062;--rule:#d9dad2;
        --navy:#1f3a5f;--navy-soft:#eef1f4}
  *{box-sizing:border-box}
  body{margin:0;background:var(--paper);color:var(--ink);
       font:15px/1.5 "Avenir Next","Segoe UI",system-ui,sans-serif}
  .wrap{max-width:1200px;margin:0 auto;padding:28px 20px 80px}
  h1{font-family:"Iowan Old Style",Georgia,serif;font-weight:600;
     font-size:30px;margin:0 0 4px}
  h2{font-family:"Iowan Old Style",Georgia,serif;font-weight:600;
     font-size:21px;margin:34px 0 10px;border-bottom:2px solid var(--ink);
     padding-bottom:5px}
  .back{color:var(--navy);text-decoration:none;font-size:13.5px}
  .back:hover{text-decoration:underline}
  p.lead{color:var(--meta);margin:6px 0 0}
  table{width:100%;border-collapse:collapse;font-size:13.5px}
  th{text-align:left;color:var(--meta);font-weight:600;font-size:12px;
     letter-spacing:.3px;padding:6px 10px 6px 0;border-bottom:1px solid var(--rule)}
  td{padding:8px 10px 8px 0;border-bottom:1px solid var(--rule);
     vertical-align:top}
  td:first-child{font-weight:600;min-width:190px}
  .chip{display:inline-block;padding:1px 8px;border-radius:3px;
        font-size:12px;white-space:nowrap}
  .chip.covered{background:var(--navy-soft);color:var(--navy)}
  .chip.partial{background:#f3ecd9;color:#7a5d17}
  .chip.blocked{background:#f4e3df;color:#8a3b2e}
  .chip.pending{background:#eee;color:var(--meta)}
  .chip.not{background:none;border:1px solid var(--rule);color:var(--meta)}
  .conf-high{color:var(--navy);font-weight:600}
  .conf-medium{color:#7a5d17;font-weight:600}
  .conf-pending,.conf-none{color:var(--meta)}
  footer{margin-top:40px;color:var(--meta);font-size:12.5px;
         border-top:1px solid var(--rule);padding-top:12px}
  /* (coverage page shares the stylesheet block below via its own copy) */
</style>
</head>
<body>
<div class="wrap">
  <a class="back" href="index.html">&larr; Back to the documents index</a>
  <h1>Coverage register</h1>
  <p class="lead">What this index watches, what it cannot see, and how much to
  trust each. Confidence is an honest judgment from probe evidence, not a
  promise: <strong>High</strong> = verified pulling the right content;
  <strong>Medium</strong> = working but partial, thin, or unaudited in depth;
  <strong>Blocked</strong> = the site actively refuses automated access
  (respected, not circumvented). Scope is policy-significant federal entities
  &mdash; small statutory offices and corporate entities are added on request.</p>
__BODY__
  <footer>Maintained by hand alongside the source registry; the registry is
  the operational source of truth. Gaps are diagnosable: any document this
  index should have but doesn't can be run through the miss log.</footer>
</div>
</body>
</html>
"""
