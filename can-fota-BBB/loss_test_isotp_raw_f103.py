import sys
import time
import struct
import random
import zlib
import argparse
import socket
import os
import csv
from datetime import datetime

# 설정
CAN_INTERFACE = 'can0'
BITRATE = 500000

# CAN ID 설정 
CAN_ID_CMD  = 0x7E0   # PC -> STM32
CAN_ID_RESP = 0x7E8   # STM32 -> PC

# FOTA 명령어
CMD_FW_START      = 0x10
CMD_FW_DATA       = 0x20
CMD_FW_END        = 0x30
CMD_FW_JUMP_TO_FW = 0x40

total_frames_sent = 0
total_frames_received = 0
retransmitted_frames = 0
total_transmission_time = 0.0

CAN_ID_FOTA_REQUEST = 0x200  # App FW에게 FOTA 진입 요청

# 로그 파일 경로
LOG_DIR     = os.path.dirname(os.path.abspath(__file__))
CSV_PATH    = os.path.join(LOG_DIR, "fota_results.csv")
TEXT_LOG    = os.path.join(LOG_DIR, "fota_results.log")
CSV_HEADERS = [
    "timestamp", "protocol", "loss_rate_pct", "trial",
    "fw_size_bytes", "total_time_sec",
    "tx_frames", "rx_frames", "total_frames",
    "retransmit_frames", "overhead_pct", "status"
]

# argparse는 __main__에서 파싱하지만, 글로벌 초기값 설정
LOSS_RATE      = 0.0
TARGET_SIZE_KB = 64
TRIAL_NUM      = 1
PROTOCOL_NAME  = "RAW_ISO-TP"

def save_result(fw_size, total_time, tx, rx, retx, status="OK"):
    """결과를 CSV와 텍스트 로그 파일에 저장한다."""
    overhead_pct = (retx / tx * 100) if tx > 0 else 0.0
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    row = {
        "timestamp":         ts,
        "protocol":          PROTOCOL_NAME,
        "loss_rate_pct":     f"{LOSS_RATE * 100:.5f}",
        "trial":             TRIAL_NUM,
        "fw_size_bytes":     fw_size,
        "total_time_sec":    f"{total_time:.3f}",
        "tx_frames":         tx,
        "rx_frames":         rx,
        "total_frames":      tx + rx,
        "retransmit_frames": retx,
        "overhead_pct":      f"{overhead_pct:.2f}",
        "status":            status,
    }

    file_exists = os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

    with open(TEXT_LOG, "a") as f:
        f.write(f"\n{'='*53}\n")
        f.write(f"  [{ts}] {PROTOCOL_NAME} - Trial {TRIAL_NUM}\n")
        f.write(f"{'='*53}\n")
        f.write(f"  Loss Rate    : {LOSS_RATE*100:.2f}%\n")
        f.write(f"  FW Size      : {fw_size} bytes\n")
        f.write(f"  Total Time   : {total_time:.3f} sec\n")
        f.write(f"  TX Frames    : {tx}\n")
        f.write(f"  RX Frames    : {rx}\n")
        f.write(f"  Total Frames : {tx + rx}\n")
        f.write(f"  Retransmit   : {retx} frames ({overhead_pct:.2f}% overhead)\n")
        f.write(f"  Status       : {status}\n")

    print(f"[LOG] 결과 저장 완료 → {CSV_PATH}")

def build_can_frame(can_id, data_bytes):
    # 8바이트 고정 길이 CAN 페이로드 패딩
    data_padded = data_bytes + b'\x00' * (8 - len(data_bytes))
    return struct.pack("<IB3x8s", can_id, len(data_bytes), data_padded)

def send_frame_with_enobufs(bus, payload):
    frame = build_can_frame(CAN_ID_CMD, payload)
    while True:
        try:
            bus.send(frame)
            break
        except OSError as e:
            if getattr(e, 'errno', None) == 105: # ENOBUFS
                time.sleep(0.0005)
            else:
                raise

def flush_rx_buffer(bus):
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
    flush_rx_buffer(bus)  # 리셋 전 수신된 스토일 데이터 제거
    print("[FOTA] 부트로더 준비 완료. FOTA 시작!")

def wait_sf_ack(bus, expected_cmd, timeout=3.0):
    global total_frames_received
    bus.settimeout(timeout)
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            frame = bus.recv(16)
            if len(frame) == 16:
                rx_id, rx_dlc, rx_data = struct.unpack("<IB3x8s", frame)
                rx_id &= 0x7FF 
                if rx_id == CAN_ID_RESP:
                    total_frames_received += 1
                    # Single Frame 파싱 (0x00 ~ 0x07)
                    if (rx_data[0] & 0xF0) == 0x00:
                        sf_len = rx_data[0] & 0x0F
                        if sf_len >= 2 and rx_data[1] == expected_cmd:
                            return rx_data[1:1+sf_len]
        except socket.timeout:
            return None
        except BlockingIOError:
            pass
    return None

def raw_isotp_send_chunk(bus, payload, loss_rate):
    global total_frames_sent, total_frames_received
    payload_len = len(payload)
    
    # 1. First Frame (FF) 전송
    ff_data = bytearray(8)
    ff_data[0] = 0x10 | ((payload_len >> 8) & 0x0F)
    ff_data[1] = payload_len & 0xFF
    ff_data[2:8] = payload[0:6]
    
    send_frame_with_enobufs(bus, ff_data)
    total_frames_sent += 1
    
    # 2. Flow Control (FC) 대기 (1회 왕복 딜레이 발생 포인트)
    fc_received = False
    stmin_ms = 0
    bus.settimeout(1.0)
    start_time = time.time()
    while time.time() - start_time < 1.0:
        try:
            frame = bus.recv(16)
            if len(frame) == 16:
                rx_id, rx_dlc, rx_data = struct.unpack("<IB3x8s", frame)
                rx_id &= 0x7FF 
                if rx_id == CAN_ID_RESP:
                    total_frames_received += 1
                    if (rx_data[0] & 0xF0) == 0x30:
                        stmin_ms = rx_data[2]
                        if stmin_ms >= 0xF1 and stmin_ms <= 0xF9:
                            stmin_ms = (stmin_ms - 0xF0) * 0.1 # 100us 단위
                        elif stmin_ms > 0x7F:
                            stmin_ms = 0
                        fc_received = True
                        break
        except socket.timeout:
            break
        except BlockingIOError:
            pass
    
    if not fc_received:
        return False
        
    # 3. Consecutive Frames (CF) 풀악셀 전송
    seq = 1
    idx = 6
    while idx < payload_len:
        cf_len = min(7, payload_len - idx)
        cf_data = bytearray(8)
        cf_data[0] = 0x20 | (seq & 0x0F)
        cf_data[1:1+cf_len] = payload[idx:idx+cf_len]
        
        # 패킷 고의 유실
        if loss_rate > 0 and random.random() < loss_rate:
            idx += cf_len
            seq = (seq + 1) & 0x0F
            continue
            
        send_frame_with_enobufs(bus, cf_data)
        if stmin_ms > 0:
            time.sleep(stmin_ms / 1000.0)
            
        total_frames_sent += 1
        idx += cf_len
        seq = (seq + 1) & 0x0F
        
    return True

def start_can_fota(firmware_path):
    global total_frames_sent, retransmitted_frames, total_transmission_time, total_frames_received
    
    try:
        # 🚨 [하드웨어 시뮬레이션 완벽 통제] python-can을 버리고 Pure Raw SocketCAN 적용!
        bus = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
        bus.bind((CAN_INTERFACE,))
    except Exception as e:
        print(f"[CAN] 소켓 초기화 실패: {e}")
        return

    # App FW에 FOTA 진입 신호 전송 후 부트로더 대기
    trigger_fota_entry(bus)

    with open(firmware_path, "rb") as f:
        fw_data = f.read()
        
    if TARGET_SIZE_KB > 0:
        target_bytes = TARGET_SIZE_KB * 1024
        if len(fw_data) < target_bytes:
            padding_len = target_bytes - len(fw_data)
            fw_data += bytes((i % 256) for i in range(padding_len))
            print(f"[CAN] 테스트용 패턴 패딩 완료: {TARGET_SIZE_KB}KB 로 확장됨")
            
    fw_size = len(fw_data)
    print(f"[CAN] 전송할 펌웨어 크기: {fw_size} bytes")
    print(f"[CAN] RAW ISO-TP 측정 시작 (Pure SocketCAN 최적화 적용) (Packet Loss: {LOSS_RATE*100}%)")

    fota_start_time = time.time()
    flush_rx_buffer(bus)
    
    # 3. [Start] 명령 전송 (Single Frame)
    sf_data = bytearray(8)
    sf_data[0] = 0x05
    sf_data[1] = CMD_FW_START
    sf_data[2:6] = struct.pack('<I', fw_size)
    
    send_frame_with_enobufs(bus, sf_data)
    total_frames_sent += 1
    
    rx_payload = wait_sf_ack(bus, CMD_FW_START, timeout=15.0)
    if not rx_payload:
        print("[CAN] Error: Start ACK Timeout")
        return
        
    if len(rx_payload) >= 4:
        chunk_size = rx_payload[2] | (rx_payload[3] << 8)
    else:
        chunk_size = 256
        
    # 4. [Data] 데이터 전송 (ISO-TP Pipelining)
    for i in range(0, fw_size, chunk_size):
        chunk = fw_data[i : i + chunk_size]
        payload = bytes([CMD_FW_DATA]) + chunk
        
        retry_count = 0
        success = False
        # 재전송 실패 기준 제거: 실제 UDS처럼 성공할 때까지 계속 재시도
        # (공정한 비교 기준: 재전송 횟수/오버헤드를 측정하되 FAIL은 없음)
        MAX_RETRIES = 50  # 무한루프 방지용 안전장치
        while not success and retry_count < MAX_RETRIES:
            if retry_count > 0:
                print(f"\n[CAN] Block {i//chunk_size} 재전송 #{retry_count} (ISO-TP Go-Back-N: 256B 블록 전체)")
                # 블록 전체 재전송 비용 가산 (FF 1 + 모든 CF)
                retransmitted_frames += ((len(payload) + 6) // 7)
                
            flush_rx_buffer(bus)
            if raw_isotp_send_chunk(bus, payload, LOSS_RATE):
                # 최신 OEM 권장 규격(N_Cr ~ 150ms) 적용
                ack = wait_sf_ack(bus, CMD_FW_DATA, timeout=0.15)
                if ack and ack[1] == 0:  # BOOT_OK
                    success = True
                    break
            retry_count += 1
            
        if not success:
            print(f"\n[CAN] 경고: Block {i//chunk_size} {MAX_RETRIES}회 재시도 후에도 실패. 계속 진행.")
            save_result(fw_size, time.time() - fota_start_time, total_frames_sent, total_frames_received, retransmitted_frames, status="FAIL")
            return


        idx = min(i + chunk_size, fw_size)
        print(f"\r[CAN] 진행률: {idx}/{fw_size} bytes ({(idx/fw_size)*100:.1f}%)", end='', flush=True)

    print("\n\n[CAN] 데이터 전송 완료")
    # 5. [End] 명령 전송
    fw_crc32 = zlib.crc32(fw_data) & 0xFFFFFFFF
    sf_data = bytearray(8)
    sf_data[0] = 0x05
    sf_data[1] = CMD_FW_END
    sf_data[2:6] = struct.pack('<I', fw_crc32)
    
    send_frame_with_enobufs(bus, sf_data)
    total_frames_sent += 1
    
    ack = wait_sf_ack(bus, CMD_FW_END, timeout=3.0)
    if ack and ack[1] == 0:
        print("[CAN] 펌웨어 무결성 최종 통과! (CRC Validated) ✅")
    else:
        print("[CAN] CRC 검증 실패")
        return

    # 6. [Jump] 명령 전송
    time.sleep(0.5)
    sf_data = bytearray(8)
    sf_data[0] = 0x02   # length 2
    sf_data[1] = CMD_FW_JUMP_TO_FW
    sf_data[2] = 0x00
    
    send_frame_with_enobufs(bus, sf_data)
    print("[CAN] JUMP 명령 전송 완료.")

    total_transmission_time = time.time() - fota_start_time
    overhead_pct = (retransmitted_frames / total_frames_sent) * 100 if total_frames_sent > 0 else 0
    
    print(f"=============================================")
    time.sleep(0.05)
    print(f"[RESULT] 총 소요 시간 (Loss {LOSS_RATE*100}%): {total_transmission_time:.2f} 초")
    time.sleep(0.05)
    print(f"[RESULT] 송신 프레임 (TX): {total_frames_sent} 프레임")
    time.sleep(0.05)
    print(f"[RESULT] 수신 프레임 (RX): {total_frames_received} 프레임")
    time.sleep(0.05)
    print(f"[RESULT] 총 통신 프레임 (TX+RX 합산): {total_frames_sent + total_frames_received} 프레임")
    time.sleep(0.05)
    print(f"[RESULT] 트래픽 오버헤드: 재전송 {retransmitted_frames} 프레임 ({overhead_pct:.2f}% 통신 낭비)")
    time.sleep(0.05)
    print(f"=============================================")

    # 결과 저장 (CSV + 로그)
    save_result(fw_size, total_transmission_time, total_frames_sent, total_frames_received, retransmitted_frames, status="OK")

if __name__ == "__main__":
    # CAN 하드웨어 소켓 초기화(Bitrate 500,000)
    os.system("sudo ip link set can0 down 2>/dev/null")
    os.system("sudo ip link set can0 up type can bitrate 500000 2>/dev/null")

    parser = argparse.ArgumentParser(description='RAW ISO-TP CAN FOTA Loss Test')
    parser.add_argument('--loss',     type=float, default=0.0,        help='Packet Loss Rate (0.0~1.0)')
    parser.add_argument('--size_kb',  type=int,   default=64,         help='Target firmware size in KB (padding)')
    parser.add_argument('--trial',    type=int,   default=1,          help='Trial number (for logging)')
    parser.add_argument('--protocol', type=str,   default='RAW_ISO-TP', help='Protocol name (for logging)')
    args = parser.parse_args()
    
    LOSS_RATE      = args.loss
    TARGET_SIZE_KB = args.size_kb
    TRIAL_NUM      = args.trial
    PROTOCOL_NAME  = args.protocol
    SAVE_PATH = "received_fw.bin"

    if not os.path.exists(SAVE_PATH):
        print(f"[WARN] {SAVE_PATH} 파일이 없습니다. Fake FOTA를 위해 최소 1회 기존 스크립트를 실행해 다운로드해주세요.")
        sys.exit(1)

    start_can_fota(SAVE_PATH)
