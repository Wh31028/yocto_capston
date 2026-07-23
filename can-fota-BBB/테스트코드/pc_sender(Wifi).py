import socket
import struct
import os

# ==========================================
# 설정
# ==========================================
# 비글본 IP 주소 (확인하신 주소)
BEAGLEBONE_IP = '172.30.1.98' 
PORT = 5000
# 보낼 펌웨어 파일 경로 (본인의 bin 파일 경로로 수정하세요!)
FW_FILE = 'boot_can_fw.bin' 

def send_firmware():
    if not os.path.exists(FW_FILE):
        print(f"에러: 파일이 없습니다 -> {FW_FILE}")
        return

    file_size = os.path.getsize(FW_FILE)
    print(f"[PC] 연결 시도... {BEAGLEBONE_IP}:{PORT}")
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((BEAGLEBONE_IP, PORT))
        print(f"[PC] 연결 성공!")

        # 1. 파일 크기 먼저 전송 (Pack as 4-byte Big Endian)
        sock.send(struct.pack('>I', file_size))
        
        # 2. 파일 내용 전송
        print(f"[PC] 전송 시작 ({file_size} bytes)...")
        with open(FW_FILE, 'rb') as f:
            data = f.read()
            sock.sendall(data)
            
        print(f"[PC] 전송 완료. 비글본 응답 대기중...")

        # 3. 비글본의 'OK' 응답 대기
        response = sock.recv(1024)
        if response == b'OK':
            print("[PC] 성공! 비글본이 CAN 업데이트를 진행합니다.")
        else:
            print(f"[PC] 비글본 응답 이상함: {response}")

    except Exception as e:
        print(f"[Error] 연결 실패: {e}")
    finally:
        sock.close()

if __name__ == '__main__':
    send_firmware()