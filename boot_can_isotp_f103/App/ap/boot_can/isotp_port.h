#ifndef _ISOTP_PORT_H_
#define _ISOTP_PORT_H_

#include "iso15765/isotp.h"
#include "stm32f1xx_hal.h"

// Global link instance
extern IsoTpLink g_isotp_link;

// Initialize the iso-tp link
void isotp_port_init(void);

// Polling loop to be called in main loop
void isotp_port_poll(void);

// Callback to feed received CAN messages to the ISO-TP library
void isotp_port_on_can_rx(uint32_t id, uint8_t *data, uint8_t dlc);

#endif // _ISOTP_PORT_H_
