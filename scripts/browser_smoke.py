#!/usr/bin/env python3
"""Browser DOM/canvas smoke checks using local HTML bytes (no network navigation).
The delivery environment blocked loopback browser navigation. This checks inline
UI only; the standalone ESM/GLB viewer still needs a normal local browser test.
"""
from pathlib import Path
import json,shutil,re
from playwright.sync_api import sync_playwright
R=Path(__file__).resolve().parents[1];errors=[];results=[]
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path=shutil.which('chromium'),headless=True,args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1440,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
 html=(R/'offline/index.html').read_text();html=html.replace('<link rel="stylesheet" href="style.css">','<style>'+(R/'offline/style.css').read_text()+'</style>');html=re.sub(r'<img [^>]+>','',html)
 page.set_content(html);page.fill('#search','TLV9064');assert page.locator('.card:visible').count()==1;results.append('Inline offline catalogue search')
 html=(R/'doc/public/prototype/index.html').read_text().replace('<script src="scope-ui.js"></script>','<script>'+(R/'doc/public/prototype/scope-ui.js').read_text()+'</script>')
 page.set_content(html);assert page.locator('input[type=range]').count()==10;assert page.locator('input[type=radio]').count()==30
 for i,v in [(0,1000),(5,3000)]:page.locator(f'#time-{i}').evaluate('(e,v)=>{e.value=v;e.dispatchEvent(new Event("input",{bubbles:true}))}',v)
 a=page.locator('#out-0').inner_text();b=page.locator('#out-5').inner_text();assert a!=b
 page.click('#link');assert page.locator('#out-5').inner_text()==a
 page.click('#link');assert page.locator('#out-5').inner_text()==b
 page.click('#hold');assert page.locator('#hold').get_attribute('aria-pressed')=='true';page.wait_for_timeout(100)
 one=page.locator('#screen').evaluate('(e)=>e.toDataURL()');page.wait_for_timeout(100);assert one==page.locator('#screen').evaluate('(e)=>e.toDataURL()')
 page.screenshot(path=str(R/'reports/ui-desktop.png'),full_page=True);results.append('Ten controls / three ranges / link restores local positions / hold freezes pixels')
 page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(100)
 assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1');page.screenshot(path=str(R/'reports/ui-mobile.png'),full_page=True);results.append('390px mobile viewport: no document horizontal overflow')
 browser.close()
report={'result':'PASS' if not errors else 'FAIL','mode':'Inline local HTML/JS bytes, no URL navigation','checks':results,'page_errors':errors,'not_run':['HTTP/file URL loading','Standalone ESM/GLB model viewer','Native zudo-doc build','Physical LCD'],'environment_note':'Initial loopback navigation returned ERR_BLOCKED_BY_ADMINISTRATOR; no browser policy settings were changed.'}
(R/'reports/browser-smoke.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
raise SystemExit(0 if not errors else 1)
