import os
import time
import struct
import socket
import urllib.request
import ssl
import zlib
import random
import argparse
import csv
from datetime import datetime

parser = argparse.ArgumentParser(description="Custom CAN FOTA Gateway")
parser.add_argument('--loss',     type=float, default=0.0,      help='Packet loss rate (0.0~1.0)')
parser.add_argument('--size_kb',  type=int,   default=0,        help='Pad firmware to target size in KB')
parser.add_argument('--trial',    type=int,   default=1,        help='Trial number (for logging)')
parser.add_argument('--protocol', type=str,   default='Custom', help='Protocol name (for logging)')
args = parser.parse_args()
LOSS_RATE      = args.loss
TARGET_SIZE_KB = args.size_kb
TRIAL_NUM      = args.trial
PROTOCOL_NAME  = args.protocol

LOG_DIR      = os.path.dirname(os.path.abspath(__file__))
CSV_PATH     = os.path.join(LOG_DIR, "fota_results.csv")
TEXT_LOG     = os.path.join(LOG_DIR, "fota_results.log")
CSV_HEADERS  = [
    "timestamp", "protocol", "loss_rate_pct", "trial",
    "fw_size_bytes", "total_time_sec",
    "tx_frames", "rx_frames", "total_frames",
    "retransmit_frames", "overhead_pct", "status"
]

def save_result(fw_size, total_time, tx, rx, retx, status="OK"):
    """결과를 CSV와 텍스트 로그 파일에 저장한다."""
    overhead_pct = (retx / tx * 100) if tx > 0 else 0.0
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    row = {
        "timestamp":       ts,
        "protocol":        PROTOCOL_NAME,
        "loss_rate_pct":   f"{LOSS_RATE * 100:.5f}",
        "trial":           TRIAL_NUM,
        "fw_size_bytes":   fw_size,
        "total_time_sec":  f"{total_time:.3f}",
        "tx_frames":       tx,
        "rx_frames":       rx,
        "total_frames":    tx + rx,
        "retransmit_frames": retx,
        "overhead_pct":    f"{overhead_pct:.2f}",
        "status":          status,
    }

    # CSV 저장 (헤더는 파일이 없을 때만 작성)
    file_exists = os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

    # 가독성 텍스트 로그 저장
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

# ==========================================
# 1. 설정 및 커스텀 프로토콜 매크로
# ==========================================
FW_URL            = "https://unbarreled-alayna-eustatic.ngrok-free.dev/boot_can_fw.bin"
SAVE_PATH         = "received_fw.bin"

CAN_ID_RESP       = 0x101 
CAN_ID_CMD        = 0x100 

# [Host -> Target] 명령어 (상위 2비트)
CMD_RX_DATA  = 0x00
CMD_RX_START = 0x01
CMD_RX_END   = 0x02
CMD_RX_JUMP  = 0x03

# [Target -> Host] 응답 코드 (상위 2비트)
CMD_TX_ACK  = 0x00
CMD_TX_NACK = 0x01
CMD_TX_ERR  = 0x02

def pack_header(cmd, seq):
    return ((cmd & 0x03) << 6) | (seq & 0x3F)

# ==========================================
# 2. LTE 다운로드 
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
# 3. SocketCAN 통신 (비트맵 NACK 적용)
# ==========================================
CAN_ID_FOTA_REQUEST = 0x200  # App FW에게 FOTA 진입 요청

def build_can_frame(can_id, data_list):
    data_bytes = bytes(data_list)
    # 8바이트 고정 길이 CAN 페이로드 패딩
    data_padded = data_bytes + b'\x00' * (8 - len(data_bytes))
    # DLC (Data Length Code)는 실제 data_list 길이
    return struct.pack("<IB3x8s", can_id, len(data_bytes), data_padded)

def wait_response(bus, timeout=2.0):
    bus.settimeout(timeout)
    start_time = time.time()
    while (time.time() - start_time) < timeout:
        try:
            frame = bus.recv(16)
            if len(frame) == 16:
                rx_id, rx_dlc, rx_data = struct.unpack("<IB3x8s", frame)
                rx_id &= 0x7FF 
                
                if rx_id == CAN_ID_RESP:
                    header = rx_data[0]
                    cmd = (header >> 6) & 0x03
                    
                    if cmd == CMD_TX_ACK or cmd == CMD_TX_ERR:
                        result = header & 0x3F # 상태 코드는 시퀀스 6자리에 들어옴
                        return (cmd, result)
                        
                    elif cmd == CMD_TX_NACK:
                        # ⚡ 비트맵 NACK 수신: Data[1]~Data[7]까지의 56비트 읽기 (O(1))
                        nack_map = 0
                        for i in range(1, 8):
                            nack_map |= (rx_data[i] << (8 * (i - 1)))
                        return (cmd, nack_map)
                        
        except socket.timeout:
            return None
        except BlockingIOError:
            pass
    return None

def _flush_rx(bus):
    """RX 버퍼에 난은 스토일 데이터륿이다."""
    bus.settimeout(0.0)
    flushed = 0
    while True:
        try:
            bus.recv(16)
            flushed += 1
        except BlockingIOError:
            break
        except Exception:
            break
    if flushed:
        print(f"[FOTA] 스토일 RX 데이터 {flushed}개 폐기")

def trigger_fota_entry(bus):
    """App FW에 FOTA 진입 신호(CAN 0x200)를 보내고 부트로더 진입을 기다린다."""
    print("[FOTA] STM32 App FW에 FOTA 진입 신호 전송 중... (CAN ID=0x200)")
    trigger_frame = build_can_frame(CAN_ID_FOTA_REQUEST, [0xDE, 0xAD])
    bus.send(trigger_frame)
    print("[FOTA] 신호 전송 완료. 부트로더 진입 대기 중... (3.0초)")
    time.sleep(3.0)  # STM32 소프트 리셋 + HAL 초기화 + CAN 재동기화 대기
    _flush_rx(bus)    # 리셋 전 수신된 스토일 데이터 제거
    print("[FOTA] 부트로더 준비 완료. FOTA 시작!")

def start_can_fota(firmware_path):
    print(f"=============================================")
    print(f"[CAN] 비트맵 NACK 적용 FOTA Gateway 시작!")
    print(f"=============================================")
    try:
        bus = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
        bus.bind(('can0',))
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
            print(f"[CAN] 테스트용 패턴(0x00~0xFF) 패딩 완료: {TARGET_SIZE_KB}KB 로 확장됨")
            
    fw_size = len(fw_data)
    print(f"[CAN] 전송할 펌웨어 크기: {fw_size} bytes")
    print(f"[CAN] 측정 시작 (Packet Loss: {LOSS_RATE*100}%)")

    fota_start_time = time.time()

    # -------------------------------------------------------------
    # 1. START 전송 (Erase 명령)
    # -------------------------------------------------------------
    total_tx_frames = 1       # CMD_START 전송분 미리 초기화
    total_rx_frames = 0
    retransmitted_frames = 0

    payload_start = [pack_header(CMD_RX_START, 0)] + list(fw_size.to_bytes(4, byteorder='little'))
    bus.send(build_can_frame(CAN_ID_CMD, payload_start))
    print("[CAN] CMD_RX_START 전송 (Flash 지우기 대기 중... ⏳)")
    
    resp = wait_response(bus, timeout=10.0) # Erase는 최대 10초 대기
    if not resp or resp[0] != CMD_TX_ACK:
        print(f"[CAN] Error: Erase ACK 실패. 응답: {resp}")
        save_result(fw_size, time.time() - fota_start_time, total_tx_frames, total_rx_frames, retransmitted_frames, status="FAIL_ERASE")
        return
    total_rx_frames = 1  # Erase ACK 수신 카운트
    print("[CAN] Erase 완료! 본격 데이터 전송 시작 🚀")

    # -------------------------------------------------------------
    # 2. DATA 전송 (256B 블록 + 비트맵 NACK 파이프라이닝 복구)
    # -------------------------------------------------------------
    idx = 0
    total_size = len(fw_data)

    while idx < total_size:
        block_data = fw_data[idx : idx + 256]
        frames = []
        
        # 블록 내에서 헤더와 7바이트 데이터 분할
        for seq in range(0, len(block_data), 7):
            chunk = block_data[seq : seq + 7]
            seq_num = seq // 7
            header = pack_header(CMD_RX_DATA, seq_num)
            payload = [header] + list(chunk)
            frames.append((seq_num, payload))
            
        expected_frames = len(frames)
        
        # 블록 일괄 풀악셀 전송
        for seq_num, payload in frames:
            total_tx_frames += 1
            if LOSS_RATE > 0 and random.random() < LOSS_RATE:
                # 패킷 고의 드랍
                continue
            # SocketCAN 큐 오버플로우(ENOBUFS) 발생 시 공간이 날 때까지 대기 (진정한 하드웨어 풀스피드 전송)
            while True:
                try:
                    bus.send(build_can_frame(CAN_ID_CMD, payload))
                    break
                except OSError as getattr_err:
                    if getattr(getattr_err, 'errno', None) == 105: # No buffer space available
                        time.sleep(0.0005)
                    else:
                        raise

        # 블록 수신 무결성 대기 (비트맵 NACK 처리 구조)
        while True:
            # 2. STM32의 수신 결과(ACK/NACK) 대기 (꼬리 프레임 유실 대비 타임아웃 150ms 적용)
            response = wait_response(bus, timeout=0.15)
            if response:
                total_rx_frames += 1
            
            # 🚨 타임아웃 발생 시, 체커 프레임 재전송 구조 
            # (만약 노이즈때문에 꼬리 프레임 자체가 날아가서 STM32가 끝나지 않았을 경우 구출)
            if not response:
                print("\n[CAN Warning] 응답 타임아웃! 꼬리 프레임 단독 송출하여 NACK 검사 트리거!")
                last_seq = expected_frames - 1
                bus.send(build_can_frame(CAN_ID_CMD, frames[last_seq][1]))
                total_tx_frames += 1
                retransmitted_frames += 1
                continue
                
            cmd, args = response
            
            # 🟢 전체 무결성 수신 (블록 쓰기 성공)
            if cmd == CMD_TX_ACK:
                idx += len(block_data)
                print(f"\r[CAN] 진행률: {idx}/{total_size} bytes ({(idx/total_size)*100:.1f}%)", end='', flush=True)
                break
                
            # 🟠 일부 유실 프레임 발생 (비트맵 O(M) 부분 복구)
            elif cmd == CMD_TX_NACK:
                nack_map = args
                missing_seqs = []
                # 64비트 지도(Map)에서 불이 꺼진(0) 빈자리 찾기
                for seq_num in range(expected_frames):
                    if (nack_map & (1 << seq_num)) == 0:
                        missing_seqs.append(seq_num)
                
                print(f"\n[CAN Recovery] NACK 비트맵 수신! 손실 프레임 {len(missing_seqs)}개. 파이프라인 묶음 재전송 실행!")
                
                # 딱 누락된 프레임 M개만 골라서 역송출
                for seq_num in missing_seqs:
                    total_tx_frames += 1
                    retransmitted_frames += 1
                    if LOSS_RATE > 0 and random.random() < LOSS_RATE:
                        continue
                    while True:
                        try:
                            bus.send(build_can_frame(CAN_ID_CMD, frames[seq_num][1]))
                            break
                        except OSError as getattr_err:
                            if getattr(getattr_err, 'errno', None) == 105:
                                time.sleep(0.0005)
                            else:
                                raise
                    
            # 🔴 치명적 에러 발생
            elif cmd == CMD_TX_ERR:
                print(f"\n[CAN Error] 타겟 보드 치명적 에러! 코드: {args}")
                save_result(fw_size, time.time() - fota_start_time, total_tx_frames, total_rx_frames, retransmitted_frames, status="FAIL_ERR")
                return

    print("\n[CAN] 펌웨어 전체 데이터 전송 완료!")

    # -------------------------------------------------------------
    # 3. END 전송 (최종 CRC 무결성 점검)
    # -------------------------------------------------------------
    print("[CAN] 전체 펌웨어 CRC32 로컬 계산 및 비교 전송 중...")
    fw_crc32 = zlib.crc32(fw_data) & 0xFFFFFFFF
    payload_end = [pack_header(CMD_RX_END, 0)] + list(fw_crc32.to_bytes(4, byteorder='little'))
    bus.send(build_can_frame(CAN_ID_CMD, payload_end))
    
    resp = wait_response(bus, timeout=3.0)
    if not resp or resp[0] != CMD_TX_ACK:
        print(f"[CAN] Error: CRC 불일치 또는 End 응답 실패! (벽돌 방지 활성화) 응답: {resp}")
        elapsed = time.time() - fota_start_time
        save_result(fw_size, elapsed, total_tx_frames, total_rx_frames, retransmitted_frames, status="FAIL_CRC")
        return
    total_tx_frames += 1  # END 전송분 포함
    total_rx_frames += 1  # END ACK 수신 카운트
    
    fota_end_time = time.time()
    total_time = fota_end_time - fota_start_time
    overhead_pct = (retransmitted_frames / total_tx_frames) * 100 if total_tx_frames > 0 else 0
    
    print(f"[CAN] 펌웨어 무결성 최종 통과! (CRC Validated) ✅")
    print(f"=============================================")
    print(f"[RESULT] 총 소요 시간 (Loss {LOSS_RATE*100}%): {total_time:.2f} 초")
    print(f"[RESULT] 송신 프레임 (TX): {total_tx_frames} 프레임")
    print(f"[RESULT] 수신 프레임 (RX): {total_rx_frames} 프레임")
    print(f"[RESULT] 총 통신 프레임 (TX+RX 합산): {total_tx_frames + total_rx_frames} 프레임")
    print(f"[RESULT] 트래픽 오버헤드: 재전송 {retransmitted_frames} 프레임 ({overhead_pct:.2f}% 통신 낭비)")
    print(f"=============================================")

    # 결과 저장 (CSV + 로그)
    save_result(fw_size, total_time, total_tx_frames, total_rx_frames, retransmitted_frames, status="OK")

    # -------------------------------------------------------------
    # 4. Jump 명령
    # -------------------------------------------------------------
    time.sleep(0.5)
    payload_jump = [pack_header(CMD_RX_JUMP, 0)]
    bus.send(build_can_frame(CAN_ID_CMD, payload_jump))
    total_tx_frames += 1 # JUMP 전송분
    print("[CAN] JUMP 명령 전송 완료. 디바이스 재부팅 확인 요망!")

if __name__ == '__main__':
    # CAN 하드웨어 소켓 초기화(Bitrate 1,000,000)
    os.system("sudo ip link set can0 down 2>/dev/null")
    os.system("sudo ip link set can0 up type can bitrate 1000000 2>/dev/null")
    
    if os.path.exists(SAVE_PATH):
        print(f"[TEST] 로컬 파일 사용 중 ({SAVE_PATH}) - LTE 다운로드 생략")
        start_can_fota(SAVE_PATH)
    elif download_firmware_via_lte(FW_URL, SAVE_PATH):
        start_can_fota(SAVE_PATH)
    else:
        print("[System] 펌웨어 다운로드 실패 및 로컬 파일 없음. 종료합니다.")