const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url'),path=require('node:path');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true,args:['--enable-unsafe-swiftshader']});
 try{
  const page=await browser.newPage({viewport:{width:1500,height:1050}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(pathToFileURL(path.resolve('output/space_scale_generalization.html')).href);
  await page.evaluate(()=>window.dheReady);
  assert.equal(await page.locator('#operation option').count(),5);
  assert.equal(await page.locator('#heightLabel').textContent(),'Scale extent');
  assert.equal(await page.locator('#positionLabel').textContent(),'Scale Z');
  const setZ=async z=>{await page.locator('#slicePosition').fill(String(z));await page.locator('#slicePosition').dispatchEvent('input');await page.evaluate(()=>dheViewer.idle());};
  const area=await page.evaluate(()=>dheViewer.section.area);
  for(let i=0;i<5;i++){
   await page.locator('#operation').selectOption(String(i));await page.evaluate(()=>dheViewer.idle());
   for(const z of [0,4.5,5,8,9,9.5,10]){
    await setZ(z);const current=await page.evaluate(()=>dheViewer.section.area);
    assert.ok(Math.abs(current-area)<1e-4,`operation ${i}, Z ${z}: coverage ${current} vs ${area}`);
   }
   if(i===2||i===3){
    await setZ(9);
    const source=await page.evaluate(()=>dheViewer.section.cells.find(c=>c.feature_id==='2001'));
    assert.ok(source);assert.ok(source.area<1e-6);
    if(i===3)assert.equal(source.points.length,1);else assert.ok(source.open.length>0);
   }
   await page.locator('[data-action=f]').click();await page.evaluate(()=>dheViewer.idle());
   await page.locator('[data-action=d]').click();await page.evaluate(()=>dheViewer.idle());
  }
  await page.locator('#operation').selectOption('0');await page.evaluate(()=>dheViewer.idle());
  await setZ(2.5);await page.locator('#connectDual').click();await page.evaluate(()=>dheViewer.idle());
  await page.evaluate(()=>document.querySelector('aside').scrollTop=0);
  await page.screenshot({path:'output/space-scale-simplification.png'});
  await page.locator('#operation').selectOption('3');await page.evaluate(()=>dheViewer.idle());
  await setZ(9);await page.evaluate(()=>document.querySelector('aside').scrollTop=0);
  await page.screenshot({path:'output/space-scale-point-collapse.png'});
  await page.locator('#planeKind').selectOption('inclined');await page.evaluate(()=>dheViewer.idle());
  assert.match(await page.locator('#sectionSummary').textContent(),/plot units/);
  assert.deepEqual(errors,[]);
  console.log('PASS: all five operation selectors; constant coverage across scale and event planes; true terminal line/point; DHE navigation; scale units; inclined slicing.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
