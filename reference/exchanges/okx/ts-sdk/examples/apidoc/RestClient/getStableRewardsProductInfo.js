import { RestClient } from 'okx-api';
// or, if require is preferred:
// const { RestClient } = require('okx-api');

// This example shows how to call this OKX API endpoint with either node.js, javascript (js) or typescript (ts) with the npm module "okx-api" for OKX exchange
// This OKX API SDK is available on npm via "npm install okx-api"
// ENDPOINT: /api/v5/finance/stable-rewards/product-info
// METHOD: GET
// PUBLIC: NO

const client = new RestClient({
    apiKey: 'apiKeyHere',
    apiSecret: 'apiSecretHere',
    apiPass: 'apiPassHere',
});

client.getStableRewardsProductInfo(params)
  .then((response) => {
    console.log(response);
  })
  .catch((error) => {
    console.error(error);
  });
