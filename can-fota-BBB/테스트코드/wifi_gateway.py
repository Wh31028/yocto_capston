import socket
import struct
import os
import time
import can  # pip3 install python-can

# ==========================================
# CAN FOTA 설정
# ==========================================
CMD_FW_START      = 0x10
CMD_FW_DATA       = 0x20
CMD_FW_END        = 0x30
CMD_FW_JUMP_TO_FW = 0x40

# MCU에서 응답하는 ID
CAN_ID_RESP       = 0x101
# PC -> MCU로 보내는 ID
CAN_ID_CMD        = 0x100

def wait_ack(bus, timeout=2.0):
    """ MCU로부터 ACK(0x101)가 올 때까지 대기 """
    start_time = time.time()
    while (time.time() - start_time) < timeout:
        msg = bus.recv(0.1) # 0.1초 타임아웃으로 계속 확인
        if msg and msg.arbitration_id == CAN_ID_RESP:
            # msg.data[1] == 0 이면 성공, 아니면 에러
            return msg.data[1] == 0
    return False

def start_can_fota(firmware_path):
    print(f"\n[CAN] FOTA 시작: {firmware_path}")
    
    # 1. CAN 인터페이스 열기
    # (미리 터미널에서 'sudo ip link set can0 up type can bitrate 500000' 실행 필요)
    try:
        bus = can.interface.Bus(channel='can0', bustype='socketcan')
    except Exception as e:
        print(f"[CAN] 초기화 실패: {e}")
        return

    # 2. 펌웨어 파일 읽기
    with open(firmware_path, "rb") as f:
        fw_data = f.read()
    fw_size = len(fw_data)
    print(f"[CAN] 펌웨어 크기: {fw_size} bytes")

    # ---------------------------------------------------------
    # 3. [Start] Flash Erase 명령 전송
    # ---------------------------------------------------------
    # 데이터 구조: [CMD(1), Reserved(3), Size(4)]
    data = [CMD_FW_START, 0x00, 0x00, 0x00]
    # Little Endian으로 사이즈 변환해서 뒤에 붙임
    size_bytes = list(fw_size.to_bytes(4, byteorder='little'))
    data.extend(size_bytes)
    
    msg = can.Message(arbitration_id=CAN_ID_CMD, data=data, is_extended_id=False)
    bus.send(msg)
    print("[CAN] CMD_FW_START 전송 (Erase 대기...)")
    
    if not wait_ack(bus, timeout=5.0): # Erase는 시간이 좀 걸릴 수 있음
        print("[CAN] Error: Erase ACK Timeout/Fail")
        return

    # ---------------------------------------------------------
    # 4. [Data] 펌웨어 데이터 전송 (256바이트 단위 처리)
    # ---------------------------------------------------------
    # 중요: MCU 코드는 256바이트 버퍼가 찰 때마다 ACK를 보냄
    #      따라서 파이썬은 데이터를 계속 쏘되, 256바이트 경계마다 ACK를 확인해야 함
    
    idx = 0
    buffer_accumulated = 0 # MCU 버퍼에 쌓인 양
    
    while idx < fw_size:
        # 1패킷(8바이트) 구성: [CMD(1), Data(7)]
        chunk = fw_data[idx : idx + 7]
        payload = [CMD_FW_DATA] + list(chunk)
        
        msg = can.Message(arbitration_id=CAN_ID_CMD, data=payload, is_extended_id=False)
        bus.send(msg)
        
        data_len = len(chunk)
        idx += data_len
        buffer_accumulated += data_len
        
        # 256바이트가 꽉 찼거나(MCU가 Flash Write함), 파일의 끝이라면
        if buffer_accumulated >= 256:
            # MCU가 Flash Write 후 ACK 보낼 때까지 대기
            if not wait_ack(bus):
                print(f"[CAN] Error: Data Write ACK Fail at index {idx}")
                return
            buffer_accumulated = 0 # 리셋
            # print(f"[CAN] Progress: {idx}/{fw_size}") # 너무 시끄러우면 주석처리

        # 너무 빨리 쏘면 CAN 버퍼 터질 수 있으니 아주 살짝 지연 (필요시 조절)
        time.sleep(0.001)

    print("[CAN] 데이터 전송 완료")

    # ---------------------------------------------------------
    # 5. [End] 종료 및 잔여 데이터 처리 명령
    # ---------------------------------------------------------
    msg = can.Message(arbitration_id=CAN_ID_CMD, data=[CMD_FW_END], is_extended_id=False)
    bus.send(msg)
    
    if not wait_ack(bus):
        print("[CAN] Error: End ACK Fail")
        return
    print("[CAN] 펌웨어 플래싱 완료!")

    # ---------------------------------------------------------
    # 6. [Jump] 앱 실행 명령
    # ---------------------------------------------------------
    time.sleep(0.5)
    msg = can.Message(arbitration_id=CAN_ID_CMD, data=[CMD_FW_JUMP_TO_FW], is_extended_id=False)
    bus.send(msg)
    
    if wait_ack(bus):
        print("[CAN] 점프 성공! MCU가 재부팅됩니다.")
    else:
        print("[CAN] 점프 명령 보냈으나 응답 없음 (이미 점프했을 수도 있음)")


# ==========================================
# Wi-Fi TCP 서버
# ==========================================
def run_wifi_server(port=5000):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # 0.0.0.0은 모든 IP에서의 접속을 허용한다는 의미
    server_socket.bind(('0.0.0.0', port))
    server_socket.listen(1)
    
    print(f"=============================================")
    print(f" [비글본] FOTA Gateway 대기 중... IP: 172.30.1.98 Port: {port}")
    print(f"=============================================")

    while True:
        try:
            client_socket, addr = server_socket.accept()
            print(f"\n[WiFi] PC 연결됨: {addr}")

            # 1. 파일 크기 수신 (4바이트 Big Endian)
            size_data = client_socket.recv(4)
            if not size_data:
                client_socket.close()
                continue
            
            fw_size = struct.unpack('>I', size_data)[0]
            print(f"[WiFi] 수신할 파일 크기: {fw_size} bytes")

            # 2. 파일 데이터 수신
            received_size = 0
            fw_buffer = b''
            
            while received_size < fw_size:
                chunk = client_socket.recv(min(4096, fw_size - received_size))
                if not chunk:
                    break
                fw_buffer += chunk
                received_size += len(chunk)

            print(f"[WiFi] 파일 수신 완료. 저장 중...")

            # 3. 파일 저장
            save_path = "received_fw.bin"
            with open(save_path, "wb") as f:
                f.write(fw_buffer)
            
            # 4. PC에게 수신 완료 알림
            client_socket.send(b'OK')
            client_socket.close()

            # 5. CAN FOTA 시작
            start_can_fota(save_path)

        except Exception as e:
            print(f"[Error] {e}")
            # 에러 나도 서버는 죽지 않고 다시 대기
            time.sleep(1)

if __name__ == '__main__':
    # CAN 활성화 (이미 되어있다면 에러나도 무관)
    os.system("sudo ip link set can0 up type can bitrate 1000000")
    run_wifi_server()