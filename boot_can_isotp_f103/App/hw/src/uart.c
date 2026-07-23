#include "uart.h"

#ifdef _USE_HW_UART
#include "qbuffer.h"

#define UART_RX_BUF_LENGTH 512

// 내부 참조 데이터 정의
//
typedef struct
{
  bool is_open;
  uint32_t baud;
  qbuffer_t q_rx;
  uint8_t q_rx_buf[UART_RX_BUF_LENGTH];

  UART_HandleTypeDef *p_huart;
} uart_tbl_t;

// 외부 참조 데이터
//
extern UART_HandleTypeDef huart1;

// 내부 참조 데이터
//
static bool is_init = false;

static uart_tbl_t uart_tbl[UART_MAX_CH];

bool uartInit(void)
{

  for (int i = 0; i < UART_MAX_CH; i++)
  {
    uart_tbl[i].is_open = false;
    uart_tbl[i].baud    = 115200;
    uart_tbl[i].p_huart = NULL;

    qbufferCreate(&uart_tbl[i].q_rx, &uart_tbl[i].q_rx_buf[0],
                  UART_RX_BUF_LENGTH);
  }

  is_init = true;

  return is_init;
}

bool uartDeInit(void)
{
  is_init = false;
  return true;
}

bool uartIsInit(void) { return is_init; }

bool uartOpen(uint8_t ch, uint32_t baud)
{
  bool ret = false;

  switch (ch)
  {
  case _DEF_UART1:
    // UART 하드웨어 초기화
    //
    uart_tbl[ch].p_huart                = &huart1;
    uart_tbl[ch].p_huart->Init.BaudRate = baud;
    uart_tbl[ch].baud                   = baud;
    uart_tbl[ch].is_open                = false;

    HAL_UART_DeInit(uart_tbl[ch].p_huart);
    if (HAL_UART_Init(uart_tbl[ch].p_huart) == HAL_OK)
    {
      uart_tbl[ch].is_open = true;
    }

    if (uart_tbl[ch].is_open)
    {
      HAL_StatusTypeDef hal_ret;

      hal_ret = HAL_UART_Receive_DMA(uart_tbl[ch].p_huart,
                                     uart_tbl[ch].q_rx_buf, UART_RX_BUF_LENGTH);
      if (hal_ret != HAL_OK)
      {
        uart_tbl[ch].is_open = false;
      }

      // 수신버퍼 설정
      //
      uart_tbl[ch].q_rx.in =
          uart_tbl[ch].q_rx.len - uart_tbl[ch].p_huart->hdmarx->Instance->CNDTR;
      uart_tbl[ch].q_rx.out = uart_tbl[ch].q_rx.in;
    }
    ret = uart_tbl[ch].is_open;
    break;

  default:
    break;
  }

  return ret;
}

bool uartIsOpen(uint8_t ch)
{
  if (ch >= UART_MAX_CH)
    return false;

  return uart_tbl[ch].is_open;
}

bool uartClose(uint8_t ch)
{
  if (ch >= UART_MAX_CH)
    return false;

  uart_tbl[ch].is_open = false;

  return true;
}

uint32_t uartAvailable(uint8_t ch)
{
  uint32_t ret = 0;

  if (ch >= UART_MAX_CH)
    return false;

  uart_tbl[ch].q_rx.in =
      uart_tbl[ch].q_rx.len - uart_tbl[ch].p_huart->hdmarx->Instance->CNDTR;
  ret = qbufferAvailable(&uart_tbl[ch].q_rx);

  return ret;
}

bool uartFlush(uint8_t ch)
{
  uint32_t pre_time;

  if (ch >= UART_MAX_CH)
    return false;

  pre_time = millis();
  while (uartAvailable(ch))
  {
    if (millis() - pre_time >= 10)
    {
      break;
    }
    uartRead(ch);
  }
  return true;
}

uint8_t uartRead(uint8_t ch)
{
  uint8_t ret = 0;

  qbufferRead(&uart_tbl[ch].q_rx, &ret, 1);

  return ret;
}

uint32_t uartWrite(uint8_t ch, uint8_t *p_data, uint32_t length)
{
  uint32_t ret = 0;

  if (ch >= UART_MAX_CH)
    return false;

  if (HAL_UART_Transmit(uart_tbl[ch].p_huart, p_data, length, 100) == HAL_OK)
  {
    ret = length;
  }

  return ret;
}

uint32_t uartPrintf(uint8_t ch, const char *fmt, ...)
{
  char buf[256];
  va_list args;
  int len;
  uint32_t ret;

  if (ch >= UART_MAX_CH)
    return false;

  va_start(args, fmt);
  len = vsnprintf(buf, 256, fmt, args);

  ret = uartWrite(ch, (uint8_t *)buf, len);

  va_end(args);

  return ret;
}

uint32_t uartGetBaud(uint8_t ch)
{
  if (ch >= UART_MAX_CH)
    return false;

  return uart_tbl[ch].baud;
}

#endif