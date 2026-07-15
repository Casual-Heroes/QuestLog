# Asset Provenance Audit

Audit date: 2026-07-14

This inventory covers media found in the QuestLog workspace. It is a provenance
review, not a legal opinion. An asset should not be distributed unless its
origin and permission are known.

## Git-tracked assets

No image, audio, video, font, or other binary media files are currently tracked
by Git. The repository's `.gitignore` excludes common media extensions.

## Removed and quarantined assets

The former `app/static/r2/` directory contained 678 Remnant 2 item images,
approximately 103 MB. Their names and the deleted download scripts indicated
that they were collected as game or wiki imagery, and no complete per-file
permission record was available.

On 2026-07-14, the files were placed in a non-public quarantine archive at
`/backup/secondary4tb/questlog_quarantine/remnant2_images_quarantine_2026-07-14.zip`
and removed from the served static tree. The archive contains 678 entries and
has SHA-256:

`a9ea2820bf06a3a169acbd53edd9655ec9b76b348acdbae61569131329bc535b`

The archive is retained only for provenance review and must not be republished
without verified permission for each retained file.

## Ignored static assets still present on the server

These files are outside Git but may still be served by the deployed site:

- `app/static/img/`: 53 images. Casual Heroes and QuestLog brand files may be
  first-party, but game logos, screenshots, key art, and promotional images need
  a recorded source and permission or license.
- `media/uploads/`: user-uploaded avatars, community graphics, emoji, and posts.
  These are operational user content rather than repository assets. They need
  uploader terms, reporting, and takedown handling rather than a source-code
  license notice.

## Database content

Database content is outside the scope of this repository cleanup. By project
owner instruction, no MariaDB records may be deleted, rewritten, or otherwise
mutated because the applications depend on that data. This audit made no
database changes.

## Required handling

1. Do not recommit scraped/downloaded game or wiki media.
2. Remove unverified static media from deployment, or document its source and
   permission before continued use.
3. Keep first-party logos in a clearly identified first-party directory.
4. Record source URL, creator/rightsholder, license or permission, retrieval
   date, and any attribution requirement for every retained third-party asset.
5. Replace removed art with original graphics, licensed media, or neutral
   code-generated placeholders.
6. Keep database records intact. Any future database review must preserve every
   operational and factual value and requires separate owner authorization.
