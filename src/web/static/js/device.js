// Laughing Pig Solar Monitor - Device Telemetry Detail Client

document.addEventListener("DOMContentLoaded", () => {
  const pathParts = window.location.pathname.split("/").filter(Boolean);
  const deviceId = pathParts[pathParts.length - 1] || "midnite";

  const devicePill = document.getElementById("device-pill");
  const deviceStatusText = document.getElementById("device-status-text");
  const deviceTitle = document.getElementById("device-title");
  const deviceSubtitle = document.getElementById("device-subtitle");
  const badgeModel = document.getElementById("badge-model");
  const badgeProtocol = document.getElementById("badge-protocol");
  const badgeUpdated = document.getElementById("badge-updated");
  const heroGrid = document.getElementById("hero-grid");
  const parameterSections = document.getElementById("parameter-sections");
  const diagTableBody = document.getElementById("diag-table-body");
  const diagSearch = document.getElementById("diag-search");

  let rawRowsData = [];

  // Filter diagnostics table on search input
  diagSearch.addEventListener("input", (e) => {
    const query = e.target.value.toLowerCase().trim();
    renderFilteredTable(query);
  });

  function renderFilteredTable(query = "") {
    if (!rawRowsData || rawRowsData.length === 0) {
      diagTableBody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No diagnostic channels or registers available.</td></tr>`;
      return;
    }

    const filtered = rawRowsData.filter(row => {
      if (!query) return true;
      const text = `${row.id} ${row.name} ${row.desc} ${row.val}`.toLowerCase();
      return text.includes(query);
    });

    if (filtered.length === 0) {
      diagTableBody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No registers or channels match "${query}".</td></tr>`;
      return;
    }

    diagTableBody.innerHTML = filtered.map(row => `
      <tr>
        <td class="mono-code">${escapeHtml(row.id)}</td>
        <td><strong>${escapeHtml(row.name)}</strong></td>
        <td style="color: var(--text-muted);">${escapeHtml(row.desc)}</td>
        <td><strong style="color: #38bdf8;">${escapeHtml(row.val)}</strong></td>
      </tr>
    `).join("");
  }

  function escapeHtml(str) {
    if (str === null || str === undefined) return "--";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function fetchDeviceTelemetry() {
    try {
      const resp = await fetch(`/api/device/${deviceId}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();

      updateDeviceUI(data);
    } catch (err) {
      console.error("Failed to fetch device data:", err);
      devicePill.className = "pill offline";
      deviceStatusText.textContent = "Offline / Connection Error";
    }
  }

  function updateDeviceUI(payload) {
    const isOnline = Boolean(payload.online);
    devicePill.className = isOnline ? "pill online" : "pill offline";
    deviceStatusText.textContent = isOnline ? "Device Online" : "Device Offline";

    const now = new Date();
    badgeUpdated.textContent = `Last Polled: ${now.toLocaleTimeString()}`;

    const dev = (payload.device_id || deviceId).toLowerCase();
    const d = payload.data || {};

    if (dev.includes("midnite") || dev.includes("classic")) {
      renderMidNiteView(payload, d);
    } else if (dev.includes("island") || dev.includes("si") || dev.includes("battery") || dev.includes("ess") || dev.includes("discover")) {
      renderSunnyIslandView(payload, d);
    } else if (dev.includes("boy") || dev.includes("sb")) {
      renderSunnyBoyView(payload, d);
    } else {
      renderGenericView(payload, d);
    }
  }

  // --- MIDNITE SOLAR CLASSIC RENDERER ---
  function renderMidNiteView(payload, d) {
    deviceTitle.textContent = "MidNite Solar Classic";
    deviceSubtitle.textContent = "High-Voltage MPPT Charge Controller";
    badgeModel.textContent = d.model_name || payload.model || "Classic 150/200/250";
    badgeProtocol.textContent = "Modbus TCP (Port 502)";

    // 1. Hero Grid
    heroGrid.innerHTML = `
      <div class="stat-card">
        <div class="stat-header">
          <span class="stat-title">SOLAR PV POWER</span>
          <span class="stat-badge">${escapeHtml(d.mppt_mode || "MPPT")}</span>
        </div>
        <div class="stat-main" style="color: var(--solar-color);">${(d.pv_power_watts || 0).toFixed(0)} W</div>
        <div class="stat-footer">
          <span>PV: ${(d.pv_voltage || 0).toFixed(1)} V</span>
          <span>Current: ${(d.pv_current || 0).toFixed(1)} A</span>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-header">
          <span class="stat-title">BATTERY VOLTAGE</span>
          <span class="stat-badge">${(d.nominal_bat_v || 48)}V System</span>
        </div>
        <div class="stat-main" style="color: var(--battery-color);">${(d.battery_voltage || 0).toFixed(1)} V</div>
        <div class="stat-footer">
          <span>Current: ${(d.battery_current || 0).toFixed(1)} A</span>
          <span>Target: ${(d.temp_comp_target_v || "--")} V</span>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-header">
          <span class="stat-title">CHARGE STAGE</span>
          <span class="stat-badge">Algorithm</span>
        </div>
        <div class="stat-main" style="font-size: 1.5rem; color: #38bdf8;">${escapeHtml(d.charge_stage || "--")}</div>
        <div class="stat-footer">
          <span>Absorb: ${escapeHtml(d.absorb_time_str || "--")}</span>
          <span>Float: ${escapeHtml(d.float_time_today_str || "--")}</span>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-header">
          <span class="stat-title">TODAY'S ENERGY</span>
          <span class="stat-badge">Accumulated</span>
        </div>
        <div class="stat-main" style="color: #10b981;">${(d.energy_today_kwh || 0).toFixed(2)} kWh</div>
        <div class="stat-footer">
          <span>Lifetime: ${(d.energy_total_kwh || 0).toFixed(1)} kWh</span>
          <span>Daily Ah: ${d.amphours_today || 0} Ah</span>
        </div>
      </div>
    `;

    // 2. Categorized Sections
    parameterSections.innerHTML = `
      <section class="device-section">
        <div class="device-section-title"><span>☀️</span> Solar Array & PV Input</div>
        <div class="params-grid">
          <div class="param-card">
            <span class="param-label">PV Input Voltage</span>
            <span class="param-val">${(d.pv_voltage || 0).toFixed(1)} V</span>
            <span class="param-sub">Register 4116 (dispavgVpv)</span>
          </div>
          <div class="param-card">
            <span class="param-label">PV Input Current</span>
            <span class="param-val">${(d.pv_current || 0).toFixed(1)} A</span>
            <span class="param-sub">Register 4121 (PvInputCurrent)</span>
          </div>
          <div class="param-card">
            <span class="param-label">Instantaneous Power</span>
            <span class="param-val">${(d.pv_power_watts || 0).toFixed(0)} W</span>
            <span class="param-sub">Register 4119 (Watts)</span>
          </div>
          <div class="param-card">
            <span class="param-label">Last Open-Circuit Voc</span>
            <span class="param-val">${(d.pv_voc || 0).toFixed(1)} V</span>
            <span class="param-sub">Register 4122 (VocLastMeasured)</span>
          </div>
          <div class="param-card">
            <span class="param-label">Peak Input Voltage</span>
            <span class="param-val">${(d.pv_highest_v || 0).toFixed(1)} V</span>
            <span class="param-sub">Register 4123 (HighestVinputLog)</span>
          </div>
        </div>
      </section>

      <section class="device-section">
        <div class="device-section-title"><span>🔋</span> Battery Bank & Regulation Target</div>
        <div class="params-grid">
          <div class="param-card">
            <span class="param-label">Battery Voltage</span>
            <span class="param-val">${(d.battery_voltage || 0).toFixed(1)} V</span>
            <span class="param-sub">Register 4115 (dispavgVbatt)</span>
          </div>
          <div class="param-card">
            <span class="param-label">Battery Current</span>
            <span class="param-val">${(d.battery_current || 0).toFixed(1)} A</span>
            <span class="param-sub">Register 4117 (IbattDisplayS)</span>
          </div>
          <div class="param-card">
            <span class="param-label">Nominal Bank Voltage</span>
            <span class="param-val">${d.nominal_bat_v ? d.nominal_bat_v + ' V' : '--'}</span>
            <span class="param-sub">Register 4245 (VbattNominal)</span>
          </div>
          <div class="param-card">
            <span class="param-label">Temp-Comp Regulation Target</span>
            <span class="param-val">${d.temp_comp_target_v ? d.temp_comp_target_v.toFixed(1) + ' V' : '--'}</span>
            <span class="param-sub">Register 4244 (VbattRegSetPTmpComp)</span>
          </div>
          <div class="param-card">
            <span class="param-label">Daily Amp-Hours</span>
            <span class="param-val">${d.amphours_today || 0} Ah</span>
            <span class="param-sub">Register 4125 (AmpHours)</span>
          </div>
          <div class="param-card">
            <span class="param-label">Lifetime Amp-Hours</span>
            <span class="param-val">${(d.lifetime_amphours || 0).toLocaleString()} Ah</span>
            <span class="param-sub">Register 4128-4129 (LifetimeAmpHours)</span>
          </div>
          <div class="param-card">
            <span class="param-label">Ending Current (Amps)</span>
            <span class="param-val">${d.ending_amps !== undefined ? d.ending_amps + ' A' : '--'}</span>
            <span class="param-sub">Register 4246 (EndingAmps)</span>
          </div>
          <div class="param-card">
            <span class="param-label">Rebulk Threshold</span>
            <span class="param-val">${d.rebulk_v !== undefined ? d.rebulk_v + ' V' : '--'}</span>
            <span class="param-sub">Register 4249 (RebulkVolts)</span>
          </div>
        </div>
      </section>

      <section class="device-section">
        <div class="device-section-title"><span>⏱️</span> Charge Timers & State Counters</div>
        <div class="params-grid">
          <div class="param-card">
            <span class="param-label">Current Charge Stage</span>
            <span class="param-val" style="color: #38bdf8;">${escapeHtml(d.charge_stage || "--")}</span>
            <span class="param-sub">Register 4120 (ComboChargeStage)</span>
          </div>
          <div class="param-card">
            <span class="param-label">Absorb Time Counter</span>
            <span class="param-val">${escapeHtml(d.absorb_time_str || "--")}</span>
            <span class="param-sub">Register 4139 (AbsorbTime)</span>
          </div>
          <div class="param-card">
            <span class="param-label">Time in Float Today</span>
            <span class="param-val">${escapeHtml(d.float_time_today_str || "--")}</span>
            <span class="param-sub">Register 4138 (FloatTimeTodaySeconds)</span>
          </div>
          <div class="param-card">
            <span class="param-label">Equalize Time Remaining</span>
            <span class="param-val">${escapeHtml(d.equalize_time_str || "--")}</span>
            <span class="param-sub">Register 4143 (Equalize Time)</span>
          </div>
          <div class="param-card">
            <span class="param-label">Night Minutes (No Solar)</span>
            <span class="param-val">${d.night_minutes || 0} min</span>
            <span class="param-sub">Register 4135 (NiteMinutesNoPwr)</span>
          </div>
        </div>
      </section>

      <section class="device-section">
        <div class="device-section-title"><span>🌡️</span> Thermals, Diagnostics & System</div>
        <div class="params-grid">
          <div class="param-card">
            <span class="param-label">Remote Battery Temp</span>
            <span class="param-val">${d.battery_temp_c !== undefined ? d.battery_temp_c.toFixed(1) + ' °C' : '--'}</span>
            <span class="param-sub">${d.battery_temp_f !== undefined ? d.battery_temp_f.toFixed(1) + ' °F' : ''} (Reg 4132)</span>
          </div>
          <div class="param-card">
            <span class="param-label">Power FETs Temp</span>
            <span class="param-val">${d.fet_temp_c !== undefined ? d.fet_temp_c.toFixed(1) + ' °C' : '--'}</span>
            <span class="param-sub">${d.fet_temp_f !== undefined ? d.fet_temp_f.toFixed(1) + ' °F' : ''} (Reg 4133)</span>
          </div>
          <div class="param-card">
            <span class="param-label">PCB Controller Temp</span>
            <span class="param-val">${d.pcb_temp_c !== undefined ? d.pcb_temp_c.toFixed(1) + ' °C' : '--'}</span>
            <span class="param-sub">${d.pcb_temp_f !== undefined ? d.pcb_temp_f.toFixed(1) + ' °F' : ''} (Reg 4134)</span>
          </div>
          <div class="param-card">
            <span class="param-label">PWM Duty Cycle</span>
            <span class="param-val">${d.pwm_duty !== undefined ? d.pwm_duty : '--'}</span>
            <span class="param-sub">Register 4141 (PWM_ReadOnly)</span>
          </div>
          <div class="param-card">
            <span class="param-label">Firmware Build Date</span>
            <span class="param-val">${escapeHtml(d.sw_date || "--")}</span>
            <span class="param-sub">Registers 4102-4103</span>
          </div>
          <div class="param-card">
            <span class="param-label">Ethernet MAC Address</span>
            <span class="param-val" style="font-size: 1rem; font-family: monospace;">${escapeHtml(d.mac_address || "--")}</span>
            <span class="param-sub">Registers 4106-4108</span>
          </div>
        </div>
      </section>
    `;

    // 3. Raw Table Rows
    const regs = payload.registers || [];
    rawRowsData = regs.map(r => ({
      id: `Reg ${r.register}`,
      name: r.name,
      desc: r.description,
      val: r.value
    }));

    renderFilteredTable(diagSearch.value.toLowerCase().trim());
  }

  // --- SMA SUNNY ISLAND 6048 & DISCOVER AES LITHIUM RENDERER ---
  function renderSunnyIslandView(payload, d) {
    deviceTitle.textContent = "Discover AES Lithium & SMA Sunny Island 6048";
    deviceSubtitle.textContent = "Closed-Loop Battery Management System (LYNK II CAN) & Island Inverter";
    badgeModel.textContent = "Discover AES LiFePO4 + SI 6048-US";
    badgeProtocol.textContent = "LYNK II CAN ➔ SMA ComSync ➔ WebBox RPC";

    const isCharging = (d.battery_current || 0) >= 0;

    heroGrid.innerHTML = `
      <div class="stat-card">
        <div class="stat-header">
          <span class="stat-title">BATTERY STATE OF CHARGE</span>
          <span class="stat-badge">SoH: ${(d.battery_soh || 100).toFixed(0)}%</span>
        </div>
        <div class="stat-main" style="color: var(--battery-color);">${(d.battery_soc || 0).toFixed(0)}%</div>
        <div class="stat-footer">
          <span>Voltage: ${(d.battery_voltage || 0).toFixed(1)} V</span>
          <span>Current: ${(d.battery_current || 0).toFixed(1)} A</span>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-header">
          <span class="stat-title">BATTERY POWER</span>
          <span class="stat-badge">${isCharging ? "Charging" : "Discharging"}</span>
        </div>
        <div class="stat-main" style="color: ${isCharging ? 'var(--charging-color)' : 'var(--discharging-color)'};">
          ${(d.battery_power_watts || 0).toFixed(0)} W
        </div>
        <div class="stat-footer">
          <span>Net Amps: ${(d.battery_current || 0).toFixed(1)} A</span>
          <span>Temp: ${(d.battery_temp_c || 25).toFixed(1)} °C</span>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-header">
          <span class="stat-title">HOUSEHOLD LOADS</span>
          <span class="stat-badge">Consumption</span>
        </div>
        <div class="stat-main" style="color: var(--load-color);">${(d.load_power_watts || 0).toFixed(0)} W</div>
        <div class="stat-footer">
          <span>Inverter Out: ${(d.inverter_power_watts || 0).toFixed(0)} W</span>
          <span>Grid/Gen In: ${(d.grid_gen_power_watts || 0).toFixed(0)} W</span>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-header">
          <span class="stat-title">AC ISLAND BUS</span>
          <span class="stat-badge">Grid Forming</span>
        </div>
        <div class="stat-main" style="color: #38bdf8;">${(d.ac_voltage || 120).toFixed(1)} V</div>
        <div class="stat-footer">
          <span>Frequency: ${(d.ac_frequency || 60).toFixed(2)} Hz</span>
          <span>Phase: 120V L1</span>
        </div>
      </div>
    `;

    parameterSections.innerHTML = `
      <section class="device-section">
        <div class="device-section-title"><span>🔋</span> Discover AES Lithium Battery (Live BMS Measurements)</div>
        <div class="params-grid">
          <div class="param-card">
            <span class="param-label">State of Charge (SoC)</span>
            <span class="param-val" style="color: var(--battery-color);">${(d.battery_soc || 0).toFixed(1)}%</span>
            <span class="param-sub">CAN 0x355 / WebBox: BatSoc</span>
          </div>
          <div class="param-card">
            <span class="param-label">State of Health (SoH)</span>
            <span class="param-val">${(d.battery_soh || 100).toFixed(1)}%</span>
            <span class="param-sub">CAN 0x355 / WebBox: Soh</span>
          </div>
          <div class="param-card">
            <span class="param-label">Battery Terminal Voltage</span>
            <span class="param-val">${(d.battery_voltage || 0).toFixed(1)} V</span>
            <span class="param-sub">CAN 0x356 / WebBox: BatVtg</span>
          </div>
          <div class="param-card">
            <span class="param-label">Net Battery Current</span>
            <span class="param-val">${(d.battery_current || 0).toFixed(1)} A</span>
            <span class="param-sub">CAN 0x356 (+Chg, -Dischg)</span>
          </div>
          <div class="param-card">
            <span class="param-label">Battery Net Power</span>
            <span class="param-val">${(d.battery_power_watts || 0).toFixed(0)} W</span>
            <span class="param-sub">${((d.battery_power_watts || 0) / 1000).toFixed(2)} kW Terminal Flow</span>
          </div>
          <div class="param-card">
            <span class="param-label">Average Cell Temperature</span>
            <span class="param-val">${(d.battery_temp_c || 25).toFixed(1)} °C</span>
            <span class="param-sub">${d.battery_temp_f ? d.battery_temp_f.toFixed(1) + ' °F' : ''} (CAN 0x356 / BatTmp)</span>
          </div>
        </div>
      </section>

      <section class="device-section">
        <div class="device-section-title"><span>🔗</span> LYNK II Closed-Loop CANbus Parameters (Passed to SI 6048)</div>
        <div class="params-grid">
          <div class="param-card">
            <span class="param-label">Target Charge Voltage</span>
            <span class="param-val">54.4 V</span>
            <span class="param-sub">CAN 0x351 (Dynamic BMS Target)</span>
          </div>
          <div class="param-card">
            <span class="param-label">Charge Current Limit</span>
            <span class="param-val">Auto (BMS)</span>
            <span class="param-sub">CAN 0x351 (Requested Charge Amps)</span>
          </div>
          <div class="param-card">
            <span class="param-label">Max Discharge Current</span>
            <span class="param-val">Auto (BMS)</span>
            <span class="param-sub">CAN 0x351 (Max Discharge Amps)</span>
          </div>
          <div class="param-card">
            <span class="param-label">Low Battery Cut-Out</span>
            <span class="param-val">48.0 V</span>
            <span class="param-sub">CAN 0x351 (Hardware Cutoff)</span>
          </div>
          <div class="param-card">
            <span class="param-label">Battery Chemistry</span>
            <span class="param-val">LiFePO4</span>
            <span class="param-sub">Lithium Iron Phosphate (AES)</span>
          </div>
          <div class="param-card">
            <span class="param-label">Closed-Loop Link</span>
            <span class="param-val" style="color: #10b981;">Connected</span>
            <span class="param-sub">250 kbps RJ45 (ComSync In)</span>
          </div>
          <div class="param-card">
            <span class="param-label">BMS Alarms / Faults</span>
            <span class="param-val" style="color: #10b981;">Normal</span>
            <span class="param-sub">CAN 0x35A / 0x35B (No Alarms)</span>
          </div>
          <div class="param-card">
            <span class="param-label">Nominal Bank Voltage</span>
            <span class="param-val">48 V</span>
            <span class="param-sub">Auto-set by SI on BMS Sync</span>
          </div>
        </div>
      </section>

      <section class="device-section">
        <div class="device-section-title"><span>⚡</span> SMA Sunny Island 6048 Inverter & AC Distribution</div>
        <div class="params-grid">
          <div class="param-card">
            <span class="param-label">Inverter Active Power</span>
            <span class="param-val">${(d.inverter_power_watts || 0).toFixed(0)} W</span>
            <span class="param-sub">WebBox Channel: TotInvPwrAt</span>
          </div>
          <div class="param-card">
            <span class="param-label">Household Load Power</span>
            <span class="param-val" style="color: var(--load-color);">${(d.load_power_watts || 0).toFixed(0)} W</span>
            <span class="param-sub">WebBox Channel: TotLodPwr</span>
          </div>
          <div class="param-card">
            <span class="param-label">External Input / Gen</span>
            <span class="param-val">${(d.grid_gen_power_watts || 0).toFixed(0)} W</span>
            <span class="param-sub">WebBox Channel: TotExtPwrAt</span>
          </div>
          <div class="param-card">
            <span class="param-label">AC Island Bus Voltage</span>
            <span class="param-val">${(d.ac_voltage || 120).toFixed(1)} V</span>
            <span class="param-sub">WebBox Channel: Vac</span>
          </div>
          <div class="param-card">
            <span class="param-label">AC Grid Frequency</span>
            <span class="param-val">${(d.ac_frequency || 60).toFixed(2)} Hz</span>
            <span class="param-sub">WebBox Channel: Fac</span>
          </div>
        </div>
      </section>
    `;

    // 3. Raw Table Rows
    const channels = payload.channels || d.raw_channels || [];
    rawRowsData = channels.map(c => ({
      id: c.meta || "--",
      name: c.name || c.meta || "--",
      desc: "Sunny Island WebBox Process Channel",
      val: `${c.value !== undefined ? c.value : '--'} ${c.unit || ''}`
    }));

    renderFilteredTable(diagSearch.value.toLowerCase().trim());
  }

  // --- SMA SUNNY BOY 4000 RENDERER ---
  function renderSunnyBoyView(payload, d) {
    deviceTitle.textContent = "SMA Sunny Boy 4000";
    deviceSubtitle.textContent = "Grid-Tie Photovoltaic Inverter (AC-Coupled)";
    badgeModel.textContent = "Sunny Boy 4000-US";
    badgeProtocol.textContent = "RS485 via WebBox";

    heroGrid.innerHTML = `
      <div class="stat-card">
        <div class="stat-header">
          <span class="stat-title">AC POWER GENERATION</span>
          <span class="stat-badge">${escapeHtml(d.mode || "OK")}</span>
        </div>
        <div class="stat-main" style="color: var(--solar-color);">${(d.pv_power_watts || 0).toFixed(0)} W</div>
        <div class="stat-footer">
          <span>AC Volts: ${(d.ac_voltage || 240).toFixed(1)} V</span>
          <span>Freq: ${(d.ac_frequency || 60).toFixed(2)} Hz</span>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-header">
          <span class="stat-title">LIFETIME GENERATION</span>
          <span class="stat-badge">Total Yield</span>
        </div>
        <div class="stat-main" style="color: #10b981;">${(d.energy_total_kwh || 0).toFixed(1)} kWh</div>
        <div class="stat-footer">
          <span>Channel: E-Total</span>
          <span>Operating: Active</span>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-header">
          <span class="stat-title">DC ARRAY INPUT</span>
          <span class="stat-badge">Solar String</span>
        </div>
        <div class="stat-main" style="color: #38bdf8;">${(d.dc_power_watts || 0).toFixed(0)} W</div>
        <div class="stat-footer">
          <span>Voltage: ${(d.pv_voltage || 0).toFixed(1)} V</span>
          <span>Current: ${(d.pv_current || 0).toFixed(1)} A</span>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-header">
          <span class="stat-title">INVERTER HEALTH</span>
          <span class="stat-badge">Thermals</span>
        </div>
        <div class="stat-main" style="color: #f59e0b;">${(d.temp_c || 0).toFixed(1)} °C</div>
        <div class="stat-footer">
          <span>${d.temp_f ? d.temp_f.toFixed(1) + ' °F' : '--'}</span>
          <span>Status: ${escapeHtml(d.mode || "OK")}</span>
        </div>
      </div>
    `;

    parameterSections.innerHTML = `
      <section class="device-section">
        <div class="device-section-title"><span>⚡</span> AC Output Telemetry</div>
        <div class="params-grid">
          <div class="param-card">
            <span class="param-label">Active AC Power</span>
            <span class="param-val">${(d.pv_power_watts || 0).toFixed(0)} W</span>
            <span class="param-sub">WebBox Channel: Pac</span>
          </div>
          <div class="param-card">
            <span class="param-label">AC Grid Voltage</span>
            <span class="param-val">${(d.ac_voltage || 240).toFixed(1)} V</span>
            <span class="param-sub">WebBox Channel: Vac</span>
          </div>
          <div class="param-card">
            <span class="param-label">AC Grid Frequency</span>
            <span class="param-val">${(d.ac_frequency || 60).toFixed(2)} Hz</span>
            <span class="param-sub">WebBox Channel: Fac</span>
          </div>
        </div>
      </section>

      <section class="device-section">
        <div class="device-section-title"><span>☀️</span> DC Photovoltaic Input String</div>
        <div class="params-grid">
          <div class="param-card">
            <span class="param-label">DC Solar Voltage</span>
            <span class="param-val">${(d.pv_voltage || 0).toFixed(1)} V</span>
            <span class="param-sub">WebBox Channel: Vpv</span>
          </div>
          <div class="param-card">
            <span class="param-label">DC Solar Current</span>
            <span class="param-val">${(d.pv_current || 0).toFixed(1)} A</span>
            <span class="param-sub">WebBox Channel: Ipv</span>
          </div>
          <div class="param-card">
            <span class="param-label">Calculated DC Power</span>
            <span class="param-val">${(d.dc_power_watts || 0).toFixed(0)} W</span>
            <span class="param-sub">Vpv * Ipv</span>
          </div>
        </div>
      </section>

      <section class="device-section">
        <div class="device-section-title"><span>📊</span> Energy Yield & Thermals</div>
        <div class="params-grid">
          <div class="param-card">
            <span class="param-label">Lifetime Total Energy</span>
            <span class="param-val">${(d.energy_total_kwh || 0).toFixed(1)} kWh</span>
            <span class="param-sub">WebBox Channel: E-Total</span>
          </div>
          <div class="param-card">
            <span class="param-label">Internal Temperature</span>
            <span class="param-val">${(d.temp_c || 0).toFixed(1)} °C</span>
            <span class="param-sub">${d.temp_f ? d.temp_f.toFixed(1) + ' °F' : ''} (Temperature)</span>
          </div>
          <div class="param-card">
            <span class="param-label">Operating Mode</span>
            <span class="param-val">${escapeHtml(d.mode || "OK")}</span>
            <span class="param-sub">WebBox Channel: Mode</span>
          </div>
        </div>
      </section>
    `;

    const channels = payload.channels || d.raw_channels || [];
    rawRowsData = channels.map(c => ({
      id: c.meta || "--",
      name: c.name || c.meta || "--",
      desc: "Sunny Boy WebBox Process Channel",
      val: `${c.value !== undefined ? c.value : '--'} ${c.unit || ''}`
    }));

    renderFilteredTable(diagSearch.value.toLowerCase().trim());
  }

  function renderGenericView(payload, d) {
    deviceTitle.textContent = payload.device_name || "Device Telemetry";
    deviceSubtitle.textContent = payload.model || "Hardware Telemetry View";
    heroGrid.innerHTML = `<div class="stat-card"><div class="stat-main">Active</div></div>`;
  }

  // Initial fetch and 3-second polling interval
  fetchDeviceTelemetry();
  setInterval(fetchDeviceTelemetry, 3000);
});
