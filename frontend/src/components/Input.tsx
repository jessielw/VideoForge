import React from "react";
import {
  calcAvgBitrateFromMediaInfoKbps,
  bitRateKbpsToMbs,
  getHdrString,
  getTrack,
  getTrackArray,
} from "./utils/mediainfo";
import "../styles/input.css";

export default function InputSection({
  inputPath,
  setInputPath,
  openFileModal,
  fileDetails,
}: {
  inputPath: string;
  setInputPath: (v: string) => void;
  openFileModal: () => void;
  fileDetails?: any;
}): JSX.Element {
  const mediaInfo = fileDetails?.mediainfo;
  const generalTrack = getTrack(mediaInfo, "General");
  const videoTrack = getTrack(mediaInfo, "Video");

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
      </div>
      <div>
        {generalTrack ? (
          <div className="file-details">
            {getTrackArray(generalTrack, "other_duration")[3] && (
              <div>
                <strong>Duration:</strong>{" "}
                {getTrackArray(generalTrack, "other_duration")[3].split(".")[0]}
              </div>
            )}
            {getTrackArray(generalTrack, "other_file_size")[0] && (
              <div>
                <strong>Size:</strong>{" "}
                {getTrackArray(generalTrack, "other_file_size")[0]}
              </div>
            )}
            {getTrackArray(generalTrack, "other_frame_rate")[0] && (
              <div>
                <strong>Frame Rate:</strong>{" "}
                {getTrackArray(generalTrack, "other_frame_rate")[0]}
              </div>
            )}
            {videoTrack?.frame_rate_mode && (
              <div>
                <strong>Mode:</strong> {videoTrack.frame_rate_mode}
              </div>
            )}
            {calcAvgBitrateFromMediaInfoKbps(mediaInfo) && (
              <div>
                <strong>Avg Bitrate:</strong>{" "}
                {bitRateKbpsToMbs(calcAvgBitrateFromMediaInfoKbps(mediaInfo))}
              </div>
            )}
            {videoTrack?.width && videoTrack?.height && (
              <div>
                <strong>Resolution:</strong> {videoTrack.width}x
                {videoTrack.height}
              </div>
            )}
            {videoTrack?.color_space && (
              <div>
                <strong>Color Space:</strong> {videoTrack.color_space}
              </div>
            )}
            {videoTrack?.chroma_subsampling && (
              <div>
                <strong>Chroma:</strong> {videoTrack.chroma_subsampling}
              </div>
            )}
            {getTrackArray(videoTrack, "other_bit_depth")[0] && (
              <div>
                <strong>Bit Depth:</strong>{" "}
                {getTrackArray(videoTrack, "other_bit_depth")[0]}
              </div>
            )}
            {getTrackArray(videoTrack, "other_hdr_format")[0] &&
              getHdrString(
                getTrackArray(videoTrack, "other_hdr_format")[0]
              ) && (
                <div>
                  <strong>HDR:</strong>{" "}
                  {getHdrString(
                    getTrackArray(videoTrack, "other_hdr_format")[0]
                  )}
                </div>
              )}
            {videoTrack?.format && videoTrack?.format_profile && (
              <div>
                <strong>Format:</strong> {videoTrack.format}{" "}
                {videoTrack.format_profile}
              </div>
            )}
            {getTrackArray(videoTrack, "other_display_aspect_ratio")[0] && (
              <div>
                <strong>DAR:</strong>{" "}
                {getTrackArray(videoTrack, "other_display_aspect_ratio")[0]}
              </div>
            )}
            {videoTrack?.pixel_aspect_ratio && (
              <div>
                <strong>PAR:</strong> {videoTrack.pixel_aspect_ratio}
              </div>
            )}
            {videoTrack?.width && videoTrack?.height && (
              <div>
                <strong>SAR:</strong>{" "}
                {(Number(videoTrack.width) / Number(videoTrack.height)).toFixed(
                  2
                )}
              </div>
            )}
          </div>
        ) : (
          ""
        )}
      </div>
    </section>
  );
}
