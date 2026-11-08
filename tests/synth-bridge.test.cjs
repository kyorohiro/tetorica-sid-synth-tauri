const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../desktop/synth-bridge.js'),'utf8');
function boot({url='tauri://localhost/index.html',subframe=false,bridge=true,native=true}={}){
  const events=[],errors=[],window={dispatchEvent:event=>events.push(event.type)};
  window.top=subframe?{}:window;
  if(native)window.__TAURI_INTERNALS__={};
  if(bridge)window.tetoricaSynthAudio={setOutputHandler(){}};
  vm.runInNewContext(source,{window,location:new URL(url),Event:class{constructor(type){this.type=type;}},console:{error:message=>errors.push(message)}});
  return {events,errors};
}
test('desktop adapter announces only the existing guarded Web bridge on local top-level Tauri pages',()=>{
  for(const url of ['tauri://localhost/','http://tauri.localhost/','https://tauri.localhost/'])assert.deepEqual(boot({url}),{events:['tetorica-synth-ready'],errors:[]});
  for(const options of [{url:'https://example.com/'},{url:'http://localhost/'},{subframe:true},{native:false}])assert.deepEqual(boot(options),{events:[],errors:[]});
});
test('an incompatible imported Web app is reported without installing or faking an audio bridge',()=>{
  const result=boot({bridge:false});assert.deepEqual(result.events,[]);assert.match(result.errors[0],/does not provide/);
});
