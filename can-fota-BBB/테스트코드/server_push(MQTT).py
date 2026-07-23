import paho.mqtt.publish as publish
import json

BROKER = "broker.emqx.io"
TOPIC = "pnu/fota/trigger_can"

# 비글본에게 보낼 알림 내용 (JSON 형태)
payload = json.dumps({
    "cmd": "UPDATE_START",
    "version": "1.1",
    "desc": "CAN FOTA Update Triggered from Server"
})

print("[Server] 비글본으로 FOTA Push 알림 전송 중...")

# 메세지를 쏘고 바로 종료됩니다.
publish.single(TOPIC, payload, hostname=BROKER)

print("[Server] 전송 완료! 비글본의 반응을 확인하세요.")