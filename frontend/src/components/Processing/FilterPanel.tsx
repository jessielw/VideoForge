import React, { useState } from 'react';

interface FilterPreset {
  id: string;
  name: string;
  description: string;
  code: string;
}

const FILTER_PRESETS: FilterPreset[] = [
  {
    id: 'resize_720p',
    name: 'Resize to 720p',
    description: 'Resize video to 1280x720',
    code: 'clip = core.resize.Lanczos(clip, width=1280, height=720)',
  },
  {
    id: 'resize_1080p',
    name: 'Resize to 1080p',
    description: 'Resize video to 1920x1080',
    code: 'clip = core.resize.Lanczos(clip, width=1920, height=1080)',
  },
  // {
  //   id: 'deinterlace',
  //   name: 'Deinterlace',
  //   description: 'Remove interlacing artifacts',
  //   code: 'clip = core.vivtc.VFM(clip, order=1)\nclip = core.vivtc.VDecimate(clip)'
  // },
  // {
  //   id: 'denoise_basic',
  //   name: 'Basic Denoise',
  //   description: 'Light denoising with BM3D',
  //   code: 'clip = core.bm3d.BM3D(clip, sigma=3.0)'
  // },
  // {
  //   id: 'sharpen',
  //   name: 'Sharpen',
  //   description: 'Apply unsharp mask sharpening',
  //   code: 'clip = core.std.UnsharpMask(clip, strength=0.5, radius=1)'
  // },
  // {
  //   id: 'colormatrix_bt709',
  //   name: 'Color Matrix BT.709',
  //   description: 'Convert to BT.709 color matrix',
  //   code: 'clip = core.resize.Lanczos(clip, matrix_s="709")'
  // },
  {
    id: 'crop_basic',
    name: 'Basic Crop',
    description: 'Crop borders (adjust values as needed)',
    code: 'clip = core.std.Crop(clip, left=0, right=0, top=0, bottom=0)',
  },
];

interface FilterPanelProps {
  onFilterAdd: (code: string) => void;
}

export default function FilterPanel({ onFilterAdd }: FilterPanelProps): JSX.Element {
  const [copiedFilter, setCopiedFilter] = useState<string | null>(null);

  const copyToClipboard = async (code: string, filterName: string) => {
    try {
      await navigator.clipboard.writeText(code);
      setCopiedFilter(filterName);
      // Clear the "copied" state after 2 seconds
      setTimeout(() => setCopiedFilter(null), 2000);
    } catch (error) {
      console.error('Failed to copy to clipboard:', error);
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = code;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      setCopiedFilter(filterName);
      setTimeout(() => setCopiedFilter(null), 2000);
    }
  };

  return (
    <div className="filter-panel">
      <h3>Common Filters</h3>
      <p className="filter-help">
        Click any filter to copy its code to clipboard, then paste into the script editor:
      </p>
      <div className="filter-presets">
        {FILTER_PRESETS.map(preset => (
          <div
            key={preset.id}
            className="filter-preset clickable"
            onClick={() => copyToClipboard(preset.code, preset.name)}
          >
            <div className="filter-header">
              <span className="filter-name">{preset.name}</span>
              <span className="copy-icon">{copiedFilter === preset.name ? '✅' : '📋'}</span>
            </div>
            <p className="filter-description">
              {preset.description}
              {copiedFilter === preset.name && ' - Copied!'}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
