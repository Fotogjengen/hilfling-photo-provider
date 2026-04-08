import requests
from django.http import StreamingHttpResponse, JsonResponse
from django.conf import settings
from hilfling_image_proxy.utils.login import mock_login_response
import base64

def proxy_view(request, path=""):
    url = f"{settings.PROXY_TARGET_URL}/{path}"

    resp = requests.request(
        method=request.method,
        url=url,
        headers={k: v for k, v in request.META.items() if k.startswith("HTTP_")},
        data=request.body,
        params=request.GET,
        allow_redirects=False,
        stream=True,
        timeout=10,
    )

    return StreamingHttpResponse(
        resp.iter_content(chunk_size=8192),
        status=resp.status_code,
        content_type=resp.headers.get("Content-Type", "application/octet-stream"),
    )

def login_view(request):
    #TODO: implement the actual login
    # res = request.post(...) if should_mock_login() else (det under)
    auth_response, error = mock_login_response(request)

    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    if error:
        return error

    token_resp = requests.post(
        f"{settings.BACKEND_URL}/auth/token",
        json={"username": auth_response},
        timeout=10,
    )

    if token_resp.status_code != 200:
        return JsonResponse({"error": "Failed to get token"}, status=500)

    return JsonResponse(token_resp.json(), status=200)
    

    
