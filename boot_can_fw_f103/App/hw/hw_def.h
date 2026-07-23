#ifndef HW_DEF_H
#define HW_DEF_H

#include "def.h"
#include "main.h"

#define _USE_HW_LED
#define HW_LED_MAX_CH 1

#define _USE_HW_UART
#define HW_UART_MAX_CH 1

#define _USE_HW_CLI
#define HW_CLI_CMD_LIST_MAX 32
#define HW_CLI_CMD_NAME_MAX 16
#define HW_CLI_LINE_HIS_MAX 8
#define HW_CLI_LINE_BUF_MAX 64

#define _USE_HW_CAN
#define HW_CAN_MAX_CH 1

#define _USE_HW_FLASH
#define _USE_MAC

// FOTA 진입 Magic Number (boot_can_fw가 쓰고, 부트로더가 읽음)
#define FOTA_MAGIC_NUMBER  0xDEADBEEFUL
#define CAN_ID_FOTA_REQUEST 0x200UL

#define FLASH_ADDR_FW 0x08004000

#define FLASH_ADDR_START 0x08004000

#define FLASH_ADDR_END   0x08020000 // 128KB Limit

#define FLASH_ADDR_FW_MAX_LEN ((1024 * 56) - 8)

#define logPrintf printf

void delay(uint32_t ms);
uint32_t millis(void);

#endif