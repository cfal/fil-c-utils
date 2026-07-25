#!/usr/bin/env bash
# Write one real container per 7-Zip format handler into /out.
#
# Each generator is allowed to fail: the tool may be missing from a future base
# image, or may refuse on a given kernel. A missing format costs coverage, not
# correctness, so the run reports what it produced and keeps going.
set -u

OUT=/out
SRC=/src
mkdir -p "${OUT}" "${SRC}"

# Payload with enough structure that compressing filesystems have real work to
# do, and enough size that images are not entirely metadata.
mkdir -p "${SRC}/dir/sub"
printf 'the quick brown fox jumps over the lazy dog\n%.0s' $(seq 1 400) > "${SRC}/text.txt"
head -c 65536 /dev/urandom > "${SRC}/random.bin"
printf 'nested\n' > "${SRC}/dir/sub/leaf.txt"
printf 'unicode: éà中文\n' > "${SRC}/dir/unicode.txt"
ln -sf text.txt "${SRC}/link.txt" 2>/dev/null
cp /bin/true "${SRC}/dir/elf.bin" 2>/dev/null

made=0
skipped=""
MANIFEST="${OUT}/manifest.tsv"
: > "${MANIFEST}"

# Each container is recorded with the 7-Zip handler it is meant to reach.
# The fuzzer replays it both by autodetection and with an explicit -t, because
# a mutation that lands on the magic bytes otherwise stops at dispatch and
# never enters the handler being tested.
emit() {  # emit <name> <7z-type> <command...>
    local name="$1" type="$2"; shift 2
    if "$@" > "/tmp/${name}.log" 2>&1 && [ -s "${OUT}/${name}" ]; then
        made=$((made + 1))
        printf '%s\t%s\n' "${name}" "${type}" >> "${MANIFEST}"
        printf '  ok    %-24s %-9s %s bytes\n' "${name}" "${type}" "$(stat -c%s "${OUT}/${name}")"
    else
        rm -f "${OUT}/${name}"
        skipped="${skipped} ${name}"
        printf '  skip  %-24s %s\n' "${name}" "${type}"
    fi
}

# ---- disk images: qemu-img covers five handlers at once ---------------------
qcow_base=/tmp/base.raw
head -c 4194304 /dev/zero > "${qcow_base}"
mkfs.ext4 -q -F -b 1024 -d "${SRC}" "${qcow_base}" 2>/dev/null

emit fmt-qcow2.qcow2 QCOW  qemu-img convert -f raw -O qcow2 "${qcow_base}" "${OUT}/fmt-qcow2.qcow2"
emit fmt-qcow.qcow QCOW    qemu-img convert -f raw -O qcow  "${qcow_base}" "${OUT}/fmt-qcow.qcow"
emit fmt-vmdk.vmdk VMDK    qemu-img convert -f raw -O vmdk  "${qcow_base}" "${OUT}/fmt-vmdk.vmdk"
emit fmt-vhd.vhd VHD      qemu-img convert -f raw -O vpc   "${qcow_base}" "${OUT}/fmt-vhd.vhd"
emit fmt-vhdx.vhdx VHDX    qemu-img convert -f raw -O vhdx  "${qcow_base}" "${OUT}/fmt-vhdx.vhdx"
emit fmt-vdi.vdi VDI      qemu-img convert -f raw -O vdi   "${qcow_base}" "${OUT}/fmt-vdi.vdi"

# ---- filesystems ------------------------------------------------------------
emit fmt-ext4.img Ext sh -c "head -c 4194304 /dev/zero > '${OUT}/fmt-ext4.img' \
    && mkfs.ext4 -q -F -b 1024 -d '${SRC}' '${OUT}/fmt-ext4.img'"

emit fmt-ext2.img Ext sh -c "head -c 2097152 /dev/zero > '${OUT}/fmt-ext2.img' \
    && mkfs.ext2 -q -F -b 1024 -d '${SRC}' '${OUT}/fmt-ext2.img'"

emit fmt-squashfs.squashfs SquashFS mksquashfs "${SRC}" "${OUT}/fmt-squashfs.squashfs" -noappend -quiet
emit fmt-squashfs-xz.squashfs SquashFS mksquashfs "${SRC}" "${OUT}/fmt-squashfs-xz.squashfs" \
    -noappend -quiet -comp xz

# FAT12, FAT16 and FAT32 have materially different on-disk layouts, and each
# size below is one mkfs.vfat accepts for that variant.
fat() {  # fat <bits> <bytes> <path>
    head -c "$2" /dev/zero > "$3" \
        && mkfs.vfat -F "$1" "$3" >/dev/null \
        && MTOOLS_SKIP_CHECK=1 mcopy -i "$3" "${SRC}/text.txt" "${SRC}/random.bin" ::
}
emit fmt-fat12.img FAT fat 12  4194304 "${OUT}/fmt-fat12.img"
emit fmt-fat16.img FAT fat 16 33554432 "${OUT}/fmt-fat16.img"
emit fmt-fat32.img FAT fat 32 34603008 "${OUT}/fmt-fat32.img"

emit fmt-ntfs.img NTFS sh -c "head -c 8388608 /dev/zero > '${OUT}/fmt-ntfs.img' \
    && mkfs.ntfs -F -Q -f '${OUT}/fmt-ntfs.img' >/dev/null"

emit fmt-hfsplus.hfs HFS sh -c "head -c 4194304 /dev/zero > '${OUT}/fmt-hfsplus.hfs' \
    && mkfs.hfsplus '${OUT}/fmt-hfsplus.hfs' >/dev/null"

# ---- optical images ---------------------------------------------------------
emit fmt-iso9660.iso Iso genisoimage -quiet -o "${OUT}/fmt-iso9660.iso" "${SRC}"
emit fmt-iso-rr.iso Iso  genisoimage -quiet -R -J -o "${OUT}/fmt-iso-rr.iso" "${SRC}"
emit fmt-udf.iso Udf     genisoimage -quiet -udf -o "${OUT}/fmt-udf.iso" "${SRC}"
emit fmt-udf-only.udf Udf sh -c "head -c 4194304 /dev/zero > '${OUT}/fmt-udf-only.udf' \
    && mkudffs --utf8 --media-type=hd '${OUT}/fmt-udf-only.udf' >/dev/null"

# ---- partition tables -------------------------------------------------------
emit fmt-gpt.gpt GPT sh -c "head -c 4194304 /dev/zero > '${OUT}/fmt-gpt.gpt' \
    && sgdisk -n 1:2048:4096 -t 1:8300 '${OUT}/fmt-gpt.gpt' >/dev/null"
emit fmt-mbr.mbr MBR sh -c "head -c 4194304 /dev/zero > '${OUT}/fmt-mbr.mbr' \
    && printf 'label: dos\n1 : start=2048, size=2048, type=83\n' | sfdisk '${OUT}/fmt-mbr.mbr' >/dev/null"

# ---- packages and archives --------------------------------------------------
emit fmt-ar.a Ar        sh -c "cd '${SRC}' && ar rcs '${OUT}/fmt-ar.a' text.txt random.bin"
emit fmt-cpio.cpio Cpio   sh -c "cd '${SRC}' && find . | cpio -o -H newc --quiet > '${OUT}/fmt-cpio.cpio'"
emit fmt-cpio-odc.cpio Cpio sh -c "cd '${SRC}' && find . | cpio -o -H odc --quiet > '${OUT}/fmt-cpio-odc.cpio'"
emit fmt-cab.cab Cab     sh -c "cd '${SRC}' && gcab -c '${OUT}/fmt-cab.cab' text.txt random.bin"
emit fmt-cab-z.cab Cab   sh -c "cd '${SRC}' && gcab -c -z '${OUT}/fmt-cab-z.cab' text.txt random.bin"
emit fmt-arj.arj Arj     sh -c "cd '${SRC}' && arj a -i '${OUT}/fmt-arj.arj' text.txt random.bin >/dev/null"
emit fmt-compress.Z Z  sh -c "compress -c '${SRC}/text.txt' > '${OUT}/fmt-compress.Z'"

emit fmt-deb.deb Ar sh -c "
    mkdir -p /tmp/pkg/DEBIAN /tmp/pkg/usr/share/probe
    printf 'Package: probe\nVersion: 1.0\nArchitecture: all\nMaintainer: t <t@example.com>\nDescription: probe\n' > /tmp/pkg/DEBIAN/control
    cp '${SRC}/text.txt' /tmp/pkg/usr/share/probe/
    dpkg-deb --build /tmp/pkg '${OUT}/fmt-deb.deb' >/dev/null"

emit fmt-rpm.rpm Rpm sh -c "
    mkdir -p /root/rpmbuild/BUILD /root/rpmbuild/RPMS /root/rpmbuild/SOURCES \
             /root/rpmbuild/SPECS /root/rpmbuild/SRPMS
    printf 'Name: probe\nVersion: 1\nRelease: 1\nSummary: probe\nLicense: MIT\nBuildArch: noarch\n%%description\nprobe\n%%install\nmkdir -p %%{buildroot}/usr/share/probe\ncp /src/text.txt %%{buildroot}/usr/share/probe/\n%%files\n/usr/share/probe/text.txt\n' > /root/rpmbuild/SPECS/probe.spec
    rpmbuild -bb /root/rpmbuild/SPECS/probe.spec >/dev/null 2>&1
    cp /root/rpmbuild/RPMS/noarch/probe-1-1.noarch.rpm '${OUT}/fmt-rpm.rpm'"

# ---- executables and encodings ---------------------------------------------
# 7-Zip parses PE and ELF to find self-extracting payloads, so both are live
# attack surface even though neither is an archive.
emit fmt-elf.elf ELF     cp /bin/true "${OUT}/fmt-elf.elf"
emit fmt-elf-obj.obj ELF sh -c "cp /usr/lib/x86_64-linux-gnu/crt1.o '${OUT}/fmt-elf-obj.obj' 2>/dev/null \
    || objcopy -O elf64-x86-64 /bin/true '${OUT}/fmt-elf-obj.obj'"
emit fmt-pe64.exe PE    objcopy -O pei-x86-64 /bin/true "${OUT}/fmt-pe64.exe"
emit fmt-pe32.exe PE    objcopy -O pei-i386   /bin/true "${OUT}/fmt-pe32.exe"
emit fmt-ihex.ihex IHex   objcopy -O ihex /bin/true "${OUT}/fmt-ihex.ihex"
emit fmt-base64.b64 Base64  sh -c "base64 '${SRC}/random.bin' > '${OUT}/fmt-base64.b64'"

emit fmt-sparse.simg Sparse sh -c "head -c 4194304 /dev/zero > /tmp/sp.raw \
    && mkfs.ext4 -q -F -b 1024 -d '${SRC}' /tmp/sp.raw \
    && img2simg /tmp/sp.raw '${OUT}/fmt-sparse.simg'"

# ---- 7-Zip's own less-used containers --------------------------------------
# Split needs the whole .00N chain present or it cannot rejoin the payload.
emit fmt-split.001 Split sh -c "cd '${SRC}' && zip -q -r /tmp/split.zip . \
    && split -b 20000 -d -a 3 /tmp/split.zip /tmp/part. \
    && i=1; for p in /tmp/part.*; do cp \"\$p\" \"\$(printf '${OUT}/fmt-split.%03d' \$i)\"; i=\$((i+1)); done"

printf '\n%d containers written to %s\n' "${made}" "${OUT}"
[ -n "${skipped}" ] && printf 'not produced:%s\n' "${skipped}"
exit 0
