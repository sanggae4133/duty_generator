#!/bin/bash
# 업그레이드·롤백: sudo /opt/duty_generator/deploy/upgrade.sh [버전]
#   버전 없이 → 최신 main. 버전(커밋 해시)을 주면 그 버전으로(롤백).
# 한 단계라도 실패하면 그 자리에서 멈춘다(set -e). 서비스는 멈춘 상태로 남으니 메시지를 보고 고친 뒤 다시 실행한다.
set -euo pipefail

main() {  # 함수로 감싸 전체를 먼저 읽는다(git checkout 이 실행 중인 이 파일을 바꿔도 안전)
  [ "$(id -u)" = 0 ] || { echo "sudo 로 실행하세요."; exit 1; }
  cd /opt/duty_generator
  [ -f .env ] || { echo "!! /opt/duty_generator/.env 가 없습니다(README \"설치\" 참고)."; exit 1; }
  local db alarms_on backup
  db=$(.venv/bin/python -c 'import config.settings as s; print(s.DB_PATH)')   # .env 의 DUTY_DB_PATH(없으면 기본값)
  dm() { sudo -u duty /opt/duty_generator/.venv/bin/python /opt/duty_generator/manage.py "$@"; }

  echo "== 지금 버전: $(git log -1 --format=%h) (롤백할 때 이 값을 쓴다)"
  backup=/var/backups/duty_generator/before-upgrade-$(date +%Y%m%d-%H%M%S).sqlite3
  sudo -u duty sqlite3 "$db" ".backup $backup"
  echo "== 백업: $backup"

  git fetch -q origin
  local target=${1:-origin/main}
  # 이 스크립트가 없는 예전 버전으로는 되돌릴 수 없다(README "업그레이드·롤백" 참고)
  git cat-file -e "$target:deploy/upgrade.sh" 2>/dev/null || { echo "!! $target 에는 deploy/upgrade.sh 가 없어 이 스크립트로 되돌릴 수 없습니다."; exit 1; }

  alarms_on=0; systemctl is-enabled -q duty-alarms 2>/dev/null && alarms_on=1
  systemctl stop duty-health.timer duty-health.service 2>/dev/null || true   # 계획된 정지를 장애로 알리지 않게
  systemctl stop duty-alarms duty-generator

  if [ $# -ge 1 ]; then git checkout -q "$1"; else git checkout -q main && git pull -q --ff-only; fi
  echo "== 새 버전: $(git log -1 --format='%h %s')"

  .venv/bin/pip install -q -r requirements.lock
  .venv/bin/pip install -q --no-deps -e .
  .venv/bin/python manage.py collectstatic --noinput -v0   # root: /opt 는 duty 쓰기 권한이 없다
  dm migrate

  install -d -o root -g adm -m 750 /var/log/duty_generator
  cp deploy/*.service deploy/*.timer /etc/systemd/system/
  [ -f deploy/duty_generator.logrotate ] && cp deploy/duty_generator.logrotate /etc/logrotate.d/duty_generator
  systemctl daemon-reload

  systemctl start duty-generator
  [ "$alarms_on" = 1 ] && systemctl start duty-alarms

  if [ -f .env.example ]; then   # .env.example 의 필수 줄(주석 아님)이 .env 에 없거나, .env 에 더는 안 쓰는 이름이 있으면 알린다
    local missing unused
    missing=$(comm -23 <(grep -oE '^DUTY_[A-Z_]+=' .env.example | sort -u) <(grep -oE '^DUTY_[A-Z_]+=' .env | sort -u) | tr -d = | tr '\n' ' ')
    unused=$(comm -13 <(grep -oE '^(# )?DUTY_[A-Z_]+=' .env.example | sed 's/^# //' | sort -u) <(grep -oE '^DUTY_[A-Z_]+=' .env | sort -u) | tr -d = | tr '\n' ' ')
    [ -z "$missing" ] || echo "!! .env 에 없는 설정: $missing— .env.example 설명을 보고 sudoedit /opt/duty_generator/.env 로 추가한 뒤 서비스를 재시작"
    [ -z "$unused" ] || echo "!! .env 에 더는 쓰지 않는 설정: $unused— 지워도 된다(sudoedit /opt/duty_generator/.env)"
  fi

  sleep 3
  systemctl is-active -q duty-generator || { echo "!! 웹이 뜨지 않음:"; tail -n 30 /var/log/duty_generator/web.log; exit 1; }
  systemctl enable -q --now duty-health.timer
  echo "== 완료: 웹 실행 중"
}

main "$@"
exit
