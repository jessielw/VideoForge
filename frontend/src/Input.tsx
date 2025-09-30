import React from "react";
import "./styles/input.css";

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

function getTrack(mediaInfo: any, trackType: string, idx?: number) {
  if (!Array.isArray(mediaInfo?.tracks)) return undefined;
  const tracks = mediaInfo.tracks.filter(
    (t: any) => t.track_type === trackType
  );
  if (tracks.length === 0) return undefined;
  if (typeof idx === "number" && idx >= 0 && idx < tracks.length) {
    return tracks[idx];
  }
  return tracks[0];
}

function getTrackArray(track: any, prop: string): any[] {
  const arr = track && Array.isArray(track[prop]) ? track[prop] : [];
  return arr;
}

function calcAvgBitrateFromMediaInfoKbps(mediaInfo: any): number | undefined {
  let miBitRate;
  if (mediaInfo) {
    const videoTrack = Array.isArray(mediaInfo.tracks)
      ? mediaInfo.tracks.find((t: any) => t.track_type === "Video")
      : undefined;
    const generalTrack = Array.isArray(mediaInfo.tracks)
      ? mediaInfo.tracks.find((t: any) => t.track_type === "General")
      : undefined;

    if (videoTrack?.stream_size && videoTrack?.duration) {
      miBitRate = Math.round(
        parseFloat(videoTrack.stream_size) /
          1000 /
          ((parseFloat(videoTrack.duration) / 60000) * 0.0075) /
          1000
      );
    } else if (generalTrack?.file_size && generalTrack?.duration) {
      miBitRate = Math.round(
        (parseFloat(generalTrack.file_size) /
          1000 /
          ((parseFloat(generalTrack.duration) / 60000) * 0.0075) /
          1000) *
          0.88
      );
    }
  }
  return miBitRate;
}

function bitRateKbpsToMbs(bitRateKbps: number | undefined): string {
  if (typeof bitRateKbps !== "number" || isNaN(bitRateKbps)) return "N/A";
  const mbs = bitRateKbps / 1000;
  return mbs.toFixed(2) + " Mb/s";
}

function getHdrString(hdrString: string | undefined): string {
  var hdr = "";
  if (hdrString?.includes("Dolby Vision") && hdrString?.includes("HDR10+")) {
    hdr = "DV HDR10+";
  } else if (
    hdrString?.includes("Dolby Vision") &&
    hdrString?.includes("HDR10")
  ) {
    hdr = "DV HDR10";
  } else if (hdrString?.includes("HDR10")) {
    hdr = "HDR10";
  }
  return hdr;
}
