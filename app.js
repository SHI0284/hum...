const screens=[...document.querySelectorAll('.screen')];
const steps=[...document.querySelectorAll('.step')];
const dots=[...document.querySelectorAll('.dots i')];
const order=['home','record','archive','artwork'];
function show(id){
  screens.forEach(s=>s.classList.toggle('active',s.id===id));
  const mapped=id==='processing'?'archive':id;
  const index=Math.max(0,order.indexOf(mapped));
  steps.forEach((s,i)=>s.classList.toggle('active',i===index));
  dots.forEach((d,i)=>d.style.background=i===index?'#fff':'transparent');
}
steps.forEach(s=>s.addEventListener('click',()=>show(s.dataset.screen)));
document.querySelectorAll('[data-next]').forEach(b=>b.addEventListener('click',()=>show(b.dataset.next)));
const wave=document.getElementById('wave');
for(let i=0;i<56;i++){const b=document.createElement('b');b.style.setProperty('--h',`${7+Math.sin(i*.55)**2*30}%`);wave.append(b)}
let recording=false,started=0,raf;
document.getElementById('recordButton').addEventListener('click',()=>{
  if(recording)return; recording=true;started=performance.now();
  function tick(now){
    const elapsed=Math.min(5,(now-started)/1000);document.getElementById('timer').textContent=`00:0${Math.floor(elapsed)}`;
    [...wave.children].forEach((b,i)=>b.style.setProperty('--h',`${8+Math.random()*55*(.45+Math.sin(i*.35)**2)}%`));
    if(elapsed<5)raf=requestAnimationFrame(tick);else{recording=false;show('archive')}
  }raf=requestAnimationFrame(tick);
});
document.querySelectorAll('.play').forEach(b=>b.addEventListener('click',()=>{b.textContent=b.textContent==='▶'?'Ⅱ':'▶'}));
document.querySelectorAll('.heart').forEach(b=>b.addEventListener('click',()=>{b.classList.toggle('selected');b.textContent=b.classList.contains('selected')?'♥':'♡'}));
document.querySelectorAll('.choose').forEach(b=>b.addEventListener('click',()=>{
  document.querySelectorAll('.choose').forEach(x=>x.classList.remove('chosen'));b.classList.add('chosen');show('processing');setTimeout(()=>show('artwork'),1800);
}));
document.getElementById('again').addEventListener('click',()=>show('record'));
document.getElementById('list').addEventListener('click',()=>show('archive'));
const listen=document.getElementById('listen');listen.addEventListener('click',()=>listen.querySelector('span').textContent=listen.querySelector('span').textContent==='LISTEN'?'PAUSE':'LISTEN');
const overlay=document.getElementById('volumeOverlay');
document.getElementById('soundButton').addEventListener('click',()=>{overlay.classList.add('open');overlay.setAttribute('aria-hidden','false')});
overlay.querySelector('.sound').addEventListener('click',()=>{overlay.classList.remove('open');overlay.setAttribute('aria-hidden','true')});
document.getElementById('volume').addEventListener('input',e=>document.getElementById('overlaySoundIcon').src=Number(e.target.value)===0?'assets/mute2.svg':'assets/icon_sound.svg');
show('home');
