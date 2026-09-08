import io
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from PIL import Image


class InternalImageTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self):
        self.storage = tempfile.TemporaryDirectory()
        self.addCleanup(self.storage.cleanup)
        self.settings_override = override_settings(IMAGE_STORAGE_PATH=self.storage.name, IMAGE_BASE_URL="/media")
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        key_lookup = patch("hilfling_image_proxy.utils.auth._jwks_client.get_signing_key_from_jwt", return_value=SimpleNamespace(key=self.key.public_key()))
        key_lookup.start()
        self.addCleanup(key_lookup.stop)
        self.image_id = uuid4()
        self.url = f"/internal/images/{self.image_id}"

    def token(self, method="POST", **changes):
        claims = {"sub": str(self.image_id), "iss": "hilfling-backend", "aud": "hilfling-image-provider",
                  "iat": int(time.time()), "exp": int(time.time()) + 120, "operation": method, "securityLevel": "ALLE"}
        claims.update(changes)
        return jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": "test"})

    def file(self, image_format="PNG", size=(600, 400), name="../../profile.exe", exif=None):
        buffer = io.BytesIO()
        img = Image.new("RGB", size, "red")
        img.save(buffer, format=image_format, **({"exif": exif} if exif else {}))
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="application/octet-stream")

    def upload(self, media=None, token=None):
        return self.client.post(self.url, {"media": media or self.file()}, HTTP_AUTHORIZATION=f"Bearer {token or self.token()}")

    def delete(self):
        return self.client.delete(self.url, HTTP_AUTHORIZATION=f"Bearer {self.token('DELETE')}")

    def test_upload_serve_download_and_delete(self):
        response = self.upload()
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual((data["width"], data["height"]), (600, 400))
        for variant, expected in (("prod", (600, 400)), ("web", (600, 400)), ("thumb", (300, 300))):
            served = self.client.get(data[variant])
            self.assertEqual(served.status_code, 200)
            with Image.open(io.BytesIO(b"".join(served.streaming_content))) as img:
                self.assertEqual(img.size, expected)
            served.close()
        download = self.client.get(data["prod"] + "?download=1")
        self.assertTrue(download["Content-Disposition"].startswith("attachment;"))
        download.close()
        self.assertEqual(self.delete().status_code, 204)
        self.assertEqual(self.delete().status_code, 204)
        self.assertEqual(self.client.get(data["prod"]).status_code, 404)
        self.assertEqual(self.upload().status_code, 409)

    def test_missing_and_user_tokens_cannot_mutate_files(self):
        self.assertEqual(self.client.post(self.url, {"media": self.file()}).status_code, 401)
        user_token = jwt.encode({"sub": "member", "securityLevel": "FG", "exp": time.time() + 120}, self.key, algorithm="RS256")
        self.assertEqual(self.upload(token=user_token).status_code, 401)
        self.assertEqual(list(Path(self.storage.name).iterdir()), [])

    def test_capability_is_bound_to_id_method_audience_expiry_and_level(self):
        for changes in ({"sub": str(uuid4())}, {"operation": "DELETE"}, {"aud": "other"},
                        {"iss": "other"}, {"exp": time.time() - 1}, {"securityLevel": "../alle"}):
            with self.subTest(changes=changes):
                self.assertEqual(self.upload(token=self.token(**changes)).status_code, 401)
        self.assertEqual(self.client.delete(self.url, HTTP_AUTHORIZATION=f"Bearer {self.token()}").status_code, 401)

    def test_tampered_signature_is_rejected(self):
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        token = jwt.encode(jwt.decode(self.token(), options={"verify_signature": False}), other_key, algorithm="RS256")
        self.assertEqual(self.upload(token=token).status_code, 401)

    def test_unsupported_corrupt_and_oversized_files_are_rejected(self):
        self.assertEqual(self.upload(media=SimpleUploadedFile("fake.png", b"not an image")).status_code, 400)
        self.assertEqual(self.upload(media=self.file("GIF")).status_code, 400)
        with override_settings(INTERNAL_IMAGE_MAX_BYTES=10):
            self.assertEqual(self.upload().status_code, 413)
        with override_settings(INTERNAL_IMAGE_MAX_PIXELS=10):
            self.assertEqual(self.upload().status_code, 400)
        self.assertEqual(list(Path(self.storage.name).iterdir()), [])

    def test_missing_file_and_wrong_method(self):
        self.assertEqual(self.client.post(self.url, HTTP_AUTHORIZATION=f"Bearer {self.token()}").status_code, 400)
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_filename_is_generated_and_formats_are_detected_from_content(self):
        for image_format, extension in (("JPEG", "jpg"), ("PNG", "png"), ("WEBP", "webp")):
            with self.subTest(image_format=image_format):
                self.image_id = uuid4()
                self.url = f"/internal/images/{self.image_id}"
                response = self.upload(media=self.file(image_format))
                self.assertEqual(response.status_code, 201)
                self.assertTrue(response.json()["prod"].endswith(f"/{self.image_id}/prod.{extension}"))

    def test_orientation_is_applied_and_exif_is_removed(self):
        exif = Image.Exif()
        exif[274] = 6
        exif[270] = "private description"
        response = self.upload(media=self.file("JPEG", exif=exif))
        self.assertEqual(response.status_code, 201)
        self.assertEqual((response.json()["width"], response.json()["height"]), (400, 600))
        prod = Path(self.storage.name) / response.json()["prod"].removeprefix("/media/")
        with Image.open(prod) as img:
            self.assertFalse(img.getexif())

    def test_png_transparency_is_preserved(self):
        buffer = io.BytesIO()
        Image.new("RGBA", (100, 100), (255, 0, 0, 0)).save(buffer, "PNG")
        result = self.upload(media=SimpleUploadedFile("alpha.png", buffer.getvalue())).json()
        with Image.open(Path(self.storage.name) / result["thumb"].removeprefix("/media/")) as img:
            self.assertEqual(img.getpixel((0, 0))[3], 0)

    def test_internal_images_require_a_member_token(self):
        result = self.upload(token=self.token(securityLevel="FG")).json()
        self.assertEqual(self.client.get(result["web"]).status_code, 403)
        member_token = jwt.encode({"sub": "member", "securityLevel": "FG", "exp": time.time() + 120}, self.key, algorithm="RS256")
        response = self.client.get(result["web"], HTTP_X_HILFLING_TOKEN=member_token)
        self.assertEqual(response.status_code, 200)
        response.close()

    def test_delete_before_upload_prevents_late_publication(self):
        self.assertEqual(self.delete().status_code, 204)
        self.assertEqual(self.upload().status_code, 409)

    def test_processing_failure_does_not_publish_partial_images(self):
        media = self.file()
        with self.assertLogs("hilfling_image_proxy.shared.internal_images", level="ERROR"), patch("PIL.Image.Image.save", side_effect=OSError("disk full")):
            response = self.upload(media=media)
        self.assertEqual(response.status_code, 503)
        self.assertFalse((Path(self.storage.name) / "alle" / "internal" / str(self.image_id)).exists())

    def test_delete_during_publication_cancels_all_variants(self):
        import os
        replace = os.replace

        def delete_during_replace(source, destination):
            replace(source, destination)
            if Path(destination).name == "web.png":
                self.assertEqual(self.delete().status_code, 204)

        with patch("hilfling_image_proxy.shared.internal_images.os.replace", side_effect=delete_during_replace):
            self.assertEqual(self.upload().status_code, 409)
        directory = Path(self.storage.name) / "alle" / "internal" / str(self.image_id)
        self.assertEqual([path.name for path in directory.iterdir()], [".deleted"])
