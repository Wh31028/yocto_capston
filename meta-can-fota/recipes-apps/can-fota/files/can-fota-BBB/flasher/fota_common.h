#ifndef FOTA_COMMON_H
#define FOTA_COMMON_H

#include <stddef.h>
#include <stdint.h>

uint32_t calculate_crc32(const uint8_t *data, size_t length);
void precise_delay(double seconds);
void trigger_fota_entry(int sock, uint32_t request_id);

#endif
