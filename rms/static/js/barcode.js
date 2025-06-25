let buffer = "";
let lastTime = Date.now();

document.addEventListener('keypress', e => {
  const char = e.key;
  const now  = Date.now();

  if (now - lastTime > 100) buffer = "";  // new input
  lastTime = now;

  if (char === 'Enter') {
    if (buffer) handleScanned(buffer);
    buffer = "";
  } else if (char.length === 1) {
    buffer += char;
  }
});

function handleScanned(code) {
  const inp = document.getElementById('barcodeInput');
  if (inp) {
    inp.value = code;
    inp.dispatchEvent(new Event('input'));
    inp.classList.add('scan-ok');
    setTimeout(()=> inp.classList.remove('scan-ok'), 200);
  }
}
