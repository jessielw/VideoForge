import React, { useState } from 'react'
import './styles.css'

export default function App(): JSX.Element {
  // Input box state
  const [inputPath, setInputPath] = useState<string>('')
  const [inputOpened, setInputOpened] = useState<boolean>(false)

  // Target box state
  const [outputPath, setOutputPath] = useState<string>('')
  const [container, setContainer] = useState<string>('mkv')
  const [videoCodec, setVideoCodec] = useState<string>('x264')

  return (
    <div className="app">
      <h1>Video Forge — Minimal Editor</h1>

      <section className="box" style={{ marginBottom: 12 }}>
        <h2 style={{ margin: '6px 0' }}>Input</h2>
        <div className="form">
          <input
            placeholder="Path to source file or script"
            value={inputPath}
            onChange={(e) => setInputPath(e.target.value)}
          />
          <button onClick={() => setInputOpened(true)}>Browse</button>
          <button onClick={() => alert('Probe not implemented in minimal UI')}>Probe</button>
        </div>
        <div style={{ color: '#666', fontSize: 13 }}>{inputOpened ? 'Browser opened (placeholder)' : 'No file opened'}</div>
      </section>

      <section className="box">
        <h2 style={{ margin: '6px 0' }}>Target</h2>
        <div className="form">
          <input
            placeholder="Output path (e.g. output.mkv)"
            value={outputPath}
            onChange={(e) => setOutputPath(e.target.value)}
          />
          <select value={container} onChange={(e) => setContainer(e.target.value)}>
            <option value="mkv">MKV</option>
            <option value="mp4">MP4</option>
            <option value="mov">MOV</option>
          </select>
          <select value={videoCodec} onChange={(e) => setVideoCodec(e.target.value)}>
            <option value="x264">x264</option>
            <option value="x265">x265</option>
            <option value="nvenc_h264">NVENC H.264</option>
          </select>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={() => alert('Start encode - not wired')}>Start</button>
          <button onClick={() => { setOutputPath(''); setInputPath('') }}>Reset</button>
        </div>
      </section>
    </div>
  )
}
