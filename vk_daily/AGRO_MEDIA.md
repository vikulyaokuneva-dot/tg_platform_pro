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

For a genuinely separate illustration, use `origin: "licensed_url"` only when
the committed record contains the source image URL, SHA-256 of its exact bytes,
the licence kind, a rights-evidence URL, the licence URL, and attribution. The
exact attribution string must also be present in `vk_text`. This route is for
independently licensed assets such as Wikimedia Commons; it does not grant any
rights to the original AGRO source image.

For a control post, a verified JPEG/PNG may instead be committed under
`vk_daily/assets/`. Use `origin: "licensed_file"`, retain the public source URL
as provenance, and set `path` to the repository-relative asset. The local file
takes precedence over the URL and its exact SHA-256 is checked before any VK
API call. This keeps GitHub Actions independent of temporary rate limits at
the source host; the committed binary is not managed by Git LFS.
