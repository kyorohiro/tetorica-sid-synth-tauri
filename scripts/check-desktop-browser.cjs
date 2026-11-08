// Exercise the packaged frontend and actual WASM/AudioWorklets with a mocked
// desktop IPC host. Speakers stay muted; this does not test a CPAL device.
const {chromium, webkit} = require('playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const http = require('node:http');

const root = path.resolve(__dirname, '..');
const nativeSource = require('node:fs').readFileSync(path.join(root,'src-tauri/src/audio.rs'),'utf8');
const nativeCredits = Number(/const QUEUE_PACKETS: usize = (\d+);/.exec(nativeSource)[1]);
const nativePrefillPackets = Number(/const PREFILL_PACKETS: usize = (\d+);/.exec(nativeSource)[1]);
const options = {out:path.join(root,'docs/desktop_browser_20261108.json'), screenshots:null};
for(let index=2;index<process.argv.length;index++) {
  const name=process.argv[index].replace(/^--/,'');
  assert(Object.hasOwn(options,name),`Unknown option: ${name}`);
  assert(process.argv[index+1],`Missing value: ${name}`);
  options[name]=path.resolve(process.argv[++index]);
}
const mime = {'.html':'text/html','.js':'text/javascript','.css':'text/css','.wasm':'application/wasm',
  '.json':'application/json','.webp':'image/webp','.png':'image/png','.svg':'image/svg+xml'};
async function run(name, engine, backend) {
  const browser=await engine.launch({headless:true});
  const page=await browser.newPage({viewport:{width:1280,height:1000},acceptDownloads:true});page.setDefaultTimeout(15000);
  const errors=[],missing=[],consoleErrors=[],checks=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('console',message=>{if(message.type()==='error')consoleErrors.push(message.text());});
  const desktop=await fs.readFile(path.join(root,'desktop/desktop-interface.js'),'utf8');
  const overlay=(await fs.readFile(path.join(root,'desktop/synth-bridge.js'),'utf8'))+'\n;\n'+(await fs.readFile(path.join(root,'desktop/audio-interface.js'),'utf8'));
  await page.route('**/*',async route=>{
    const url=new URL(route.request().url());if(['blob:','data:'].includes(url.protocol))return route.continue();
    if(url.hostname!=='tauri.localhost'){missing.push(url.href);return route.abort();}
    try{
      const file=url.pathname==='/desktop-audio-worklet.js'?path.join(root,'desktop/audio-worklet.js'):path.resolve(root,'dist','.'+decodeURIComponent(url.pathname==='/'?'/index.html':url.pathname));
      assert(file.startsWith(path.join(root,'dist')+path.sep)||file===path.join(root,'desktop/audio-worklet.js'));
      let body=await fs.readFile(file);if(url.pathname==='/synth-sid/synth.js')body=Buffer.concat([body,Buffer.from('\n;\n'+overlay)]);
      return route.fulfill({status:200,body,contentType:mime[path.extname(file)]||'application/octet-stream',headers:{'access-control-allow-origin':'*'}});
    }catch(error){missing.push(url.pathname+': '+error.message);return route.fulfill({status:404,body:'Missing asset'});}
  });
  await page.addInitScript(({backend,nativeCredits})=>{
    const audit=window.desktopAudit={calls:[],saves:[],contexts:[],worklets:[],speakerEdges:new Map(),
      pinned:false,nextRead:0,packets:0,returned:0,nativePeak:0,nativeFinite:true,nativeSession:0,failWrites:false,holdStart:false,cancelSave:false,sessions:new Map()};
    const Context=window.AudioContext??window.webkitAudioContext, Node=window.AudioWorkletNode;
    const connect=AudioNode.prototype.connect,disconnect=AudioNode.prototype.disconnect;
    window.AudioContext=class extends Context {constructor(...args){
      super(...args);audit.contexts.push(this);
      // Playwright page routes do not see AudioWorklet module fetches. Serve
      // those exact bytes through a real CORS-enabled loopback test server.
      const add=this.audioWorklet.addModule.bind(this.audioWorklet);
      this.audioWorklet.addModule=(url,...options)=>{
        const value=new URL(url,location.href);
        return add(value.hostname==='tauri.localhost'?new URL(value.pathname+value.search,backend).href:url,...options);
      };
    }};
    if(window.webkitAudioContext) window.webkitAudioContext=window.AudioContext;
    window.AudioWorkletNode=class extends Node {constructor(...args){super(...args);audit.worklets.push({node:this,name:args[1]});}};
    AudioNode.prototype.connect=function(destination,...args){
      if(destination!==this.context.destination) return connect.call(this,destination,...args);
      const analyser=this.context.createAnalyser();analyser.fftSize=4096;
      const mute=this.context.createGain();mute.gain.value=0;
      connect.call(this,analyser);connect.call(analyser,mute);connect.call(mute,destination);
      audit.speakerEdges.set(this,{analyser,mute});return destination;
    };
    AudioNode.prototype.disconnect=function(destination,...args){
      const edge=audit.speakerEdges.get(this);
      if(edge&&(arguments.length===0||destination===this.context.destination)) {
        disconnect.call(this,edge.analyser);disconnect.call(edge.analyser);disconnect.call(edge.mute);audit.speakerEdges.delete(this);
        if(arguments.length) return;
      }
      return arguments.length?disconnect.call(this,destination,...args):disconnect.call(this);
    };
    audit.read=(kind='keyboard')=>new Promise((resolve,reject)=>{
      const node=audit.worklets.findLast(entry=>entry.name===(kind==='preview'?'tetorica-sid-player':'tetorica-sid-synth')&&entry.node.context.state!=='closed')?.node;
      if(!node) return reject(Error('No synth worklet'));
      const id=--audit.nextRead,timer=setTimeout(()=>{node.port.removeEventListener('message',receive);reject(Error('Read timed out'));},5000);
      function receive({data}) {if(data.id!==id)return;clearTimeout(timer);node.port.removeEventListener('message',receive);data.error?reject(Error(data.error)):resolve(data.value);}
      node.port.addEventListener('message',receive);node.port.start();node.port.postMessage({id,method:'read',args:[]});
    });
    audit.webPeak=async()=>{
      const {output}=await window.tetoricaSynthAudio.ensureReady(),edge=audit.speakerEdges.get(output);
      if(!edge)return 0;const samples=new Float32Array(edge.analyser.fftSize);edge.analyser.getFloatTimeDomainData(samples);
      return samples.reduce((peak,value)=>Math.max(peak,Math.abs(value)),0);
    };
    window.__TAURI_INTERNALS__={invoke:async(command,args={},options)=>{
      audit.calls.push({command,session:args?.session,bytes:args instanceof ArrayBuffer?args.byteLength:null});
      if(command==='window_pin_state')return audit.pinned;
      if(command==='set_window_pin')return audit.pinned=args.pinned;
      if(command==='save_export_binary') {
        const length=new DataView(args).getUint32(0,true),header=JSON.parse(new TextDecoder().decode(new Uint8Array(args,4,length)));
        const bytes=new Uint8Array(args,4+length),text=new TextDecoder().decode(bytes);
        audit.saves.push({header,text,bytes:[...bytes]});return audit.cancelSave?null:'/tmp/'+header.filename;
      }
      if(command==='audio_devices')return [{id:'offline-test',name:'Offline test device',isDefault:true}];
      if(command==='audio_start') {
        if(audit.holdStart)await new Promise(resolve=>{audit.releaseStart=()=>{audit.holdStart=false;resolve();};});
        const session=`offline-${++audit.nativeSession}`;audit.sessions.set(session,{packets:0,returned:0});return {session,frames:512,credits:nativeCredits,sampleRate:48000};
      }
      if(command==='audio_stop')return null;
      if(command==='audio_write') {
        if(audit.failWrites)throw Error('Injected offline device failure');
        const session=audit.sessions.get(options.headers['x-synth-audio-session']);if(!session)throw Error('Unknown write session');const samples=new Float32Array(args),packets=args.byteLength/(512*8);session.packets+=packets;audit.packets+=packets;
        for(const value of samples){audit.nativeFinite&&=Number.isFinite(value);audit.nativePeak=Math.max(audit.nativePeak,Math.abs(value));}
        return {rustMicros:100,serviceMicros:200};
      }
      if(command==='audio_poll') {
        await new Promise(resolve=>setTimeout(resolve,20));const session=audit.sessions.get(args.session);const credits=session?Math.min(nativeCredits,session.packets-session.returned):0;if(session)session.returned+=credits;
        return {credits,queuedFrames:1024,underruns:0};
      }
      if(command==='reload_window')return null;
      throw Error(`Unexpected native command: ${command}`);
    }};
  },{backend,nativeCredits});
  await page.addInitScript({content:desktop});
  const check=label=>{checks.push(label);console.log(`CHECK ${name}: ${label}`);};
  const state=kind=>page.evaluate(kind=>window.desktopAudit.read(kind),kind);
  const wait=async(predicate,kind)=>{
    // Startup creates the worklet only after fetching/compiling WASM. Wait for
    // that one absence explicitly; read errors after creation must still fail.
    await page.waitForFunction(kind=>desktopAudit.worklets.some(entry=>entry.name===(kind==='preview'?'tetorica-sid-player':'tetorica-sid-synth')&&entry.node.context.state!=='closed'),kind);
    let value;for(let i=0;i<120;i++){value=await state(kind);if(predicate(value))return value;await page.waitForTimeout(25);}throw Error('State did not settle: '+JSON.stringify(value));
  };
  const menu=async()=>{if(!await page.locator('#synthMenu').evaluate(node=>node.open))await page.click('#synthMenuButton');};
  const target=async value=>{await page.locator(`[data-sid-live-voice="${value}"]`).click();await wait(v=>v.channelSettings.target===value);};
  const keyboard=async()=>{await page.keyboard.down('a');await wait(v=>v.voices.length===1);await page.waitForFunction(async()=>await window.desktopAudit.webPeak()>.00001);await page.keyboard.up('a');await wait(v=>v.voices.length===0);};
  const output=async value=>{await menu();if(!await page.locator('#desktop-audio-output').evaluate(n=>n.open))await page.locator('#desktop-audio-output > summary').click();await page.click('#desktop-audio-'+value);await page.waitForFunction(value=>{
    const mode=document.querySelector('#desktop-audio-mode'),status=document.querySelector('#desktop-audio-status').textContent;
    return mode.value===value&&!mode.disabled&&(value==='native'?status.startsWith('Native →'):status==='Web Audio output');
  },value);};
  const save=async id=>{const before=await page.evaluate(()=>desktopAudit.saves.length);await menu();await page.click('#'+id);await page.waitForFunction(n=>desktopAudit.saves.length===n+1,before);return JSON.parse(await page.evaluate(()=>desktopAudit.saves.at(-1).text));};
  const load=async preset=>{await menu();const chooser=page.waitForEvent('filechooser');await page.click('#loadPreset');await(await chooser).setFiles({name:'sid-setup.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(preset))});await page.waitForFunction(()=>document.querySelector('#patchStatus').dataset.busy!=='true'&&document.querySelector('#audioStatus').textContent.startsWith('SID channel setup loaded'));};
  const previewState=()=>state('preview');
  try{
    check('SID desktop toolbar, Pin, lazy editable Web sources');
    await page.goto(backend+'/index.html');await page.waitForFunction(()=>window.tetoricaSynthAudio&&document.querySelector('#synthPinButton')?.hidden===false&&document.querySelector('#desktop-audio-native'));
    assert.equal(await page.title(),'Tetorica SID Synth');assert.equal(await page.evaluate(()=>desktopAudit.contexts.length),0);
    assert.equal(await page.locator('#saveChannelSettings').textContent(),'All channels · SID setup…');
    await page.click('#synthPinButton');await page.waitForFunction(()=>document.querySelector('#synthPinButton').getAttribute('aria-pressed')==='true');
    await page.click('#synthPinButton');await page.waitForFunction(()=>document.querySelector('#synthPinButton').getAttribute('aria-pressed')==='false');
    await page.click('#startAudio');await wait(v=>v.model==='6581');await keyboard();
    check('both actual SID WASM models, combined waveform and independent channel banks');
    const voice=await save('savePreset');assert.equal(voice.format,'tetorica-sid-voice');assert.equal(voice.version,2);
    await page.uncheck('#sidLiveEnabled');
    for(const model of ['8580','6581']){await page.locator(`[data-choice-for="sidModel"][data-value="${model}"]`).click();await wait(v=>v.model===model);await keyboard();}
    await target(0);await page.locator('[data-choice-for="waveform"][data-value="triangle"]').click();
    await wait(v=>v.channelSettings.channels[0].voice.waveform==='triangle+saw');
    await target(1);await wait(v=>v.preset.voice.waveform==='saw');await target('round-robin');
    let setup=await save('saveChannelSettings');assert.equal(setup.version,2);assert.equal(setup.channels[0].voice.waveform,'triangle+saw');assert.equal(setup.channels[1].voice.waveform,'saw');
    for(const key of ['a','s','d'])await page.keyboard.down(key);let current=await wait(v=>v.voices.length===3);assert.deepEqual(current.voices.map(v=>v.channel).sort(),[0,1,2]);
    for(const key of ['a','s','d'])await page.keyboard.up(key);await wait(v=>!v.voices.length);
    check('fixed-channel Legato returns to a held key; setup saves keyboard mode');
    await target(1);await page.locator('[data-sid-keyboard-mode="legato"]').click();await wait(v=>v.channelSettings.keyboardMode==='legato');
    await page.keyboard.down('a');current=await wait(v=>v.voices.length===1);const held=current.voices[0];
    await page.keyboard.down('s');await wait(v=>v.voices.length===2&&v.voices.every(n=>n.channel===1));await page.keyboard.up('s');
    current=await wait(v=>v.voices.length===1);assert.equal(current.voices[0].id,held.id);assert(current.registers[11]&1);await page.keyboard.up('a');await wait(v=>!v.voices.length);
    setup=await save('saveChannelSettings');assert.equal(setup.keyboardMode,'legato');assert.equal(setup.target,1);
    await target(2);await load(setup);await wait(v=>v.channelSettings.target===1&&v.channelSettings.keyboardMode==='legato');
    check('native final PCM tap, monitors retained, explicit output switch stops keys and Pitch');
    await page.keyboard.down('a');await wait(v=>v.voices.length===1);await page.locator('#pitchBend').evaluate(n=>{n.value='.5';n.dispatchEvent(new Event('input',{bubbles:true}));});await wait(v=>v.pitch===.5);
    await output('native');await wait(v=>!v.voices.length&&v.pitch===0);await page.keyboard.up('a');
    assert.equal(await page.evaluate(()=>desktopAudit.speakerEdges.has(tetoricaSynthAudio.getOutput().output)),false);
    await page.keyboard.down('a');await wait(v=>v.voices.length===1);await page.waitForFunction(()=>desktopAudit.nativePeak>.00001&&desktopAudit.packets>0);await page.keyboard.up('a');await wait(v=>!v.voices.length);
    assert.equal(await page.evaluate(()=>desktopAudit.nativeFinite),true);
    check('native SID song preview follows its separate context; Live inactive fields, Pause and Resume');
    const {createSidPairFixture}=await import('../tests/helpers/sid-fixture.mjs');const fixture=createSidPairFixture({sync:false,ring:false,waveform:'triangle',filterModeMask:0});
    await menu();const chooser=page.waitForEvent('filechooser');await page.click('#synthMenuSid');await(await chooser).setFiles({name:'desktop.sid',mimeType:'application/octet-stream',buffer:Buffer.from(fixture.bytes)});
    await page.waitForFunction(()=>!document.querySelector('#sidImportPlay').disabled);await page.check('#sidLiveEnabled');
    const startsBefore=await page.evaluate(()=>desktopAudit.calls.filter(v=>v.command==='audio_start').length);
    await page.click('#sidImportPlay');await wait(v=>v.playing,'preview');
    await page.waitForFunction(()=>document.querySelector('#voiceEditor').dataset.observing==='true');
    assert.equal(await page.evaluate(()=>desktopAudit.calls.filter(v=>v.command==='audio_start').length),startsBefore+1);
    assert.equal(await page.evaluate(()=>desktopAudit.speakerEdges.has(tetoricaSynthAudio.getOutput().output)),false);
    assert.equal(await page.locator('#pulseWidth').isDisabled(),true);assert.equal(await page.locator('#modulationRatio').isDisabled(),true);
    await page.click('#sidImportPause');await wait(v=>v.paused&&!v.playing,'preview');assert.match(await page.locator('#sidImportPause').textContent(),/Resume/);
    const frozen=await previewState();await page.waitForTimeout(100);const still=await previewState();assert.equal(still.cycles,frozen.cycles);
    await page.click('#sidImportPause');await wait(v=>v.playing&&!v.paused,'preview');
    await page.click('#sidImportStop');await page.waitForFunction(()=>document.querySelector('#sidImportPlay').disabled===false);
    assert.equal(await page.locator('#desktop-audio-native').getAttribute('aria-pressed'),'true');
    check('song Stop and keyboard handoff keep Native selected without duplicate speaker routes');
    await page.keyboard.down('a');await wait(v=>v.voices.length===1);await page.waitForFunction(()=>document.querySelector('#desktop-audio-status').textContent.startsWith('Native →'));
    assert.equal(await page.evaluate(()=>desktopAudit.speakerEdges.has(tetoricaSynthAudio.getOutput().output)),false);await page.keyboard.up('a');await wait(v=>!v.voices.length);
    await page.click('#sidImportPlay');await wait(v=>v.playing,'preview');await page.keyboard.down('a');await wait(v=>v.voices.length===1);
    assert.equal(await page.locator('#sidImportStop').isDisabled(),true);await page.keyboard.up('a');await wait(v=>!v.voices.length);
    check('Stop during delayed native preview setup disposes its stale session before playback');
    await page.evaluate(()=>{desktopAudit.holdStart=true;});await page.click('#sidImportPlay');await page.waitForFunction(()=>typeof desktopAudit.releaseStart==='function');
    await page.click('#sidImportStop');await page.evaluate(()=>desktopAudit.releaseStart());await page.waitForFunction(()=>!document.querySelector('#sidImportPlay').disabled);
    await page.keyboard.down('a');await wait(v=>v.voices.length===1);await page.keyboard.up('a');await wait(v=>!v.voices.length);
    check('native failure falls back safely and preserves editable patches; Web output restores');
    await page.evaluate(()=>{desktopAudit.failWrites=true;});await page.keyboard.down('a');
    await page.waitForFunction(()=>document.querySelector('#desktop-audio-status').textContent.includes('Injected offline device failure'));
    await wait(v=>!v.voices.length);await page.keyboard.up('a');assert.equal(await page.locator('#desktop-audio-web').getAttribute('aria-pressed'),'true');
    await page.uncheck('#sidLiveEnabled');await keyboard();await load(setup);current=await wait(v=>v.channelSettings.keyboardMode==='legato'&&v.channelSettings.target===1);assert.deepEqual(current.channelSettings,setup);
    await output('web');await keyboard();
    check('native save cancellation and narrow window remain usable');
    await page.evaluate(()=>{desktopAudit.cancelSave=true;});await save('savePreset');await page.waitForFunction(()=>document.querySelector('#audioStatus').textContent==='Save cancelled.');
    if(options.screenshots)await page.screenshot({path:path.join(options.screenshots,`desktop-${name}.png`),fullPage:true});
    await page.setViewportSize({width:390,height:900});await page.waitForTimeout(120);const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth);assert(overflow<=1,`Narrow desktop overflow: ${overflow}`);
    if(options.screenshots)await page.screenshot({path:path.join(options.screenshots,`desktop-${name}-narrow.png`),fullPage:true});
    assert.deepEqual(errors,[]);assert.deepEqual(missing,[]);assert.deepEqual(consoleErrors,[]);
    const measurements=await page.evaluate(()=>({nativePackets:desktopAudit.packets,nativePeak:desktopAudit.nativePeak,nativeFinite:desktopAudit.nativeFinite,audioContexts:desktopAudit.contexts.length}));
    return {engine:name,checks,passed:true,mobileOverflow:overflow,nativeCredits,nativePrefillPackets,...measurements,nativeHost:'mocked Tauri IPC; no CPAL device',physicalOutput:'muted'};
  }catch(error){console.error(JSON.stringify({engine:name,audioStatus:await page.locator('#audioStatus').textContent().catch(()=>null),diagnostics:await page.evaluate(()=>({activeElement:document.activeElement?.outerHTML,outputMode:document.querySelector('#desktop-audio-mode')?.value,outputBusy:document.querySelector('#desktop-audio-mode')?.disabled,outputStatus:document.querySelector('#desktop-audio-status')?.textContent,activeKeys:[...document.querySelectorAll('#keyboard .is-active')].map(node=>node.dataset.key)})).catch(()=>null),errors,missing,consoleErrors}));if(options.screenshots)await page.screenshot({path:path.join(options.screenshots,`desktop-${name}-failure.png`),fullPage:true}).catch(()=>{});throw error;}
  finally{await browser.close();}
}
(async()=>{
  if(options.screenshots)await fs.mkdir(options.screenshots,{recursive:true});
  const server=http.createServer(async(request,response)=>{
    try {
      const name=decodeURIComponent(new URL(request.url,'http://localhost').pathname);
      const file=name==='/desktop-audio-worklet.js'?path.join(root,'desktop/audio-worklet.js'):path.resolve(root,'dist','.'+name);
      assert(file.startsWith(path.join(root,'dist')+path.sep)||file===path.join(root,'desktop/audio-worklet.js'));
      const bytes=await fs.readFile(file);response.writeHead(200,{'content-type':mime[path.extname(file)]||'application/octet-stream','access-control-allow-origin':'*'});response.end(bytes);
    } catch(error){response.writeHead(404,{'access-control-allow-origin':'*'});response.end('Missing test asset');}
  });
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
  try {
    const backend=`http://tauri.localhost:${server.address().port}`;
    const rows=[];for(const [name,engine] of [['chromium',chromium],['webkit',webkit]])rows.push(await run(name,engine,backend));
    await fs.mkdir(path.dirname(options.out),{recursive:true});await fs.writeFile(options.out,JSON.stringify({passed:true,rows},null,2)+'\n');
    console.log(`Desktop browser check passed: ${options.out}`);
  } finally {await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});
