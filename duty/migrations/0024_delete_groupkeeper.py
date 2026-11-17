"""그룹 관리자(GroupKeeper) 표를 지운다(근무표 통합 설계 5.6·10.2, 3단계). 멤버 넣고 빼기는 [근무표 설정]의 관리자·입력 담당자 칸이 한다.

- 행은 권한 지정일 뿐 기록(변경·상태)이 걸려 있지 않다. 업그레이드 전에 OPERATIONS 확인 ②대로 전부 CSV 로 내보내 둔다(참고용).
- 거꾸로는 빈 표가 돌아온다(거부하지 않는다: 늘 거부하면 0024 아래로 내려가는 마이그레이션 테스트가 모두 깨진다).
  행까지 되돌리는 롤백은 업그레이드 전 백업 복원만 지원한다.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('duty', '0023_board_steps'),
    ]

    operations = [
        migrations.DeleteModel(
            name='GroupKeeper',
        ),
    ]
