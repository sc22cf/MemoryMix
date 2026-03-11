# MemoryMix — Postman Requests

All requests go to `http://localhost:8000`.
Authenticated routes require the header: `Authorization: Bearer <access_token>`

---

## 1. GET Hardcoded Songs

```
GET http://localhost:8000/auth/test/preview-songs?mode=hardcoded
```

| Scenario | Status |
|---|---|
| `?mode=hardcoded` or `?mode=random` | `200 OK` |
| `mode` omitted | `200 OK` — defaults to `random` |
| Any other `mode` value | `422 Unprocessable Entity` |

> No auth required on this route — you will never get a 401 here.

---

## 2. POST Test Login — Hardcoded

```
POST http://localhost:8000/auth/test/login
Content-Type: application/json

{
  "mode": "hardcoded"
}
```

---

## 3. POST Test Login — Random

```
POST http://localhost:8000/auth/test/login
Content-Type: application/json

{
  "mode": "random"
}
```

---

## 4. POST Create Memory

```
POST http://localhost:8000/memories
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "title": "Sunset at the Beach",
  "description": "Golden hour on a quiet beach, warm light reflecting off the water, waves gently rolling in. A peaceful, contemplative evening alone.",
  "memory_date": "2026-03-11T18:00:00",
  "photo": {
    "google_photo_id": "local-upload",
    "base_url": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQ==",
    "filename": "test-photo.jpg",
    "mime_type": "image/jpeg",
    "creation_time": "2026-03-11T18:00:00",
    "width": 1920,
    "height": 1080
  }
}
```

> `memory_date` must be today's date. Replace the `base_url` value with a real base64-encoded image.

---

## 5. GET All Memories

```
GET http://localhost:8000/memories
Authorization: Bearer <access_token>
```

---

## 6. GET Single Memory

```
GET http://localhost:8000/memories/1
Authorization: Bearer <access_token>
```

> Replace `1` with the `id` from the POST Create Memory response.

---

## 7. PUT Swap Matched Track

> Use `mapping.id` from the GET memory response, and a `track_id` from `mood_candidates`.

```
PUT http://localhost:8000/mappings/1
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "track_id": 42
}
```

---

## 9. DELETE Memory

```
DELETE http://localhost:8000/memories/1
Authorization: Bearer <access_token>
```
