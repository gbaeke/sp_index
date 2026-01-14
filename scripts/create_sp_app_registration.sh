#!/bin/bash

# Script to create Azure AD app registration for SharePoint indexing with federated credentials
# This app is used by Azure AI Search to authenticate to SharePoint via managed identity

set -e  # Exit on error

# Default values
APP_NAME="SPIndexer"
SHAREPOINT_ENDPOINT=""
SEARCH_SERVICE_NAME=""
RG=""

# Function to display usage
usage() {
  cat <<EOF
Usage: $0 -s <search-service-name> -g <resource-group> -e <sharepoint-endpoint> [-n <app-name>]

Creates an Azure AD app registration for SharePoint indexing with federated credentials.

Required arguments:
  -s    Azure AI Search service name
  -g    Resource group containing the search service
  -e    SharePoint endpoint (e.g., https://yourcompany.sharepoint.com)

Optional arguments:
  -n    App registration name (default: SPIndexer)
  -h    Display this help message

Example:
  $0 -s ais-geba-sp -g rg-geba-sp -e https://geertbaekehotmail.sharepoint.com -n SPIndexer
EOF
  exit 1
}

# Parse command line arguments
while getopts "s:g:e:n:h" opt; do
  case $opt in
    s) SEARCH_SERVICE_NAME="$OPTARG" ;;
    g) RG="$OPTARG" ;;
    e) SHAREPOINT_ENDPOINT="$OPTARG" ;;
    n) APP_NAME="$OPTARG" ;;
    h) usage ;;
    *) usage ;;
  esac
done

# Validate required arguments
if [[ -z "$SEARCH_SERVICE_NAME" || -z "$RG" || -z "$SHAREPOINT_ENDPOINT" ]]; then
  echo "Error: Missing required arguments"
  usage
fi

echo "============================================"
echo "SharePoint App Registration Setup"
echo "============================================"
echo "App Name: $APP_NAME"
echo "Search Service: $SEARCH_SERVICE_NAME"
echo "Resource Group: $RG"
echo "SharePoint Endpoint: $SHAREPOINT_ENDPOINT"
echo "============================================"
echo ""

# Get tenant ID
echo "Retrieving tenant ID..."
TENANT_ID=$(az account show --query tenantId -o tsv)
echo "Tenant ID: $TENANT_ID"
echo ""

# Get search service managed identity object ID
echo "Retrieving Azure AI Search managed identity..."
MANAGED_IDENTITY_OBJECT_ID=$(az search service show \
  --name "$SEARCH_SERVICE_NAME" \
  --resource-group "$RG" \
  --query "identity.principalId" -o tsv)

if [[ -z "$MANAGED_IDENTITY_OBJECT_ID" ]]; then
  echo "Error: No managed identity found for search service '$SEARCH_SERVICE_NAME'"
  echo "Ensure the search service has system-assigned managed identity enabled."
  exit 1
fi

echo "Managed Identity Object ID: $MANAGED_IDENTITY_OBJECT_ID"
echo ""

# Check if app registration already exists
echo "Checking if app registration '$APP_NAME' already exists..."
EXISTING_APP_ID=$(az ad app list --display-name "$APP_NAME" --query "[0].appId" -o tsv)

if [[ -n "$EXISTING_APP_ID" ]]; then
  echo "App registration '$APP_NAME' already exists (App ID: $EXISTING_APP_ID)"
  APP_ID="$EXISTING_APP_ID"
  echo ""
else
  # Create app registration
  echo "Creating app registration '$APP_NAME'..."
  APP_ID=$(az ad app create \
    --display-name "$APP_NAME" \
    --sign-in-audience AzureADMyOrg \
    --query appId -o tsv)
  echo "App registration created with App ID: $APP_ID"
  echo ""
fi

# Get Microsoft Graph resource app ID
MS_GRAPH_RESOURCE_APP_ID="00000003-0000-0000-c000-000000000000"

# Microsoft Graph permission IDs (application permissions / Role type)
# Files.Read.All: 01d4889c-1287-42c6-ac1f-5d1e02578ef6
# Sites.FullControl.All: a82116e5-55eb-4c41-a434-62fe8a61c773
# Sites.Read.All: 332a536c-c7ef-4017-ab91-336970924f0d

echo "Configuring Microsoft Graph API permissions..."

# Add required resource access for Microsoft Graph (Files.Read.All, Sites.FullControl.All, Sites.Read.All)
az ad app update --id "$APP_ID" --required-resource-accesses @- <<EOF
[
  {
    "resourceAppId": "$MS_GRAPH_RESOURCE_APP_ID",
    "resourceAccess": [
      {
        "id": "01d4889c-1287-42c6-ac1f-5d1e02578ef6",
        "type": "Role"
      },
      {
        "id": "a82116e5-55eb-4c41-a434-62fe8a61c773",
        "type": "Role"
      },
      {
        "id": "332a536c-c7ef-4017-ab91-336970924f0d",
        "type": "Role"
      }
    ]
  }
]
EOF

echo "Microsoft Graph permissions configured (Files.Read.All, Sites.FullControl.All, Sites.Read.All)"
echo ""

# Create service principal if it doesn't exist
echo "Ensuring service principal exists..."
SP_OBJECT_ID=$(az ad sp list --filter "appId eq '$APP_ID'" --query "[0].id" -o tsv)

if [[ -z "$SP_OBJECT_ID" ]]; then
  echo "Creating service principal..."
  az ad sp create --id "$APP_ID" >/dev/null
  echo "Service principal created."
else
  echo "Service principal already exists."
fi
echo ""

# Grant admin consent for the permissions
echo "Granting admin consent for Microsoft Graph permissions..."
echo "Note: This requires Global Administrator or Application Administrator role."
az ad app permission admin-consent --id "$APP_ID" || {
  echo "Warning: Failed to grant admin consent automatically."
  echo "Please grant admin consent manually in the Azure Portal:"
  echo "1. Go to Azure Portal > App registrations > $APP_NAME"
  echo "2. Navigate to 'API permissions'"
  echo "3. Click 'Grant admin consent for <your tenant>'"
  echo ""
}
echo ""

# Check if federated credential already exists
echo "Checking for existing federated credentials..."
EXISTING_FED_CRED=$(az ad app federated-credential list --id "$APP_ID" \
  --query "[?subject=='$MANAGED_IDENTITY_OBJECT_ID'].name" -o tsv)

if [[ -n "$EXISTING_FED_CRED" ]]; then
  echo "Federated credential '$EXISTING_FED_CRED' already exists for this managed identity."
  FED_CRED_NAME="$EXISTING_FED_CRED"
  FED_CRED_OBJECT_ID="$MANAGED_IDENTITY_OBJECT_ID"
else
  # Create federated credential for the managed identity
  FED_CRED_NAME="search_fed_cred"
  echo "Creating federated credential '$FED_CRED_NAME'..."
  
  az ad app federated-credential create \
    --id "$APP_ID" \
    --parameters @- <<EOF
{
  "name": "$FED_CRED_NAME",
  "issuer": "https://login.microsoftonline.com/$TENANT_ID/v2.0",
  "subject": "$MANAGED_IDENTITY_OBJECT_ID",
  "audiences": ["api://AzureADTokenExchange"],
  "description": "Federated credential for Azure AI Search managed identity"
}
EOF

  echo "Federated credential created: $FED_CRED_NAME"
  FED_CRED_OBJECT_ID="$MANAGED_IDENTITY_OBJECT_ID"
fi
echo ""

# Generate connection string
CONNECTION_STRING="SharePointOnlineEndpoint=$SHAREPOINT_ENDPOINT;ApplicationId=$APP_ID;FederatedCredentialObjectId=$FED_CRED_OBJECT_ID;TenantId=$TENANT_ID"

echo "============================================"
echo "Setup Complete!"
echo "============================================"
echo ""
echo "App Registration Details:"
echo "  Name: $APP_NAME"
echo "  Application (Client) ID: $APP_ID"
echo "  Tenant ID: $TENANT_ID"
echo "  Managed Identity Object ID: $FED_CRED_OBJECT_ID"
echo "  Federated Credential: $FED_CRED_NAME"
echo ""
echo "Microsoft Graph Permissions Granted:"
echo "  - Files.Read.All (Application)"
echo "  - Sites.FullControl.All (Application)"
echo "  - Sites.Read.All (Application)"
echo ""
echo "Connection String for .env:"
echo "============================================"
echo "CONNECTION_STRING=\"$CONNECTION_STRING\""
echo "============================================"
echo ""
echo "Next Steps:"
echo "1. Copy the CONNECTION_STRING to your .env file"
echo "2. Verify admin consent was granted in Azure Portal"
echo "3. Create your Azure AI Search datasource with this connection string"
echo ""
