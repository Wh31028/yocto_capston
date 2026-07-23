import paho.mqtt.client as mqtt
import os
import json

# 테스트용 무료 공개 브로커(서버) 사용
BROKER = "broker.emqx.io" 
# 우리만의 고유한 통신 채널 (주파수)
TOPIC = "pnu/fota/trigger_can" 

def on_connect(client, userdata, flags, rc):
    print(f"[MQTT] 서버 연결 성공! (상태 코드: {rc})")
    client.subscribe(TOPIC)
    print(f"[MQTT] '{TOPIC}' 채널 수신 대기 중...")

def on_message(client, userdata, msg):
    payload = msg.payload.decode('utf-8')
    print(f"\n[알림 수신!] 메세지: {payload}")
    
    try:
        data = json.loads(payload)
        # 서버에서 보낸 명령이 "UPDATE_START" 라면?
        if data.get("cmd") == "UPDATE_START":
            print("[System] FOTA 업데이트 명령을 확인했습니다. 플래싱을 시작합니다!")
            
            # 방금 성공했던 CAN FOTA 스크립트를 즉시 실행!
            os.system("sudo python3 isotp_lte_gateway.py")
            
            print("[System] FOTA 프로세스 종료. 다시 대기 모드로 돌아갑니다.")
    except Exception as e:
        print(f"메세지 분석 에러: {e}")

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

print("=========================================")
print(" BeagleBone Black FOTA Listener 실행 중")
print("=========================================")
client.connect(BROKER, 1883, 60)

# 꺼지지 않고 무한히 대기합니다.
client.loop_forever()