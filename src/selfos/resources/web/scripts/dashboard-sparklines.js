(function(window){'use strict';window.selfosUI.register('sparklines',()=>({init(){
// Sparkline
document.querySelectorAll('.sparkline').forEach(canvas => {
  const values = JSON.parse(canvas.dataset.values);
  const color = canvas.dataset.color;
  const ctx = canvas.getContext('2d');if(!ctx)return;ctx.clearRect(0,0,canvas.width,canvas.height);
  const w = canvas.width, h = canvas.height;
  if (values.filter(v => v !== null).length < 2) return;
  ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.beginPath();
  let first = true;
  values.forEach((v, i) => {
    if (v === null) { first = true; return; }
    const x = (i / (values.length - 1)) * w;
    const y = h - ((v - 1) / 9) * (h - 4) - 2;
    if (first) { ctx.moveTo(x, y); first = false; } else ctx.lineTo(x, y);
  });
  ctx.stroke();
});
}}),{roots:['.grid']});})(window);
