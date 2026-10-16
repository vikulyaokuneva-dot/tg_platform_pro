# AGRO source-image bridge

The AGRO SQLite record supplies only `materials.image_url`. It does not store
the downloaded bytes, a checksum, a licence, or permission for republication.
The daily VK sync copies that URL to the same verified material as
`agro_image_url` and `media.source_image_url`; it never grants media rights.

An operator may complete that media record only after documented permission is
available by adding all of: an allowed `license`, a non-empty
`rights_reference`, and the SHA-256 of the exact JPEG or PNG. At publish time
the existing `case_pipeline.httpclient.fetch_bytes` downloads that URL, checks
its type and size, and checks the SHA-256 before the existing VK uploader is
called. A WebP source remains blocked because the existing VK publisher
accepts JPEG and PNG only.

The same-run bytes are held only under `vk_daily/.runtime/`, which is ignored
by Git. No AGRO or Telegram record is updated by this bridge.
