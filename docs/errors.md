# API error types

Every error response is an [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) problem document with media type `application/problem+json`:

```json
{
  "type": "https://github.com/Thytus777/car-crash-ai/blob/main/docs/errors.md#not-found",
  "title": "Resource not found",
  "status": 404,
  "detail": "Estimate 42 not found",
  "instance": "/api/v1/estimates/42"
}
```

Clients should branch on `type` (stable) or `status`, and show `detail` to the user. `title` is fixed per type; `detail` is specific to the occurrence.

## invalid-input

**400.** The request was well-formed but its content can't be processed. Examples:
- an uploaded file isn't a valid image
- an image is below the minimum resolution

## unauthorized

**401.** The API has keys configured and the request carried no valid one. Send it as `X-API-Key: <key>` or `Authorization: Bearer <key>`.

## not-found

**404.** The estimate, upload or route doesn't exist.

## method-not-allowed

**405.** The route exists, but not for this HTTP method.

## payload-too-large

**413.** One of the size limits was exceeded:
- too many images
- a single file over `MAX_UPLOAD_SIZE_MB` (default 20)
- all files together over `MAX_UPLOAD_TOTAL_MB` (default 40)

## unsupported-media-type

**415.** The file decodes as an image, but not as JPEG, PNG or WebP. The format is detected from the file contents; the `Content-Type` header is ignored.

## not-a-vehicle

**422.** Image triage found no road vehicle in any uploaded photo. `detail` says what was seen.

## unusable-images

**422.** A vehicle is visible, but no photo shows it clearly enough to judge damage (too dark, blurry, distant or obstructed). `detail` says what to retake.

## validation-error

**422.** The request body or parameters failed schema validation, e.g. an `upload_id` that isn't 12 lowercase hex characters. An extra member, `errors`, lists each failure:

```json
{ "errors": [{ "loc": ["body", "upload_id"], "msg": "String should match pattern '^[0-9a-f]{12}$'", "type": "string_pattern_mismatch" }] }
```

## rate-limited

**429.** This client (API key, or IP when auth is off) exceeded its per-minute limit: `RATE_LIMIT_PER_MINUTE` overall, `ANALYZE_RATE_LIMIT_PER_MINUTE` for `/analyze`. Wait for the `Retry-After` header's number of seconds. This is different from `upstream-rate-limited`, which means the AI provider is rate-limiting *us*.

## upstream-rate-limited

**429.** Every configured AI provider is rate-limited. Retry after a short wait.

## internal-error

**500.** An unexpected server error. The response never includes exception details; the error is logged server-side.

## upstream-error

**502.** The AI provider returned a response that couldn't be used, e.g. output that failed schema validation after retries.

## upstream-unavailable

**503.** The AI provider couldn't be reached or returned a server error.

## redaction-unavailable

**503.** Uploads are paused because face and number-plate redaction isn't available on this server, and the server is configured never to store unredacted photos (`REDACTION_REQUIRED`).

## upstream-timeout

**504.** The AI provider didn't respond within the configured deadline.
