import os
import time
import struct
import socket
import urllib.request
import ssl
import zlib
import sys

# ==========================================
# FOTA 서버 및 CAN 설정
# ==========================================
FW_URL            = "https://unbarreled-alayna-eustatic.ngrok-free.dev/boot_can_fw_f103.bin"
SAVE_PATH         = "received_fw.bin"

CMD_FW_START      = 0x10
CMD_FW_DATA       = 0x20
CMD_FW_END        = 0x30
CMD_FW_JUMP_TO_FW = 0x40

# CAN ID 설정 (ISO-TP)
CAN_ID_RESP         = 0x7E8  # MCU -> PC
CAN_ID_CMD          = 0x7E0  # PC -> MCU
CAN_ID_FOTA_REQUEST = 0x200  # App FW에게 FOTA 진입 요청

# ==========================================
# 유틸리티
# ==========================================
def build_can_frame(can_id, data_bytes):
    data_padded = data_bytes + b'\x00' * (8 - len(data_bytes))
    return struct.pack("<IB3x8s", can_id, len(data_bytes), data_padded)

def send_frame_with_enobufs(bus, payload):
    """ENOBUFS(SocketCAN 커널 큐 포화) 발생 시 재시도하며 전송한다."""
    frame = build_can_frame(CAN_ID_CMD, payload)
    while True:
        try:
            bus.send(frame)
            break
        except OSError as e:
            if getattr(e, 'errno', None) == 105:  # ENOBUFS
                time.sleep(0.0005)
            else:
                raise

def flush_rx_buffer(bus):
    """RX 버퍼에 남은 스테일 데이터를 제거한다."""
    bus.settimeout(0.0)
    while True:
        try:
            bus.recv(16)
        except BlockingIOError:
            break
        except Exception:
            break

def trigger_fota_entry(bus):
    """App FW에 FOTA 진입 신호(CAN 0x200)를 보내고 부트로더 진입을 기다린다."""
    print("[FOTA] STM32 App FW에 FOTA 진입 신호 전송 중... (CAN ID=0x200)")
    frame = build_can_frame(CAN_ID_FOTA_REQUEST, bytes([0xDE, 0xAD]))
    bus.send(frame)
    print("[FOTA] 신호 전송 완료. 부트로더 진입 대기 중... (3.0초)")
    time.sleep(3.0)  # STM32 소프트 리셋 + HAL 초기화 + CAN 재동기화 대기
    flush_rx_buffer(bus)
    print("[FOTA] 부트로더 준비 완료. FOTA 시작!")

# ==========================================
# LTE 다운로드
# ==========================================
def download_firmware_via_lte(url, save_path):
    print(f"=============================================")
    print(f" [LTE] FOTA 다운로드 시작 (서버 접속 중...)")
    print(f" URL: {url}")
    print(f"=============================================")
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            fw_data = response.read()
            with open(save_path, "wb") as f:
                f.write(fw_data)

        print(f"[LTE] 펌웨어 다운로드 완료! 크기: {len(fw_data)} bytes\n")
        return True
    except Exception as e:
        print(f"[LTE Error] 다운로드 실패: {e}")
        return False

# ==========================================
# ISO-TP 응답 대기 (Raw SocketCAN, Single Frame 파싱)
# ==========================================
def wait_sf_ack(bus, expected_cmd, timeout=3.0):
    bus.settimeout(timeout)
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            frame = bus.recv(16)
            if len(frame) == 16:
                rx_id, rx_dlc, rx_data = struct.unpack("<IB3x8s", frame)
                rx_id &= 0x7FF
                if rx_id == CAN_ID_RESP:
                    # Single Frame 파싱 (PCI: 0x0N)
                    if (rx_data[0] & 0xF0) == 0x00:
                        sf_len = rx_data[0] & 0x0F
                        if sf_len >= 2 and rx_data[1] == expected_cmd:
                            return rx_data[1:1 + sf_len]
        except socket.timeout:
            return None
        except BlockingIOError:
            pass
    return None

# ==========================================
# Raw ISO-TP 청크 전송 (FF + FC대기 + CFs)
# ==========================================
def raw_isotp_send_chunk(bus, payload):
    payload_len = len(payload)

    # 1. First Frame (FF)
    ff_data = bytearray(8)
    ff_data[0] = 0x10 | ((payload_len >> 8) & 0x0F)
    ff_data[1] = payload_len & 0xFF
    ff_data[2:8] = payload[0:6]
    send_frame_with_enobufs(bus, ff_data)

    # 2. Flow Control (FC) 대기
    fc_received = False
    stmin_sec = 0.0  # 파싱할 STmin
    bus.settimeout(1.0)
    start_time = time.time()
    while time.time() - start_time < 1.0:
        try:
            frame = bus.recv(16)
            if len(frame) == 16:
                rx_id, rx_dlc, rx_data = struct.unpack("<IB3x8s", frame)
                rx_id &= 0x7FF
                if rx_id == CAN_ID_RESP and (rx_data[0] & 0xF0) == 0x30:
                    fc_received = True
                    
                    # ISO-TP STmin 파싱 (Data[2])
                    stmin_val = rx_data[2]
                    if stmin_val <= 0x7F:
                        stmin_sec = stmin_val / 1000.0  # 0~127 ms
                    elif 0xF1 <= stmin_val <= 0xF9:
                        stmin_sec = (stmin_val - 0xF0) / 10000.0  # 100~900 us (0.1ms ~ 0.9ms)
                    else:
                        stmin_sec = 0.127 # Reserve/Invalid -> max
                        
                    break
        except socket.timeout:
            break
        except BlockingIOError:
            pass

    if not fc_received:
        return False

    # 3. Consecutive Frames (CF) 전송 (STmin 준수)
    seq = 1
    idx = 6
    while idx < payload_len:
        cf_len = min(7, payload_len - idx)
        cf_data = bytearray(8)
        cf_data[0] = 0x20 | (seq & 0x0F)
        cf_data[1:1 + cf_len] = payload[idx:idx + cf_len]
        send_frame_with_enobufs(bus, cf_data)
        
        if stmin_sec > 0:
            # Linux time.sleep() is inaccurate for microseconds. Use a busy wait (spin loop)
            # for high precision STmin delays to prevent STM32 block timeouts.
            target = time.perf_counter() + stmin_sec
            while time.perf_counter() < target:
                pass
            
        idx += cf_len
        seq = (seq + 1) & 0x0F

    return True

# ==========================================
# ISO-TP FOTA 메인 전송 로직
# ==========================================
def start_can_fota(firmware_path):
    print(f"[CAN] ISO-TP FOTA Flashing 시작: {firmware_path}")

    try:
        # python-can 라이브러리 없이 Pure Raw SocketCAN 사용
        bus = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
        bus.bind(('can0',))
    except Exception as e:
        print(f"[CAN] 소켓 초기화 실패: {e}")
        return

    # App FW에 FOTA 진입 신호 전송 후 부트로더 대기
    trigger_fota_entry(bus)

    with open(firmware_path, "rb") as f:
        fw_data = f.read()

    fw_size = len(fw_data)
    print(f"[CAN] 전송할 펌웨어 크기: {fw_size} bytes")

    fota_start_time = time.time()
    total_tx_frames = 0
    total_rx_frames = 0
    retransmitted_frames = 0

    flush_rx_buffer(bus)

    # ----------------------------------------------------------
    # 1. START 명령 전송 (Single Frame)
    # ----------------------------------------------------------
    sf_data = bytearray(8)
    sf_data[0] = 0x05
    sf_data[1] = CMD_FW_START
    sf_data[2:6] = struct.pack('<I', fw_size)
    send_frame_with_enobufs(bus, sf_data)
    total_tx_frames += 1

    rx_payload = wait_sf_ack(bus, CMD_FW_START, timeout=15.0)
    if not rx_payload:
        print("[CAN] Error: Erase ACK Timeout")
        return
    total_rx_frames += 1

    if len(rx_payload) >= 4:
        chunk_size = rx_payload[2] | (rx_payload[3] << 8)
        print(f"[CAN] START 성공! STM32가 {chunk_size} bytes 단위로 보내라고 하네요.")
    else:
        chunk_size = 256
        print(f"[CAN] START 성공! (chunk_size 기본값 {chunk_size} 사용)")

    # ----------------------------------------------------------
    # 2. DATA 전송 (ISO-TP Framing, Go-Back-N 재전송)
    # ----------------------------------------------------------
    print("[CAN] Firmware Data 전송 중 (Raw ISO-TP)...")

    for i in range(0, fw_size, chunk_size):
        chunk = fw_data[i: i + chunk_size]
        payload = bytes([CMD_FW_DATA]) + chunk

        retry_count = 0
        success = False

        while retry_count < 3:
            if retry_count > 0:
                block_idx = i // chunk_size
                retx_frames = (len(payload) + 6) // 7
                print(f"\n[CAN] Block {block_idx} 재전송 (ISO-TP Go-Back-N, {retx_frames}프레임 통째로 재전송!)")
                retransmitted_frames += retx_frames
                flush_rx_buffer(bus)

            if raw_isotp_send_chunk(bus, payload):
                # OEM 권장 규격(N_Cr ~ 150ms) 적용
                ack = wait_sf_ack(bus, CMD_FW_DATA, timeout=0.15)
                if ack and ack[1] == 0:  # BOOT_OK
                    total_rx_frames += 1
                    success = True
                    break

            retry_count += 1

        if not success:
            print("\n[CAN] 치명적 에러: 지속적인 패킷 유실로 인해 STM32가 응답하지 않음.")
            return

        idx = min(i + chunk_size, fw_size)
        print(f"[CAN] 진행률: {idx}/{fw_size} bytes ({(idx/fw_size)*100:.1f}%)", flush=True)

    print("\n[CAN] 데이터 전송 완료")

    # ----------------------------------------------------------
    # 3. END 명령 전송 (CRC 검증)
    # ----------------------------------------------------------
    fw_crc32 = zlib.crc32(fw_data) & 0xFFFFFFFF
    sf_data = bytearray(8)
    sf_data[0] = 0x05
    sf_data[1] = CMD_FW_END
    sf_data[2:6] = struct.pack('<I', fw_crc32)
    send_frame_with_enobufs(bus, sf_data)
    total_tx_frames += 1

    ack = wait_sf_ack(bus, CMD_FW_END, timeout=5.0)
    if ack and ack[1] == 0:
        total_rx_frames += 1
        print("[CAN] 펌웨어 무결성 검증 통과 및 플래싱 완료! ✅")
    else:
        print("[CAN] ❌ Error: End ACK Fail (CRC 불일치 혹은 타임아웃)")
        return

    total_time = time.time() - fota_start_time
    overhead_pct = (retransmitted_frames / total_tx_frames * 100) if total_tx_frames > 0 else 0.0
    print(f"=============================================")
    print(f"[RESULT] 총 소요 시간: {total_time:.2f} 초")
    print(f"[RESULT] 송신 프레임 (TX): {total_tx_frames} 프레임")
    print(f"[RESULT] 수신 프레임 (RX): {total_rx_frames} 프레임")
    print(f"[RESULT] 재전송 프레임: {retransmitted_frames} 프레임 ({overhead_pct:.2f}% overhead)")
    print(f"=============================================")

    # ----------------------------------------------------------
    # 4. Jump 명령 전송
    # ----------------------------------------------------------
    time.sleep(0.5)
    sf_data = bytearray(8)
    sf_data[0] = 0x02
    sf_data[1] = CMD_FW_JUMP_TO_FW
    sf_data[2] = 0x00
    send_frame_with_enobufs(bus, sf_data)
    print("[CAN] JUMP 명령 전송 완료. 디바이스 재부팅 확인 요망!")

if __name__ == '__main__':
    os.system("sudo ip link set can0 down 2>/dev/null")
    os.system("sudo ip link set can0 up type can bitrate 500000 2>/dev/null")

    if len(sys.argv) > 1:
        local_path = sys.argv[1]
        print(f"[System] 대시보드에서 업로드된 파일({local_path})로 즉시 FOTA를 시작합니다.")
        start_can_fota(local_path)
    elif os.path.exists(SAVE_PATH):
        print(f"[TEST] 로컬 파일 사용 중 ({SAVE_PATH}) - LTE 다운로드 생략")
        start_can_fota(SAVE_PATH)
    elif download_firmware_via_lte(FW_URL, SAVE_PATH):
        start_can_fota(SAVE_PATH)
    else:
        print("[System] 다운로드 실패로 플래싱 절차 진입을 취소합니다.")
