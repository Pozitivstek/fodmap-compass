// Сканер штрихкодов: камера (BarcodeDetector или ZXing), фото или ввод цифр.
import { api } from "../api.js";
import { go, onLeave } from "../state.js";
import { haptic, html, mount } from "../ui.js";

const ZXING_URL = "https://cdn.jsdelivr.net/npm/@zxing/library@0.21.3/umd/index.min.js";
const ZXING_SRI = "sha384-BzBxP10ZE72aitqj5UMmUsbKFliP/DZqA8Wq+BNNhlIJDGoEd1tpkMYXOg9+n6sB";
const RESTART_DELAY_MS = 1500;
const FORMATS = ["ean_13", "ean_8", "upc_a", "upc_e"];
const DETECT_EVERY_MS = 250;

function loadScript(src) {
  return new Promise((resolve, reject) => {
    if (window.ZXing) return resolve();
    const script = document.createElement("script");
    script.src = src;
    script.integrity = ZXING_SRI;
    script.crossOrigin = "anonymous";
    script.onload = resolve;
    script.onerror = () => reject(new Error("Не удалось загрузить сканер"));
    document.head.appendChild(script);
  });
}

async function startNative(video, onCode) {
  const detector = new window.BarcodeDetector({ formats: FORMATS });
  const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
  video.srcObject = stream;
  await video.play();
  let alive = true;
  const loop = async () => {
    if (!alive) return;
    try {
      const codes = await detector.detect(video);
      if (codes.length) return onCode(codes[0].rawValue);
    } catch { /* кадр ещё не готов */ }
    setTimeout(loop, DETECT_EVERY_MS);
  };
  loop();
  return () => { alive = false; stream.getTracks().forEach((t) => t.stop()); };
}

async function startZxing(video, onCode) {
  await loadScript(ZXING_URL);
  const reader = new window.ZXing.BrowserMultiFormatReader();
  await reader.decodeFromConstraints({ video: { facingMode: "environment" } }, video, (result) => {
    if (result) onCode(result.getText());
  });
  return () => reader.reset();
}

export async function render(root) {
  mount(root, html`
    <header class="topbar"><div><h1>Сканер</h1><div class="sub">Штрихкод на упаковке → состав и вердикт</div></div></header>
    <div class="scanner"><video playsinline muted></video><div class="frame"></div><div class="laser"></div></div>
    <p class="center muted small" id="status">Наведите камеру на штрихкод</p>
    <label class="btn ghost block">📸 Сфотографировать штрихкод
      <input type="file" accept="image/*" capture="environment" id="photo" hidden></label>
    <form class="search" style="margin-top:12px" id="manual">
      <input id="code" inputmode="numeric" pattern="[0-9]*" maxlength="14" placeholder="Или введите цифры под штрихкодом">
      <button class="btn sm" type="submit">Найти</button></form>
    <p class="small muted center" style="margin-top:14px">Данные о товарах — из открытой базы Open Food Facts.</p>`);
  const status = root.querySelector("#status");
  const video = root.querySelector("video");
  let stop = null;
  let busy = false;
  let left = false;
  onLeave(() => { left = true; stop?.(); });

  async function startCamera() {
    if (left) return;
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error("no camera");
      stop = "BarcodeDetector" in window ? await startNative(video, lookup) : await startZxing(video, lookup);
      root.querySelector(".scanner").classList.remove("hidden");
    } catch {
      status.textContent = "Камера недоступна — сфотографируйте штрихкод или введите цифры";
      root.querySelector(".scanner").classList.add("hidden");
    }
  }

  async function lookup(code) {
    if (busy) return;
    busy = true;
    stop?.();
    haptic("success");
    status.textContent = `Ищу товар ${code}…`;
    try {
      const card = await api.get(`/api/foods/barcode/${encodeURIComponent(code)}`);
      go(`/food/${encodeURIComponent(card.ref)}`, { replace: true });
    } catch (error) {
      status.textContent = `${error.message}. Попробуйте другой товар.`;
      haptic("error");
      busy = false;
      setTimeout(startCamera, RESTART_DELAY_MS);
    }
  }

  root.querySelector("#manual").addEventListener("submit", (event) => {
    event.preventDefault();
    const code = root.querySelector("#code").value.replace(/\D/g, "");
    if (code.length >= 8) lookup(code);
    else status.textContent = "Штрихкод — это 8–14 цифр";
  });
  root.querySelector("#photo").addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    stop?.();
    status.textContent = "Распознаю фото…";
    const form = new FormData();
    form.append("photo", file);
    try {
      const card = await api.upload("/api/foods/barcode/photo", form);
      haptic("success");
      go(`/food/${encodeURIComponent(card.ref)}`, { replace: true });
    } catch (error) {
      status.textContent = error.message;
      haptic("error");
    }
  });

  startCamera();
}
