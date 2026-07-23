#ifndef HW_H_
#define HW_H_

#include "hw_def.h"

#include "can.h"
#include "cli.h"
#include "flash.h"
#include "led.h"
#include "uart.h"

bool hwInit(void);

void bspDeInit(void);

#endif