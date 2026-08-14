#include <errno.h>
#include <net/if.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>
#include <linux/can.h>
#include <linux/can/raw.h>

#include "can_socket.h"
#include "fota_common.h"
#include "protocol.h"

int open_can_socket(const char *interface_name) {
    if (!interface_name || strlen(interface_name) >= IFNAMSIZ) {
        errno = EINVAL;
        return -1;
    }
    int sock = socket(PF_CAN, SOCK_RAW, CAN_RAW);
    if (sock < 0) return -1;

    struct ifreq ifr = {0};
    memcpy(ifr.ifr_name, interface_name, strlen(interface_name) + 1);
    if (ioctl(sock, SIOCGIFINDEX, &ifr) < 0) {
        close(sock);
        return -1;
    }

    struct sockaddr_can addr = {0};
    addr.can_family = AF_CAN;
    addr.can_ifindex = ifr.ifr_ifindex;
    if (bind(sock, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        close(sock);
        return -1;
    }
    return sock;
}

int send_can_frame(int sock, uint32_t can_id, const uint8_t *data, uint8_t len) {
    if (!data || len > CAN_MAX_DLEN) {
        errno = EINVAL;
        return -1;
    }
    struct can_frame frame = {0};
    frame.can_id = can_id;
    frame.can_dlc = len;
    memcpy(frame.data, data, len);
    for (;;) {
        if (write(sock, &frame, sizeof(frame)) == sizeof(frame)) return 0;
        if (errno != ENOBUFS) return -1;
        precise_delay(0.0005);
    }
}

void flush_rx_buffer(int sock) {
    struct can_frame frame;
    int flushed = 0;
    while (recv(sock, &frame, sizeof(frame), MSG_DONTWAIT) > 0) flushed++;
    if (flushed > 0) printf("[FOTA] 스테일 RX 데이터 %d개 폐기\n", flushed);
}

static int wait_readable(int sock, double timeout) {
    struct pollfd pfd = {.fd = sock, .events = POLLIN};
    return poll(&pfd, 1, timeout > 0.0 ? (int)(timeout * 1000.0) : 0);
}

int wait_custom_response(int sock, double timeout, uint8_t *cmd, uint64_t *args) {
    struct can_frame frame;
    struct timespec start, now;
    clock_gettime(CLOCK_MONOTONIC, &start);
    for (;;) {
        clock_gettime(CLOCK_MONOTONIC, &now);
        double elapsed = (now.tv_sec - start.tv_sec) +
                         (now.tv_nsec - start.tv_nsec) / 1000000000.0;
        if (elapsed >= timeout) return -1;
        if (wait_readable(sock, timeout - elapsed) <= 0) return -1;
        if (recv(sock, &frame, sizeof(frame), MSG_DONTWAIT) != sizeof(frame)) continue;
        if ((frame.can_id & CAN_SFF_MASK) != CUSTOM_CAN_ID_RESP) continue;

        uint8_t header = frame.data[0];
        *cmd = (header >> 6) & 0x03;
        if (*cmd == CUSTOM_CMD_TX_ACK || *cmd == CUSTOM_CMD_TX_ERR) {
            *args = header & 0x3F;
            return 0;
        }
        if (*cmd == CUSTOM_CMD_TX_NACK) {
            *args = 0;
            for (int i = 1; i < 8; i++) *args |= (uint64_t)frame.data[i] << (8 * (i - 1));
            return 0;
        }
    }
}

int wait_isotp_sf_ack(int sock, uint8_t expected_cmd, double timeout,
                      uint8_t *rx_payload, uint8_t *rx_len) {
    struct can_frame frame;
    struct timespec start, now;
    clock_gettime(CLOCK_MONOTONIC, &start);
    for (;;) {
        clock_gettime(CLOCK_MONOTONIC, &now);
        double elapsed = (now.tv_sec - start.tv_sec) +
                         (now.tv_nsec - start.tv_nsec) / 1000000000.0;
        if (elapsed >= timeout) return -1;
        if (wait_readable(sock, timeout - elapsed) <= 0) return -1;
        if (recv(sock, &frame, sizeof(frame), MSG_DONTWAIT) != sizeof(frame)) continue;
        if ((frame.can_id & CAN_SFF_MASK) != ISOTP_CAN_ID_RESP) continue;
        if ((frame.data[0] & 0xF0) != 0x00) continue;
        uint8_t sf_len = frame.data[0] & 0x0F;
        if (sf_len < 2 || sf_len > 7 || frame.data[1] != expected_cmd) continue;
        *rx_len = sf_len;
        memcpy(rx_payload, &frame.data[1], sf_len);
        return 0;
    }
}
