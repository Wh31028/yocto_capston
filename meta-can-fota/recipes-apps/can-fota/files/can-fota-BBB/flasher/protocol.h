#ifndef PROTOCOL_H
#define PROTOCOL_H

#define CUSTOM_CAN_ID_RESP         0x101
#define CUSTOM_CAN_ID_CMD          0x100
#define CUSTOM_CAN_ID_FOTA_REQUEST 0x200

#define CUSTOM_CMD_RX_DATA  0x00
#define CUSTOM_CMD_RX_START 0x01
#define CUSTOM_CMD_RX_END   0x02
#define CUSTOM_CMD_RX_JUMP  0x03

#define CUSTOM_CMD_TX_ACK  0x00
#define CUSTOM_CMD_TX_NACK 0x01
#define CUSTOM_CMD_TX_ERR  0x02

/* ISO-TP Protocol Macros */
#define ISOTP_CAN_ID_RESP         0x7E8
#define ISOTP_CAN_ID_CMD          0x7E0
#define ISOTP_CAN_ID_FOTA_REQUEST 0x200

#define ISOTP_CMD_FW_START      0x10
#define ISOTP_CMD_FW_DATA       0x20
#define ISOTP_CMD_FW_END        0x30
#define ISOTP_CMD_FW_JUMP_TO_FW 0x40

#endif
