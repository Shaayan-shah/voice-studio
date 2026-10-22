const textArea = document.querySelector("#script-text");
const fileInput = document.querySelector("#file-input");
const dropzone = document.querySelector("#dropzone");
const engineSelect = document.querySelector("#engine-select");
const languageSelect = document.querySelector("#language-select");
const voiceSelect = document.querySelector("#voice-select");
const voiceSearch = document.querySelector("#voice-search");
const generateButton = document.querySelector("#generate-button");
const statusMessage = document.querySelector("#status-message");
const playerPanel = document.querySelector("#player-panel");
const audioPlayer = document.querySelector("#audio-player");
const downloadLink = document.querySelector("#download-link");
const formatSelect = document.querySelector("#format-select");
const toneSelect = document.querySelector("#tone-select");

const tones = {
  neutral: { rate: 0, pitch: 0, volume: 0 },
  warm: { rate: -4, pitch: -2, volume: 2 },
  calm: { rate: -12, pitch: -3, volume: -2 },
  bright: { rate: 5, pitch: 5, volume: 1 },
  energetic: { rate: 12, pitch: 4, volume: 3 },
  serious: { rate: -5, pitch: -6, volume: 0 },
};

let voices = [];
let audioUrl = null;
let audioBaseName = "voice-over";
let voiceRequest = 0;

function setStatus(message, isError = false) {
  statusMessage.textContent = message;
  statusMessage.classList.toggle("is-error", isError);
}

function updateCharacterCount() {
  const length = textArea.value.length;
  document.querySelector("#character-count").textContent =
    `${length.toLocaleString()} characters`;
  generateButton.disabled =
    !voices.length || !voiceSelect.value || !textArea.value.trim();
}

function setSlider(name, value) {
  const slider = document.querySelector(`#${name}-range`);
  slider.value = value;
  slider.dispatchEvent(new Event("input", { bubbles: true }));
}

function updateSliderOutput(name) {
  const slider = document.querySelector(`#${name}-range`);
  const value = Number(slider.value);
  const suffix = name === "pitch" ? " Hz" : "%";
  document.querySelector(`#${name}-value`).textContent =
    `${value > 0 ? "+" : ""}${value}${suffix}`;
}

function voiceLabel(voice) {
  const gender = voice.Gender ? ` · ${voice.Gender}` : "";
  return `${voice.FriendlyName || voice.ShortName}${gender}`;
}

function renderVoices() {
  const language = languageSelect.value;
  const query = voiceSearch.value.trim().toLocaleLowerCase();
  const filtered = voices.filter((voice) =>
    voice.Locale === language &&
    `${voice.FriendlyName} ${voice.ShortName} ${voice.Gender}`
      .toLocaleLowerCase()
      .includes(query)
  );
  const previous = voiceSelect.value;
  voiceSelect.replaceChildren();
  for (const voice of filtered) {
    const option = document.createElement("option");
    option.value = voice.ShortName;
    option.textContent = voiceLabel(voice);
    voiceSelect.append(option);
  }
  voiceSelect.disabled = filtered.length === 0;
  if (filtered.some((voice) => voice.ShortName === previous)) {
    voiceSelect.value = previous;
  }
  const count = voices.filter((voice) => voice.Locale === language).length;
  document.querySelector("#voice-meta").textContent = filtered.length
    ? `${count} ${count === 1 ? "speaker" : "speakers"} available`
    : "No speakers found. Try a different search.";
}

function populateLanguages() {
  const locales = [...new Set(voices.map((voice) => voice.Locale))]
    .filter(Boolean)
    .sort((left, right) => left.localeCompare(right));
  languageSelect.replaceChildren();
  for (const locale of locales) {
    const option = document.createElement("option");
    option.value = locale;
    const voice = voices.find((item) => item.Locale === locale);
    option.textContent = voice?.LocaleName
      ? `${voice.LocaleName} (${locale})`
      : locale;
    languageSelect.append(option);
  }
  const preferred = locales.find((locale) => locale.startsWith("en-US")) ||
    locales.find((locale) => locale.startsWith("en-")) ||
    locales[0];
  if (preferred) languageSelect.value = preferred;
  languageSelect.disabled = locales.length === 0;
  voiceSearch.disabled = locales.length === 0;
  renderVoices();
  updateCharacterCount();
}

async function loadVoices() {
  const requestNumber = ++voiceRequest;
  const engine = engineSelect.value;
  voices = [];
  languageSelect.disabled = true;
  voiceSelect.disabled = true;
  voiceSearch.disabled = true;
  updateCharacterCount();
  document.querySelector("#voice-meta").textContent = "Loading speakers…";
  document.querySelector("#engine-hint").textContent = engine === "offline"
    ? "Runs locally with voices installed on this PC. No internet or usage quota."
    : "Uses Microsoft Edge neural voices. Internet required; service availability may vary.";
  document.querySelector("#privacy-hint").textContent = engine === "offline"
    ? "Documents and voice generation stay on this device."
    : "Documents are read on this device. The text is sent to Microsoft to create audio.";
  document.querySelector("#pitch-hint").textContent = engine === "offline"
    ? "Pitch adjustment is available with online neural voices."
    : "Fine-tune the height of the speaker's voice.";
  document.querySelector("#pitch-range").disabled = engine === "offline";
  try {
    const response = await fetch(`/api/voices?engine=${encodeURIComponent(engine)}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not load speakers.");
    if (requestNumber !== voiceRequest) return;
    voices = data.voices;
    populateLanguages();
    setStatus("");
    if (!voices.length) {
      document.querySelector("#voice-meta").textContent = engine === "offline"
        ? "No Windows speech voices are installed. Add a voice pack in Windows Settings."
        : "No online speakers were returned.";
    }
  } catch (error) {
    if (requestNumber !== voiceRequest) return;
    languageSelect.replaceChildren(new Option("Unavailable", ""));
    voiceSelect.replaceChildren(new Option("Unable to load speakers", ""));
    document.querySelector("#voice-meta").textContent = error.message;
    setStatus(engine === "offline"
      ? "Could not read Windows speech voices. Check that Windows speech components are available."
      : "Could not reach the online voice service. Check your internet connection.", true);
  }
}

async function readFile(file) {
  if (file.size > 20 * 1024 * 1024) {
    throw new Error("This file is larger than the 20 MB limit.");
  }
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  const chunkSize = 16_384;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  const response = await fetch("/api/extract", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename: file.name, content: btoa(binary) }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Could not read this file.");
  textArea.value = data.text;
  audioBaseName = file.name.replace(/\.[^.]+$/, "").trim() || "voice-over";
  document.querySelector("#file-status").textContent = `Imported ${data.filename}`;
  setStatus("Document text is ready to use.");
  updateCharacterCount();
}

function handleDroppedText(event) {
  const text = event.dataTransfer?.getData("text/plain");
  if (!text) return false;
  textArea.value = text;
  document.querySelector("#file-status").textContent = "Text added from drop";
  updateCharacterCount();
  setStatus("Text is ready to use.");
  return true;
}

function downloadName(extension) {
  const safeName = audioBaseName
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, "-")
    .replace(/[. ]+$/, "")
    .slice(0, 90);
  return `${safeName || "voice-over"}.${extension}`;
}

function makeWav(audioBuffer) {
  const channels = audioBuffer.numberOfChannels;
  const frameCount = audioBuffer.length;
  const bytesPerSample = 2;
  const blockAlign = channels * bytesPerSample;
  const buffer = new ArrayBuffer(44 + frameCount * blockAlign);
  const view = new DataView(buffer);
  const writeString = (offset, value) => {
    for (let index = 0; index < value.length; index += 1) {
      view.setUint8(offset + index, value.charCodeAt(index));
    }
  };
  writeString(0, "RIFF");
  view.setUint32(4, 36 + frameCount * blockAlign, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, channels, true);
  view.setUint32(24, audioBuffer.sampleRate, true);
  view.setUint32(28, audioBuffer.sampleRate * blockAlign, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, 16, true);
  writeString(36, "data");
  view.setUint32(40, frameCount * blockAlign, true);

  const channelData = Array.from({ length: channels }, (_, channel) =>
    audioBuffer.getChannelData(channel)
  );
  let offset = 44;
  for (let frame = 0; frame < frameCount; frame += 1) {
    for (let channel = 0; channel < channels; channel += 1) {
      const sample = Math.max(-1, Math.min(1, channelData[channel][frame]));
      view.setInt16(
        offset,
        sample < 0 ? sample * 0x8000 : sample * 0x7fff,
        true
      );
      offset += bytesPerSample;
    }
  }
  return new Blob([buffer], { type: "audio/wav" });
}

async function presentAudio(mp3Blob, extension) {
  let outputBlob = mp3Blob;
  if (extension === "wav" && mp3Blob.type !== "audio/wav") {
    setStatus("Preparing WAV download…");
    const context = new AudioContext();
    try {
      const audioBuffer = await context.decodeAudioData(
        await mp3Blob.arrayBuffer()
      );
      outputBlob = makeWav(audioBuffer);
    } finally {
      await context.close();
    }
  }

  if (audioUrl) URL.revokeObjectURL(audioUrl);
  audioUrl = URL.createObjectURL(outputBlob);
  const filename = downloadName(extension);
  audioPlayer.src = audioUrl;
  downloadLink.href = audioUrl;
  downloadLink.download = filename;
  document.querySelector("#audio-filename").textContent = filename;
  playerPanel.hidden = false;
  playerPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  setStatus("Your audio is ready.");
}

async function generateAudio() {
  if (!textArea.value.trim()) {
    setStatus("Add some text before creating audio.", true);
    return;
  }
  generateButton.disabled = true;
  document.querySelector("#generate-label").textContent = "Creating audio…";
  setStatus("Generating your voice-over. Larger scripts take a little longer.");

  const tone = tones[toneSelect.value];
  const payload = {
    engine: engineSelect.value,
    text: textArea.value,
    voice: voiceSelect.value,
    format: formatSelect.value,
    rate: Number(document.querySelector("#rate-range").value) + tone.rate,
    pitch: engineSelect.value === "offline"
      ? 0
      : Number(document.querySelector("#pitch-range").value) + tone.pitch,
    volume: Number(document.querySelector("#volume-range").value) + tone.volume,
  };
  payload.rate = Math.max(-30, Math.min(30, payload.rate));
  payload.pitch = Math.max(-25, Math.min(25, payload.pitch));
  payload.volume = Math.max(-20, Math.min(20, payload.volume));

  try {
    const response = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.error || "Could not generate audio.");
    }
    await presentAudio(await response.blob(), payload.format);
  } catch (error) {
    setStatus(error.message || (engineSelect.value === "offline"
      ? "Could not generate audio. Check the Windows voice and MP3 encoder setup."
      : "Could not generate audio. Check your connection and try again."), true);
  } finally {
    document.querySelector("#generate-label").textContent = "Create audio";
    updateCharacterCount();
  }
}

document.querySelector("#browse-button").addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", async () => {
  const [file] = fileInput.files;
  if (!file) return;
  setStatus("Reading document…");
  try {
    await readFile(file);
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    fileInput.value = "";
  }
});

for (const eventName of ["dragenter", "dragover"]) {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.add("is-dragging");
  });
}
for (const eventName of ["dragleave", "drop"]) {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.remove("is-dragging");
  });
}
dropzone.addEventListener("drop", async (event) => {
  if (handleDroppedText(event)) return;
  const [file] = event.dataTransfer?.files || [];
  if (!file) return;
  setStatus("Reading document…");
  try {
    await readFile(file);
  } catch (error) {
    setStatus(error.message, true);
  }
});

textArea.addEventListener("input", updateCharacterCount);
document.querySelector("#clear-button").addEventListener("click", () => {
  textArea.value = "";
  document.querySelector("#file-status").textContent = "";
  setStatus("");
  updateCharacterCount();
  textArea.focus();
});
languageSelect.addEventListener("change", renderVoices);
voiceSearch.addEventListener("input", renderVoices);
engineSelect.addEventListener("change", loadVoices);
generateButton.addEventListener("click", generateAudio);
toneSelect.addEventListener("change", () => {
  for (const name of ["rate", "pitch", "volume"]) setSlider(name, 0);
});
for (const name of ["rate", "pitch", "volume"]) {
  document.querySelector(`#${name}-range`).addEventListener("input", () => updateSliderOutput(name));
  updateSliderOutput(name);
}
document.querySelector("#pitch-range").disabled = engineSelect.value === "offline";
window.addEventListener("beforeunload", () => {
  if (audioUrl) URL.revokeObjectURL(audioUrl);
});

updateCharacterCount();
loadVoices();
