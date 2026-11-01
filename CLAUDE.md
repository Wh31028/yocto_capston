# CLAUDE.md

Yocto (scarthgap) image for the BeagleBone Black (BBB) gateway of the CAN FOTA
system. Custom layer `meta-can-fota` + kas config. The STM32 bootloader/application
and the reference BBB flasher live in the separate `CanBootloader` repository.

## Working rules

- Respond to the user in Korean. Identifiers, commands, and technical terms may stay in English. New code comments in English.
- State only what repo files or executed commands show. Never claim a build or board test passed unless it was run.
- Before modifying files: check `git status`, inspect the relevant recipe/config, and treat existing uncommitted changes as the user's work.
- No commit or push without explicit approval. Keep changes minimal; don't touch unrelated files or remove functionality.
- Never write secrets (ngrok token), personal info, or absolute local paths into recipes, docs, or commits.
- Do not modify `poky/` or `meta-openembedded/` (kas-managed upstream checkouts, gitignored). Solve problems in `meta-can-fota`.
- Do not scan `build/tmp/` unless diagnosing a specific build failure. To check image contents, use `build/tmp/deploy/images/beaglebone-yocto/*.rootfs.manifest`.

## Layout

| Path | Role |
| --- | --- |
| `kas-project.yml` | Machine `beaglebone-yocto`, distro `poky`, target `core-image-minimal`; layers (poky, meta-oe/python/networking on branch `scarthgap`); `local_conf_header` → `build/conf/local.conf` |
| `meta-can-fota/recipes-apps/can-fota/` | BBB app: C flasher (`make` in `do_compile`), FastAPI dashboard, `setup-can0`/`can-fota`/`ngrok-fota` systemd services |
| `meta-can-fota/recipes-kernel/linux/` | `linux-yocto` bbappend: `can.cfg` kernel fragment, DT patch adding `can0` (+ `ECU_READY` GPIO) |
| `meta-can-fota/recipes-connectivity/usb-gadget-network/` | Dev access: `g_ncm` autoload, static IP + DHCP server on `usb0` (`10-usb0.network`) |
| `meta-can-fota/recipes-devtools/` | `ngrok` (prebuilt, `LICENSE = "CLOSED"`), FastAPI stack python3 recipes |

## Build

Always run kas from the repo root. kas clones layers and creates `build/` in the
current directory, so building elsewhere loses the sstate/downloads cache and
rebuilds from scratch.

```sh
kas build kas-project.yml                               # full image
kas build kas-project.yml --target <recipe>             # single recipe (fast check after recipe edits)
kas shell kas-project.yml -c "bitbake -e <recipe> | grep ^VAR="   # inspect final variable values
```

- Output: `build/tmp/deploy/images/beaglebone-yocto/core-image-minimal-beaglebone-yocto.rootfs.wic` (symlink; copy with `cp -L`). Filename timestamps are UTC.
- `rm_work` is enabled, so recipe `WORKDIR`s are deleted after a successful build.
- Clean build requires `meta-can-fota/recipes-apps/can-fota/files/ngrok.yml` (gitignored secret; template `ngrok.yml.sample`).

## Target access

- Dev image has `debug-tweaks` (empty root password) and OpenSSH. These are development-only.
- `eth0` usually has no cable; use SSH over the mini-USB port (NCM gadget). The BBB address is the `Address=` in `10-usb0.network`.
- Host keys change on every reflash: `ssh-keygen -R <addr>`. Keys in `authorized_keys` are lost on reflash (`ssh-copy-id -f`, since empty-password auth makes ssh-copy-id skip the copy).
- The board has no RTC battery; the clock is wrong without network time (can break TLS, e.g. ngrok).
- Ask before flashing an STM32, rebooting the board, or stopping services.

## Known issues (do not "fix" unasked; F4 in the private plan)

- Layer `refspec` uses branch names, not pinned commits (no `kas lock` yet).
- `ngrok_3.0.bb` downloads an unversioned URL; upstream changes break `do_fetch` with a checksum mismatch.
- `can-fota-BBB` sources are copied into the recipe and drift from `CanBootloader/can-fota-BBB/`. Protocol-relevant changes belong in `CanBootloader` first.
- `do_install` copies the whole `can-fota-BBB` tree (sources included) into `/usr/share/can-fota`.
- `.gitignore` uses CRLF line endings; append with CRLF and keep a newline after the last entry.

## CAN / protocol

CAN ID, command format, timeouts, and bitrate (500 kbit/s, set by `setup-can0.service`)
must stay compatible with the STM32 bootloader. The normative spec is
`CanBootloader/docs/protocol.md`; explain compatibility impact before changing anything there.

## Reporting

After a change, report root cause, files changed, what changed, verification run
(e.g. `kas build --target`, manifest check, on-board check), and remaining concerns.
