import can
import time
import struct

# --- 설정 ---
BUS_INTERFACE = 'can0' # 또는 can1
TARGET_ID     = 0x100  # 비글본 -> STM32
RESPONSE_ID   = 0x101  # STM32 -> 비글본
CMD_FW_START  = 0x10   # Erase 명령

def test_erase():
    # 1. CAN 연결
    try:
        bus = can.interface.Bus(channel=BUS_INTERFACE, bustype='socketcan')
        print(f"Connected to {BUS_INTERFACE}")
    except Exception as e:
        print(f"CAN Init Fail: {e}")
        return

    # 2. 패킷 생성: [CMD(0x10)] + [Padding(3byte)] + [Size(4byte)]
    # 테스트용으로 1024 바이트(1KB)만 지운다고 가정
    dummy_size = 1024 
    cmd_packet = struct.pack('<B3xI', CMD_FW_START, dummy_size)
    
    msg = can.Message(arbitration_id=TARGET_ID, data=list(cmd_packet), is_extended_id=True)
    
    print("Sending ERASE Command...")
    bus.send(msg)

    # 3. ACK 대기 (지우는 시간 고려하여 5초 대기)
    print("Waiting for ACK (This may take a few seconds)...")
    start_time = time.time()
    
    while (time.time() - start_time) < 5.0:
        rx_msg = bus.recv(timeout=0.1)
        
        if rx_msg and rx_msg.arbitration_id == RESPONSE_ID:
            # 응답 확인: [CMD, RESULT]
            if rx_msg.data[0] == CMD_FW_START:
                if rx_msg.data[1] == 0:
                    print("\n[SUCCESS] Flash Erase OK! (ACK Received)")
                    return
                else:
                    print(f"\n[FAIL] STM32 Error Code: {rx_msg.data[1]}")
                    return
    
    print("\n[TIMEOUT] No ACK received. Check connection or STM32 status.")

if __name__ == "__main__":
    test_erase()
    