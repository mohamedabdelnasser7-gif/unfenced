"""The two tab page's style, from the locked designs: _system/hackathon/design/agents/r1/opt-a.html
(Today, the agent page) and design/quickstart/r1/opt-b.html (New agent, nested under .qs). The page
loads no outside font, so Outfit falls back to the system font."""
CSS = r"""
:root{
  --bone:#F4F3EF; --ink:#0B0F12; --ink-2:#4b514f; --ink-3:#5d6360;
  --card:#ffffff; --card-2:#FAF9F6; --card-3:#F6F5F1; --card-4:#F1F0EB;
  --chip:#EDECE6; --line:rgba(11,15,18,.08);
  --sage-a:#5f7471; --sage-b:#2f3a39; --sage-c:#141a19; --sage:#2a3332;
  --volt:#d7f24b;
  --font:"Outfit", ui-sans-serif, system-ui, sans-serif;
  --ease:cubic-bezier(.2,.8,.2,1); --t:200ms; --t-press:160ms;
  --r-card:28px; --r-inner:20px;
  --shadow-card:0 1px 2px rgba(11,15,18,.05), 0 24px 48px -28px rgba(11,15,18,.22);
  --shadow-soft:0 1px 2px rgba(11,15,18,.04), 0 12px 28px -18px rgba(11,15,18,.18);
  --bubble:radial-gradient(120% 120% at 30% 18%, #fff, rgba(255,255,255,.92) 55%, rgba(246,245,241,.9) 80%);
  --bubble-shadow:inset 0 1px 1px #fff, inset 0 -6px 12px rgba(11,15,18,.05), 0 10px 22px -12px rgba(11,15,18,.32);
  --glass:rgba(250,249,246,.84);
  --mist:
    radial-gradient(60% 70% at 100% 0%, rgba(95,116,113,.36) 0%, rgba(95,116,113,0) 100%),
    radial-gradient(55% 60% at 0% 100%, rgba(143,163,158,.34) 0%, rgba(143,163,158,0) 100%),
    linear-gradient(160deg, #e2e8e5 0%, #edefeb 55%, #f4f3ef 100%);
}
@supports (corner-shape: squircle){
  :root{ --r-card:44px; --r-inner:32px; }
  .sq{ corner-shape:squircle; }
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%; text-size-adjust:100%}
body{margin:0; background:#E6E5E0; color:var(--ink); font:400 15px/1.5 var(--font); -webkit-font-smoothing:antialiased; overflow-x:hidden}
button{font:inherit; color:inherit; border:0; background:none; padding:0; cursor:pointer}
textarea{font:inherit; color:inherit}
:focus-visible{outline:2px solid var(--ink); outline-offset:3px}
.num{font-variant-numeric:tabular-nums}
svg.i{width:20px; height:20px; fill:none; stroke:currentColor; stroke-width:1.6; stroke-linecap:round; stroke-linejoin:round; flex:none}

/* ---------- product chrome, shared with A3 and Quick start B ---------- */
.page{padding:16px 20px 112px}
.bar{display:flex; align-items:center; justify-content:space-between; height:48px}
.brand{display:flex; align-items:center; gap:12px}
.logo{width:44px; height:44px; border-radius:50%; display:grid; place-items:center; background:var(--bubble); box-shadow:var(--bubble-shadow); color:var(--ink)}
.logo svg{width:24px; height:24px}
.word{font:600 17px/1 var(--font); letter-spacing:-.035em}
.bar-r{display:flex; align-items:center; gap:12px}
.sample{font:500 12px/16px var(--font); letter-spacing:.04em; color:var(--ink-2); padding:4px 12px; border-radius:999px; background:var(--chip); white-space:nowrap}
.bubble{width:44px; height:44px; border-radius:50%; display:grid; place-items:center; background:var(--bubble); box-shadow:var(--bubble-shadow); font:500 14px/1 var(--font); color:var(--ink)}
.lab{display:flex; align-items:center; gap:8px; font:500 12px/16px var(--font); letter-spacing:.08em; text-transform:uppercase; color:var(--ink-2)}
.sec-h{display:flex; align-items:baseline; justify-content:space-between; gap:12px; margin:0 4px 12px}
.sec-h h2{margin:0; font:500 20px/24px var(--font); letter-spacing:-.01em}
.sec-h small{font:400 14px/20px var(--font); color:var(--ink-2)}
.top{margin:20px 0 24px}
.top h1{margin:0; font:300 40px/44px var(--font); letter-spacing:-.035em; text-wrap:balance}
.top p{margin:8px 0 0; font:400 15px/22px var(--font); color:var(--ink-2); text-wrap:pretty}
.vchip{font:500 12px/16px var(--font); padding:4px 10px; border-radius:999px; background:var(--chip); color:var(--ink); white-space:nowrap}
.yes{height:52px; padding:0 24px 0 20px; border-radius:26px; display:inline-flex; align-items:center; justify-content:center; gap:8px; background:var(--volt); color:var(--ink); font:600 16px/1 var(--font); white-space:nowrap;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.6), 0 12px 24px -14px rgba(90,110,0,.7);
  transition:transform var(--t-press) var(--ease), filter var(--t) var(--ease)}
.yes:hover{filter:brightness(1.04)}
.yes:active{transform:scale(.97)}
.yes svg.i{stroke-width:2}
button.no{width:52px; height:52px; border-radius:50%; display:grid; place-items:center; flex:none; background:var(--bubble); box-shadow:var(--bubble-shadow), 0 0 0 1px rgba(11,15,18,.06); font:500 15px/1 var(--font); color:var(--ink);
  transition:transform var(--t-press) var(--ease)}
button.no:active{transform:scale(.97)}

/* phone tab bar: Today and Agents only, docked flat, light frosted glass */
.isl{position:fixed; left:0; right:0; bottom:0; z-index:40; display:flex; align-items:center; gap:4px; padding:8px 24px 22px;
  border-radius:28px 28px 0 0; background:var(--glass); backdrop-filter:blur(24px) saturate(160%); -webkit-backdrop-filter:blur(24px) saturate(160%);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.9), 0 -1px 0 rgba(11,15,18,.06), 0 -12px 32px -16px rgba(11,15,18,.22)}
.tab{flex:1; height:52px; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:3px; border-radius:22px; color:#4b514f; font:500 11px/14px var(--font)}
.tab .i{width:22px; height:22px}
.tab.on{color:var(--ink); background:rgba(42,51,50,.09)}
.tisl{display:none}

/* ---------- Today: yes cards you act on in place ---------- */
.today{display:flex; flex-direction:column; gap:32px}
.cards{display:flex; flex-direction:column; gap:16px}
.yc{border-radius:var(--r-card); padding:22px; background:var(--mist);
  box-shadow:var(--shadow-card), inset 0 1px 0 rgba(255,255,255,.7), inset 0 0 0 1px rgba(42,51,50,.06)}
.yc-h{display:flex; align-items:center; justify-content:space-between; gap:12px}
.agent{display:flex; align-items:center; gap:12px; min-width:0}
.av{width:40px; height:40px; border-radius:50%; display:grid; place-items:center; background:#fff; color:var(--ink); flex:none}
.av svg.i{width:19px; height:19px}
.agent b{display:block; font:500 15px/20px var(--font)}
.agent small{display:block; font:400 13px/16px var(--font); color:#2f3433}
.risk{display:inline-flex; align-items:center; gap:8px; font:500 12px/16px var(--font); padding:6px 12px; border-radius:999px; background:var(--ink); color:#fff; white-space:nowrap}
.risk i{width:6px; height:6px; border-radius:50%; background:#fff; opacity:.9}
.yc .lesson{margin:18px 0 0; font:400 23px/30px var(--font); letter-spacing:-.018em; text-wrap:pretty}
.yc .why{margin:8px 0 0; font:400 15px/22px var(--font); color:#2f3433; text-wrap:pretty}
.exam{display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top:18px; padding:14px 18px; border-radius:var(--r-inner); background:rgba(255,255,255,.6)}
.exam .lab{grid-column:1 / -1; margin-bottom:-8px; color:#2f3433}
.stat b{display:block; font:300 28px/36px var(--font); letter-spacing:-.02em; font-variant-numeric:tabular-nums}
.stat span{display:block; font:400 13px/18px var(--font); color:#2f3433}

/* the input that opens inside the card */
.edit{display:none; margin-top:16px}
.yc.open .edit{display:block}
.yc.open .lesson,.yc.open .why{display:none}
.edit .lab{color:#2f3433}
.box{margin-top:8px; border-radius:var(--r-inner); background:#fff; box-shadow:inset 0 0 0 1px rgba(42,51,50,.14), 0 1px 2px rgba(11,15,18,.04)}
.box textarea{display:block; width:100%; min-height:96px; resize:none; border:0; outline:0; background:transparent; padding:14px 16px 6px; font:400 19px/26px var(--font); letter-spacing:-.01em}
.box .add{min-height:0; height:46px; overflow:hidden; display:block; width:100%; resize:none; border:0; outline:0; background:transparent; padding:8px 16px 14px; border-top:1px dashed rgba(11,15,18,.12); font:400 15px/22px var(--font); color:var(--ink)}
.box .add::placeholder{color:var(--ink-3)}
.quiet{display:flex; align-items:flex-start; gap:8px; margin:10px 2px 0; font:400 13px/18px var(--font); color:#2f3433}
.quiet svg.i{width:16px; height:16px; margin-top:1px}

.act{display:flex; flex-wrap:wrap; align-items:center; gap:10px; margin-top:16px}
.act .trial{flex:1 1 100%; margin:0; font:400 14px/20px var(--font); color:#2f3433}
.act .trial b{font-weight:500; color:var(--ink)}
.mod{height:52px; padding:0 18px; border-radius:26px; display:inline-flex; align-items:center; gap:8px; background:rgba(255,255,255,.55); box-shadow:inset 0 0 0 1px rgba(42,51,50,.18); font:500 15px/1 var(--font); color:var(--ink);
  transition:background var(--t) var(--ease), transform var(--t-press) var(--ease)}
.mod svg.i{width:18px; height:18px}
.mod:active{transform:scale(.97)}
.mod[aria-expanded="true"]{background:var(--ink); color:#fff; box-shadow:none}
.act .yes{flex:1}

/* last night, one line per agent */
.night{background:var(--card); border-radius:var(--r-card); box-shadow:var(--shadow-soft); padding:6px 20px}
.nl{display:grid; grid-template-columns:40px minmax(0,1fr); gap:12px; align-items:start; padding:14px 0; border-top:1px solid var(--line)}
.nl:first-child{border-top:0}
.nl .av{background:var(--card-3)}
.nl b{display:flex; align-items:center; gap:8px; font:500 15px/20px var(--font)}
.nl p{margin:2px 0 0; font:400 14px/20px var(--font); color:var(--ink-2); text-wrap:pretty}
.st{font:500 11px/14px var(--font); padding:3px 8px; border-radius:999px; background:var(--chip); color:var(--ink-2); white-space:nowrap}
.st.live{background:rgba(42,51,50,.09); color:var(--ink)}

/* empty state */
.calm.sq{display:flex; align-items:center; gap:14px; padding:20px 22px; border-radius:var(--r-card); background:rgba(255,255,255,.5); box-shadow:inset 0 0 0 1px rgba(11,15,18,.08)}
.calm .ok{width:44px; height:44px; border-radius:50%; display:grid; place-items:center; background:#fff; box-shadow:var(--shadow-soft); flex:none}
.calm b{display:block; font:500 17px/24px var(--font); letter-spacing:-.01em}
.calm p{margin:2px 0 0; font:400 14px/20px var(--font); color:var(--ink-2)}

/* ---------- Agent page: one calm column ---------- */
.col{display:flex; flex-direction:column; gap:16px}
.back{display:inline-flex; align-items:center; gap:6px; margin:16px 0 0; font:500 14px/20px var(--font); color:var(--ink-2)}
.back svg.i{width:18px; height:18px}
.ag-top{margin:8px 0 8px}
.status{position:relative; overflow:hidden; border-radius:var(--r-card); padding:18px 18px 18px 20px; color:#fff;
  background:
    radial-gradient(42% 46% at 100% 0%, rgba(176,192,187,.62), rgba(176,192,187,0) 100%),
    radial-gradient(60% 50% at 0% 100%, rgba(8,11,10,.55), rgba(8,11,10,0) 100%),
    radial-gradient(55% 45% at 78% 92%, rgba(95,116,113,.55), rgba(95,116,113,0) 100%),
    linear-gradient(160deg, var(--sage-a) 0%, var(--sage-b) 45%, var(--sage-c) 100%);
  box-shadow:0 30px 56px -30px rgba(20,26,25,.7), inset 0 1px 0 rgba(255,255,255,.18);
  display:flex; flex-wrap:wrap; align-items:center; gap:12px 16px}
.st-l{flex:1 1 auto; min-width:0; display:flex; flex-direction:column; gap:8px}
.states{display:inline-flex; align-self:flex-start; padding:3px; border-radius:999px; background:rgba(11,15,18,.3)}
.states span{display:inline-flex; align-items:center; gap:7px; padding:5px 11px; border-radius:999px; font:500 12px/16px var(--font); color:rgba(255,255,255,.62); white-space:nowrap}
.states .on{background:rgba(255,255,255,.94); color:var(--ink)}
.states .on i{width:7px; height:7px; border-radius:50%; background:#3d8f5a}
.st-l small{font:400 13px/18px var(--font); color:rgba(255,255,255,.86)}
.st-r{display:flex; gap:8px}
.gb{height:40px; padding:0 14px; border-radius:20px; display:inline-flex; align-items:center; gap:6px; color:#fff; font:500 14px/1 var(--font);
  background:radial-gradient(120% 120% at 30% 18%, rgba(255,255,255,.34), rgba(255,255,255,.08) 50%, rgba(255,255,255,.05) 75%);
  border:1px solid rgba(255,255,255,.3); box-shadow:inset 0 1px 1px rgba(255,255,255,.5), 0 10px 20px -10px rgba(0,0,0,.5);
  transition:transform var(--t-press) var(--ease)}
.gb svg.i{width:16px; height:16px}
.gb:active{transform:scale(.96)}

.say{background:var(--card); border-radius:var(--r-card); box-shadow:var(--shadow-card); padding:18px}
.say .lab{margin:0 2px}
.say .box{background:var(--card-3); box-shadow:inset 0 0 0 1px var(--line)}
.say textarea{min-height:84px; font-size:18px; line-height:25px}
.say-f{display:flex; align-items:center; gap:12px; margin-top:12px}
.say-f .quiet{flex:1; margin:0}
.say-f .pick{align-items:center; min-width:0}
.say-f .pick input{min-width:0; max-width:100%; font:400 13px/18px var(--font); color:var(--ink-2)}
.sdata{margin:12px 2px 0}
.send{height:48px; padding:0 20px; border-radius:24px; display:inline-flex; align-items:center; gap:8px; background:var(--volt); color:var(--ink); font:600 15px/1 var(--font); flex:none;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.6), 0 12px 24px -14px rgba(90,110,0,.7)}
.send svg.i{width:18px; height:18px; stroke-width:2}

.grp{background:var(--card); border-radius:var(--r-card); box-shadow:var(--shadow-soft); padding:16px 20px 6px}
.grp h3{margin:0 0 4px; font:500 17px/24px var(--font); letter-spacing:-.01em}
.lr{display:grid; grid-template-columns:minmax(0,1fr) auto; gap:4px 12px; align-items:start; padding:13px 0; border-top:1px solid var(--line)}
.lr:first-of-type{border-top:0}
.lr b{font:400 15px/21px var(--font); text-wrap:pretty}
.lr small{grid-column:1; font:400 12px/16px var(--font); color:var(--ink-3)}
.lr .vchip{grid-row:1; grid-column:2}
.vchip.hot{background:var(--ink); color:#fff}
.vchip.trial{background:rgba(42,51,50,.12)}
.nr{padding:13px 0; border-top:1px solid var(--line)}
.stl{margin:0; font:500 15px/21px var(--font); text-wrap:pretty}
/* the Arena track reads as steps, never as buttons: a numbered circle, the word, a line to the next step */
.trk{display:flex; flex-wrap:wrap; align-items:center; gap:8px 0; list-style:none; margin:14px 0 0; padding:0}
.trk li{display:flex; align-items:center; gap:8px; font:400 14px/20px var(--font); color:var(--ink-2); cursor:default}
.trk li + li::before{content:""; flex:none; width:24px; height:1px; margin-right:4px; background:rgba(11,15,18,.18)}
.trk .n{flex:none; width:22px; height:22px; border-radius:50%; display:grid; place-items:center; font:500 12px/1 var(--font); color:var(--ink-2); box-shadow:inset 0 0 0 1px rgba(11,15,18,.22)}
.trk .n svg.i{width:13px; height:13px; stroke-width:2.4}
.trk .w{display:block}
.trk li.next{color:var(--ink); font-weight:500}
.trk li.next .n{background:var(--ink); color:#fff; box-shadow:none}
.trk li.done .n{background:rgba(42,51,50,.12); color:var(--ink); box-shadow:none}
.trk li.soon{color:var(--ink-3)}
.trk li.soon .n{color:var(--ink-3); box-shadow:inset 0 0 0 1px rgba(11,15,18,.12)}
.vh{position:absolute; width:1px; height:1px; overflow:hidden; clip-path:inset(50%); white-space:nowrap}
/* a run going, where its button was: a greyed pill with a turning ring */
.runp{display:inline-flex; align-items:center; gap:10px; min-height:52px; padding:10px 22px 10px 18px; border-radius:26px; background:var(--chip); color:var(--ink-2); font:500 15px/21px var(--font); box-shadow:inset 0 0 0 1px rgba(11,15,18,.08); cursor:default; text-wrap:pretty}
.runp .spin{flex:none; width:16px; height:16px; border-radius:50%; border:2px solid rgba(11,15,18,.16); border-top-color:var(--ink-2); animation:spin 1s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.arq > * + *{margin-top:24px}
.arq > div[data-live]:first-child:empty + *{margin-top:0}
.rsn{list-style:none; margin:8px 0 0; padding:0}
.rsn li{padding:7px 0; border-top:1px solid var(--line); font:400 15px/21px var(--font)}
.rsn li:first-child{border-top:0}
.say .stl+.rsn,.say .rsn+.quiet{margin-top:8px}
.say > div[data-live] + form{margin-top:16px}
.nr:first-of-type{border-top:0}
.nr .to{display:flex; align-items:center; gap:8px; font:500 12px/16px var(--font); color:var(--ink-3)}
.nr .to svg.i{width:14px; height:14px}
.nr p{margin:4px 0 0; font:400 15px/21px var(--font); text-wrap:pretty}

/* ---------- desktop, by the frame's own width ---------- */
@media (min-width: 1024px){
  .bar,.isl{display:none}
  .page{max-width:1376px; margin:0 auto; padding:16px 56px 64px}
  .tisl{position:sticky; top:16px; z-index:40; display:grid; grid-template-columns:1fr auto 1fr; align-items:center; gap:16px; height:64px; padding:0 10px; border-radius:32px;
    background:var(--glass); backdrop-filter:blur(24px) saturate(160%); -webkit-backdrop-filter:blur(24px) saturate(160%);
    box-shadow:inset 0 1px 0 rgba(255,255,255,.9), inset 0 0 0 1px rgba(11,15,18,.05), 0 18px 40px -22px rgba(11,15,18,.3)}
  .tisl .left,.tisl .right{display:flex; align-items:center; gap:12px}
  .tisl .right{justify-content:flex-end}
  .tnav{display:flex; align-items:center; gap:4px}
  .titem{display:inline-flex; align-items:center; gap:8px; height:44px; padding:0 18px; border-radius:22px; color:#4b514f; font:500 15px/1 var(--font)}
  .titem.on{color:var(--ink); background:rgba(42,51,50,.09)}
  .top{margin:40px 0 32px}
  .top h1{font-size:56px; line-height:60px}
  .top p{font-size:17px; line-height:24px}

  .today{display:grid; grid-template-columns:minmax(0,7fr) minmax(0,5fr); gap:40px; align-items:start}
  .cards{gap:20px}
  .yc{padding:28px 32px}
  .yc .lesson{font-size:30px; line-height:38px; margin-top:22px; letter-spacing:-.022em}
  .yc .why{font-size:16px; line-height:24px}
  .exam{padding:18px 24px; gap:24px; margin-top:22px}
  .stat b{font-size:32px; line-height:40px}
  .stat span{font-size:14px}
  .box textarea{font-size:24px; line-height:32px; padding:18px 20px 8px; min-height:112px}
  .box .add{padding:10px 20px 16px; height:50px; min-height:0}
  .act{flex-wrap:nowrap; gap:12px; margin-top:22px}
  .act .trial{flex:1 1 auto}
  .act .yes{flex:none; height:56px; padding:0 28px 0 22px; border-radius:28px}
  .act .no{width:56px; height:56px}
  .act .mod{height:56px; border-radius:28px; padding:0 20px}
  .night{padding:8px 24px}
  .today.empty{grid-template-columns:minmax(0,7fr) minmax(0,5fr)}
  .calm.sq{padding:28px 32px}

  .col{max-width:760px; margin:0 auto; gap:20px}
  .colhead{max-width:760px; margin:0 auto}
  .back{margin-top:32px}
  .ag-top{margin:8px 0 16px}
  .status{padding:22px 24px 22px 26px}
  .st-l{flex-direction:row; align-items:center; gap:14px}
  .st-l small{font-size:14px}
  .gb{height:44px; padding:0 16px; border-radius:22px}
  .say{padding:22px 24px}
  .say textarea{font-size:22px; line-height:30px; min-height:96px}
  .grp{padding:20px 26px 8px}
  .lr b,.nr p{font-size:16px; line-height:23px}
}
.qs{
/* ---------- screen 1: the ask ---------- */
.mode{display:grid; grid-template-columns:1fr 1fr; gap:4px; padding:4px; border-radius:24px; background:var(--chip); margin-bottom:16px}
.mode span{display:flex; align-items:center; justify-content:center; gap:8px; height:44px; border-radius:20px; font:500 14px/1 var(--font); color:var(--ink-2)}
.mode .on{background:var(--card); color:var(--ink); box-shadow:var(--shadow-soft)}
.mode .off i{font-style:normal; font:500 11px/14px var(--font); padding:2px 8px; border-radius:999px; background:rgba(255,255,255,.7); color:var(--ink-3)}

.ask{position:relative; border-radius:var(--r-card); padding:24px;
  background:
    radial-gradient(60% 70% at 100% 0%, rgba(95,116,113,.36) 0%, rgba(95,116,113,0) 100%),
    radial-gradient(55% 60% at 0% 100%, rgba(143,163,158,.34) 0%, rgba(143,163,158,0) 100%),
    linear-gradient(160deg, #e2e8e5 0%, #edefeb 55%, #f4f3ef 100%);
  box-shadow:var(--shadow-card), inset 0 1px 0 rgba(255,255,255,.7), inset 0 0 0 1px rgba(42,51,50,.06)}
.ask .lab{color:#2f3433}
.field{margin-top:12px; padding:18px 20px 16px; border-radius:var(--r-inner); background:rgba(255,255,255,.66); box-shadow:inset 0 0 0 1px rgba(42,51,50,.08)}
.typed{margin:0; font:400 24px/32px var(--font); letter-spacing:-.018em; text-wrap:pretty}
.caret{display:inline-block; width:2px; height:26px; margin-left:3px; vertical-align:-4px; background:var(--ink); animation:blink 1.1s steps(1) infinite}
@keyframes blink{50%{opacity:0}}
.heard{display:flex; flex-wrap:wrap; align-items:center; gap:6px; margin-top:14px}
.heard em{font-style:normal; font:400 13px/16px var(--font); color:var(--ink-3); margin-right:2px}
.heard .vchip{background:#fff; box-shadow:inset 0 0 0 1px rgba(42,51,50,.08)}
.needs{margin-top:20px}
.file{display:grid; grid-template-columns:44px minmax(0,1fr) 36px; align-items:center; gap:12px; margin-top:10px; padding:10px 8px 10px 10px; border-radius:22px; background:#fff; box-shadow:var(--shadow-soft)}
.file .fi{width:44px; height:44px; border-radius:14px; display:grid; place-items:center; background:var(--card-4)}
.file b{display:block; font:500 15px/20px var(--font); white-space:nowrap; overflow:hidden; text-overflow:ellipsis}
.file small{display:block; font:400 13px/18px var(--font); color:var(--ink-2); white-space:nowrap; overflow:hidden; text-overflow:ellipsis}
.file .x{width:36px; height:36px; border-radius:50%; display:grid; place-items:center; color:var(--ink-3)}
.file .x:hover{background:var(--card-3); color:var(--ink)}
.add{display:flex; align-items:center; gap:10px; width:100%; margin-top:8px; padding:12px 14px; border-radius:22px; text-align:left; font:500 14px/20px var(--font); color:var(--ink);
  background:rgba(255,255,255,.34); box-shadow:inset 0 0 0 1px rgba(42,51,50,.16)}
.add small{font:400 13px/18px var(--font); color:var(--ink-2)}
.add .plus{width:28px; height:28px; border-radius:50%; display:grid; place-items:center; background:#fff; flex:none}
.act{display:flex; flex-wrap:wrap; align-items:center; gap:12px 16px; margin-top:20px}
.act p{flex:1 1 100%; margin:0; font:400 14px/20px var(--font); color:#2f3433}
.act p b{font-weight:500; color:var(--ink)}
.act .yes{flex:1}

.side1{display:flex; flex-direction:column; gap:16px; margin-top:24px}
.bs{display:none}
.next{background:var(--card); border-radius:var(--r-card); box-shadow:var(--shadow-soft); padding:22px 22px 8px}
.next h3{margin:0 0 6px; font:500 17px/24px var(--font); letter-spacing:-.01em}
.steps{list-style:none; margin:0; padding:0}
.steps li{position:relative; display:grid; grid-template-columns:36px minmax(0,1fr); gap:14px; padding:12px 0 16px}
.steps li:not(:last-child)::after{content:""; position:absolute; left:17.5px; top:52px; bottom:-4px; width:1px; background:rgba(11,15,18,.12)}
.steps .dot{width:36px; height:36px; border-radius:50%; display:grid; place-items:center; background:var(--card-3); color:var(--ink)}
.steps .dot svg.i{width:18px; height:18px}
.steps li:first-child .dot{background:var(--sage); color:#fff}
.steps b{display:block; font:500 15px/20px var(--font)}
.steps p{margin:2px 0 0; font:400 14px/20px var(--font); color:var(--ink-2)}
.who{display:flex; flex-wrap:wrap; gap:6px; margin-top:10px}

/* ---------- screen 2: the build, live ---------- */
.s2{display:flex; flex-direction:column; gap:24px}
.glow{position:relative; overflow:hidden; border-radius:var(--r-card); padding:22px 22px 20px; color:#fff;
  background:
    radial-gradient(42% 46% at 100% 0%, rgba(176,192,187,.62), rgba(176,192,187,0) 100%),
    radial-gradient(60% 50% at 0% 100%, rgba(8,11,10,.55), rgba(8,11,10,0) 100%),
    radial-gradient(55% 45% at 78% 92%, rgba(95,116,113,.55), rgba(95,116,113,0) 100%),
    linear-gradient(160deg, var(--sage-a) 0%, var(--sage-b) 45%, var(--sage-c) 100%);
  box-shadow:0 30px 56px -30px rgba(20,26,25,.7), inset 0 1px 0 rgba(255,255,255,.18)}
.glow-h{display:flex; align-items:center; gap:10px}
.gchip{display:inline-flex; align-items:center; gap:8px; font:500 12px/16px var(--font); padding:6px 12px; border-radius:999px; background:rgba(11,15,18,.34); color:#fff; white-space:nowrap}
.pulse{width:7px; height:7px; border-radius:50%; background:#fff; box-shadow:0 0 0 0 rgba(255,255,255,.6); animation:pulse 2.4s var(--ease) infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(255,255,255,.55)}70%{box-shadow:0 0 0 8px rgba(255,255,255,0)}100%{box-shadow:0 0 0 0 rgba(255,255,255,0)}}
.gsub{font:400 13px/16px var(--font); color:rgba(255,255,255,.86)}
.climb{display:block; width:100%; height:auto; margin:14px 0 2px}
.climb-l{display:flex; justify-content:space-between; font:400 12px/16px var(--font); color:rgba(255,255,255,.72)}
.glow .say{margin:16px 0 0; font:400 24px/30px var(--font); letter-spacing:-.015em}
.glow .why{margin:6px 0 0; font:400 15px/22px var(--font); color:rgba(255,255,255,.86); text-wrap:pretty}
.glow .calm{display:flex; gap:10px; align-items:flex-start; margin:16px 0 0; padding:12px 14px; border-radius:18px; background:rgba(11,15,18,.26); font:400 13px/18px var(--font); color:rgba(255,255,255,.9)}
.glow .calm svg.i{width:18px; height:18px; margin-top:0}

.tiles{display:grid; grid-template-columns:minmax(0,1fr); gap:12px}
.tile{background:var(--card); border-radius:26px; box-shadow:var(--shadow-soft); padding:16px 18px 16px}
.t-h{display:grid; grid-template-columns:40px minmax(0,1fr) auto; align-items:center; gap:12px}
.pav{width:40px; height:40px; border-radius:50%; display:grid; place-items:center; background:var(--card-4); font:500 15px/1 var(--font); color:var(--ink)}
.t-h b{display:block; font:500 15px/20px var(--font)}
.t-h small{display:block; font:400 12px/16px var(--font); color:var(--ink-3)}
.res{display:inline-flex; align-items:center; gap:6px; font:500 12px/16px var(--font); padding:5px 11px; border-radius:999px; white-space:nowrap}
.res svg.i{width:14px; height:14px; stroke-width:2}
.won .res{background:var(--ink); color:#fff}
.lost .res{background:var(--chip); color:var(--ink)}
.live .res{background:rgba(42,51,50,.09); color:var(--ink)}
.live .res .pulse{background:var(--sage); animation-name:pulse-d}
@keyframes pulse-d{0%{box-shadow:0 0 0 0 rgba(42,51,50,.4)}70%{box-shadow:0 0 0 7px rgba(42,51,50,0)}100%{box-shadow:0 0 0 0 rgba(42,51,50,0)}}
.persona{margin:12px 0 0; font:400 19px/25px var(--font); letter-spacing:-.012em; text-wrap:pretty}
.tags{display:flex; flex-wrap:wrap; gap:6px; margin-top:10px}
.tags span{font:500 12px/16px var(--font); padding:3px 9px; border-radius:999px; background:var(--card-3); color:var(--ink-2); box-shadow:inset 0 0 0 1px var(--line)}
.fix{margin-top:12px}
.fix summary{display:inline-flex; align-items:center; gap:6px; cursor:pointer; list-style:none; font:600 14px/20px var(--font); color:var(--ink-2)}
.fix summary::-webkit-details-marker{display:none}
.fix summary svg.i{width:16px; height:16px}
.fix .box{background:var(--card-3); box-shadow:inset 0 0 0 1px var(--line)}
.fix textarea{min-height:72px; font-size:16px; line-height:22px}
.out{margin:12px 0 0; padding-top:12px; border-top:1px solid var(--line); font:400 14px/20px var(--font); color:var(--ink-2); text-wrap:pretty}
.out b{font-weight:500; color:var(--ink)}
.live{box-shadow:var(--shadow-card), inset 0 0 0 1.5px rgba(42,51,50,.22)}
.chat{display:flex; flex-direction:column; gap:6px; margin-top:12px; padding:12px; border-radius:18px; background:var(--card-3)}
.msg{max-width:86%; padding:8px 12px; border-radius:16px; font:400 13px/18px var(--font)}
.msg.c{align-self:flex-start; background:#fff; box-shadow:inset 0 0 0 1px var(--line); border-bottom-left-radius:6px}
.msg.a{align-self:flex-end; background:#e3e9e6; border-bottom-right-radius:6px}
.typing{align-self:flex-start; display:inline-flex; gap:4px; padding:10px 12px; border-radius:16px; border-bottom-left-radius:6px; background:#fff; box-shadow:inset 0 0 0 1px var(--line)}
.typing i{width:5px; height:5px; border-radius:50%; background:var(--ink-3); animation:dot 1.3s var(--ease) infinite}
.typing i:nth-child(2){animation-delay:.18s} .typing i:nth-child(3){animation-delay:.36s}
@keyframes dot{0%,60%,100%{opacity:.25; transform:none}30%{opacity:1; transform:translateY(-2px)}}
.pend{margin:12px 0 0; padding-top:12px; border-top:1px dashed rgba(11,15,18,.14)}
.pend span{display:block; height:10px; border-radius:5px; background:linear-gradient(90deg, var(--card-4) 0%, #fff 50%, var(--card-4) 100%); background-size:200% 100%; animation:sheen 2.2s linear infinite}
.pend span+span{width:62%; margin-top:8px}
@keyframes sheen{from{background-position:100% 0}to{background-position:-100% 0}}
.ghost{display:flex; align-items:center; gap:12px; padding:18px; border-radius:26px; box-shadow:inset 0 0 0 1.5px rgba(11,15,18,.1); background:rgba(255,255,255,.35); font:400 14px/20px var(--font); color:var(--ink-3)}
.ghost .pav{background:transparent; box-shadow:inset 0 0 0 1.5px rgba(11,15,18,.12)}

.learned{background:var(--card); border-radius:var(--r-card); box-shadow:var(--shadow-soft); padding:20px 22px 10px}
.learned h3{margin:0; font:500 17px/24px var(--font); letter-spacing:-.01em}
.learned > p{margin:2px 0 6px; font:400 13px/18px var(--font); color:var(--ink-2)}
.learned ul{list-style:none; margin:0; padding:0}
.learned li{display:grid; grid-template-columns:28px minmax(0,1fr); gap:10px; padding:12px 0; border-top:1px solid var(--line)}
.learned li:first-child{border-top:0}
.learned li .lk{width:28px; height:28px; border-radius:50%; display:grid; place-items:center; background:var(--card-3)}
.learned li .lk svg.i{width:15px; height:15px}
.learned li b{display:block; font:400 15px/21px var(--font)}
.learned li small{display:block; margin-top:2px; font:400 12px/16px var(--font); color:var(--ink-3)}

/* phone first screen keeps the main action above the tab bar */
@media (max-width: 1023px){
  .s1-top{margin:12px 0 16px}
  .s1-top p{display:none}
  .ask{padding:20px}
  .field{margin-top:10px; padding:16px 18px}
  .typed{font-size:23px; line-height:30px}
  .heard{display:none}
  .needs{margin-top:16px}
  .act{margin-top:16px; gap:10px}
}

@media (min-width: 1024px){
  .bar,.isl,.mode{display:none}
  .page{max-width:1376px; margin:0 auto; padding:16px 56px 64px}
  .tisl{position:sticky; top:16px; z-index:40; display:grid; grid-template-columns:1fr auto 1fr; align-items:center; gap:16px; height:64px; padding:0 10px; border-radius:32px;
    background:var(--glass); backdrop-filter:blur(24px) saturate(160%); -webkit-backdrop-filter:blur(24px) saturate(160%);
    box-shadow:inset 0 1px 0 rgba(255,255,255,.9), inset 0 0 0 1px rgba(11,15,18,.05), 0 18px 40px -22px rgba(11,15,18,.3)}
  .tisl .left,.tisl .right{display:flex; align-items:center; gap:12px}
  .tisl .right{justify-content:flex-end}
  .tnav{display:flex; align-items:center; gap:4px}
  .titem{display:inline-flex; align-items:center; gap:8px; height:44px; padding:0 16px; border-radius:22px; color:#4b514f; font:500 15px/1 var(--font)}
  .titem.on{color:var(--ink); background:rgba(42,51,50,.09)}
  .top{display:flex; align-items:flex-end; justify-content:space-between; gap:32px; margin:40px 0 32px}
  .top h1{font-size:56px; line-height:60px}
  .top p{font-size:17px; line-height:24px}

  .s1{display:grid; grid-template-columns:minmax(0,7fr) minmax(0,5fr); gap:40px; align-items:start}
  .ask{padding:32px 36px 32px}
  .field{padding:24px 28px 20px}
  .typed{font-size:34px; line-height:44px; letter-spacing:-.025em}
  .caret{height:36px; vertical-align:-6px}
  .needs{display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:0 12px; margin-top:24px}
  .needs .lab{grid-column:1 / -1}
  .add{margin-top:10px; height:auto}
  .act{flex-wrap:nowrap; margin-top:28px}
  .act p{flex:1 1 auto; font-size:15px}
  .act .yes{flex:none; height:60px; padding:0 30px 0 32px; border-radius:30px; font-size:17px}
  .side1{margin-top:0; gap:20px}
  .bs{display:block; position:relative; border-radius:var(--r-card); padding:22px 24px; background:rgba(255,255,255,.5); box-shadow:inset 0 0 0 1px rgba(11,15,18,.08)}
  .bs-h{display:flex; align-items:center; justify-content:space-between; gap:12px}
  .bs-h b{display:flex; align-items:center; gap:10px; font:500 17px/24px var(--font); color:var(--ink-2)}
  .bs p{margin:8px 0 0; font:400 14px/20px var(--font); color:var(--ink-3)}
  .next{padding:26px 28px 10px}

  .s2{display:grid; grid-template-columns:minmax(0,8fr) minmax(0,4fr); grid-template-areas:"matches climb" "matches learned"; gap:24px 40px; align-items:start}
  .s2 .a-climb{grid-area:climb} .s2 .a-matches{grid-area:matches} .s2 .a-learned{grid-area:learned}
  .glow{padding:26px 26px 22px}
  .tiles{grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px}
  .tile{padding:20px 22px}
  .persona{font-size:21px; line-height:28px}
  .live{grid-column:1 / -1}
  .live .body{display:grid; grid-template-columns:minmax(0,5fr) minmax(0,6fr); gap:20px; align-items:start}
  .live .chat{margin-top:12px}
}

@media (prefers-reduced-motion: reduce){
  *{transition-duration:1ms !important; animation:none !important}
  .yes:active{transform:none}
}
}

body{background:var(--bone); background-image:radial-gradient(90% 60% at 20% -10%, rgba(255,255,255,.75), rgba(255,255,255,0) 70%); background-repeat:no-repeat; min-height:100vh}
a{color:inherit; text-decoration:none}
.page{max-width:560px; margin:0 auto}
.flash{margin:0 0 16px; padding:12px 16px; border-radius:18px; background:#fff; box-shadow:var(--shadow-soft); font:400 14px/20px var(--font)}
.flash a{color:inherit; font-weight:600; text-decoration:underline; text-underline-offset:3px}
form{margin:0; display:contents}
.yc details.mx>summary{list-style:none}
.yc details.mx>summary::-webkit-details-marker{display:none}
.yc details.mx[open] ~ .lesson{display:none}
.mx[open]>summary{background:var(--ink); color:#fff; box-shadow:none}
.mx .edit{display:block}
.today>*,.cards>*,.col>*,.yc,.act>*{min-width:0}
.yc .why{overflow-wrap:anywhere}
.peek-note{margin:0 4px; font:400 13px/18px var(--font); color:var(--ink-2)}
.days{display:inline-flex; gap:4px; padding:3px; border-radius:999px; background:var(--chip)}
.days a{padding:4px 12px; border-radius:999px; font:500 12px/16px var(--font); color:var(--ink-2); white-space:nowrap}
.days a.on{background:#fff; color:var(--ink); box-shadow:var(--shadow-soft)}
.agl{display:grid; grid-template-columns:40px minmax(0,1fr) auto; gap:12px; align-items:center; padding:14px 0; border-top:1px solid var(--line)}
.agl:first-child{border-top:0}
.gb[disabled]{opacity:.55; cursor:not-allowed}
.nr a.lk{text-decoration:underline; text-underline-offset:3px; color:var(--ink)}
.days a.live{display:inline-flex; align-items:center; gap:5px}
.no-yet{margin-top:16px; padding:14px 16px; border-radius:var(--r-inner); background:rgba(255,255,255,.7); font:400 15px/22px var(--font)}
@media (min-width: 1024px){ .page{max-width:1376px} }
textarea.typed{width:100%; border:0; background:transparent; resize:none; outline:0}  /* no style attribute: the CSP allows only this sheet */
/* phone first screen: the second waiting card peeks above the tab bar (LOCKS "Today and agent page: A",
   known weakness); the sample day switch fits beside the logo */
@media (max-width: 600px){
  .top{margin:12px 0 16px}
  .top h1{font-size:34px; line-height:38px}
  .today{gap:24px}
  .yc{padding:18px}
  .yc .lesson{margin-top:14px; font-size:21px; line-height:28px}
  .exam{margin-top:14px; padding:10px 14px; gap:12px}
  .stat b{font-size:24px; line-height:30px}
  .act{margin-top:14px}
  .bar:has(.days) .word{display:none}
  .bar{gap:8px}
  .bar-r{gap:6px; min-width:0}
  .bar .sample{padding:4px 8px; letter-spacing:0}
  .bar .days{gap:2px}
  .bar .days a{padding:4px 7px}
}

/* Quick start chat on screen 1 (reflection/quickstart.py): the user's lines, the model's card, its one
   question and its second message, inside the light sage ask card */
.qs .thread{display:flex; flex-direction:column; align-items:flex-end; gap:6px; margin-top:12px}
.qs .said{max-width:86%; margin:0; padding:8px 12px; border-radius:16px; border-bottom-right-radius:6px; background:#e3e9e6; font:400 14px/20px var(--font); white-space:pre-line; overflow-wrap:anywhere}
.qs .plan{margin-top:12px; padding:18px 20px 8px; border-radius:var(--r-inner); background:#fff; box-shadow:var(--shadow-soft)}
.qs .plan h3{margin:0; font:500 21px/28px var(--font); letter-spacing:-.012em; overflow-wrap:anywhere}
.qs .plan dl{margin:8px 0 0}
.qs .plan dl>div{padding:10px 0; border-top:1px solid var(--line)}
.qs .plan dt{font:500 12px/16px var(--font); letter-spacing:.08em; text-transform:uppercase; color:var(--ink-2)}
.qs .plan dd{margin:4px 0 0; font:400 15px/22px var(--font); overflow-wrap:anywhere}
.qs .plan dd p{margin:0}
.qs .plan ul{margin:0; padding-left:18px}
.qs .file.on .fi{background:var(--sage); color:#fff}
.qs .file b{white-space:normal}
.qs .uq{margin:16px 2px 0; font:500 18px/25px var(--font); letter-spacing:-.01em; overflow-wrap:anywhere}
.qs .uf{margin:8px 2px 0; font:400 15px/22px var(--font); color:#2f3433; overflow-wrap:anywhere}
.qs textarea.typed.sm{font-size:18px; line-height:26px}
.qs .act .mod{flex:none}
.qs .over{height:44px; padding:0 14px; border-radius:22px; font:500 14px/44px var(--font); color:var(--ink-2)}
.qs .over:hover{color:var(--ink); background:rgba(255,255,255,.5)}
@media (min-width: 1024px){
  .qs .plan{padding:22px 26px 10px}
  .qs .plan h3{font-size:24px; line-height:30px}
  .qs .plan dd{font-size:16px; line-height:24px}
  .qs .uq{font-size:20px; line-height:28px}
  .qs textarea.typed.sm{font-size:20px; line-height:28px}
}
.conn .act{margin:2px 0 14px}
.conn .yes[disabled]{opacity:.45; cursor:not-allowed; filter:none; transform:none}
.try .thread{display:flex; flex-direction:column; gap:6px; margin-top:12px}
.try .said{max-width:86%; margin:0; padding:8px 12px; border-radius:16px; font:400 14px/20px var(--font); white-space:pre-line; overflow-wrap:anywhere}
.try .said.me{align-self:flex-end; border-bottom-right-radius:6px; background:#e3e9e6}
.try .said.ag{align-self:flex-start; border-bottom-left-radius:6px; background:var(--card-3); box-shadow:inset 0 0 0 1px var(--line)}
.try .said.no{align-self:flex-start; border-bottom-left-radius:6px; background:var(--card-3); box-shadow:inset 0 0 0 1px var(--line); color:var(--ink-2); font-style:italic}
.try .say-f form{margin:0}
.try .over{height:44px; padding:0 14px; border:0; border-radius:22px; background:none; font:500 14px/44px var(--font); color:var(--ink-2); cursor:pointer}
.try .used{align-self:flex-start; margin:0 4px; font:400 12px/16px var(--font); color:var(--ink-2)}
.try details.mine{align-self:flex-start; width:86%}
.try details.mine>summary{list-style:none; cursor:pointer; margin:0 4px; font:500 13px/18px var(--font); color:var(--ink-2)}
.try details.mine>summary::-webkit-details-marker{display:none}
.try details.mine>summary:focus-visible{outline:2px solid var(--ink); outline-offset:2px}
.try details.mine textarea{min-height:120px; font-size:15px; line-height:22px}
.try details.mine .say-f{margin-top:8px}
.trk li.soon{background:none; box-shadow:inset 0 0 0 1px var(--line); color:var(--ink-2)}
.trkc{margin:10px 0 0; font:400 13px/18px var(--font); color:var(--ink-2)}
.trkc b{font-weight:600; color:var(--ink)}

/* the agent page's head and its four tabs (design/boards/pages-r2/structure-b.html) */
.ahead{margin:12px 0 0}
.ahead .back{margin:0}
.ah-row{display:flex; flex-wrap:wrap; align-items:flex-end; justify-content:space-between; gap:12px; margin-top:8px}
.ah-row h1{margin:0; font:300 40px/44px var(--font); letter-spacing:-.035em}
.ah-row p{margin:6px 0 0; font:400 15px/22px var(--font); color:var(--ink-2)}
.cons{display:inline-flex; align-items:center; gap:6px; height:40px; padding:0 14px; border-radius:20px; background:var(--bubble); box-shadow:var(--bubble-shadow), 0 0 0 1px rgba(11,15,18,.06); font:500 14px/1 var(--font); color:var(--ink); white-space:nowrap; flex:none; text-decoration:none}
.cons svg.i{width:16px; height:16px}
.atabs{display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:4px; padding:4px; margin:18px 0 20px; border-radius:24px; background:var(--chip)}
.atabs a{height:42px; border-radius:20px; display:flex; align-items:center; justify-content:center; font:500 13px/1 var(--font); color:var(--ink-2); white-space:nowrap; text-decoration:none}
.atabs a.on{background:var(--card); color:var(--ink); box-shadow:var(--shadow-soft)}
.ov,.ov-l,.ov-r,.ar,.ar-l,.ar-r,.livetab,.lv-l,.lv-r,.lstab{display:flex; flex-direction:column; gap:16px; min-width:0}
.ar-r{order:-1}
.lvc .score{margin:6px 0 0; font:400 15px/22px var(--font); color:var(--ink-2)}
.lvc .score b{font:300 34px/40px var(--font); letter-spacing:-.02em; color:var(--ink)}
.lvc .calm,.lvc .quiet{margin:8px 0 0; font:400 14px/20px var(--font); color:var(--ink-2)}
.lvc .rnd{list-style:none; margin:14px 0 0; padding:0; display:grid; gap:6px}
.lvc .rnd li{display:flex; justify-content:space-between; gap:12px; padding:10px 14px; border-radius:14px; background:var(--chip); font:400 14px/20px var(--font); color:var(--ink-2)}
.lvc .rnd li b{font-weight:500; color:var(--ink)}
.lvc .lab{margin:16px 0 0; font:500 13px/18px var(--font); color:var(--ink)}
.lvc .blk{margin:6px 0 0; padding:0 0 0 18px; display:grid; gap:4px; font:400 14px/20px var(--font); color:var(--ink)}
.lvc .lvb{display:flex; flex-wrap:wrap; gap:8px; margin:16px 0 12px}
.lvc .lvb form{margin:0}
.lb{height:40px; padding:0 16px; border-radius:20px; border:0; background:#fff; box-shadow:inset 0 0 0 1px rgba(42,51,50,.18); font:500 14px/1 var(--font); color:var(--ink); cursor:pointer}
.lb.on{background:var(--ink); color:#fff; box-shadow:none}
.lb:focus-visible{outline:2px solid var(--ink); outline-offset:2px}
.grp-h{display:flex; align-items:center; justify-content:space-between; gap:12px}
.grp-h h3{margin:0}
.lrows{display:flex; flex-direction:column; gap:8px}
.lrow{display:grid; grid-template-columns:minmax(0,1fr) auto; gap:12px; align-items:center; padding:14px 18px; border-radius:20px; background:#fff; box-shadow:var(--shadow-soft); color:inherit; text-decoration:none}
.lrow .who{min-width:0}
.lrow .who b{display:block; font:500 15px/21px var(--font); overflow:hidden; text-overflow:ellipsis; white-space:nowrap}
.lrow .line{display:block; font:400 14px/20px var(--font); color:var(--ink-2); overflow:hidden; text-overflow:ellipsis; white-space:nowrap}
.lrow .meta{display:flex; flex-direction:column; align-items:flex-end; gap:4px}
.lrow small{font:400 12px/16px var(--font); color:var(--ink-3)}
.note{display:flex; align-items:flex-start; gap:14px; padding:18px 20px; border-radius:var(--r-card); background:#fff; box-shadow:var(--shadow-soft)}
.note b{display:block; font:500 16px/22px var(--font)}
.note p{margin:4px 0 0; font:400 14px/21px var(--font); color:var(--ink-2)}
@media (min-width: 1024px){
  .agp{max-width:1180px; margin:0 auto}
  .ahead{margin:32px 0 0}
  .ah-row h1{font-size:56px; line-height:60px}
  .ah-row p{font-size:17px; line-height:24px}
  .cons{height:44px; padding:0 18px; border-radius:22px; font-size:15px}
  .atabs{display:inline-grid; grid-template-columns:repeat(4,128px); margin:24px 0 28px}
  .atabs a{height:44px; font-size:15px}
  .ov{display:grid; grid-template-columns:minmax(0,7fr) minmax(0,5fr); gap:24px; align-items:start}
  .ov-l,.ov-r{gap:20px}
  .ar,.livetab{display:grid; grid-template-columns:minmax(0,8fr) minmax(0,4fr); gap:24px 32px; align-items:start}
  .ar-r{order:2}
  .ar .tiles{grid-template-columns:repeat(2,minmax(0,1fr))}
  .lstab{max-width:880px}
}

/* the agent page layout (2026-11-05): room under the sticky bar, the Arena tab's two column grid, the track's
   equal steps and the stacked action rows (the line, the button, the note under it) */
html{scroll-padding-top:16px}
.ahead{scroll-margin-top:16px}
.arg{display:grid; grid-template-columns:minmax(0,1fr); grid-template-areas:"c" "s" "m"; gap:16px; align-items:start}
.arg-c{grid-area:c; min-width:0}
.arg-m{grid-area:m; min-width:0}
.arg-s{grid-area:s; min-width:0; display:flex; flex-direction:column; gap:16px}
.arg-c:empty,.arg-c:has(> div[data-live]:only-child:empty){display:none}
.arg:has(> .arg-c:empty),.arg:has(> .arg-c > div[data-live]:only-child:empty){grid-template-areas:"s" "m"}
.trc{display:flex; flex-direction:column; gap:16px; min-width:0}
.arg .sec-h{justify-content:flex-start; flex-wrap:wrap; gap:2px 12px}
.arg .sec-h small{color:var(--ink-2)}
.arg .tiles > .ghost{grid-column:1 / -1}
.trk{gap:10px 12px}
.trk li,.trk li.next,.trk li.done,.trk li.soon{gap:8px; margin:0; padding:0; border-radius:0; background:none; box-shadow:none; font:400 14px/20px var(--font)}
.trk li.next{font-weight:600; color:var(--ink)}
.trk li + li::before{width:28px; margin:0 4px 0 0}
.trkc{max-width:65ch; font:400 14px/21px var(--font); text-wrap:pretty}
.trkl{margin:6px 0 0}
.trkl .lk{font:500 14px/20px var(--font); color:var(--ink); text-decoration:underline; text-underline-offset:3px}
.act.stk{display:flex; flex-direction:column; flex-wrap:nowrap; align-items:flex-start; gap:12px; max-width:65ch}
.act.stk > *{flex:none; max-width:100%}
.act.stk p{flex:none; margin:0}
.act.stk .yes{flex:none; width:auto}
.act.stk .nt,.act.stk > button.yes + .no-yet{margin:0; padding:0; border-radius:0; background:none; font:400 13px/19px var(--font); color:var(--ink-2); overflow-wrap:anywhere}
@media (max-width: 599px){
  .trk{display:grid; grid-auto-flow:column; grid-auto-columns:minmax(0,1fr); gap:0; align-items:start}
  .trk li,.trk li.next,.trk li.done,.trk li.soon{position:relative; flex-direction:column; align-items:center; gap:6px; padding:0 4px; text-align:center}
  .trk li + li::before{position:absolute; top:11px; left:calc(-50% + 19px); right:calc(50% + 19px); width:auto; margin:0}
}
@media (min-width: 1024px){
  html{scroll-padding-top:104px}
  .ahead{scroll-margin-top:104px}
  .arg{grid-template-columns:minmax(0,8fr) minmax(0,4fr); grid-template-rows:auto 1fr; grid-template-areas:"c s" "m s"; gap:24px 32px}
  .arg:has(> .arg-c:empty),.arg:has(> .arg-c > div[data-live]:only-child:empty){grid-template-rows:auto; grid-template-areas:"m s"}
  .arg-s{gap:20px}
}

/* the build page (design/boards/pages-r2/build-a.html): a centred thread, the box pinned at the bottom */
.bp{display:flex; flex-direction:column}
.bp .hero{min-height:calc(100vh - 260px); display:flex; flex-direction:column; justify-content:center; padding:24px 4px 0}
.bp .hello{margin:0; font:300 40px/46px var(--font); letter-spacing:-.035em; text-wrap:balance}
.bp .hello span{background:linear-gradient(100deg, var(--sage-a) 0%, var(--sage-b) 55%, var(--sage-c) 100%); -webkit-background-clip:text; background-clip:text; color:transparent}
.bp .hero .sub{margin:12px 0 24px; font:400 15px/22px var(--font); color:var(--ink-2); text-wrap:pretty}
.bp .comp{border-radius:26px; background:#fff; box-shadow:inset 0 0 0 1px rgba(42,51,50,.1), 0 1px 2px rgba(11,15,18,.04), 0 16px 32px -24px rgba(11,15,18,.3); padding:12px 10px 10px 18px}
.bp .comp:focus-within{box-shadow:inset 0 0 0 1.5px rgba(42,51,50,.32), 0 1px 2px rgba(11,15,18,.04), 0 16px 32px -24px rgba(11,15,18,.3)}
.bp .comp textarea{display:block; width:100%; margin:2px 0 0; padding:0; border:0; outline:0; resize:none; background:none; field-sizing:content; min-height:96px; max-height:260px; overflow-y:auto; font:400 17px/24px var(--font); letter-spacing:-.01em; color:var(--ink); box-shadow:none}
.bp .comp textarea::placeholder{color:var(--ink-3); opacity:1}
.bp .crow{display:flex; align-items:center; gap:8px; margin-top:10px; min-width:0}
.bp .crow .sp{flex:1}
.bp .bmode{display:inline-flex; align-items:center; gap:2px; padding:3px; border-radius:18px; background:var(--chip); min-width:0}
.bp .bmode span{display:inline-flex; align-items:center; gap:6px; height:28px; padding:0 10px; border-radius:14px; font:500 13px/1 var(--font); color:var(--ink-2); white-space:nowrap}
.bp .bmode .on{background:#fff; color:var(--ink); box-shadow:var(--shadow-soft)}
.bp .bmode i{font-style:normal; font:500 10px/12px var(--font); letter-spacing:.04em; padding:2px 6px; border-radius:999px; background:rgba(255,255,255,.7); color:var(--ink-3); text-transform:uppercase}
.bp .send{width:44px; height:44px; padding:0; border-radius:50%; display:grid; place-items:center; flex:none}
.bp .send svg.i{stroke-width:2}
.bp .send.pill{width:auto; padding:0 16px 0 18px; border-radius:22px; display:inline-flex; align-items:center; gap:6px; font:500 15px/1 var(--font); white-space:nowrap}
.bthread{display:flex; flex-direction:column; gap:18px; padding:12px 0 210px}
.bp .you{align-self:flex-end; max-width:84%; padding:12px 16px; border-radius:22px 22px 8px 22px; background:#e3e9e6; font:400 16px/23px var(--font); white-space:pre-line; overflow-wrap:anywhere}
.bp .who{display:flex; align-items:center; gap:10px; margin-bottom:8px}
.bp .who .mk{width:28px; height:28px; border-radius:50%; display:grid; place-items:center; background:var(--bubble); box-shadow:var(--bubble-shadow)}
.bp .who .mk svg{width:15px; height:15px}
.bp .who b{font:500 13px/16px var(--font)}
.bp .who small{font:400 12px/16px var(--font); color:var(--ink-3)}
.bp .bot > p{margin:0; font:400 16px/24px var(--font); text-wrap:pretty; overflow-wrap:anywhere}
.bp .bot > p.err{color:var(--ink); padding:12px 14px; border-radius:18px; background:#fff; box-shadow:inset 0 0 0 1px var(--line)}
.bp .acard{margin-top:12px; border-radius:var(--r-card); padding:20px; background:var(--mist); box-shadow:var(--shadow-card), inset 0 1px 0 rgba(255,255,255,.7), inset 0 0 0 1px rgba(42,51,50,.06)}
.bp .acard .lab{color:#2f3433}
.bp .plan{margin-top:10px; padding:16px 18px 6px; border-radius:var(--r-inner); background:rgba(255,255,255,.62); box-shadow:inset 0 0 0 1px rgba(42,51,50,.07)}
.bp .plan h3{margin:0; font:400 24px/30px var(--font); letter-spacing:-.02em; overflow-wrap:anywhere}
.bp .plan dl{margin:8px 0 0}
.bp .plan dl>div{padding:10px 0; border-top:1px solid var(--line)}
.bp .plan dt{font:500 11px/14px var(--font); letter-spacing:.08em; text-transform:uppercase; color:#2f3433}
.bp .plan dd{margin:4px 0 0; font:400 15px/21px var(--font); overflow-wrap:anywhere}
.bp .plan dd p{margin:0}
.bp .plan ul{margin:0; padding-left:18px}
.bp .needs{margin-top:12px}
.bp .file{display:grid; grid-template-columns:40px minmax(0,1fr); align-items:center; gap:12px; margin-top:8px; padding:8px 12px 8px 8px; border-radius:20px; background:rgba(255,255,255,.62); box-shadow:inset 0 0 0 1px rgba(42,51,50,.07)}
.bp .file .fi{width:40px; height:40px; border-radius:14px; display:grid; place-items:center; background:var(--card-4)}
.bp .file .fi svg.i{width:18px; height:18px}
.bp .file b{display:block; font:500 15px/20px var(--font); white-space:normal; overflow-wrap:anywhere}
.bp .file small{display:block; font:400 13px/18px var(--font); color:var(--ink-2)}
.bp .file > span:last-child:empty{display:none}
.bp .file.on .fi{background:var(--sage); color:#fff}
.bp details.need>summary{list-style:none; cursor:pointer}
.bp details.need>summary::-webkit-details-marker{display:none}
.bp details.need>summary:hover .fi{background:var(--card-3)}
.bp details.need>summary:focus-visible{outline:2px solid var(--ink); outline-offset:2px}
.bp details.need[open]>summary .fi{background:var(--ink); color:#fff}
.bp details.need[open]>summary .fi svg.i{transform:rotate(45deg)}
.bp .need .how{margin:6px 0 0; padding:10px 14px; border-radius:16px; background:#fff; box-shadow:inset 0 0 0 1px rgba(42,51,50,.07); font:400 13px/19px var(--font); color:var(--ink-2); overflow-wrap:anywhere}
.bp .need .how p{margin:0}
.bp .need .how p + p{margin-top:8px}
.bp .need .how b, .bp .need .how a{font-weight:500; color:var(--ink)}
.bp .need .how a{text-decoration:underline; text-underline-offset:2px}
.bp .file small.mcp{margin-top:2px; font-size:12px; color:var(--ink-3); cursor:default}
.bp .uq{margin:14px 2px 0; font:500 17px/24px var(--font); overflow-wrap:anywhere}
.bp .cact{display:flex; flex-wrap:wrap; align-items:center; gap:10px 16px; margin-top:16px}
.bp .cact form{margin:0}
.bp .cact .cnote{font:400 13px/18px var(--font); color:var(--ink-2)}
.bp .cact form.lvlf{flex:1 1 100%; display:grid; gap:14px; justify-items:start}
.bp .lvl{border:0; margin:0; padding:0; min-width:0; width:100%; display:grid; gap:8px}
.bp .lvl legend{padding:0; margin:0 0 8px; font:500 13px/18px var(--font); color:var(--ink-2)}
.bp .lv{display:flex; gap:12px; align-items:flex-start; padding:12px 14px; border-radius:16px; background:#fff; box-shadow:inset 0 0 0 1px rgba(42,51,50,.1); cursor:pointer}
.bp .lv:has(input:checked){box-shadow:inset 0 0 0 2px var(--ink)}
.bp .lv input{flex:none; width:18px; height:18px; margin:1px 0 0; accent-color:var(--ink)}
.bp .lv input:focus-visible{outline:2px solid var(--ink); outline-offset:2px}
.bp .lv b{display:flex; align-items:center; gap:8px; font:500 15px/20px var(--font); color:var(--ink)}
.bp .lv small{display:block; margin-top:2px; font:400 13px/18px var(--font); color:var(--ink-2)}
.bp .lv .tip{font:500 11px/1 var(--font); font-style:normal; padding:4px 8px; border-radius:10px; background:var(--volt); color:var(--ink)}
.bp .started{display:inline-flex; align-items:center; gap:8px; height:40px; padding:0 16px 0 12px; border-radius:20px; background:var(--ink); color:#fff; font:500 14px/1 var(--font)}
.bp .started svg.i{width:16px; height:16px; stroke-width:2}
.bp .check{margin-top:4px; border-radius:var(--r-card); background:var(--card); box-shadow:var(--shadow-soft); padding:8px 18px}
.bp .check:empty{display:none}
.bp .step{display:grid; grid-template-columns:28px minmax(0,1fr); gap:12px; align-items:start; padding:10px 0}
.bp .step + .step{border-top:1px solid var(--line)}
.bp .tick{width:28px; height:28px; border-radius:50%; display:grid; place-items:center; background:var(--card-3); box-shadow:inset 0 0 0 1.5px rgba(11,15,18,.12); color:transparent}
.bp .tick svg.i{width:15px; height:15px; stroke-width:2.2}
.bp .step.done .tick{background:var(--sage); color:#fff; box-shadow:none}
.bp .step.work .tick{background:#fff; box-shadow:inset 0 0 0 1.5px rgba(42,51,50,.28)}
.bp .step.work .tick svg{display:none}
.bp .step.work .tick::after{content:""; width:8px; height:8px; border-radius:50%; background:var(--sage); animation:bbreath 1.6s var(--ease) infinite}
@keyframes bbreath{0%,100%{transform:scale(.7); opacity:.55}50%{transform:scale(1); opacity:1}}
.bp .step b{display:block; font:500 15px/20px var(--font); padding-top:4px}
.bp .step p{margin:2px 0 0; font:400 14px/20px var(--font); color:var(--ink-2); overflow-wrap:anywhere}
.bp .step.big b{font:400 22px/28px var(--font); letter-spacing:-.02em; padding-top:0}
.bp .step.big.done .tick{background:var(--ink)}
.bp .took{display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin-top:12px; padding:12px 14px; border-radius:20px; background:var(--card-2); box-shadow:inset 0 0 0 1px var(--line)}
.bp .took .tag{font:500 11px/14px var(--font); letter-spacing:.08em; text-transform:uppercase; padding:4px 9px; border-radius:999px; background:var(--ink); color:#fff}
.bp .took b{flex:1 1 160px; font:400 15px/20px var(--font); overflow-wrap:anywhere}
.bp .took .st{display:inline-flex; align-items:center; gap:6px; font:500 12px/16px var(--font); padding:4px 10px; border-radius:999px; background:rgba(42,51,50,.09)}
.bp .took .st i{width:6px; height:6px; border-radius:50%; background:var(--sage)}
.bp .ready{margin:6px 0 4px 40px}
.bp .ready > p{margin:0; font:400 15px/22px var(--font); color:var(--ink-2)}
.bp .goto{display:flex; flex-wrap:wrap; align-items:center; gap:10px 16px; margin-top:14px}
.bp .goto .yes{text-decoration:none}
.bp .auto{display:flex; align-items:center; gap:10px; font:400 13px/18px var(--font); color:var(--ink-2)}
.bp .auto b{display:inline; font:inherit; padding:0}
.bp .ring{width:22px; height:22px; flex:none}
.bp .ring circle{fill:none; stroke-width:2.4}
.bp .ring .bg{stroke:rgba(11,15,18,.1)}
.bp .ring .fg{stroke:var(--sage); stroke-linecap:round; stroke-dasharray:56.5; stroke-dashoffset:56.5; transform:rotate(-90deg); transform-origin:50% 50%; transition:stroke-dashoffset 1s linear}
.bp .stay{border:0; background:none; padding:0; cursor:pointer; font:500 13px/18px var(--font); color:var(--ink); text-decoration:underline; text-underline-offset:3px; text-decoration-color:rgba(11,15,18,.3)}
.bp .dock{position:fixed; left:0; right:0; bottom:82px; z-index:39; padding:10px 12px 12px; background:linear-gradient(180deg, rgba(244,243,239,0) 0%, rgba(244,243,239,.92) 30%, var(--bone) 100%)}
.bp .dock > *{max-width:760px; margin-left:auto; margin-right:auto}
.bp .dock > form{display:block}
.bp .dock .over{display:block; margin-top:6px; border:0; background:none; font:500 13px/18px var(--font); color:var(--ink-2); text-decoration:underline; text-underline-offset:3px; cursor:pointer}
.bp .dock form + form{display:flex; justify-content:flex-end}
@media (min-width: 1024px){
  .bp .hero,.bthread{width:100%; max-width:760px; margin:0 auto}
  .bp .hero{text-align:center; padding-bottom:64px}
  .bp .hello{font-size:60px; line-height:66px; letter-spacing:-.04em}
  .bp .hero .sub{font-size:17px; line-height:24px}
  .bp .hero .comp{text-align:left}
  .bp .comp{padding:16px 12px 12px 22px}
  .bp .comp textarea{font-size:18px; line-height:26px; min-height:104px}
  .bthread{gap:26px; padding-top:32px}
  .bp .you{max-width:70%}
  .bp .acard{padding:24px 26px}
  .bp .plan dl{display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); column-gap:20px}
  .bp .needs{display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:0 12px; margin-top:16px}
  .bp .needs .lab{grid-column:1 / -1}
  .bp .check{padding:8px 22px}
  .bp .step{padding:12px 0}
  .bp .dock{bottom:0; padding:28px 0 28px}
}
@media (prefers-reduced-motion: reduce){ .runp .spin{animation:none} }
/* the live chats of a running Arena run (pages.py so_far_tiles): the page chat's bubbles, customer right, agent left */
.lc{margin-top:12px}
.lc summary{display:inline-flex; align-items:center; gap:6px; cursor:pointer; list-style:none; font:600 14px/20px var(--font); color:var(--ink-2)}
.lc summary::-webkit-details-marker{display:none}
.lc .thread{display:flex; flex-direction:column; align-items:stretch; gap:6px; margin-top:10px}
.lc .said{max-width:86%; margin:0; padding:8px 12px; border-radius:16px; font:400 14px/20px var(--font); white-space:pre-line; overflow-wrap:anywhere}
.lc .said.me{align-self:flex-end; border-bottom-right-radius:6px; background:#e3e9e6}
.lc .said.ag{align-self:flex-start; border-bottom-left-radius:6px; background:var(--card-3); box-shadow:inset 0 0 0 1px var(--line)}
.lc .said.nil{align-self:flex-start; background:none; color:var(--ink-2); font-style:italic}
.tile.live{box-shadow:var(--shadow-soft), inset 0 0 0 1px var(--line)}
@media (prefers-reduced-motion: reduce){ .live .res .pulse{animation:none} }

"""
