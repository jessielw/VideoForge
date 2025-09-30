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

export {
  getTrack,
  getTrackArray,
  calcAvgBitrateFromMediaInfoKbps,
  bitRateKbpsToMbs,
  getHdrString,
};
