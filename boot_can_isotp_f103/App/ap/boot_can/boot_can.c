#include "boot_can.h"
#include "can.h" // 작성하신 CAN 드라이버 포함
#include "flash.h"
#include "isotp_port.h"
#include <stdbool.h>

// 비글본 파이썬 코드와 맞춘 명령어
#define CMD_FW_START      0x10
#define CMD_FW_DATA       0x20
#define CMD_FW_END        0x30
#define CMD_FW_JUMP_TO_FW 0x40

// STM32가 PC에게 요구할 데이터 청크 크기 (UDS의 MaxNumberOfBlockLength 개념)
#define FOTA_CHUNK_SIZE 256

// 펌웨어 데이터 임시 저장용 구형 버퍼 삭제 (Zero-Copy로 최적화됨)
static uint32_t fw_addr = FLASH_ADDR_FW; // App 시작 주소 (모델에 따라 다름)
static uint32_t original_fw_size = 0;    // 원본 파일 크기 저장용 (CRC 계산용)

static void SendResponse(uint8_t cmd, uint8_t result);
static uint8_t bootIsoTpFlashErase(uint8_t *payload, uint16_t size);
static uint8_t bootIsoTpFlashWrite(uint8_t *payload, uint16_t size);
static uint8_t bootIsoTpFlashEnd(uint8_t *payload, uint16_t size);
static uint8_t bootIsoTpJump(uint8_t cmd);
static bool bootVerifyFw(void);
static void JumpToFw(void);
static uint32_t calculate_crc32(uint32_t start_addr, uint32_t length);

void bootInit(void) { isotp_port_init(); }

void bootProcess(void)
{
  // 1. ISO-TP library keep-alive (타이머 감시 및 폴링)
  isotp_port_poll();

  // 2. 물리적인 8바이트 CAN 프레임 수신 및 ISO-TP 조립 공장으로 전달
  while (canAvailable() > 0)
  {
    can_msg_t msg;
    canMsgRead(&msg);

    if (msg.id == g_isotp_link.receive_arbitration_id || msg.id == 0x7E0 ||
        msg.id == 0x7E8)
    {
      isotp_port_on_can_rx(msg.id, msg.data, msg.dlc);
    }
  }
}

// 구형 레거시 함수(bootFlashErase, bootFlashWrite 등) 4종 완벽히 삭제 완료

void bootIsoTpProcessCommand(uint8_t *payload, uint16_t size)
{
  if (size < 1)
    return;

  uint8_t cmd    = payload[0];
  uint8_t status = BOOT_OK;

  switch (cmd)
  {
  case CMD_FW_START:
    status = bootIsoTpFlashErase(payload, size);
    break;

  case CMD_FW_DATA:
    status = bootIsoTpFlashWrite(payload, size);
    break;

  case CMD_FW_END:
    status = bootIsoTpFlashEnd(payload, size);
    break;

  case CMD_FW_JUMP_TO_FW:
    status = bootIsoTpJump(cmd);
    if (status == BOOT_OK)
      return;
    break;
  }

  // 응답 전송 (ISO-TP로 ACK 송신)
  // [초특급 진화 포인트] START 명령이 성공했을 때는, UDS(0x34) 프로토콜처럼
  // "나 256바이트 단위로 받을 테니까 256씩 쪼개서 보내!" 라고
  // 네고시에이션(협상) 응답을 보냅니다.
  if (cmd == CMD_FW_START && status == BOOT_OK)
  {
    uint8_t ack_payload[4] = {cmd, status, (FOTA_CHUNK_SIZE & 0xFF),
                              ((FOTA_CHUNK_SIZE >> 8) & 0xFF)};
    extern IsoTpLink g_isotp_link;
    isotp_send(&g_isotp_link, ack_payload, sizeof(ack_payload));
  }
  else
  {
    uint8_t ack_payload[2] = {cmd, status};
    extern IsoTpLink g_isotp_link;
    isotp_send(&g_isotp_link, ack_payload, sizeof(ack_payload));
  }
}

bool bootVerifyFw(void)
{
  uint32_t *jump_addr = (uint32_t *)(FLASH_ADDR_START + 4);

  if ((*jump_addr) >= FLASH_ADDR_START && (*jump_addr) < FLASH_ADDR_END)
  {
    return true;
  }
  else
  {
    return false;
  }
}

void JumpToFw(void)
{
  void (**jump_func)(void) = (void (**)(void))(FLASH_ADDR_START + 4);

  bspDeInit();

  __disable_irq();

  // 벡터 테이블 위치를 앱의 시작 주소로 변경
  //  이걸 안 하면 앱에서 인터럽트 켜는 순간 죽습니다.
  SCB->VTOR = FLASH_ADDR_START;

  //  메인 스택 포인터(MSP)를 앱의 스택 시작점으로 변경
  //    (FLASH_ADDR_START 번지에는 스택 주소가 들어있음)
  __set_MSP(*(__IO uint32_t *)FLASH_ADDR_START);

  (*jump_func)();
}

// 응답을 보내는 함수 추가
void SendResponse(uint8_t cmd, uint8_t result)
{
  uint8_t data[2];
  data[0] = cmd;    // 어떤 명령에 대한 응답인지
  data[1] = result; // 0:성공, 1:실패

  // ID 0x101로 응답 전송
  canMsgWrite(0x101, data, 2);
}

static uint32_t calculate_crc32(uint32_t start_addr, uint32_t length)
{
  uint32_t crc  = 0xFFFFFFFF;
  uint8_t *data = (uint8_t *)start_addr;

  for (uint32_t i = 0; i < length; i++)
  {
    crc ^= data[i];
    for (int j = 0; j < 8; j++)
    {
      if (crc & 1)
        crc = (crc >> 1) ^ 0xEDB88320;
      else
        crc >>= 1;
    }
  }
  return ~crc;
}

// 합치기 완료!

// ==========================================
// ISO-TP 펌웨어 굽기 전용 헬퍼 함수 구현부
// ==========================================

static uint8_t bootIsoTpFlashErase(uint8_t *payload, uint16_t size)
{
  if (size < 5)
    return BOOT_ERR_FLASH_ERASE;

  fw_addr = FLASH_ADDR_FW;

  uint32_t rx_size = 0;
  rx_size          = (uint32_t)payload[1] << 0 | (uint32_t)payload[2] << 8 |
                     (uint32_t)payload[3] << 16 | (uint32_t)payload[4] << 24;

  original_fw_size = rx_size;

  if (rx_size == 0 || rx_size > FLASH_ADDR_FW_MAX_LEN)
  {
    rx_size = FLASH_ADDR_FW_MAX_LEN;
  }

  if (flashErase(FLASH_ADDR_FW, rx_size) == true)
    return BOOT_OK;
  else
    return BOOT_ERR_FLASH_ERASE;
}

static uint8_t bootIsoTpFlashWrite(uint8_t *payload, uint16_t size)
{
  uint16_t data_len = size - 1;

  while ((data_len % 4) != 0)
  {
    payload[1 + data_len] = 0xFF;
    data_len++;
  }

  if (data_len > 0)
  {
    if (flashWrite(fw_addr, &payload[1], data_len) == true)
    {
      fw_addr += data_len;
      return BOOT_OK;
    }
    else
    {
      return BOOT_ERR_FLASH_WRITE;
    }
  }
  return BOOT_OK;
}

static uint8_t bootIsoTpFlashEnd(uint8_t *payload, uint16_t size)
{
  uint32_t received_crc = 0;
  if (size >= 5)
  {
    received_crc = (uint32_t)payload[1] << 0 | (uint32_t)payload[2] << 8 |
                   (uint32_t)payload[3] << 16 | (uint32_t)payload[4] << 24;
  }

  uint32_t calculated_crc = calculate_crc32(FLASH_ADDR_FW, original_fw_size);

  if (calculated_crc == received_crc)
  {
    return BOOT_OK;
  }
  else
  {
    return BOOT_ERR_CRC;
  }
}

static uint8_t bootIsoTpJump(uint8_t cmd)
{
  if (bootVerifyFw() == true)
  {
    uint8_t ack[2] = {cmd, BOOT_OK};
    extern IsoTpLink g_isotp_link;
    isotp_send(&g_isotp_link, ack, sizeof(ack));
    delay(100);
    JumpToFw();
    return BOOT_OK;
  }
  else
  {
    return BOOT_ERR_FLASH_JUMP;
  }
}