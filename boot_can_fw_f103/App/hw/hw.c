#include "hw.h"


bool hwInit(void)
{
  cliInit();
  ledInit();
  flashInit();
  canInit();

  uartInit();
  for (int i = 0; i < UART_MAX_CH; i++)
  {
    uartOpen(i, 115200);
  }
  logPrintf("\r\n[ Firmware Begin... ]\r\n");
  logPrintf("Booting..Clock\t: %d Mhz\r\n",
            (int)HAL_RCC_GetSysClockFreq() / 1000000);
  logPrintf("\n");

  return true;
}

void delay(uint32_t ms) { HAL_Delay(ms); }

uint32_t millis(void) { return HAL_GetTick(); }