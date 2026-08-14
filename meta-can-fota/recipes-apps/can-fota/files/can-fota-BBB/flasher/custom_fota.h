#ifndef CUSTOM_FOTA_H
#define CUSTOM_FOTA_H

#include <stddef.h>
#include <stdint.h>

int start_custom_fota(int sock, const uint8_t *fw_data, size_t fw_size);

#endif
