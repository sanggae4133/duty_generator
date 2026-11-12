# NXT 당번표

IT 부서의 출근조·장중관제 당번표를 만들고, 바꾸고, 알려 주는 사내 웹앱. 구글 시트 + Apps Script 당번표를 대체한다.

- 회차 단위로 **부서 출근표를 취합**하고(표·CSV), **장중관제 당번을 자동 생성**해(편차 2 이하를 목표로) **배포**한다.
- 배포된 근무표를 휴대폰·PC 에서 보고 **근무를 바꾸면 누가 언제 무엇을 바꿨는지 남는다**. 지난 날짜는 관리자만.
- 근무 전 **텔레그램·웹 푸시 알림**, 휴대폰 캘린더에 **내 근무 구독(ICS)**.
- 잘못 배포하면 **배포 취소**로 되돌린다. 매일 DB 를 백업한다.
- 처음 쓰는 사람을 위한 **권한별 1분 사용법 영상**(메뉴 [도움말]).

## 누가 무엇을

| 역할 | 할 수 있는 일 |
|---|---|
| 멤버 | 근무표·내 근무 보기, 오늘·미래 근무 바꾸기, 알림·캘린더 |
| 출근표 입력 담당 | 취합 중인 회차에 자기 부서 출근표 입력 |
| 관리자(스태프) | 회차 만들기·취합·생성·배포·배포 취소, 지난 날짜 수정, 통계·이력 |
| 슈퍼유저 | 관리 화면: 계정 발급·부서·입력 담당자·로그인 잠금 해제·알림 설정(관리자 1~2명이 함께 가진다) |

## 기술

Python 3.12 · Django 5.2 · SQLite(WAL) · 서버 렌더링 템플릿 + htmx + Pico.css(빌드 없음) · gunicorn · systemd · Tailscale Funnel · 사내 서버 RHEL 9.4+

## 빠른 시작 (개발 PC)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock -r requirements-dev.txt
cp .env.example .env                       # 견본이 개발 PC 값이라 그대로 쓴다
.venv/bin/pytest -W error                  # 전체 테스트
.venv/bin/python manage.py migrate         # data/db.sqlite3 를 만든다
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py runserver       # http://127.0.0.1:8000 (Ctrl+C 로 끈다)
```

## 문서

| 문서 | 내용 |
|---|---|
| [docs/OVERVIEW.md](docs/OVERVIEW.md) | 기획: 배경, 목표, 사용자, 한 회차의 흐름, 범위, 용어 |
| [docs/PRINCIPLES.md](docs/PRINCIPLES.md) | 설계 철학, 기술 선택의 이유, 결정 기록 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 구조와 도메인 규칙: 코드 지도, 데이터, 회차, 근무 변경, 알림, 캘린더, 화면 디자인 |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | 운영: 설치, 업그레이드·롤백, 백업·복원, 로그·장애 알림, 알림 설정, 데이터 보기 |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | 개발: 환경, 테스트, 작업 방식, 사용법 영상 다시 만들기, 의존성 고정 |

## 폴더

```
config/        Django 설정(.env 를 읽는다)·URL
duty/          앱 본체: 모델·서비스·화면·관리 명령·템플릿·정적 파일·사용법 영상
tests/         pytest
deploy/        systemd 유닛 두 개(웹·작업자)
tools/         개발용 도구(사용법 영상 녹화)
docs/          문서
.env.example   설정 견본(.env 로 복사, git 에 올리지 않음)
data/          실행 중 생기는 파일: DB·백업·로그(git 에 올리지 않음)
```

## 프로젝트 정보

- 사내 프로젝트다. 저장소에는 실명·비밀값을 올리지 않는다(테스트·영상은 가짜 데이터).
- 문의·버그는 저장소 이슈 또는 IT 운영 관리자에게.
