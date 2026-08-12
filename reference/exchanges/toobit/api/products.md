# Product Management

Manage your product catalog through the API.

## The Product Object

json
```
{
  "id": "prd_123",
  "name": "Premium Widget",
  "description": "A high-quality widget for your needs",
  "sku": "WGT-001",
  "price": 29.99,
  "currency": "USD",
  "stock": 100,
  "category": "widgets",
  "images": [
    "https://example.com/products/prd_123_1.jpg",
    "https://example.com/products/prd_123_2.jpg"
  ],
  "status": "active",
  "created_at": "2025-01-01T00:00:00Z",
  "updated_at": "2025-01-15T10:30:00Z"
}
```

1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17

### Attributes

Attribute| Type| Description
---|---|---
id| string| Unique identifier for the product
name| string| Product name
description| string| Product description
sku| string| Stock Keeping Unit
price| number| Product price
currency| string| Currency code (ISO 4217)
stock| integer| Available quantity
category| string| Product category
images| array| Array of image URLs
status| string| Product status: `active`, `draft`, `archived`
created_at| string| ISO 8601 timestamp of creation
updated_at| string| ISO 8601 timestamp of last update

## List All Products

Retrieve a paginated list of products.

http
```
GET /v1/products
```

1

### Query Parameters

Parameter| Type| Default| Description
---|---|---|---
page| integer| 1| Page number
limit| integer| 20| Items per page (max: 100)
category| string| -| Filter by category
status| string| active| Filter by status
min_price| number| -| Minimum price filter
max_price| number| -| Maximum price filter
search| string| -| Search by name or SKU

### Example Request

bash
```
curl -X GET "https://api.example.com/v1/products?category=widgets&status=active" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

1
2

### Example Response

json
```
{
  "success": true,
  "data": [
    {
      "id": "prd_123",
      "name": "Premium Widget",
      "description": "A high-quality widget for your needs",
      "sku": "WGT-001",
      "price": 29.99,
      "currency": "USD",
      "stock": 100,
      "category": "widgets",
      "status": "active",
      "created_at": "2025-01-01T00:00:00Z",
      "updated_at": "2025-01-15T10:30:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 20,
    "total": 1,
    "pages": 1
  }
}
```

1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24

## Get a Product

Retrieve details of a specific product.

http
```
GET /v1/products/{product_id}
```

1

### Example Request

bash
```
curl -X GET https://api.example.com/v1/products/prd_123 \
  -H "Authorization: Bearer YOUR_API_KEY"
```

1
2

### Example Response

json
```
{
  "success": true,
  "data": {
    "id": "prd_123",
    "name": "Premium Widget",
    "description": "A high-quality widget for your needs",
    "sku": "WGT-001",
    "price": 29.99,
    "currency": "USD",
    "stock": 100,
    "category": "widgets",
    "images": [
      "https://example.com/products/prd_123_1.jpg"
    ],
    "status": "active",
    "created_at": "2025-01-01T00:00:00Z",
    "updated_at": "2025-01-15T10:30:00Z"
  }
}
```

1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19

## Create a Product

Create a new product.

http
```
POST /v1/products
```

1

### Request Body

json
```
{
  "name": "New Widget",
  "description": "An amazing new widget",
  "sku": "WGT-002",
  "price": 39.99,
  "currency": "USD",
  "stock": 50,
  "category": "widgets",
  "status": "active"
}
```

1
2
3
4
5
6
7
8
9
10

### Example Request

bash
```
curl -X POST https://api.example.com/v1/products \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "New Widget",
    "description": "An amazing new widget",
    "sku": "WGT-002",
    "price": 39.99,
    "currency": "USD",
    "stock": 50,
    "category": "widgets",
    "status": "active"
  }'
```

1
2
3
4
5
6
7
8
9
10
11
12
13

### Example Response

json
```
{
  "success": true,
  "data": {
    "id": "prd_456",
    "name": "New Widget",
    "description": "An amazing new widget",
    "sku": "WGT-002",
    "price": 39.99,
    "currency": "USD",
    "stock": 50,
    "category": "widgets",
    "status": "active",
    "created_at": "2025-01-20T15:00:00Z",
    "updated_at": "2025-01-20T15:00:00Z"
  },
  "message": "Product created successfully"
}
```

1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17

## Update a Product

Update an existing product.

http
```
PATCH /v1/products/{product_id}
```

1

### Request Body

json
```
{
  "price": 34.99,
  "stock": 75
}
```

1
2
3
4

### Example Request

bash
```
curl -X PATCH https://api.example.com/v1/products/prd_123 \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "price": 34.99,
    "stock": 75
  }'
```

1
2
3
4
5
6
7

### Example Response

json
```
{
  "success": true,
  "data": {
    "id": "prd_123",
    "name": "Premium Widget",
    "price": 34.99,
    "stock": 75,
    "updated_at": "2025-01-20T16:00:00Z"
  },
  "message": "Product updated successfully"
}
```

1
2
3
4
5
6
7
8
9
10
11

## Delete a Product

Delete a product permanently.

http
```
DELETE /v1/products/{product_id}
```

1

### Example Request

bash
```
curl -X DELETE https://api.example.com/v1/products/prd_123 \
  -H "Authorization: Bearer YOUR_API_KEY"
```

1
2

### Example Response

json
```
{
  "success": true,
  "message": "Product deleted successfully"
}
```

1
2
3
4

## Bulk Operations

### Bulk Update Stock

Update stock levels for multiple products at once.

http
```
POST /v1/products/bulk/stock
```

1

### Request Body

json
```
{
  "updates": [
    {
      "product_id": "prd_123",
      "stock": 150
    },
    {
      "product_id": "prd_456",
      "stock": 200
    }
  ]
}
```

1
2
3
4
5
6
7
8
9
10
11
12

### Example Response

json
```
{
  "success": true,
  "data": {
    "updated": 2,
    "failed": 0
  },
  "message": "Stock updated successfully"
}
```

1
2
3
4
5
6
7
8

## Error Responses

### 400 Bad Request

json
```
{
  "success": false,
  "error": {
    "code": "invalid_request",
    "message": "Price must be a positive number",
    "field": "price"
  }
}
```

1
2
3
4
5
6
7
8

### 404 Not Found

json
```
{
  "success": false,
  "error": {
    "code": "not_found",
    "message": "Product not found"
  }
}
```

1
2
3
4
5
6
7

### 409 Conflict

json
```
{
  "success": false,
  "error": {
    "code": "duplicate_sku",
    "message": "A product with this SKU already exists"
  }
}
```

1
2
3
4
5
6
7
