import React from "react";
import "./styles/input.css";

export default function InputSection({
  inputPath,
  setInputPath,
  openFileModal,
}: {
  inputPath: string;
  setInputPath: (v: string) => void;
  openFileModal: () => void;
}): JSX.Element {
  return (
    <section className="input-box" style={{ marginBottom: 12 }}>
      <h2>Input</h2>
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
  );
}
