---
name: managing-api-clients
description: "How to call Gemini, OpenAI, and SerpAPI from Swift using URLSession and the Gemini SDK. Use when working on the AI service layer or API integrations."
---

# Managing API Clients

How to call AI APIs (Gemini, OpenAI, SerpAPI) from Swift in the Car Crash AI iOS app.

## AI Service Architecture

- `AIService` is a singleton accessed via `AIService.shared`
- Two primary methods:
  - `visionCompletion(prompt:images:)` — sends text + images to a vision model
  - `textCompletion(prompt:)` — sends text-only requests
- Provider abstraction: callers don't choose the provider; `AIService` routes to the configured primary provider and falls back automatically

## Gemini SDK Usage

- Uses the **GoogleGenerativeAI** Swift package
- Create a `GenerativeModel` with the desired model name and API key
- Configure with `GenerationConfig`:
  - Set `responseMIMEType: "application/json"` for structured JSON responses
  - Add **+8000 to `maxOutputTokens`** to account for thinking token padding
- Pass images as `ModelContent.Part.data(mimetype: "image/jpeg", data)` alongside text parts
- Call `generateContent(_:)` with an array of `ModelContent` parts

## OpenAI REST API

- Use `URLSession` to POST to `https://api.openai.com/v1/chat/completions`
- Set header `Authorization: Bearer <api_key>`
- Build the request body with a `messages` array containing a `content` array:
  - `{"type": "text", "text": "..."}` for text blocks
  - `{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}` for images
- Model selection:
  - **`gpt-4.1-mini`** for vision tasks
  - **`gpt-4.1-nano`** for text-only tasks

## SerpAPI

- Use `URLSession` to GET `https://serpapi.com/search.json`
- Query parameters: `q` (search query), `api_key`, `engine` (e.g., `google`)
- URL-encode query parameters with `addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed)`
- Parse the JSON response to extract search results

## Retry Logic

- Maximum **2 retries** per provider call
- Check for HTTP **429** status codes and rate limit error messages in the response body
- Use **exponential backoff** with a base delay of **10 seconds** (10s, 20s)

## Provider Fallback

1. Attempt the request on the **primary provider**
2. If the primary is rate-limited after exhausting retries, switch to the **secondary provider**
3. If both providers fail, throw `AIServiceError.allProvidersRateLimited`

## Error Types

`AIServiceError` enum cases:

- `rateLimited` — provider returned HTTP 429 or rate limit error
- `invalidResponse` — response could not be parsed or was missing expected fields
- `networkError` — URLSession transport failure
- `invalidAPIKey` — provider rejected the API key (HTTP 401/403)

## Testing

- Use `MockURLProtocol` (a `URLProtocol` subclass) to intercept `URLSession` network calls
- Register `MockURLProtocol` on a custom `URLSessionConfiguration`
- Inject mock responses and status codes to test retry logic, fallback behavior, and error handling
