"""<<boundary>> 알림 발송 연결 — SPRINT 3(알림) 범위. 아직 만들지 않았다."""


class NotifierError(Exception):
    """발송 실패 (SPRINT 3에서 재시도 규칙과 함께 정한다)."""


def send(channel, message):  # 발송한다(채널, 메시지) : 결과
    raise NotImplementedError("SPRINT 3 범위 (알림)")
