"""Universal media import — session lifecycle, dedup, and the Celery hand-off.

An import lives entirely in a MediaImportSession while it downloads; only once a
local file exists does it call ``create_upload()`` and enter the existing
pipeline. No AI/transcription/knowledge logic lives here.
"""
