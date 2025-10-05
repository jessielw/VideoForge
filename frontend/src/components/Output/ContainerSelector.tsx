/**
 * ContainerSelector - Choose output container format (MKV/MP4)
 */

import React from 'react';
import { ContainerFormat, CONTAINER_INFO } from '../../types/output';

interface ContainerSelectorProps {
  selected: ContainerFormat;
  onChange: (container: ContainerFormat) => void;
}

export default function ContainerSelector({
  selected,
  onChange,
}: ContainerSelectorProps): JSX.Element {
  return (
    <div className="container-selector">
      <label>Output Container Format</label>
      <div className="container-options">
        {(Object.keys(CONTAINER_INFO) as ContainerFormat[]).map(format => {
          const info = CONTAINER_INFO[format];
          const isSelected = selected === format;

          return (
            <div
              key={format}
              className={`container-option ${isSelected ? 'selected' : ''}`}
              onClick={() => onChange(format)}
            >
              <div className="container-option-header">
                <span className="container-icon">{info.icon}</span>
                <span className="container-name">{info.displayName}</span>
                {isSelected && <span className="check-icon">✓</span>}
              </div>
              <div className="container-description">{info.description}</div>
              <div className="container-features">
                <div className="feature-grid">
                  <div className={`feature ${info.supportsChapters ? 'supported' : 'unsupported'}`}>
                    {info.supportsChapters ? '✓' : '✗'} Chapters
                  </div>
                  <div
                    className={`feature ${info.supportsMultipleAudioTracks ? 'supported' : 'unsupported'}`}
                  >
                    {info.supportsMultipleAudioTracks ? '✓' : '✗'} Multi-Audio
                  </div>
                  <div
                    className={`feature ${info.supportsMultipleSubtitleTracks ? 'supported' : 'unsupported'}`}
                  >
                    {info.supportsMultipleSubtitleTracks ? '✓' : '✗'} Multi-Subtitle
                  </div>
                  <div
                    className={`feature ${info.supportsAttachments ? 'supported' : 'unsupported'}`}
                  >
                    {info.supportsAttachments ? '✓' : '✗'} Attachments
                  </div>
                </div>
              </div>
              <div className="container-muxer">
                Muxer: <code>{info.muxer}</code>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
