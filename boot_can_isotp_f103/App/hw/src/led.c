#include "led.h"
#include "def.h"
#include "hw_def.h"
#include <stdbool.h>
#include <stdint.h>

#ifdef _USE_HW_LED
#include "cli.h"

typedef struct
{
  GPIO_TypeDef *port;
  uint16_t pin;
  GPIO_PinState on_state;
  GPIO_PinState off_state;
} led_tbl_t;

static void ledCmd(cli_args_t *args);

static led_tbl_t led_tbl[LED_MAX_CH] = {
    {GPIOA, GPIO_PIN_5, GPIO_PIN_SET, GPIO_PIN_RESET}};

bool ledInit(void)
{

  for (int i = 0; i < LED_MAX_CH; i++)
  {
    ledOff(i);
  }

  cliAdd("led", ledCmd);

  return true;
}

void ledOn(uint8_t ch)
{
  if (ch >= LED_MAX_CH)
    return;

  HAL_GPIO_WritePin(led_tbl[ch].port, led_tbl[ch].pin, led_tbl[ch].on_state);
}

void ledOff(uint8_t ch)
{
  if (ch >= LED_MAX_CH)
    return;

  HAL_GPIO_WritePin(led_tbl[ch].port, led_tbl[ch].pin, led_tbl[ch].off_state);
}

void ledToggle(uint8_t ch)
{
  if (ch >= LED_MAX_CH)
    return;

  HAL_GPIO_TogglePin(led_tbl[ch].port, led_tbl[ch].pin);
}

void ledCmd(cli_args_t *args)
{
  bool ret = false;

  // 명령어 실행 코드

  if (args->argc == 1 && args->isStr(0, "test"))
  {
    uint32_t pre_time;
    uint32_t test_cnt = 0;

    cliShowCursor(false);
    pre_time = millis();
    while (cliKeepLoop())
    {
      if (millis() - pre_time >= 500)
      {
        pre_time = millis();
        ledToggle(_DEF_LED1);

        test_cnt++;
        cliPrintf("led test\n\r");
        cliPrintf("  cnt : %d\n\r", test_cnt);

        cliMoveUp(2);
      }
    }
    cliMoveDown(2);

    cliShowCursor(true);
    ret = true;
  }

  if (!ret)
  {
    logPrintf("led test\n\r");
  }
}

#endif