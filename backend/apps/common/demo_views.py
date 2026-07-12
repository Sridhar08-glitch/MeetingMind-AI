"""Demo Mode API — reset and info endpoints.

`POST /api/demo/reset/` re-seeds the demo workspace to its original state (gated to the
demo account or staff, so a normal user can never wipe their own data by accident).
`GET  /api/demo/info/` reports whether demo mode is available and the demo credentials.
"""
from __future__ import annotations

import mimetypes

from django.http import FileResponse, Http404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common import demo_media
from apps.common.demo import DEMO_EMAIL, DEMO_PASSWORD, seed_demo


class DemoInfoView(APIView):
    """Public: advertise the demo account so the login page can offer a one-click demo."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            "enabled": True,
            "email": DEMO_EMAIL,
            "password": DEMO_PASSWORD,
            "workspace": "MeetingMind AI Demo",
        })


class DemoResetView(APIView):
    """Re-seed the demo workspace. Only the demo account (or staff) may do this."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if not (user.is_staff or getattr(user, "email", "") == DEMO_EMAIL):
            return Response(
                {"detail": "Only the demo account can reset the demo workspace."},
                status=status.HTTP_403_FORBIDDEN,
            )
        counts = seed_demo(log=lambda _m: None)
        return Response({"detail": "Demo workspace reset to its original state.", "seeded": counts})


class DemoSamplesView(APIView):
    """List the bundled demo recordings a user can upload to try the real pipeline."""

    permission_classes = [AllowAny]

    def get(self, request):
        rows = demo_media.load_manifest()
        samples = [
            {
                "title": r["title"],
                "project": r["project"],
                "mtype": r["mtype"],
                "media": r["media"],
                "filename": r["filename"],
                "content_type": r["content_type"],
                "size_bytes": r["size_bytes"],
                "duration_seconds": r["duration_seconds"],
                "download_url": f"/api/demo/samples/{r['filename']}/",
            }
            for r in rows
        ]
        return Response({"count": len(samples), "samples": samples})


class DemoSampleDownloadView(APIView):
    """Stream one bundled demo recording so the user can upload it via the real UI."""

    permission_classes = [AllowAny]

    def get(self, request, filename: str):
        path = demo_media.media_path(filename)
        if path is None:
            raise Http404("Unknown demo sample.")
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        response = FileResponse(path.open("rb"), content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
