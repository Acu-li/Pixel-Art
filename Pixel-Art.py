from flask import Flask, request, send_file, render_template_string
from PIL import Image
import io

app = Flask(__name__)

# Single-file Flask app: background image, paint canvas, grid canvas with upload/preview button
# Final export scales the pixel-art to 4K resolution (4096x4096) via nearest-neighbor
INDEX_HTML = '''<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Acu.li Pixel-Art</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.0.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { background: #f8f9fa; }
    #canvasContainer {
      position: relative;
      border: 1px solid #ccc;
      margin: auto;
      user-select: none;
      touch-action: none;
      background: white;
    }
    #canvasContainer canvas {
      position: absolute;
      top: 0;
      left: 0;
      image-rendering: pixelated;
      width: 100%;
      height: 100%;
    }
    #bgCanvas { z-index: 0; }
    #gridCanvas { z-index: 1; pointer-events: none; }
    #paintCanvas { z-index: 2; }
    .palette-swatch {
      width: 24px; height: 24px;
      cursor: pointer;
      border: 2px solid transparent;
      margin: 2px;
    }
    .palette-swatch.active { border-color: #000; }
  </style>
</head>
<body>
<div class="container py-3">
  <h1 class="mb-3 text-center">Acu.li Pixel-Art</h1>
  <div class="input-group mb-3">
    <input type="file" id="imageUpload" accept="image/*" class="form-control">
    <button id="applyImage" class="btn btn-outline-secondary">Bild anzeigen</button>
  </div>
  <div class="row mb-3">
    <div class="col-md-3 mb-2">
      <label for="resolution" class="form-label">Auflösung</label>
      <select id="resolution" class="form-select">
        <option value="512">512×512</option>
        <option value="256" selected>256×256</option>
        <option value="128">128×128</option>
      </select>
    </div>
    <div class="col-md-6 mb-2">
      <label class="form-label">Palette (16 Farben + Custom)</label>
      <div id="paletteContainer" class="d-flex flex-wrap align-items-center">
        <input type="color" id="customColor" class="form-control form-control-color ms-2" value="#000000" title="Custom Color">
      </div>
    </div>
    <div class="col-md-3 mb-2 d-flex align-items-end">
      <button id="zoomIn" class="btn btn-secondary me-2">Plus</button>
      <button id="zoomOut" class="btn btn-secondary">Minus</button>
    </div>
  </div>
  <div id="canvasContainer" style="width:512px; height:512px;">
    <canvas id="bgCanvas"></canvas>
    <canvas id="gridCanvas"></canvas>
    <canvas id="paintCanvas"></canvas>
  </div>
  <div class="text-center mt-3"><button id="downloadBtn" class="btn btn-primary">Download 4K PNG</button></div>
</div>
<script>
// Palette setup
const paletteHex = ['#1E2328','#787082','#F0F5FA','#F0C0B4','#B4A85A','#F02328','#F07028','#F0F528','#1EF528','#50C3FA','#1E23FA','#8C23FA','#F055C8','#782328','#B4B928','#1E2382'];
const paletteContainer = document.getElementById('paletteContainer');
const customInput = document.getElementById('customColor');
let selectedColor = paletteHex[0];

// Create swatches
paletteHex.forEach((hex, idx) => {
  const sw = document.createElement('div');
  sw.classList.add('palette-swatch');
  sw.style.backgroundColor = hex;
  sw.title = hex;
  sw.onclick = () => selectSwatch(idx);
  paletteContainer.insertBefore(sw, customInput);
});
function selectSwatch(idx) {
  document.querySelectorAll('.palette-swatch').forEach((el,i) => el.classList.toggle('active', i===idx));
  selectedColor = paletteHex[idx]; customInput.value = selectedColor;
}
customInput.oninput = () => {
  selectedColor = customInput.value;
  document.querySelectorAll('.palette-swatch').forEach(el => el.classList.remove('active'));
};
selectSwatch(0);

// Canvas and state
const bgCanvas = document.getElementById('bgCanvas');
const gridCanvas = document.getElementById('gridCanvas');
const paintCanvas = document.getElementById('paintCanvas');
const container = document.getElementById('canvasContainer');
const resSelect = document.getElementById('resolution');
const zoomIn = document.getElementById('zoomIn');
const zoomOut = document.getElementById('zoomOut');
const downloadBtn = document.getElementById('downloadBtn');
let resolution = parseInt(resSelect.value), pixelData = [], zoom = 512/resolution, tmpBgCanvas = null;
let drawing = false;

function initGrid() {
  resolution = parseInt(resSelect.value);
  pixelData = Array.from({length:resolution}, ()=>Array.from({length:resolution}, ()=>[0,0,0,0]));
  [bgCanvas, gridCanvas, paintCanvas].forEach(c => { c.width = resolution; c.height = resolution; });
  container.style.width = resolution*zoom+'px'; container.style.height = resolution*zoom+'px';
  drawGrid(); paintCanvas.getContext('2d').clearRect(0,0,resolution,resolution);
  if(tmpBgCanvas) {
    const ctx = bgCanvas.getContext('2d');
    ctx.clearRect(0,0,resolution,resolution);
    ctx.drawImage(tmpBgCanvas, 0,0, tmpBgCanvas.width, tmpBgCanvas.height, 0,0, resolution,resolution);
  }
}

function drawGrid() {
  const ctx = gridCanvas.getContext('2d');
  ctx.clearRect(0,0,resolution,resolution);
  ctx.strokeStyle = 'rgba(0,0,0,0.2)';
  for(let i=0;i<=resolution;i++){
    ctx.beginPath(); ctx.moveTo(i+0.5,0); ctx.lineTo(i+0.5,resolution); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(0,i+0.5); ctx.lineTo(resolution,i+0.5); ctx.stroke();
  }
}

function paintAt(e, erase=false) {
  const rect = paintCanvas.getBoundingClientRect();
  const x = Math.floor((e.clientX-rect.left)*resolution/rect.width);
  const y = Math.floor((e.clientY-rect.top)*resolution/rect.height);
  if(x<0||y<0||x>=resolution||y>=resolution) return;
  const ctx = paintCanvas.getContext('2d');
  if(erase) {
    pixelData[y][x] = [0,0,0,0];
    paintCanvas.getContext('2d').clearRect(x,y,1,1);
  } else {
    let hex = selectedColor;
    let r8 = parseInt(hex.substr(1,2),16), g8 = parseInt(hex.substr(3,2),16), b8 = parseInt(hex.substr(5,2),16);
    let r5 = (r8>>3)<<3, g6 = (g8>>2)<<2, b5 = (b8>>3)<<3;
    pixelData[y][x] = [r5,g6,b5,255];
    ctx.fillStyle = `rgba(${r5},${g6},${b5},1)`;
    ctx.fillRect(x,y,1,1);
  }
}

paintCanvas.addEventListener('contextmenu', e => e.preventDefault());
paintCanvas.addEventListener('mousedown', e => {
  if(e.button===0) drawing=true, paintAt(e,false);
  if(e.button===2) paintAt(e,true);
});
paintCanvas.addEventListener('mouseup', e => { if(e.button===0) drawing=false; });
paintCanvas.addEventListener('mouseleave', () => drawing=false);
paintCanvas.addEventListener('mousemove', e => { if(drawing) paintAt(e,false); });

zoomIn.onclick = ()=>{ zoom*=1.2; container.style.width=resolution*zoom+'px'; container.style.height=resolution*zoom+'px'; };
zoomOut.onclick = ()=>{ zoom/=1.2; container.style.width=resolution*zoom+'px'; container.style.height=resolution*zoom+'px'; };
resSelect.onchange = initGrid;

// Upload
const applyBtn = document.getElementById('applyImage');
document.getElementById('imageUpload').onchange = e => {
  const file = e.target.files[0]; if(!file) return;
  const img = new Image();
  img.onload = () => {
    const size = Math.min(img.width, img.height);
    const offX = (img.width-size)/2, offY = (img.height-size)/2;
    tmpBgCanvas = document.createElement('canvas'); tmpBgCanvas.width=tmpBgCanvas.height=size;
    tmpBgCanvas.getContext('2d').drawImage(img,offX,offY,size,size,0,0,size,size);
    applyBtn.disabled=false;
  };
  img.src = URL.createObjectURL(file);
};
applyBtn.onclick = ()=>{ if(tmpBgCanvas) initGrid(); };
applyBtn.disabled = true;
initGrid();

// Download
// Sends pixelData and resolution; backend rescales to 4K

downloadBtn.onclick = ()=>{ fetch('/export',{
    method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({ size:resolution, pixels:pixelData.map(r=>r.map(c=>c.slice(0,3))) })
  })
  .then(r=>r.blob())
  .then(blob=>{ const url=URL.createObjectURL(blob), a=document.createElement('a'); a.href=url; a.download='pixelart_4k.png'; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url); });
};
</script>
</body>
</html>'''

@app.route('/')
def index(): return render_template_string(INDEX_HTML)

@app.route('/export', methods=['POST'])
def export_image():
    data = request.get_json(force=True)
    size = data.get('size')
    pixels = data.get('pixels')
    # Create base pixel-art image
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    for y, row in enumerate(pixels):
        for x, (r_val, g_val, b_val) in enumerate(row):
            img.putpixel((x, y), (r_val, g_val, b_val, 255))
    # Scale to 4K square (4096x4096) using nearest neighbor
    target = 4096
    img = img.resize((target, target), resample=Image.NEAREST)
    buf = io.BytesIO()
    img.save(buf, 'PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png', as_attachment=True, download_name='pixelart_4k.png')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8899, debug=False)
