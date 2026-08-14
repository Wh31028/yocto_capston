# Yocto Build and Deployment

## Build 설정

`kas-project.yml`의 machine은 `beaglebone-yocto`, distro는 `poky`, target image는 `core-image-minimal`이다.

사용 layer:

```text
poky/meta
poky/meta-poky
poky/meta-yocto-bsp
meta-openembedded/meta-oe
meta-openembedded/meta-python
meta-openembedded/meta-networking
meta-can-fota
```

## Build 명령

```bash
kas build kas-project.yml
```

기존 build directory를 사용하는 경우:

```bash
source oe-init-build-env build
bitbake can-fota
bitbake core-image-minimal
```

## Recipe

```text
meta-can-fota/recipes-apps/can-fota/can-fota_1.0.bb
```

Recipe가 Python application, systemd unit, Python dependency, CAN 설정을 image에 포함한다.

## 설치 경로

```text
/usr/share/can-fota/
├── web_dashboard/
├── custom_lte_gateway.py
├── custom_lte_gateway_f103.py
├── isotp_lte_gateway.py
├── isotp_lte_gateway_f103.py
└── received_fw.bin
```

systemd unit:

```text
/lib/systemd/system/setup-can0.service
/lib/systemd/system/can-fota.service
/lib/systemd/system/ngrok-fota.service
```

## CAN0 / kernel

CAN service:

```text
meta-can-fota/recipes-apps/can-fota/files/setup-can0.service
```

실행 명령:

```bash
ip link set can0 up type can bitrate 500000
```

CAN 설정:

```text
meta-can-fota/recipes-kernel/linux/files/can.cfg
```

CAN0 pinmux patch:

```text
meta-can-fota/recipes-kernel/linux/files/0001-am335x-boneblack-add-can0.patch
```

`ngrok.yml`은 인증 정보가 포함될 수 있으므로 실제 token을 공개 repository에 commit하지 않아야 한다.
