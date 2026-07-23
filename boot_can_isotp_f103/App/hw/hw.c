#include "hw.h"
// #include "stm32f4xx_hal.h"
// #include <stdint.h>

bool hwInit(void)
{
  cliInit();
  ledInit();
  flashInit();

  uartInit();
  for (int i = 0; i < UART_MAX_CH; i++)
  {
    uartOpen(i, 115200);
  }
  logPrintf("\r\n[ Firmware Begin... ]\r\n");
  logPrintf("Booting..Clock\t: %d Mhz\r\n",
            (int)HAL_RCC_GetSysClockFreq() / 1000000);
  logPrintf("\n");

  canInit();

  return true;
}

void bspDeInit(void)
{
  uartDeInit();
  HAL_RCC_DeInit();

  // Disable Interrupts
  //
  for (int i = 0; i < 8; i++)
  {
    NVIC->ICER[i] = 0xFFFFFFFF;
    __DSB();
    __ISB();
  }

  SysTick->CTRL = 0;
}

void delay(uint32_t ms) { HAL_Delay(ms); }

uint32_t millis(void) { return HAL_GetTick(); }