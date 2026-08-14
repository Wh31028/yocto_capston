# FOTA Protocol

## 공통 FOTA 진입

Custom과 ISO-TP 모두 다음 frame을 전송해 FOTA 진입을 요청한다.

```text
CAN ID: 0x200
Data:   DE AD
```

## Custom

```text
Command ID: 0x100
Response ID: 0x101
```

Command:

```text
DATA  0x00
START 0x01
END   0x02
JUMP  0x03
```

흐름:

```text
FOTA request → START → 256-byte DATA block
             → ACK/NACK bitmap → END + CRC32 → JUMP
```

Custom DATA block은 최대 256바이트다. CAN frame 하나에는 header 1바이트와 firmware data 최대 7바이트가 들어간다.

## ISO-TP

```text
Command ID: 0x7E0
Response ID: 0x7E8
```

Command:

```text
FW_START       0x10
FW_DATA        0x20
FW_END         0x30
FW_JUMP_TO_FW  0x40
```

Python Gateway는 First Frame, Flow Control, Consecutive Frame을 직접 처리한다. START 응답에서 target이 전달한 chunk size를 사용한다.

## CAN bitrate

| 구성 | bitrate |
|---|---:|
| F103 Python Gateway | 500000bps |
| F407 Python Gateway | 1000000bps |
| `setup-can0.service` | 500000bps |
| dashboard 기본값 | 1000000bps |

Target과 Gateway의 CAN 설정을 일치시켜야 한다.
