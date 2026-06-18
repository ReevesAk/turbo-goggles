# Brand Ads — API Reference

> **Note:** All request and response bodies are **encrypted**. The client must wrap payloads with the shared encryption helper before sending and decrypt responses after receiving.  
> Auth is **Bearer JWT** on every endpoint.

---

## Endpoints Overview

| Method | URL | Description |
|---|---|---|
| `POST` | `/v1/brands/ads/onboard-and-create` | Create an ad campaign (auto-onboards as BrandAd) |
| `POST` | `/v1/brands/ads/cost-preview/` | Preview charge after credit is applied |
| `GET` | `/v1/brands/ads/list-all-ads` | List your own ad campaigns |
| `GET` | `/v1/brands/ads/get/{ad_id}/` | Get a single ad's details |
| `GET` | `/v1/brands/ads/profile?email={email}` | Get a BrandAd profile by email |
| `PUT/PATCH` | `/v1/brands/ads/update-profile` | Update BrandAd profile |
| `GET` | `/v1/brands/ads/list-all-ads-users` | Admin — list all BrandAd users |

---

## 1. Create Ad & Onboard — `POST /v1/brands/ads/onboard-and-create`

Creates a new ad campaign. Debits wallet or processes card payment. If the user is not yet a BrandAd, they are auto-onboarded.

**Auth:** `Bearer <token>`  
**Optional Header:** `Idempotency-Key: <uuid>` — prevents duplicate charges on network retry

### Request Payload

```json
{
  "payment_option": "WALLET",              // REQUIRED — "WALLET" | "CARD"
  "pin": "123456",                         // REQUIRED for WALLET (unless using biometrics)
  "use_biometrics": false,                 // OPTIONAL — omit or false to use PIN

  "business_or_brand_name": "Acme Co",    // OPTIONAL (recommended)
  "type_of_business": "Online",            // OPTIONAL — "Online" | "Physical" | "Hybrid"
  "industry": "Technology",               // OPTIONAL — see Industry Choices
  "brand_objective": "Brand Awareness",   // OPTIONAL — see Brand Objective Choices
  "campaign_name": "Summer 2025",         // OPTIONAL (recommended)
  "gender": "All",                        // OPTIONAL — "Male" | "Female" | "All"
  "demography": "26 - 35",               // OPTIONAL — "18 - 25" | "26 - 35" | "36 - 45" | "46+"
  "engagement_type": "Passive",           // OPTIONAL — free text
  "daily_allocation": "500",              // OPTIONAL — max users/day (free text)
  "campaign_duration": "7",              // OPTIONAL — number of days as a string
  "amount": "15000",                      // OPTIONAL — total campaign cost in Naira (string)
  "type_of_brand": "SME",               // OPTIONAL — free text

  "website": "https://acme.com",          // OPTIONAL
  "brand_socials": [                      // OPTIONAL — max 4 valid URLs
    "https://instagram.com/acme",
    "https://twitter.com/acme"
  ],

  "state": ["Lagos", "Abuja"],            // OPTIONAL — paired 1:1 with city
  "city": ["Ikeja", "Wuse"],             // OPTIONAL — paired 1:1 with state

  "images": ["https://cdn.example.com/img1.jpg"],  // OPTIONAL — paired 1:1 with videos
  "videos": ["https://cdn.example.com/vid1.mp4"],  // OPTIONAL — paired 1:1 with images

  "location_type": "states",             // OPTIONAL — "nationwide" | "states" | "cities"
  "targeting_type": "broad",             // OPTIONAL — "broad" | "city" | "niche" | "influencer"
  "countries": ["Nigeria"],              // OPTIONAL — default []
  "auto_boost": false,                   // OPTIONAL — spend earned points to boost

  "task_type": "watch_video",            // OPTIONAL — see Task Types section
  "task_name": "Watch our promo",        // OPTIONAL (recommended if task_type set)
  "task_description": "Watch 30 secs of our latest ad.",  // OPTIONAL
  "task_details": {},                    // OPTIONAL — shape depends on task_type (see below)
  "slot_cap": 200                        // OPTIONAL — max number of task completions
}
```

### `targeting_type` Pricing Multiplier

| Value | Label | Multiplier |
|---|---|---|
| `broad` | All of Nigeria | ×1.00 (default) |
| `city` | City-Specific | ×1.15 |
| `niche` | Niche Behaviour | ×1.25 |
| `influencer` | Influencer Tier (10k+ followers) | ×1.50 |

### Industry Choices
`Technology` · `Fashion & Beauty` · `Food & Drinks` · `Health & Fitness` · `Travels` · `Education` · `Entertainment` · `Home Decor` · `Sports` · `Business & Finance` · `Retail & General Trade` · `Charities & Membership`

### Brand Objective Choices
`Brand Awareness` · `Generate Leads` · `Drive Sales` · `Promote Awareness(Engagement)`

### Success Response `200`

```json
{
  "status": "Success!",
  "message": "Brand advert promoted successfully."
}
```

### Error Responses

| Status | Message |
|---|---|
| `400` | `"Insufficient balance."` |
| `400` | `"Invalid payment option"` |
| `400` | Validation error object |
| `500` | `"Transaction failed"` |

---

## 1a. Task Type — `task_details` Shapes

> Include `task_details` when `task_type` is set. Each type has its own required fields.

### `watch_video`

```json
{
  "task_type": "watch_video",
  "task_details": {
    "video_url": "https://youtube.com/watch?v=abc123",  // REQUIRED
    "platform": "YouTube",                               // REQUIRED — "YouTube" | "TikTok" | "Instagram" | "X"
    "min_watch_duration": "30s"                          // REQUIRED — "15s" | "30s" | "60s" | "full"
  }
}
```

### `social_engage`

```json
{
  "task_type": "social_engage",
  "task_details": {
    "platform": "Instagram",                             // REQUIRED — "Facebook" | "X" | "TikTok" | "Instagram" | "YouTube"
    "post_url": "https://instagram.com/p/xyz123",        // REQUIRED
    "required_actions": ["like", "follow"],              // REQUIRED — at least one of: "like" | "comment" | "share" | "follow"
    "timing": "30s"                                      // OPTIONAL — "15s" | "30s" | "60s"
  }
}
```

### `website_visit`

```json
{
  "task_type": "website_visit",
  "task_details": {
    "landing_url": "https://acme.com/summer-promo",     // REQUIRED
    "min_time_on_page": 60                              // REQUIRED — 30 | 60 | 120 | 180 (seconds)
  }
}
```

### `store_visit`

```json
{
  "task_type": "store_visit",
  "task_details": {
    "store_name": "Acme Lagos",                         // REQUIRED
    "store_address": "12 Lagos Island, Lagos State"     // REQUIRED
  }
}
```

### `survey`

```json
{
  "task_type": "survey",
  "task_details": {
    "survey_title": "Customer Feedback Q3 2025",        // REQUIRED
    "questions": [                                       // REQUIRED — at least 1 item
      "How did you hear about us?",
      "Would you recommend us to a friend?"
    ]
  }
}
```

### `app_download`

```json
{
  "task_type": "app_download",
  "task_details": {
    "app_name": "Acme App",                             // REQUIRED
    "play_store_url": "https://play.google.com/store/apps/details?id=com.acme"  // REQUIRED
  }
}
```

---

## 2. Cost Preview — `POST /v1/brands/ads/cost-preview/`

Call this **before** creating the ad to see the real charge after any existing ledger credit is applied.

**Auth:** `Bearer <token>`

### Request Payload

```json
{
  "amount": "15000"   // REQUIRED — total campaign cost the frontend calculated (string or number)
}
```

### Success Response `200`

```json
{
  "status": "success",
  "data": {
    "new_ad_total": "15000",       // The amount you sent
    "ledger_balance": "3000",      // Available credit from unused slots on past expired ads
    "credit_to_apply": "3000",     // How much credit will be deducted
    "amount_to_charge": "12000"    // What the user actually pays
  }
}
```

### Error Responses

| Status | Message |
|---|---|
| `400` | `"amount must be a valid number."` |
| `400` | `"amount must be greater than zero."` |

---

## 3. List My Ads — `GET /v1/brands/ads/list-all-ads`

Returns all campaigns created by the authenticated user. Cached for 2 minutes.

**Auth:** `Bearer <token>`  
**Permission:** BrandAd | BrandAdAdmin | SuperAdmin  
**No request body.**

### Success Response `200`

```json
{
  "status": "success",
  "message": "All created ads retrieved successfully!",
  "data": [
    {
      "id": 1,
      "user": 42,
      "business_or_brand_name": "Acme Co",
      "type_of_business": "Online",
      "industry": "Technology",
      "brand_objective": "Brand Awareness",
      "campaign_name": "Summer 2025",
      "gender": "All",
      "demography": "26 - 35",
      "engagement_type": "Passive",
      "daily_allocation": "500",
      "website": "https://acme.com",
      "type_of_brand": "SME",
      "campaign_duration": "7",
      "remaining_time": "5 days 3 hours remaining",
      "amount": "15000",
      "brand_location": [
        { "state": "Lagos", "city": "Ikeja" },
        { "state": "Abuja", "city": "Wuse" }
      ],
      "brand_socials": [
        "https://instagram.com/acme"
      ],
      "ad_media": [
        {
          "images": "https://cdn.example.com/img1.jpg",
          "videos": "https://cdn.example.com/vid1.mp4"
        }
      ],
      "is_active": true,
      "created_at": "2025-06-01T10:00:00Z",
      "updated_at": "2025-06-01T10:00:00Z",
      "task_type": "watch_video",
      "task_type_display": "Watch Video",
      "task_name": "Watch our promo",
      "task_description": "Watch 30 secs of our latest ad.",
      "task_details": {
        "video_url": "https://youtube.com/watch?v=abc123",
        "platform": "YouTube",
        "min_watch_duration": "30s"
      },
      "reward_points": 10,
      "slot_cap": 200,
      "slots_filled": 45,
      "slots_remaining": 155,
      "ads_credit": "0.00",
      "auto_boost_points": 0,
      "location_type": "states",
      "targeting_type": "broad",
      "countries": [],
      "auto_boost": false
    }
  ]
}
```

> `remaining_time` returns `"Expired"` once the campaign duration elapses.

---

## 4. Single Ad Detail — `GET /v1/brands/ads/get/{ad_id}/`

Fetch one ad by its numeric ID. Cached for 5 minutes.

**Auth:** `Bearer <token>`  
**Permission:** Any authenticated user  
**URL param:** `ad_id` — integer

### Success Response `200`

```json
{
  "status": "success",
  "message": "Ad retrieved successfully!",
  "data": {
    // Same shape as a single item in list-all-ads above
  }
}
```

### Error Responses

| Status | Message |
|---|---|
| `404` | `"Ad not found."` |

---

## 5. BrandAd Profile — `GET /v1/brands/ads/profile?email={email}`

Returns the BrandAd profile for any user by email. Cached for 5 minutes.

**Auth:** `Bearer <token>`  
**Permission:** BrandAd | BrandAdAdmin | SuperAdmin

### Query Params

| Param | Required | Description |
|---|---|---|
| `email` | **REQUIRED** | Email address of the BrandAd user to look up |

**Example:** `GET /v1/brands/ads/profile?email=jane@example.com`

### Success Response `200`

```json
{
  "status": "success",
  "message": "Ad detail retrieved successfully!",
  "data": {
    // All CreateAd model fields for that user
  }
}
```

### Error Responses

| Status | Condition |
|---|---|
| `400` | `email` query param missing |
| `403` | User found but does not have BrandAd role |
| `404` | No user found with that email |

---

## 6. Update Profile — `PUT / PATCH /v1/brands/ads/update-profile`

Update the authenticated user's BrandAd profile. Use `PATCH` to update only specific fields.

**Auth:** `Bearer <token>`  
**Permission:** BrandAd | BrandAdAdmin

### Request Payload (all fields optional for PATCH)

```json
{
  "business_or_brand_name": "Acme Co Updated",
  "type_of_business": "Hybrid",
  "industry": "Retail & General Trade",
  "brand_objective": "Drive Sales",
  "campaign_name": "Autumn 2025",
  "gender": "Female",
  "demography": "26 - 35",
  "engagement_type": "Active",
  "daily_allocation": "1000",
  "website": "https://acme.com",
  "brand_socials": ["https://instagram.com/acme"],
  "campaign_duration": "14",
  "amount": "30000",
  "type_of_brand": "Enterprise",
  "location_type": "nationwide",
  "targeting_type": "niche",
  "countries": [],
  "auto_boost": true,
  "task_type": "app_download",
  "task_name": "Download our app",
  "task_description": "Install Acme from the Play Store.",
  "task_details": {
    "app_name": "Acme",
    "play_store_url": "https://play.google.com/store/apps/details?id=com.acme"
  },
  "slot_cap": 500
}
```

### Success Response `200`
Returns the updated ad object (same shape as list-all-ads data item).

### Error Responses

| Status | Condition |
|---|---|
| `400` | Validation errors — returned as a field-keyed object |

---

## 7. List All BrandAd Users — `GET /v1/brands/ads/list-all-ads-users`

Admin-only endpoint. Returns all users with the BrandAd role, paginated 20 per page.

**Auth:** `Bearer <token>`  
**Permission:** BrandAdAdmin only  
**No request body.**

### Query Params

| Param | Required | Description |
|---|---|---|
| `page` | OPTIONAL | Page number (default: 1) |

### Success Response `200`

```json
{
  "count": 50,
  "next": "https://api.example.com/v1/brands/ads/list-all-ads-users?page=2",
  "previous": null,
  "results": [
    {
      // User + CreateAd profile fields
    }
  ]
}
```

---

## Pricing Reference

**Formula:** `total_cost = slot_cap × cost_per_engagement × targeting_multiplier`

| Task Type | 1–3 days | 4–7 days | 8–14 days |
|---|---|---|---|
| `watch_video` | ₦20 | ₦15 | ₦10 |
| `social_engage` | ₦50 | ₦30 | ₦20 |
| `website_visit` | ₦100 | ₦50 | ₦30 |
| `app_download` | ₦400 | ₦200 | ₦150 |
| `survey` | ₦400 | ₦200 | ₦150 |
| `store_visit` | ₦2,000 | ₦1,500 | ₦1,200 |

**Targeting multipliers:** `broad` ×1.00 · `city` ×1.15 · `niche` ×1.25 · `influencer` ×1.50

**Example:** 200 slots · `watch_video` · 7-day campaign · `city` targeting  
→ ₦15 × 1.15 × 200 = **₦3,450**
