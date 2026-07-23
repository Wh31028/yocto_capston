#ifndef AP_INCLUDE_FOTA_H_
#define AP_INCLUDE_FOTA_H_

#include "ap_def.h"

#define BOOT_OK              0x00
#define BOOT_ERR_FLASH_ERASE 0x03
#define BOOT_ERR_FLASH_WRITE 0x04
#define BOOT_ERR_FLASH_JUMP  0x05
#define BOOT_ERR_CRC         0x06

// Custom Protocol Commands (2-bit)
// Host->Target (RX_CMD)
#define CMD_RX_DATA  0x00
#define CMD_RX_START 0x01
#define CMD_RX_END   0x02
#define CMD_RX_JUMP  0x03

// Target->Host (TX_CMD)
#define CMD_TX_ACK  0x00
#define CMD_TX_NACK 0x01
#define CMD_TX_ERR  0x02

// Header Macros
#define PACK_HEADER(cmd, seq) (((cmd & 0x03) << 6) | (seq & 0x3F))
#define GET_CMD(header)       ((header >> 6) & 0x03)
#define GET_SEQ(header)       (header & 0x3F)

void bootInit(void);
void bootProcess(void);

bool bootAutoRecover(void);

bool bootVerifyFw(void);
void JumpToFw(void);

uint32_t bootGetLastRxTime(void);

// 내부 함수이지만 혹시 외부 참조 필요시를 대비
bool bootCopyFw(uint32_t fw_size);

#endif