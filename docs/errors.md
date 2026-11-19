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
- too many images in one upload

## not-found

**404.** The estimate, upload or route doesn't exist.

## method-not-allowed

**405.** The route exists, but not for this HTTP method.

## validation-error

**422.** The request body or parameters failed schema validation, e.g. an `upload_id` that isn't 12 lowercase hex characters. An extra member, `errors`, lists each failure:

```json
{ "errors": [{ "loc": ["body", "upload_id"], "msg": "String should match pattern '^[0-9a-f]{12}$'", "type": "string_pattern_mismatch" }] }
```

## upstream-rate-limited

**429.** Every configured AI provider is rate-limited. Retry after a short wait.

## internal-error

**500.** An unexpected server error. The response never includes exception details; the error is logged server-side.

## upstream-error

**502.** The AI provider returned a response that couldn't be used, e.g. output that failed schema validation after retries.

## upstream-unavailable

**503.** The AI provider couldn't be reached or returned a server error.

## upstream-timeout

**504.** The AI provider didn't respond within the configured deadline.
