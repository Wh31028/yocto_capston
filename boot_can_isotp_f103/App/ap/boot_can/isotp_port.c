#include "isotp_port.h"
#include <stdarg.h>
#include <stdio.h>

extern CAN_HandleTypeDef hcan;

IsoTpLink g_isotp_link;

// Data buffers for ISO-TP (Zero-Copy 아키텍처: 256바이트 페이로드 + 명령어 +
// 여유공간)
static uint8_t g_isotp_send_buf[270];
static uint8_t g_isotp_recv_buf[270];

void isotp_port_init(void)
{
  // Initialize ISO-TP link
  // Default diagnosis IDs: Client(PC) -> Server(STM32) = 0x7E0
  //                        Server(STM32) -> Client(PC) = 0x7E8
  // So STM32 sends with 0x7E8, receives with 0x7E0
  isotp_init_link(&g_isotp_link, 0x7E8, g_isotp_send_buf,
                  sizeof(g_isotp_send_buf), g_isotp_recv_buf,
                  sizeof(g_isotp_recv_buf));

  g_isotp_link.receive_arbitration_id = 0x7E0;
}

void isotp_port_poll(void)
{
  isotp_poll(&g_isotp_link);

  // Check if a complete ISO-TP message has been received
  uint16_t out_size = 0;
  if (isotp_receive(&g_isotp_link, g_isotp_recv_buf, sizeof(g_isotp_recv_buf),
                    &out_size) == ISOTP_RET_OK)
  {
    // A complete message was successfully reassembled from multiple CAN frames
    extern void bootIsoTpProcessCommand(uint8_t *payload, uint16_t size);
    bootIsoTpProcessCommand(g_isotp_recv_buf, out_size);
  }
}

void isotp_port_on_can_rx(uint32_t id, uint8_t *data, uint8_t dlc)
{
  // Check if the received CAN frame is targeted at our ISO-TP instance
  if (id == g_isotp_link.receive_arbitration_id)
  {
    isotp_on_can_message(&g_isotp_link, data, dlc);
  }
}

// ------ isotp_user.h implementations ------

void isotp_user_debug(const char *message, ...)
{
  // Optional: map to printf or CDC_Transmit for debugging
}

int isotp_user_send_can(const uint32_t arbitration_id, const uint8_t *data,
                        const uint8_t size)
{
  CAN_TxHeaderTypeDef tx_header;
  uint32_t tx_mailbox;

  tx_header.StdId              = arbitration_id;
  tx_header.ExtId              = arbitration_id;
  tx_header.IDE                = CAN_ID_STD; // Standard 11-bit ID
  tx_header.RTR                = CAN_RTR_DATA;
  tx_header.DLC                = size;
  tx_header.TransmitGlobalTime = DISABLE;

  if (HAL_CAN_GetTxMailboxesFreeLevel(&hcan) > 0)
  {
    if (HAL_CAN_AddTxMessage(&hcan, &tx_header, (uint8_t *)data,
                             &tx_mailbox) == HAL_OK)
    {
      return ISOTP_RET_OK;
    }
  }

  return ISOTP_RET_ERROR;
}

uint32_t isotp_user_get_ms(void) { return HAL_GetTick(); }
