# Generates real container files for the format handlers 7-Zip compiles in.
#
# 7-Zip opens about sixty container formats, and its published vulnerability
# history is concentrated in the filesystem and installer handlers rather than
# in 7z or zip. Fuzzing those handlers needs genuine images to mutate, and the
# tools that produce them are not the ones a build host normally carries, so
# they are assembled here instead of being required of the host.
#
# Every image is built from a plain file. Nothing here needs a loop device or
# any privilege.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        qemu-utils squashfs-tools genisoimage xorriso cpio rpm gcab \
        ntfs-3g dosfstools mtools gdisk fdisk ncompress udftools \
        hfsprogs arj lhasa binutils binutils-x86-64-linux-gnu dpkg-dev \
        cabextract zip xz-utils \
        android-sdk-libsparse-utils \
        bzip2 gzip zstd file coreutils util-linux e2fsprogs \
    && rm -rf /var/lib/apt/lists/*

COPY generate.sh /generate.sh
RUN chmod +x /generate.sh

ENTRYPOINT ["/generate.sh"]
