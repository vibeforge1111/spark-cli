from __future__ import annotations


SECRET_ID_SET_HELP = "Stable dotted identifier used to retrieve the value later, for example telegram.bot_token"
SECRET_ID_GET_HELP = "Stable dotted identifier of the secret to inspect"
SECRET_ID_DELETE_HELP = "Stable dotted identifier of the secret to remove"
SECRET_BACKEND_HELP = (
    "Storage backend: keychain uses the OS keychain (default); file is DPAPI-protected on Windows "
    "and an explicitly enabled insecure opt-in elsewhere"
)
