import { DurableObject } from "cloudflare:workers";

const siteOrigin = "https://pknu-leejihoon.github.io";
const expiresAfter = 75_000;
const maxParticipants = 500;
const zones = /^(venue|north|south|hall-(?:[1-9]|1[0-8]|20))$/;
const deviceName = /^(iPhone|iPad|Android|Mobile|Computer)-[0-9A-F]{4}$/;
const sessionToken = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

export class VenueRoom extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.sql = ctx.storage.sql;
    this.sql.exec("CREATE TABLE IF NOT EXISTS presence (token TEXT PRIMARY KEY, device TEXT NOT NULL, zone TEXT NOT NULL, expires INTEGER NOT NULL)");
    this.sql.exec("CREATE INDEX IF NOT EXISTS presence_expiry ON presence (expires)");
  }

  async update(token, device, zone) {
    if (!sessionToken.test(token) || !deviceName.test(device)) return null;
    const now = Date.now();
    this.sql.exec("DELETE FROM presence WHERE expires <= ?", now);
    if (zone === "") {
      this.sql.exec("DELETE FROM presence WHERE token = ?", token);
      return [];
    }
    if (!zones.test(zone)) return null;
    if (this.sql.exec("SELECT count(*) AS n FROM presence").one().n >= maxParticipants
        && !this.sql.exec("SELECT 1 FROM presence WHERE token = ?", token).toArray().length) return null;
    this.sql.exec("INSERT OR REPLACE INTO presence (token, device, zone, expires) VALUES (?, ?, ?, ?)",
      token, device, zone, now + expiresAfter);
    if (await this.ctx.storage.getAlarm() === null) await this.ctx.storage.setAlarm(now + expiresAfter);
    return this.sql.exec("SELECT device, zone, expires FROM presence WHERE token <> ? ORDER BY zone, device", token).toArray();
  }

  async alarm() {
    this.sql.exec("DELETE FROM presence WHERE expires <= ?", Date.now());
    const next = this.sql.exec("SELECT min(expires) AS next FROM presence").one().next;
    if (next !== null) await this.ctx.storage.setAlarm(next);
  }
}

export default {
  async fetch(request, env) {
    if (request.headers.get("Origin") !== siteOrigin || new URL(request.url).pathname !== "/presence") {
      return new Response(null, { status: 404 });
    }
    const headers = {
      "Access-Control-Allow-Origin": siteOrigin,
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Cache-Control": "no-store",
      "Vary": "Origin"
    };
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers });
    if (request.method !== "POST") return new Response(null, { status: 405, headers });
    const { success } = await env.REQUESTS.limit({ key: request.headers.get("CF-Connecting-IP") || "unknown" });
    if (!success) return new Response(null, { status: 429, headers });
    const length = Number(request.headers.get("Content-Length"));
    if (!Number.isInteger(length) || length <= 0 || length > 256) return new Response(null, { status: 400, headers });
    const body = await request.json().catch(() => null);
    if (!body || typeof body.token !== "string" || typeof body.device !== "string" || typeof body.zone !== "string") {
      return new Response(null, { status: 400, headers });
    }
    const people = await env.ROOM.getByName("chtf2026").update(body.token, body.device, body.zone);
    return people === null ? new Response(null, { status: 400, headers }) : Response.json({ people }, { headers });
  }
};
