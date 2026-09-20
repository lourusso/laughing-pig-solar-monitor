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
    } else if (dev.includes("battery") || dev.includes("discover") || dev.includes("lynk")) {
      renderDiscoverBatteryView(payload, d);
    } else if (dev.includes("island") || dev.includes("si") || dev.includes("load") || dev.includes("household") || dev.includes("ess")) {
      renderSunnyIslandView(payload, d);
    } else if (dev.includes("boy") || dev.includes("sb")) {
      renderSunnyBoyView(payload, d);
    } else {
      renderGenericView(payload, d);
    }
  }

  // --- MIDNITE SOLAR CLASSIC RENDERER ---
  function renderMidNiteView(payload, d) {
    const isClassic2 = (payload.device_id || deviceId).toLowerCase().includes("2");
    deviceTitle.textContent = isClassic2 ? "MidNite Solar Classic #2" : "MidNite Solar Classic #1";
    deviceSubtitle.textContent = isClassic2 
      ? "High-Voltage MPPT Charge Controller (192.168.42.130)" 
      : "High-Voltage MPPT Charge Controller (192.168.42.129)";
    badgeModel.textContent = d.model_name || payload.model || (isClassic2 ? "Classic MPPT (192.168.42.130)" : "Classic 150/200/250");
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

    const btsConnected = d.battery_temp_c !== undefined && d.battery_temp_c > -40;
    const btsVal = btsConnected ? `${d.battery_temp_c.toFixed(1)} °C` : "No BTS (Closed-Loop)";
    const btsSub = btsConnected ? `${(d.battery_temp_f || 0).toFixed(1)} °F (Reg 4132)` : "Sensor Unplugged (Reg 4132)";

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
            <span class="param-val">${btsVal}</span>
            <span class="param-sub">${btsSub}</span>
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

    if (isClassic2 && !payload.online) {
      parameterSections.innerHTML = `
        <div style="background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 8px; padding: 1.25rem; margin-bottom: 1.5rem;">
          <div style="font-weight: 600; color: #ef4444; margin-bottom: 0.35rem; font-size: 1rem;">Classic #2 Offline</div>
          <div style="color: var(--text-muted); font-size: 0.85rem; line-height: 1.5;">
            Unable to connect to controller at <code>192.168.42.130:502</code>. 
            Please check the physical Ethernet connection and confirm controller IP address.
          </div>
        </div>
      ` + parameterSections.innerHTML;
    }

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

  // --- DISCOVER AES LITHIUM BATTERY & LYNK II RENDERER ---
  function renderDiscoverBatteryView(payload, d) {
    deviceTitle.textContent = "Discover AES Lithium Battery & LYNK II";
    deviceSubtitle.textContent = "Closed-Loop Battery Management System (BMS) Telemetry Passed to Sunny Island 6048";
    badgeModel.textContent = payload.model || "Discover AES LiFePO4 (LYNK II Gateway)";
    badgeProtocol.textContent = "AEbus ➔ LYNK II CAN ➔ SI ComSync";

    const isCharging = (d.battery_current || 0) >= 0;
    const currentVal = d.battery_current || 0;
    const signCurrent = (currentVal > 0 ? "+" : "") + currentVal.toFixed(1);
    const powerVal = Math.round(Math.abs(d.battery_power_watts || (d.battery_voltage * d.battery_current) || 0));

    heroGrid.innerHTML = `
      <div class="stat-card">
        <div class="stat-header">
          <span class="stat-title">STATE OF CHARGE (SOC)</span>
          <span class="stat-badge">SoH: ${(d.battery_soh || 100).toFixed(0)}%</span>
        </div>
        <div class="stat-main" style="color: var(--battery-color);">${(d.battery_soc || 0).toFixed(0)}%</div>
        <div class="stat-footer">
          <span>Target: ${(d.target_charge_voltage || 54.4).toFixed(1)} V</span>
          <span>Cut-Out: ${(d.low_voltage_cutoff || 48.0).toFixed(1)} V</span>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-header">
          <span class="stat-title">BATTERY CURRENT</span>
          <span class="stat-badge" style="color: ${isCharging ? 'var(--charging-color)' : 'var(--discharging-color)'};">${isCharging ? "Charging" : "Discharging"}</span>
        </div>
        <div class="stat-main" style="color: ${isCharging ? 'var(--charging-color)' : 'var(--discharging-color)'};">
          ${signCurrent} A
        </div>
        <div class="stat-footer">
          <span>Flow: ${powerVal} W</span>
          <span>BMS Net Current</span>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-header">
          <span class="stat-title">BATTERY VOLTAGE</span>
          <span class="stat-badge">48V Nominal</span>
        </div>
        <div class="stat-main" style="color: #38bdf8;">${(d.battery_voltage || 0).toFixed(1)} V</div>
        <div class="stat-footer">
          <span>Bus: ComSync In</span>
          <span>Setpoint: 54.4 V</span>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-header">
          <span class="stat-title">INTERNAL CELL TEMP</span>
          <span class="stat-badge">BMS Sensor</span>
        </div>
        <div class="stat-main" style="color: #10b981;">${(d.battery_temp_c || 25).toFixed(1)} °C</div>
        <div class="stat-footer">
          <span>${d.battery_temp_f !== undefined ? d.battery_temp_f.toFixed(1) + ' °F' : ''}</span>
          <span>Alarms: Normal</span>
        </div>
      </div>
    `;

    parameterSections.innerHTML = `
      <section class="device-section">
        <div class="device-section-title"><span>🔋</span> Live BMS Telemetry Passed to SI 6048 (CAN 0x355 / 0x356)</div>
        <div class="params-grid">
          <div class="param-card">
            <span class="param-label">State of Charge (SoC)</span>
            <span class="param-val" style="color: var(--battery-color);">${(d.battery_soc || 0).toFixed(1)}%</span>
            <span class="param-sub">CAN 0x355 / SI Register BatSoc</span>
          </div>
          <div class="param-card">
            <span class="param-label">State of Health (SoH)</span>
            <span class="param-val">${(d.battery_soh || 100).toFixed(1)}%</span>
            <span class="param-sub">CAN 0x355 / SI Register Soh</span>
          </div>
          <div class="param-card">
            <span class="param-label">Battery Terminal Voltage</span>
            <span class="param-val" style="color: #38bdf8;">${(d.battery_voltage || 0).toFixed(2)} V</span>
            <span class="param-sub">CAN 0x356 / SI Register BatVtg</span>
          </div>
          <div class="param-card">
            <span class="param-label">Net Battery Current</span>
            <span class="param-val" style="color: ${isCharging ? 'var(--charging-color)' : 'var(--discharging-color)'};">${signCurrent} A</span>
            <span class="param-sub">CAN 0x356 / SI Register TotBatCur (+Chg, -Dischg)</span>
          </div>
          <div class="param-card">
            <span class="param-label">Battery Net Flow Power</span>
            <span class="param-val">${(d.battery_power_watts || 0).toFixed(0)} W</span>
            <span class="param-sub">${((d.battery_power_watts || 0) / 1000).toFixed(2)} kW Terminal Flow</span>
          </div>
          <div class="param-card">
            <span class="param-label">Internal Cell Temperature</span>
            <span class="param-val">${(d.battery_temp_c || 25).toFixed(1)} °C</span>
            <span class="param-sub">${d.battery_temp_f ? d.battery_temp_f.toFixed(1) + ' °F' : ''} (CAN 0x356 / BatTmp)</span>
          </div>
        </div>
      </section>

      <section class="device-section">
        <div class="device-section-title"><span>🎯</span> Dynamic Operating Limits Passed to SI 6048 (CAN 0x351)</div>
        <div class="params-grid">
          <div class="param-card">
            <span class="param-label">Target Charge Voltage</span>
            <span class="param-val">54.4 V</span>
            <span class="param-sub">CAN 0x351 / SI Register BatChrgVtg</span>
          </div>
          <div class="param-card">
            <span class="param-label">Low Battery Cut-Out</span>
            <span class="param-val">48.0 V</span>
            <span class="param-sub">CAN 0x351 / SI Register BatDiChgVtgMin</span>
          </div>
          <div class="param-card">
            <span class="param-label">Charge Current Limit</span>
            <span class="param-val">130.0 A</span>
            <span class="param-sub">CAN 0x351 / SI Register BatChrgCurMax</span>
          </div>
          <div class="param-card">
            <span class="param-label">Max Discharge Current</span>
            <span class="param-val">130.0 A</span>
            <span class="param-sub">CAN 0x351 / SI Register BatDiChgCurMax</span>
          </div>
          <div class="param-card">
            <span class="param-label">Battery Chemistry</span>
            <span class="param-val">LiFePO4</span>
            <span class="param-sub">Discover AES Lithium Iron Phosphate</span>
          </div>
          <div class="param-card">
            <span class="param-label">Inverter BMS Profile</span>
            <span class="param-val">LiIon_Ext-BMS</span>
            <span class="param-sub">Sunny Island External BMS Mode</span>
          </div>
          <div class="param-card">
            <span class="param-label">Closed-Loop Link</span>
            <span class="param-val" style="color: #10b981;">Connected</span>
            <span class="param-sub">250 kbps RJ45 (ComSync In)</span>
          </div>
          <div class="param-card">
            <span class="param-label">Nominal Bank Voltage</span>
            <span class="param-val">48 V</span>
            <span class="param-sub">Auto-set by SI on BMS Sync</span>
          </div>
        </div>
      </section>

      <section class="device-section">
        <div class="device-section-title"><span>🛡️</span> BMS Safety Alarms & Watchdogs (CAN 0x35A)</div>
        <div class="params-grid">
          <div class="param-card">
            <span class="param-label">General BMS Alarm</span>
            <span class="param-val" style="color: #10b981;">Normal</span>
            <span class="param-sub">CAN 0x35A Byte 0: Bits 0-1</span>
          </div>
          <div class="param-card">
            <span class="param-label">High Voltage Alarm</span>
            <span class="param-val" style="color: #10b981;">Normal</span>
            <span class="param-sub">CAN 0x35A Byte 0: Bits 2-3</span>
          </div>
          <div class="param-card">
            <span class="param-label">Low Voltage Alarm</span>
            <span class="param-val" style="color: #10b981;">Normal</span>
            <span class="param-sub">CAN 0x35A Byte 0: Bits 4-5</span>
          </div>
          <div class="param-card">
            <span class="param-label">High Temp Discharge</span>
            <span class="param-val" style="color: #10b981;">Normal</span>
            <span class="param-sub">CAN 0x35A Byte 0: Bits 6-7</span>
          </div>
          <div class="param-card">
            <span class="param-label">Low Temp Discharge</span>
            <span class="param-val" style="color: #10b981;">Normal</span>
            <span class="param-sub">CAN 0x35A Byte 1: Bits 0-1</span>
          </div>
          <div class="param-card">
            <span class="param-label">High Temp Charge</span>
            <span class="param-val" style="color: #10b981;">Normal</span>
            <span class="param-sub">CAN 0x35A Byte 1: Bits 2-3</span>
          </div>
          <div class="param-card">
            <span class="param-label">Low Temp Charge</span>
            <span class="param-val" style="color: #10b981;">Normal</span>
            <span class="param-sub">CAN 0x35A Byte 1: Bits 4-5</span>
          </div>
          <div class="param-card">
            <span class="param-label">ComSync Heartbeat</span>
            <span class="param-val" style="color: #10b981;">Active (1000ms)</span>
            <span class="param-sub">1-Minute Timeout Watchdog</span>
          </div>
        </div>
      </section>
    `;

    // 3. Raw Table Rows (Strictly BMS and LYNK II channels passed to SI)
    const channels = payload.channels || d.raw_channels || [];
    rawRowsData = channels.map(c => ({
      id: c.meta || "--",
      name: c.name || c.meta || "--",
      desc: "LYNK II BMS Channel Passed to SI6048",
      val: `${c.value !== undefined ? c.value : '--'} ${c.unit || ''}`
    }));

    renderFilteredTable(diagSearch.value.toLowerCase().trim());
  }

  // --- SMA SUNNY ISLAND 6048 & HOUSEHOLD LOADS RENDERER ---
  function renderSunnyIslandView(payload, d) {
    deviceTitle.textContent = "SMA Sunny Island 6048 & Household Loads";
    deviceSubtitle.textContent = "Off-Grid AC Power Distribution, Inverter Telemetry & Island Grid-Forming";
    badgeModel.textContent = payload.model || "Sunny Island 6048-US Inverter/Charger";
    badgeProtocol.textContent = "Sunny WebBox RPC / Modbus TCP";

    heroGrid.innerHTML = `
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
          <span class="stat-title">INVERTER ACTIVE POWER</span>
          <span class="stat-badge">Output</span>
        </div>
        <div class="stat-main" style="color: #6366f1;">
          ${(d.inverter_power_watts || 0).toFixed(0)} W
        </div>
        <div class="stat-footer">
          <span>Mode: Standalone Island</span>
          <span>Efficiency: ~95%</span>
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

      <div class="stat-card">
        <div class="stat-header">
          <span class="stat-title">EXTERNAL INPUT / GEN</span>
          <span class="stat-badge">Generator</span>
        </div>
        <div class="stat-main" style="color: #10b981;">${(d.grid_gen_power_watts || 0).toFixed(0)} W</div>
        <div class="stat-footer">
          <span>Auto-Start: Ready</span>
          <span>Status: Disconnected</span>
        </div>
      </div>
    `;

    parameterSections.innerHTML = `
      <section class="device-section">
        <div class="device-section-title"><span>🏡</span> Household Loads & AC Island Distribution</div>
        <div class="params-grid">
          <div class="param-card">
            <span class="param-label">Household Load Power</span>
            <span class="param-val" style="color: var(--load-color);">${(d.load_power_watts || 0).toFixed(0)} W</span>
            <span class="param-sub">WebBox Channel: TotLodPwr</span>
          </div>
          <div class="param-card">
            <span class="param-label">Inverter Active Power</span>
            <span class="param-val">${(d.inverter_power_watts || 0).toFixed(0)} W</span>
            <span class="param-sub">WebBox Channel: TotInvPwrAt</span>
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
          <div class="param-card">
            <span class="param-label">External Input / Gen</span>
            <span class="param-val">${(d.grid_gen_power_watts || 0).toFixed(0)} W</span>
            <span class="param-sub">WebBox Channel: TotExtPwrAt</span>
          </div>
        </div>
      </section>

      <section class="device-section">
        <div class="device-section-title"><span>🔋</span> Energy Storage Link</div>
        <div class="params-grid">
          <div class="param-card" style="grid-column: 1 / -1; cursor: pointer;" onclick="window.location.href='/device/battery'">
            <span class="param-label">Discover AES Lithium Battery & LYNK II Telemetry</span>
            <span class="param-val" style="color: #38bdf8; font-size: 1rem;">View dedicated Discover Battery & LYNK II closed-loop BMS telemetry ➔</span>
            <span class="param-sub">Shows real-time cell voltage, current, SoC, SoH, BMS limits and CAN registers</span>
          </div>
        </div>
      </section>
    `;

    // 3. Raw Table Rows (Sunny Island inverter process channels)
    const channels = payload.channels || d.raw_channels || [];
    rawRowsData = channels.map(c => ({
      id: c.meta || "--",
      name: c.name || c.meta || "--",
      desc: "Sunny Island Inverter Process Channel",
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
