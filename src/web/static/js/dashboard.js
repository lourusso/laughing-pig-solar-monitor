let powerChart = null;
let socChart = null;

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
    document.getElementById("solar-power").textContent = `${totalPv} W`;
    document.getElementById("solar-breakdown").textContent = `DC: ${dcPv}W | AC: ${acPv}W`;

    // Battery Storage
    const soc = Math.round(data.battery_soc ?? 0);
    const rawVolts = data.battery_volts ?? data.battery_voltage ?? 0;
    const batVolts = Number(rawVolts).toFixed(1);
    const batWatts = Math.round(data.battery_power_watts ?? 0);
    let rawAmps = data.battery_amps ?? data.battery_current;
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
    
    if (batWatts > 10) {
      // Charging: Green
      batSub.textContent = `Charging (${batWatts} W)`;
      batSub.style.color = "#22c55e";
      batDetails.style.color = "#22c55e";
      batSoc.style.color = "#22c55e";
    } else if (batWatts < -10) {
      // Discharging: Red
      batSub.textContent = `Discharging (${Math.abs(batWatts)} W)`;
      batSub.style.color = "#ef4444";
      batDetails.style.color = "#ef4444";
      batSoc.style.color = "#ef4444";
    } else {
      // Idle: Default/Gray
      batSub.textContent = "Idle";
      batSub.style.color = "#94a3b8";
      batDetails.style.color = "var(--text-main)";
      batSoc.style.color = "var(--battery-color)";
    }

    // Household Loads
    const loadWatts = Math.round(data.load_power_watts || 0);
    document.getElementById("load-power").textContent = `${loadWatts} W`;
    document.getElementById("load-sub").textContent = `${(data.ac_voltage_volts || 120).toFixed(1)}V @ ${(data.ac_frequency_hz || 60).toFixed(2)}Hz`;

    // MidNite Classic #1 Details
    const c1Power = Math.round(data.classic1_power_watts ?? (data.pv_dc_power_watts || 0));
    const c1Stage = data.classic1_stage || data.charge_stage || "RESTING";
    const c1PvV = Number(data.classic1_volts ?? (data.pv_dc_volts || 0)).toFixed(1);
    const c1BatV = Number(data.classic1_bat_volts ?? (data.classic_bat_volts || 0)).toFixed(1);
    const c1Daily = Number(data.classic1_daily_kwh ?? (data.pv_dc_daily_kwh || 0)).toFixed(2);

    const c1StageEl = document.getElementById("classic1-stage");
    if (c1StageEl) c1StageEl.textContent = c1Stage;
    const c1PowerEl = document.getElementById("classic1-power");
    if (c1PowerEl) c1PowerEl.textContent = `${c1Power} W`;
    const c1PvEl = document.getElementById("classic1-pv-v");
    if (c1PvEl) c1PvEl.textContent = `${c1PvV} V`;
    const c1BatEl = document.getElementById("classic1-bat-v");
    if (c1BatEl) c1BatEl.textContent = `${c1BatV} V`;
    const c1DailyEl = document.getElementById("classic1-daily");
    if (c1DailyEl) c1DailyEl.textContent = `${c1Daily} kWh`;

    // MidNite Classic #2 Details (192.168.42.130)
    const c2Online = Boolean(data.classic2_online);
    const c2StageEl = document.getElementById("classic2-stage");
    const c2PowerEl = document.getElementById("classic2-power");
    const c2PvEl = document.getElementById("classic2-pv-v");
    const c2BatEl = document.getElementById("classic2-bat-v");
    const c2DailyEl = document.getElementById("classic2-daily");

    if (c2Online) {
      const c2Power = Math.round(data.classic2_power_watts || 0);
      if (c2StageEl) {
        c2StageEl.textContent = data.classic2_stage || "RESTING";
        c2StageEl.style.backgroundColor = "var(--border-color)";
        c2StageEl.style.color = "var(--text-main)";
      }
      if (c2PowerEl) c2PowerEl.textContent = `${c2Power} W`;
      if (c2PvEl) c2PvEl.textContent = `${Number(data.classic2_volts || 0).toFixed(1)} V`;
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
      if (c2BatEl) c2BatEl.textContent = "-- V";
      if (c2DailyEl) c2DailyEl.textContent = "0.00 kWh";
    }

    // Sunny Boy Details
    document.getElementById("sunnyboy-power").textContent = `${acPv} W`;
    document.getElementById("sunnyboy-total").textContent = `${(data.pv_ac_total_kwh || 0).toFixed(1)} kWh`;

    // Hardware Status Pills
    const pClassic1 = document.getElementById("pill-classic");
    const c1Online = data.classic1_online ?? data.classic_online;
    if (pClassic1) {
      if (c1Online) {
        pClassic1.classList.add("online");
        pClassic1.querySelector("span:last-child").textContent = "Classic #1: Online";
      } else {
        pClassic1.classList.remove("online");
        pClassic1.querySelector("span:last-child").textContent = "Classic #1: Offline";
      }
    }

    const pClassic2 = document.getElementById("pill-classic2");
    if (pClassic2) {
      if (c2Online) {
        pClassic2.classList.add("online");
        pClassic2.querySelector("span:last-child").textContent = "Classic #2: Online";
      } else {
        pClassic2.classList.remove("online");
        pClassic2.querySelector("span:last-child").textContent = "Classic #2: Offline";
      }
    }

    const pWebbox = document.getElementById("pill-webbox");
    if (pWebbox) {
      if (data.webbox_online) {
        pWebbox.classList.add("online");
        pWebbox.querySelector("span:last-child").textContent = "WebBox: Online";
      } else {
        pWebbox.classList.remove("online");
        pWebbox.querySelector("span:last-child").textContent = "WebBox: Offline";
      }
    }

  } catch (err) {
    console.error("Failed to fetch live telemetry:", err);
  }
}

async function loadHistoryCharts() {
  try {
    const res = await fetch("/api/history?hours=24");
    if (!res.ok) return;
    const history = await res.json();
    if (!history || history.length === 0) return;

    const labels = history.map(h => {
      const d = new Date(h.timestamp);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    });

    const solarData = history.map(h => Math.round(h.total_pv_power_watts || 0));
    const loadData = history.map(h => Math.round(h.load_power_watts || 0));
    const batteryData = history.map(h => Math.round(h.battery_power_watts || 0));
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
            label: "Solar Generation (W)",
            data: solarData,
            borderColor: "#f59e0b",
            backgroundColor: "rgba(245, 158, 11, 0.1)",
            fill: true,
            tension: 0.3,
            borderWidth: 2,
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
loadHistoryCharts();

// Polling intervals
setInterval(fetchLiveTelemetry, 3000);
setInterval(loadHistoryCharts, 60000);
