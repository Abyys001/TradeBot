# User Management

Manage users through the API.

## The User Object

json
```
{
  "id": "usr_123",
  "name": "John Doe",
  "email": "john@example.com",
  "role": "admin",
  "status": "active",
  "avatar": "https://example.com/avatars/usr_123.jpg",
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

### Attributes

Attribute| Type| Description
---|---|---
id| string| Unique identifier for the user
name| string| User's full name
email| string| User's email address
role| string| User role: `admin`, `user`, `viewer`
status| string| Account status: `active`, `inactive`, `suspended`
avatar| string| URL to user's avatar image
created_at| string| ISO 8601 timestamp of creation
updated_at| string| ISO 8601 timestamp of last update

## List All Users

Retrieve a paginated list of users.

http
```
GET /v1/users
```

1

### Query Parameters

Parameter| Type| Default| Description
---|---|---|---
page| integer| 1| Page number
limit| integer| 20| Items per page (max: 100)
role| string| -| Filter by role
status| string| -| Filter by status
search| string| -| Search by name or email

### Example Request

bash
```
curl -X GET "https://api.example.com/v1/users?page=1&limit=20&role=admin" \
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
      "id": "usr_123",
      "name": "John Doe",
      "email": "john@example.com",
      "role": "admin",
      "status": "active",
      "avatar": "https://example.com/avatars/usr_123.jpg",
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

## Get a User

Retrieve details of a specific user.

http
```
GET /v1/users/{user_id}
```

1

### Example Request

bash
```
curl -X GET https://api.example.com/v1/users/usr_123 \
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
    "id": "usr_123",
    "name": "John Doe",
    "email": "john@example.com",
    "role": "admin",
    "status": "active",
    "avatar": "https://example.com/avatars/usr_123.jpg",
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

## Create a User

Create a new user.

http
```
POST /v1/users
```

1

### Request Body

json
```
{
  "name": "Jane Smith",
  "email": "jane@example.com",
  "role": "user",
  "password": "secure_password_123"
}
```

1
2
3
4
5
6

### Example Request

bash
```
curl -X POST https://api.example.com/v1/users \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Jane Smith",
    "email": "jane@example.com",
    "role": "user",
    "password": "secure_password_123"
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

### Example Response

json
```
{
  "success": true,
  "data": {
    "id": "usr_456",
    "name": "Jane Smith",
    "email": "jane@example.com",
    "role": "user",
    "status": "active",
    "created_at": "2025-01-20T15:00:00Z",
    "updated_at": "2025-01-20T15:00:00Z"
  },
  "message": "User created successfully"
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

## Update a User

Update an existing user's information.

http
```
PATCH /v1/users/{user_id}
```

1

### Request Body

json
```
{
  "name": "John Smith",
  "role": "admin"
}
```

1
2
3
4

### Example Request

bash
```
curl -X PATCH https://api.example.com/v1/users/usr_123 \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Smith",
    "role": "admin"
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
    "id": "usr_123",
    "name": "John Smith",
    "email": "john@example.com",
    "role": "admin",
    "status": "active",
    "updated_at": "2025-01-20T16:00:00Z"
  },
  "message": "User updated successfully"
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

## Delete a User

Delete a user permanently.

http
```
DELETE /v1/users/{user_id}
```

1

### Example Request

bash
```
curl -X DELETE https://api.example.com/v1/users/usr_123 \
  -H "Authorization: Bearer YOUR_API_KEY"
```

1
2

### Example Response

json
```
{
  "success": true,
  "message": "User deleted successfully"
}
```

1
2
3
4

## Error Responses

### 400 Bad Request

json
```
{
  "success": false,
  "error": {
    "code": "invalid_request",
    "message": "Invalid email format",
    "field": "email"
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
    "message": "User not found"
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
    "code": "duplicate_email",
    "message": "A user with this email already exists"
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
