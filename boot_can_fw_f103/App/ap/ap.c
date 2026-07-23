#include "ap.h"

#include "hw_def.h"

// BKP Register에 Magic Number를 기록하고 소프트 리셋
static void enterFotaMode(void)
{
  // PWR + BKP 클록 활성화
  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_RCC_BKP_CLK_ENABLE();
  HAL_PWR_EnableBkUpAccess();

  // Backup Register DR1, DR2에 32비트 Magic Number 저장
  // 부트로더가 시작 시 이 값을 확인해 FOTA 모드 진입 여부 결정
  BKP->DR1 = FOTA_MAGIC_NUMBER & 0xFFFF;
  BKP->DR2 = (FOTA_MAGIC_NUMBER >> 16) & 0xFFFF;

#ifdef _USE_HW_CLI
  cliPrintf("[AP] FOTA request received! Rebooting to bootloader...\n\r");
#endif

  // 100ms 후 소프트 리셋 (UART TX 완료 대기)
  delay(100);
  NVIC_SystemReset();
}

void apInit(void)
{
  cliOpen(_DEF_UART1, 115200);
  cliLogo();

#ifdef _USE_HW_CLI
  cliPrintf("[AP] Firmware Running. Waiting for FOTA request on CAN ID 0x200...\n\r");
#endif
}

void apMain(void)
{
  uint32_t pre_time;

  pre_time = millis();
  while (1)
  {
    // LED 토글 (동작 확인용)
    if (millis() - pre_time >= 1000) // 펌웨어는 1000ms(1초) 주기로 천천히 깜빡임
    {
      pre_time = millis();
      ledToggle(_DEF_LED1);
    }

    // CAN 메시지 폴링 - FOTA 진입 신호 감지
#ifdef _USE_HW_CAN
    while (canAvailable() > 0)
    {
      can_msg_t msg;
      canMsgRead(&msg);

      // BBB에서 CAN ID 0x200으로 0xDE 0xAD를 보내면 FOTA 진입
      if (msg.id == CAN_ID_FOTA_REQUEST && msg.dlc >= 2 &&
          msg.data[0] == 0xDE && msg.data[1] == 0xAD)
      {
        enterFotaMode();
      }
    }
#endif

    cliMain();
  }
}