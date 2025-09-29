import React, { useState } from "react";
import "./styles.css";

const API = "http://127.0.0.1:8000";

export default function App(): JSX.Element {
  // Input box state
  const [inputPath, setInputPath] = useState<string>("");
  const [fileModalOpen, setFileModalOpen] = useState<boolean>(false);
  const [fileEntries, setFileEntries] = useState<any[] | null>(null);
  const [fileCurrent, setFileCurrent] = useState<string | null>(null);
  const [fileLoading, setFileLoading] = useState<boolean>(false);
  const [fileError, setFileError] = useState<string | null>(null);

  // Target box state
  const [outputPath, setOutputPath] = useState<string>("");
  const [container, setContainer] = useState<string>("mkv");
  const [videoCodec, setVideoCodec] = useState<string>("x264");

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
  function selectFile(path: string) {
    setInputPath(path);
    setFileModalOpen(false);
  }

  // Go up one directory
  function goUp() {
    if (!fileCurrent) return;
    const parts = fileCurrent.split(/\\|\//);
    if (parts.length <= 1) return;
    const up = parts.slice(0, -1).join("/");
    drill(up);
  }

  return (
    <div className="app">
      <h1>Video Forge — Minimal Editor</h1>

      <section className="box" style={{ marginBottom: 12 }}>
        <h2 style={{ margin: "6px 0" }}>Input</h2>
        <div className="form">
          <input
            placeholder="Path to source file or script"
            value={inputPath}
            onChange={(e) => setInputPath(e.target.value)}
            readOnly
          />
          <button onClick={openFileModal}>Browse</button>
          <button onClick={() => alert("Probe not implemented in minimal UI")}>
            Probe
          </button>
        </div>
      </section>

      <section className="box">
        <h2 style={{ margin: "6px 0" }}>Target</h2>
        <div className="form">
          <input
            placeholder="Output path (e.g. output.mkv)"
            value={outputPath}
            onChange={(e) => setOutputPath(e.target.value)}
          />
          <select
            value={container}
            onChange={(e) => setContainer(e.target.value)}
          >
            <option value="mkv">MKV</option>
            <option value="mp4">MP4</option>
            <option value="mov">MOV</option>
          </select>
          <select
            value={videoCodec}
            onChange={(e) => setVideoCodec(e.target.value)}
          >
            <option value="x264">x264</option>
            <option value="x265">x265</option>
            <option value="nvenc_h264">NVENC H.264</option>
          </select>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => alert("Start encode - not wired")}>
            Start
          </button>
          <button
            onClick={() => {
              setOutputPath("");
              setInputPath("");
            }}
          >
            Reset
          </button>
        </div>
      </section>

      {/* Minimal modal file selector */}
      {fileModalOpen && (
        <div
          style={{
            position: "fixed",
            left: 0,
            top: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0,0,0,0.15)",
            zIndex: 1000,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <div
            style={{
              background: "white",
              // minWidth: 340,
              width: "80%",
              padding: 18,
              borderRadius: 8,
              boxShadow: "0 2px 12px #0002",
              height: "80%",
              overflowY: "auto",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <strong>File Browser</strong>
              <button onClick={() => setFileModalOpen(false)}>Close</button>
            </div>
            <div style={{ margin: "10px 0", fontSize: 13, color: "#666" }}>
              {fileCurrent ? (
                <span>Current: {fileCurrent}</span>
              ) : (
                <span>Roots</span>
              )}
              {fileCurrent && (
                <button style={{ marginLeft: 12 }} onClick={goUp}>
                  Up
                </button>
              )}
            </div>
            {fileLoading ? (
              <div>Loading...</div>
            ) : fileError ? (
              <div style={{ color: "red" }}>{fileError}</div>
            ) : (
              <ul style={{ listStyle: "none", padding: 0 }}>
                {fileEntries &&
                  fileEntries.map((e: any) => (
                    <li
                      key={e.normalized || e.name}
                      style={{ margin: "4px 0" }}
                    >
                      {e.is_dir ? "📁" : "📄"}{" "}
                      <a
                        href="#"
                        style={{
                          color: e.is_dir ? "#0077cc" : "#222",
                          textDecoration: "none",
                        }}
                        onClick={(ev) => {
                          ev.preventDefault();
                          if (e.is_dir) drill(e.normalized);
                          else selectFile(e.normalized);
                        }}
                      >
                        {e.name}
                      </a>
                    </li>
                  ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
