"""Tool package: importing it registers all first-party tools."""
from app.services.tools import recall, web_search, fetch_page  # noqa: F401
from app.services.tools import current_time, search_conversations, generate_image  # noqa: F401
from app.services.tools import calculate  # noqa: F401
