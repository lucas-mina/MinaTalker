"""Avatar-related routes."""
from aiohttp import web

from src.config.loader import load_avatar_entries


async def list_avatars(request: web.Request) -> web.Response:
    """
    Return the list of avatars defined in avatar_config.yaml.

    Response JSON structure:
        {
          "code": 0,
          "avatars": [ { ...avatar fields... }, ... ]
        }
    """
    avatars = load_avatar_entries()
    return web.json_response({"code": 0, "avatars": avatars})

