let powerChart = null;
let socChart = null;

// Backwards-compatible nullish coalescing helper (equivalent to a ?? b)
function coalesce(val, fallback) {
  return (val !== undefined && val !== null) ? val : fallback;
}

// Update power flow connector animation, speed, and directional indicator
function updateFlowConnector(connId, streamId, arrowId, watts, direction, streamColorClass) {
  const conn = document.getElementById(connId);
  const stream = document.getElementById(streamId);
  const arrow = document.getElementById(arrowId);
  if (!conn || !stream) return;

  if (watts < 15 || direction === 0) {
    conn.className = conn.className.replace(/\bflow-dir-\S+/g, "").trim() + " flow-dir-idle";
    stream.className = "flow-stream " + streamColorClass + " flow-idle";
    if (arrow) {
      arrow.className = "flow-direction-indicator idle";
    }
    return;
  }

  // Calculate animation speed based on power wattage
  var speed = 1.4;
  if (watts > 2500) speed = 0.65;
  else if (watts > 1200) speed = 0.85;
  else if (watts > 400) speed = 1.1;

  stream.style.setProperty("--flow-speed", speed + "s");

  if (direction > 0) {
    conn.className = conn.className.replace(/\bflow-dir-\S+/g, "").trim() + " flow-dir-fwd";
    stream.className = "flow-stream " + streamColorClass + " flow-fwd";
    if (arrow) {
      arrow.className = "flow-direction-indicator active";
    }
  } else {
    conn.className = conn.className.replace(/\bflow-dir-\S+/g, "").trim() + " flow-dir-rev";
    stream.className = "flow-stream " + streamColorClass + " flow-rev";
    if (arrow) {
      arrow.className = "flow-direction-indicator active";
    }
  }
}

async function fetchLiveTelemetry() {
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

    const solarPowerEl = document.getElementById("solar-power");
    if (solarPowerEl) solarPowerEl.textContent = `${totalPv} W`;
    const solarBreakdownEl = document.getElementById("solar-breakdown");
    if (solarBreakdownEl) {
      if (data.classic2_online || data.classic1_online) {
        solarBreakdownEl.textContent = `DC: ${dcPv}W (C1: ${c1PowerVal}W · C2: ${c2PowerVal}W) | AC: ${acPv}W`;
      } else {
        solarBreakdownEl.textContent = `DC: ${dcPv}W | AC: ${acPv}W`;
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
    
    const batSoc = document.getElementById("battery-soc");
    const batVa = document.getElementById("battery-va");
    const batDetails = document.getElementById("battery-details");
    const batSub = document.getElementById("battery-sub");
    
    if (batSoc) batSoc.textContent = `${soc}%`;
    if (batVa) {
      batVa.textContent = `${batVolts} V | ${signAmps} A`;
    }
    const batVoltsEl = document.getElementById("battery-volts");
    if (batVoltsEl) batVoltsEl.textContent = `${batVolts} V`;
    if (batDetails) batDetails.textContent = `${batWatts > 0 ? "+" : ""}${batWatts} W (${signAmps} A)`;
    
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
          batSub.textContent = `Charging from Gen & Solar (${batWatts} W)`;
        } else if (genWatts > 50) {
          batSub.textContent = `Charging from Generator (${batWatts} W)`;
        } else if (totalPv > 50) {
          batSub.textContent = `Charging from Solar (${batWatts} W)`;
        } else {
          batSub.textContent = `Charging (${batWatts} W)`;
        }
        batSub.style.color = "#22c55e";
      }
      if (batDetails) batDetails.style.color = "#22c55e";
      if (batSoc) batSoc.style.color = "#22c55e";
    } else if (batWatts < -10) {
      // Discharging: Red
      if (batSub) {
        batSub.textContent = `Discharging (${Math.abs(batWatts)} W)`;
        batSub.style.color = "#ef4444";
      }
      if (batDetails) batDetails.style.color = "#ef4444";
      if (batSoc) batSoc.style.color = "#ef4444";
    } else {
      // Idle: Default/Gray
      if (batSub) {
        batSub.textContent = "Idle";
        batSub.style.color = "#94a3b8";
      }
      if (batDetails) batDetails.style.color = "var(--text-main)";
      if (batSoc) batSoc.style.color = "var(--battery-color)";
    }

    // --- Option 2: Discover Battery Rich Card Telemetry ---
    // 1. Visual SOC Bar Gauge (fill width & dynamic color)
    const batGaugeFill = document.getElementById("bat-gauge-fill");
    if (batGaugeFill) {
      const clampedSoc = Math.max(3, Math.min(100, soc));
      batGaugeFill.style.width = `${clampedSoc}%`;
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
    const batPill = document.getElementById("battery-pill");
    const batPillText = document.getElementById("battery-pill-text");
    if (batPill && batPillText) {
      if (batWatts > 10) {
        batPill.className = "flow-status-pill pill-charge";
        batPillText.textContent = `CHARGING +${batWatts} W`;
      } else if (batWatts < -10) {
        batPill.className = "flow-status-pill pill-discharge";
        batPillText.textContent = `DISCHARGING ${Math.abs(batWatts)} W`;
      } else {
        batPill.className = "flow-status-pill pill-idle";
        batPillText.textContent = "IDLE / STANDBY";
      }
    }

    // 3. Battery Telemetry Triad (Voltage, Net Current, Cell Temperature)
    const batVoltsVal = document.getElementById("bat-volts-val");
    if (batVoltsVal) batVoltsVal.textContent = `${batVolts} V`;

    const batAmpsVal = document.getElementById("bat-amps-val");
    if (batAmpsVal) {
      batAmpsVal.textContent = `${signAmps} A`;
      if (numAmps > 0.1) {
        batAmpsVal.style.color = "#22c55e";
      } else if (numAmps < -0.1) {
        batAmpsVal.style.color = "#ef4444";
      } else {
        batAmpsVal.style.color = "#f1f5f9";
      }
    }

    const batTempVal = document.getElementById("bat-temp-val");
    if (batTempVal) {
      if (data.battery_temp_c !== undefined && data.battery_temp_c !== null) {
        batTempVal.textContent = `${Number(data.battery_temp_c).toFixed(1)} °C`;
      } else {
        batTempVal.textContent = "-- °C";
      }
    }

    // 4. Battery System Link Footer (Closed loop status and SOH)
    const batSohText = document.getElementById("bat-soh-text");
    if (batSohText) {
      if (data.battery_soh !== undefined && data.battery_soh !== null) {
        batSohText.textContent = `LYNK II CAN · SOH ${Math.round(data.battery_soh)}%`;
      } else {
        batSohText.textContent = "LYNK II CAN Closed-Loop";
      }
    }

    // Household Loads
    const loadWatts = Math.round(data.load_power_watts || 0);
    const loadPowerEl = document.getElementById("load-power");
    if (loadPowerEl) loadPowerEl.textContent = `${loadWatts} W`;
    const loadSubEl = document.getElementById("load-sub");
    if (loadSubEl) loadSubEl.textContent = `${(data.ac_voltage_volts || 120).toFixed(1)}V @ ${(data.ac_frequency_hz || 60).toFixed(2)}Hz`;

    // --- Option 2: Household Loads Rich Card Telemetry ---
    // 1. Inverter Capacity Meter (Relative to 6000W continuous rating of SI 6048)
    const loadGaugeFill = document.getElementById("load-gauge-fill");
    const loadCapacityPct = Math.round((loadWatts / 6000) * 100);
    if (loadGaugeFill) {
      const clampedLoadPct = Math.max(3, Math.min(100, loadCapacityPct));
      loadGaugeFill.style.width = `${clampedLoadPct}%`;
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

    // 2. Household Load Status Pill
    const loadPill = document.getElementById("load-pill");
    const loadPillText = document.getElementById("load-pill-text");
    if (loadPill && loadPillText) {
      if (loadWatts > 4500) {
        loadPill.className = "flow-status-pill pill-discharge";
        loadPillText.textContent = `HEAVY DRAW · ${loadCapacityPct}% CAP`;
      } else if (loadWatts > 1800) {
        loadPill.className = "flow-status-pill pill-amber";
        loadPillText.textContent = `MODERATE DRAW · ${loadCapacityPct}% CAP`;
      } else if (loadWatts > 50) {
        loadPill.className = "flow-status-pill pill-load";
        loadPillText.textContent = `LIGHT DRAW · ${loadCapacityPct}% CAP`;
      } else {
        loadPill.className = "flow-status-pill pill-idle";
        loadPillText.textContent = "MINIMAL DRAW";
      }
    }

    // 3. Load Telemetry Triad (AC Volts, Frequency, AC Current)
    const acVoltsNum = Number(coalesce(data.ac_voltage_volts, 120));
    const acFreqNum = Number(coalesce(data.ac_frequency_hz, 60));
    const loadVoltsVal = document.getElementById("load-volts-val");
    if (loadVoltsVal) loadVoltsVal.textContent = `${acVoltsNum.toFixed(1)} V`;

    const loadFreqVal = document.getElementById("load-freq-val");
    if (loadFreqVal) loadFreqVal.textContent = `${acFreqNum.toFixed(2)} Hz`;

    const loadAmpsVal = document.getElementById("load-amps-val");
    if (loadAmpsVal) {
      const loadAmps = acVoltsNum > 0 ? (loadWatts / acVoltsNum).toFixed(1) : "0.0";
      loadAmpsVal.textContent = `${loadAmps} A`;
    }

    const loadFooterText = document.getElementById("load-footer-text");
    if (loadFooterText) {
      if (data.load_source === "eGauge S1" || data.egauge_online) {
        loadFooterText.textContent = "eGauge EG3010 · CT S1 (120V)";
      } else {
        loadFooterText.textContent = "SMA Sunny Island 6048-US";
      }
    }

    // Generator Flow Node
    const genPowerEl = document.getElementById("gen-power");
    if (genPowerEl) genPowerEl.textContent = `${genWatts} W`;
    const genSubEl = document.getElementById("gen-sub");
    if (genSubEl) {
      if (genWatts > 25) {
        genSubEl.textContent = `${genVolts}V · ${genAmps}A @ ${genFreq}Hz · Running`;
        genSubEl.style.color = "var(--gen-color, #06b6d4)";
      } else {
        genSubEl.textContent = "SI6048 Gen Input (Standby)";
        genSubEl.style.color = "#94a3b8";
      }
    }

    // Dynamic Power Flow Connectors (Directional & Proportional Speed)
    // 1. Solar PV Flow -> Battery / System
    updateFlowConnector("conn-solar", "stream-solar", "arrow-solar", totalPv, totalPv > 15 ? 1 : 0, "solar-stream");

    // 2. Generator Flow -> Battery / System
    updateFlowConnector("conn-gen", "stream-gen", "arrow-gen", genWatts, genWatts > 25 ? 1 : 0, "gen-stream");

    // 3. System / Battery Flow -> Household Loads
    updateFlowConnector("conn-load", "stream-load", "arrow-load", loadWatts, loadWatts > 15 ? 1 : 0, "load-stream");

    // Generator Card in Metrics Grid (if visible)
    const genCardPowerEl = document.getElementById("gen-card-power");
    if (genCardPowerEl) genCardPowerEl.textContent = `${genWatts} W`;
    const genCardVaEl = document.getElementById("gen-card-va");
    if (genCardVaEl) genCardVaEl.textContent = `${genVolts} V (${genAmps} A)`;
    const genCardStatusEl = document.getElementById("gen-card-status");
    if (genCardStatusEl) genCardStatusEl.textContent = genWatts > 25 ? "Running / Supplying" : "Standby";
    const genCardBadgeEl = document.getElementById("gen-card-badge");
    if (genCardBadgeEl) {
      if (genWatts > 25) {
        genCardBadgeEl.textContent = "ACTIVE";
        genCardBadgeEl.style.backgroundColor = "rgba(6, 182, 212, 0.15)";
        genCardBadgeEl.style.color = "var(--gen-color, #06b6d4)";
      } else {
        genCardBadgeEl.textContent = "STANDBY";
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

    const c1StageEl = document.getElementById("classic1-stage");
    if (c1StageEl) c1StageEl.textContent = c1Stage;
    const c1PowerEl = document.getElementById("classic1-power");
    if (c1PowerEl) c1PowerEl.textContent = `${c1Power} W`;
    const c1PvEl = document.getElementById("classic1-pv-v");
    if (c1PvEl) c1PvEl.textContent = `${c1PvV} V`;
    const c1PvAEl = document.getElementById("classic1-pv-a");
    if (c1PvAEl) c1PvAEl.textContent = `(${c1PvA} A)`;
    const c1BatEl = document.getElementById("classic1-bat-v");
    if (c1BatEl) c1BatEl.textContent = `${c1BatV} V`;
    const c1DailyEl = document.getElementById("classic1-daily");
    if (c1DailyEl) c1DailyEl.textContent = `${c1Daily} kWh`;

    // MidNite Classic #2 Details (192.168.42.130)
    const c2Online = Boolean(data.classic2_online);
    const c2StageEl = document.getElementById("classic2-stage");
    const c2PowerEl = document.getElementById("classic2-power");
    const c2PvEl = document.getElementById("classic2-pv-v");
    const c2PvAEl = document.getElementById("classic2-pv-a");
    const c2BatEl = document.getElementById("classic2-bat-v");
    const c2DailyEl = document.getElementById("classic2-daily");

    if (c2Online) {
      const c2Power = Math.round(data.classic2_power_watts || 0);
      const c2PvA = Number(data.classic2_amps || 0).toFixed(1);
      if (c2StageEl) {
        c2StageEl.textContent = data.classic2_stage || "RESTING";
        c2StageEl.style.backgroundColor = "";
        c2StageEl.style.color = "";
      }
      if (c2PowerEl) c2PowerEl.textContent = `${c2Power} W`;
      if (c2PvEl) c2PvEl.textContent = `${Number(data.classic2_volts || 0).toFixed(1)} V`;
      if (c2PvAEl) c2PvAEl.textContent = `(${c2PvA} A)`;
      if (c2BatEl) c2BatEl.textContent = `${Number(data.classic2_bat_volts || 0).toFixed(1)} V`;
      if (c2DailyEl) c2DailyEl.textContent = `${Number(data.classic2_daily_kwh || 0).toFixed(2)} kWh`;
    } else {
      if (c2StageEl) {
        c2StageEl.textContent = "OFFLINE";
        c2StageEl.style.backgroundColor = "rgba(239, 68, 68, 0.15)";
        c2StageEl.style.color = "#ef4444";
      }
      if (c2PowerEl) c2PowerEl.textContent = "0 W";
      if (c2PvEl) c2PvEl.textContent = "-- V";
      if (c2PvAEl) c2PvAEl.textContent = "(-- A)";
      if (c2BatEl) c2BatEl.textContent = "-- V";
      if (c2DailyEl) c2DailyEl.textContent = "0.00 kWh";
    }

    // Sunny Boy Details
    const sbPowerEl = document.getElementById("sunnyboy-power");
    if (sbPowerEl) sbPowerEl.textContent = `${acPv} W`;
    const sbTotalEl = document.getElementById("sunnyboy-total");
    if (sbTotalEl) sbTotalEl.textContent = `${(data.pv_ac_total_kwh || 0).toFixed(1)} kWh`;

    // Hardware Status Pills
    const pClassic1 = document.getElementById("pill-classic");
    const c1Online = coalesce(data.classic1_online, data.classic_online);
    if (pClassic1) {
      const lbl = pClassic1.querySelector("span:last-child");
      if (c1Online) {
        pClassic1.classList.add("online");
        if (lbl) lbl.textContent = "Classic #1: Online";
      } else {
        pClassic1.classList.remove("online");
        if (lbl) lbl.textContent = "Classic #1: Offline";
      }
    }

    const pClassic2 = document.getElementById("pill-classic2");
    if (pClassic2) {
      const lbl2 = pClassic2.querySelector("span:last-child");
      if (c2Online) {
        pClassic2.classList.add("online");
        if (lbl2) lbl2.textContent = "Classic #2: Online";
      } else {
        pClassic2.classList.remove("online");
        if (lbl2) lbl2.textContent = "Classic #2: Offline";
      }
    }

    const pWebbox = document.getElementById("pill-webbox");
    if (pWebbox) {
      const lblW = pWebbox.querySelector("span:last-child");
      if (data.webbox_online) {
        pWebbox.classList.add("online");
        if (lblW) lblW.textContent = "WebBox: Online";
      } else {
        pWebbox.classList.remove("online");
        if (lblW) lblW.textContent = "WebBox: Offline";
      }
    }

    const pSunnyBoy = document.getElementById("pill-sunnyboy");
    const sbOnline = Boolean(coalesce(data.sunnyboy_online, (data.pv_ac_power_watts > 0 || (data.webbox_online && data.pv_ac_total_kwh > 0))));
    if (pSunnyBoy) {
      const lblSB = pSunnyBoy.querySelector("span:last-child");
      if (sbOnline) {
        pSunnyBoy.classList.add("online");
        if (lblSB) lblSB.textContent = "SB4000: Online";
      } else {
        pSunnyBoy.classList.remove("online");
        if (lblSB) lblSB.textContent = "SB4000: Offline";
      }
    }

    const pEgauge = document.getElementById("pill-egauge");
    if (pEgauge) {
      const lblEg = pEgauge.querySelector("span:last-child");
      if (data.egauge_online) {
        pEgauge.classList.add("online");
        if (lblEg) lblEg.textContent = "eGauge: Online";
      } else {
        pEgauge.classList.remove("online");
        if (lblEg) lblEg.textContent = "eGauge: Offline";
      }
    }

    const pGen = document.getElementById("pill-gen");
    if (pGen) {
      const lblGen = pGen.querySelector("span:last-child");
      if (genWatts > 25) {
        pGen.classList.add("online");
        if (lblGen) lblGen.textContent = `Gen: ${genWatts} W`;
      } else {
        pGen.classList.remove("online");
        if (lblGen) lblGen.textContent = "Gen: Standby";
      }
    }

  } catch (err) {
    console.error("Failed to fetch live telemetry:", err);
  }
}

async function loadHistoryCharts() {
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

    // Power Chart
    const ctxPower = document.getElementById("powerChart").getContext("2d");
    if (powerChart) {
      powerChart.destroy();
    }
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
            label: "Household Load (W)",
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

    // SoC Chart
    const ctxSoc = document.getElementById("socChart").getContext("2d");
    if (socChart) {
      socChart.destroy();
    }
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
