import can
import time
import os
import struct

# --- 설정 (환경에 맞게 수정하세요) ---
BUS_INTERFACE = 'can0'  # ifconfig로 확인한 CAN 인터페이스 이름
TARGET_ID     = 0x100   # 보낼 때 ID (비글본 -> STM32)
RESPONSE_ID   = 0x101   # 받을 때 ID (STM32 -> 비글본)

CMD_FW_START  = 0x10
CMD_FW_DATA   = 0x20
CMD_FW_END    = 0x30

FLASH_PAGE_SIZE = 256   # STM32 플래시 페이지 크기

def wait_for_ack(bus, expected_cmd, timeout=2.0):
    """
    특정 명령어에 대한 ACK(성공 응답)만 기다리는 함수
    """
    start_time = time.time()
    while (time.time() - start_time) < timeout:
        rx_msg = bus.recv(timeout=0.1) # 0.1초씩 끊어서 확인
        
        if rx_msg and rx_msg.arbitration_id == RESPONSE_ID:
            # 데이터 구조: [명령어, 결과코드]
            if len(rx_msg.data) >= 2:
                cmd = rx_msg.data[0]
                result = rx_msg.data[1]
                
                # 기대한 명령어에 대한 성공(0) 응답인지 확인
                if cmd == expected_cmd and result == 0:
                    return True
                elif cmd == expected_cmd and result != 0:
                    print(f" [Error] STM32 returned error code: {result}")
                    return False
    return False

def send_packet_with_ack(bus, data, timeout=2.0):
    """
    명령을 보내고 바로 ACK를 기다리는 함수 (START, END 용)
    """
    msg = can.Message(arbitration_id=TARGET_ID, data=data, is_extended_id=True)
    try:
        bus.send(msg)
        return wait_for_ack(bus, data[0], timeout)
    except can.CanError:
        print(" [Error] CAN Send Failed")
        return False

def send_firmware(filename):
    # 0. CAN 연결
    try:
        bus = can.interface.Bus(channel=BUS_INTERFACE, bustype='socketcan')
        print(f"[Info] Connected to {BUS_INTERFACE}")
    except OSError:
        print(f"[Error] Could not open {BUS_INTERFACE}. Check if interface is UP.")
        return

    if not os.path.exists(filename):
        print(f"[Error] File not found: {filename}")
        return

    file_size = os.path.getsize(filename)
    with open(filename, "rb") as f:
        firmware_blob = f.read()

    print(f"--- FOTA Start : {filename} ({file_size} bytes) ---")

    # ---------------------------------------------------------
    # 1. [FW_START] 전송 (파일 크기 포함, Flash Erase 수행)
    # ---------------------------------------------------------
    print("1. Sending Start Command (Erasing Flash...)")
    # [CMD] + [Reserved 3bytes] + [Size 4bytes]
    cmd_start = struct.pack('<B3xI', CMD_FW_START, file_size)
    
    # Erase 시간 고려하여 타임아웃 5초 설정
    if not send_packet_with_ack(bus, list(cmd_start), timeout=5.0):
        print(" [Fail] Start command failed or timed out.")
        return
    print(" -> Erase Complete & Start OK.")

    # ---------------------------------------------------------
    # 2. [FW_DATA] 데이터 전송 (256바이트마다 ACK 대기)
    # ---------------------------------------------------------
    print("2. Sending Firmware Data...")
    
    total_sent = 0       # 전체 전송량
    page_buffer_acc = 0  # 현재 페이지(256) 누적량
    
    # 7바이트씩 잘라서 루프
    for i in range(0, len(firmware_blob), 7):
        chunk = firmware_blob[i : i + 7]
        payload = list(chunk)
        
        # 마지막 패킷 패딩 (0으로 채움, STM32 로직상 필수는 아니지만 안전하게)
        while len(payload) < 7:
            payload.append(0)

        # 패킷 전송: [CMD(0x20)] + [DATA 7bytes]
        can_data = [CMD_FW_DATA] + payload
        msg = can.Message(arbitration_id=TARGET_ID, data=can_data, is_extended_id=True)
        bus.send(msg)
        
        # 카운트 증가
        page_buffer_acc += len(chunk) # 실제 데이터 길이만큼 증가
        total_sent += len(chunk)

        # ★ 동기화 핵심 로직 ★
        # STM32는 버퍼가 256바이트 꽉 차면 Flash에 쓰고 ACK를 보냄.
        # 우리도 누적량이 256 이상이면 ACK를 기다려야 함.
        if page_buffer_acc >= FLASH_PAGE_SIZE:
            # print(f"   Waiting for ACK (Page Write)... {total_sent}/{file_size}")
            
            if wait_for_ack(bus, CMD_FW_DATA, timeout=1.5):
                # 성공 시 누적 카운터에서 256 차감 (STM32 버퍼가 비워짐)
                # 남은 값은 다음 페이지의 시작 데이터가 됨
                page_buffer_acc -= FLASH_PAGE_SIZE 
                print(f"\r -> Progress: {total_sent}/{file_size} bytes ({(total_sent/file_size)*100:.1f}%)", end='')
            else:
                print("\n [Error] Missing ACK for Page Write! Stopping.")
                return

        # 너무 빠르면 STM32 수신 버퍼 오버플로우 날 수 있으므로 아주 약간 딜레이
        time.sleep(0.002) 
    print("\n -> Data Transmission Complete.")

    # ---------------------------------------------------------
    # 3. [FW_END] 종료 명령 (나머지 데이터 Flush & Reboot)
    # ---------------------------------------------------------
    print("3. Sending End Command...")
    
    # 데이터 없는 순수 명령 패킷
    cmd_end = [CMD_FW_END, 0, 0, 0, 0, 0, 0, 0]
    
    if send_packet_with_ack(bus, cmd_end, timeout=3.0):
        print("\n[SUCCESS] Firmware Update Finished Successfully!")
    else:
        print("\n[Warning] No ACK for End command (Maybe device rebooted immediately?)")
    
    # ---------------------------------------------------------
    # 4. [FW_JUMP] 펌웨어 실행 명령 (0x40)
    # ---------------------------------------------------------
    print("4. Sending Jump Command...")
    CMD_FW_JUMP_TO_FW = 0x40
    
    cmd_jump = [CMD_FW_JUMP_TO_FW, 0, 0, 0, 0, 0, 0, 0]
    
    # 점프 명령을 보내고 ACK를 기다림
    if send_packet_with_ack(bus, cmd_jump, timeout=2.0):
        print("\n[SUCCESS] Jump Command Accepted! Application should start now.")
    else:
        print("\n[Warning] No ACK for Jump command (Maybe device jumped too fast?)")

if __name__ == "__main__":
    # 테스트용 파일 이름 (실제 bin 파일 이름으로 바꾸세요)
    fw_filename = "boot_can_fw.bin"
    
    # 파일이 없으면 테스트용 더미 파일 생성
    if not os.path.exists(fw_filename):
        print(f"File {fw_filename} not found. Creating dummy file for test...")
        with open(fw_filename, "wb") as f:
            # 1024 + 50 바이트 (딱 안 떨어지게 테스트)
            for i in range(1074): 
                f.write(struct.pack('B', i % 256))
                
    send_firmware(fw_filename)