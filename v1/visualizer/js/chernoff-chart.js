/**
 * ============================================================================
 * Chernoff-Hoeffding Security Bound Interactive Canvas Chart (Editorial Theme)
 * ============================================================================
 */

import { state } from './state.js';
import { calculateSecurityBounds } from './quantum-math.js';

export function renderChernoffChart(canvasId = 'chernoffCanvas') {
  const canvas = document.getElementById(canvasId);
  if (!canvas || !canvas.getContext) return;

  const ctx = canvas.getContext('2d');
  const width = canvas.width;
  const height = canvas.height;

  // Clear with off-white background
  ctx.fillStyle = '#f7f7f5';
  ctx.fillRect(0, 0, width, height);

  // Layout Paddings
  const padLeft = 60;
  const padRight = 30;
  const padTop = 30;
  const padBottom = 40;
  const chartW = width - padLeft - padRight;
  const chartH = height - padTop - padBottom;

  // Draw Subtle Grid & Y-Axis Labels
  ctx.strokeStyle = '#d0d0c8';
  ctx.lineWidth = 1;
  ctx.fillStyle = '#555555';
  ctx.font = '11px "JetBrains Mono", monospace';

  for (let i = 0; i <= 5; i++) {
    const y = padTop + (chartH / 5) * i;
    ctx.beginPath();
    ctx.moveTo(padLeft, y);
    ctx.lineTo(padLeft + chartW, y);
    ctx.stroke();

    const probVal = (1.0 - (i / 5.0)).toFixed(1);
    ctx.fillText(probVal, 20, y + 4);
  }

  // Draw X-Axis Ticks & Labels (Signature Length L from 16 to 512)
  const xSteps = [16, 128, 256, 384, 512];
  xSteps.forEach(lVal => {
    const x = padLeft + ((lVal - 16) / (512 - 16)) * chartW;
    ctx.beginPath();
    ctx.moveTo(x, padTop + chartH);
    ctx.lineTo(x, padTop + chartH + 5);
    ctx.stroke();

    ctx.fillText(`${lVal}`, x - 10, padTop + chartH + 18);
  });

  // Axis Titles
  ctx.fillStyle = '#141414';
  ctx.font = '11px "JetBrains Mono", monospace';
  ctx.fillText('Signature Length (L qubits)', padLeft + chartW / 2 - 75, height - 6);
  
  ctx.save();
  ctx.translate(14, padTop + chartH / 2 + 35);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText('Insecurity Probability P', 0, 0);
  ctx.restore();

  const delta = (0.25 - state.chNoise) / 3.0;
  const gap = (0.25 - delta) - (state.chNoise + delta);

  // Helper: Draw Smooth Function Curve
  function drawFunctionCurve(calcFn, strokeColor, lineWidth = 2) {
    ctx.strokeStyle = strokeColor;
    ctx.lineWidth = lineWidth;
    ctx.beginPath();

    for (let x = 0; x <= chartW; x += 2) {
      const lVal = 16 + (x / chartW) * (512 - 16);
      const pVal = calcFn(lVal);
      const yCoord = padTop + chartH * (1.0 - pVal);

      if (x === 0) ctx.moveTo(padLeft + x, yCoord);
      else ctx.lineTo(padLeft + x, yCoord);
    }
    ctx.stroke();
  }

  // 1. Draw Forgery Bound Curve P_forge <= exp(-2 * delta^2 * L) [Dark Blue / Charcoal Ink]
  drawFunctionCurve(
    (l) => Math.min(1.0, Math.exp(-2.0 * (delta ** 2) * l)),
    '#2c5282',
    2.2
  );

  // 2. Draw Repudiation Bound Curve P_rep <= 2 * exp(-0.5 * gap^2 * L) [Muted Purple Ink]
  drawFunctionCurve(
    (l) => Math.min(1.0, 2.0 * Math.exp(-0.5 * (gap ** 2) * l)),
    '#634375',
    2.2
  );

  // 3. Highlight Current Selected L Value (Solid Black Line)
  const currentL = Math.max(16, Math.min(512, state.chLength));
  const currentX = padLeft + ((currentL - 16) / (512 - 16)) * chartW;
  
  ctx.strokeStyle = '#141414';
  ctx.setLineDash([4, 3]);
  ctx.lineWidth = 1.2;
  ctx.beginPath();
  ctx.moveTo(currentX, padTop);
  ctx.lineTo(currentX, padTop + chartH);
  ctx.stroke();
  ctx.setLineDash([]);

  // Marker Point for Current Forgery
  const currentPForge = Math.min(1.0, Math.exp(-2.0 * (delta ** 2) * currentL));
  const markerY = padTop + chartH * (1.0 - currentPForge);

  ctx.fillStyle = '#141414';
  ctx.beginPath();
  ctx.arc(currentX, markerY, 5, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = '#ffffff';
  ctx.lineWidth = 1.5;
  ctx.stroke();
}
