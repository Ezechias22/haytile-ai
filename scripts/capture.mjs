// Capture actual UI and rasterize our original SVG mark; no generated AI results.
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
const require=createRequire(new URL('../apps/web/package.json',import.meta.url));
const {chromium}=require('@playwright/test');
const server=require('@sparticuz/chromium').default||require('@sparticuz/chromium');
const browser=await chromium.launch({executablePath:await server.executablePath(),args:server.args.filter(a=>a!=='--disable-web-security'),headless:true});
try{
 await fs.mkdir(new URL('../artifacts/',import.meta.url),{recursive:true});
 const page=await browser.newPage({viewport:{width:1440,height:1050},deviceScaleFactor:1});
 await page.addInitScript(()=>localStorage.setItem('haytile-locale','ht'));
 await page.goto('http://localhost:3000');
 await page.getByRole('heading',{name:'Kisa w ap kreye jodi a?'}).waitFor();
 await page.screenshot({path:new URL('../artifacts/haytile-web.png',import.meta.url).pathname,fullPage:true});
 await page.setViewportSize({width:390,height:844});
 await page.screenshot({path:new URL('../artifacts/haytile-web-mobile.png',import.meta.url).pathname,fullPage:true});
 const mark=await fs.readFile(new URL('../apps/web/public/mark.svg',import.meta.url),'utf8');
 const icon=await browser.newPage({viewport:{width:1024,height:1024},deviceScaleFactor:1});
 await icon.setContent('<style>body{margin:0;background:#111219}svg{display:block;width:1024px;height:1024px}</style>'+mark);
 await fs.mkdir(new URL('../apps/mobile/assets/',import.meta.url),{recursive:true});
 await icon.screenshot({path:new URL('../apps/mobile/assets/icon.png',import.meta.url).pathname});
 console.log('Captured real web screenshots and rendered the original brand icon.');
}finally{await browser.close()}
