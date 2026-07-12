# FFmpeg Setup (Windows, local dev)

FFmpeg (`ffmpeg` + `ffprobe`) is used by the media services for **audio
extraction, normalization and media inspection** before Faster-Whisper
transcription. A portable build works — **no admin/system install required**.

## Install (portable, no admin)

```powershell
$dest = "E:\MeetingMind\tools"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Invoke-WebRequest -Uri "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" `
  -OutFile "$dest\ffmpeg.zip" -UseBasicParsing
Expand-Archive -Path "$dest\ffmpeg.zip" -DestinationPath $dest -Force
# -> E:\MeetingMind\tools\ffmpeg-<version>-essentials_build\bin\{ffmpeg,ffprobe}.exe
```

(Verified with FFmpeg **8.1.2** essentials build.)

## Configuration (`backend/.env`)

The app resolves the binaries via `settings.FFMPEG_BINARY` / `FFPROBE_BINARY`,
which are **env-overridable**. Point them at the absolute paths so no PATH change
is needed:

```dotenv
FFMPEG_BINARY=E:\MeetingMind\tools\ffmpeg-8.1.2-essentials_build\bin\ffmpeg.exe
FFPROBE_BINARY=E:\MeetingMind\tools\ffmpeg-8.1.2-essentials_build\bin\ffprobe.exe
```

(Alternatively add the `bin` dir to your user PATH: `setx PATH "$env:PATH;<bin>"`
— no admin needed — then leave the defaults `ffmpeg`/`ffprobe`.)

## Verify

```powershell
& "E:\MeetingMind\tools\ffmpeg-8.1.2-essentials_build\bin\ffmpeg.exe" -version
```
```bash
# App-level check:
backend/venv/Scripts/python.exe -c "import os,django;os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings');django.setup();from apps.meetings.services.media import ffmpeg_available,ffprobe_available;print(ffmpeg_available(),ffprobe_available())"
# -> True True
```

## Notes / troubleshooting

- **`ffmpeg_available()` is False:** the path in `.env` is wrong or the exe
  missing — check the version folder name matches your download.
- Restart the Django server **and** the Celery worker after editing `.env` (the
  worker runs the transcription pipeline and must see the new paths).
- Without ffmpeg the STT stage raises `ffmpeg_missing`; media *inspection* has a
  stdlib fallback but *extraction/normalization* requires ffmpeg.
