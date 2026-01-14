#!/usr/bin/env bash
set -euo pipefail

# Function to display usage
usage() {
  cat << EOF
Usage: $0 -g <resource-group> [-y]

Required arguments:
  -g    Resource group name to delete

Optional arguments:
  -y    Skip confirmation prompt (auto-confirm deletion)
  -h    Display this help message

Example:
  $0 -g rg-sp
  $0 -g rg-sp -y

EOF
  exit 1
}

# Initialize variables
RG=""
AUTO_CONFIRM=false

# Parse command line arguments
while getopts "g:yh" opt; do
  case $opt in
    g) RG="$OPTARG" ;;
    y) AUTO_CONFIRM=true ;;
    h) usage ;;
    *) usage ;;
  esac
done

# Check if required argument is provided
if [[ -z "$RG" ]]; then
  echo "Error: Resource group name is required." >&2
  echo "" >&2
  usage
fi

# Check if az CLI is available
if ! command -v az >/dev/null 2>&1; then
  echo "az CLI not found. Install Azure CLI and login to the desired subscription." >&2
  exit 2
fi

# Ensure we are logged in and have a subscription
if ! az account show >/dev/null 2>&1; then
  echo "Not logged in to Azure CLI. Run 'az login' and select the correct subscription." >&2
  exit 2
fi

# Check if resource group exists
if ! az group show --name "$RG" >/dev/null 2>&1; then
  echo "Resource group '$RG' does not exist. Nothing to delete." >&2
  exit 0
fi

# Confirmation prompt (unless auto-confirm is enabled)
if [[ "$AUTO_CONFIRM" != true ]]; then
  echo "WARNING: You are about to delete resource group '$RG' and ALL its resources."
  read -p "Are you sure you want to continue? (yes/no): " -r
  echo
  if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo "Deletion cancelled."
    exit 0
  fi
fi

echo "Deleting resource group '$RG'..."
az group delete --name "$RG" --yes --no-wait
echo "Resource group '$RG' deletion initiated (running in background)."
echo "Run 'az group show --name $RG' to check if deletion is complete."
