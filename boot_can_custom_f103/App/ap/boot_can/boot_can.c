#include "boot_can.h"
#include "can.h" // 작성하신 CAN 드라이버 포함
#include "flash.h"
#include <stdbool.h>
#include <string.h>

// 펌웨어 데이터 버퍼 (256바이트 페이지 단위)
#define BOOT_BUF_SIZE 256
static uint8_t boot_buf[BOOT_BUF_SIZE];
static uint32_t fw_addr = FLASH_ADDR_DOWN;  // 다운로드 구역 주소
static uint32_t original_fw_size     = 0; // 원본 파일 크기 저장용 (CRC 계산용)
static uint32_t total_received_bytes = 0;

// 블록별 수신 상태 관리
static uint64_t rx_block_map            = 0;
static uint8_t expected_frames_in_block = 37; // 256/7 = 36.57 -> 37프레임
static uint32_t boot_last_rx_time       = 0;

static void SendResponse(uint8_t cmd, uint8_t result_or_seq);
static void SendNackMap(uint64_t map);
static void bootProcessStart(can_msg_t *msg);
static void bootProcessData(can_msg_t *msg, uint8_t seq);
static void bootProcessEnd(can_msg_t *msg);
static void bootProcessJump(can_msg_t *msg);
bool bootVerifyFw(void);
void JumpToFw(void);
static uint32_t calculate_crc32(uint32_t start_addr, uint32_t length);
bool bootCopyFw(uint32_t fw_size);

void bootInit(void)
{
  rx_block_map         = 0;
  total_received_bytes = 0;
  boot_last_rx_time    = millis();
}

void bootProcess(void)
{
  while (canAvailable() > 0)
  {
    can_msg_t msg;
    canMsgRead(&msg);

    // Host -> Target ID: 0x100
    if (msg.id == 0x100 && msg.dlc > 0)
    {
      boot_last_rx_time = millis(); // 통신 수신 시간 갱신

      uint8_t header = msg.data[0];
      uint8_t cmd    = GET_CMD(header);
      uint8_t seq    = GET_SEQ(header);

      switch (cmd)
      {
      case CMD_RX_START:
        bootProcessStart(&msg);
        break;
      case CMD_RX_DATA:
        bootProcessData(&msg, seq);
        break;
      case CMD_RX_END:
        bootProcessEnd(&msg);
        break;
      case CMD_RX_JUMP:
        bootProcessJump(&msg);
        break;
      }
    }
  }
}

static void bootProcessStart(can_msg_t *msg)
{
  fw_addr          = FLASH_ADDR_DOWN;
  uint8_t status   = BOOT_OK;
  uint32_t rx_size = 0;

  memset(boot_buf, 0xFF, BOOT_BUF_SIZE);
  rx_block_map         = 0;
  total_received_bytes = 0;

  if (msg->dlc >= 5)
  {
    rx_size = (uint32_t)msg->data[1] << 0;
    rx_size |= (uint32_t)msg->data[2] << 8;
    rx_size |= (uint32_t)msg->data[3] << 16;
    rx_size |= (uint32_t)msg->data[4] << 24;
  }

  original_fw_size = rx_size;

  if (rx_size == 0 || rx_size > FLASH_ADDR_FW_MAX_LEN)
  {
    rx_size = FLASH_ADDR_FW_MAX_LEN;
  }

  if (flashErase(FLASH_ADDR_DOWN, 1024 * 56) == true)
  {
    status = BOOT_OK;
  }
  else
  {
    status = BOOT_ERR_FLASH_ERASE;
  }

  if (status == BOOT_OK)
  {
    SendResponse(CMD_TX_ACK, 0);
  }
  else
  {
    SendResponse(CMD_TX_ERR, status);
  }
}

static void bootProcessData(can_msg_t *msg, uint8_t seq)
{
  if (seq > 36)
  {
    return; // Ignore invalid sequences (max 37 frames for 256 bytes)
  }

  // 1. 버퍼 복사 (7바이트 단위, 마지막 프레임은 남은 바이트만큼)
  uint32_t offset     = seq * 7;
  uint8_t payload_len = msg->dlc - 1;

  if (offset + payload_len <= BOOT_BUF_SIZE)
  {
    memcpy(&boot_buf[offset], &msg->data[1], payload_len);
  }

  // 2. 해당 시퀀스 비트 마킹
  rx_block_map |= (1ULL << seq);

  // 현재 받아야 할 프레임 개수 계산
  uint32_t rem_bytes = original_fw_size - total_received_bytes;
  uint32_t block_expected_bytes =
      (rem_bytes > BOOT_BUF_SIZE) ? BOOT_BUF_SIZE : rem_bytes;
  expected_frames_in_block = (block_expected_bytes + 6) / 7;

  // 3. 기대하는 모든 프레임을 수신했는지 확인
  uint64_t target_map = (1ULL << expected_frames_in_block) - 1;

  if ((rx_block_map & target_map) == target_map)
  {
    // 모두 정상 수신됨 -> 플래시 기록
    if (flashWrite(fw_addr, boot_buf, BOOT_BUF_SIZE) == true)
    {
      fw_addr              += BOOT_BUF_SIZE;
      total_received_bytes += block_expected_bytes;
      rx_block_map         = 0;
      
      memset(boot_buf, 0xFF, BOOT_BUF_SIZE);
      SendResponse(CMD_TX_ACK, 0); // 블록 완료 ACK
    }
    else
    {
      SendResponse(CMD_TX_ERR, BOOT_ERR_FLASH_WRITE);
    }
  }
  // 만약 마지막 프레임이 도착했는데도 전체 출석부가 덜 찼다면
  else if (seq == (expected_frames_in_block - 1))
  {
    // 출석부(비트맵) 전체를 8바이트에 담아 1개의 NACK으로 한 방에 묶어서 보고합니다!
    SendNackMap(rx_block_map);
  }
}

static void bootProcessEnd(can_msg_t *msg)
{
  uint8_t status        = BOOT_OK;
  uint32_t received_crc = 0;

  if (msg->dlc >= 5)
  {
    received_crc = (uint32_t)msg->data[1] << 0 | (uint32_t)msg->data[2] << 8 |
                   (uint32_t)msg->data[3] << 16 | (uint32_t)msg->data[4] << 24;
  }

  uint32_t calculated_crc = calculate_crc32(FLASH_ADDR_DOWN, original_fw_size);

  if (calculated_crc == received_crc)
  {
    // 검증 성공 -> 1. 메타 헤더(Size, CRC) 기록
    flashWrite(FLASH_ADDR_META_SIZE, (uint8_t *)&original_fw_size, 4);
    flashWrite(FLASH_ADDR_META_CRC, (uint8_t *)&received_crc, 4);

    // 2. 실행 구역으로 복사
    bool copy_success = bootCopyFw(original_fw_size);

    if (copy_success)
    {
      status = BOOT_OK;
      SendResponse(CMD_TX_ACK, 0);
    }
    else
    {
      status = BOOT_ERR_FLASH_WRITE;
      SendResponse(CMD_TX_ERR, status);
    }
  }
  else
  {
    status = BOOT_ERR_CRC;
    SendResponse(CMD_TX_ERR, status);
  }
}

static void bootProcessJump(can_msg_t *msg)
{
  (void)msg;
  if (bootVerifyFw() == true)
  {
    SendResponse(CMD_TX_ACK, 0);
    delay(100);
    JumpToFw();
  }
  else
  {
    SendResponse(CMD_TX_ERR, BOOT_ERR_FLASH_JUMP);
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

// 컴파일러의 스택 메모리 해제(pop) 오작동을 원천 차단하기 위해 naked(어셈블리) 함수로 점프를 구현합니다.
__attribute__((naked)) void bootJump(uint32_t sp, uint32_t pc)
{
  __asm volatile (
    "msr msp, r0\n" // r0에 담긴 sp 값으로 스택 포인터 변경
    "bx r1\n"       // r1에 담긴 pc 값으로 점프 (절대 돌아오지 않음)
  );
}

void JumpToFw(void)
{
  delay(50);
  
  // HAL 레벨의 CAN/UART 인터럽트만 안전하게 비활성화
  HAL_NVIC_DisableIRQ(USB_LP_CAN1_RX0_IRQn);
  HAL_NVIC_DisableIRQ(USB_HP_CAN1_TX_IRQn);
  HAL_NVIC_DisableIRQ(CAN1_RX1_IRQn);
  HAL_NVIC_DisableIRQ(CAN1_SCE_IRQn);
  HAL_NVIC_DisableIRQ(USART1_IRQn);

  __disable_irq();

  SCB->VTOR = FLASH_ADDR_START;

  uint32_t sp = *(__IO uint32_t *)FLASH_ADDR_START;
  uint32_t pc = *(__IO uint32_t *)(FLASH_ADDR_START + 4);

  // 어셈블리 점프 함수 호출 (이후 컴파일러의 불필요한 pop 동작 원천 차단)
  bootJump(sp, pc);
}

uint32_t bootGetLastRxTime(void)
{
  return boot_last_rx_time;
}

// 응답 헤더 구성 후 전송
void SendResponse(uint8_t cmd, uint8_t result_or_seq)
{
  uint8_t data[2];
  data[0] = PACK_HEADER(cmd, result_or_seq);
  data[1] = 0x00;

  canMsgWrite(0x101, data, 2);
}

// 출석부 전체 비트맵 정보 한 번에 전송
static void SendNackMap(uint64_t map)
{
  uint8_t data[8];
  data[0] = PACK_HEADER(CMD_TX_NACK, 0); // 명령어: NACK
  // 37개의 출석부 비트를 7바이트(56비트) 공간에 여유 있게 꽉 눌러 담음
  data[1] = (map >> 0)  & 0xFF;
  data[2] = (map >> 8)  & 0xFF;
  data[3] = (map >> 16) & 0xFF;
  data[4] = (map >> 24) & 0xFF;
  data[5] = (map >> 32) & 0xFF;
  data[6] = (map >> 40) & 0xFF;
  data[7] = (map >> 48) & 0xFF;

  canMsgWrite(0x101, data, 8); // 8바이트 꽉꽉 채워서 송신
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
      {
        crc = (crc >> 1) ^ 0xEDB88320;
      }
      else
      {
        crc >>= 1;
      }
    }
  }
  return ~crc;
}

bool bootCopyFw(uint32_t fw_size)
{
  bool copy_success = true;
  if (flashErase(FLASH_ADDR_START, fw_size) == true)
  {
    // 안전장치: 전원이 끊겼을 때를 대비해, 부팅 여부를 결정하는 '첫 번째 블록'을 가장 마지막에 복사합니다.
    uint32_t offset = BOOT_BUF_SIZE;
    while (offset < fw_size)
    {
      uint32_t copy_len = (fw_size - offset > BOOT_BUF_SIZE) ? BOOT_BUF_SIZE : (fw_size - offset);
      if (flashWrite(FLASH_ADDR_START + offset, (uint8_t *)(FLASH_ADDR_DOWN + offset), copy_len) != true)
      {
        copy_success = false;
        break;
      }
      offset += copy_len;
    }

    // 나머지 펌웨어가 모두 정상 복사되었을 때만 마지막으로 첫 번째 블록(인터럽트 벡터 테이블)을 복사!
    if (copy_success)
    {
      uint32_t first_len = (fw_size > BOOT_BUF_SIZE) ? BOOT_BUF_SIZE : fw_size;
      
      // 1. 오프셋 8부터 나머지 벡터 테이블(예: 8 ~ 255)을 먼저 복사
      if (first_len > 8)
      {
        if (flashWrite(FLASH_ADDR_START + 8, ((uint8_t *)FLASH_ADDR_DOWN) + 8, first_len - 8) != true)
        {
          copy_success = false;
        }
      }

      // 2. 가장 마지막 순간에 오프셋 0~7 (Initial SP 및 Reset Vector) 복사!!
      // 이렇게 하면 SP와 Reset Vector가 온전히 적히기 전까지는 부트로더가 절대 점프하지 않음.
      if (copy_success)
      {
        if (flashWrite(FLASH_ADDR_START, (uint8_t *)FLASH_ADDR_DOWN, 8) != true)
        {
          copy_success = false;
        }
      }
    }
  }
  else
  {
    copy_success = false;
  }
  return copy_success;
}

bool bootAutoRecover(void)
{
  // 1. 읽어온 메타 헤더
  uint32_t meta_size = *(uint32_t *)FLASH_ADDR_META_SIZE;
  uint32_t meta_crc  = *(uint32_t *)FLASH_ADDR_META_CRC;

  // 2. 유효한 사이즈인지 검사
  if (meta_size == 0 || meta_size > FLASH_ADDR_FW_MAX_LEN || meta_size == 0xFFFFFFFF)
  {
    return false; // 복구 불가
  }

  // 3. 다운로드 구역의 CRC 계산
  uint32_t calc_crc = calculate_crc32(FLASH_ADDR_DOWN, meta_size);

  // 4. CRC가 일치하면 다운로드 구역이 온전하다는 뜻! 복사 재개!
  if (calc_crc == meta_crc)
  {
    // 다운로드 구역이 온전하므로 다시 복사를 시도합니다.
    if (bootCopyFw(meta_size) == true)
    {
      return true; // 복구 성공
    }
  }

  return false;
}