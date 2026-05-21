import requests
from django.conf import settings
from django.http import JsonResponse, StreamingHttpResponse

from hilfling_image_proxy.utils.login import mock_login_response


def _forward_headers(meta: dict) -> dict:
    """Convert Django META keys to proper HTTP header names for forwarding."""
    headers = {}
    for key, value in meta.items():
        if key.startswith("HTTP_"):
            # e.g. HTTP_X_HILFLING_TOKEN → X-Hilfling-Token
            header_name = key[5:].replace("_", "-").title()
            headers[header_name] = value
    return headers

# These are dev views, not to be deployed in prod!
# Because ITK is deploying their own proxy on our behalf, we have no need
# for our own proxy in prod. BUT, we do need them for simulating ITK
# server behaviour because I have no idea how to set that up myself.
# If someone knows how to dockerize this with some sort of apache magic config
# given from ITK, please do! But for now, we mock their behaviour for our own internal
# testing.


def proxy_view(request, path=""):
    url = f"{settings.PROXY_TARGET_URL}/{path}"

    resp = requests.request(
        method=request.method,
        url=url,
        headers=_forward_headers(request.META),
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
    # TODO: implement the actual login
    auth_response, error = mock_login_response(request)

    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    if error:
        return error

    token_resp = requests.post(
        f"{settings.PROXY_TARGET_URL}/auth/login",
        json={"username": auth_response},
        timeout=10,
    )

    if token_resp.status_code != 200:
        print(token_resp.json(), flush=True)
        print(token_resp.status_code)
        return JsonResponse({"error": "Failed to get token"}, status=500)

    return JsonResponse(token_resp.json(), status=200)
