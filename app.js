const $ = (s) => document.querySelector(s);
const fileInput = $('#files'), fileList = $('#file-list'), mergeBtn = $('#merge'), clearBtn = $('#clear');
let files = [], pyodide = null, coreReady = false;
const status = (message, kind='') => { $('#status').textContent = message; $('#status').className = `status ${kind}`; };
const sizeText = n => n < 1024 ? `${n} B` : n < 1024*1024 ? `${(n/1024).toFixed(1)} KB` : `${(n/1024/1024).toFixed(2)} MB`;
function render(){
  $('#count').textContent = `${files.length}개 선택`;
  fileList.innerHTML = '';
  if(!files.length){ fileList.innerHTML='<li class="empty">아직 추가된 파일이 없습니다.</li>'; }
  files.forEach((f,i)=>{ const li=document.createElement('li'); const name=document.createElement('span'); name.textContent=f.name; const meta=document.createElement('small'); meta.textContent=sizeText(f.size); const remove=document.createElement('button'); remove.textContent='×'; remove.title='제거'; remove.className='remove'; remove.style.cssText='border:0;background:none;color:#9a5260;font-size:18px;cursor:pointer'; remove.onclick=()=>{files.splice(i,1);render()}; li.append(name,meta,remove);fileList.append(li); });
  mergeBtn.disabled = files.length < 2; clearBtn.disabled = files.length===0;
}
function addFiles(list){ for(const f of list){ if(!f.name.toLowerCase().endsWith('.ent')) continue; if(!files.some(x=>x.name===f.name && x.size===f.size && x.lastModified===f.lastModified)) files.push(f); } render(); }
fileInput.addEventListener('change',e=>{addFiles(e.target.files);fileInput.value='';});
clearBtn.onclick=()=>{files=[];render();status('ENT 파일을 2개 이상 추가해 주세요.');$('#summary').hidden=true;};
const dz=$('#dropzone');
for(const ev of ['dragenter','dragover']) dz.addEventListener(ev,e=>{e.preventDefault();dz.style.borderColor='#666de8'});
for(const ev of ['dragleave','drop']) dz.addEventListener(ev,e=>{e.preventDefault();dz.style.borderColor='';});
dz.addEventListener('drop',e=>addFiles(e.dataTransfer.files));
async function loadPython(){
  if(pyodide) return pyodide;
  status('병합 엔진을 처음으로 불러오는 중...');
  pyodide = await loadPyodide();
  const response = await fetch('./merge_core.py');
  if(!response.ok) throw new Error('merge_core.py 파일을 불러오지 못했습니다.');
  await pyodide.runPythonAsync(await response.text());
  coreReady=true; return pyodide;
}
function toBase64(buffer){let binary='';const bytes=new Uint8Array(buffer);const chunk=0x8000;for(let i=0;i<bytes.length;i+=chunk)binary+=String.fromCharCode(...bytes.subarray(i,i+chunk));return btoa(binary);}
function downloadBase64(base64,name){const raw=atob(base64);const bytes=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);const blob=new Blob([bytes],{type:'application/gzip'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1500);}
mergeBtn.onclick=async()=>{
  if(files.length<2)return;
  mergeBtn.disabled=true;$('#summary').hidden=true;
  try{
    const py=await loadPython(); status('파일을 읽고 병합하는 중...');
    const items=[];
    for(const f of files) items.push([f.name,toBase64(await f.arrayBuffer())]);
    py.globals.set('browser_items',py.toPy(items));
    const mode=document.querySelector('input[name="mode"]:checked').value;
    py.globals.set('browser_mode',mode);
    const result=await py.runPythonAsync('merge_browser(browser_items, browser_mode)');
    const tuple=result.toJs(); result.destroy();
    const [encoded,objects,scenes,assets]=tuple;
    const outputName=(files[0].name.replace(/\.ent$/i,'')||'Entry작품')+'_합본.ent';
    downloadBase64(encoded,outputName);
    $('#summary').innerHTML=`병합 완료<br>오브젝트 ${objects}개 · 장면 ${scenes}개 · 에셋 ${assets}개`;
    $('#summary').hidden=false;status('완료! 병합된 ENT 파일을 저장했습니다.','success');
  }catch(err){console.error(err);status(`병합 실패: ${err.message||err}`,'error');}
  finally{mergeBtn.disabled=files.length<2;}
};
render();
