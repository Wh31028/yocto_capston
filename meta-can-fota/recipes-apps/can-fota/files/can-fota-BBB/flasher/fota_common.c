#include <stdio.h>
#include <time.h>

#include "can_socket.h"
#include "fota_common.h"

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


void trigger_fota_entry(int sock, uint32_t request_id) {
    printf("[FOTA] STM32 App FW에 FOTA 진입 신호 전송 중... (CAN ID=0x%X)\n", request_id);
    uint8_t trigger_data[2] = {0xDE, 0xAD};
    send_can_frame(sock, request_id, trigger_data, 2);
    printf("[FOTA] 신호 전송 완료. 부트로더 진입 대기 중... (3.0초)\n");
    precise_delay(3.0);
    flush_rx_buffer(sock);
    printf("[FOTA] 부트로더 준비 완료. FOTA 시작!\n");
}
