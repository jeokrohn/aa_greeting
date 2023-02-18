#!/bin/bash
set -a
if [ -f ".env" ]; then echo "reading .env"; source .env; fi
set +a
if [ -z "$WEBEX_TOKEN" ]; then echo "WEBEX_TOKEN not set"; exit 1; fi
# run the docker image, map the current directory to the /home directory in the container and pass token
docker run --rm -v "$PWD":/home aa_greeting --token "$WEBEX_TOKEN" "$@"