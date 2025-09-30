import React, { useState } from "react";
import "./styles.css";
import Sidebar from "./Sidebar";
import InputSection from "./Input";
import TargetSection from "./Target";
import FileBrowserModal from "./FileBrowserModal";

const API = "http://127.0.0.1:8000";

export default function App(): JSX.Element {
  // Tab state
  const [activeTab, setActiveTab] = useState<string>("main");

  // Input box state
  const [inputPath, setInputPath] = useState<string>("");
  const [fileModalOpen, setFileModalOpen] = useState<boolean>(false);
  const [fileEntries, setFileEntries] = useState<any[] | null>(null);
  const [fileCurrent, setFileCurrent] = useState<string | null>(null);
  const [fileLoading, setFileLoading] = useState<boolean>(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const [fileDetails, setFileDetails] = useState<any>(null);

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
      </div>
    </div>
  );
}
