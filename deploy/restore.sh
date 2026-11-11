#!/bin/bash
# DB 복원: sudo /opt/duty_generator/deploy/restore.sh /var/backups/duty_generator/<백업 파일>
# 백업이 깨졌으면(quick_check 가 ok 가 아니면) 아무것도 바꾸지 않고 멈춘다.
set -euo pipefail

main() {
  [ "$(id -u)" = 0 ] || { echo "sudo 로 실행하세요."; exit 1; }
  [ $# = 1 ] && [ -f "$1" ] || { echo "사용: sudo $0 <백업 파일>"; exit 1; }
  local src=$1 db check alarms_on
  db=$(cd /opt/duty_generator && .venv/bin/python -c 'import config.settings as s; print(s.DB_PATH)')   # .env 의 DUTY_DB_PATH
  check=$(sudo -u duty sqlite3 "$src" "PRAGMA quick_check")
  [ "$check" = ok ] || { echo "!! 백업 파일 검사 실패: $check"; exit 1; }

  alarms_on=0; systemctl is-enabled -q duty-alarms 2>/dev/null && alarms_on=1
  systemctl stop duty-health.timer duty-health.service 2>/dev/null || true
  systemctl stop duty-alarms duty-generator
  sudo -u duty sqlite3 "$db" ".backup /var/backups/duty_generator/before-restore-$(date +%Y%m%d-%H%M%S).sqlite3"
  sudo -u duty cp "$src" "$db"
  sudo -u duty rm -f "$db-wal" "$db-shm"
  # 지금 코드보다 오래된 백업이면 구조를 맞춘다
  sudo -u duty /opt/duty_generator/.venv/bin/python /opt/duty_generator/manage.py migrate
  systemctl start duty-generator
  [ "$alarms_on" = 1 ] && systemctl start duty-alarms
  sleep 3
  systemctl is-active -q duty-generator || { echo "!! 웹이 뜨지 않음:"; tail -n 30 /var/log/duty_generator/web.log; exit 1; }
  systemctl enable -q --now duty-health.timer
  echo "== 복원 완료: $src (복원 직전 DB 는 before-restore-*.sqlite3)"
}

main "$@"
exit
