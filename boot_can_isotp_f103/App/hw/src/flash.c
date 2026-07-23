#include "flash.h"
#include "cli.h"

#ifdef _USE_HW_FLASH

#define FLASH_PAGE_SIZE 1024

#ifdef _USE_HW_CLI
static void cliFlash(cli_args_t *args);
#endif

bool flashInit(void)
{
#ifdef _USE_HW_CLI
  cliAdd("flash", cliFlash);
#endif
  return true;
}

bool flashErase(uint32_t addr, uint32_t length)
{
  bool ret = false;
  HAL_StatusTypeDef status;
  FLASH_EraseInitTypeDef init;
  uint32_t page_error;

  if (length == 0) return true;

  // --- [보안/안전 장치] 부트로더 및 허용되지 않은 영역 지우기 방지 ---
  if (addr < FLASH_ADDR_START || (addr + length) > FLASH_ADDR_END)
  {
    return false;
  }
  // -----------------------------------------------------------------

  HAL_FLASH_Unlock();

  init.TypeErase   = FLASH_TYPEERASE_PAGES;
  init.Banks       = FLASH_BANK_1;
  init.PageAddress = addr & ~(FLASH_PAGE_SIZE - 1); // Round down to page boundary
  
  uint32_t end_addr = addr + length - 1;
  uint32_t end_page = end_addr & ~(FLASH_PAGE_SIZE - 1);
  init.NbPages      = ((end_page - init.PageAddress) / FLASH_PAGE_SIZE) + 1;

  status = HAL_FLASHEx_Erase(&init, &page_error);
  if (status == HAL_OK)
  {
    ret = true;
  }

  HAL_FLASH_Lock();

  return ret;
}

bool flashWrite(uint32_t addr, uint8_t *p_data, uint32_t length)
{
  bool ret = true;
  HAL_StatusTypeDef status;

  // 안전장치: 4의 배수가 아니면 쓰지 않고 에러 반환
  if (length % 4 != 0)
  {
    return false;
  }

  // --- [보안/안전 장치] 부트로더 및 허용되지 않은 영역 쓰기 방지 ---
  if (addr < FLASH_ADDR_START || (addr + length) > FLASH_ADDR_END)
  {
    return false;
  }
  // -----------------------------------------------------------------

  HAL_FLASH_Unlock();

  // 4바이트씩 건너뛰며 반복
  for (int i = 0; i < length; i += 4)
  {
    uint32_t data32;

    // 4개의 1바이트를 -> 1개의 32비트 변수로 합침 (Little Endian)
    data32 = (uint32_t)p_data[i + 0] << 0 | (uint32_t)p_data[i + 1] << 8 |
             (uint32_t)p_data[i + 2] << 16 | (uint32_t)p_data[i + 3] << 24;

    // FLASH_TYPEPROGRAM_WORD (4바이트) 모드로 기록
    status =
        HAL_FLASH_Program(FLASH_TYPEPROGRAM_WORD, addr + i, (uint64_t)data32);

    if (status != HAL_OK)
    {
      ret = false;
      break;
    }
  }

  HAL_FLASH_Lock();

  return ret;
}

bool flashRead(uint32_t addr, uint8_t *p_data, uint32_t length)
{
  bool ret        = true;
  uint8_t *p_byte = (uint8_t *)addr;

  for (int i = 0; i < length; i++)
  {
    p_data[i] = p_byte[i];
  }

  return ret;
}

#ifdef _USE_HW_CLI
void cliFlash(cli_args_t *args)
{
  bool ret = false;

  if (args->argc == 1 && args->isStr(0, "info") == true)
  {
    cliPrintf("Flash Page Size : %d Bytes\n\r", FLASH_PAGE_SIZE);
    cliPrintf("Flash Start Addr: 0x08000000\n\r");
    cliPrintf("Flash End Addr  : 0x0801FFFF (128KB)\n\r");
    ret = true;
  }

  if (args->argc == 3 && args->isStr(0, "read") == true)
  {
    uint32_t addr;
    uint32_t length;

    addr   = (uint32_t)args->getData(1);
    length = (uint32_t)args->getData(2);

    for (int i = 0; i < length; i++)
    {
      cliPrintf("0x%X : 0x%X\n\r", addr + i, *((uint8_t *)(addr + i)));
    }

    ret = true;
  }

  if (args->argc == 3 && args->isStr(0, "erase") == true)
  {
    uint32_t addr;
    uint32_t length;

    addr   = (uint32_t)args->getData(1);
    length = (uint32_t)args->getData(2);

    if (flashErase(addr, length) == true)
    {
      cliPrintf("Erase OK\n\r");
    }
    else
    {
      cliPrintf("Erase Fail\n\r");
    }
  }

  if (args->argc == 3 && args->isStr(0, "write") == true)
  {
    uint32_t addr;
    uint32_t data;

    addr = (uint32_t)args->getData(1);
    data = (uint32_t)args->getData(2);

    if (flashWrite(addr, (uint8_t *)&data, 4) == true)
    {
      cliPrintf("Write OK\n\r");
    }
    else
    {
      cliPrintf("Write Fail\n\r");
    }

    ret = true;
  }

  if (ret != true)
  {
    cliPrintf("flash info\n\r");
    cliPrintf("flash read  addr length\n\r");
    cliPrintf("flash erase addr length\n\r");
    cliPrintf("flash write addr data\n\r");
  }
}
#endif

#endif