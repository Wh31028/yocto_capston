#ifndef CAN_H_
#define CAN_H_

#ifdef __cplusplus
extern "C"
{
#endif

#include "hw_def.h"

#ifdef _USE_HW_CAN

#define CAN_MAX_CH HW_CAN_MAX_CH

  typedef enum
  {
    CAN_STD,
    CAN_EXT
  } CanIdType_t;

  typedef enum
  {
    CAN_DLC_0,
    CAN_DLC_1,
    CAN_DLC_2,
    CAN_DLC_3,
    CAN_DLC_4,
    CAN_DLC_5,
    CAN_DLC_6,
    CAN_DLC_7,
    CAN_DLC_8,
  } CanDlc_t;

  typedef struct
  {
    uint32_t id;
    uint8_t data[8];

    CanDlc_t dlc;
    CanIdType_t id_type;
  } can_msg_t;

  bool canInit(void);
  uint32_t canAvailable(void);
  bool canMsgRead(can_msg_t *p_mesg);
  bool canMsgWrite(uint32_t id, uint8_t *p_data, uint8_t len);

#endif

#ifdef __cplusplus
}
#endif

#endif
