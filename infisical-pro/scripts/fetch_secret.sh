#!/bin/bash
# OpenClaw exec provider for Infisical
# Protocol: JSON stdin -> JSON stdout (required by OpenClaw exec provider)
# Input:  { "protocolVersion": 1, "provider": "infisical", "ids": ["KEY1", "KEY2"] }
# Output: { "protocolVersion": 1, "values": { "KEY1": "val1" }, "errors": { "KEY2": {"message":"..."} } }
#
# Requires: jq
# Install:  sudo apt-get install jq

INFISICAL_TOKEN="st.xxxx.yyyy.zzzz"
INFISICAL_API_URL="http://your-infisical-instance"

input=$(cat)
ids=$(echo "$input" | jq -r '.ids[]')

values="{}"
errors="{}"

while IFS= read -r id; do
  value=$(/usr/bin/infisical secrets get "$id" \
    --token="$INFISICAL_TOKEN" \
    --plain --silent \
    --domain "$INFISICAL_API_URL" 2>/dev/null)
  if [ -n "$value" ]; then
    values=$(echo "$values" | jq --arg k "$id" --arg v "$value" '. + {($k): $v}')
  else
    errors=$(echo "$errors" | jq --arg k "$id" '. + {($k): {"message": "not found or empty"}}')
  fi
done <<< "$ids"

jq -n --argjson v "$values" --argjson e "$errors" \
  '{"protocolVersion": 1, "values": $v} + (if ($e | length) > 0 then {"errors": $e} else {} end)'
