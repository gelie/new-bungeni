import httpx
from decouple import config


def get_token():
    """
    Django dependency that fetches an access token from Azure AD.
    Returns the parsed JSON response containing the access token.
    """
    url = config("TOKEN_URL")

    # Log what we're working with for debugging
    # print(f"TOKEN_URL: {'set' if url else 'NOT SET'}")

    if not url:
        raise Exception("TOKEN_URL environment variable not set")

    payload = dict(
        client_id=config("CLIENT_ID"),
        client_secret=config("CLIENT_SECRET"),
        grant_type=config("GRANT_TYPE"),
        scope=config("SCOPE"),
    )

    # Log what we're working with for debugging (without exposing secrets)
    # print(f"CLIENT_ID: {'set' if payload['client_id'] else 'NOT SET'}")
    # print(f"CLIENT_SECRET: {'set' if payload['client_secret'] else 'NOT SET'}")

    # Check that required environment variables are set
    if not payload["client_id"]:
        raise Exception("CLIENT_ID environment variable not set")
    if not payload["client_secret"]:
        raise Exception("CLIENT_SECRET environment variable not set")

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
    }

    with httpx.Client() as client:
        try:
            # print(f"Making POST request to: {url}")
            response = client.post(url, data=payload, headers=headers)
            # print(f"Response status: {response.status_code}")
            # print(f"Response headers: {dict(response.headers)}")

            # Try to get response text even if there's an error
            response_text = response.text
            # print(f"Response text: {response_text[:200]}...")  # First 200 chars

            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise Exception(
                f"Token request failed with HTTP error: {str(e)}, response: {response_text if 'response_text' in locals() else 'no response'}"
            )
        except Exception as e:
            raise Exception(f"Unexpected error in token request: {str(e)}")


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
