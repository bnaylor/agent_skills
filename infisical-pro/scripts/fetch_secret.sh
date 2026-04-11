#!/bin/sh
# Wrapper script for fetching secrets from Infisical using a Service Token
# Usage: ./fetch_secret.sh <SECRET_ID>

export INFISICAL_TOKEN=st.xxxx.yyyy.zzzz
export INFISICAL_API_URL=http://infisical.mink.local

# --plain ensures only the secret value is returned
# --silent suppresses informational tips/messages
/usr/bin/infisical secrets get "$1" --token="$INFISICAL_TOKEN" --plain --silent --domain $INFISICAL_API_URL --path /
