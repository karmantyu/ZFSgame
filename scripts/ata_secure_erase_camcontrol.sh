#!/bin/sh
# ATA Secure Erase wrapper for FreeBSD camcontrol
# Usage: ata_secure_erase_camcontrol.sh <device>
# Accepts ada0 or /dev/ada0

DEV="$1"
if [ -z "$DEV" ]; then
  echo "usage: $0 <device>" >&2
  exit 2
fi

DEV="${DEV#/dev/}"
PASS="${ZFSGURU_ATA_PASS:-zfsguru}"
MODE="${ZFSGURU_ATA_MODE:-normal}"  # normal|enhanced

# Enable security with user password
/sbin/camcontrol security "$DEV" -U user -s "$PASS" -y
RV=$?
if [ "$RV" != "0" ]; then
  echo "camcontrol security -s failed (rv=$RV)" >&2
  exit $RV
fi

# Secure erase (normal or enhanced)
if [ "$MODE" = "enhanced" ]; then
  /sbin/camcontrol security "$DEV" -U user -h "$PASS" -y
else
  /sbin/camcontrol security "$DEV" -U user -e "$PASS" -y
fi
RV=$?
if [ "$RV" != "0" ]; then
  echo "camcontrol secure erase failed (rv=$RV)" >&2
fi
exit $RV
