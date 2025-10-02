import React, { useState } from 'react';

interface FilterPreset {
  id: string;
  name: string;
  description: string;
  code: string;
}

const FILTER_PRESETS: FilterPreset[] = [
  {
    id: 'crop',
    name: 'Crop',
    description: 'Remove unwanted borders (use preview crop tool)',
    code: '# Use the crop tool in preview'
  },
  {
    id: 'resize_720p',
    name: 'Resize to 720p',
    description: 'Resize video to 1280x720',
    code: 'clip = core.resize.Lanczos(clip, width=1280, height=720)'
  },
  {
    id: 'resize_1080p',
    name: 'Resize to 1080p', 
    description: 'Resize video to 1920x1080',
    code: 'clip = core.resize.Lanczos(clip, width=1920, height=1080)'
  },
  {
    id: 'deinterlace',
    name: 'Deinterlace',
    description: 'Remove interlacing artifacts',
    code: 'clip = core.vivtc.VFM(clip, order=1)\nclip = core.vivtc.VDecimate(clip)'
  },
  {
    id: 'denoise_basic',
    name: 'Basic Denoise',
    description: 'Light denoising with BM3D',
    code: 'clip = core.bm3d.BM3D(clip, sigma=3.0)'
  },
  {
    id: 'sharpen',
    name: 'Sharpen',
    description: 'Apply unsharp mask sharpening',
    code: 'clip = core.std.UnsharpMask(clip, strength=0.5, radius=1)'
  },
  {
    id: 'colormatrix_bt709',
    name: 'Color Matrix BT.709',
    description: 'Convert to BT.709 color matrix',
    code: 'clip = core.resize.Lanczos(clip, matrix_s="709")'
  }
];

interface FilterPanelProps {
  onFilterAdd: (code: string) => void;
}

export default function FilterPanel({ onFilterAdd }: FilterPanelProps): JSX.Element {
  const [selectedPresets, setSelectedPresets] = useState<Set<string>>(new Set());

  const handlePresetToggle = (preset: FilterPreset) => {
    const newSelected = new Set(selectedPresets);
    
    if (newSelected.has(preset.id)) {
      newSelected.delete(preset.id);
    } else {
      newSelected.add(preset.id);
      if (preset.code !== '# Use the crop tool in preview') {
        onFilterAdd(preset.code);
      }
    }
    
    setSelectedPresets(newSelected);
  };

  const addCustomFilter = () => {
    const code = prompt('Enter custom VapourSynth code:');
    if (code) {
      onFilterAdd(code);
    }
  };

  return (
    <div className="filter-panel">
      <h3>Common Filters</h3>
      <div className="filter-presets">
        {FILTER_PRESETS.map(preset => (
          <div key={preset.id} className="filter-preset">
            <label className="filter-checkbox">
              <input
                type="checkbox"
                checked={selectedPresets.has(preset.id)}
                onChange={() => handlePresetToggle(preset)}
              />
              <span className="filter-name">{preset.name}</span>
            </label>
            <p className="filter-description">{preset.description}</p>
          </div>
        ))}
      </div>
      
      <div className="custom-filter">
        <button onClick={addCustomFilter} className="add-custom-button">
          ➕ Add Custom Filter
        </button>
      </div>
    </div>
  );
}