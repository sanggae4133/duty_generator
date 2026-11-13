# 개발

개발 PC 에서 코드를 고치고 시험하는 방법. 코드를 고치기 전에 [ARCHITECTURE.md](ARCHITECTURE.md)를, 왜 그렇게 만들었는지는 [PRINCIPLES.md](PRINCIPLES.md)를 읽는다.

## 환경 만들기

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock -r requirements-dev.txt
cp .env.example .env   # 견본 값이 개발 PC 용이라 고칠 것 없다
.venv/bin/pytest -W error   # 테스트는 .env 를 읽지 않는다
.venv/bin/python manage.py migrate   # data/db.sqlite3 를 만든다
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py runserver
```

- `.env` 없이 `DUTY_DEBUG=1 .venv/bin/python manage.py runserver` 처럼 앞에 환경변수를 붙여도 된다(환경변수가 `.env` 보다 이긴다).
- 개발 PC 에서 `run_worker` 를 켜면 실제로 알림을 보낸다(관리 화면에 봇 토큰을 넣었을 때). 상태 점검은 웹을 nginx 주소 `127.0.0.1:8008` 에서 찾으므로, runserver(8000)만 켰다면 "웹 응답 없음"이 로그에 남는다(장애 알림 chat_id 를 비워 두면 보내지는 않는다).

## 테스트

```bash
.venv/bin/pytest -W error                    # 전체(약 7~8분). 경고가 하나라도 있으면 실패로 본다
.venv/bin/pytest -W error tests/test_help.py # 파일 하나
.venv/bin/pytest -W error -k "unpublish"     # 이름으로 골라서
```

- 설정은 `config.test_settings`(pytest 가 알아서 쓴다). 테스트는 `.env` 를 읽지 않고 임시 `data/` 를 쓴다.
- **테스트를 먼저 쓴다**: 실패하는 것을 확인한 뒤 구현한다. 버그도 재현 테스트부터.
- 실명을 쓰지 않는다(가상 이름·멤버 코드만). 비밀값처럼 생긴 문자열은 실행 중에 조립한다(`"1234567890:" + "FAKE" + ...`).
- 텔레그램·웹 푸시는 실제로 부르지 않는다(`duty.alarms.senders` 를 monkeypatch).
- "오늘"이 필요한 테스트는 `fixed_today` fixture 로 `perms.today()` 를 바꿔 끼운다.

## 화면을 바꿨을 때

테스트만으로 끝내지 않고 브라우저에서 직접 본다: **PC 1400px, 휴대폰 390px, 다크 모드**. 가로로 넘치는 곳(`document.documentElement.scrollWidth > innerWidth`)이 없어야 한다. 화면 규칙(색·버튼 위계·메시지)은 ARCHITECTURE.md "화면 디자인". 사용법 영상에 나오는 화면이면 영상도 다시 뽑는다(아래).

## 작업 방식

- `main` 에서 직접 고치지 않는다. 브랜치(`feat/…`, `fix/…`, `docs/…`)를 따서 PR 로 합친다.
- 커밋 메시지는 `feat:` / `fix:` / `docs:` / `style:` 접두어 + 한국어 요약.
- 큰 변경은 다른 사람(또는 Codex 같은 리뷰 도구)의 리뷰를 받고, 지적마다 반영하거나 이유를 남긴다.
- 동작을 바꾸면 문서도 같은 PR 에서 고친다: 구조·규칙은 ARCHITECTURE.md, 운영 명령은 OPERATIONS.md, 결정의 이유는 PRINCIPLES.md "결정 기록".
- 모델을 바꾸면 `DUTY_DEBUG=1 .venv/bin/python manage.py makemigrations` 로 마이그레이션 파일을 만들어 함께 커밋한다. 마이그레이션 파일은 지우지 않는다(운영 DB 를 올리는 유일한 길).
- 실명 데이터(DB 파일·`data/`·백업)는 저장소에 올리지 않는다(`.gitignore`). 회사 CI 원본 같은 큰 자료도 올리지 않고 필요한 것만 골라 `duty/static/duty/` 에 넣는다.

## 사용법 영상 다시 만들기 (개발 PC)

메뉴 [도움말]과 첫 로그인 팝업의 영상은 `duty/help_videos/{member,manager,admin}.mp4` 이다(권한 확인 뒤에만 내려준다: 담당자 영상은 담당자·관리자, 관리자 영상은 관리자). 화면을 크게 바꿨으면 가짜 데이터로 다시 녹화한다. 실명은 나오지 않는다.

```bash
W=$(mktemp -d)                                         # 작업 폴더(끝나면 지운다)
python3 -m venv $W/ff && $W/ff/bin/pip install imageio-ffmpeg   # ffmpeg(시스템에 깔지 않는다)
FF=$($W/ff/bin/python -c "import imageio_ffmpeg as i; print(i.get_ffmpeg_exe())")
export DUTY_ENV_FILE= DUTY_DEBUG=1 DUTY_DATA_DIR=$W/data   # 빈 DB(지금 data/ 를 건드리지 않는다)
.venv/bin/python manage.py migrate && .venv/bin/python manage.py shell < tools/help_videos/seed.py
.venv/bin/python manage.py runserver 127.0.0.1:8795 --noreload & SRV=$!
node tools/help_videos/record.mjs http://127.0.0.1:8795 $W $FF     # member → manager → admin 순서
kill $SRV; rm -rf $W
```

- 자막·순서는 `tools/help_videos/record.mjs` 의 `VIDEOS` 에서 고치고, 같은 내용의 글(`duty/help.py` 의 `STEPS`, 도움말의 "글로 보기")도 같이 고친다.
- 영상 하나만 다시 뽑으려면 끝에 이름(`member` 등)을 붙인다. 단 `admin` 은 담당자 영상이 채우는 출근표를 쓰므로 `manager admin` 으로 함께 뽑는다(새 데이터에서).
- Chrome·Node 가 필요하다. 영상은 휴대폰 화면(390×844, 2배율), 관리자 영상만 PC 화면(1280×800)이다.

## 의존성 고정

설치하지 않는 프로젝트다(`pip install -e .` 없음). 직접 쓰는 라이브러리와 허용 범위는 `requirements.in`, 운영 설치는 `requirements.lock` 의 고정 버전만 쓴다. 테스트 도구는 `requirements-dev.txt`(고정). 라이브러리를 올릴 때만 개발 PC 에서 lock 을 다시 만든다.

```bash
python3 -m venv /tmp/lockvenv && /tmp/lockvenv/bin/pip install -U -r requirements.in
{ echo '# 운영 설치용 고정 버전. 갱신: docs/DEVELOPMENT.md "의존성 고정" 참고'; /tmp/lockvenv/bin/pip freeze; } > requirements.lock
rm -rf /tmp/lockvenv
.venv/bin/pip install -r requirements.lock -r requirements-dev.txt && .venv/bin/pytest -W error   # 통과하면 커밋
```
