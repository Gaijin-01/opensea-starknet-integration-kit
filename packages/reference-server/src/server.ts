/**
 * @storm/reference-server
 *
 * Minimal HTTP server demonstrating the API contract between the kit
 * and a marketplace backend. Shows the routes needed for a Starknet NFT
 * marketplace integration with OpenSea-style APIs.
 *
 * Routes:
 *   GET  /health                                    — health check
 *   GET  /v1/starknet/assets/:contract/:tokenId    — get asset from indexer
 *   GET  /v1/starknet/accounts/:address/assets     — get assets by owner
 *   GET  /v1/starknet/listings                     — get all active listings
 *   GET  /v1/starknet/assets/:contract/:tokenId/listings — listings for an asset
 *   POST /v1/starknet/venues/:venue/list           — create listing
 *   POST /v1/starknet/venues/:venue/fulfill        — fulfill listing
 *   POST /v1/starknet/venues/:venue/cancel         — cancel listing
 */

import { createServer, type IncomingMessage, type ServerResponse } from "node:http"

// Environment
const STARKNET_RPC = process.env.STARKNET_RPC ?? "https://starknet-sepolia.infura.io/v3/YOUR_INFURA_KEY"
const MEDIALANE_API_KEY = process.env.MEDIALANE_API_KEY ?? ""
const PORT = parseInt(process.env.PORT ?? "3001", 10)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function jsonResponse(res: ServerResponse, status: number, data: unknown): void {
  res.writeHead(status, { "Content-Type": "application/json" })
  res.end(JSON.stringify(data))
}

function parseBody(req: IncomingMessage): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    let body = ""
    req.on("data", (chunk: string) => (body += chunk))
    req.on("end", () => {
      try {
        resolve(body ? JSON.parse(body) : {})
      } catch {
        reject(new Error("Invalid JSON"))
      }
    })
    req.on("error", reject)
  })
}

function requireWalletSignature(req: IncomingMessage): { address: string } | null {
  // SECURITY NOTE: This reference implementation performs NO cryptographic verification.
  // Any caller supplying an X-Wallet-Address header is accepted as that address.
  // PRODUCTION: must verify a SNIP-12 signed message challenge from the wallet.
  // Until implemented, mark these routes as requiring external authentication.
  const address = req.headers["x-wallet-address"] as string | undefined
  if (!address) return null
  return { address }
}

// ---------------------------------------------------------------------------
// Routes
// ---------------------------------------------------------------------------

async function handleRequest(req: IncomingMessage, res: ServerResponse): Promise<void> {
  // CORS preflight
  if (req.method === "OPTIONS") {
    res.writeHead(204, {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, X-Wallet-Address",
    })
    res.end()
    return
  }

  res.setHeader("Access-Control-Allow-Origin", "*")

  const url = req.url ?? "/"
  const [base, query] = url.split("?")

  try {
    // GET /health
    if (req.method === "GET" && base === "/health") {
      jsonResponse(res, 200, { status: "ok", timestamp: new Date().toISOString() })
      return
    }

    // GET /v1/starknet/assets/:contract/:tokenId
    const assetMatch = base.match(/^\/v1\/starknet\/assets\/([^/]+)\/([^/]+)$/)
    if (req.method === "GET" && assetMatch && !assetMatch.input?.includes("/listings")) {
      const [, contract, tokenId] = assetMatch
      // In production: query indexer for asset
      jsonResponse(res, 200, {
        contract,
        tokenId,
        chain: "starknet",
        // Placeholder — real implementation fetches from @storm/indexer
        owner: null,
        metadata: null,
      })
      return
    }

    // GET /v1/starknet/accounts/:address/assets
    const accountMatch = base.match(/^\/v1\/starknet\/accounts\/([^/]+)\/assets$/)
    if (req.method === "GET" && accountMatch) {
      const [, address] = accountMatch
      jsonResponse(res, 200, {
        address,
        assets: [],
        // Placeholder — real implementation fetches from @storm/indexer
      })
      return
    }

    // GET /v1/starknet/listings
    if (req.method === "GET" && base === "/v1/starknet/listings") {
      // Aggregated across all venues — placeholder
      jsonResponse(res, 200, { listings: [] })
      return
    }

    // GET /v1/starknet/assets/:contract/:tokenId/listings
    const listingsMatch = base.match(/^\/v1\/starknet\/assets\/([^/]+)\/([^/]+)\/listings$/)
    if (req.method === "GET" && listingsMatch) {
      jsonResponse(res, 200, { listings: [] })
      return
    }

    // POST /v1/starknet/venues/:venue/list
    const listMatch = base.match(/^\/v1\/starknet\/venues\/([^/]+)\/list$/)
    if (req.method === "POST" && listMatch) {
      const wallet = requireWalletSignature(req)
      if (!wallet) {
        jsonResponse(res, 401, { error: "Wallet signature required" })
        return
      }
      const body = await parseBody(req).catch(() => null)
      if (!body) {
        jsonResponse(res, 400, { error: "Invalid request body" })
        return
      }
      const venue = listMatch[1]

      try {
        let result: { transactionHash?: string; status?: string }
        if (venue === "ark") {
          // Ark settlement is browser-side: the browser has the wallet account.
          // The reference server returns the listing parameters so the client can
          // build and submit the transaction directly via @storm/venue-ark.
          // This avoids pulling venue-ark (and its internal SDK deps) into the server.
          const bodyTyped = body as { asset?: { contractAddress: string; tokenId: string; standard: string }; price?: { amount: string; currency: string; decimals: number } }
          if (!bodyTyped.asset || !bodyTyped.price) {
            jsonResponse(res, 400, { error: "asset and price are required" })
            return
          }
          jsonResponse(res, 200, {
            venue: "ark",
            action: "CREATE_LISTING",
            maker: wallet.address,
            asset: bodyTyped.asset,
            price: bodyTyped.price,
            // Client should use @storm/venue-ark in the browser with the wallet account.
            instructions: "Use ArkAdapter.createListing() in the browser with the wallet Account.",
          })
        } else if (venue === "medialane") {
          // Medialane: REST API
          if (!MEDIALANE_API_KEY) throw new Error("MEDIALANE_API_KEY not configured")
          const mlRes = await fetch("https://api.medialane.io/v1/orders", {
            method: "POST",
            headers: { "x-api-key": MEDIALANE_API_KEY, "Content-Type": "application/json" },
            body: JSON.stringify({ ...body, maker: wallet.address }),
          })
          const result = await mlRes.json()
          jsonResponse(res, 200, result)
          return
        }
      } catch (err) {
        jsonResponse(res, 500, { error: String(err) })
      }
      return
    }

    // POST /v1/starknet/venues/:venue/fulfill
    const fulfillMatch = base.match(/^\/v1\/starknet\/venues\/([^/]+)\/fulfill$/)
    if (req.method === "POST" && fulfillMatch) {
      const wallet = requireWalletSignature(req)
      if (!wallet) {
        jsonResponse(res, 401, { error: "Wallet signature required" })
        return
      }
      const body = await parseBody(req).catch(() => null)
      if (!body) {
        jsonResponse(res, 400, { error: "Invalid request body" })
        return
      }
      const venue = fulfillMatch[1]

      try {
        if (venue === "ark") {
          // Ark fulfillment is browser-side (wallet account required).
          // Return parameters so the browser client can build the transaction.
          const bodyTyped = body as { listingId?: string; amount?: string; quantity?: string }
          if (!bodyTyped.listingId) {
            jsonResponse(res, 400, { error: "listingId is required" })
            return
          }
          jsonResponse(res, 200, {
            venue: "ark",
            action: "FULFILL_LISTING",
            taker: wallet.address,
            listingId: bodyTyped.listingId,
            amount: bodyTyped.amount,
            quantity: bodyTyped.quantity,
            instructions: "Use ArkAdapter.fulfillListing() in the browser with the wallet Account.",
          })
        } else if (venue === "medialane") {
          if (!MEDIALANE_API_KEY) throw new Error("MEDIALANE_API_KEY not configured")
          const mlRes = await fetch("https://api.medialane.io/v1/orders/fulfill", {
            method: "POST",
            headers: { "x-api-key": MEDIALANE_API_KEY, "Content-Type": "application/json" },
            body: JSON.stringify({ ...body, taker: wallet.address }),
          })
          const result = await mlRes.json()
          jsonResponse(res, 200, result)
          return
        } else {
          jsonResponse(res, 400, { error: `Unknown venue: ${venue}` })
          return
        }
      } catch (err) {
        jsonResponse(res, 500, { error: String(err) })
      }
      return
    }

    // POST /v1/starknet/venues/:venue/cancel
    const cancelMatch = base.match(/^\/v1\/starknet\/venues\/([^/]+)\/cancel$/)
    if (req.method === "POST" && cancelMatch) {
      const wallet = requireWalletSignature(req)
      if (!wallet) {
        jsonResponse(res, 401, { error: "Wallet signature required" })
        return
      }
      const body = await parseBody(req).catch(() => null)
      if (!body) {
        jsonResponse(res, 400, { error: "Invalid request body" })
        return
      }
      const venue = cancelMatch[1]

      try {
        if (venue === "ark") {
          // Ark cancellation is browser-side (wallet account required).
          // Return parameters so the browser client can build the transaction.
          const bodyTyped = body as { listingId?: string }
          if (!bodyTyped.listingId) {
            jsonResponse(res, 400, { error: "listingId is required" })
            return
          }
          jsonResponse(res, 200, {
            venue: "ark",
            action: "CANCEL_LISTING",
            maker: wallet.address,
            listingId: bodyTyped.listingId,
            instructions: "Use ArkAdapter.cancelListing() in the browser with the wallet Account.",
          })
        } else if (venue === "medialane") {
          if (!MEDIALANE_API_KEY) throw new Error("MEDIALANE_API_KEY not configured")
          const mlRes = await fetch("https://api.medialane.io/v1/orders/cancel", {
            method: "POST",
            headers: { "x-api-key": MEDIALANE_API_KEY, "Content-Type": "application/json" },
            body: JSON.stringify({ ...body, maker: wallet.address }),
          })
          const result = await mlRes.json()
          jsonResponse(res, 200, result)
          return
        } else {
          jsonResponse(res, 400, { error: `Unknown venue: ${venue}` })
          return
        }
      } catch (err) {
        jsonResponse(res, 500, { error: String(err) })
      }
      return
    }

    // 404
    jsonResponse(res, 404, { error: "Not found" })
  } catch (err) {
    console.error("Server error:", err)
    jsonResponse(res, 500, { error: "Internal server error" })
  }
}

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------

const server = createServer(handleRequest)
server.listen(PORT, () => {
  console.log(`Reference server running on port ${PORT}`)
  console.log(`  STARKNET_RPC=${STARKNET_RPC ? "(configured)" : "(not set)"}`)
  console.log(`  MEDIALANE_API_KEY=${MEDIALANE_API_KEY ? "(set)" : "(not set)"}`)
})
