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
.sample{font:500 12px/16px var(--font); letter-spacing:.04em; color:var(--ink-2); padding:4px 12px; border-radius:999px; background:var(--chip)}
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
.no{width:52px; height:52px; border-radius:50%; display:grid; place-items:center; flex:none; background:var(--bubble); box-shadow:var(--bubble-shadow), 0 0 0 1px rgba(11,15,18,.06); font:500 15px/1 var(--font); color:var(--ink);
  transition:transform var(--t-press) var(--ease)}
.no:active{transform:scale(.97)}

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
.st{font:500 11px/14px var(--font); padding:3px 8px; border-radius:999px; background:var(--chip); color:var(--ink-2)}
.st.live{background:rgba(42,51,50,.09); color:var(--ink)}

/* empty state */
.calm{display:flex; align-items:center; gap:14px; padding:20px 22px; border-radius:var(--r-card); background:rgba(255,255,255,.5); box-shadow:inset 0 0 0 1px rgba(11,15,18,.08)}
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
.states span{display:inline-flex; align-items:center; gap:7px; padding:5px 11px; border-radius:999px; font:500 12px/16px var(--font); color:rgba(255,255,255,.62)}
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
  .calm{padding:28px 32px}

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
.days a{padding:4px 12px; border-radius:999px; font:500 12px/16px var(--font); color:var(--ink-2)}
.days a.on{background:#fff; color:var(--ink); box-shadow:var(--shadow-soft)}
.agl{display:grid; grid-template-columns:40px minmax(0,1fr) auto; gap:12px; align-items:center; padding:14px 0; border-top:1px solid var(--line)}
.agl:first-child{border-top:0}
.gb[disabled]{opacity:.55; cursor:not-allowed}
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
  .bar .sample{padding:4px 8px}
  .bar .days a{padding:4px 9px}
}

"""
