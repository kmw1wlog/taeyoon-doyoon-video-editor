const $ = (id) => document.getElementById(id);
const state = { clips: [], mutes: [], speech: [], speaker: '태윤', profiles: { 태윤: {}, 도윤: {} }, time: 0, playing: false };
const video = $('video');
const ttsAudio = new Audio();
let activeClip = null;
let raf = null;
const px = 80;
const fmt = (seconds) => `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(Math.floor(seconds % 60)).padStart(2, '0')}.${Math.floor(seconds % 1 * 10)}`;
const total = () => state.clips.reduce((sum, clip) => sum + clip.duration, 0);
const safe = (value) => String(value).replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const status = (message, error = false) => { $('status').textContent = message; $('status').classList.toggle('error', error); };
async function api(path, payload, raw = false) {
  const response = await fetch(path, { method: 'POST', headers: raw ? {} : { 'Content-Type': 'application/json' }, body: raw ? payload : JSON.stringify(payload) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || '요청 실패');
  return result;
}
function locate(time) {
  let offset = 0;
  for (const clip of state.clips) {
    if (time < offset + clip.duration || clip === state.clips.at(-1)) return { clip, local: Math.max(0, time - offset), offset };
    offset += clip.duration;
  }
  return null;
}
function syncMedia() {
  const found = locate(state.time);
  if (!found) { video.removeAttribute('src'); video.load(); activeClip = null; return; }
  if (activeClip !== found.clip.id) { video.src = found.clip.url; activeClip = found.clip.id; }
  if (Math.abs(video.currentTime - found.local) > 0.25) video.currentTime = Math.min(found.local, found.clip.duration - 0.03);
  video.muted = $('muteToggle').dataset.muted === 'true' || state.mutes.some(m => state.time >= m.start && state.time < m.end);
  const currentSpeech = state.speech.find(s => state.time >= s.start && state.time < s.start + s.duration);
  if (currentSpeech) {
    if (ttsAudio.dataset.id !== currentSpeech.id) { ttsAudio.src = currentSpeech.url; ttsAudio.dataset.id = currentSpeech.id; }
    const local = state.time - currentSpeech.start;
    if (Math.abs(ttsAudio.currentTime - local) > 0.25) ttsAudio.currentTime = local;
    if (state.playing && ttsAudio.paused) ttsAudio.play().catch(() => {});
  } else { ttsAudio.pause(); ttsAudio.dataset.id = ''; }
  if (state.playing) video.play().catch(() => {});
  $('timeLabel').textContent = `${fmt(state.time)} / ${fmt(total())}`;
  $('seek').max = total() || 1;
  $('seek').value = state.time;
  $('playhead').style.left = `${120 + state.time * px}px`;
}
function tick() {
  if (!state.playing) return;
  const found = locate(state.time);
  if (found && Number.isFinite(video.currentTime)) state.time = Math.min(total(), found.offset + video.currentTime);
  if (state.time >= total() - 0.04) { pause(); state.time = total(); }
  syncMedia();
  raf = requestAnimationFrame(tick);
}
function play() { if (!state.clips.length) return; if (state.time >= total()) state.time = 0; state.playing = true; $('playButton').textContent = 'Ⅱ'; syncMedia(); raf = requestAnimationFrame(tick); }
function pause() { state.playing = false; cancelAnimationFrame(raf); video.pause(); ttsAudio.pause(); $('playButton').textContent = '▶'; }
function seek(time) { state.time = Math.min(total(), Math.max(0, time)); syncMedia(); }
function draw() {
  const duration = total();
  $('mediaCount').textContent = state.clips.length;
  $('projectLength').textContent = `전체 ${fmt(duration)}`;
  $('emptyPreview').parentElement.classList.toggle('has-video', state.clips.length > 0);
  $('mediaList').innerHTML = state.clips.map((clip, index) => `<div class="media-card" draggable="true" data-index="${index}"><video class="thumb" src="${clip.url}#t=0.1" muted preload="metadata"></video><div><strong title="${safe(clip.name)}">${safe(clip.name)}</strong><small>${fmt(clip.duration)}</small></div><button data-remove="${index}" title="제거">×</button></div>`).join('');
  $('refClip').innerHTML = state.clips.map(clip => `<option value="${clip.id}">${safe(clip.name)}</option>`).join('');
  loadProfile();
  const width = Math.max(700, Math.ceil(duration * px));
  for (const name of ['ruler','videoTrack','audioTrack','ttsTrack']) $(name).style.width = `${width}px`;
  $('ruler').innerHTML = Array.from({length: Math.ceil(width / px) + 1}, (_, i) => `<span class="ruler-mark" style="left:${i * px}px">${fmt(i)}</span>`).join('');
  let left = 0;
  $('videoTrack').innerHTML = state.clips.length ? state.clips.map((clip, i) => { const html = `<div class="clip-block" draggable="true" data-index="${i}" style="left:${left * px}px;width:${clip.duration * px}px">${safe(clip.name)}<small>${fmt(clip.duration)}</small><button data-clip-remove="${i}" title="제거">×</button></div>`; left += clip.duration; return html; }).join('') : '<div class="track-empty">소스 영상을 드래그하거나 가져오세요</div>';
  $('audioTrack').innerHTML = state.mutes.map((m, i) => `<div class="mute-block" style="left:${m.start*px}px;width:${(m.end-m.start)*px}px" title="${fmt(m.start)}–${fmt(m.end)}">음소거<button data-mute-remove="${i}">×</button></div>`).join('');
  $('ttsTrack').innerHTML = state.speech.map((s, i) => `<div class="tts-block" style="left:${s.start*px}px;width:${Math.min(s.duration,total()-s.start)*px}px" title="${safe(s.text)}">${safe(s.speaker)} · ${safe(s.text)}<small>${fmt(s.duration)}</small><button data-speech-remove="${i}">×</button></div>`).join('');
  syncMedia();
}
async function importFiles(files) {
  for (const file of files) {
    if (!file.type.startsWith('video/')) continue;
    status(`${file.name} 가져오는 중…`);
    try {
      const result = await api('/api/upload', file, true);
      state.clips.push({ ...result, name: file.name });
      draw();
    } catch (error) { status(`${file.name}: ${error.message}`, true); }
  }
  status(`${state.clips.length}개 영상이 타임라인에 배치되었습니다.`);
}
function saveProfile() {
  const p = state.profiles[state.speaker];
  p.refId = $('refClip').value;
  p.refStart = $('refStart').value;
  p.refEnd = $('refEnd').value;
  p.refText = $('refText').value;
}
function loadProfile() {
  const p = state.profiles[state.speaker];
  $('refClip').value = p.refId || state.clips[0]?.id || '';
  $('refStart').value = p.refStart ?? 0;
  $('refEnd').value = p.refEnd ?? 5;
  $('refText').value = p.refText || '';
}
$('videoFiles').onchange = (event) => importFiles(event.target.files);
for (const target of [$('dropzone'), $('videoTrack')]) {
  target.ondragover = (event) => { event.preventDefault(); target.classList.add('over'); };
  target.ondragleave = () => target.classList.remove('over');
  target.ondrop = (event) => { event.preventDefault(); target.classList.remove('over'); if (event.dataTransfer.files.length) importFiles(event.dataTransfer.files); else if (event.dataTransfer.getData('text/plain')) { const from = Number(event.dataTransfer.getData('text/plain')); const to = Math.min(state.clips.length - 1, Math.max(0, Math.floor((event.offsetX / px)))); const moved = state.clips.splice(from, 1)[0]; if (moved) { state.clips.splice(to, 0, moved); pause(); seek(0); draw(); } } };
}
document.addEventListener('dragstart', event => { const card = event.target.closest('[data-index]'); if (card) event.dataTransfer.setData('text/plain', card.dataset.index); });
document.addEventListener('click', event => {
  const button = event.target.closest('button');
  if (!button) return;
  const key = [['remove','clips'],['clipRemove','clips'],['muteRemove','mutes'],['speechRemove','speech']].find(([name]) => button.dataset[name] !== undefined);
  if (key) { const index = Number(button.dataset[key[0]]); state[key[1]].splice(index, 1); pause(); seek(Math.min(state.time, total())); draw(); }
});
document.querySelectorAll('[data-speaker]').forEach(button => button.onclick = () => { saveProfile(); state.speaker = button.dataset.speaker; document.querySelectorAll('[data-speaker]').forEach(b => b.classList.toggle('selected', b === button)); loadProfile(); });
['refClip','refStart','refEnd','refText'].forEach(id => $(id).addEventListener('change', saveProfile));
$('speechMode').onchange = () => $('replaceEndLabel').classList.toggle('hidden', $('speechMode').value !== 'replace');
$('playButton').onclick = () => state.playing ? pause() : play();
$('seek').oninput = () => seek(Number($('seek').value));
$('muteToggle').onclick = () => { $('muteToggle').dataset.muted = $('muteToggle').dataset.muted === 'true' ? 'false' : 'true'; $('muteToggle').textContent = $('muteToggle').dataset.muted === 'true' ? '♪̸' : '♫'; syncMedia(); };
document.querySelectorAll('.track-content').forEach(track => track.onclick = (event) => { if (event.target === track) seek(event.offsetX / px); });
$('addMute').onclick = () => { const start = Number($('muteStart').value), end = Number($('muteEnd').value); if (!state.clips.length || start < 0 || end <= start || end > total()) return status('영상 범위 안에서 올바른 시작·끝 위치를 입력하세요.', true); state.mutes.push({start,end}); draw(); status(`${fmt(start)}–${fmt(end)} 원본 음성을 제거했습니다.`); };
$('generateButton').onclick = async () => {
  saveProfile();
  const p = state.profiles[state.speaker], text = $('speechText').value.trim(), start = Number($('speechStart').value), mode = $('speechMode').value, end = Number($('replaceEnd').value);
  if (!state.clips.length || !text || start < 0 || start >= total()) return status('영상과 대사, 올바른 삽입 위치를 입력하세요.', true);
  if (mode === 'replace' && (end <= start || end > total())) return status('교체 끝 위치가 올바르지 않습니다.', true);
  if (!p.refText?.trim()) return status(`${state.speaker} 참조 음성의 실제 대본을 입력하세요.`, true);
  $('generateButton').disabled = true;
  status(`${state.speaker} 목소리로 음성을 생성하는 중입니다. 잠시 기다려 주세요…`);
  try {
    const result = await api('/api/tts', { text, refId:p.refId, refStart:Number(p.refStart), refEnd:Number(p.refEnd), refText:p.refText });
    if (mode === 'replace') state.mutes.push({start,end});
    state.speech.push({ ...result, speaker:state.speaker, text, start });
    draw();
    status(`${state.speaker} 음성을 ${fmt(start)}에 넣었습니다.`);
  } catch (error) { status(`음성 생성 실패: ${error.message}`, true); }
  finally { $('generateButton').disabled = false; }
};
$('exportButton').onclick = async () => {
  if (!state.clips.length) return status('영상을 먼저 추가하세요.', true);
  $('exportButton').disabled = true;
  status('최종 MP4를 만드는 중입니다…');
  try {
    const result = await api('/api/export', { clips:state.clips.map(({id,duration}) => ({id,duration})), mutes:state.mutes, speech:state.speech.map(({id,start}) => ({id,start})) });
    const link = document.createElement('a'); link.href = result.url; link.download = 'taeyoon-doyoon-edited.mp4'; link.click(); status('최종 MP4가 준비되었습니다.');
  } catch (error) { status(`내보내기 실패: ${error.message}`, true); }
  finally { $('exportButton').disabled = false; }
};
$('saveProject').onclick = () => { saveProfile(); const blob = new Blob([JSON.stringify({clips:state.clips,mutes:state.mutes,speech:state.speech,profiles:state.profiles}, null, 2)], {type:'application/json'}); const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = 'taeyoon-doyoon-project.json'; link.click(); setTimeout(() => URL.revokeObjectURL(link.href), 1000); };
$('projectFile').onchange = async (event) => { try { const data = JSON.parse(await event.target.files[0].text()); if (!Array.isArray(data.clips) || !Array.isArray(data.mutes) || !Array.isArray(data.speech)) throw Error('프로젝트 형식이 올바르지 않습니다'); Object.assign(state, {clips:data.clips,mutes:data.mutes,speech:data.speech,profiles:data.profiles || {태윤:{},도윤:{}}}); pause(); seek(0); draw(); status('프로젝트를 열었습니다. 저장 당시의 로컬 미디어 파일이 필요합니다.'); } catch(error) { status(error.message,true); } };
draw();
