// 근무표 화면 브라우저 동작 확인(개발 PC 전용, CI 밖). roster.js·me.html 끝 스크립트는 서버 테스트가 못 보니 화면 PR 때 손으로 돌린다.
// 빈 임시 DATA_DIR 에 가짜 데이터(help_videos/seed.py)로 서버를 띄우고 headless Chrome(CDP)으로 눌러 본 뒤 모두 정리한다.
//   node tools/browser_check.mjs [파이썬 경로, 기본 .venv/bin/python]    (실패하면 종료 코드 1)
import {spawn, execFileSync} from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const PY = process.argv[2] ? path.resolve(process.argv[2]) : path.join(ROOT, '.venv/bin/python');
const sleep = ms => new Promise(r => setTimeout(r, ms));
const WORK = fs.mkdtempSync(path.join(os.tmpdir(), 'duty-check-'));
const env = {...process.env, DUTY_ENV_FILE: '', DUTY_DEBUG: '1', DUTY_DATA_DIR: path.join(WORK, 'data')};
const PORT = 8800 + Math.floor(Math.random() * 100);  // 8000·8765(개발·운영 서버)는 쓰지 않는다
const BASE = `http://127.0.0.1:${PORT}`;
// 남의 근무표(ops): member 의 내 근무표가 아닌 근무표 하나
const EXTRA = `
from datetime import time
from duty.models import Board, BoardShift, Department
b = Board.objects.create(code="ops", name="운영팀")
BoardShift.objects.create(board=b, key="normal", name="가운데", start=time(9), end=time(18))
Department.objects.create(code="OPS", name="운영", shifts="normal", board=b)
`;
// POST /prefs/ 본문을 기록한다(roster.js 의 save 는 fetch 를 쓴다)
const SPY = `
window.__posts = [];
const f0 = window.fetch;
window.fetch = (u, o) => { if (o && o.method === 'POST' && String(u).includes('/prefs/')) window.__posts.push([...o.body]); return f0(u, o); };`;

let server, chrome, failed = 0;
const ok = (cond, msg) => { console.log(`${cond ? '통과' : '실패'}: ${msg}`); if (!cond) failed++; };

async function browser() {
  const port = 9400 + Math.floor(Math.random() * 400);
  chrome = spawn('google-chrome', ['--headless=new', '--no-sandbox', '--window-size=1400,900', `--remote-debugging-port=${port}`,
    `--user-data-dir=${path.join(WORK, 'prof')}`, 'about:blank'], {stdio: 'ignore', env: {...process.env, TMPDIR: WORK}});  // Chrome 임시 파일도 WORK 안에(끝나면 같이 지운다)
  let tabs;
  for (let i = 0; i < 50 && !tabs; i++) { try { tabs = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); } catch { await sleep(200); } }
  if (!tabs) throw new Error('Chrome 을 띄우지 못했습니다(google-chrome 설치·TMPDIR 경로 길이 확인)');
  const ws = new WebSocket(tabs.find(t => t.type === 'page').webSocketDebuggerUrl);
  await new Promise(r => ws.onopen = r);
  let id = 0; const pend = {};
  const send = (method, params = {}) => new Promise(r => { const i = ++id; pend[i] = r; ws.send(JSON.stringify({id: i, method, params})); });
  ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pend[m.id]) pend[m.id](m); };
  const ev = async x => {
    const r = (await send('Runtime.evaluate', {expression: x, returnByValue: true, awaitPromise: true})).result;
    if (r.exceptionDetails) throw new Error(`${r.exceptionDetails.exception?.description || r.exceptionDetails.text} (주소 ${await ev('location.href')})`);
    return r.result?.value;
  };
  await send('Page.enable');
  await send('Page.addScriptToEvaluateOnNewDocument', {source: SPY});
  const go = async (u, settle = 800) => {
    await send('Page.navigate', {url: BASE + u});
    for (let i = 0; i < 50; i++) { await sleep(200); if (await ev(`document.readyState === 'complete' && !!document.body`)) break; }
    await sleep(settle);  // roster.js 가 ◀ ▶ 앞뒤 기간을 미리 받는 시간
  };
  await send('Network.enable');
  const slow = ms => send('Network.emulateNetworkConditions', {offline: false, latency: ms, downloadThroughput: -1, uploadThroughput: -1});
  return {ev, go, slow};
}

async function run() {
  process.chdir(ROOT);
  fs.mkdirSync(env.DUTY_DATA_DIR);
  execFileSync(PY, ['manage.py', 'migrate', '-v0'], {env, stdio: 'inherit'});
  execFileSync(PY, ['manage.py', 'shell'], {env, input: fs.readFileSync('tools/help_videos/seed.py'), stdio: ['pipe', 'ignore', 'inherit']});
  execFileSync(PY, ['manage.py', 'shell'], {env, input: EXTRA, stdio: ['pipe', 'ignore', 'inherit']});
  server = spawn(PY, ['manage.py', 'runserver', `127.0.0.1:${PORT}`, '--noreload'], {env, stdio: 'ignore'});
  for (let i = 0; i < 50; i++) { try { await fetch(BASE + '/login/'); break; } catch { await sleep(200); } }
  const s = await browser();
  await s.go('/login/');
  await s.ev(`document.querySelector('[name=username]').value = 'member'; document.querySelector('[name=password]').value = 'Demo-pass-123';
    document.querySelector('form button').click()`);
  for (let i = 0; i < 50 && (await s.ev('location.pathname').catch(() => '/login/')) === '/login/'; i++) await sleep(200);
  if (await s.ev('location.pathname') === '/login/') throw new Error('member 로그인 실패');
  await sleep(1000);

  // (1) 체크 상자 세 상태: 보임 → 흐리게 → 숨김 → 보임. 표 클래스·주소창·POST /prefs/ 본문, 새로고침 뒤 유지
  const box = `document.querySelector('#flt input[name=shift][value=dinner]')`;
  const look = () => s.ev(`(() => { const secs = [...document.querySelectorAll('#roster-root .sec[data-k=dinner]')], u = new URL(location.href);
    return {n: secs.length, dm: secs.every(e => e.classList.contains('dm')), x: secs.every(e => e.classList.contains('x')),
      anyDm: secs.some(e => e.classList.contains('dm')), anyX: secs.some(e => e.classList.contains('x')),
      st: ${box}.dataset.state, sdim: u.searchParams.getAll('sdim'), shift: u.searchParams.getAll('shift')}; })()`);
  const post = async () => { await sleep(700); return s.ev(`window.__posts.at(-1) || null`); };
  const has = (body, k, v) => !!body && body.some(([a, b]) => a === k && b === v);
  await s.go('/?view=week');
  let v = await look();
  ok(v.n > 0 && v.st === 'on' && !v.anyDm && !v.anyX, `처음엔 석식교대 '보임'(칸 ${v.n}개)`);
  const steps = [
    ['dim', 'dm', p => has(p, 'sdim', 'dinner') && has(p, 'shift', 'dinner') && has(p, 'mine', '1'),
     u => u.sdim.includes('dinner') && u.shift.includes('dinner')],
    ['off', 'x', p => !has(p, 'sdim', 'dinner') && !has(p, 'shift', 'dinner') && has(p, 'shift', 'normal'),
     u => !u.sdim.includes('dinner') && !u.shift.includes('dinner') && u.shift.includes('normal')],
    ['on', null, p => !has(p, 'sdim', 'dinner') && has(p, 'shift', 'dinner'), u => !u.sdim.length],
  ];
  for (const [st, cls, body, url] of steps) {
    await s.ev(`${box}.click()`);
    v = await look();
    const tbl = cls === 'dm' ? v.dm && !v.anyX : cls === 'x' ? v.x && !v.anyDm : !v.anyDm && !v.anyX;
    ok(v.st === st && tbl, `누르면 '${st}' 상태, 표 클래스 ${cls ? '.' + cls : '없음'}`);
    ok(url(v), `'${st}' 주소창 shift=${v.shift.join(',')} sdim=${v.sdim.join(',')}`);
    const p = await post();
    ok(body(p), `'${st}' POST /prefs/ 본문 ${JSON.stringify(p)}`);
    await s.go('/?view=week');  // 주소에 필터 없이 = 저장값
    v = await look();
    ok(v.st === st, `새로고침 뒤 '${st}' 유지(지금 ${v.st})`);
  }

  // (2) [내 근무]를 ?shift= 로 새로 열면 처음부터 거른다
  await s.go('/me/?shift=normal');
  v = await s.ev(`(() => { const ws = [...document.querySelectorAll('ul.mine .w[data-k]')], shown = ws.filter(w => !w.classList.contains('x'));
    return {shown: shown.length, other: shown.filter(w => w.dataset.k !== 'normal').length, hidden: ws.length - shown.length,
      boxes: [...document.querySelectorAll('form.dl input[name=shift]')].filter(c => c.checked).map(c => c.value)}; })()`);
  ok(v.shown > 0 && v.other === 0 && v.hidden > 0 && v.boxes.join() === 'normal',
     `[내 근무] ?shift=normal 처음부터 거름(보임 ${v.shown}, 숨김 ${v.hidden}, 다른 근무 보임 ${v.other}, 체크 ${v.boxes})`);

  // (3) ▶ 연타: 한 번만 넘어가고 history 도 한 번. 느린 망으로 미리 받기가 끝나기 전에 누른다(바꿔 끼우는 중 또 누름)
  await s.slow(1500);
  await s.go('/?view=week', 0);
  const before = await s.ev(`({len: history.length, next: new URL(document.querySelector('a[data-nav=next]').href).searchParams.get('date')})`);
  await s.ev(`(() => { const a = document.querySelector('a[data-nav=next]'); a.click(); a.click(); a.click(); })()`);
  await sleep(6000);
  await s.slow(0);
  v = await s.ev(`({len: history.length, date: new URL(location.href).searchParams.get('date')})`);
  ok(v.date === before.next && v.len === before.len + 1, `▶ 세 번 연타 = 한 주만(기대 ${before.next}, 지금 ${v.date}), history +${v.len - before.len}`);

  // (4) 남의 근무표만 볼 때 변경 내역 체크를 바꿔도 내 흐리게 값 유지
  await s.go('/?view=week');
  await s.ev(`${box}.click()`);  // 내 근무표: 석식교대 흐리게
  await post();
  await s.go('/?view=week&board=ops');
  const hist = `document.querySelector('#flt input[name=hist][type=checkbox]')`;
  ok(await s.ev(`!!${hist} && !document.querySelector('#flt input[name=shift]')`), '남의 근무표만: 변경 내역 체크만 있다');
  await s.ev(`${hist}.click()`);
  const p = await post();
  ok(has(p, 'mine', '0') && has(p, 'hdim', '1'), `남의 근무표 POST /prefs/ mine=0 ${JSON.stringify(p)}`);
  await s.go('/?view=week');
  v = await look();
  ok(v.st === 'dim' && v.dm, `내 근무표로 돌아와도 석식교대 '흐리게' 유지(지금 ${v.st})`);
}

try {
  await run();
} catch (e) {
  console.log('실패: 확인 중 오류 ' + (e.stack || e));
  failed++;
} finally {
  chrome?.kill(); server?.kill();
  await sleep(500);
  fs.rmSync(WORK, {recursive: true, force: true});
}
console.log(failed ? `실패 ${failed}건` : '모두 통과');
process.exit(failed ? 1 : 0);
