const $ = (id) => document.getElementById(id),
  canvas = $("scene"),
  ctx = canvas.getContext("2d");
let state = null,
  running = false,
  busy = false,
  resetting = false,
  trail = [],
  samples = [],
  keys = new Set(),
  lastSample = -1,
  epoch = 0;
let padEnabled = false,
  padInput = { forward: 0, right: 0, climb: 0, yaw: 0 },
  pausePressed = false,
  padSignature = "";
let camera = { angle: -2.2, elevation: 0.54, distance: 13 },
  focus = [0, 0, 1],
  lastFrame = performance.now();
const movers = [
  "KeyW",
  "KeyA",
  "KeyS",
  "KeyD",
  "KeyQ",
  "KeyE",
  "ArrowUp",
  "ArrowDown",
  "ArrowLeft",
  "ArrowRight",
];
const vec = {
  add: (a, b) => a.map((x, i) => x + b[i]),
  sub: (a, b) => a.map((x, i) => x - b[i]),
  mul: (a, k) => a.map((x) => x * k),
  dot: (a, b) => a.reduce((s, x, i) => s + x * b[i], 0),
  cross: (a, b) => [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ],
  norm: (a) => Math.hypot(...a),
};
const unit = (a) => vec.mul(a, 1 / vec.norm(a));
for (let i = 1; i <= 4; i++)
  $("motors").insertAdjacentHTML(
    "beforeend",
    `<div class="motor"><span>M${i}</span><div class="bar"><i id="bar${i}"></i></div><strong id="rpm${i}">—</strong></div>`,
  );
function clearKeys() {
  keys.clear();
  document
    .querySelectorAll("[data-key]")
    .forEach((b) => b.classList.remove("active"));
}
const mapping = [
  ["climb", "推力", 1, true],
  ["yaw", "Yaw", 0, false],
  ["forward", "Pitch（前進）", 3, true],
  ["right", "Roll（右）", 2, false],
];
for (const [key, label, axis, invert] of mapping) {
  $("axisSettings").insertAdjacentHTML(
    "beforeend",
    `<div class="field"><label>${label}<span><input type="checkbox" id="invert-${key}" ${invert ? "checked" : ""}>反転</span></label><select id="axis-${key}" aria-label="${label}の軸">${Array.from({ length: 12 }, (_, i) => `<option value="${i}" ${i === axis ? "selected" : ""}>Axis ${i}</option>`).join("")}</select></div>`,
  );
}
function modeChanged() {
  const manual = $("controlMode").value === "attitude";
  $("modeHint").textContent = manual
    ? "右スティックで最大25°の姿勢、左で推力・Yawを指令。中立は水平・ホバー相当推力。位置・高度は保持しません。"
    : "キーを離すと減速し、高度と方位を保ちます。";
  $("targetSpeed").disabled = manual;
  reset();
}
$("controlMode").onchange = modeChanged;
$("padUse").onclick = () => {
  padEnabled = !padEnabled;
  if (padEnabled) {
    $("controlMode").value = "attitude";
    modeChanged();
  }
  $("padUse").textContent = padEnabled
    ? "キーボード操作に戻す"
    : "コントローラーで操縦する";
};
function gamepad() {
  const pads = Array.from(
      navigator.getGamepads ? navigator.getGamepads() : [],
    ).filter(Boolean),
    signature = pads.map((p) => p.index + ":" + p.id).join("|");
  if (signature !== padSignature) {
    const old = $("padSelect").value;
    $("padSelect").innerHTML = pads.length
      ? pads
          .map((p) => {
            const o = document.createElement("option");
            o.value = p.index;
            o.textContent = p.id;
            return o.outerHTML;
          })
          .join("")
      : '<option value="">接続を待っています</option>';
    if (pads.some((p) => String(p.index) === old)) $("padSelect").value = old;
    padSignature = signature;
  }
  const p = pads.find((p) => String(p.index) === $("padSelect").value);
  if (!p) {
    if (padEnabled) {
      pause();
      padEnabled = false;
      $("padUse").textContent = "コントローラーで操縦する";
    }
    $("padStatus").textContent =
      "接続後、コントローラーのボタンを一度押してください。";
    return;
  }
  $("padStatus").textContent =
    `認識済み · ${p.axes.length}軸 / ${p.buttons.length}ボタン${padEnabled ? " · 操縦中" : ""}`;
  $("rawAxes").textContent = p.axes
    .map((v, i) => `${i}: ${v.toFixed(2)}`)
    .join(" ／ ");
  let valid = true;
  for (const [key] of mapping) {
    const axis = Number($("axis-" + key).value);
    if (axis >= p.axes.length) {
      valid = false;
      padInput[key] = 0;
      continue;
    }
    let v = p.axes[axis] * ($("invert-" + key).checked ? -1 : 1);
    v = Math.abs(v) < 0.08 ? 0 : (Math.sign(v) * (Math.abs(v) - 0.08)) / 0.92;
    padInput[key] = 0.7 * v + 0.3 * v * v * v;
  }
  $("stickReadout").textContent =
    `推力 ${padInput.climb.toFixed(2)} ／ Yaw ${padInput.yaw.toFixed(2)} ／ Pitch ${padInput.forward.toFixed(2)} ／ Roll ${padInput.right.toFixed(2)}`;
  if (!valid && padEnabled) {
    pause();
    $("padStatus").textContent =
      "軸割り当てが範囲外です。設定を変更してください。";
  }
  const pressed = p.buttons[9]?.pressed || false;
  if (padEnabled && pressed && !pausePressed) $("play").click();
  pausePressed = pressed;
}
function pause() {
  running = false;
  clearKeys();
  $("play").textContent = "▶ 再開";
}
function accept(s) {
  state = s;
  if (s.time > lastSample) {
    trail.push([s.position[0], s.position[1], -s.position[2]]);
    if (trail.length > 12000) trail.shift();
    samples.push([s.time, Math.hypot(...s.velocity), -s.position[2]]);
    samples = samples.filter((a) => a[0] > s.time - 20);
    lastSample = s.time;
  }
  $("height").innerHTML = `${(-s.position[2]).toFixed(2)} <small>m</small>`;
  $("speed").innerHTML =
    `${Math.hypot(...s.velocity).toFixed(2)} <small>m/s</small>`;
  $("air").innerHTML =
    `${Math.hypot(...s.velocity.map((v, i) => v - s.wind[i])).toFixed(2)} <small>m/s</small>`;
  ["roll", "pitch", "yaw"].forEach(
    (id, i) => ($(id).textContent = s.angles[i].toFixed(1) + "°"),
  );
  s.rpm.forEach((v, i) => {
    $("rpm" + (i + 1)).textContent = Math.round(v);
    $("bar" + (i + 1)).style.width = Math.min(100, (v / 9000) * 100) + "%";
  });
  $("targets").textContent =
    $("controlMode").value === "attitude"
      ? "姿勢＋推力操縦 · 高度保持なし"
      : `目標高度 ${s.height_target.toFixed(1)} m ／ 方位 ${(((s.heading_target % 360) + 360) % 360).toFixed(0)}°`;
  $("saturation").textContent = [
    s.torque_saturated ? "姿勢制御のモーメント上限" : null,
    s.motor_saturated ? "モーター指令の上限 / 下限" : null,
  ]
    .filter(Boolean)
    .join(" ／ ");
  $("clock").textContent = `計算時間 ${s.time.toFixed(2)} s`;
  $("badge").textContent =
    s.model === "identified" ? "同定モデル" : "既存モデル";
  $("badge").style.color = s.model === "identified" ? "#087e9b" : "#b4783b";
  if (!["running", "ready"].includes(s.status)) {
    pause();
    $("notice").textContent = s.status;
    $("notice").style.display = "block";
    $("play").disabled = true;
  }
}
async function api(path, body) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const r = await fetch(path, {
      signal: controller.signal,
      method: body ? "POST" : "GET",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    const j = await r.json();
    if (!r.ok) throw Error(j.error || r.statusText);
    return j;
  } finally {
    clearTimeout(timeout);
  }
}
async function reset() {
  if (resetting) return;
  resetting = true;
  pause();
  epoch++;
  $("play").disabled = true;
  $("notice").textContent = "ホバーの釣り合いを計算中…";
  $("notice").style.display = "block";
  try {
    while (busy) await new Promise((r) => setTimeout(r, 20));
    const s = await api("/reset", {
      model: $("model").value,
      route: $("route").value,
    });
    trail = [];
    samples = [];
    lastSample = -1;
    focus = [0, 0, 1];
    $("wind").value = 0;
    updateSliders();
    accept(s);
    $("notice").style.display = "none";
    $("play").disabled = false;
    $("reconnect").hidden = true;
    $("play").textContent = "▶ 開始";
  } catch (e) {
    failure(e);
  } finally {
    resetting = false;
  }
}
function failure(e) {
  pause();
  $("play").disabled = true;
  $("reconnect").hidden = false;
  $("notice").textContent =
    "接続できません。起動用ターミナルを確認し、再接続してください。状態は自動リセットしません。 (" +
    e.message +
    ")";
  $("notice").style.display = "block";
}
$("reconnect").onclick = async () => {
  try {
    accept(await api("/state"));
    $("model").value = state.model;
    $("route").value = state.route;
    $("controlMode").value = state.control_mode;
    $("reconnect").hidden = true;
    if (["running", "ready"].includes(state.status)) {
      $("notice").style.display = "none";
      $("play").disabled = false;
    }
  } catch (e) {
    failure(e);
  }
};
$("play").onclick = () => {
  if (running) pause();
  else if (state && ["ready", "running"].includes(state.status)) {
    running = true;
    $("play").textContent = "Ⅱ 一時停止";
  }
};
$("reset").onclick = reset;
$("model").onchange = reset;
$("route").onchange = reset;
$("camera").onclick = () =>
  (camera = { angle: -2.2, elevation: 0.54, distance: 13 });
$("brake").onclick = () => {
  clearKeys();
  if (padEnabled) pause();
};
function updateSliders() {
  $("targetSpeedValue").textContent =
    Number($("targetSpeed").value).toFixed(1) + " m/s";
  $("windValue").textContent = Number($("wind").value).toFixed(1) + " m/s";
  $("windHeadingValue").textContent = $("windHeading").value + "°";
}
["targetSpeed", "wind", "windHeading"].forEach(
  (id) => ($(id).oninput = updateSliders),
);
document.querySelectorAll("[data-key]").forEach((b) => {
  b.onpointerdown = (e) => {
    e.preventDefault();
    b.setPointerCapture(e.pointerId);
    keys.add(b.dataset.key);
    b.classList.add("active");
  };
  const end = () => {
    keys.delete(b.dataset.key);
    b.classList.remove("active");
  };
  b.onpointerup = end;
  b.onpointercancel = end;
  b.onlostpointercapture = end;
});
window.addEventListener("keydown", (e) => {
  if (["INPUT", "SELECT"].includes(document.activeElement.tagName)) return;
  if (movers.includes(e.code)) {
    e.preventDefault();
    keys.add(e.code);
  } else if (e.code === "Space") {
    e.preventDefault();
    clearKeys();
  } else if (!e.repeat && e.code === "KeyP") $("play").click();
  else if (!e.repeat && e.code === "KeyR") reset();
});
window.addEventListener("keyup", (e) => keys.delete(e.code));
window.addEventListener("blur", pause);
document.addEventListener("visibilitychange", () => {
  if (document.hidden) pause();
});
async function tick() {
  if (running && !busy && !resetting) {
    busy = true;
    const version = epoch,
      t = performance.now();
    try {
      const controls = padEnabled
        ? padInput
        : {
            forward: Number(keys.has("KeyW")) - Number(keys.has("KeyS")),
            right: Number(keys.has("KeyD")) - Number(keys.has("KeyA")),
            climb: Number(keys.has("ArrowUp")) - Number(keys.has("ArrowDown")),
            yaw:
              Number(keys.has("KeyE") || keys.has("ArrowRight")) -
              Number(keys.has("KeyQ") || keys.has("ArrowLeft")),
          };
      const s = await api("/step", {
        ...controls,
        mode: $("controlMode").value,
        speed: Number($("targetSpeed").value),
        wind: Number($("wind").value),
        wind_heading: Number($("windHeading").value),
      });
      if (version === epoch) {
        accept(s);
        $("performance").textContent =
          `200 Hz積分 · 実時間比 ${Math.min(1, 50 / (performance.now() - t)).toFixed(2)}×`;
      }
    } catch (e) {
      failure(e);
    } finally {
      busy = false;
    }
    const delay = Math.max(0, 50 - (performance.now() - t));
    setTimeout(tick, delay);
  } else setTimeout(tick, 50);
}
let dragging = null;
canvas.onpointerdown = (e) => {
  dragging = [e.clientX, e.clientY];
  canvas.setPointerCapture(e.pointerId);
};
canvas.onpointermove = (e) => {
  if (!dragging) return;
  camera.angle -= (e.clientX - dragging[0]) * 0.006;
  camera.elevation = Math.max(
    0.12,
    Math.min(1.4, camera.elevation + (e.clientY - dragging[1]) * 0.005),
  );
  dragging = [e.clientX, e.clientY];
};
canvas.onpointerup = () => (dragging = null);
canvas.onpointercancel = () => (dragging = null);
canvas.onwheel = (e) => {
  e.preventDefault();
  camera.distance = Math.max(
    3,
    Math.min(50, camera.distance * Math.exp(e.deltaY * 0.001)),
  );
};
function resize(c) {
  const d = Math.min(devicePixelRatio || 1, 2),
    w = c.clientWidth,
    h = c.clientHeight;
  if (c.width !== Math.round(w * d) || c.height !== Math.round(h * d)) {
    c.width = Math.round(w * d);
    c.height = Math.round(h * d);
  }
  const cx = c.getContext("2d");
  cx.setTransform(d, 0, 0, d, 0, 0);
  return [w, h, cx];
}
function draw() {
  gamepad();
  const [w, h] = resize(canvas);
  ctx.clearRect(0, 0, w, h);
  const dt = Math.min(0.1, (performance.now() - lastFrame) / 1000);
  lastFrame = performance.now();
  if (state) {
    const p = [
      state.position[0],
      state.position[1],
      Math.max(0.5, -state.position[2] * 0.6),
    ];
    focus = focus.map((f, i) => f + (p[i] - f) * (1 - Math.exp(-dt * 3)));
  }
  const ce = Math.cos(camera.elevation),
    se = Math.sin(camera.elevation),
    eye = vec.add(focus, [
      camera.distance * ce * Math.cos(camera.angle),
      camera.distance * ce * Math.sin(camera.angle),
      camera.distance * se,
    ]);
  const f = unit(vec.sub(focus, eye)),
    right = unit(vec.cross(f, [0, 0, 1])),
    up = vec.cross(right, f),
    focal = Math.min(w, h) * 1.15;
  const project = (p) => {
    const v = vec.sub(p, eye),
      z = vec.dot(v, f);
    return z > 0.15
      ? [
          w / 2 + (focal * vec.dot(v, right)) / z,
          h * 0.55 - (focal * vec.dot(v, up)) / z,
          z,
        ]
      : null;
  };
  function line(a, b, color, width = 1) {
    a = project(a);
    b = project(b);
    if (!a || !b) return;
    ctx.beginPath();
    ctx.moveTo(a[0], a[1]);
    ctx.lineTo(b[0], b[1]);
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.stroke();
  }
  const gx = Math.round(focus[0]),
    gy = Math.round(focus[1]);
  for (let i = -24; i <= 24; i++) {
    const alpha = Math.max(0.02, 0.18 - Math.abs(i) * 0.005);
    line(
      [gx + i, gy - 24, 0],
      [gx + i, gy + 24, 0],
      `rgba(111,135,150,${alpha})`,
    );
    line(
      [gx - 24, gy + i, 0],
      [gx + 24, gy + i, 0],
      `rgba(111,135,150,${alpha})`,
    );
  }
  line([0, 0, 0], [4, 0, 0], "#c99263", 2);
  line([0, 0, 0], [0, 4, 0], "#6f9daf", 2);
  for (const [p, label] of [
    [[4.3, 0, 0], "+X"],
    [[0, 4.3, 0], "+Y"],
  ]) {
    const a = project(p);
    if (a) {
      ctx.fillStyle = "#6f8190";
      ctx.font = "12px sans-serif";
      ctx.fillText(label, a[0], a[1]);
    }
  }
  if (state) {
    const p = [state.position[0], state.position[1], -state.position[2]],
      r = state.rotation;
    const body = (b) =>
      vec.add(p, [
        r[0].reduce((s, x, i) => s + x * b[i], 0),
        r[1].reduce((s, x, i) => s + x * b[i], 0),
        -r[2].reduce((s, x, i) => s + x * b[i], 0),
      ]);
    for (let i = 1; i < trail.length; i++)
      line(
        trail[i - 1],
        trail[i],
        state.model === "identified" ? "#13899c8a" : "#bc834e8a",
        2,
      );
    line([p[0], p[1], 0], p, "#8ba5b880");
    const foot = project([p[0], p[1], 0.01]);
    if (foot) {
      ctx.beginPath();
      ctx.ellipse(
        foot[0],
        foot[1],
        Math.max(8, 60 / foot[2]),
        Math.max(3, 22 / foot[2]),
        0,
        0,
        Math.PI * 2,
      );
      ctx.fillStyle = "#243d571a";
      ctx.fill();
    }
    // Render at 2× physical size to make orientation readable; trajectory/grid stay metric.
    const arm = 0.5,
      rotor = 0.23,
      motor = [
        [-arm, arm, 0],
        [arm, -arm, 0],
        [arm, arm, 0],
        [-arm, -arm, 0],
      ];
    line(body([-arm, -arm, 0]), body([arm, arm, 0]), "#344b60", 5);
    line(body([-arm, arm, 0]), body([arm, -arm, 0]), "#344b60", 5);
    motor
      .map((b, i) => ({ b, i, z: project(body(b))?.[2] || 0 }))
      .sort((a, b) => b.z - a.z)
      .forEach(({ b, i }) => {
        const a = project(body(b));
        if (!a) return;
        ctx.beginPath();
        for (let k = 0; k <= 32; k++) {
          const t = (k * Math.PI) / 16,
            q = project(
              body([
                b[0] + rotor * Math.cos(t),
                b[1] + rotor * Math.sin(t),
                -0.03,
              ]),
            );
          if (q) k ? ctx.lineTo(q[0], q[1]) : ctx.moveTo(q[0], q[1]);
        }
        ctx.fillStyle = b[0] > 0 ? "#d8a87a40" : "#277e9940";
        ctx.fill();
        ctx.strokeStyle = b[0] > 0 ? "#b67d46" : "#2a718a";
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.fillStyle = "#324f62";
        ctx.beginPath();
        ctx.arc(a[0], a[1], 3, 0, 7);
        ctx.fill();
      });
    line(body([-0.15, 0, -0.05]), body([0.3, 0, -0.05]), "#344b60", 12);
    line(body([0.16, 0, -0.06]), body([0.42, 0, -0.06]), "#da9750", 6);
    if (Math.hypot(...state.wind) > 0.05) {
      const base = [p[0] - 2, p[1] - 2, 0.3],
        end = vec.add(base, vec.mul([state.wind[0], state.wind[1], 0], 0.3));
      line(base, end, "#748d75", 3);
      const ep = project(end);
      if (ep) {
        ctx.fillStyle = "#5f7960";
        ctx.font = "11px sans-serif";
        ctx.fillText(
          `風 ${Math.hypot(...state.wind).toFixed(1)} m/s`,
          ep[0] + 5,
          ep[1],
        );
      }
    }
  }
  const [cw, ch, cc] = resize($("chart"));
  cc.clearRect(0, 0, cw, ch);
  const max = Math.max(3, ...samples.flatMap((a) => a.slice(1))) * 1.1,
    tEnd = state?.time || 0;
  cc.font = "10px sans-serif";
  cc.fillStyle = "#84919c";
  cc.fillText(max.toFixed(1), cw - 25, 22);
  cc.fillText("0", cw - 15, ch - 4);
  cc.strokeStyle = "#e2e8ed";
  cc.beginPath();
  cc.moveTo(0, ch - 10);
  cc.lineTo(cw, ch - 10);
  cc.stroke();
  [1, 2].forEach((j) => {
    cc.beginPath();
    samples.forEach((a, i) => {
      const x = ((a[0] - (tEnd - 20)) / 20) * (cw - 30),
        y = ch - 10 - (a[j] / max) * (ch - 28);
      i ? cc.lineTo(x, y) : cc.moveTo(x, y);
    });
    cc.strokeStyle = j === 1 ? "#087e9b" : "#b4783b";
    cc.lineWidth = 1.8;
    cc.stroke();
  });
  requestAnimationFrame(draw);
}
api("/state").then(accept).catch(failure);
draw();
tick();
