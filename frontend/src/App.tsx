import React, { useState } from 'react';
import MainLayout from './components/Layout/MainLayout';
import FileSelector from './components/Source/FileSelector';
import MediaInfoPanel from './components/Source/MediaInfoPanel';
import ScriptEditor from './components/Processing/ScriptEditor';
import FilterPanel from './components/Processing/FilterPanel';
import FramePreview from './components/Processing/FramePreview';
import TargetSection from './components/Target';
import FileBrowserModal from './components/FileBrowserModal';
import IndexingModal from './components/Processing/IndexingModal';
import './styles/index.css';

const API = 'http://127.0.0.1:8000';

export default function App(): JSX.Element {
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
  // Preview trigger (increment to tell FramePreview to fetch new frames)
  const [previewVersion, setPreviewVersion] = useState(0);
  // Track last path we've indexed via Apply/auto-index so we don't re-index repeatedly
  const [lastIndexedPath, setLastIndexedPath] = useState<string | null>(null);

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
    try {
      const resp = await fetch(`${API}/api/vs/probe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: inputPath }),
      });
      const data = await resp.json();
      console.log('Probe data:', data);
      setIndexInfo(data);
      if (data && data.ok) {
        setLastIndexedPath(inputPath);
      }
      // Trigger preview refresh
      setPreviewVersion(v => v + 1);
    } catch (e) {
      console.error('Probing failed during apply:', e);
    } finally {
      setIndexing(false);
    }
  };

  // Render tab content
  const renderTabContent = () => {
    switch (activeTab) {
      case 'source':
        return (
          <div className="source-tab">
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

      case 'processing':
        return (
          <div className="processing-tab">
            <div className="processing-layout">
              <div className="processing-left">
                <ScriptEditor
                  script={script}
                  onScriptChange={setScript}
                  onValidate={handleScriptValidate}
                  onApply={handleScriptApply}
                  selectedPath={inputPath}
                />
                <FilterPanel onFilterAdd={handleFilterAdd} />
              </div>
              <div className="processing-right">
                <FramePreview
                  inputPath={inputPath}
                  script={script}
                  indexInfo={indexInfo}
                  onScriptChange={setScript}
                  previewVersion={previewVersion}
                />
              </div>
            </div>
          </div>
        );

      case 'output':
        return (
          <div className="output-tab">
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

      case 'jobs':
        return (
          <div className="jobs-tab">
            <h2>Jobs</h2>
            <p>Job management coming in Phase 3...</p>
          </div>
        );

      default:
        return <div>Unknown tab</div>;
    }
  };

  // Disable Processing and Output tabs when there's no input path loaded
  const disabledTabs = inputPath ? [] : ['processing', 'output'];
  // If inputPath is cleared, ensure we return to Source tab
  React.useEffect(() => {
    if (!inputPath && activeTab !== 'source') {
      setActiveTab('source');
    }
  }, [inputPath, activeTab]);

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
      {renderTabContent()}

      {/* Blocking indexing modal shown while indexing is running */}
      <IndexingModal indexing={indexing} />

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
