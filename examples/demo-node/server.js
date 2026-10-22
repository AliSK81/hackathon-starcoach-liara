// Demo shop for StarCoach. Plain Node, no dependencies.
// It needs SHOP_DB_URL. Without it, every page fails with HTTP 500, like a real app
// whose database setting is missing. LEAK_MB makes each request keep that much memory.
const http = require("http");

const PORT = Number(process.env.PORT || 3000);
const DB_URL = process.env.SHOP_DB_URL || "";
const LEAK_MB = Number(process.env.LEAK_MB || 0);
const leaked = [];

const products = [
  { name: "Persian tea", price: 120000 },
  { name: "Saffron 1g", price: 350000 },
  { name: "Pistachio 500g", price: 980000 },
];

function connectDb() {
  if (!DB_URL) {
    const err = new Error("connect ECONNREFUSED 127.0.0.1:5432");
    err.code = "ECONNREFUSED";
    throw err;
  }
  return products;
}

const server = http.createServer((req, res) => {
  const started = Date.now();
  if (LEAK_MB > 0) leaked.push(Buffer.alloc(LEAK_MB * 1024 * 1024, 1));
  if (req.url === "/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ ok: true }));
    return;
  }
  try {
    const items = connectDb();
    const rows = items.map((p) => `<li>${p.name} — ${p.price.toLocaleString()} Toman</li>`).join("");
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    res.end(`<!doctype html><meta charset="utf-8"><title>Demo shop</title><h1>Demo shop</h1><ul>${rows}</ul>`);
    console.log(`${req.method} ${req.url} 200 ${Date.now() - started}ms`);
  } catch (err) {
    console.error(`${req.method} ${req.url} 500 ${Date.now() - started}ms`);
    console.error(err.stack);
    res.writeHead(500, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("500 Internal Server Error");
  }
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`demo shop listening on 0.0.0.0:${PORT}`);
  if (!DB_URL) console.error("SHOP_DB_URL is not set; using default 127.0.0.1:5432");
});
