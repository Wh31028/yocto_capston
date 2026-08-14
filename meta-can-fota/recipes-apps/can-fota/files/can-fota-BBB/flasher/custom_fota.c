#include <stdio.h>
#include <string.h>
#include <time.h>

#include "can_socket.h"
#include "custom_fota.h"
#include "fota_common.h"
#include "protocol.h"

static uint8_t pack_custom_header(uint8_t cmd, uint8_t seq) {
    return ((cmd & 0x03) << 6) | (seq & 0x3F);
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
