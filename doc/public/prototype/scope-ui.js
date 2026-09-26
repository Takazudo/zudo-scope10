'use strict';
const canvas=document.querySelector('#screen'),ctx=canvas.getContext('2d');
const names=['SINE','TRIANGLE','RAMP','PULSE','DC','AM','FM','BEATING','STEPS','COMPOSITE'];
let times=Array(10).fill(3000),ranges=Array(10).fill(5),holding=false,linked=false,frozen=0;
function windowS(raw){return .002*Math.pow(4096,raw/4095)}
function labelTime(sec){return sec<1?`${(sec*1000).toFixed(sec<.01?1:0)} ms`:`${sec.toFixed(2)} s`}
for(let i=0;i<10;i++){
 const el=document.createElement('div');el.className='channel';
 el.innerHTML=`<strong>${String(i+1).padStart(2,'0')} <small>${names[i]}</small></strong><label class="control">TIME <input id="time-${i}" aria-label="Channel ${i+1} time window" type="range" min="0" max="4095" value="3000"><output id="out-${i}"></output></label><fieldset><legend>RANGE ±V</legend>${[3,5,8].map(v=>`<label class="range-label"><input type="radio" name="range-${i}" value="${v}" ${v===5?'checked':''}>${v}</label>`).join('')}</fieldset>`;
 document.querySelector(i<5?'#left':'#right').append(el);
 el.querySelector('input[type=range]').addEventListener('input',e=>{times[i]=+e.target.value;updateLabels()});
 el.querySelectorAll('input[type=radio]').forEach(r=>r.addEventListener('change',e=>ranges[i]=+e.target.value));
}
function updateLabels(){for(let i=0;i<10;i++)document.querySelector(`#out-${i}`).textContent=labelTime(windowS(times[linked?0:i]));document.querySelector('#state').textContent=`${holding?'HOLD':'RUN'} · ${linked?'all TIME follows 01':'independent time'}`}
for(const [id,action] of [['hold',()=>{holding=!holding;if(holding)frozen=performance.now()/1000;return holding}],['link',()=>{linked=!linked;updateLabels();return linked}]])document.querySelector('#'+id).addEventListener('click',e=>{e.currentTarget.setAttribute('aria-pressed',String(action()));updateLabels()});
document.querySelector('#reset').addEventListener('click',()=>{times.fill(3000);ranges.fill(5);holding=linked=false;document.querySelectorAll('input[type=range]').forEach(r=>r.value=3000);document.querySelectorAll('input[type=radio]').forEach(r=>r.checked=r.value==='5');document.querySelector('#hold').setAttribute('aria-pressed','false');document.querySelector('#link').setAttribute('aria-pressed','false');updateLabels()});
function wave(i,t){const s=x=>Math.sin(2*Math.PI*x);switch(i){case 0:return 4*s(t);case 1:return 4*(2/Math.PI)*Math.asin(s(.7*t));case 2:return 6*(t*.8-Math.floor(t*.8))-3;case 3:return s(1.8*t)>0?5:0;case 4:return 2.5;case 5:return 2*s(12*t)*(1+.8*s(.5*t));case 6:return 4*s(8*t+.7*s(.6*t));case 7:return 2*s(9*t)+2*s(9.8*t);case 8:return [0,2,4,-1,-3,1,3,0][Math.floor(t*3+800000)%8];default:return 2.5*s(3*t)+1.3*s(9*t)+.8*s(15*t)}}
function draw(){const now=holding?frozen:performance.now()/1000;ctx.fillStyle='#071716';ctx.fillRect(0,0,320,480);ctx.font='10px monospace';
 for(let i=0;i<10;i++){
  const x=(i<5?0:160),y=(i%5)*96,T=windowS(times[linked?0:i]),range=ranges[i];
  ctx.strokeStyle='#294640';ctx.strokeRect(x+.5,y+.5,159,95);ctx.fillStyle='#b9cbc2';ctx.fillText(`${String(i+1).padStart(2,'0')}  ±${range}V  ${labelTime(T)}`,x+5,y+12);
  const px=x+8,py=y+20,pw=144,ph=62,mid=py+ph/2;ctx.strokeStyle='#35564d';ctx.beginPath();ctx.moveTo(px,mid);ctx.lineTo(px+pw,mid);ctx.stroke();
  let clip=false,previous=null;ctx.strokeStyle=i<5?'#d4e6b5':'#7ed2bc';ctx.beginPath();
  for(let col=0;col<pw;col++){
   let lo=Infinity,hi=-Infinity;
   for(let k=0;k<4;k++){const v=wave(i,now-T+(col+k/4)*T/pw);lo=Math.min(lo,v);hi=Math.max(hi,v)}
   if(lo< -range||hi>range)clip=true;
   const a=mid-Math.max(-range,Math.min(range,hi))/range*(ph/2),b=mid-Math.max(-range,Math.min(range,lo))/range*(ph/2);
   if(previous!==null){ctx.moveTo(px+col-1,previous);ctx.lineTo(px+col,(a+b)/2)}ctx.moveTo(px+col,a);ctx.lineTo(px+col,Math.max(a+.75,b));previous=(a+b)/2;
  }
  ctx.stroke();ctx.fillStyle=clip?'#f0a578':'#8eaaa0';ctx.fillText(clip?'VIEW CLIP':`${wave(i,now).toFixed(2)} V · SIM`,x+6,y+91);
 }
 requestAnimationFrame(draw);
}
updateLabels();draw();
