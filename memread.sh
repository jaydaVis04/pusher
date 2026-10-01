#!/system/bin/sh

BASE=$((0x64000000))
SIZE=$((0x10000000))

ADDR=$(( $1 ))
COUNT=${2:-16}

OFFSET=$((ADDR - BASE))

if [ "$OFFSET" -lt 0 ] || [ "$OFFSET" -ge "$SIZE" ]; then
    echo "Address $1 is outside mapped range 0x64000000-0x73ffffff"
    exit 1
fi

printf "physical: 0x%x\n" "$ADDR"
printf "offset:   0x%x\n" "$OFFSET"

dd if=/dev/re_mem \
   bs=1 \
   skip="$OFFSET" \
   count="$COUNT" \
   2>/dev/null | xxd -g1
