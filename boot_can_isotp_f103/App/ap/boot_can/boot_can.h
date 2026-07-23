#ifndef AP_INCLUDE_FOTA_H_
#define AP_INCLUDE_FOTA_H_

#include "ap_def.h"

#define BOOT_OK              0x00
#define BOOT_ERR_FLASH_ERASE 0x03
#define BOOT_ERR_FLASH_WRITE 0x04
#define BOOT_ERR_FLASH_JUMP  0x05
#define BOOT_ERR_CRC         0x06

void bootInit(void);
void bootProcess(void); // 메인 루프에서 계속 돌릴 함수
void bootIsoTpProcessCommand(uint8_t *payload, uint16_t size);

#endif