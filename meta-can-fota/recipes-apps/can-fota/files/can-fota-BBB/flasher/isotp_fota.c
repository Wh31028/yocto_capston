#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <sys/socket.h>
#include <linux/can.h>

#include "can_socket.h"
#include "fota_common.h"
#include "isotp_fota.h"
#include "protocol.h"

static int isotp_send_chunk(int sock, const uint8_t *payload, uint16_t payload_len) {
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
