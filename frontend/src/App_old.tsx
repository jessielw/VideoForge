import React, { useState } from "react";
import MainLayout from "./components/Layout/MainLayout";
import FileSelector from "./components/Source/FileSelector";
import MediaInfoPanel from "./components/Source/MediaInfoPanel";
import ScriptEditor from "./components/Processing/ScriptEditor";
import FilterPanel from "./components/Processing/FilterPanel";
import FramePreview from "./components/Processing/FramePreview";
import TargetSection from "./components/Target";
import FileBrowserModal from "./components/FileBrowserModal";

import "./styles/styles.css";

const API = "http://127.0.0.1:8000";

export default function App(): JSX.Element {
  // Tab state
  const [activeTab, setActiveTab] = useState<string>("source");

  // Input box state
  const [inputPath, setInputPath] = useState<string>("");
  const [fileModalOpen, setFileModalOpen] = useState<boolean>(false);
  const [fileEntries, setFileEntries] = useState<any[] | null>(null);
  const [fileCurrent, setFileCurrent] = useState<string | null>(null);
  const [fileLoading, setFileLoading] = useState<boolean>(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const [fileDetails, setFileDetails] = useState<any>(null);

  // Script state
  const [script, setScript] = useState<string>("");

  // Target box state
  const [outputPath, setOutputPath] = useState<string>("");
  const [container, setContainer] = useState<string>("mkv");
  const [videoCodec, setVideoCodec] = useState<string>("x264");

  // Indexing state
  const [indexing, setIndexing] = useState(false);
  const [indexInfo, setIndexInfo] = useState<any>(null);
  const [selectedFrame, setSelectedFrame] = useState<number>(0);
  const [frameImage, setFrameImage] = useState<string | null>(null);
  const [frameLoading, setFrameLoading] = useState<boolean>(false);

  // Open file browser modal and load roots
  async function openFileModal() {
    setFileModalOpen(true);
    setFileLoading(true);
    setFileError(null);
    setFileCurrent(null);
    try {
      const res = await fetch(`${API}/api/list`);
      const j = await res.json();
      if (j.ok) {
        setFileEntries(j.entries);
        setFileCurrent(j.path || null);
      } else {
        setFileError(j.reason || "Failed to list roots");
        setFileEntries([]);
      }
    } catch (e) {
      setFileError(String(e));
      setFileEntries([]);
    } finally {
      setFileLoading(false);
    }
  }

  // Drill into a folder
  async function drill(path: string) {
    setFileLoading(true);
    setFileError(null);
    try {
      const res = await fetch(
        `${API}/api/list?path=${encodeURIComponent(path)}`
      );
      const j = await res.json();
      if (j.ok) {
        setFileEntries(j.entries);
        setFileCurrent(j.path || null);
      } else {
        setFileError(j.reason || "Failed to list directory");
        setFileEntries([]);
      }
    } catch (e) {
      setFileError(String(e));
      setFileEntries([]);
    } finally {
      setFileLoading(false);
    }
  }

  // Select a file
  async function selectFile(path: string) {
    setInputPath(path);
    setFileModalOpen(false);
    // Fetch details from backend
    try {
      const res = await fetch(
        `${API}/api/details?path=${encodeURIComponent(path)}`
      );
      const details = await res.json();
      setFileDetails(details);
    } catch (e) {
      setFileDetails({ error: "Failed to load details" });
    }

    // Now index the file
    setIndexing(true);  
    console.log("Indexing file:", path);
    const indexResp = await fetch(`${API}/api/index`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    const indexData = await indexResp.json();
    console.log("Index data:", indexData);
    setIndexInfo(indexData);
    setIndexing(false);
  }

  // Go up one directory
  function goUp() {
    if (!fileCurrent) return;
    const parts = fileCurrent.split(/\\|\//);
    if (parts.length <= 1) return;
    const up = parts.slice(0, -1).join("/");
    drill(up);
  }

  function handleStart() {
    alert("Start encode - not wired");
  }
  function handleReset() {
    setOutputPath("");
    setInputPath("");
  }

  // Fetch frame image from backend
  async function fetchFrameImage(frame: number) {
    if (!inputPath) return;
    setFrameLoading(true);
    try {
      const resp = await fetch(`${API}/api/frame?path=${encodeURIComponent(inputPath)}&frame=${frame}`);
      if (resp.ok) {
        const blob = await resp.blob();
        setFrameImage(URL.createObjectURL(blob));
      } else {
        setFrameImage(null);
      }
    } catch {
      setFrameImage(null);
    } finally {
      setFrameLoading(false);
    }
  }

  // Add effect to fetch frame image when selectedFrame changes and crop dialog is open
  React.useEffect(() => {
    if (showCrop && indexInfo?.ok) {
      const handle = setTimeout(() => {
        fetchFrameImage(selectedFrame);
      }, 300); // 300ms debounce
      return () => clearTimeout(handle);
    }
  }, [showCrop, selectedFrame, indexInfo?.ok]);

  return (
    <div
      className="app"
      style={{
        display: "flex",
        height: "100vh",
        width: "100vw",
        overflow: "hidden",
      }}
    >
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} />
      <div
        style={{
          flex: 1,
          background: "#fff",
          margin: 0,
          padding: 0,
          boxSizing: "border-box",
          height: "100vh",
          overflow: "auto",
        }}
      >
        <div style={{ padding: 32, minHeight: "100vh" }}>
          {activeTab === "main" && (
            <>
              <InputSection
                inputPath={inputPath}
                setInputPath={setInputPath}
                openFileModal={openFileModal}
                fileDetails={fileDetails}
              />
              <TargetSection
                outputPath={outputPath}
                setOutputPath={setOutputPath}
                container={container}
                setContainer={setContainer}
                videoCodec={videoCodec}
                setVideoCodec={setVideoCodec}
                onStart={handleStart}
                onReset={handleReset}
              />
              {/* Set Crop button under target file section */}
              {indexInfo?.ok && (
                <button style={{ marginTop: 16 }} onClick={() => setShowCrop(true)}>
                  Set Crop
                </button>
              )}
            </>
          )}
          {activeTab === "settings" && (
            <div>
              <h2>Settings</h2>
              <p>Settings UI goes here.</p>
            </div>
          )}
          {activeTab === "jobs" && (
            <div>
              <h2>Jobs</h2>
              <p>Jobs UI goes here.</p>
            </div>
          )}
        </div>
        {/* Minimal modal file selector */}
        {fileModalOpen && (
          <FileBrowserModal
            fileCurrent={fileCurrent}
            goUp={goUp}
            fileLoading={fileLoading}
            fileError={fileError}
            fileEntries={fileEntries}
            drill={drill}
            selectFile={selectFile}
            onClose={() => setFileModalOpen(false)}
          />
        )}
        {/* Indexing modal overlay */}
        {indexing && (
          <div
            style={{
              position: "fixed",
              top: 0,
              left: 0,
              width: "100vw",
              height: "100vh",
              background: "rgba(0,0,0,0.5)",
              zIndex: 9999,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <div
              style={{
                background: "#fff",
                padding: "32px 48px",
                borderRadius: 8,
                boxShadow: "0 2px 16px rgba(0,0,0,0.2)",
                textAlign: "center",
              }}
            >
              <h2>Indexing file...</h2>
              <p>Please wait, this may take a moment.</p>
            </div>
          </div>
        )}
        {/* Show index info after indexing is complete */}
        {!indexing && indexInfo?.ok && (
          <button onClick={() => setShowCrop(true)}>
            Open Cropping Dialog
          </button>
        )}
        {/* Crop dialog for setting video crop */}
        {showCrop && (
          <div className="crop-dialog">
            <h3>Crop Dialog</h3>
            <p>Frame count: {indexInfo.frame_count}</p>
            <p>
              Resolution: {indexInfo.width}x{indexInfo.height}
            </p>
            {/* Frame slider */}
            <input
              type="range"
              min={0}
              max={indexInfo.frame_count - 1}
              value={selectedFrame}
              onChange={e => setSelectedFrame(Number(e.target.value))}
              style={{ width: 400 }}
            />
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <div>Frame: {selectedFrame}</div>
              {frameLoading && (
                <span className="spinner" style={{ display: "inline-block", width: 24, height: 24, border: "4px solid #ccc", borderTop: "4px solid #333", borderRadius: "50%", animation: "spin 1s linear infinite" }}></span>
              )}
            </div>
            {/* Display frame image (always show last loaded image) */}
            {frameImage ? (
              <img src={frameImage} alt={`Frame ${selectedFrame}`} style={{ maxWidth: "100%", maxHeight: 400, margin: "16px 0" }} />
            ) : (
              <div style={{ margin: "16px 0" }}>No image available</div>
            )}
            <button onClick={() => setShowCrop(false)}>Close</button>
          </div>
        )}
      </div>
    </div>
  );
}

/* Add spinner animation to global styles */
// In your CSS file (styles.css), add:
// @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
