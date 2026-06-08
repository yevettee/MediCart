"use strict";

// 이 파일은 브라우저에서 실행되는 dashboard 로직이다.
// Python dashboard_node.py와 HTTP API(/api/...) 및 SSE(/api/events)로 통신한다.
// 발표 때는 "화면 조작 -> fetch API -> Python -> ROS action" 순서로 설명하면 된다.

const $ = (selector) => document.querySelector(selector);
const format = (value) => Number.parseFloat(value.toFixed(3)).toString();
const radToDeg = (rad) => (rad * 180) / Math.PI;

// HTML 요소를 미리 찾아둔다. 아래 함수들은 이 요소들의 text/src/style을 바꿔 화면을 갱신한다.
const mapStage = $("#mapStage");
const mapWrap = $("#mapWrap");
const mapImage = $("#mapImage");
const markerLayer = $("#markerLayer");
const statusText = $("#statusText");
const poseText = $("#poseText");
const cameraText = $("#cameraText");
const rgbView = $("#rgbView");
const depthView = $("#depthView");
const logList = $("#logList");
const captureToggle = $("#captureToggle");

let mapConfig = null;
let targets = [];
let amrPose = null;
let captureBusy = false;
let captureCount = 0;
let captureEnabled = false;
let captureTimer = null;

function worldToPixel({ x, y }) {
  // ROS map frame의 실제 좌표(x/y)를 웹 지도 이미지 위 pixel 위치로 바꾼다.
  const dx = x - mapConfig.origin.x;
  const dy = y - mapConfig.origin.y;
  const cos = Math.cos(-mapConfig.origin.yaw);
  const sin = Math.sin(-mapConfig.origin.yaw);
  const mapX = (dx * cos - dy * sin) / mapConfig.resolution;
  const mapY = (dx * sin + dy * cos) / mapConfig.resolution;
  return { x: mapX, y: mapConfig.height - mapY };
}

function pixelToWorld(pixelX, pixelY) {
  // 사용자가 지도 이미지를 클릭한 pixel 위치를 ROS map frame 좌표로 되돌린다.
  // 현재 클릭 이동은 방향을 따로 드래그하지 않으므로 yaw는 0으로 시작한다.
  const mapX = pixelX * mapConfig.resolution;
  const mapY = (mapConfig.height - pixelY) * mapConfig.resolution;
  const cos = Math.cos(mapConfig.origin.yaw);
  const sin = Math.sin(mapConfig.origin.yaw);
  return {
    x: mapConfig.origin.x + mapX * cos - mapY * sin,
    y: mapConfig.origin.y + mapX * sin + mapY * cos,
    yaw: 0,
  };
}

function fitMap() {
  // 지도 원본 비율을 유지하면서 화면 카드 안에 최대한 크게 맞춘다.
  const bounds = mapWrap.getBoundingClientRect();
  const scale = Math.min(
    bounds.width / mapConfig.width,
    bounds.height / mapConfig.height,
  );
  mapStage.style.width = `${mapConfig.width * scale}px`;
  mapStage.style.height = `${mapConfig.height * scale}px`;
}

function renderMarkers() {
  // 기본 목적지 marker와 현재 AMR marker를 전부 다시 그린다.
  markerLayer.innerHTML = "";
  const samePlaceCounts = new Map();
  targets.forEach((target) => {
    const key = `${target.x.toFixed(2)},${target.y.toFixed(2)}`;
    const offsetIndex = samePlaceCounts.get(key) || 0;
    samePlaceCounts.set(key, offsetIndex + 1);
    addMarker(target, "target", offsetIndex);
  });
  if (amrPose) {
    addMarker({
      name: "AMR",
      x: amrPose.x,
      y: amrPose.y,
      yaw: amrPose.yaw,
      color: "#2f3440",
    }, "amr");
  }
}

function addMarker(target, type, offsetIndex = 0) {
  // marker 하나를 만든다. 목적지 marker는 클릭하면 sendGoal()로 이동 요청을 보낸다.
  const pixel = worldToPixel(target);
  const button = document.createElement("button");
  button.className = `marker marker-${type}`;
  button.type = "button";
  button.style.setProperty("--x", `${(pixel.x / mapConfig.width) * 100}%`);
  button.style.setProperty("--y", `${(pixel.y / mapConfig.height) * 100}%`);
  button.style.setProperty("--color", target.color || "#0f8b7b");
  button.style.setProperty("--yaw", `${-radToDeg(target.yaw || 0)}deg`);
  button.style.setProperty("--label-offset", `${offsetIndex * 24 - 12}px`);
  button.title = `${target.name}: ${format(target.x)}, ${format(target.y)}`;

  const label = document.createElement("span");
  label.textContent = target.name;
  button.append(label);

  if (type !== "amr") {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      sendGoal(target);
    });
  }
  markerLayer.append(button);
}

async function sendGoal(target) {
  // 목적지 클릭 -> POST /api/goals -> dashboard_node.py send_navigation_goal().
  // Python 쪽에서 최종적으로 Nav2 NavigateToPose action을 보낸다.
  statusText.textContent = `목표 전송: ${target.name}`;
  try {
    const response = await fetch("/api/goals", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: target.name,
        x: target.x,
        y: target.y,
        yaw: target.yaw || 0,
        dock_after: Boolean(target.dock_after),
      }),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      appendLog({
        level: "error",
        message: payload.message || "목표 전송 실패",
        time: new Date().toISOString(),
      });
    }
  } catch (error) {
    appendLog({
      level: "error",
      message: `서버 연결 실패: ${error.message}`,
      time: new Date().toISOString(),
    });
  }
}

async function runCommand(command) {
  // 상단 Dock/Undock/ROS Restart/Reboot/Shutdown 버튼 처리.
  // POST /api/commands로 보내면 Python이 ROS action 또는 SSH 명령을 실행한다.
  if (
    ["reboot", "shutdown"].includes(command) &&
    !window.confirm(`${command} 명령을 robot6에 실행할까요?`)
  ) {
    return;
  }

  try {
    const response = await fetch("/api/commands", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command }),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      appendLog({
        level: "error",
        message: payload.message || `${command} 실패`,
        time: new Date().toISOString(),
      });
    }
  } catch (error) {
    appendLog({
      level: "error",
      message: `명령 전송 실패: ${error.message}`,
      time: new Date().toISOString(),
    });
  }
}

function setCaptureEnabled(enabled) {
  // Capture ON이면 화면에 보이는 RGB/Depth 이미지를 주기적으로 서버에 저장한다.
  captureEnabled = enabled;
  captureToggle.classList.toggle("is-on", enabled);
  captureToggle.setAttribute("aria-pressed", String(enabled));
  captureToggle.textContent = enabled ? "Capture ON" : "Capture OFF";

  if (captureTimer) {
    window.clearInterval(captureTimer);
    captureTimer = null;
  }

  if (enabled) {
    captureCount = 0;
    cameraText.textContent = "Capture ON";
    captureTimer = window.setInterval(captureDisplayedImages, 750);
    captureDisplayedImages();
  } else {
    cameraText.textContent = "Capture OFF";
  }
}

async function captureDisplayedImages() {
  // 브라우저 img 태그에 표시된 이미지를 JPEG data URL로 바꿔 /api/captures에 전송한다.
  if (captureBusy || (!rgbView.src && !depthView.src)) {
    return;
  }

  captureBusy = true;
  try {
    const rgb = imageToDegradedJpeg(rgbView);
    const depth = imageToDegradedJpeg(depthView);
    if (!rgb && !depth) {
      return;
    }

    const response = await fetch("/api/captures", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rgb, depth }),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || "capture failed");
    }

    captureCount += 1;
    cameraText.textContent = `Capture ON · saved ${captureCount}`;
  } catch (error) {
    appendLog({
      level: "error",
      message: `캡쳐 저장 실패: ${error.message}`,
      time: new Date().toISOString(),
    });
  } finally {
    captureBusy = false;
  }
}

function imageToDegradedJpeg(image) {
  // 원본 topic 이미지를 그대로 저장하지 않고 브라우저에서 줄인 JPEG로 저장한다.
  // 저장 파일 크기를 줄이기 위한 처리다.
  if (!image.src || !image.complete || !image.naturalWidth) {
    return null;
  }

  const scale = 0.65;
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
  canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
  const context = canvas.getContext("2d");
  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = "low";
  context.drawImage(image, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.45);
}

function appendLog(event) {
  // SSE log 이벤트나 fetch 실패 메시지를 오른쪽 로그 패널에 한 줄 추가한다.
  const item = document.createElement("li");
  const time = document.createElement("time");
  const message = document.createElement("span");
  const stamp = event.time ? new Date(event.time) : new Date();
  item.className = `log-item log-${event.level || "info"}`;
  time.textContent = stamp.toLocaleTimeString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  message.textContent = event.message;
  item.append(time, message);
  logList.prepend(item);
  while (logList.children.length > 100) {
    logList.lastElementChild.remove();
  }
  statusText.textContent = event.message;
}

function connectEvents() {
  // Python의 /api/events SSE stream에 연결한다.
  // log/pose/rgb/depth/rgbd 이벤트를 받아 화면을 실시간 갱신한다.
  const events = new EventSource("/api/events");
  events.addEventListener("open", () => {
    statusText.textContent = "대시보드 연결됨";
  });
  events.addEventListener("log", (event) => appendLog(JSON.parse(event.data)));
  events.addEventListener("pose", (event) => {
    amrPose = JSON.parse(event.data);
    poseText.textContent = `AMR ${format(amrPose.x)}, ${format(amrPose.y)}, ${format(amrPose.yaw)}`;
    renderMarkers();
  });
  events.addEventListener("rgbd", (event) => {
    const frame = JSON.parse(event.data);
    rgbView.src = frame.rgb;
    depthView.src = frame.depth;
    cameraText.textContent = "RGB-D sync 10fps";
  });
  events.addEventListener("rgb", (event) => {
    const frame = JSON.parse(event.data);
    rgbView.src = frame.rgb;
    cameraText.textContent = "RGB stream 10fps";
  });
  events.addEventListener("depth", (event) => {
    const frame = JSON.parse(event.data);
    depthView.src = frame.depth;
    cameraText.textContent = "Depth stream 10fps";
  });
  events.addEventListener("error", () => {
    statusText.textContent = "이벤트 재연결 중";
  });
}

async function load() {
  // 페이지가 처음 열릴 때 실행되는 초기화 함수.
  // map metadata, 기본 목적지, 현재 상태를 받아온 뒤 SSE 연결을 시작한다.
  const response = await fetch("/api/config");
  const config = await response.json();
  mapConfig = config.map;
  targets = config.targets;
  amrPose = config.status.amr_pose;
  mapImage.src = mapConfig.image;
  mapImage.addEventListener("load", () => {
    fitMap();
    renderMarkers();
  });
  statusText.textContent = `${config.status.map_frame} · ${config.status.action_name}`;
  connectEvents();
}

mapStage.addEventListener("click", (event) => {
  // 사용자가 지도 빈 곳을 클릭하면 pixel 좌표를 world 좌표로 바꿔 바로 이동 goal을 보낸다.
  if (!mapConfig) {
    return;
  }
  const bounds = mapStage.getBoundingClientRect();
  const pixelX = ((event.clientX - bounds.left) / bounds.width) * mapConfig.width;
  const pixelY = ((event.clientY - bounds.top) / bounds.height) * mapConfig.height;
  const world = pixelToWorld(pixelX, pixelY);
  sendGoal({ name: "Map Point", ...world, color: "#6f4bb5" });
});

document.querySelectorAll("[data-command]").forEach((button) => {
  // HTML의 data-command 값이 command 이름이다. 버튼을 늘릴 때 HTML만 맞추면 된다.
  button.addEventListener("click", () => runCommand(button.dataset.command));
});
captureToggle.addEventListener("click", () => {
  setCaptureEnabled(!captureEnabled);
});
$("#clearLogs").addEventListener("click", () => {
  logList.innerHTML = "";
});
window.addEventListener("resize", () => {
  if (mapConfig) {
    fitMap();
    renderMarkers();
  }
});

load();
