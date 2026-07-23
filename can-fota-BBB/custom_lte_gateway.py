import os
import time
import struct
import socket
import urllib.request
import ssl
import zlib
import sys

# ==========================================
# 1. 설정 및 커스텀 프로토콜 매크로
# ==========================================
FW_URL            = "https://unbarreled-alayna-eustatic.ngrok-free.dev/boot_can_fw.bin"
SAVE_PATH         = "received_fw.bin"

CAN_ID_RESP         = 0x101
CAN_ID_CMD          = 0x100
CAN_ID_FOTA_REQUEST = 0x200  # App FW에게 FOTA 진입 요청

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
# 3. SocketCAN 유틸리티
# ==========================================
def build_can_frame(can_id, data_list):
    data_bytes = bytes(data_list)
    data_padded = data_bytes + b'\x00' * (8 - len(data_bytes))
    return struct.pack("<IB3x8s", can_id, len(data_bytes), data_padded)

def send_frame_with_enobufs(bus, frame):
    """ENOBUFS(SocketCAN 커널 큐 포화) 발생 시 재시도하며 전송한다."""
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
        print(f"[FOTA] 스테일 RX 데이터 {flushed}개 폐기")

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
                        result = header & 0x3F
                        return (cmd, result)

                    elif cmd == CMD_TX_NACK:
                        # 비트맵 NACK: Data[1]~Data[7]까지의 56비트 읽기
                        nack_map = 0
                        for i in range(1, 8):
                            nack_map |= (rx_data[i] << (8 * (i - 1)))
                        return (cmd, nack_map)

        except socket.timeout:
            return None
        except BlockingIOError:
            pass
    return None

def trigger_fota_entry(bus):
    """App FW에 FOTA 진입 신호(CAN 0x200)를 보내고 부트로더 진입을 기다린다."""
    print("[FOTA] STM32 App FW에 FOTA 진입 신호 전송 중... (CAN ID=0x200)")
    trigger_frame = build_can_frame(CAN_ID_FOTA_REQUEST, [0xDE, 0xAD])
    bus.send(trigger_frame)
    print("[FOTA] 신호 전송 완료. 부트로더 진입 대기 중... (3.0초)")
    time.sleep(3.0)  # STM32 소프트 리셋 + HAL 초기화 + CAN 재동기화 대기
    flush_rx_buffer(bus)
    print("[FOTA] 부트로더 준비 완료. FOTA 시작!")

# ==========================================
# 4. Custom FOTA 메인 전송 로직
# ==========================================
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

    fw_size = len(fw_data)
    print(f"[CAN] 전송할 펌웨어 크기: {fw_size} bytes")

    fota_start_time = time.time()
    total_tx_frames = 0
    total_rx_frames = 0
    retransmitted_frames = 0

    # ----------------------------------------------------------
    # 1. START 전송 (Erase 명령)
    # ----------------------------------------------------------
    payload_start = [pack_header(CMD_RX_START, 0)] + list(fw_size.to_bytes(4, byteorder='little'))
    frame = build_can_frame(CAN_ID_CMD, payload_start)
    send_frame_with_enobufs(bus, frame)
    total_tx_frames += 1
    print("[CAN] CMD_RX_START 전송 (Flash 지우기 대기 중... ⏳)")

    resp = wait_response(bus, timeout=10.0)
    if not resp or resp[0] != CMD_TX_ACK:
        print(f"[CAN] Error: Erase ACK 실패. 응답: {resp}")
        return
    total_rx_frames += 1
    print("[CAN] Erase 완료! 본격 데이터 전송 시작 🚀")

    # ----------------------------------------------------------
    # 2. DATA 전송 (256B 블록 + 비트맵 NACK 파이프라이닝 복구)
    # ----------------------------------------------------------
    idx = 0
    total_size = len(fw_data)

    while idx < total_size:
        block_data = fw_data[idx : idx + 256]
        frames = []

        for seq in range(0, len(block_data), 7):
            chunk = block_data[seq : seq + 7]
            seq_num = seq // 7
            header = pack_header(CMD_RX_DATA, seq_num)
            payload = [header] + list(chunk)
            frames.append((seq_num, payload))

        expected_frames = len(frames)

        # 블록 일괄 풀악셀 전송 (ENOBUFS 방어 포함)
        for seq_num, payload in frames:
            total_tx_frames += 1
            frame = build_can_frame(CAN_ID_CMD, payload)
            send_frame_with_enobufs(bus, frame)

        # 블록 수신 무결성 대기 (비트맵 NACK, 150ms N_Cr 타임아웃)
        while True:
            response = wait_response(bus, timeout=0.15)
            if response:
                total_rx_frames += 1

            # 타임아웃: 꼬리 프레임이 유실된 경우 마지막 프레임 재전송으로 NACK 트리거
            if not response:
                print("\n[CAN Warning] 응답 타임아웃! 꼬리 프레임 단독 송출하여 NACK 검사 트리거!")
                last_seq = expected_frames - 1
                frame = build_can_frame(CAN_ID_CMD, frames[last_seq][1])
                send_frame_with_enobufs(bus, frame)
                total_tx_frames += 1
                retransmitted_frames += 1
                continue

            cmd, args = response

            # 🟢 블록 쓰기 성공
            if cmd == CMD_TX_ACK:
                idx += len(block_data)
                print(f"\r[CAN] 진행률: {idx}/{total_size} bytes ({(idx/total_size)*100:.1f}%)", end='', flush=True)
                break

            # 🟠 NACK: 누락된 프레임만 선별 재전송
            elif cmd == CMD_TX_NACK:
                nack_map = args
                missing_seqs = [
                    seq_num for seq_num in range(expected_frames)
                    if (nack_map & (1 << seq_num)) == 0
                ]
                print(f"\n[CAN Recovery] NACK 비트맵 수신! 손실 프레임 {len(missing_seqs)}개. 선별 재전송 실행!")

                for seq_num in missing_seqs:
                    total_tx_frames += 1
                    retransmitted_frames += 1
                    frame = build_can_frame(CAN_ID_CMD, frames[seq_num][1])
                    send_frame_with_enobufs(bus, frame)

            # 🔴 치명적 에러
            elif cmd == CMD_TX_ERR:
                print(f"\n[CAN Error] 타겟 보드 치명적 에러! 코드: {args}")
                return

    print("\n[CAN] 펌웨어 전체 데이터 전송 완료!")

    # ----------------------------------------------------------
    # 3. END 전송 (최종 CRC 무결성 점검)
    # ----------------------------------------------------------
    print("[CAN] 전체 펌웨어 CRC32 로컬 계산 및 비교 전송 중...")
    fw_crc32 = zlib.crc32(fw_data) & 0xFFFFFFFF
    payload_end = [pack_header(CMD_RX_END, 0)] + list(fw_crc32.to_bytes(4, byteorder='little'))
    frame = build_can_frame(CAN_ID_CMD, payload_end)
    send_frame_with_enobufs(bus, frame)
    total_tx_frames += 1

    print("[CAN] 대상 기기에서 무결성 검증 및 Dual-Bank 플래시 복사를 진행 중입니다... (최대 10초 대기 ⏳)")
    resp = wait_response(bus, timeout=10.0)
    if not resp or resp[0] != CMD_TX_ACK:
        print(f"[CAN] Error: CRC 불일치 또는 복사/End 응답 실패! (벽돌 방지 활성화) 응답: {resp}")
        return
    total_rx_frames += 1
    print("[CAN] 펌웨어 무결성 최종 통과 및 복사 완료! (CRC Validated & Copied) ✅")

    total_time = time.time() - fota_start_time
    overhead_pct = (retransmitted_frames / total_tx_frames * 100) if total_tx_frames > 0 else 0.0
    print(f"=============================================")
    print(f"[RESULT] 총 소요 시간: {total_time:.2f} 초")
    print(f"[RESULT] 송신 프레임 (TX): {total_tx_frames} 프레임")
    print(f"[RESULT] 수신 프레임 (RX): {total_rx_frames} 프레임")
    print(f"[RESULT] 재전송 프레임: {retransmitted_frames} 프레임 ({overhead_pct:.2f}% overhead)")
    print(f"=============================================")

    # ----------------------------------------------------------
    # 4. Jump 명령
    # ----------------------------------------------------------
    time.sleep(0.5)
    payload_jump = [pack_header(CMD_RX_JUMP, 0)]
    frame = build_can_frame(CAN_ID_CMD, payload_jump)
    send_frame_with_enobufs(bus, frame)
    print("[CAN] JUMP 명령 전송 완료. 디바이스 재부팅 확인 요망!")

if __name__ == '__main__':
    os.system("sudo ip link set can0 down 2>/dev/null")
    os.system("sudo ip link set can0 up type can bitrate 1000000 2>/dev/null")

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