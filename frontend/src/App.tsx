import React, { useState } from 'react';
import MainLayout from './components/Layout/MainLayout';
import FileSelector from './components/Source/FileSelector';
import MediaInfoPanel from './components/Source/MediaInfoPanel';
import ScriptEditor from './components/Processing/ScriptEditor';
import FilterPanel from './components/Processing/FilterPanel';
import FramePreview from './components/Processing/FramePreview';
import TargetSection from './components/Target';
import FileBrowserModal from './components/FileBrowserModal';
import ProbeFailureModal from './components/Source/ProbeFailureModal';
import GlobalOverlay from './components/GlobalOverlay';
import { useOverlay } from './context/OverlayContext';
import './styles/index.css';

const API = 'http://127.0.0.1:8000';

export default function App(): JSX.Element {
  const overlay = useOverlay();

  // Tab state
  const [activeTab, setActiveTab] = useState<string>('source');

  // Input state
  const [inputPath, setInputPath] = useState<string>('');
  const [fileModalOpen, setFileModalOpen] = useState<boolean>(false);
  const [fileEntries, setFileEntries] = useState<any[] | null>(null);
  const [fileCurrent, setFileCurrent] = useState<string | null>(null);
  const [fileLoading, setFileLoading] = useState<boolean>(false);
  const [fileError, setFileError] = useState<string | null>(null);

  // Script state
  const [script, setScript] = useState<string>('');

  // Target state
  const [outputPath, setOutputPath] = useState<string>('');
  const [container, setContainer] = useState<string>('mkv');
  const [videoCodec, setVideoCodec] = useState<string>('x264');

  // Indexing state
  const [indexing, setIndexing] = useState(false);
  const [indexInfo, setIndexInfo] = useState<any>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  // Preview trigger (increment to tell FramePreview to fetch new frames)
  const [previewVersion, setPreviewVersion] = useState(0);
  // Track last path we've indexed via Apply/auto-index so we don't re-index repeatedly
  const [lastIndexedPath, setLastIndexedPath] = useState<string | null>(null);
  // Processing reset signal (increment to force children to reset)
  const [processingResetVersion, setProcessingResetVersion] = useState(0);

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
        setFileError(j.reason || 'Failed to list roots');
      }
    } catch (err) {
      setFileError('Network error');
    } finally {
      setFileLoading(false);
    }
  }

  // Navigate file browser
  async function drill(path: string) {
    setFileLoading(true);
    setFileError(null);
    try {
      const res = await fetch(`${API}/api/list?path=${encodeURIComponent(path)}`);
      const j = await res.json();
      if (j.ok) {
        setFileEntries(j.entries);
        setFileCurrent(j.path || path);
      } else {
        setFileError(j.reason || 'Failed to list directory');
      }
    } catch (err) {
      setFileError('Network error');
    } finally {
      setFileLoading(false);
    }
  }

  // Select file from browser
  async function selectFile(path: string) {
    // When a new source is selected, fully reset processing widget state
    // so that the preview/frame and script template return to defaults.
    setProcessingResetVersion(v => v + 1);
    setInputPath(path);
    setFileModalOpen(false);
    // Fetch MediaInfo/index info for UI immediately on selection
    try {
      await indexFile(path);
    } catch (e) {
      console.error('Index on select failed:', e);
    }
  }

  // Index the selected file
  async function indexFile(path: string) {
    setIndexing(true);
    overlay.show({
      type: 'indexing',
      message: 'Please wait while the video is being analyzed. This operation locks the UI.',
    });
    console.log('Indexing file:', path);
    try {
      const indexResp = await fetch(`${API}/api/mediainfo`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      });
      const indexData = await indexResp.json();
      console.log('Index data:', indexData);
      setIndexInfo(indexData);

      return indexData;

      //       // Generate basic script template
      //       if (indexData.ok) {
      //         const template = `import vapoursynth as vs
      // core = vs.core

      // # Load source
      // clip = core.lsmas.LWLibavSource(r'${path.replace(/\\/g, '\\\\')}')

      // # Add your filters here
      // `;
      //         setScript(template);
      //       }
    } catch (error) {
      console.error('Failed to index file:', error);
      return { ok: false, reason: String(error) };
    } finally {
      setIndexing(false);
      overlay.hide();
    }
  }

  // Go up one directory
  function goUp() {
    if (!fileCurrent) return;
    const parts = fileCurrent.split(/\\|\//);
    if (parts.length <= 1) return;
    const up = parts.slice(0, -1).join('/');
    drill(up);
  }

  // Handle filter addition from preset panel
  const handleFilterAdd = (code: string) => {
    const newScript = script ? `${script}\n${code}` : code;
    setScript(newScript);
  };

  // Handle script validation
  const handleScriptValidate = () => {
    // Validation logic is handled inside ScriptEditorRefactored
  };

  // Handle script application (refresh preview)
  const handleScriptApply = async () => {
    // Probe the selected file via VapourSynth (frame/fps/size). This is the Apply action.
    if (!inputPath) return;
    setIndexing(true);
    overlay.show({
      type: 'indexing',
      message: 'Analyzing video with VapourSynth...',
    });
    try {
      const resp = await fetch(`${API}/api/vs/probe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: inputPath }),
      });
      const data = await resp.json();
      console.log('Probe data:', data);
      // The probe endpoint returns vapoursynth/probe-only data. Don't overwrite
      // the full mediainfo previously fetched by indexFile — merge the
      // vapoursynth/probe result into the existing indexInfo so MediaInfoPanel
      // continues to show the previously loaded media information.
      setIndexInfo((prev: any) => {
        // If the probe returned a full index (ok + mediainfo), replace.
        if (data && data.ok && (data.mediainfo || data.tracks)) return data;
        // Otherwise merge vapoursynth/probe result into previous indexInfo.
        const vap = data && data.vapoursynth ? data.vapoursynth : data || {};
        return { ...(prev || {}), vapoursynth: { ...(prev?.vapoursynth || {}), ...vap } };
      });
      if (data && data.ok) {
        setLastIndexedPath(inputPath);
      }
      // Trigger preview refresh
      setPreviewVersion(v => v + 1);
    } catch (e) {
      console.error('Probing failed during apply:', e);
    } finally {
      setIndexing(false);
      overlay.hide();
    }
  };

  // Render all tab panes but keep them mounted. We toggle visibility via inline styles
  // so that heavy components (Processing) don't remount when switching tabs.
  const sourcePane = (
    <div className="source-tab" style={{ display: activeTab === 'source' ? 'block' : 'none' }}>
      <div className="source-layout">
        <div className="source-left">
          <FileSelector
            inputPath={inputPath}
            onFileSelect={setInputPath}
            onBrowseClick={openFileModal}
            indexing={indexing}
          />
          <MediaInfoPanel filePath={inputPath} indexInfo={indexInfo} />
        </div>
      </div>
    </div>
  );

  const processingPane = (
    <div
      className="processing-tab"
      style={{ display: activeTab === 'processing' ? 'block' : 'none' }}
    >
      <div className="processing-layout">
        <div className="processing-left">
          <ScriptEditor
            script={script}
            onScriptChange={setScript}
            onValidate={handleScriptValidate}
            onApply={handleScriptApply}
            selectedPath={inputPath}
            resetSignal={processingResetVersion}
          />
          <FilterPanel onFilterAdd={handleFilterAdd} resetSignal={processingResetVersion} />
        </div>
        <div className="processing-right">
          <FramePreview
            inputPath={inputPath}
            script={script}
            indexInfo={indexInfo}
            onScriptChange={setScript}
            previewVersion={previewVersion}
            onPreviewError={(err: string | null) => setPreviewError(err)}
            resetSignal={processingResetVersion}
          />
        </div>
      </div>
    </div>
  );

  const outputPane = (
    <div className="output-tab" style={{ display: activeTab === 'output' ? 'block' : 'none' }}>
      <TargetSection
        outputPath={outputPath}
        setOutputPath={setOutputPath}
        container={container}
        setContainer={setContainer}
        videoCodec={videoCodec}
        setVideoCodec={setVideoCodec}
        onStart={() => alert('Start encode - not wired yet')}
        onReset={() => {
          setOutputPath('');
          setInputPath('');
          setScript('');
        }}
      />
    </div>
  );

  const jobsPane = (
    <div className="jobs-tab" style={{ display: activeTab === 'jobs' ? 'block' : 'none' }}>
      <h2>Jobs</h2>
      <p>Job management coming in Phase 3...</p>
    </div>
  );

  // Disable Processing and Output tabs when there's no input path loaded,
  // or when the VapourSynth probe has failed (in which case we cannot proceed).
  let disabledTabs: string[] = [];
  if (!inputPath) {
    disabledTabs = ['processing', 'output'];
  } else if (indexInfo && indexInfo.vapoursynth && indexInfo.vapoursynth.error) {
    // Probe failed; prevent user from using Processing/Output since previews/encodes won't work
    disabledTabs = ['processing', 'output'];
  } else if (previewError) {
    // If the preview failed (script/runtime error), block Processing/Output
    disabledTabs = [...disabledTabs, 'processing', 'output'];
  }

  // If inputPath is cleared, ensure we return to Source tab
  React.useEffect(() => {
    if (!inputPath && activeTab !== 'source') {
      setActiveTab('source');
    }
  }, [inputPath, activeTab]);

  // Redirect user to Source if the vapoursynth probe failed while they were on a blocked tab
  React.useEffect(() => {
    if (indexInfo && indexInfo.vapoursynth && indexInfo.vapoursynth.error) {
      if (activeTab !== 'source') setActiveTab('source');
    }
  }, [indexInfo?.vapoursynth?.error, activeTab]);

  // When the user opens the Processing tab, auto-run the apply/index once for the current
  // input path if it hasn't been indexed yet. This provides an initial preview without
  // requiring the user to click Apply every time they open the tab.
  React.useEffect(() => {
    if (activeTab !== 'processing') return;
    if (!inputPath) return;
    if (lastIndexedPath === inputPath) return; // already indexed

    // Fire-and-forget the apply (it manages indexing state and previewVersion)
    void handleScriptApply();
  }, [activeTab, inputPath, lastIndexedPath]);

  return (
    <MainLayout activeTab={activeTab} onTabChange={setActiveTab} disabledTabs={disabledTabs}>
      {sourcePane}
      {processingPane}
      {outputPane}
      {jobsPane}

      {/* Global blocking overlay for all blocking operations */}
      <GlobalOverlay />

      {/* Probe failure modal blocks processing/output when VapourSynth probe failed */}
      <ProbeFailureModal
        error={indexInfo?.vapoursynth?.error}
        onClose={() => {
          // Clear probe error locally so user can attempt to re-index/probe
          setIndexInfo((prev: any) => {
            if (!prev) return prev;
            const copy = { ...prev };
            if (copy.vapoursynth) copy.vapoursynth = { ...copy.vapoursynth, error: null };
            return copy;
          });
        }}
      />

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
    </MainLayout>
  );
}
