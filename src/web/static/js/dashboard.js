let powerChart = null;
let socChart = null;

// ==============================================================================
// Dashboard JavaScript: Bringing the Solar Farm to Life on Screen!
// ==============================================================================
// This code is like an artist painting a moving picture:
// Every 3 seconds, it checks the farm sensors, updates all the dials and cards,
// and animates glowing rivers of electricity flowing between the sun, batteries,
// and farm buildings!
// ==============================================================================

// Backwards-compatible nullish coalescing helper (equivalent to a ?? b).
// Keeps older iPads and Safari browsers from crashing if a value is missing!
function coalesce(val, fallback) {
  return (val !== undefined && val !== null) ? val : fallback;
}

// Fast DOM Element Memory (Cache):
// Instead of searching the whole web page for 45 different boxes every 3 seconds,
// we remember where each box lives in `domCache` and only repaint a box if its text
// or color actually changed!
var domCache = {};
function getEl(id) {
  if (domCache[id] === undefined) {
    domCache[id] = document.getElementById(id);
  }
  return domCache[id];
}

function setText(el, text) {
  if (el && el.textContent !== text) {
    el.textContent = text;
  }
}

function setClass(el, cls) {
  if (el && el.className !== cls) {
    el.className = cls;
  }
}

// ------------------------------------------------------------------------------
// Glowing River Animator (Power Flow Connectors)
// ------------------------------------------------------------------------------
// Think of the power lines on the dashboard like magical glowing rivers!
// - If no electricity is moving (less than 15 Watts), the river goes to sleep (idle).
// - The more Watts of electricity flowing, the faster the glowing river rushes!
//   * Over 2,500 Watts: Rushing rapids (super fast!)
//   * 1,200 to 2,500 Watts: Fast river
//   * 400 to 1,200 Watts: Brisk jog
//   * Under 400 Watts: Gentle stroll
// - Direction arrows show which way the power is moving:
//   * Forward: Sunshine filling the battery, or power lighting up the house!
//   * Reverse: Energy flowing backwards into the grid or charger.
// ------------------------------------------------------------------------------
function updateFlowConnector(connId, streamId, arrowId, watts, direction, streamColorClass) {
  const conn = getEl(connId);
  const stream = getEl(streamId);
  const arrow = getEl(arrowId);
  if (!conn || !stream) return;

  if (watts < 15 || direction === 0) {
    const idleConnCls = conn.className.replace(/\bflow-dir-\S+/g, "").trim() + " flow-dir-idle";
    setClass(conn, idleConnCls);
    setClass(stream, "flow-stream " + streamColorClass + " flow-idle");
    if (arrow) {
      setClass(arrow, "flow-direction-indicator idle");
    }
    return;
  }

  // Calculate animation speed based on power wattage
  var speed = 1.4;
  if (watts > 2500) speed = 0.65;
  else if (watts > 1200) speed = 0.85;
  else if (watts > 400) speed = 1.1;

  const speedStr = speed + "s";
  if (stream.getAttribute("data-speed") !== speedStr) {
    stream.style.setProperty("--flow-speed", speedStr);
    stream.setAttribute("data-speed", speedStr);
  }

  if (direction > 0) {
    const fwdConnCls = conn.className.replace(/\bflow-dir-\S+/g, "").trim() + " flow-dir-fwd";
    setClass(conn, fwdConnCls);
    setClass(stream, "flow-stream " + streamColorClass + " flow-fwd");
    if (arrow) {
      setClass(arrow, "flow-direction-indicator active");
    }
  } else {
    const revConnCls = conn.className.replace(/\bflow-dir-\S+/g, "").trim() + " flow-dir-rev";
    setClass(conn, revConnCls);
    setClass(stream, "flow-stream " + streamColorClass + " flow-rev");
    if (arrow) {
      setClass(arrow, "flow-direction-indicator active");
    }
  }
}

// ------------------------------------------------------------------------------
// Fetch Live Telemetry: Checking in with the Farm Conductor!
// ------------------------------------------------------------------------------
// Every 3 seconds, this function rings up the server at "/api/live" and asks:
// "What are the latest solar numbers right now?"
// Then it updates every number and card on the dashboard!
// ------------------------------------------------------------------------------
async function fetchLiveTelemetry() {
  if (document.hidden) return;
  try {
    const res = await fetch("/api/live");
    if (!res.ok) return;
    const data = await res.json();
    if (!data || Object.keys(data).length === 0) return;

    // Solar PV Generation
    const totalPv = Math.round(data.total_pv_power_watts || 0);
    const dcPv = Math.round(data.pv_dc_power_watts || 0);
    const acPv = Math.round(data.pv_ac_power_watts || 0);
    const c1PowerVal = Math.round(coalesce(data.classic1_power_watts, data.pv_dc_power_watts || 0));
    const c2PowerVal = Math.round(data.classic2_power_watts || 0);

    setText(getEl("solar-power"), `${totalPv} W`);
    const solarBreakdownEl = getEl("solar-breakdown");
    if (solarBreakdownEl) {
      if (data.classic2_online || data.classic1_online) {
        setText(solarBreakdownEl, `DC: ${dcPv}W (C1: ${c1PowerVal}W · C2: ${c2PowerVal}W) | AC: ${acPv}W`);
      } else {
        setText(solarBreakdownEl, `DC: ${dcPv}W | AC: ${acPv}W`);
      }
    }

    // Battery Storage
    const soc = Math.round(coalesce(data.battery_soc, 0));
    const rawVolts = coalesce(data.battery_volts, coalesce(data.battery_voltage, 0));
    const batVolts = Number(rawVolts).toFixed(1);
    const batWatts = Math.round(coalesce(data.battery_power_watts, 0));
    let rawAmps = coalesce(data.battery_amps, data.battery_current);
    if ((rawAmps === undefined || rawAmps === null || rawAmps === 0) && batWatts !== 0 && Number(rawVolts) > 0) {
      rawAmps = batWatts / Number(rawVolts);
    }
    const numAmps = Number(rawAmps || 0);
    const signAmps = (numAmps > 0 ? "+" : "") + numAmps.toFixed(1);
    
    const batSoc = getEl("battery-soc");
    const batVa = getEl("battery-va");
    const batDetails = getEl("battery-details");
    const batSub = getEl("battery-sub");
    
    setText(batSoc, `${soc}%`);
    setText(batVa, `${batVolts} V | ${signAmps} A`);
    setText(getEl("battery-volts"), `${batVolts} V`);
    setText(batDetails, `${batWatts > 0 ? "+" : ""}${batWatts} W (${signAmps} A)`);
    
    // Generator Telemetry
    const genWatts = Math.round(coalesce(data.grid_gen_power_watts, 0));
    const genVolts = Number(coalesce(data.generator_volts, coalesce(data.ac_voltage_volts, 120))).toFixed(1);
    var rawGenAmps = coalesce(data.generator_amps, (genWatts > 0 ? (genWatts / Number(genVolts)) : 0));
    const genAmps = Number(rawGenAmps || 0).toFixed(1);
    const genFreq = Number(coalesce(data.generator_frequency, coalesce(data.ac_frequency_hz, 60))).toFixed(1);

    if (batWatts > 10) {
      // Charging: Green
      if (batSub) {
        if (genWatts > 50 && totalPv > 50) {
          setText(batSub, `Charging from Gen & Solar (${batWatts} W)`);
        } else if (genWatts > 50) {
          setText(batSub, `Charging from Generator (${batWatts} W)`);
        } else if (totalPv > 50) {
          setText(batSub, `Charging from Solar (${batWatts} W)`);
        } else {
          setText(batSub, `Charging (${batWatts} W)`);
        }
        batSub.style.color = "#22c55e";
      }
      if (batDetails) batDetails.style.color = "#22c55e";
      if (batSoc) batSoc.style.color = "#22c55e";
    } else if (batWatts < -10) {
      // Discharging: Red
      if (batSub) {
        setText(batSub, `Discharging (${Math.abs(batWatts)} W)`);
        batSub.style.color = "#ef4444";
      }
      if (batDetails) batDetails.style.color = "#ef4444";
      if (batSoc) batSoc.style.color = "#ef4444";
    } else {
      // Idle: Default/Gray
      if (batSub) {
        setText(batSub, "Idle");
        batSub.style.color = "#94a3b8";
      }
      if (batDetails) batDetails.style.color = "var(--text-main)";
      if (batSoc) batSoc.style.color = "var(--battery-color)";
    }

    // --- Option 2: Discover Battery Rich Card Telemetry ---
    // 1. Visual SOC Bar Gauge (fill width & dynamic color)
    const batGaugeFill = getEl("bat-gauge-fill");
    if (batGaugeFill) {
      const clampedSoc = Math.max(3, Math.min(100, soc));
      const newWidth = `${clampedSoc}%`;
      if (batGaugeFill.style.width !== newWidth) batGaugeFill.style.width = newWidth;
      if (soc > 40) {
        batGaugeFill.style.background = "linear-gradient(90deg, #16a34a, #22c55e)";
        batGaugeFill.style.boxShadow = "0 0 10px rgba(34, 197, 94, 0.4)";
      } else if (soc > 20) {
        batGaugeFill.style.background = "linear-gradient(90deg, #d97706, #f59e0b)";
        batGaugeFill.style.boxShadow = "0 0 10px rgba(245, 158, 11, 0.4)";
      } else {
        batGaugeFill.style.background = "linear-gradient(90deg, #dc2626, #ef4444)";
        batGaugeFill.style.boxShadow = "0 0 10px rgba(239, 68, 68, 0.4)";
      }
    }

    // 2. Battery Flow Pill
    const batPill = getEl("battery-pill");
    const batPillText = getEl("battery-pill-text");
    if (batPill && batPillText) {
      if (batWatts > 10) {
        setClass(batPill, "flow-status-pill pill-charge");
        setText(batPillText, `CHARGING +${batWatts} W`);
      } else if (batWatts < -10) {
        setClass(batPill, "flow-status-pill pill-discharge");
        setText(batPillText, `DISCHARGING ${Math.abs(batWatts)} W`);
      } else {
        setClass(batPill, "flow-status-pill pill-idle");
        setText(batPillText, "IDLE / STANDBY");
      }
    }

    // 3. Battery Telemetry Triad (Voltage, Net Current, Cell Temperature)
    setText(getEl("bat-volts-val"), `${batVolts} V`);

    const batAmpsVal = getEl("bat-amps-val");
    if (batAmpsVal) {
      setText(batAmpsVal, `${signAmps} A`);
      if (numAmps > 0.1) {
        batAmpsVal.style.color = "#22c55e";
      } else if (numAmps < -0.1) {
        batAmpsVal.style.color = "#ef4444";
      } else {
        batAmpsVal.style.color = "#f1f5f9";
      }
    }

    const batTempVal = getEl("bat-temp-val");
    if (batTempVal) {
      if (data.battery_temp_f !== undefined && data.battery_temp_f !== null) {
        setText(batTempVal, `${Number(data.battery_temp_f).toFixed(1)} °F`);
      } else if (data.battery_temp_c !== undefined && data.battery_temp_c !== null) {
        const tempF = Number(data.battery_temp_c) * 1.8 + 32.0;
        setText(batTempVal, `${tempF.toFixed(1)} °F`);
      } else {
        setText(batTempVal, "-- °F");
      }
    }

    // 4. Battery System Link Footer (Closed loop status and SOH)
    const batSohText = getEl("bat-soh-text");
    if (batSohText) {
      if (data.battery_soh !== undefined && data.battery_soh !== null) {
        setText(batSohText, `LYNK II CAN · SOH ${Math.round(data.battery_soh)}%`);
      } else {
        setText(batSohText, "LYNK II CAN Closed-Loop");
      }
    }

    // Farm Loads (Formula: ((SB4000 Pac) - S3) + S1)
    const loadWatts = Math.round(data.load_power_watts || 0);
    setText(getEl("load-power"), `${loadWatts} W`);
    setText(getEl("load-sub"), `${(data.ac_voltage_volts || 120).toFixed(1)}V @ ${(data.ac_frequency_hz || 60).toFixed(2)}Hz`);

    // --- Option 2: Farm Loads Rich Card Telemetry ---
    // 1. Inverter Capacity Meter (Relative to 6000W continuous rating of SI 6048)
    const loadGaugeFill = getEl("load-gauge-fill");
    const loadCapacityPct = Math.round((loadWatts / 6000) * 100);
    if (loadGaugeFill) {
      const clampedLoadPct = Math.max(3, Math.min(100, loadCapacityPct));
      const newLoadWidth = `${clampedLoadPct}%`;
      if (loadGaugeFill.style.width !== newLoadWidth) loadGaugeFill.style.width = newLoadWidth;
      if (loadCapacityPct > 80) {
        loadGaugeFill.style.background = "linear-gradient(90deg, #dc2626, #ef4444)";
        loadGaugeFill.style.boxShadow = "0 0 10px rgba(239, 68, 68, 0.4)";
      } else if (loadCapacityPct > 50) {
        loadGaugeFill.style.background = "linear-gradient(90deg, #d97706, #f59e0b)";
        loadGaugeFill.style.boxShadow = "0 0 10px rgba(245, 158, 11, 0.4)";
      } else {
        loadGaugeFill.style.background = "linear-gradient(90deg, #0284c7, #38bdf8)";
        loadGaugeFill.style.boxShadow = "0 0 10px rgba(56, 189, 248, 0.4)";
      }
    }

    // 2. Farm Load Status Pill
    const loadPill = getEl("load-pill");
    const loadPillText = getEl("load-pill-text");
    if (loadPill && loadPillText) {
      if (loadWatts > 4500) {
        setClass(loadPill, "flow-status-pill pill-discharge");
        setText(loadPillText, `HEAVY DRAW · ${loadCapacityPct}% CAP`);
      } else if (loadWatts > 1800) {
        setClass(loadPill, "flow-status-pill pill-amber");
        setText(loadPillText, `MODERATE DRAW · ${loadCapacityPct}% CAP`);
      } else if (loadWatts > 50) {
        setClass(loadPill, "flow-status-pill pill-load");
        setText(loadPillText, `LIGHT DRAW · ${loadCapacityPct}% CAP`);
      } else {
        setClass(loadPill, "flow-status-pill pill-idle");
        setText(loadPillText, "MINIMAL DRAW");
      }
    }

    // 3. Load Telemetry Triad (AC Volts, Frequency, AC Current)
    const acVoltsNum = Number(coalesce(data.ac_voltage_volts, 120));
    const acFreqNum = Number(coalesce(data.ac_frequency_hz, 60));
    setText(getEl("load-volts-val"), `${acVoltsNum.toFixed(1)} V`);
    setText(getEl("load-freq-val"), `${acFreqNum.toFixed(2)} Hz`);

    const loadAmpsVal = getEl("load-amps-val");
    if (loadAmpsVal) {
      const loadAmps = acVoltsNum > 0 ? (loadWatts / acVoltsNum).toFixed(1) : "0.0";
      setText(loadAmpsVal, `${loadAmps} A`);
    }

    const loadFooterText = getEl("load-footer-text");
    if (loadFooterText) {
      if (data.load_source === "eGauge Farm Load") {
        setText(loadFooterText, "eGauge EG3010 · S1 House + Shop");
      } else if (data.load_source === "eGauge S1") {
        setText(loadFooterText, "eGauge EG3010 · CT S1 (120V)");
      } else if (data.egauge_online) {
        setText(loadFooterText, "eGauge EG3010 · S1 House + Shop");
      } else {
        setText(loadFooterText, "SMA Sunny Island 6048-US");
      }
    }

    // Generator Flow Node
    setText(getEl("gen-power"), `${genWatts} W`);
    const genSubEl = getEl("gen-sub");
    if (genSubEl) {
      if (genWatts > 25) {
        setText(genSubEl, `${genVolts}V · ${genAmps}A @ ${genFreq}Hz · Running`);
        genSubEl.style.color = "var(--gen-color, #06b6d4)";
      } else {
        setText(genSubEl, "SI6048 Gen Input (Standby)");
        genSubEl.style.color = "#94a3b8";
      }
    }

    // Dynamic Power Flow Connectors (Directional & Proportional Speed)
    // 1. Solar PV Flow -> Battery / System
    updateFlowConnector("conn-solar", "stream-solar", "arrow-solar", totalPv, totalPv > 15 ? 1 : 0, "solar-stream");

    // 2. Generator Flow -> Battery / System
    updateFlowConnector("conn-gen", "stream-gen", "arrow-gen", genWatts, genWatts > 25 ? 1 : 0, "gen-stream");

    // 3. System / Battery Flow -> Farm Loads
    updateFlowConnector("conn-load", "stream-load", "arrow-load", loadWatts, loadWatts > 15 ? 1 : 0, "load-stream");

    // Generator Card in Metrics Grid (if visible)
    setText(getEl("gen-card-power"), `${genWatts} W`);
    setText(getEl("gen-card-va"), `${genVolts} V (${genAmps} A)`);
    setText(getEl("gen-card-status"), genWatts > 25 ? "Running / Supplying" : "Standby");
    const genCardBadgeEl = getEl("gen-card-badge");
    if (genCardBadgeEl) {
      if (genWatts > 25) {
        setText(genCardBadgeEl, "ACTIVE");
        genCardBadgeEl.style.backgroundColor = "rgba(6, 182, 212, 0.15)";
        genCardBadgeEl.style.color = "var(--gen-color, #06b6d4)";
      } else {
        setText(genCardBadgeEl, "STANDBY");
        genCardBadgeEl.style.backgroundColor = "";
        genCardBadgeEl.style.color = "";
      }
    }

    // MidNite Classic #1 Details
    const c1Power = Math.round(coalesce(data.classic1_power_watts, data.pv_dc_power_watts || 0));
    const c1Stage = data.classic1_stage || data.charge_stage || "RESTING";
    const c1PvV = Number(coalesce(data.classic1_volts, data.pv_dc_volts || 0)).toFixed(1);
    const c1PvA = Number(data.classic1_amps || 0).toFixed(1);
    const c1BatV = Number(coalesce(data.classic1_bat_volts, data.classic_bat_volts || 0)).toFixed(1);
    const c1Daily = Number(coalesce(data.classic1_daily_kwh, data.pv_dc_daily_kwh || 0)).toFixed(2);

    setText(getEl("classic1-stage"), c1Stage);
    setText(getEl("classic1-power"), `${c1Power} W`);
    setText(getEl("classic1-pv-v"), `${c1PvV} V`);
    setText(getEl("classic1-pv-a"), `(${c1PvA} A)`);
    setText(getEl("classic1-bat-v"), `${c1BatV} V`);
    setText(getEl("classic1-daily"), `${c1Daily} kWh`);

    // MidNite Classic #2 Details (192.168.42.130)
    const c2Online = Boolean(data.classic2_online);
    const c2StageEl = getEl("classic2-stage");
    const c2PowerEl = getEl("classic2-power");
    const c2PvEl = getEl("classic2-pv-v");
    const c2PvAEl = getEl("classic2-pv-a");
    const c2BatEl = getEl("classic2-bat-v");
    const c2DailyEl = getEl("classic2-daily");

    if (c2Online) {
      const c2Power = Math.round(data.classic2_power_watts || 0);
      const c2PvA = Number(data.classic2_amps || 0).toFixed(1);
      if (c2StageEl) {
        setText(c2StageEl, data.classic2_stage || "RESTING");
        c2StageEl.style.backgroundColor = "";
        c2StageEl.style.color = "";
      }
      setText(c2PowerEl, `${c2Power} W`);
      setText(c2PvEl, `${Number(data.classic2_volts || 0).toFixed(1)} V`);
      setText(c2PvAEl, `(${c2PvA} A)`);
      setText(c2BatEl, `${Number(data.classic2_bat_volts || 0).toFixed(1)} V`);
      setText(c2DailyEl, `${Number(data.classic2_daily_kwh || 0).toFixed(2)} kWh`);
    } else {
      if (c2StageEl) {
        setText(c2StageEl, "OFFLINE");
        c2StageEl.style.backgroundColor = "rgba(239, 68, 68, 0.15)";
        c2StageEl.style.color = "#ef4444";
      }
      setText(c2PowerEl, "0 W");
      setText(c2PvEl, "-- V");
      setText(c2PvAEl, "(-- A)");
      setText(c2BatEl, "-- V");
      setText(c2DailyEl, "0.00 kWh");
    }

    // Sunny Boy Details
    setText(getEl("sunnyboy-power"), `${acPv} W`);
    setText(getEl("sunnyboy-total"), `${(data.pv_ac_total_kwh || 0).toFixed(1)} kWh`);

    // Hardware Status Pills (with cached child label lookup)
    function updateStatusPill(id, isOnline, onlineLabel, offlineLabel) {
      const pill = getEl(id);
      if (!pill) return;
      if (!pill._lbl) pill._lbl = pill.querySelector("span:last-child");
      if (isOnline) {
        if (!pill.classList.contains("online")) pill.classList.add("online");
        setText(pill._lbl, onlineLabel);
      } else {
        if (pill.classList.contains("online")) pill.classList.remove("online");
        setText(pill._lbl, offlineLabel);
      }
    }

    const c1Online = coalesce(data.classic1_online, data.classic_online);
    updateStatusPill("pill-classic", c1Online, "Classic #1: Online", "Classic #1: Offline");
    updateStatusPill("pill-classic2", c2Online, "Classic #2: Online", "Classic #2: Offline");
    updateStatusPill("pill-webbox", data.webbox_online, "WebBox: Online", "WebBox: Offline");

    const sbOnline = Boolean(coalesce(data.sunnyboy_online, (data.pv_ac_power_watts > 0 || (data.webbox_online && data.pv_ac_total_kwh > 0))));
    updateStatusPill("pill-sunnyboy", sbOnline, "SB4000: Online", "SB4000: Offline");
    updateStatusPill("pill-egauge", data.egauge_online, "eGauge: Online", "eGauge: Offline");
    updateStatusPill("pill-gen", genWatts > 25, `Gen: ${genWatts} W`, "Gen: Standby");

  } catch (err) {
    console.error("Failed to fetch live telemetry:", err);
  }
}

async function loadHistoryCharts() {
  if (document.hidden) return;
  try {
    if (typeof Chart === "undefined") {
      return;
    }
    const res = await fetch("/api/history?hours=24");
    if (!res.ok) return;
    const history = await res.json();
    if (!history || history.length === 0) return;

    const labels = history.map(h => {
      const d = new Date(h.timestamp);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    });

    const solarData = history.map(h => Math.round(h.total_pv_power_watts || 0));
    const c1Data = history.map(h => Math.round(h.classic1_power_watts || 0));
    const c2Data = history.map(h => Math.round(h.classic2_power_watts || 0));
    const loadData = history.map(h => Math.round(h.load_power_watts || 0));
    const batteryData = history.map(h => Math.round(h.battery_power_watts || 0));
    const genData = history.map(h => Math.round(coalesce(h.grid_gen_power_watts, 0)));
    const socData = history.map(h => Math.round(h.battery_soc || 0));

    // Power Chart: Update in-place if already created instead of tearing down the canvas!
    if (powerChart) {
      powerChart.data.labels = labels;
      powerChart.data.datasets[0].data = solarData;
      powerChart.data.datasets[1].data = c1Data;
      powerChart.data.datasets[2].data = c2Data;
      powerChart.data.datasets[3].data = loadData;
      powerChart.data.datasets[4].data = batteryData;
      powerChart.data.datasets[5].data = genData;
      powerChart.update("none");
    } else {
      const ctxPower = getEl("powerChart").getContext("2d");
      powerChart = new Chart(ctxPower, {
        type: "line",
        data: {
          labels: labels,
          datasets: [
            {
              label: "Solar Total (W)",
              data: solarData,
              borderColor: "#f59e0b",
              backgroundColor: "rgba(245, 158, 11, 0.08)",
              fill: true,
              tension: 0.3,
              borderWidth: 2,
              pointRadius: 0
            },
            {
              label: "Classic #1 (W)",
              data: c1Data,
              borderColor: "#eab308",
              borderDash: [3, 3],
              backgroundColor: "transparent",
              borderWidth: 1.5,
              tension: 0.3,
              pointRadius: 0
            },
            {
              label: "Classic #2 (W)",
              data: c2Data,
              borderColor: "#fb923c",
              borderDash: [3, 3],
              backgroundColor: "transparent",
              borderWidth: 1.5,
              tension: 0.3,
              pointRadius: 0
            },
            {
              label: "Farm Load (W)",
              data: loadData,
              borderColor: "#38bdf8",
              backgroundColor: "transparent",
              borderWidth: 2,
              tension: 0.3,
              pointRadius: 0
            },
            {
              label: "Battery Power (W)",
              data: batteryData,
              borderColor: "#10b981",
              backgroundColor: "transparent",
              borderWidth: 1.5,
              borderDash: [4, 4],
              tension: 0.3,
              pointRadius: 0
            },
            {
              label: "Generator (W)",
              data: genData,
              borderColor: "#06b6d4",
              backgroundColor: "rgba(6, 182, 212, 0.08)",
              fill: false,
              tension: 0.3,
              borderWidth: 1.5,
              pointRadius: 0
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          plugins: {
            legend: { labels: { color: "#94a3b8" } }
          },
          scales: {
            x: {
              grid: { color: "#1e293b" },
              ticks: { color: "#64748b", maxTicksLimit: 12 }
            },
            y: {
              grid: { color: "#1e293b" },
              ticks: { color: "#64748b" }
            }
          }
        }
      });
    }

    // SoC Chart: Update in-place if already created!
    if (socChart) {
      socChart.data.labels = labels;
      socChart.data.datasets[0].data = socData;
      socChart.update("none");
    } else {
      const ctxSoc = getEl("socChart").getContext("2d");
      socChart = new Chart(ctxSoc, {
        type: "line",
        data: {
          labels: labels,
          datasets: [
            {
              label: "Battery SoC %",
              data: socData,
              borderColor: "#10b981",
              backgroundColor: "rgba(16, 185, 129, 0.15)",
              fill: true,
              tension: 0.2,
              borderWidth: 2,
              pointRadius: 0
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          plugins: {
            legend: { labels: { color: "#94a3b8" } }
          },
          scales: {
            x: {
              grid: { color: "#1e293b" },
              ticks: { color: "#64748b", maxTicksLimit: 8 }
            },
            y: {
              min: 0,
              max: 100,
              grid: { color: "#1e293b" },
              ticks: { color: "#64748b" }
            }
          }
        }
      });
    }

  } catch (err) {
    console.error("Failed to load historical charts:", err);
  }
}

// Initial calls
fetchLiveTelemetry();
setInterval(fetchLiveTelemetry, 3000);

// Only load and poll historical charts on non-touch devices (desktop)
const isTouchDevice = window.matchMedia("(pointer: coarse), (hover: none)").matches;
if (!isTouchDevice) {
  loadHistoryCharts();
  setInterval(loadHistoryCharts, 60000);
}

// Wake up immediately when the user switches back to this browser tab!
document.addEventListener("visibilitychange", function () {
  if (!document.hidden) {
    fetchLiveTelemetry();
    if (!isTouchDevice) {
      loadHistoryCharts();
    }
  }
});
