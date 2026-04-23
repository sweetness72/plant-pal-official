#!/usr/bin/env bash
# Restore is NOT one-size-fits-all: the Docker volume name is Compose-prefixed.
# Read BACKUPS.md: docker volume ls → set PLANTPAL_DATA_VOLUME → then run the
# docker run / docker cp steps there. Do not use a guess like "plantpal_data".

echo "Read BACKUPS.md and set PLANTPAL_DATA_VOLUME from: docker volume ls"
exit 0
