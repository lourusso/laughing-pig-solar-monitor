# Laughing Pig Solar Monitor — Future Enhancements & Roadmap

This file tracks planned upcoming features so we can pick up right where we left off.

---

## 1. Combined Solar PV Generation Detail Page (Click-Through from Solar PV Card)
**Goal**: Update the **Solar PV Generation** flow node on the main dashboard (`index.html`) so clicking it displays a unified view of **all three solar generation sources** instead of only MidNite Classic #1:
- **MidNite Solar Classic #1** (`192.168.42.129` — DC PV Charge Controller)
- **MidNite Solar Classic #2** (`192.168.42.130` — DC PV Charge Controller)
- **SMA Sunny Boy 4000** (`WR40U08E:2000702586` via WebBox — Shop AC-Coupled PV Inverter)

**Planned Implementation Steps**:
1. Add a combined `/api/device/solar-pv` (or `/device/solar-pv`) handler in `src/main.py` (`get_device_telemetry`) that returns:
   - Total combined PV power (`total_pv_power_watts`), total DC power (`pv_dc_power_watts`), and total AC power (`pv_ac_power_watts`).
   - Full side-by-side telemetry for **Classic #1**, **Classic #2**, and **Sunny Boy 4000** (power, PV voltage/current, charge stage/mode, daily & lifetime kWh yield, and temperatures in `°F`).
2. Add a rich multi-device renderer in `src/web/static/js/device.js` for `/device/solar-pv` that displays all three solar devices on one page with quick links to each individual device's raw register/channel table.
3. Update the Solar PV flow card in `src/web/templates/index.html` (`onclick="window.location.href='/device/solar-pv'"`).

---

## 2. Public Mobile Power Flow Page (Cloudflare Publishing)
**Goal**: Publish a read-only, public-facing webpage that displays **only the Mobile Power Flow view** (the 4-node animated Power Flow card) without exposing internal `192.168.42.x` IP addresses, `/device/*` diagnostic pages, `/api/history`, or `/api/export`.

**Two Cloudflare Options Discussed**:
- **Method A: Cloudflare Worker ("Push-to-Cloud")** *(100% Free, No Domain or Extra NAS Container Needed)*
  - Host a single `cloudflare_worker.js` on Cloudflare Workers (`*.workers.dev` or custom domain).
  - Have the Solar Monitor push a sanitized ~250-byte JSON payload outbound every 10 seconds using a `PUSH_SECRET` header.
  - Zero inbound traffic to the farm network; handles thousands of concurrent viewers on Cloudflare's edge.
- **Method B: Cloudflare Tunnel (`cloudflared`)** *(Custom Domain, Unlimited 3-Second Live Updates)*
  - Run a locked-down Public Kiosk route/port (`8051`) in the Solar Monitor that serves only the Mobile Power Flow HTML (with click-throughs disabled) and `/api/public/live`.
  - Expose port `8051` via a `cloudflared` container on the NAS to a custom Cloudflare domain (e.g., `solar.yourdomain.com`).
