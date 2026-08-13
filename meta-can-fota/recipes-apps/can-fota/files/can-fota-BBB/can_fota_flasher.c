#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <stdint.h>
#include <time.h>
#include <errno.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <net/if.h>
#include <linux/can.h>
#include <linux/can/raw.h>
#include <poll.h>

/* Custom Protocol Macros */
#define CUSTOM_CAN_ID_RESP         0x101
#define CUSTOM_CAN_ID_CMD          0x100
#define CUSTOM_CAN_ID_FOTA_REQUEST 0x200

#define CUSTOM_CMD_RX_DATA  0x00
#define CUSTOM_CMD_RX_START 0x01
#define CUSTOM_CMD_RX_END   0x02
#define CUSTOM_CMD_RX_JUMP  0x03

#define CUSTOM_CMD_TX_ACK  0x00
#define CUSTOM_CMD_TX_NACK 0x01
#define CUSTOM_CMD_TX_ERR  0x02

/* ISO-TP Protocol Macros */
#define ISOTP_CAN_ID_RESP         0x7E8
#define ISOTP_CAN_ID_CMD          0x7E0
#define ISOTP_CAN_ID_FOTA_REQUEST 0x200

#define ISOTP_CMD_FW_START      0x10
#define ISOTP_CMD_FW_DATA       0x20
#define ISOTP_CMD_FW_END        0x30
#define ISOTP_CMD_FW_JUMP_TO_FW 0x40

/* Standard IEEE 802.3 CRC32 */
uint32_t calculate_crc32(const uint8_t *data, size_t length) {
    uint32_t crc = 0xFFFFFFFF;
    for (size_t i = 0; i < length; i++) {
        crc ^= data[i];
        for (int j = 0; j < 8; j++) {
            if (crc & 1) {
                crc = (crc >> 1) ^ 0xEDB88320;
            } else {
                crc >>= 1;
            }
        }
    }
    return ~crc;
}

uint8_t pack_custom_header(uint8_t cmd, uint8_t seq) {
    return ((cmd & 0x03) << 6) | (seq & 0x3F);
}

void precise_delay(double seconds) {
    if (seconds <= 0.0) return;
    struct timespec start, current;
    clock_gettime(CLOCK_MONOTONIC, &start);
    double elapsed = 0.0;
    while (elapsed < seconds) {
        clock_gettime(CLOCK_MONOTONIC, &current);
        elapsed = (current.tv_sec - start.tv_sec) + 
                  (current.tv_nsec - start.tv_nsec) / 1000000000.0;
    }
}

/* SocketCAN Helpers */
int send_can_frame(int sock, uint32_t can_id, const uint8_t *data, uint8_t len) {
    struct can_frame frame;
    memset(&frame, 0, sizeof(frame));
    frame.can_id = can_id;
    frame.can_dlc = len;
    memcpy(frame.data, data, len);

    while (1) {
        if (write(sock, &frame, sizeof(frame)) == sizeof(frame)) {
            return 0;
        }
        if (errno == ENOBUFS) {
            precise_delay(0.0005); /* 0.5 ms wait on ENOBUFS */
            continue;
        }
        return -1;
    }
}

void flush_rx_buffer(int sock) {
    struct can_frame frame;
    int flushed = 0;
    while (recv(sock, &frame, sizeof(frame), MSG_DONTWAIT) > 0) {
        flushed++;
    }
    if (flushed > 0) {
        printf("[FOTA] 스테일 RX 데이터 %d개 폐기\n", flushed);
    }
}

int wait_custom_response(int sock, double timeout, uint8_t *cmd, uint64_t *args) {
    struct can_frame frame;
    struct pollfd pfd;
    pfd.fd = sock;
    pfd.events = POLLIN;

    struct timespec start_time, current_time;
    clock_gettime(CLOCK_MONOTONIC, &start_time);

    while (1) {
        clock_gettime(CLOCK_MONOTONIC, &current_time);
        double elapsed = (current_time.tv_sec - start_time.tv_sec) + 
                         (current_time.tv_nsec - start_time.tv_nsec) / 1000000000.0;
        if (elapsed >= timeout) {
            return -1;
        }

        int timeout_ms = (int)((timeout - elapsed) * 1000);
        if (timeout_ms <= 0) return -1;

        int ret = poll(&pfd, 1, timeout_ms);
        if (ret < 0) continue;
        if (ret == 0) return -1;

        int n = recv(sock, &frame, sizeof(frame), MSG_DONTWAIT);
        if (n < 0) continue;

        if (n == sizeof(frame)) {
            uint32_t rx_id = frame.can_id & 0x7FF;
            if (rx_id == CUSTOM_CAN_ID_RESP) {
                uint8_t header = frame.data[0];
                *cmd = (header >> 6) & 0x03;
                if (*cmd == CUSTOM_CMD_TX_ACK || *cmd == CUSTOM_CMD_TX_ERR) {
                    *args = header & 0x3F;
                    return 0;
                } else if (*cmd == CUSTOM_CMD_TX_NACK) {
                    uint64_t nack_map = 0;
                    for (int i = 1; i < 8; i++) {
                        nack_map |= ((uint64_t)frame.data[i] << (8 * (i - 1)));
                    }
                    *args = nack_map;
                    return 0;
                }
            }
        }
    }
}

int wait_isotp_sf_ack(int sock, uint8_t expected_cmd, double timeout, uint8_t *rx_payload, uint8_t *rx_len) {
    struct can_frame frame;
    struct pollfd pfd;
    pfd.fd = sock;
    pfd.events = POLLIN;

    struct timespec start_time, current_time;
    clock_gettime(CLOCK_MONOTONIC, &start_time);

    while (1) {
        clock_gettime(CLOCK_MONOTONIC, &current_time);
        double elapsed = (current_time.tv_sec - start_time.tv_sec) + 
                         (current_time.tv_nsec - start_time.tv_nsec) / 1000000000.0;
        if (elapsed >= timeout) {
            return -1;
        }

        int timeout_ms = (int)((timeout - elapsed) * 1000);
        if (timeout_ms <= 0) return -1;

        int ret = poll(&pfd, 1, timeout_ms);
        if (ret < 0) continue;
        if (ret == 0) return -1;

        int n = recv(sock, &frame, sizeof(frame), MSG_DONTWAIT);
        if (n < 0) continue;

        if (n == sizeof(frame)) {
            uint32_t rx_id = frame.can_id & 0x7FF;
            if (rx_id == ISOTP_CAN_ID_RESP) {
                /* Single Frame (PCI: 0x0N) */
                if ((frame.data[0] & 0xF0) == 0x00) {
                    uint8_t sf_len = frame.data[0] & 0x0F;
                    if (sf_len >= 2 && frame.data[1] == expected_cmd) {
                        *rx_len = sf_len;
                        memcpy(rx_payload, &frame.data[1], sf_len);
                        return 0;
                    }
                }
            }
        }
    }
}

int isotp_send_chunk(int sock, const uint8_t *payload, uint16_t payload_len) {
    /* ISO-TP single frame for payloads up to seven bytes. */
    if (payload_len <= 7) {
        uint8_t sf_data[8] = {0};
        sf_data[0] = payload_len;
        memcpy(&sf_data[1], payload, payload_len);
        return send_can_frame(sock, ISOTP_CAN_ID_CMD, sf_data, 8);
    }

    /* 1. First Frame (FF) */
    uint8_t ff_data[8];
    memset(ff_data, 0, 8);
    ff_data[0] = 0x10 | ((payload_len >> 8) & 0x0F);
    ff_data[1] = payload_len & 0xFF;
    memcpy(&ff_data[2], payload, 6);

    if (send_can_frame(sock, ISOTP_CAN_ID_CMD, ff_data, 8) < 0) {
        return -1;
    }

    /* 2. Wait for Flow Control (FC) */
    struct can_frame frame;
    struct pollfd pfd;
    pfd.fd = sock;
    pfd.events = POLLIN;

    int fc_received = 0;
    double stmin_sec = 0.0;

    struct timespec start_time, current_time;
    clock_gettime(CLOCK_MONOTONIC, &start_time);

    while (1) {
        clock_gettime(CLOCK_MONOTONIC, &current_time);
        double elapsed = (current_time.tv_sec - start_time.tv_sec) + 
                         (current_time.tv_nsec - start_time.tv_nsec) / 1000000000.0;
        if (elapsed >= 1.0) {
            break;
        }

        int timeout_ms = (int)((1.0 - elapsed) * 1000);
        if (timeout_ms <= 0) break;

        int ret = poll(&pfd, 1, timeout_ms);
        if (ret <= 0) continue; // error or timeout

        int n = recv(sock, &frame, sizeof(frame), MSG_DONTWAIT);
        if (n < 0) continue;

        if (n == sizeof(frame)) {
            uint32_t rx_id = frame.can_id & 0x7FF;
            if (rx_id == ISOTP_CAN_ID_RESP && (frame.data[0] & 0xF0) == 0x30) {
                fc_received = 1;
                uint8_t stmin_val = frame.data[2];
                if (stmin_val <= 0x7F) {
                    stmin_sec = stmin_val / 1000.0;
                } else if (stmin_val >= 0xF1 && stmin_val <= 0xF9) {
                    stmin_sec = (stmin_val - 0xF0) / 10000.0;
                } else {
                    stmin_sec = 0.127;
                }
                break;
            }
        }
    }

    if (!fc_received) {
        return -1;
    }

    /* 3. Send Consecutive Frames (CF) */
    uint16_t idx = 6;
    uint8_t seq = 1;
    while (idx < payload_len) {
        uint8_t cf_len = (payload_len - idx < 7) ? (payload_len - idx) : 7;
        uint8_t cf_data[8];
        memset(cf_data, 0, 8);
        cf_data[0] = 0x20 | (seq & 0x0F);
        memcpy(&cf_data[1], &payload[idx], cf_len);

        if (send_can_frame(sock, ISOTP_CAN_ID_CMD, cf_data, 8) < 0) {
            return -1;
        }

        precise_delay(stmin_sec);

        idx += cf_len;
        seq = (seq + 1) & 0x0F;
    }

    return 0;
}

void trigger_fota_entry(int sock, uint32_t request_id) {
    printf("[FOTA] STM32 App FW에 FOTA 진입 신호 전송 중... (CAN ID=0x%X)\n", request_id);
    uint8_t trigger_data[2] = {0xDE, 0xAD};
    send_can_frame(sock, request_id, trigger_data, 2);
    printf("[FOTA] 신호 전송 완료. 부트로더 진입 대기 중... (3.0초)\n");
    precise_delay(3.0);
    flush_rx_buffer(sock);
    printf("[FOTA] 부트로더 준비 완료. FOTA 시작!\n");
}

/* Main FOTA Processors */
int start_custom_fota(int sock, const uint8_t *fw_data, size_t fw_size) {
    printf("=============================================\n");
    printf("[CAN] 비트맵 NACK 적용 FOTA Gateway 시작!\n");
    printf("=============================================\n");

    trigger_fota_entry(sock, CUSTOM_CAN_ID_FOTA_REQUEST);

    double fota_start_time;
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    fota_start_time = ts.tv_sec + ts.tv_nsec / 1000000000.0;

    int total_tx_frames = 0;
    int total_rx_frames = 0;
    int retransmitted_frames = 0;

    /* 1. START */
    uint8_t start_payload[5];
    start_payload[0] = pack_custom_header(CUSTOM_CMD_RX_START, 0);
    start_payload[1] = fw_size & 0xFF;
    start_payload[2] = (fw_size >> 8) & 0xFF;
    start_payload[3] = (fw_size >> 16) & 0xFF;
    start_payload[4] = (fw_size >> 24) & 0xFF;

    if (send_can_frame(sock, CUSTOM_CAN_ID_CMD, start_payload, 5) < 0) {
        printf("[CAN] Error: START CMD 송신 실패\n");
        return -1;
    }
    total_tx_frames++;
    printf("[CAN] CMD_RX_START 전송 (Flash 지우기 대기 중... ⏳)\n");

    uint8_t rx_cmd;
    uint64_t rx_args;
    if (wait_custom_response(sock, 10.0, &rx_cmd, &rx_args) < 0 || rx_cmd != CUSTOM_CMD_TX_ACK) {
        printf("[CAN] Error: Erase ACK 실패.\n");
        return -1;
    }
    total_rx_frames++;
    printf("[CAN] Erase 완료! 본격 데이터 전송 시작 🚀\n");

    /* 2. DATA */
    size_t idx = 0;
    while (idx < fw_size) {
        size_t block_len = (fw_size - idx < 256) ? (fw_size - idx) : 256;
        
        /* Prepare frames for this block */
        int expected_frames = (block_len + 6) / 7;
        uint8_t block_frames[37][8]; /* 256 / 7 = 36.57 frames max -> 37 */
        uint8_t frame_lens[37];

        for (int seq = 0; seq < expected_frames; seq++) {
            size_t chunk_offset = seq * 7;
            size_t chunk_len = (block_len - chunk_offset < 7) ? (block_len - chunk_offset) : 7;
            
            block_frames[seq][0] = pack_custom_header(CUSTOM_CMD_RX_DATA, seq);
            memcpy(&block_frames[seq][1], &fw_data[idx + chunk_offset], chunk_len);
            frame_lens[seq] = chunk_len + 1;
        }

        /* Send block frames */
        for (int seq = 0; seq < expected_frames; seq++) {
            send_can_frame(sock, CUSTOM_CAN_ID_CMD, block_frames[seq], frame_lens[seq]);
            total_tx_frames++;
        }

        /* Receive feedback */
        while (1) {
            if (wait_custom_response(sock, 0.15, &rx_cmd, &rx_args) < 0) {
                printf("\n[CAN Warning] 응답 타임아웃! 꼬리 프레임 단독 송출하여 NACK 검사 트리거!\n");
                int last_seq = expected_frames - 1;
                send_can_frame(sock, CUSTOM_CAN_ID_CMD, block_frames[last_seq], frame_lens[last_seq]);
                total_tx_frames++;
                retransmitted_frames++;
                continue;
            }
            total_rx_frames++;

            if (rx_cmd == CUSTOM_CMD_TX_ACK) {
                idx += block_len;
                printf("\r[CAN] 진행률: %zu/%zu bytes (%.1f%%)", idx, fw_size, ((double)idx / fw_size) * 100.0);
                fflush(stdout);
                break;
            } else if (rx_cmd == CUSTOM_CMD_TX_NACK) {
                uint64_t nack_map = rx_args;
                printf("\n[CAN Recovery] NACK 비트맵 수신! 선별 재전송 실행!\n");
                for (int seq = 0; seq < expected_frames; seq++) {
                    if ((nack_map & ((uint64_t)1 << seq)) == 0) {
                        send_can_frame(sock, CUSTOM_CAN_ID_CMD, block_frames[seq], frame_lens[seq]);
                        total_tx_frames++;
                        retransmitted_frames++;
                    }
                }
            } else if (rx_cmd == CUSTOM_CMD_TX_ERR) {
                printf("\n[CAN Error] 타겟 보드 치명적 에러! 코드: %llu\n", (unsigned long long)rx_args);
                return -1;
            }
        }
    }
    printf("\n[CAN] 펌웨어 전체 데이터 전송 완료!\n");

    /* 3. END */
    printf("[CAN] 전체 펌웨어 CRC32 로컬 계산 및 비교 전송 중...\n");
    uint32_t fw_crc32 = calculate_crc32(fw_data, fw_size);
    uint8_t end_payload[5];
    end_payload[0] = pack_custom_header(CUSTOM_CMD_RX_END, 0);
    end_payload[1] = fw_crc32 & 0xFF;
    end_payload[2] = (fw_crc32 >> 8) & 0xFF;
    end_payload[3] = (fw_crc32 >> 16) & 0xFF;
    end_payload[4] = (fw_crc32 >> 24) & 0xFF;

    send_can_frame(sock, CUSTOM_CAN_ID_CMD, end_payload, 5);
    total_tx_frames++;

    printf("[CAN] 대상 기기에서 무결성 검증 및 Dual-Bank 플래시 복사를 진행 중입니다... (최대 10초 대기 ⏳)\n");
    if (wait_custom_response(sock, 10.0, &rx_cmd, &rx_args) < 0 || rx_cmd != CUSTOM_CMD_TX_ACK) {
        printf("[CAN] Error: CRC 불일치 또는 복사/End 응답 실패! (벽돌 방지 활성화)\n");
        return -1;
    }
    total_rx_frames++;
    printf("[CAN] 펌웨어 무결성 최종 통과 및 복사 완료! (CRC Validated & Copied) ✅\n");

    double end_time;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    end_time = ts.tv_sec + ts.tv_nsec / 1000000000.0;
    double total_time = end_time - fota_start_time;
    double overhead_pct = (total_tx_frames > 0) ? ((double)retransmitted_frames / total_tx_frames * 100.0) : 0.0;

    printf("=============================================\n");
    printf("[RESULT] 총 소요 시간: %.2f 초\n", total_time);
    printf("[RESULT] 송신 프레임 (TX): %d 프레임\n", total_tx_frames);
    printf("[RESULT] 수신 프레임 (RX): %d 프레임\n", total_rx_frames);
    printf("[RESULT] 재전송 프레임: %d 프레임 (%.2f%% overhead)\n", retransmitted_frames, overhead_pct);
    printf("=============================================\n");

    /* 4. JUMP */
    precise_delay(0.5);
    uint8_t jump_payload[1];
    jump_payload[0] = pack_custom_header(CUSTOM_CMD_RX_JUMP, 0);
    send_can_frame(sock, CUSTOM_CAN_ID_CMD, jump_payload, 1);
    printf("[CAN] JUMP 명령 전송 완료. 디바이스 재부팅 확인 요망!\n");

    return 0;
}

int start_isotp_fota(int sock, const uint8_t *fw_data, size_t fw_size) {
    printf("=============================================\n");
    printf("[CAN] ISO-TP FOTA Flashing 시작!\n");
    printf("=============================================\n");

    trigger_fota_entry(sock, ISOTP_CAN_ID_FOTA_REQUEST);

    double fota_start_time;
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    fota_start_time = ts.tv_sec + ts.tv_nsec / 1000000000.0;

    int total_tx_frames = 0;
    int total_rx_frames = 0;
    int retransmitted_frames = 0;

    /* 1. START */
    uint8_t start_payload[8];
    memset(start_payload, 0, 8);
    start_payload[0] = 0x05;
    start_payload[1] = ISOTP_CMD_FW_START;
    start_payload[2] = fw_size & 0xFF;
    start_payload[3] = (fw_size >> 8) & 0xFF;
    start_payload[4] = (fw_size >> 16) & 0xFF;
    start_payload[5] = (fw_size >> 24) & 0xFF;

    if (send_can_frame(sock, ISOTP_CAN_ID_CMD, start_payload, 8) < 0) {
        printf("[CAN] Error: START CMD 송신 실패\n");
        return -1;
    }
    total_tx_frames++;

    uint8_t rx_payload[8];
    uint8_t rx_len = 0;
    if (wait_isotp_sf_ack(sock, ISOTP_CMD_FW_START, 15.0, rx_payload, &rx_len) < 0) {
        printf("[CAN] Error: Erase ACK Timeout\n");
        return -1;
    }
    total_rx_frames++;

    uint16_t chunk_size = 256;
    if (rx_len >= 4) {
        chunk_size = rx_payload[2] | (rx_payload[3] << 8);
        printf("[CAN] START 성공! STM32가 %d bytes 단위로 보내라고 하네요.\n", chunk_size);
    } else {
        printf("[CAN] START 성공! (chunk_size 기본값 %d 사용)\n", chunk_size);
    }

    if (chunk_size == 0) {
        printf("[CAN] Error: STM32가 유효하지 않은 chunk_size(0)를 응답했습니다.\n");
        return -1;
    }

    /* 2. DATA */
    printf("[CAN] Firmware Data 전송 중 (Raw ISO-TP)...\n");
    for (size_t i = 0; i < fw_size; i += chunk_size) {
        size_t current_chunk = (fw_size - i < chunk_size) ? (fw_size - i) : chunk_size;
        
        /* Allocate buffer for CMD_FW_DATA (1 byte) + chunk data */
        uint8_t *payload = malloc(1 + current_chunk);
        if (!payload) {
            printf("[CAN] Error: 데이터 청크 메모리 할당 실패\n");
            return -1;
        }
        payload[0] = ISOTP_CMD_FW_DATA;
        memcpy(&payload[1], &fw_data[i], current_chunk);

        int retry_count = 0;
        int success = 0;

        while (retry_count < 3) {
            if (retry_count > 0) {
                int block_idx = i / chunk_size;
                int retx_frames = (1 + current_chunk + 6) / 7;
                printf("\n[CAN] Block %d 재전송 (ISO-TP Go-Back-N, %d프레임 통째로 재전송!)\n", block_idx, retx_frames);
                retransmitted_frames += retx_frames;
                flush_rx_buffer(sock);
            }

            if (isotp_send_chunk(sock, payload, 1 + current_chunk) == 0) {
                uint8_t ack_payload[8];
                uint8_t ack_len = 0;
                if (wait_isotp_sf_ack(sock, ISOTP_CMD_FW_DATA, 0.15, ack_payload, &ack_len) == 0) {
                    if (ack_payload[1] == 0) { /* BOOT_OK */
                        total_rx_frames++;
                        success = 1;
                        break;
                    }
                }
            }
            retry_count++;
        }

        free(payload);

        if (!success) {
            printf("\n[CAN] 치명적 에러: 지속적인 패킷 유실로 인해 STM32가 응답하지 않음.\n");
            return -1;
        }

        size_t progress_idx = (i + chunk_size < fw_size) ? (i + chunk_size) : fw_size;
        printf("[CAN] 진행률: %zu/%zu bytes (%.1f%%)\n", progress_idx, fw_size, ((double)progress_idx / fw_size) * 100.0);
        fflush(stdout);
    }
    printf("\n[CAN] 데이터 전송 완료\n");

    /* 3. END */
    uint32_t fw_crc32 = calculate_crc32(fw_data, fw_size);
    uint8_t end_payload[8];
    memset(end_payload, 0, 8);
    end_payload[0] = 0x05;
    end_payload[1] = ISOTP_CMD_FW_END;
    end_payload[2] = fw_crc32 & 0xFF;
    end_payload[3] = (fw_crc32 >> 8) & 0xFF;
    end_payload[4] = (fw_crc32 >> 16) & 0xFF;
    end_payload[5] = (fw_crc32 >> 24) & 0xFF;

    send_can_frame(sock, ISOTP_CAN_ID_CMD, end_payload, 8);
    total_tx_frames++;

    uint8_t end_ack_payload[8];
    uint8_t end_ack_len = 0;
    if (wait_isotp_sf_ack(sock, ISOTP_CMD_FW_END, 5.0, end_ack_payload, &end_ack_len) == 0 && end_ack_payload[1] == 0) {
        total_rx_frames++;
        printf("[CAN] 펌웨어 무결성 검증 통과 및 플래싱 완료! ✅\n");
    } else {
        printf("[CAN] ❌ Error: End ACK Fail (CRC 불일치 혹은 타임아웃)\n");
        return -1;
    }

    double end_time;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    end_time = ts.tv_sec + ts.tv_nsec / 1000000000.0;
    double total_time = end_time - fota_start_time;
    double overhead_pct = (total_tx_frames > 0) ? ((double)retransmitted_frames / total_tx_frames * 100.0) : 0.0;

    printf("=============================================\n");
    printf("[RESULT] 총 소요 시간: %.2f 초\n", total_time);
    printf("[RESULT] 송신 프레임 (TX): %d 프레임\n", total_tx_frames);
    printf("[RESULT] 수신 프레임 (RX): %d 프레임\n", total_rx_frames);
    printf("[RESULT] 재전송 프레임: %d 프레임 (%.2f%% overhead)\n", retransmitted_frames, overhead_pct);
    printf("=============================================\n");

    /* 4. JUMP */
    precise_delay(0.5);
    uint8_t jump_payload[8];
    memset(jump_payload, 0, 8);
    jump_payload[0] = 0x02;
    jump_payload[1] = ISOTP_CMD_FW_JUMP_TO_FW;
    send_can_frame(sock, ISOTP_CAN_ID_CMD, jump_payload, 8);
    printf("[CAN] JUMP 명령 전송 완료. 디바이스 재부팅 확인 요망!\n");

    return 0;
}

int main(int argc, char *argv[]) {
    setbuf(stdout, NULL);
    if (argc < 3) {
        fprintf(stderr, "Usage: %s <protocol> <firmware_path> [interface_name]\n", argv[0]);
        fprintf(stderr, "Protocols: custom, isotp\n");
        return 1;
    }

    const char *protocol = argv[1];
    const char *firmware_path = argv[2];
    const char *interface_name = (argc >= 4) ? argv[3] : "can0";

    /* Read Firmware File */
    FILE *f = fopen(firmware_path, "rb");
    if (!f) {
        fprintf(stderr, "Error opening firmware file: %s\n", firmware_path);
        return 1;
    }

    fseek(f, 0, SEEK_END);
    long fw_size_long = ftell(f);
    if (fw_size_long <= 0) {
        fprintf(stderr, "Invalid or empty firmware file: %s\n", firmware_path);
        fclose(f);
        return 1;
    }
    size_t fw_size = (size_t)fw_size_long;
    fseek(f, 0, SEEK_SET);

    uint8_t *fw_data = malloc(fw_size);
    if (!fw_data) {
        fprintf(stderr, "Failed to allocate memory for firmware (%zu bytes)\n", fw_size);
        fclose(f);
        return 1;
    }

    if (fread(fw_data, 1, fw_size, f) != fw_size) {
        fprintf(stderr, "Error reading firmware file\n");
        free(fw_data);
        fclose(f);
        return 1;
    }
    fclose(f);

    /* Initialize SocketCAN */
    int sock = socket(PF_CAN, SOCK_RAW, CAN_RAW);
    if (sock < 0) {
        perror("Error opening SocketCAN socket");
        free(fw_data);
        return 1;
    }

    if (strlen(interface_name) >= IFNAMSIZ) {
        fprintf(stderr, "Interface name is too long: %s\n", interface_name);
        close(sock);
        free(fw_data);
        return 1;
    }

    struct ifreq ifr;
    memset(&ifr, 0, sizeof(ifr));
    memcpy(ifr.ifr_name, interface_name, strlen(interface_name) + 1);
    if (ioctl(sock, SIOCGIFINDEX, &ifr) < 0) {
        perror("Error setting interface name (ioctl)");
        close(sock);
        free(fw_data);
        return 1;
    }

    struct sockaddr_can addr;
    memset(&addr, 0, sizeof(addr));
    addr.can_family = AF_CAN;
    addr.can_ifindex = ifr.ifr_ifindex;

    if (bind(sock, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("Error binding SocketCAN socket");
        close(sock);
        free(fw_data);
        return 1;
    }

    /* Execute Protocol */
    int result = -1;
    if (strcmp(protocol, "custom") == 0) {
        result = start_custom_fota(sock, fw_data, fw_size);
    } else if (strcmp(protocol, "isotp") == 0) {
        result = start_isotp_fota(sock, fw_data, fw_size);
    } else {
        fprintf(stderr, "Unknown protocol: %s (Must be 'custom' or 'isotp')\n", protocol);
    }

    close(sock);
    free(fw_data);

    return (result == 0) ? 0 : 1;
}
