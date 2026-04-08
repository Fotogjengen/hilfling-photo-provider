from django.conf import settings
from django.http import JsonResponse
import base64

def should_mock_login():
    return getattr(settings, "MOCK_LOGIN", False)

def get_basic_auth_username(request):
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if not auth_header.startswith("Basic "):
        return None
    
    decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
    username, _, _ = decoded.partition(":")
    return username

def mock_login_response(request):
    username = get_basic_auth_username(request)
    if not username:
        return None, JsonResponse({"error": "No credentials provided"}, status=401)
    return username, None
