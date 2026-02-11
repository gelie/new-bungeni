import httpx
from django.conf import settings
from django.utils import timezone

from .models import SharePointToken


def get_application_token():
    """
    Get SharePoint access token using application credentials (client credentials flow).
    Returns the parsed JSON response containing the access token.
    """
    print("get_application_token() called")

    # Check if we have a valid cached token
    cached_token = SharePointToken.objects.filter(is_active=True).first()
    if cached_token and not cached_token.is_expired():
        print("Using cached token")
        return {"access_token": cached_token.access_token, "token_type": "Bearer"}

    # Get new token from Microsoft
    url = settings.SHAREPOINT_TOKEN_URL
    print(f"Token URL: {url}")

    if not url:
        raise Exception("SHAREPOINT_TOKEN_URL not configured")

    payload = {
        "client_id": settings.SHAREPOINT_CLIENT_ID,
        "client_secret": settings.SHAREPOINT_CLIENT_SECRET,
        "grant_type": "client_credentials",
        "scope": settings.SHAREPOINT_SCOPE,
    }

    print(f"Client ID configured: {bool(payload['client_id'])}")
    print(f"Client Secret configured: {bool(payload['client_secret'])}")
    print(f"Scope: {payload['scope']}")

    # Check that required settings are configured
    if not payload["client_id"]:
        raise Exception("SHAREPOINT_CLIENT_ID not configured")
    if not payload["client_secret"]:
        raise Exception("SHAREPOINT_CLIENT_SECRET not configured")

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
    }

    with httpx.Client() as client:
        try:
            print("Making token request...")
            response = client.post(url, data=payload, headers=headers)
            print(f"Response status: {response.status_code}")

            if response.status_code >= 400:
                print(f"Response body: {response.text}")
                raise Exception(f"HTTP {response.status_code}: {response.text}")

            token_data = response.json()
            print("Token received successfully")

            # Cache the new token
            expires_in = token_data.get("expires_in", 3600)
            expires_at = timezone.now() + timezone.timedelta(
                seconds=expires_in - 300
            )  # 5 min buffer

            # Deactivate old tokens
            SharePointToken.objects.filter(is_active=True).update(is_active=False)

            # Create new token record
            SharePointToken.objects.create(
                access_token=token_data["access_token"],
                refresh_token=token_data.get("refresh_token", ""),
                expires_at=expires_at,
                is_active=True,
            )

            print("Token cached successfully")
            return token_data

        except httpx.HTTPStatusError as e:
            print(f"HTTP status error in token request: {str(e)}")
            print(f"Response body: {e.response.text}")
            raise Exception(
                f"Token request failed with HTTP error: {str(e)}, response: {e.response.text}"
            )
        except httpx.HTTPError as e:
            print(f"HTTP error in token request: {str(e)}")
            raise Exception(f"Token request failed with HTTP error: {str(e)}")
        except Exception as e:
            print(f"General error in token request: {str(e)}")
            raise Exception(f"Unexpected error in token request: {str(e)}")


def get_token():
    """
    Legacy function for backward compatibility.
    Uses the new application token method.
    """
    return get_application_token()


async def get_all_sites(token_data: dict):
    url = "https://graph.microsoft.com/v1.0/sites/getAllSites?top=5000&count=true&filter=isPersonalSite ne true AND name ne null&orderby=displayName,name"  # &select=id,name,displayName,webUrl,isPersonalSite"

    # Extract access token from the token data
    access_token = token_data.get("access_token")
    if not access_token:
        raise Exception("No access_token found in token data")

    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)  # Should be GET, not POST
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise Exception(
                f"Site request failed: {str(e)}, response: {getattr(response, 'text', 'no response')}"
            )
        except Exception as e:
            raise Exception(f"Unexpected error in site request: {str(e)}")


async def get_site_details(token_data: dict, site_id: str):
    # url = f"https://graph.microsoft.com/v1.0/sites/{site_id}"
    url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root/children?$select=id,name,file,folder"

    # Extract access token from the token data
    access_token = token_data.get("access_token")
    if not access_token:
        raise Exception("No access_token found in token data")

    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise Exception(
                f"Site details request failed: {str(e)}, response: {getattr(response, 'text', 'no response')}"
            )
        except Exception as e:
            raise Exception(f"Unexpected error in site details request: {str(e)}")


async def get_site_drives(token_data: dict, site_id: str):
    """Get all drives for a specific site."""
    url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives?$select=id,name"

    # Extract access token from the token data
    access_token = token_data.get("access_token")
    if not access_token:
        raise Exception("No access_token found in token data")

    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise Exception(
                f"Site drives request failed: {str(e)}, response: {getattr(response, 'text', 'no response')}"
            )
        except Exception as e:
            raise Exception(f"Unexpected error in site drives request: {str(e)}")


async def get_drive_items(token_data: dict, drive_id: str):
    """Get all items for a specific drive."""
    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root/children"

    # Extract access token from the token data
    access_token = token_data.get("access_token")
    if not access_token:
        raise Exception("No access_token found in token data")

    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise Exception(
                f"Drive items request failed: {str(e)}, response: {getattr(response, 'text', 'no response')}"
            )
        except Exception as e:
            raise Exception(f"Unexpected error in drive items request: {str(e)}")


async def get_folder_items(token_data: dict, drive_id: str, folder_id: str):
    """Get all items for a specific folder."""
    url = (
        f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{folder_id}/children"
    )

    # Extract access token from the token data
    access_token = token_data.get("access_token")
    if not access_token:
        raise Exception("No access_token found in token data")

    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise Exception(
                f"Folder items request failed: {str(e)}, response: {getattr(response, 'text', 'no response')}"
            )
        except Exception as e:
            raise Exception(f"Unexpected error in folder items request: {str(e)}")


async def upload_file(
    token_data: dict, drive_id: str, folder_id: str, filename: str, file_content: bytes
):
    """
    Upload a file to SharePoint using Graph API.
    For files >4MB, use resumable upload session.
    """
    access_token = token_data.get("access_token")
    if not access_token:
        raise Exception("No access_token found in token data")

    headers = {"Authorization": f"Bearer {access_token}"}

    # For small files (<4MB), use simple upload
    if len(file_content) < 4 * 1024 * 1024:
        url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{folder_id}:/{filename}:/content"
        headers["Content-Type"] = "application/octet-stream"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.put(url, headers=headers, content=file_content)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                raise Exception(
                    f"File upload failed: {str(e)}, response: {getattr(response, 'text', 'no response')}"
                )
    else:
        # For large files, create upload session
        upload_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{folder_id}:/{filename}:/createUploadSession"

        async with httpx.AsyncClient() as client:
            try:
                # Create upload session
                session_response = await client.post(upload_url, headers=headers)
                session_response.raise_for_status()
                session_data = session_response.json()
                upload_url = session_data["uploadUrl"]

                # Upload file in chunks (recommended chunk size: 320KB * 3 = 960KB)
                chunk_size = 960 * 1024
                total_size = len(file_content)

                for i in range(0, total_size, chunk_size):
                    chunk = file_content[i : i + chunk_size]
                    content_range = f"bytes {i}-{min(i + len(chunk) - 1, total_size - 1)}/{total_size}"

                    chunk_headers = {
                        "Authorization": f"Bearer {access_token}",
                        "Content-Length": str(len(chunk)),
                        "Content-Range": content_range,
                    }

                    chunk_response = await client.put(
                        upload_url, headers=chunk_headers, content=chunk
                    )

                    if i + len(chunk) >= total_size:
                        # Last chunk - return the final response
                        chunk_response.raise_for_status()
                        return chunk_response.json()
                    else:
                        # Intermediate chunk - should return 202 Accepted
                        if chunk_response.status_code != 202:
                            chunk_response.raise_for_status()

            except httpx.HTTPError as e:
                raise Exception(
                    f"Large file upload failed: {str(e)}, response: {getattr(response, 'text', 'no response')}"
                )


async def create_folder(
    token_data: dict, drive_id: str, parent_folder_id: str, folder_name: str
):
    """
    Create a new folder in SharePoint.
    """
    access_token = token_data.get("access_token")
    if not access_token:
        raise Exception("No access_token found in token data")

    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{parent_folder_id}/children"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    data = {
        "name": folder_name,
        "folder": {},
        "@microsoft.graph.conflictBehavior": "rename",
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise Exception(
                f"Folder creation failed: {str(e)}, response: {getattr(response, 'text', 'no response')}"
            )
