# duty_generator

IT 당번표 웹. 회차 단위로 부서 출근표를 취합하고, 장중관제 당번을 생성·배포하고, 근무 변경을 기록한다.
설계: `docs/superpowers/specs/2026-11-09-duty-generator-design.md`

## 개발

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
DUTY_DEBUG=1 .venv/bin/python manage.py migrate
DUTY_DEBUG=1 .venv/bin/python manage.py createsuperuser
DUTY_DEBUG=1 .venv/bin/python manage.py runserver
```

## 설치 (사내 서버, 노티파이어와 같은 서버)

```bash
sudo apt install -y sqlite3   # 백업 타이머가 sqlite3 CLI를 쓴다
sudo useradd -r -s /usr/sbin/nologin duty
sudo mkdir -p /opt/duty_generator
sudo install -d -o duty -g duty -m 750 /var/lib/duty_generator /var/backups/duty_generator
sudo install -d -o root -g duty -m 750 /etc/duty_generator
# 코드 배치 후
cd /opt/duty_generator && python3 -m venv .venv && .venv/bin/pip install .
sudo install -o root -g duty -m 640 deploy/env.example /etc/duty_generator/env   # 값 채우기 (SECRET_KEY, API 토큰은 python -c "import secrets;print(secrets.token_urlsafe(48))")
sudo sh -c 'set -a; . /etc/duty_generator/env; cd /opt/duty_generator && .venv/bin/python manage.py collectstatic --noinput'   # root: /opt 는 duty 쓰기 권한이 없다
sudo -u duty sh -c 'set -a; . /etc/duty_generator/env; cd /opt/duty_generator && .venv/bin/python manage.py migrate'
sudo cp deploy/*.service deploy/*.timer /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now duty-generator duty-generator-backup.timer
```

## 외부 공개 (Tailscale Funnel)

443 포트를 경로로 나눈다. 웹은 `/`, 노티파이어 카카오 웹훅은 기존 경로를 유지한다.

```bash
sudo tailscale funnel --bg --set-path / http://127.0.0.1:8090
sudo tailscale funnel status
```

노티파이어는 Funnel을 거치지 않고 `http://127.0.0.1:8090/api/assignments` 를 `Authorization: Bearer $DUTY_API_TOKEN` 으로 호출한다.

## 처음 한 번: 기존 시트 가져오기

```bash
sudo -u duty sh -c 'set -a; . /etc/duty_generator/env; .venv/bin/python manage.py import_sheets --dry-run'
sudo -u duty sh -c 'set -a; . /etc/duty_generator/env; .venv/bin/python manage.py import_sheets'
```

이후 `/<DUTY_ADMIN_PATH>/` 의 멤버 목록에서 멤버를 선택하고 "계정 발급 / 비밀번호 초기화" 액션으로 임시 비밀번호를 발급한다.
부서 입력 담당자는 부서 화면의 "입력 담당자"에서 지정한다. 어드민은 사용자 화면에서 "스태프 권한"을 켠다.

## 운영 메모

- 로그인 5회 실패 시 그 계정은 15분 잠긴다. Admin의 Axes 메뉴에서 해제할 수 있다.
- 백업: 매일 03:00 `/var/backups/duty_generator/` 에 최근 30개 보관.
