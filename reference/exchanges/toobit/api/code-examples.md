# Code Examples

This document provides API integration examples for different programming languages, applicable to all endpoints that require signatures (common to both Spot and Contract).

## Signature Generation Methods

All endpoints that require signatures (`TRADE` and `USER_DATA`) need to use the HMAC SHA256 algorithm to generate signatures.

### Python

python
```
import hmac
import hashlib
import time

def generate_signature(secret_key, params):
    """
    Generate HMAC SHA256 signature
    :param secret_key: API Secret Key
    :param params: Parameter dictionary (excluding signature)
    :return: Signature string
    """
    # Concatenate parameters into query string format
    query_string = "&".join([f"{k}={v}" for k, v in params.items()])

    # Generate HMAC SHA256 signature
    signature = hmac.new(
        secret_key.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    return signature
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

### Java

java
```
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.InvalidKeyException;
import java.security.NoSuchAlgorithmException;
import java.util.Map;
import java.util.stream.Collectors;

public class SignatureUtil {
    public static String generateSignature(String secretKey, String queryString)
            throws NoSuchAlgorithmException, InvalidKeyException {
        // Generate HMAC SHA256 signature
        Mac mac = Mac.getInstance("HmacSHA256");
        SecretKeySpec secretKeySpec = new SecretKeySpec(
            secretKey.getBytes(StandardCharsets.UTF_8),
            "HmacSHA256"
        );
        mac.init(secretKeySpec);

        byte[] hash = mac.doFinal(queryString.getBytes(StandardCharsets.UTF_8));
        return bytesToHex(hash);
    }

    private static String bytesToHex(byte[] bytes) {
        StringBuilder result = new StringBuilder();
        for (byte b : bytes) {
            result.append(String.format("%02x", b));
        }
        return result.toString();
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
25
26
27
28
29
30
31

### Node.js

javascript
```
const crypto = require('crypto');

/**
 * Generate HMAC SHA256 signature
 * @param {string} secretKey - API Secret Key
 * @param {Object} params - Parameter dictionary (excluding signature)
 * @returns {string} Signature string
 */
function generateSignature(secretKey, params) {
    // Concatenate parameters into query string format
    const queryString = Object.keys(params)
        .map(key => `${key}=${params[key]}`)
        .join('&');

    // Generate HMAC SHA256 signature
    const signature = crypto
        .createHmac('sha256', secretKey)
        .update(queryString)
        .digest('hex');

    return signature;
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

### Go

go
```
package main

import (
    "crypto/hmac"
    "crypto/sha256"
    "encoding/hex"
    "fmt"
    "sort"
    "strings"
)

// GenerateSignature generates HMAC SHA256 signature
// Note: Go map iteration order is random, sort by parameter name for deterministic signature
func GenerateSignature(secretKey string, params map[string]string) string {
    // Sort by parameter name and concatenate query string
    keys := make([]string, 0, len(params))
    for k := range params {
        keys = append(keys, k)
    }
    sort.Strings(keys)
    var parts []string
    for _, k := range keys {
        parts = append(parts, fmt.Sprintf("%s=%s", k, params[k]))
    }
    queryString := strings.Join(parts, "&")

    // Generate HMAC SHA256 signature
    mac := hmac.New(sha256.New, []byte(secretKey))
    mac.Write([]byte(queryString))
    signature := hex.EncodeToString(mac.Sum(nil))

    return signature
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
25
26
27
28
29
30
31
32
33

## Complete Request Examples

The following examples demonstrate how to call an endpoint that requires a signature (applicable to all `TRADE` and `USER_DATA` endpoints).

### Python Complete Example

python
```
import requests
import hmac
import hashlib
import time

def call_signed_api(endpoint, params, api_key, secret_key, method='POST'):
    """
    Call an API endpoint that requires a signature
    :param endpoint: API endpoint path, e.g., '/api/v1/futures/order' or '/api/v1/spot/order'
    :param params: Parameter dictionary
    :param api_key: API Key
    :param secret_key: Secret Key
    :param method: HTTP method, 'GET' or 'POST'
    :return: Response result
    """
    # Add timestamp (required)
    params['timestamp'] = int(time.time() * 1000)

    # Optional: Add recvWindow
    if 'recvWindow' not in params:
        params['recvWindow'] = 5000

    # Generate signature (using the same query_string format)
    query_string_for_sign = "&".join([f"{k}={v}" for k, v in params.items()])
    signature = hmac.new(
        secret_key.encode('utf-8'),
        query_string_for_sign.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    params['signature'] = signature

    # Build complete query string (including signature, using the same order as signature generation)
    query_string = "&".join([f"{k}={v}" for k, v in params.items()])

    # Send request (using the same query_string format to ensure consistent order)
    url = f"https://api.toobit.com{endpoint}"
    headers = {"X-BB-APIKEY": api_key}

    if method == 'GET':
        # GET request: Manually build query string to ensure consistent order with signature
        url_with_params = f"{url}?{query_string}"
        response = requests.get(url_with_params, headers=headers)
    else:
        # POST request: Use manually built query string as body to ensure consistent order
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        response = requests.post(url, headers=headers, data=query_string)

    return response.json()

# Usage example
if __name__ == "__main__":
    api_key = "your-api-key"
    secret_key = "your-secret-key"

    # Example 1: Query account balance (GET request)
    params = {
        "recvWindow": 5000
    }
    result = call_signed_api("/api/v1/futures/balance", params, api_key, secret_key, method='GET')
    print(result)

    # Example 2: Place order (POST request)
    order_params = {
        "symbol": "BTC-SWAP-USDT",
        "side": "BUY_OPEN",
        "type": "LIMIT",
        "quantity": "10",
        "price": "30000",
        "newClientOrderId": "test_order_001",
        "recvWindow": 5000
    }
    result = call_signed_api("/api/v1/futures/order", order_params, api_key, secret_key, method='POST')
    print(result)
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
25
26
27
28
29
30
31
32
33
34
35
36
37
38
39
40
41
42
43
44
45
46
47
48
49
50
51
52
53
54
55
56
57
58
59
60
61
62
63
64
65
66
67
68
69
70
71
72
73

### Java Complete Example

java
```
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

public class ApiClient {
    private String apiKey;
    private String secretKey;
    private String baseUrl = "https://api.toobit.com";

    public ApiClient(String apiKey, String secretKey) {
        this.apiKey = apiKey;
        this.secretKey = secretKey;
    }

    private String buildQueryString(Map<String, String> params) {
        // Build query string (using the same order for signature and request submission)
        return params.entrySet().stream()
                .map(e -> e.getKey() + "=" + e.getValue())
                .collect(Collectors.joining("&"));
    }

    public String callSignedApi(String endpoint, Map<String, String> params, String method)
            throws Exception {
        // Add timestamp
        params.put("timestamp", String.valueOf(System.currentTimeMillis()));

        // Add recvWindow (if not present)
        if (!params.containsKey("recvWindow")) {
            params.put("recvWindow", "5000");
        }

        // Generate signature (using buildQueryString to ensure consistent order)
        String queryStringForSign = buildQueryString(params);
        String signature = SignatureUtil.generateSignature(secretKey, queryStringForSign);
        params.put("signature", signature);

        // Build query string (using the same order as signature generation)
        String queryString = buildQueryString(params);

        // Build URL
        String urlString = baseUrl + endpoint;
        if ("GET".equals(method)) {
            urlString += "?" + queryString;
        }

        // Send request
        URL url = new URL(urlString);
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setRequestMethod(method);
        conn.setRequestProperty("X-BB-APIKEY", apiKey);

        if ("POST".equals(method)) {
            conn.setDoOutput(true);
            // POST request: Use the same query string as body as used for signature
            try (OutputStream os = conn.getOutputStream()) {
                os.write(queryString.getBytes(StandardCharsets.UTF_8));
            }
        }

        // Read response
        BufferedReader reader = new BufferedReader(
                new InputStreamReader(conn.getInputStream()));
        StringBuilder response = new StringBuilder();
        String line;
        while ((line = reader.readLine()) != null) {
            response.append(line);
        }
        reader.close();

        return response.toString();
    }

    // Usage example
    public static void main(String[] args) throws Exception {
        ApiClient client = new ApiClient("your-api-key", "your-secret-key");

        // Example 1: Query account balance (GET request)
        Map<String, String> params1 = new LinkedHashMap<>();
        params1.put("recvWindow", "5000");
        String result1 = client.callSignedApi("/api/v1/futures/balance", params1, "GET");
        System.out.println(result1);

        // Example 2: Place order (POST request)
        Map<String, String> params2 = new LinkedHashMap<>();
        params2.put("symbol", "BTC-SWAP-USDT");
        params2.put("side", "BUY_OPEN");
        params2.put("type", "LIMIT");
        params2.put("quantity", "10");
        params2.put("price", "30000");
        params2.put("newClientOrderId", "test_order_001");
        params2.put("recvWindow", "5000");
        String result2 = client.callSignedApi("/api/v1/futures/order", params2, "POST");
        System.out.println(result2);
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
25
26
27
28
29
30
31
32
33
34
35
36
37
38
39
40
41
42
43
44
45
46
47
48
49
50
51
52
53
54
55
56
57
58
59
60
61
62
63
64
65
66
67
68
69
70
71
72
73
74
75
76
77
78
79
80
81
82
83
84
85
86
87
88
89
90
91
92
93
94
95
96
97
98
99
100
101

### Node.js Complete Example

javascript
```
const crypto = require('crypto');
const https = require('https');
const querystring = require('querystring');

class ApiClient {
    constructor(apiKey, secretKey) {
        this.apiKey = apiKey;
        this.secretKey = secretKey;
        this.baseUrl = 'https://api.toobit.com';
    }

    buildQueryString(params) {
        // Build query string (using the same order for signature and request submission)
        const keys = Object.keys(params);
        return keys
            .map(key => `${key}=${params[key]}`)
            .join('&');
    }

    generateSignature(params) {
        // Use buildQueryString to ensure consistent order
        const queryString = this.buildQueryString(params);

        return crypto
            .createHmac('sha256', this.secretKey)
            .update(queryString)
            .digest('hex');
    }

    async callSignedApi(endpoint, params, method = 'POST') {
        // Add timestamp
        params.timestamp = Date.now();

        // Add recvWindow (if not present)
        if (!params.recvWindow) {
            params.recvWindow = 5000;
        }

        // Generate signature
        const signature = this.generateSignature(params);
        params.signature = signature;

        // Build query string (using the same order as signature generation)
        const queryString = this.buildQueryString(params);

        // Build request
        const url = new URL(this.baseUrl + endpoint);
        const options = {
            method: method,
            headers: {
                'X-BB-APIKEY': this.apiKey
            }
        };

        if (method === 'GET') {
            // GET request: Use the same query string as used for signature
            url.search = queryString;
        } else {
            // POST request: Use the same query string as body as used for signature
            options.headers['Content-Type'] = 'application/x-www-form-urlencoded';
        }

        return new Promise((resolve, reject) => {
            const req = https.request(url, options, (res) => {
                let data = '';
                res.on('data', (chunk) => {
                    data += chunk;
                });
                res.on('end', () => {
                    try {
                        resolve(JSON.parse(data));
                    } catch (e) {
                        resolve(data);
                    }
                });
            });

            req.on('error', (e) => {
                reject(e);
            });

            if (method === 'POST') {
                // POST request: Use the same query string as used for signature
                req.write(queryString);
            }

            req.end();
        });
    }
}

// Usage example
async function main() {
    const client = new ApiClient('your-api-key', 'your-secret-key');

    // Example 1: Query account balance (GET request)
    try {
        const result1 = await client.callSignedApi(
            '/api/v1/futures/balance',
            { recvWindow: 5000 },
            'GET'
        );
        console.log(result1);
    } catch (error) {
        console.error('Error:', error);
    }

    // Example 2: Place order (POST request)
    try {
        const result2 = await client.callSignedApi(
            '/api/v1/futures/order',
            {
                symbol: 'BTC-SWAP-USDT',
                side: 'BUY_OPEN',
                type: 'LIMIT',
                quantity: '10',
                price: '30000',
                newClientOrderId: 'test_order_001',
                recvWindow: 5000
            },
            'POST'
        );
        console.log(result2);
    } catch (error) {
        console.error('Error:', error);
    }
}

main();
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
25
26
27
28
29
30
31
32
33
34
35
36
37
38
39
40
41
42
43
44
45
46
47
48
49
50
51
52
53
54
55
56
57
58
59
60
61
62
63
64
65
66
67
68
69
70
71
72
73
74
75
76
77
78
79
80
81
82
83
84
85
86
87
88
89
90
91
92
93
94
95
96
97
98
99
100
101
102
103
104
105
106
107
108
109
110
111
112
113
114
115
116
117
118
119
120
121
122
123
124
125
126
127
128
129

### Go Complete Example

go
```
package main

import (
    "bytes"
    "crypto/hmac"
    "crypto/sha256"
    "encoding/hex"
    "encoding/json"
    "fmt"
    "io"
    "net/http"
    "strconv"
    "strings"
    "time"
)

type ApiClient struct {
    apiKey    string
    secretKey string
    baseUrl   string
}

func NewApiClient(apiKey, secretKey string) *ApiClient {
    return &ApiClient{
        apiKey:    apiKey,
        secretKey: secretKey,
        baseUrl:   "https://api.toobit.com",
    }
}

func (c *ApiClient) buildQueryString(params map[string]string, keys []string) string {
    // Build query string (using the provided keys order to ensure signature and request consistency)
    // Note: Go's map iteration order is random, so we must use the same keys slice to build query string
    var parts []string
    for _, k := range keys {
        if v, exists := params[k]; exists {
            parts = append(parts, fmt.Sprintf("%s=%s", k, v))
        }
    }
    return strings.Join(parts, "&")
}

func (c *ApiClient) getParamKeys(params map[string]string) []string {
    // Get parameter key list (fixed order, used to ensure signature and request consistency)
    keys := make([]string, 0, len(params))
    for k := range params {
        keys = append(keys, k)
    }
    return keys
}

func (c *ApiClient) generateSignature(params map[string]string, keys []string) string {
    // Build query string (using the provided keys order to ensure consistency with request submission)
    queryString := c.buildQueryString(params, keys)

    // Generate HMAC SHA256 signature
    mac := hmac.New(sha256.New, []byte(c.secretKey))
    mac.Write([]byte(queryString))
    signature := hex.EncodeToString(mac.Sum(nil))

    return signature
}

func (c *ApiClient) CallSignedApi(endpoint string, params map[string]string, method string) (map[string]interface{}, error) {
    // Add timestamp
    params["timestamp"] = strconv.FormatInt(time.Now().UnixMilli(), 10)

    // Add recvWindow (if not present)
    if _, exists := params["recvWindow"]; !exists {
        params["recvWindow"] = "5000"
    }

    // Get parameter key list (used to ensure signature and request use the same order)
    keys := c.getParamKeys(params)

    // Generate signature (using keys order)
    signature := c.generateSignature(params, keys)
    params["signature"] = signature

    // Append "signature" to existing keys to preserve order (Go map iteration is random, do not call getParamKeys again)
    keysForRequest := append(keys, "signature")

    // Build query string (using the same keys order as signature generation)
    queryString := c.buildQueryString(params, keysForRequest)

    var req *http.Request
    var err error

    url := c.baseUrl + endpoint

    if method == "GET" {
        // GET request: Use the same query string as used for signature
        url += "?" + queryString
        req, err = http.NewRequest(method, url, nil)
    } else {
        // POST request: Use the same query string as body as used for signature
        req, err = http.NewRequest(method, url, strings.NewReader(queryString))
        req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
    }

    if err != nil {
        return nil, err
    }

    req.Header.Set("X-BB-APIKEY", c.apiKey)

    client := &http.Client{}
    resp, err := client.Do(req)
    if err != nil {
        return nil, err
    }
    defer resp.Body.Close()

    body, err := io.ReadAll(resp.Body)
    if err != nil {
        return nil, err
    }

    var result map[string]interface{}
    err = json.Unmarshal(body, &result)
    if err != nil {
        return nil, err
    }

    return result, nil
}

// Usage example
func main() {
    client := NewApiClient("your-api-key", "your-secret-key")

    // Example 1: Query account balance (GET request)
    params1 := map[string]string{
        "recvWindow": "5000",
    }
    result1, err := client.CallSignedApi("/api/v1/futures/balance", params1, "GET")
    if err != nil {
        fmt.Printf("Error: %v\n", err)
    } else {
        fmt.Printf("Result: %+v\n", result1)
    }

    // Example 2: Place order (POST request)
    params2 := map[string]string{
        "symbol":          "BTC-SWAP-USDT",
        "side":            "BUY_OPEN",
        "type":            "LIMIT",
        "quantity":        "10",
        "price":           "30000",
        "newClientOrderId": "test_order_001",
        "recvWindow":      "5000",
    }
    result2, err := client.CallSignedApi("/api/v1/futures/order", params2, "POST")
    if err != nil {
        fmt.Printf("Error: %v\n", err)
    } else {
        fmt.Printf("Result: %+v\n", result2)
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
25
26
27
28
29
30
31
32
33
34
35
36
37
38
39
40
41
42
43
44
45
46
47
48
49
50
51
52
53
54
55
56
57
58
59
60
61
62
63
64
65
66
67
68
69
70
71
72
73
74
75
76
77
78
79
80
81
82
83
84
85
86
87
88
89
90
91
92
93
94
95
96
97
98
99
100
101
102
103
104
105
106
107
108
109
110
111
112
113
114
115
116
117
118
119
120
121
122
123
124
125
126
127
128
129
130
131
132
133
134
135
136
137
138
139
140
141
142
143
144
145
146
147
148
149
150
151
152
153
154
155
156
157
158
159

### cURL Example

bash
```
#!/bin/bash

API_KEY="your-api-key"
SECRET_KEY="your-secret-key"
BASE_URL="https://api.toobit.com"

# Signature generation function
generate_signature() {
    local params="$1"
    echo -n "$params" | openssl dgst -sha256 -hmac "$SECRET_KEY" | awk '{print $2}'
}

# Call API that requires signature
call_signed_api() {
    local endpoint="$1"
    local method="${2:-POST}"
    local params="$3"

    # Add timestamp
    local timestamp=$(date +%s)000
    if [ -z "$params" ]; then
        params="timestamp=${timestamp}"
    else
        params="${params}&timestamp=${timestamp}"
    fi

    # Add recvWindow (if not present)
    if [[ ! "$params" =~ recvWindow ]]; then
        params="${params}&recvWindow=5000"
    fi

    # Generate signature
    local signature=$(generate_signature "$params")
    params="${params}&signature=${signature}"

    # Send request
    if [ "$method" = "GET" ]; then
        curl -X GET "${BASE_URL}${endpoint}?${params}" \
            -H "X-BB-APIKEY: ${API_KEY}"
    else
        curl -X POST "${BASE_URL}${endpoint}" \
            -H "X-BB-APIKEY: ${API_KEY}" \
            -H "Content-Type: application/x-www-form-urlencoded" \
            -d "${params}"
    fi
}

# Usage examples
# Example 1: Query account balance (GET request)
call_signed_api "/api/v1/futures/balance" "GET" ""

# Example 2: Place order (POST request)
call_signed_api "/api/v1/futures/order" "POST" \
    "symbol=BTC-SWAP-USDT&side=BUY_OPEN&type=LIMIT&quantity=10&price=30000&newClientOrderId=test_001"
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
25
26
27
28
29
30
31
32
33
34
35
36
37
38
39
40
41
42
43
44
45
46
47
48
49
50
51
52
53
54

## JSON Request Body Signing Examples (API v2)

Endpoints under `/api/v2/` with `Content-Type: application/json` (e.g. new order, batch orders) use the following signing scheme:

**String-to-sign construction rule:**
```
 string_to_sign = query string (excluding signature) + raw JSON body
```

1

The two parts are **concatenated directly with no separator**.

**Request structure:**

Location| Parameters
---|---
URL query params| `timestamp`, `recvWindow` (optional), `signature`, and other shared params (e.g. `category`)
Request headers| `X-BB-APIKEY`, `Content-Type: application/json`
Request body| Raw JSON string — must be **byte-for-byte identical** to what was signed; must use **compact format (no newlines)**. The server reads the body line-by-line and strips line terminators, so pretty-printed JSON will cause a signature mismatch.

### Python

python
```
import hmac
import hashlib
import json
import time
import requests

API_KEY  = "your-api-key"
SECRET   = "your-secret-key"
BASE_URL = "https://api.toobit.com"

def v2_json_request(endpoint, body, extra_query=None):
    """
    V2 JSON body signed request.
    string_to_sign = query string (no signature) + raw JSON body (no separator).
    timestamp / recvWindow / signature go in the URL; business params go in the JSON body.
    """
    timestamp = int(time.time() * 1000)
    query = {"timestamp": timestamp, "recvWindow": 5000}
    if extra_query:
        query.update(extra_query)

    # Serialize JSON body — must be identical to what is actually sent
    json_body = json.dumps(body, separators=(',', ':'))

    # string_to_sign = query string + JSON body (no separator)
    query_str = "&".join(f"{k}={v}" for k, v in query.items())
    sign_str  = query_str + json_body

    sig = hmac.new(SECRET.encode(), sign_str.encode(), hashlib.sha256).hexdigest()

    url     = f"{BASE_URL}{endpoint}?{query_str}&signature={sig}"
    headers = {"X-BB-APIKEY": API_KEY, "Content-Type": "application/json"}
    return requests.post(url, headers=headers, data=json_body).json()

# Example 1: New regular order (JSON object body)
order = {
    "symbol": "BTC-SWAP-USDT",
    "side": "BUY",
    "positionSide": "LONG",
    "type": "LIMIT",
    "newClientOrderId": "v2_order_001",
    "quantity": "1",
    "price": "30000",
}
print(v2_json_request("/api/v2/futures/order", order))

# Example 2: Batch new orders (JSON array body)
batch = [
    {"symbol": "BTC-SWAP-USDT", "side": "BUY", "positionSide": "LONG",
     "type": "LIMIT", "newClientOrderId": "batch_001", "quantity": "1", "price": "30000"},
    {"symbol": "ETH-SWAP-USDT", "side": "SELL", "positionSide": "SHORT",
     "type": "LIMIT", "newClientOrderId": "batch_002", "quantity": "2", "price": "2000"},
]
print(v2_json_request("/api/v2/futures/batch-orders", batch, extra_query={"category": "USDT"}))
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
25
26
27
28
29
30
31
32
33
34
35
36
37
38
39
40
41
42
43
44
45
46
47
48
49
50
51
52
53
54
55

### Java

java
```
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Instant;

public class V2JsonApiClient {

    private static final String API_KEY  = "your-api-key";
    private static final String SECRET   = "your-secret-key";
    private static final String BASE_URL = "https://api.toobit.com";

    static String hmacSha256(String key, String data) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        byte[] hash = mac.doFinal(data.getBytes(StandardCharsets.UTF_8));
        StringBuilder sb = new StringBuilder();
        for (byte b : hash) sb.append(String.format("%02x", b));
        return sb.toString();
    }

    /**
     * V2 JSON body signed request.
     * string_to_sign = query string (no signature) + raw JSON body (no separator).
     *
     * @param endpoint   e.g. /api/v2/futures/order
     * @param jsonBody   raw JSON string — must match the actual request body byte-for-byte
     * @param extraQuery additional query params, e.g. "category=USDT"; pass null if none
     */
    static String v2JsonRequest(String endpoint, String jsonBody, String extraQuery) throws Exception {
        long timestamp = Instant.now().toEpochMilli();
        String queryStr = "timestamp=" + timestamp + "&recvWindow=5000"
                + (extraQuery != null && !extraQuery.isEmpty() ? "&" + extraQuery : "");

        // string_to_sign = query string + JSON body (no separator)
        String signature = hmacSha256(SECRET, queryStr + jsonBody);

        String url = BASE_URL + endpoint + "?" + queryStr + "&signature=" + signature;
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .header("X-BB-APIKEY", API_KEY)
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(jsonBody, StandardCharsets.UTF_8))
                .build();

        return HttpClient.newHttpClient()
                .send(request, HttpResponse.BodyHandlers.ofString())
                .body();
    }

    public static void main(String[] args) throws Exception {
        // Example 1: New regular order
        String orderBody = "{\"symbol\":\"BTC-SWAP-USDT\",\"side\":\"BUY\",\"positionSide\":\"LONG\","
                + "\"type\":\"LIMIT\",\"newClientOrderId\":\"v2_order_001\","
                + "\"quantity\":\"1\",\"price\":\"30000\"}";
        System.out.println(v2JsonRequest("/api/v2/futures/order", orderBody, null));

        // Example 2: Batch new orders (JSON array body)
        String batchBody = "[{\"symbol\":\"BTC-SWAP-USDT\",\"side\":\"BUY\",\"positionSide\":\"LONG\","
                + "\"type\":\"LIMIT\",\"newClientOrderId\":\"batch_001\",\"quantity\":\"1\",\"price\":\"30000\"},"
                + "{\"symbol\":\"ETH-SWAP-USDT\",\"side\":\"SELL\",\"positionSide\":\"SHORT\","
                + "\"type\":\"LIMIT\",\"newClientOrderId\":\"batch_002\",\"quantity\":\"2\",\"price\":\"2000\"}]";
        System.out.println(v2JsonRequest("/api/v2/futures/batch-orders", batchBody, "category=USDT"));
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
25
26
27
28
29
30
31
32
33
34
35
36
37
38
39
40
41
42
43
44
45
46
47
48
49
50
51
52
53
54
55
56
57
58
59
60
61
62
63
64
65
66
67
68

### Node.js

javascript
```
const crypto = require('crypto');
const https  = require('https');

const API_KEY  = 'your-api-key';
const SECRET   = 'your-secret-key';
const BASE_URL = 'api.toobit.com';

/**
 * V2 JSON body signed request.
 * string_to_sign = query string (no signature) + raw JSON body (no separator)
 */
function v2JsonRequest(endpoint, body, extraQuery = {}) {
    return new Promise((resolve, reject) => {
        const timestamp = Date.now();
        const query = { timestamp, recvWindow: 5000, ...extraQuery };

        // Serialize JSON body — must be identical to what is actually sent
        const jsonBody  = JSON.stringify(body);
        const queryStr  = Object.entries(query).map(([k, v]) => `${k}=${v}`).join('&');
        const signature = crypto.createHmac('sha256', SECRET)
            .update(queryStr + jsonBody)
            .digest('hex');

        const path = `${endpoint}?${queryStr}&signature=${signature}`;
        const options = {
            hostname: BASE_URL,
            path,
            method: 'POST',
            headers: {
                'X-BB-APIKEY': API_KEY,
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(jsonBody),
            },
        };

        const req = https.request(options, res => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => resolve(JSON.parse(data)));
        });
        req.on('error', reject);
        req.write(jsonBody);
        req.end();
    });
}

// Example 1: New regular order
v2JsonRequest('/api/v2/futures/order', {
    symbol: 'BTC-SWAP-USDT', side: 'BUY', positionSide: 'LONG',
    type: 'LIMIT', newClientOrderId: 'v2_order_001', quantity: '1', price: '30000',
}).then(console.log).catch(console.error);

// Example 2: Batch new orders (JSON array body)
v2JsonRequest('/api/v2/futures/batch-orders', [
    { symbol: 'BTC-SWAP-USDT', side: 'BUY', positionSide: 'LONG',
      type: 'LIMIT', newClientOrderId: 'batch_001', quantity: '1', price: '30000' },
    { symbol: 'ETH-SWAP-USDT', side: 'SELL', positionSide: 'SHORT',
      type: 'LIMIT', newClientOrderId: 'batch_002', quantity: '2', price: '2000' },
], { category: 'USDT' }).then(console.log).catch(console.error);
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
25
26
27
28
29
30
31
32
33
34
35
36
37
38
39
40
41
42
43
44
45
46
47
48
49
50
51
52
53
54
55
56
57
58
59

### Go

go
```
package main

import (
    "bytes"
    "crypto/hmac"
    "crypto/sha256"
    "encoding/hex"
    "encoding/json"
    "fmt"
    "io"
    "net/http"
    "strconv"
    "time"
)

const (
    apiKey  = "your-api-key"
    secret  = "your-secret-key"
    baseURL = "https://api.toobit.com"
)

func hmacSha256(key, data string) string {
    mac := hmac.New(sha256.New, []byte(key))
    mac.Write([]byte(data))
    return hex.EncodeToString(mac.Sum(nil))
}

// v2JsonRequest sends a V2 JSON body signed request.
// string_to_sign = query string (no signature) + raw JSON body (no separator).
// body may be a map (single order) or []map (batch); extraQuery e.g. "category=USDT".
func v2JsonRequest(endpoint string, body any, extraQuery string) (string, error) {
    jsonBytes, err := json.Marshal(body)
    if err != nil {
        return "", err
    }
    jsonBody := string(jsonBytes)

    timestamp := strconv.FormatInt(time.Now().UnixMilli(), 10)
    queryStr  := "timestamp=" + timestamp + "&recvWindow=5000"
    if extraQuery != "" {
        queryStr += "&" + extraQuery
    }

    // string_to_sign = query string + JSON body (no separator)
    signature := hmacSha256(secret, queryStr+jsonBody)

    url := baseURL + endpoint + "?" + queryStr + "&signature=" + signature
    req, err := http.NewRequest("POST", url, bytes.NewBufferString(jsonBody))
    if err != nil {
        return "", err
    }
    req.Header.Set("X-BB-APIKEY", apiKey)
    req.Header.Set("Content-Type", "application/json")

    resp, err := http.DefaultClient.Do(req)
    if err != nil {
        return "", err
    }
    defer resp.Body.Close()
    result, _ := io.ReadAll(resp.Body)
    return string(result), nil
}

func main() {
    // Example 1: New regular order
    order := map[string]string{
        "symbol": "BTC-SWAP-USDT", "side": "BUY", "positionSide": "LONG",
        "type": "LIMIT", "newClientOrderId": "v2_order_001",
        "quantity": "1", "price": "30000",
    }
    result, err := v2JsonRequest("/api/v2/futures/order", order, "")
    if err != nil {
        fmt.Println("Error:", err)
    } else {
        fmt.Println(result)
    }

    // Example 2: Batch new orders (JSON array body)
    batch := []map[string]string{
        {"symbol": "BTC-SWAP-USDT", "side": "BUY", "positionSide": "LONG",
            "type": "LIMIT", "newClientOrderId": "batch_001", "quantity": "1", "price": "30000"},
        {"symbol": "ETH-SWAP-USDT", "side": "SELL", "positionSide": "SHORT",
            "type": "LIMIT", "newClientOrderId": "batch_002", "quantity": "2", "price": "2000"},
    }
    result, err = v2JsonRequest("/api/v2/futures/batch-orders", batch, "category=USDT")
    if err != nil {
        fmt.Println("Error:", err)
    } else {
        fmt.Println(result)
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
25
26
27
28
29
30
31
32
33
34
35
36
37
38
39
40
41
42
43
44
45
46
47
48
49
50
51
52
53
54
55
56
57
58
59
60
61
62
63
64
65
66
67
68
69
70
71
72
73
74
75
76
77
78
79
80
81
82
83
84
85
86
87
88
89
90
91

### cURL

bash
```
#!/bin/bash

API_KEY="your-api-key"
SECRET_KEY="your-secret-key"
BASE_URL="https://api.toobit.com"

# V2 JSON body signing: string_to_sign = query string (no signature) + raw JSON body (no separator)
sign_v2_json() {
    local query_str="$1"  # e.g. "timestamp=xxx&recvWindow=5000"
    local json_body="$2"  # raw JSON string
    echo -n "${query_str}${json_body}" | openssl dgst -sha256 -hmac "$SECRET_KEY" | awk '{print $2}'
}

TIMESTAMP=$(date +%s)000

# Example 1: New regular order
JSON_BODY='{"symbol":"BTC-SWAP-USDT","side":"BUY","positionSide":"LONG","type":"LIMIT","newClientOrderId":"v2_001","quantity":"1","price":"30000"}'
QUERY_STR="timestamp=${TIMESTAMP}&recvWindow=5000"
SIG=$(sign_v2_json "$QUERY_STR" "$JSON_BODY")

curl -s -X POST "${BASE_URL}/api/v2/futures/order?${QUERY_STR}&signature=${SIG}" \
    -H "X-BB-APIKEY: ${API_KEY}" \
    -H "Content-Type: application/json" \
    -d "${JSON_BODY}"
echo ""

# Example 2: Batch new orders (JSON array body)
BATCH_BODY='[{"symbol":"BTC-SWAP-USDT","side":"BUY","positionSide":"LONG","type":"LIMIT","newClientOrderId":"batch_001","quantity":"1","price":"30000"},{"symbol":"ETH-SWAP-USDT","side":"SELL","positionSide":"SHORT","type":"LIMIT","newClientOrderId":"batch_002","quantity":"2","price":"2000"}]'
QUERY_STR2="timestamp=${TIMESTAMP}&recvWindow=5000&category=USDT"
SIG2=$(sign_v2_json "$QUERY_STR2" "$BATCH_BODY")

curl -s -X POST "${BASE_URL}/api/v2/futures/batch-orders?${QUERY_STR2}&signature=${SIG2}" \
    -H "X-BB-APIKEY: ${API_KEY}" \
    -H "Content-Type: application/json" \
    -d "${BATCH_BODY}"
echo ""
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
25
26
27
28
29
30
31
32
33
34
35
36

## Notes

  1. **Timestamp** : Must use millisecond-level Unix timestamp
  2. **Signature format** : The signature must be a lowercase hexadecimal string and is case sensitive; do not use uppercase
  3. **Signature does not include signature field** : When generating signature, the parameter dictionary should not include the `signature` field
  4. **Mixed parameters** : When using both query string and request body, the signature input should be query string first, then request body, with no `&` separator in between
  5. **API v2 + JSON body** : For `POST` under `/api/v2/` with `Content-Type: application/json` (e.g. `POST /api/v2/futures/batch-orders`), the string to sign is the query string (including `timestamp`, etc.) **concatenated with the raw JSON body** —no `&` between them. The JSON body must use **compact format (no newlines)** ; the server reads the body line-by-line and strips line terminators, so sending pretty-printed JSON will cause a signature mismatch. The signed JSON string must match the actual request body byte-for-byte. See Basic information — JSON request body signing (API v2).

## More Information

  * For detailed signature instructions, please refer to Basic Information - SIGNED Endpoint Security
  * For specific endpoint parameters and response formats, please refer to the corresponding endpoint documentation
