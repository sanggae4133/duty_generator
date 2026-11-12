// 사용법 영상 녹화(개발 PC 전용, 운영 서버에는 필요 없음). 가짜 데이터(seed.py)로 띄운 서버를 Chrome 으로 조작하며
// 자막을 얹어 화면을 찍고 ffmpeg 로 duty/help_videos/<이름>.mp4 를 만든다. 순서와 방법은 docs/DEVELOPMENT.md "사용법 영상 다시 만들기".
//   node tools/help_videos/record.mjs <서버 주소> <작업 폴더> <ffmpeg 경로> [member manager admin]
import {spawn, execFileSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const [BASE, WORK, FFMPEG, ...only] = process.argv.slice(2);
const OUT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '../../duty/help_videos');
const PW = 'Demo-pass-123';
const sleep = ms => new Promise(r => setTimeout(r, ms));

// 화면 위 자막과 누르는 곳 표시. popover(top layer)라 근무 변경 팝업 위에도 보인다
const OVERLAY = `
window.confirm = () => true;
document.addEventListener('DOMContentLoaded', () => {
  const cap = document.createElement('div');
  cap.popover = 'manual';
  cap.style.cssText = 'inset:auto 12px 18px 12px;margin:0;border:0;background:rgba(43,27,64,.94);color:#fff;font:600 17px/1.5 "Noto Sans KR",sans-serif;padding:12px 16px;border-radius:12px;box-shadow:0 4px 18px rgba(0,0,0,.35);white-space:pre-line';
  const dot = document.createElement('div');
  dot.popover = 'manual';
  dot.style.cssText = 'inset:auto;margin:0;padding:0;width:46px;height:46px;border-radius:50%;background:rgba(229,0,56,.3);border:3px solid #e50038;transition:transform .25s';
  document.body.append(cap, dot);
  const top = el => { try { el.hidePopover(); } catch {} el.showPopover(); };
  window.__cap = t => { sessionStorage.setItem('__cap', t); cap.textContent = t; t ? top(cap) : cap.hidePopover(); };
  window.__tap = (x, y) => { dot.style.left = (x - 23) + 'px'; dot.style.top = (y - 23) + 'px'; dot.style.transform = 'scale(.5)';
    top(dot); requestAnimationFrame(() => dot.style.transform = 'scale(1)'); setTimeout(() => dot.hidePopover(), 650); };
  window.__cap(sessionStorage.getItem('__cap') || '');
});`;

async function session(name, width, height, scale) {
  const port = 9400 + Math.floor(Math.random() * 400);
  const prof = path.join(WORK, `prof-${name}`);
  const chrome = spawn('google-chrome', ['--headless=new', '--no-sandbox', '--hide-scrollbars', `--force-device-scale-factor=${scale}`,
    `--window-size=${width},${height}`, `--remote-debugging-port=${port}`,  // 배율은 시작 옵션으로 줘야 화면 캡처가 선명하다
    `--user-data-dir=${prof}`, 'about:blank'], {stdio: 'ignore'});
  let tabs;
  for (let i = 0; i < 50 && !tabs; i++) { try { tabs = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); } catch { await sleep(200); } }
  const ws = new WebSocket(tabs.find(t => t.type === 'page').webSocketDebuggerUrl);
  await new Promise(r => ws.onopen = r);
  let id = 0; const pend = {}; const frames = [];
  const dir = path.join(WORK, `frames-${name}`); fs.mkdirSync(dir, {recursive: true});
  const send = (method, params = {}) => new Promise(r => { const i = ++id; pend[i] = r; ws.send(JSON.stringify({id: i, method, params})); });
  ws.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.id && pend[m.id]) return pend[m.id](m);
    if (m.method === 'Page.screencastFrame') {
      const buf = Buffer.from(m.params.data, 'base64');
      const sof = buf.indexOf(Buffer.from([0xff, 0xc0]));  // JPEG 크기. 화면 크기가 자리 잡기 전 프레임은 버린다
      if (sof > 0 && buf.readUInt16BE(sof + 7) === width * scale && buf.readUInt16BE(sof + 5) === height * scale) {
        const f = path.join(dir, `f${String(frames.length).padStart(5, '0')}.jpg`);
        fs.writeFileSync(f, buf);
        frames.push({f, t: m.params.metadata.timestamp});
      }
      send('Page.screencastFrameAck', {sessionId: m.params.sessionId});
    }
  };
  const ev = async x => (await send('Runtime.evaluate', {expression: x, returnByValue: true, awaitPromise: true})).result.result?.value;
  await send('Page.enable');
  await send('Page.addScriptToEvaluateOnNewDocument', {source: OVERLAY});
  await send('Emulation.setDeviceMetricsOverride', {width, height, deviceScaleFactor: scale, mobile: width < 600});
  const s = {
    ev,
    go: async u => { await send('Page.navigate', {url: BASE + u}); await sleep(1200); },
    say: async (t, ms = 2600) => { await ev(`window.__cap(${JSON.stringify(t)})`); await sleep(ms); },
    // 누를 곳을 화면 가운데로 옮기고 표시한 뒤 누른다. sel 이 "text=글자"면 그 글자의 링크·버튼, idx -1 = 마지막
    tap: async (sel, wait = 1300, idx = 0) => {
      const find = `(${JSON.stringify(sel)}.startsWith('text=') ? [...document.querySelectorAll('a,button,summary')].filter(e => e.textContent.trim() === ${JSON.stringify(sel)}.slice(5))
        : [...document.querySelectorAll(${JSON.stringify(sel)})]).at(${idx})`;
      const r = await ev(`(() => { const e = ${find}; if (!e) return null;
        e.scrollIntoView({block: 'center', behavior: 'instant'}); const b = e.getBoundingClientRect(); return [b.x + b.width / 2, b.y + b.height / 2]; })()`);
      if (!r) throw new Error('없는 요소: ' + sel);
      await sleep(350); await ev(`window.__tap(${r[0]}, ${r[1]})`); await sleep(450);
      await ev(`${find}.click()`); await sleep(wait);
    },
    type: async (sel, text) => {
      await ev(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); e.scrollIntoView({block: 'center'}); e.focus(); e.value = ''; })()`);
      for (const ch of text) { await send('Input.insertText', {text: ch}); await sleep(90); }
      await sleep(400);
    },
    pick: async (sel, label) => {
      await ev(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); e.scrollIntoView({block: 'center'});
        const ok = [...e.options].filter(o => o.value && !o.disabled);  // label 이 비면 첫 사람
        const o = ok.find(o => o.text.startsWith(${JSON.stringify(label)})) || ok[0];
        e.value = o.value; e.dispatchEvent(new Event('change', {bubbles: true})); })()`);
      await sleep(1100);
    },
    scroll: async (y, ms = 1200) => { await ev(`window.scrollBy({top: ${y}, behavior: 'smooth'})`); await sleep(ms); },
    login: async user => {
      await s.go('/login/');
      await s.type('[name=username]', user); await s.type('[name=password]', PW);
      await s.tap('form button', 1800);
    },
    start: () => send('Page.startScreencast', {format: 'jpeg', quality: 85, everyNthFrame: 1}),
    finish: async () => {
      await sleep(1500); await send('Page.stopScreencast'); chrome.kill();
      // 프레임 사이 시간 그대로 이어 붙인다(화면이 안 바뀌면 프레임이 안 온다)
      const lines = ['ffconcat version 1.0'];
      frames.forEach((x, i) => { lines.push(`file '${x.f}'`, `duration ${((frames[i + 1]?.t ?? x.t + 1.5) - x.t).toFixed(3)}`); });
      lines.push(`file '${frames.at(-1).f}'`);
      const list = path.join(WORK, `${name}.txt`); fs.writeFileSync(list, lines.join('\n'));
      fs.mkdirSync(OUT, {recursive: true});
      execFileSync(FFMPEG, ['-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', list,
        '-vf', 'fps=20,scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p', '-c:v', 'libx264', '-preset', 'slow', '-crf', '30',
        '-movflags', '+faststart', path.join(OUT, `${name}.mp4`)]);
      console.log(name, frames.length, 'frames', Math.round(frames.at(-1).t - frames[0].t), 's',
        Math.round(fs.statSync(path.join(OUT, `${name}.mp4`)).size / 1024), 'KB');
    },
  };
  return s;
}

const VIDEOS = {
  async member() {
    const s = await session('member', 390, 844, 2);
    await s.start();
    await s.go('/login/');
    await s.say('NXT 당번표 사용법 — 모든 사용자\n아이디(멤버 코드)와 받은 비밀번호로 로그인합니다.', 2200);
    await s.login('member');
    await s.say('근무표: 이번 주 근무를 하루씩 봅니다.\n빨간 테두리가 오늘입니다.', 3000);
    await s.scroll(700, 1500);
    await s.say('굵은 기울임 글씨는 배포 뒤에 바뀐 근무,\n취소선은 빠진 사람입니다.', 3000);
    await s.say('바꿀 칸을 누릅니다.', 1200);
    await s.tap('a.cell[hx-get*="/normal/"]', 1600, -1);
    await s.say('From(이 칸 사람)과 To(바꿀 사람)를 고르면\n두 사람의 근무를 서로 맞바꿉니다.', 3400);
    await s.pick('#dlg select[name=after]', '');
    await s.say('To 목록 괄호 안이 그 사람의 그날 근무입니다.\n근무가 없는 사람이면 From 대신 들어갑니다.', 3400);
    await s.tap('#dlg form button', 1800);
    await s.say('저장하면 바로 반영되고 이력에 남습니다.\n지난 날짜는 관리자만 바꿀 수 있습니다.', 3200);
    await s.ev('scrollTo({top: 0})'); await sleep(600);
    await s.tap('details.filters summary', 900);
    await s.say('검색·필터: 사람 이름을 넣으면 근무표에 색으로 칠해지고,\n부서·스케줄로 거를 수 있습니다.', 2400);
    await s.type('input[name=q1]', '나사용');
    await s.tap('.names button', 1800);
    await s.scroll(500, 1600);
    await s.ev('scrollTo({top: 0})'); await sleep(500);
    await s.tap('nav.menu a[href="/me/"]', 1500);
    await s.say('내 근무: 앞으로의 내 근무만 모아 봅니다.\n날짜를 누르면 그날 전체 근무가 나옵니다.', 3200);
    await s.tap('nav.menu a[href="/alarms/"]', 1500);
    await s.say('알림·캘린더: 근무 전 알림, 내 근무가 바뀌면 바로 알림,\n휴대폰 캘린더 구독을 여기서 켭니다.', 3400);
    await s.scroll(600, 1500);
    await s.ev('scrollTo({top: 0})'); await sleep(500);
    await s.tap('nav.menu a[href="/help/"]', 1500);
    await s.say('이 영상과 설정 방법은 메뉴의 [도움말]에서\n언제든 다시 볼 수 있습니다.', 3000);
    await s.finish();
  },
  async manager() {
    const s = await session('manager', 390, 844, 2);
    await s.start();
    await s.go('/login/');
    await s.say('NXT 당번표 사용법 — 출근표 입력 담당', 2000);
    await s.login('manager');
    await s.say('부서 출근표 입력 담당에게는\n메뉴에 [출근표 입력]이 보입니다.', 2600);
    await s.tap('nav.menu a[href="/collect/"]', 1500);
    await s.say('취합 중인 회차와 부서별 입력 현황이 나옵니다.\n내 부서를 누릅니다.', 2800);
    await s.tap('a[href*="/MEMS/"]', 1500);
    await s.say('날짜마다 출근조 칸에 이름을 쉼표(,)로 구분해 적습니다.\n한 사람은 하루에 한 출근조만.', 3600);
    const names = (await s.ev(`(document.querySelector('p.guide').innerText.split('인원:')[1] || '').split(',').map(x => x.trim()).filter(Boolean)`)) || [];
    names.splice(0, names.length, ...names.filter(n => !['문하늘', '배다온', '노은별'].includes(n)));  // seed.py FREE(근무 없는 사람)는 넣지 않는다
    const rows = 'table.roster tbody tr:last-child td input';
    const cells = await s.ev(`document.querySelectorAll('${rows}').length`);
    const by = Array.from({length: cells}, () => []);
    names.forEach((n, i) => by[[1, 2, 1, 2, 1, 3, 2, 0][i % 8] % cells].push(n));  // 정상·석식교대 위주
    for (let c = 0; c < cells; c++) if (by[c].length) await s.type(`table.roster tbody tr:last-child td:nth-child(${c + 3}) input`, by[c].join(', '));
    await s.say('다 적었으면 아래 [표 저장]. 화면 아래에 늘 붙어 있습니다.', 2200);
    await s.tap('.savebar button', 1800);
    await s.ev('scrollTo({top: 0})'); await sleep(600);
    await s.say('엑셀로 하려면 [CSV 내려받기]로 받아 고친 뒤\n[CSV 올리기]로 부서 전체를 한 번에 바꿉니다.', 3600);
    await s.say('취합이 마감되면 더 고칠 수 없습니다.\n지난 날짜는 관리자만 고칠 수 있습니다.', 3000);
    await s.finish();
  },
  async admin() {
    const s = await session('admin', 1280, 800, 1);
    await s.start();
    await s.go('/login/');
    await s.say('NXT 당번표 사용법 — 관리자', 2000);
    await s.login('admin');
    await s.tap('nav.menu a[href="/periods/"]', 1500);
    await s.say('회차: 근무표를 만드는 단위입니다. 상태가 색으로 구분됩니다.\n[+ 새 회차]로 이름과 기간을 정해 만듭니다.', 3600);
    await s.tap('details.new-period summary', 1600);
    await s.tap('text=다음 회차', 1600);
    await s.say('작성 중 → 취합 중 → 마감 → 생성됨 → 배포됨 순서로 진행합니다.\n지금 할 다음 단계만 진한 버튼으로 보입니다.', 3800);
    await s.say('취합 중에는 부서 담당자가 출근표를 입력합니다.\n입력 현황이 다 차면 [취합 마감].', 3200);
    await s.tap('form[action$="/close/"] button', 1600);
    await s.say('[장중관제 생성]: 출근조를 보고 장중관제 10칸을\n편차 2 이하로 자동 배정합니다.', 3200);
    await s.tap('form[action$="/generate/"] button', 2000);
    await s.tap('button[onclick*="gen-help"]', 1400);
    await s.say('[생성 방식]에서 배정 규칙을 볼 수 있습니다.', 2800);
    await s.ev(`document.getElementById('gen-help').close()`); await sleep(600);
    await s.tap('a[href$="/publish/"]', 1500);
    await s.say('배포: 덮어쓰기 시작일을 고르면 겹치는 기존 근무표를\n그날부터 이 회차로 바꿉니다. 범위를 확인하고 [배포].', 3800);
    await s.tap('form[onsubmit*="배포할까요"] button', 2000);
    await s.say('배포하면 근무표에 바로 나타나고 알림이 나갑니다.\n잘못 배포했으면 [배포 취소]로 되돌릴 수 있습니다.', 3600);
    await s.scroll(600, 1500);
    await s.say('상태 기록에 누가 언제 무엇을 바꿨는지 남습니다.\n시험으로 만든 회차는 맨 아래 위험 구역에서 지웁니다.', 3400);
    await s.ev('scrollTo({top: 0})'); await sleep(500);
    await s.tap('nav.menu a[href="/stats/"]', 1500);
    await s.say('통계: 기간별 장중관제·새벽·야간 횟수.', 2400);
    await s.tap('nav.menu a[href="/changes/"]', 1500);
    await s.say('이력: 누가 어떤 근무를 바꿨는지 찾아봅니다.\n계정·부서·알림 설정은 [관리]에서 합니다.', 3400);
    await s.finish();
  },
};

for (const name of (only.length ? only : ['member', 'manager', 'admin'])) await VIDEOS[name]();
process.exit(0);
