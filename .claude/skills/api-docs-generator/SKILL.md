---
name: api-docs-generator
description: Generate API documentation from source code. Use when the user asks to document endpoints, create API docs, or generate OpenAPI/Swagger specs.
---

# API Documentation Generator

## Instructions

When generating API documentation:

1. Read the API source files (route handlers, controllers)
2. Identify all endpoints with their:
   - HTTP method and path
   - Request parameters (query, path, body)
   - Request/response types
   - Authentication requirements
   - Error responses

3. Generate documentation in this format:

## API Reference

### `METHOD /path`

**Description:** Brief description

**Authentication:** Required / None

**Request:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ... | ... | ... | ... |

**Request Body:**
```json
{ "example": "value" }
```

**Response (200):**
```json
{ "example": "response" }
```

**Errors:**
| Status | Description |
|--------|-------------|
| 400 | ... |
| 401 | ... |

## Rules

- Read actual source code, don't guess
- Include all parameters including optional ones
- Show realistic example payloads
- Document error responses
- If TypeScript types exist, reference them
- Group related endpoints together
- Respond in the same language as the user
