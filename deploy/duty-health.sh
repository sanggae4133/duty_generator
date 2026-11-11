#!/bin/sh
# 5분마다(duty-health.timer): 웹 응답·알림 서비스·최근 백업·디스크를 보고
# 상태가 바뀔 때만 텔레그램으로 알린다(문제 생김 / 정상 복귀). DUTY_OPS_CHAT_ID 가 비면 기록만 한다.
set -u
problems=""
curl -fs -o /dev/null -m 10 http://127.0.0.1:8090/login/ || problems="$problems 웹 응답 없음;"
if systemctl is-enabled -q duty-alarms 2>/dev/null; then
  systemctl is-active -q duty-alarms || problems="$problems 알림 서비스 멈춤;"
fi
[ -n "$(find /var/backups/duty_generator -name 'db-*.sqlite3' -mmin -1560 2>/dev/null | head -n 1)" ] \
  || problems="$problems 26시간 안에 만든 백업 없음;"
use=$(df --output=pcent "$(dirname "$DUTY_DB_PATH")" 2>/dev/null | tail -n 1 | tr -dc 0-9)
if [ -z "$use" ]; then problems="$problems 디스크 확인 실패;"
elif [ "$use" -ge 90 ]; then problems="$problems 디스크 ${use}% 사용;"; fi

state="$(dirname "$DUTY_DB_PATH")/.health.state"
if [ ! -f "$state" ] && [ -z "$problems" ]; then   # 첫 실행이 정상이면 기록만(알림 없음)
  echo "$(date '+%F %T') health: 정상(점검 시작)"; : > "$state"; exit 0
fi
[ -f "$state" ] && [ "$problems" = "$(cat "$state")" ] && exit 0
echo "$(date '+%F %T') health:${problems:- 정상}"
if [ -n "${DUTY_OPS_CHAT_ID:-}" ] && [ -n "${DUTY_TELEGRAM_BOT_TOKEN:-}" ]; then
  # 토큰이 프로세스 목록에 보이지 않게 curl 설정을 표준입력으로 넘긴다
  printf 'url = "https://api.telegram.org/bot%s/sendMessage"\n' "$DUTY_TELEGRAM_BOT_TOKEN" \
    | curl -fsS -m 10 -o /dev/null -K - --data-urlencode "chat_id=$DUTY_OPS_CHAT_ID" \
        --data-urlencode "text=[당번표 $(hostname)]${problems:- 정상으로 돌아왔습니다.}" \
    || exit 1   # 못 보냈으면 상태를 저장하지 않고 다음 번에 다시 보낸다
fi
printf '%s' "$problems" > "$state"
