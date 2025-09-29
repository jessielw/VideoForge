import React from "react";

export default function TargetSection({
  outputPath,
  setOutputPath,
  container,
  setContainer,
  videoCodec,
  setVideoCodec,
  onStart,
  onReset,
}: {
  outputPath: string;
  setOutputPath: (v: string) => void;
  container: string;
  setContainer: (v: string) => void;
  videoCodec: string;
  setVideoCodec: (v: string) => void;
  onStart: () => void;
  onReset: () => void;
}): JSX.Element {
  return (
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
        <button onClick={onStart}>Start</button>
        <button onClick={onReset}>Reset</button>
      </div>
    </section>
  );
}
