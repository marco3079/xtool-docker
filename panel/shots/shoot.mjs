#!/usr/bin/env node
// Prints automáticos do painel: tira as telas de um site estático (webDir) em cada idioma e tamanho.
// usage: node shoot.mjs <args.json>   (args gravado pelo prints.py em run_dir/args.json)
// Saída: <outDir>/<idioma>/<tamanho>/<NN>-<tela>.png e <outDir>/manifest.json.
// Só usa playwright-core (carregado com NODE_PATH via require, pois ESM não lê NODE_PATH) e módulos nativos.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright-core');

const argsPath = process.argv[2];
if (!argsPath) {
  console.error('uso: node shoot.mjs <args.json>');
  process.exit(2);
}
const A = JSON.parse(fs.readFileSync(argsPath, 'utf8'));

const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json', '.webmanifest': 'application/manifest+json',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.svg': 'image/svg+xml',
  '.webp': 'image/webp', '.ico': 'image/x-icon', '.woff': 'font/woff', '.woff2': 'font/woff2',
  '.ttf': 'font/ttf', '.otf': 'font/otf', '.txt': 'text/plain; charset=utf-8', '.map': 'application/json',
  '.wasm': 'application/wasm', '.mp3': 'audio/mpeg', '.mp4': 'video/mp4',
};

// Servidor estático para a pasta do site. Rota sem extensão que não existe cai no index.html (SPA).
function serveStatic(root) {
  const realRoot = fs.realpathSync(root);
  return http.createServer((req, res) => {
    let p;
    try {
      p = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
    } catch {
      res.writeHead(400);
      return res.end();
    }
    let file = path.normalize(path.join(realRoot, p));
    if (file !== realRoot && !file.startsWith(realRoot + path.sep)) {
      res.writeHead(403);
      return res.end();
    }
    let st = null;
    try {
      st = fs.statSync(file);
    } catch {
      st = null;
    }
    if (st && st.isDirectory()) {
      file = path.join(file, 'index.html');
      try {
        st = fs.statSync(file);
      } catch {
        st = null;
      }
    }
    if (!st && path.extname(p) === '') {
      file = path.join(realRoot, 'index.html');
      try {
        st = fs.statSync(file);
      } catch {
        st = null;
      }
    }
    if (!st || !st.isFile()) {
      res.writeHead(404);
      return res.end('não encontrado');
    }
    res.writeHead(200, {
      'Content-Type': MIME[path.extname(file).toLowerCase()] || 'application/octet-stream',
      'Cache-Control': 'no-store',
    });
    fs.createReadStream(file).pipe(res);
  });
}

function slug(s) {
  const t = String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
    .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40);
  return t || 'tela';
}

function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

async function runAction(page, a) {
  if (a.type === 'click') {
    await page.locator(a.selector).first().click({ timeout: 15000 });
  } else if (a.type === 'type') {
    await page.locator(a.selector).first().fill(a.text, { timeout: 15000 });
  } else if (a.type === 'wait') {
    await page.waitForTimeout(a.ms);
  } else if (a.type === 'eval') {
    await page.evaluate((code) => new Function(code)(), a.js);
  }
}

// Legenda no topo (até 3 linhas) e o print abaixo, com cantos arredondados e sombra, no tamanho w×h.
function captionHtml(dataUrl, caption, w, h) {
  const capFont = Math.round(h * 0.045);
  const imgH = Math.round(h * 0.75);
  const imgW = Math.round((imgH * w) / h);
  const imgTop = h - imgH - Math.round(h * 0.02);
  const radius = Math.round(w * 0.03);
  const capBlock = caption
    ? `<div class="cap">${esc(caption)}</div>`
    : '';
  return `<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;padding:0;width:${w}px;height:${h}px;overflow:hidden;background:${A.background};}
.cap{position:absolute;left:5%;right:5%;top:${Math.round(h * 0.03)}px;text-align:center;color:${A.textColor};
font-family:${A.font};font-size:${capFont}px;line-height:1.15;font-weight:600;display:-webkit-box;
-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;}
.shot{position:absolute;left:${Math.round((w - imgW) / 2)}px;top:${imgTop}px;width:${imgW}px;height:${imgH}px;
border-radius:${radius}px;box-shadow:0 ${Math.round(h * 0.012)}px ${Math.round(h * 0.04)}px rgba(0,0,0,.45);}
</style></head><body>${capBlock}<img class="shot" src="${dataUrl}"></body></html>`;
}

async function makeCaption(browser, png, caption, w, h) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
  try {
    const page = await ctx.newPage();
    const url = 'data:image/png;base64,' + png.toString('base64');
    await page.setContent(captionHtml(url, caption, w, h), { waitUntil: 'load' });
    await page.evaluate(async () => {
      const img = document.querySelector('img.shot');
      if (img && img.decode) {
        try {
          await img.decode();
        } catch {
          /* imagem sem decodificar: o screenshot sai mesmo assim */
        }
      }
    });
    return await page.screenshot({ type: 'png' });
  } finally {
    await ctx.close().catch(() => {});
  }
}

async function main() {
  const locales = A.locales && A.locales.length ? A.locales : ['pt-BR'];
  const sizeIds = Object.keys(A.sizes || {});
  const screens = A.screens || [];
  if (!sizeIds.length || !screens.length) {
    throw new Error('nenhum tamanho ou tela configurado');
  }
  const total = locales.length * sizeIds.length * screens.length;
  const outDir = A.outDir;
  fs.mkdirSync(outDir, { recursive: true });

  const items = [];
  const server = serveStatic(A.webDir);
  await new Promise((ok, bad) => {
    server.once('error', bad);
    server.listen(0, '127.0.0.1', ok);
  });
  const base = `http://127.0.0.1:${server.address().port}`;

  let browser = null;
  let n = 0;
  try {
    browser = await chromium.launch({ args: ['--disable-dev-shm-usage'] });
    for (const locale of locales) {
      for (const sid of sizeIds) {
        const sz = A.sizes[sid];
        const vw = sz.w / sz.dpr;
        const vh = sz.h / sz.dpr;
        fs.mkdirSync(path.join(outDir, locale, sid), { recursive: true });
        for (let i = 0; i < screens.length; i++) {
          const sc = screens[i];
          n++;
          console.log(`print ${n}/${total}: ${locale} ${sid} ${sc.name}`);
          const fileRel = `${locale}/${sid}/${String(i + 1).padStart(2, '0')}-${slug(sc.name)}.png`;
          const ctx = await browser.newContext({
            viewport: { width: vw, height: vh },
            deviceScaleFactor: sz.dpr,
            locale,
            isMobile: true,
            hasTouch: true,
          });
          try {
            if (A.setLocale) {
              await ctx.addInitScript(`(() => { const locale = ${JSON.stringify(locale)};\n${A.setLocale}\n})();`);
            }
            const page = await ctx.newPage();
            const url = sc.path.startsWith('#') ? `${base}/${sc.path}` : `${base}${sc.path}`;
            await page.goto(url, { waitUntil: 'load', timeout: 60000 });
            await page.waitForTimeout(sc.wait ?? 1500);
            for (const act of sc.actions || []) {
              await runAction(page, act);
            }
            const png = await page.screenshot({ type: 'png' });
            let out = png;
            if (A.style === 'caption') {
              const cap = (sc.captions || {})[locale] || '';
              out = await makeCaption(browser, png, cap, sz.w, sz.h);
            }
            fs.writeFileSync(path.join(outDir, fileRel), out);
            items.push({
              file: fileRel, locale, size: sid, store: sz.store, kind: sz.kind,
              screen: sc.name, index: i + 1,
            });
          } catch (e) {
            console.log(`  falhou: ${String((e && e.message) || e).split('\n')[0]}`);
          } finally {
            await ctx.close().catch(() => {});
          }
        }
      }
    }
  } finally {
    fs.writeFileSync(path.join(outDir, 'manifest.json'), JSON.stringify(items, null, 2));
    if (browser) await browser.close().catch(() => {});
    server.close();
  }
  console.log(`✔ ${items.length} de ${total} prints gerados`);
  if (!items.length) {
    process.exitCode = 1;
  }
}

main().catch((e) => {
  console.error(`erro: ${String((e && e.message) || e).split('\n')[0]}`);
  process.exitCode = 1;
});
