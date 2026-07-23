#include "ap.h"
#include "boot_can.h"
#include "hw_def.h"

// RTC Backup Register DR0에서 Magic Number 확인 후 플래그 초기화
static bool checkFotaRequest(void)
{
  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_RCC_BKP_CLK_ENABLE();
  HAL_PWR_EnableBkUpAccess();

  uint32_t magic = ((uint32_t)BKP->DR1) | (((uint32_t)BKP->DR2) << 16);
  if (magic == FOTA_MAGIC_NUMBER)
  {
    // 플래그 즉시 초기화 (다음 리셋 시 재진입 방지)
    BKP->DR1 = 0x0000;
    BKP->DR2 = 0x0000;
    return true;
  }
  return false;
}

// PC13 버튼(STM32F103 Nucleo-64 User Button) 눌림 확인
// 부트로더 시작 시 PC13 누르고 있으면 App FW 상태 무관하게 FOTA 모드 강제 진입
// 주의: Nucleo 보드의 User Button은 눌렀을 때 LOW(RESET)가 됩니다. (Active Low)
static bool isForceBootloaderButton(void)
{
  return (HAL_GPIO_ReadPin(GPIOC, GPIO_PIN_13) == GPIO_PIN_RESET);
}

void apInit(void)
{
  cliOpen(_DEF_UART1, 115200);
  cliLogo();

#ifdef _USE_HW_CLI
  cliPrintf("[BOOT] Checking FOTA request flag...\n\r");
#endif

  if (isForceBootloaderButton())
  {
#ifdef _USE_HW_CLI
    cliPrintf("[BOOT] PC13 button held! Forcing FOTA mode.\n\r");
#endif
  }
  else if (!checkFotaRequest())
  {
    uint32_t *app_reset_vector = (uint32_t *)(FLASH_ADDR_START + 4);
    if (*app_reset_vector >= FLASH_ADDR_START && *app_reset_vector < FLASH_ADDR_END)
    {
#ifdef _USE_HW_CLI
      cliPrintf("[BOOT] No FOTA request. Jumping to App...\n\r");
#endif
      delay(50);

      void (**jump_func)(void) = (void (**)(void))(FLASH_ADDR_START + 4);
      __disable_irq();
      SCB->VTOR = FLASH_ADDR_START;
      __set_MSP(*(__IO uint32_t *)FLASH_ADDR_START);
      (*jump_func)();
    }
    else
    {
#ifdef _USE_HW_CLI
      cliPrintf("[BOOT] No valid App found. Entering FOTA mode.\n\r");
#endif
    }
  }
  else
  {
#ifdef _USE_HW_CLI
    cliPrintf("[BOOT] FOTA request detected! Entering FOTA mode.\n\r");
#endif
  }

  // FOTA 모드: 부트로더 초기화
  bootInit();

#ifdef _USE_HW_CLI
  cliPrintf("[BOOT] Waiting for firmware from host...\n\r");
#endif
}


void apMain(void)
{
  uint32_t pre_time;

  pre_time = millis();
  while (1)
  {
    bootProcess();
    if (millis() - pre_time >= 100) // 부트로더는 100ms 주기로 빠르게 깜빡임
    {
      pre_time = millis();
      ledToggle(_DEF_LED1);
    }
    cliMain();
  }
}