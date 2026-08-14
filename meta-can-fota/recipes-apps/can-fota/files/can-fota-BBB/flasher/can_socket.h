#ifndef CAN_SOCKET_H
#define CAN_SOCKET_H

#include <stdint.h>
int open_can_socket(const char *interface_name);
int send_can_frame(int sock, uint32_t can_id, const uint8_t *data, uint8_t len);
void flush_rx_buffer(int sock);
int wait_custom_response(int sock, double timeout, uint8_t *cmd, uint64_t *args);
int wait_isotp_sf_ack(int sock, uint8_t expected_cmd, double timeout,
                      uint8_t *rx_payload, uint8_t *rx_len);
#endif
