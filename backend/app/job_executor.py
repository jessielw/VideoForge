"""
Job Executor - Runs encoding jobs from the queue

This module handles the actual execution of encoding jobs:
1. Detects frame count from VapourSynth script
2. Extracts audio tracks from source (ffmpeg)
3. Runs VapourSynth script via vspipe to generate raw video
4. Pipes output to x264/x265 encoder
5. Encodes audio separately (AAC or copy mode)
6. Muxes video + audio into final container (mkvmerge/ffmpeg)
7. Updates job progress in database
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from .database import get_db_connection


class JobExecutor:
    """Handles execution of a single encoding job."""
    
    def __init__(
        self,
        job_id: int,
        vspipe_path: str = r"D:\programming\video-forge\apps\VapourSynth\VSPipe.exe",
        x264_path: str = r"D:\programming\video-forge\apps\x264.exe",
        ffmpeg_path: str = "ffmpeg",  # Assumes ffmpeg is in PATH
        mkvmerge_path: str = "mkvmerge",  # Assumes mkvmerge is in PATH
    ):
        self.job_id = job_id
        self.vspipe_path = Path(vspipe_path)
        self.x264_path = Path(x264_path)
        self.ffmpeg_path = ffmpeg_path
        self.mkvmerge_path = mkvmerge_path
        self.process: Optional[subprocess.Popen] = None
        self.should_cancel = False
        self.temp_files: list[Path] = []  # Track temp files for cleanup
        
    def load_job(self):
        """Load job details from database."""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """
                SELECT
                    id, name, status, position, enabled,
                    source_path, output_path,
                    video_config, audio_config, output_config,
                    vs_script,
                    total_frames
                FROM jobs
                WHERE id = ?
                """,
                (self.job_id,)
            )
            
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Job {self.job_id} not found")
            
            # Parse the row data
            job_data = {
                "id": row[0],
                "name": row[1],
                "status": row[2],
                "position": row[3],
                "enabled": bool(row[4]),
                "source_path": row[5],
                "output_path": row[6],
                "video_config": json.loads(row[7]) if row[7] else {},
                "audio_config": json.loads(row[8]) if row[8] else {},
                "output_config": json.loads(row[9]) if row[9] else {},
                "vs_script": row[10],
                "total_frames": row[11],
            }
            
            return job_data
            
        finally:
            conn.close()
    
    def update_job_status(self, status: str, **kwargs):
        """Update job status in database."""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Build SET clause dynamically
            set_parts = ["status = ?"]
            values: list = [status]
            
            if status == "running" and "started_at" not in kwargs:
                set_parts.append("started_at = ?")
                values.append(datetime.now().isoformat())
            
            if status in ("completed", "failed", "cancelled"):
                set_parts.append("completed_at = ?")
                values.append(datetime.now().isoformat())
            
            for key, value in kwargs.items():
                set_parts.append(f"{key} = ?")
                values.append(value)
            
            values.append(self.job_id)
            
            query = f"UPDATE jobs SET {', '.join(set_parts)} WHERE id = ?"
            cursor.execute(query, tuple(values))
            conn.commit()
            
            print(f"✅ Job {self.job_id}: Status updated to '{status}'", flush=True)
            
        except Exception as e:
            print(f"❌ Failed to update job status: {e}", flush=True)
            conn.rollback()
        finally:
            conn.close()
    
    def update_progress(self, current_frame: int, total_frames: int, fps: float):
        """Update job progress."""
        progress = (current_frame / total_frames * 100) if total_frames > 0 else 0
        eta = ((total_frames - current_frame) / fps) if fps > 0 else 0
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """
                UPDATE jobs
                SET progress = ?, current_frame = ?, total_frames = ?, fps = ?, eta = ?
                WHERE id = ?
                """,
                (progress, current_frame, total_frames, fps, eta, self.job_id)
            )
            conn.commit()
        except Exception as e:
            print(f"⚠️ Failed to update progress: {e}", flush=True)
        finally:
            conn.close()
    
    def create_vspipe_script(self, job_data: dict) -> Path:
        """Create a temporary VapourSynth script file for vspipe."""
        script_content = job_data["vs_script"]
        
        # Create temp script file
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.vpy',
            delete=False,
            encoding='utf-8'
        ) as f:
            # Write the script
            # Note: The script should already have the source loaded and filters applied
            # We just need to ensure it outputs the clip
            if "set_output()" not in script_content:
                script_content += "\nclip.set_output()"
            
            f.write(script_content)
            script_path = Path(f.name)
        
        print(f"📜 Created VapourSynth script: {script_path}", flush=True)
        self.temp_files.append(script_path)
        return script_path
    
    def detect_frame_count(self, script_path: Path) -> Optional[int]:
        """Detect frame count from VapourSynth script using vspipe --info.
        
        Returns:
            Frame count if detected, None otherwise
        """
        try:
            # Run vspipe with --info to get clip properties
            cmd = [
                str(self.vspipe_path),
                "--info",
                str(script_path),
                "-"
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                timeout=30,  # Don't hang forever
            )
            
            if result.returncode != 0:
                print(f"⚠️ vspipe --info failed: {result.stderr}", flush=True)
                return None
            
            # Parse output for frame count
            # Example output: "Width: 1920\nHeight: 1080\nFrames: 2398\nFPS: 24000/1001 (23.976 fps)\n..."
            output = result.stdout
            for line in output.split('\n'):
                if line.startswith('Frames:'):
                    frames_str = line.split(':')[1].strip()
                    frame_count = int(frames_str)
                    print(f"📊 Detected {frame_count} frames from VapourSynth script", flush=True)
                    return frame_count
            
            print("⚠️ Could not find frame count in vspipe output", flush=True)
            return None
            
        except subprocess.TimeoutExpired:
            print("⚠️ vspipe --info timed out", flush=True)
            return None
        except Exception as e:
            print(f"⚠️ Frame count detection failed: {e}", flush=True)
            return None
    
    def detect_audio_tracks(self, source_path: str) -> list[dict]:
        """Detect audio tracks in source file using ffprobe.
        
        Returns:
            List of audio track info dicts with keys: index, codec, channels, sample_rate, bitrate
        """
        try:
            cmd = [
                self.ffmpeg_path.replace("ffmpeg", "ffprobe"),  # Use ffprobe
                "-v", "quiet",
                "-print_format", "json",
                "-show_streams",
                "-select_streams", "a",  # Audio streams only
                source_path,
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                timeout=30,
            )
            
            if result.returncode != 0:
                print(f"⚠️ ffprobe failed: {result.stderr}", flush=True)
                return []
            
            data = json.loads(result.stdout)
            streams = data.get('streams', [])
            
            audio_tracks = []
            for stream in streams:
                track_info = {
                    'index': stream.get('index', 0),
                    'codec': stream.get('codec_name', 'unknown'),
                    'channels': stream.get('channels', 2),
                    'sample_rate': stream.get('sample_rate', '48000'),
                    'bitrate': stream.get('bit_rate'),
                    'language': stream.get('tags', {}).get('language', 'und'),
                }
                audio_tracks.append(track_info)
            
            if audio_tracks:
                print(f"🎵 Detected {len(audio_tracks)} audio track(s)", flush=True)
                for i, track in enumerate(audio_tracks):
                    print(f"   Track {i}: {track['codec']}, {track['channels']}ch, {track['sample_rate']}Hz", flush=True)
            else:
                print("🔇 No audio tracks detected", flush=True)
            
            return audio_tracks
            
        except Exception as e:
            print(f"⚠️ Audio track detection failed: {e}", flush=True)
            return []
    
    def extract_audio(self, source_path: str, track_index: int, output_path: Path) -> bool:
        """Extract audio track from source file.
        
        Args:
            source_path: Source video file
            track_index: Audio stream index to extract
            output_path: Output audio file path (typically .aac or .m4a)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            cmd = [
                self.ffmpeg_path,
                "-i", source_path,
                "-map", f"0:a:{track_index}",  # Map specific audio track
                "-c", "copy",  # Copy audio stream without re-encoding
                "-y",  # Overwrite output
                str(output_path),
            ]
            
            print(f"🎵 Extracting audio track {track_index}...", flush=True)
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                timeout=300,  # 5 minute timeout for audio extraction
            )
            
            if result.returncode != 0:
                print(f"❌ Audio extraction failed: {result.stderr}", flush=True)
                return False
            
            if output_path.exists():
                print(f"✅ Audio extracted to: {output_path}", flush=True)
                self.temp_files.append(output_path)
                return True
            else:
                print(f"❌ Audio file not created: {output_path}", flush=True)
                return False
            
        except subprocess.TimeoutExpired:
            print("❌ Audio extraction timed out", flush=True)
            return False
        except Exception as e:
            print(f"❌ Audio extraction failed: {e}", flush=True)
            return False
    
    def encode_audio(self, input_audio: Path, output_audio: Path, encoder: str, bitrate: int = 192) -> bool:
        """Encode audio to AAC/Opus or copy mode.
        
        Args:
            input_audio: Extracted audio file
            output_audio: Output audio file
            encoder: Encoder to use ("aac", "opus", "copy")
            bitrate: Bitrate in kbps (ignored for copy mode)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            if encoder == 'copy':
                # Copy mode - just rename/move file
                if input_audio != output_audio:
                    shutil.copy2(input_audio, output_audio)
                print(f"✅ Audio copied (no re-encoding)", flush=True)
                return True
            
            # Determine codec based on encoder
            if encoder == 'opus':
                codec = 'libopus'
                ext_hint = 'opus'
            else:  # aac or default
                codec = 'aac'
                ext_hint = 'aac'
            
            cmd = [
                self.ffmpeg_path,
                "-i", str(input_audio),
                "-c:a", codec,
                "-b:a", f"{bitrate}k",
                "-y",
                str(output_audio),
            ]
            
            print(f"🎵 Encoding audio to {encoder.upper()} @ {bitrate}kbps...", flush=True)
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                timeout=300,
            )
            
            if result.returncode != 0:
                print(f"❌ Audio encoding failed: {result.stderr}", flush=True)
                return False
            
            if output_audio.exists():
                print(f"✅ Audio encoded to: {output_audio}", flush=True)
                self.temp_files.append(output_audio)
                return True
            else:
                return False
            
        except Exception as e:
            print(f"❌ Audio encoding failed: {e}", flush=True)
            return False
    
    def mux_video_audio(self, video_path: Path, audio_paths: list[Path], output_path: Path, container: str) -> bool:
        """Mux video and multiple audio tracks into final container.
        
        Args:
            video_path: Encoded video file (h264/h265)
            audio_paths: List of encoded/extracted audio files
            output_path: Final output file
            container: Container format (mkv, mp4)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            if not audio_paths:
                print("⚠️ No audio files provided for muxing", flush=True)
                return False
            
            # Try mkvmerge first for MKV containers (more reliable)
            if container.lower() == 'mkv' and shutil.which(self.mkvmerge_path):
                cmd = [
                    self.mkvmerge_path,
                    "-o", str(output_path),
                    str(video_path),
                ]
                # Add all audio files
                for audio_path in audio_paths:
                    cmd.append(str(audio_path))
                
                print(f"📦 Muxing with mkvmerge ({len(audio_paths)} audio track(s))...", flush=True)
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                    timeout=300,
                )
                
                if result.returncode == 0 and output_path.exists():
                    print(f"✅ Muxing successful: {output_path}", flush=True)
                    return True
                else:
                    print(f"⚠️ mkvmerge failed, falling back to ffmpeg", flush=True)
            
            # Fallback to ffmpeg for all containers
            cmd = [
                self.ffmpeg_path,
                "-i", str(video_path),
            ]
            # Add all audio inputs
            for audio_path in audio_paths:
                cmd.extend(["-i", str(audio_path)])
            
            # Map video
            cmd.extend(["-map", "0:v:0"])
            
            # Map all audio streams
            for i in range(len(audio_paths)):
                cmd.extend(["-map", f"{i+1}:a:0"])
            
            # Copy all streams without re-encoding
            cmd.extend(["-c", "copy", "-y", str(output_path)])
            
            print(f"📦 Muxing with ffmpeg ({len(audio_paths)} audio track(s))...", flush=True)
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                timeout=300,
            )
            
            if result.returncode != 0:
                print(f"❌ Muxing failed: {result.stderr}", flush=True)
                return False
            
            if output_path.exists():
                print(f"✅ Muxing successful: {output_path}", flush=True)
                return True
            else:
                return False
            
        except Exception as e:
            print(f"❌ Muxing failed: {e}", flush=True)
            return False
    
    def cleanup_temp_files(self):
        """Clean up temporary files created during encoding."""
        for temp_file in self.temp_files:
            try:
                if temp_file.exists():
                    temp_file.unlink()
                    print(f"🗑️ Cleaned up: {temp_file}", flush=True)
            except Exception as e:
                print(f"⚠️ Failed to clean up {temp_file}: {e}", flush=True)
        self.temp_files.clear()
    
    def extract_subtitle(self, source_path: Path, track_index: int, output_path: Path) -> bool:
        """Extract a subtitle track from the source file.
        
        Args:
            source_path: Source video file
            track_index: Subtitle track index (0-based)
            output_path: Output subtitle file (.srt, .ass, etc.)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            print(f"📄 Extracting subtitle track {track_index}...", flush=True)
            
            cmd = [
                self.ffmpeg_path,
                "-i", str(source_path),
                "-map", f"0:s:{track_index}",
                "-c:s", "copy",
                "-y",  # Overwrite
                str(output_path)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                timeout=120,
            )
            
            if result.returncode == 0 and output_path.exists():
                print(f"✅ Subtitle extracted: {output_path}", flush=True)
                return True
            else:
                print(f"❌ Subtitle extraction failed: {result.stderr}", flush=True)
                return False
                
        except Exception as e:
            print(f"❌ Subtitle extraction failed: {e}", flush=True)
            return False
    
    def mux_video_audio_subtitles(
        self, 
        video_path: Path, 
        audio_paths: list[Path], 
        subtitle_paths: list[Path],
        output_path: Path, 
        container: str,
        subtitle_configs: Optional[list[dict]] = None
    ) -> bool:
        """Mux video, audio tracks, and subtitle tracks into final container.
        
        Args:
            video_path: Encoded video file (h264/h265)
            audio_paths: List of encoded/extracted audio files
            subtitle_paths: List of extracted subtitle files
            output_path: Final output file
            container: Container format (mkv, mp4)
            subtitle_configs: Optional list of subtitle metadata (language, name, etc.)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # MKV with mkvmerge (best subtitle support)
            if container.lower() == 'mkv' and shutil.which(self.mkvmerge_path):
                cmd = [
                    self.mkvmerge_path,
                    "-o", str(output_path),
                    str(video_path),
                ]
                
                # Add all audio files
                for audio_path in audio_paths:
                    cmd.append(str(audio_path))
                
                # Add all subtitle files with metadata
                for idx, sub_path in enumerate(subtitle_paths):
                    if subtitle_configs and idx < len(subtitle_configs):
                        sub_config = subtitle_configs[idx]
                        # Add language tag
                        if sub_config.get('language'):
                            cmd.extend(["--language", f"0:{sub_config['language']}"])
                        # Add track name
                        if sub_config.get('name'):
                            cmd.extend(["--track-name", f"0:{sub_config['name']}"])
                        # Set default flag
                        if sub_config.get('default'):
                            cmd.extend(["--default-track", "0:yes"])
                        # Set forced flag
                        if sub_config.get('forced'):
                            cmd.extend(["--forced-track", "0:yes"])
                    
                    cmd.append(str(sub_path))
                
                print(f"📦 Muxing with mkvmerge ({len(audio_paths)} audio, {len(subtitle_paths)} subtitle)...", flush=True)
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                    timeout=300,
                )
                
                if result.returncode == 0 and output_path.exists():
                    print(f"✅ Muxing successful: {output_path}", flush=True)
                    return True
                else:
                    print(f"⚠️ mkvmerge failed: {result.stderr}", flush=True)
                    return False
            
            # Fallback to ffmpeg (limited subtitle support)
            # TODO: Implement ffmpeg subtitle muxing
            print("⚠️ Subtitle muxing with ffmpeg not yet implemented, using audio-only mux", flush=True)
            return self.mux_video_audio(video_path, audio_paths, output_path, container)
            
        except Exception as e:
            print(f"❌ Muxing with subtitles failed: {e}", flush=True)
            return False
    
    def build_x264_command(self, video_config: dict, output_path: str) -> list[str]:
        """Build x264 command line arguments.
        
        Format: x264 --demuxer y4m -o output.mp4 [options] -
        The stdin marker (-) goes at the END.
        """
        cmd = [str(self.x264_path)]
        
        # Demuxer and output file first
        cmd.extend(["--demuxer", "y4m"])
        cmd.extend(["-o", output_path])
        
        # Rate control
        mode = video_config.get("mode", "crf")
        if mode == "crf":
            crf = video_config.get("crf", 23)
            cmd.extend(["--crf", str(crf)])
        elif mode == "bitrate":
            bitrate = video_config.get("bitrate", 5000)
            cmd.extend(["--bitrate", str(bitrate)])
        elif mode == "2pass":
            # For now, just do single pass CRF
            # TODO: Implement proper 2-pass encoding
            crf = video_config.get("crf", 23)
            cmd.extend(["--crf", str(crf)])
        
        # Preset
        preset = video_config.get("preset")
        if preset and preset not in ("none", None):
            cmd.extend(["--preset", preset])
        
        # Tune
        tune = video_config.get("tune")
        if tune and tune not in ("none", None):
            cmd.extend(["--tune", tune])
        
        # Custom arguments
        custom_args = video_config.get("customArgs", "").strip()
        if custom_args:
            # Split custom args carefully
            cmd.extend(custom_args.split())
        
        # Input from stdin (must be at the END)
        cmd.append("-")
        
        return cmd
    
    def run(self):
        """Execute the encoding job with full multi-track audio support."""
        try:
            print(f"\n{'='*60}")
            print(f"🚀 Starting job {self.job_id}")
            print(f"{'='*60}\n")
            
            # Load job from database
            job_data = self.load_job()
            
            # Check if job is in correct state
            if job_data["status"] not in ("queued", "running"):
                raise ValueError(f"Job status is '{job_data['status']}', cannot start")
            
            # Update status to running (idempotent if already running)
            if job_data["status"] != "running":
                self.update_job_status("running")
            
            # Extract configuration
            source_path = job_data["source_path"]
            video_config = job_data["video_config"]
            audio_config = job_data["audio_config"]
            output_config = job_data["output_config"]
            final_output_path = Path(output_config.get("outputPath"))
            container = output_config.get("container", "mkv")
            
            print(f"📁 Source: {source_path}", flush=True)
            print(f"📁 Output: {final_output_path}", flush=True)
            print(f"⚙️ Encoder: {video_config.get('encoder', 'x264')}", flush=True)
            print(f"⚙️ Mode: {video_config.get('mode', 'crf')}", flush=True)
            print()
            
            # ===== STEP 1: Create VapourSynth script and detect frame count =====
            script_path = self.create_vspipe_script(job_data)
            
            # Detect frame count from script
            frame_count = self.detect_frame_count(script_path)
            if frame_count:
                # Update job with detected frame count
                conn = get_db_connection()
                cursor = conn.cursor()
                try:
                    cursor.execute(
                        "UPDATE jobs SET total_frames = ? WHERE id = ?",
                        (frame_count, self.job_id)
                    )
                    conn.commit()
                finally:
                    conn.close()
            else:
                print("⚠️ Could not detect frame count, progress percentage will be unavailable", flush=True)
            
            # ===== STEP 2: Detect and process audio tracks =====
            source_audio_tracks = self.detect_audio_tracks(source_path)
            audio_track_configs = audio_config.get('tracks', [])
            
            # List to store successfully processed audio files
            processed_audio_files: list[Path] = []
            
            if not source_audio_tracks:
                print("📝 No audio tracks in source, creating video-only output", flush=True)
            elif not audio_track_configs:
                print("📝 No audio tracks configured, creating video-only output", flush=True)
            else:
                print(f"\n{'='*60}")
                print(f"🎵 PROCESSING {len(audio_track_configs)} AUDIO TRACK(S)")
                print(f"{'='*60}\n")
                
                # Process each configured audio track
                for track_idx, track_config in enumerate(audio_track_configs):
                    source_track_idx = track_config.get('sourceTrack', 0)
                    encoder = track_config.get('encoder', 'aac')
                    bitrate = track_config.get('bitrate', 192)
                    track_name = track_config.get('name', f'Track {track_idx + 1}')
                    
                    print(f"🎵 Processing audio track {track_idx + 1}/{len(audio_track_configs)}: {track_name}")
                    print(f"   Source track: {source_track_idx}, Encoder: {encoder}, Bitrate: {bitrate}kbps")
                    
                    # Validate source track exists
                    if source_track_idx >= len(source_audio_tracks):
                        print(f"   ⚠️ Source track {source_track_idx} not found in source (only {len(source_audio_tracks)} tracks), skipping", flush=True)
                        continue
                    
                    # Extract audio to temp file
                    temp_audio_extracted = Path(tempfile.gettempdir()) / f"videoforge_job{self.job_id}_audio{track_idx}_extracted.m4a"
                    print(f"   Extracting...", flush=True)
                    audio_extracted = self.extract_audio(source_path, source_track_idx, temp_audio_extracted)
                    
                    if not audio_extracted:
                        print(f"   ❌ Extraction failed, skipping this track", flush=True)
                        continue
                    
                    # Encode audio
                    temp_audio_encoded = Path(tempfile.gettempdir()) / f"videoforge_job{self.job_id}_audio{track_idx}_encoded.{encoder if encoder != 'copy' else 'aac'}"
                    print(f"   Encoding...", flush=True)
                    audio_encoded = self.encode_audio(
                        temp_audio_extracted,
                        temp_audio_encoded,
                        encoder,
                        bitrate
                    )
                    
                    if audio_encoded:
                        processed_audio_files.append(temp_audio_encoded)
                        print(f"   ✅ Track {track_idx + 1} processed successfully\n", flush=True)
                    else:
                        print(f"   ❌ Encoding failed, skipping this track\n", flush=True)
            
            has_audio = len(processed_audio_files) > 0
            
            if has_audio:
                print(f"✅ Successfully processed {len(processed_audio_files)} audio track(s)\n", flush=True)
            else:
                print("⚠️ No audio tracks processed, creating video-only output\n", flush=True)
            
            # ===== STEP 3: Encode video =====
            # If we have audio, encode to temp file, then mux. Otherwise encode directly to final path.
            if has_audio:
                source_track = audio_config.get('sourceTrack', 0)

                
                # Extract audio to temp file
                temp_audio_extracted = Path(tempfile.gettempdir()) / f"videoforge_job{self.job_id}_audio_extracted.m4a"
                audio_extracted = self.extract_audio(source_path, source_track, temp_audio_extracted)
                
                if audio_extracted:
                    # Encode audio if needed
                    encoder = audio_config.get('encoder', 'aac')
                    temp_audio_encoded = Path(tempfile.gettempdir()) / f"videoforge_job{self.job_id}_audio_encoded.m4a"
                    
                    audio_encoded = self.encode_audio(
                        temp_audio_extracted,
                        temp_audio_encoded,
                        audio_config
                    )
                    
                    if not audio_encoded:
                        print("⚠️ Audio encoding failed, will create video-only output", flush=True)
                        has_audio = False
                else:
                    print("⚠️ Audio extraction failed, will create video-only output", flush=True)
                    has_audio = False
            else:
                print("� No audio tracks in source, creating video-only output", flush=True)
            
            # ===== STEP 3: Encode video =====
            # If we have audio, encode to temp file, then mux. Otherwise encode directly to final path.
            if has_audio and temp_audio_encoded:
                temp_video_path = Path(tempfile.gettempdir()) / f"videoforge_job{self.job_id}_video.{container}"
                video_output = temp_video_path
                self.temp_files.append(temp_video_path)
            else:
                video_output = final_output_path
            
            print(f"\n{'='*60}")
            print(f"🎬 ENCODING VIDEO")
            print(f"{'='*60}\n")
            
            # Build commands
            vspipe_cmd = [
                str(self.vspipe_path),
                str(script_path),
                "-",  # Output to stdout
                "-c", "y4m",  # Y4M container format
            ]
            
            x264_cmd = self.build_x264_command(video_config, str(video_output))
            
            print("🔧 VapourSynth command:")
            print(f"   {' '.join(vspipe_cmd)}", flush=True)
            print("\n🔧 x264 command:")
            print(f"   {' '.join(x264_cmd)}", flush=True)
            print()
            
            # Start vspipe process
            vspipe_process = subprocess.Popen(
                vspipe_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )
            
            # Start x264 process, reading from vspipe stdout
            x264_process = subprocess.Popen(
                x264_cmd,
                stdin=vspipe_process.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                universal_newlines=True,
                    bufsize=1,  # Line buffered
            )
            
            # Close our copy of vspipe stdout so x264 is the only reader
            if vspipe_process.stdout:
                vspipe_process.stdout.close()
            
            self.process = x264_process
            
            # Parse x264 output for progress
            current_frame = 0
            print("📊 Encoding progress:", flush=True)
            
            if x264_process.stderr:
                for line in x264_process.stderr:
                    # Check for cancellation
                    if self.should_cancel:
                        print("\n⚠️ Cancellation requested, terminating...", flush=True)
                        x264_process.terminate()
                        vspipe_process.terminate()
                        self.cleanup_temp_files()
                        self.update_job_status("cancelled")
                        return
                    
                    # Parse x264 output
                    # Example: "[99.8%] 2394/2398 frames, 145.32 fps, 5248.31 kb/s, eta 0:00:00"
                    if "frames" in line and "fps" in line:
                        try:
                            # Extract frame number
                            parts = line.split()
                            for i, part in enumerate(parts):
                                if "frames" in part and i > 0:
                                    frame_str = parts[i-1].split('/')[0]
                                    current_frame = int(frame_str)
                                    break
                            
                            # Extract FPS
                            fps = 0.0
                            for i, part in enumerate(parts):
                                if part == "fps," and i > 0:
                                    fps = float(parts[i-1])
                                    break
                            
                            # Update progress in database
                            if frame_count and frame_count > 0:
                                self.update_progress(current_frame, frame_count, fps)
                                
                                # Print progress every 100 frames
                                if current_frame % 100 == 0:
                                    progress_pct = (current_frame / frame_count * 100)
                                    print(f"   Frame {current_frame}/{frame_count} ({progress_pct:.1f}%) @ {fps:.1f} fps", flush=True)
                            else:
                                # No frame count available, just show current frame
                                if current_frame % 100 == 0:
                                    print(f"   Frame {current_frame} @ {fps:.1f} fps", flush=True)
                        
                        except (ValueError, IndexError):
                            pass
            
            # Wait for processes to complete
            x264_exit = x264_process.wait()
            vspipe_exit = vspipe_process.wait()
            
            # Check exit codes
            if x264_exit != 0:
                stderr_output = vspipe_process.stderr.read().decode('utf-8', errors='replace') if vspipe_process.stderr else ""
                self.cleanup_temp_files()
                raise RuntimeError(f"x264 failed with exit code {x264_exit}\nVapourSynth errors: {stderr_output}")
            
            if vspipe_exit != 0:
                stderr_output = vspipe_process.stderr.read().decode('utf-8', errors='replace') if vspipe_process.stderr else ""
                self.cleanup_temp_files()
                raise RuntimeError(f"vspipe failed with exit code {vspipe_exit}\n{stderr_output}")
            
            print(f"\n✅ Video encoding completed!", flush=True)
            print(f"📁 Video file: {video_output}", flush=True)
            
            # ===== STEP 4: Mux video + audio if we have audio =====
            if has_audio and processed_audio_files:
                print(f"\n{'='*60}")
                print(f"📦 MUXING VIDEO + AUDIO ({len(processed_audio_files)} track(s))")
                print(f"{'='*60}\n")
                
                mux_success = self.mux_video_audio(
                    video_output,  # type: ignore
                    processed_audio_files,
                    final_output_path,
                    container
                )
                
                if not mux_success:
                    print("⚠️ Muxing failed, keeping video-only output", flush=True)
                    # If muxing failed but we have video, copy video to final path
                    if video_output != final_output_path:
                        shutil.copy2(video_output, final_output_path)
            else:
                # No audio, video file is already at final path or needs to be moved
                if video_output != final_output_path:
                    shutil.move(str(video_output), str(final_output_path))
                    print(f"📁 Moved video to final path: {final_output_path}", flush=True)
            
            # ===== STEP 5: Update job status =====
            if final_output_path.exists():
                output_size = final_output_path.stat().st_size
                self.update_job_status("completed", output_size=output_size, progress=100.0)
                print(f"\n{'='*60}")
                print(f"✅ JOB COMPLETED SUCCESSFULLY!")
                print(f"{'='*60}")
                print(f"📁 Output: {final_output_path}", flush=True)
                print(f"� Size: {output_size / (1024*1024):.2f} MB", flush=True)
            else:
                raise RuntimeError("Final output file was not created")
            
            # Clean up temp files
            self.cleanup_temp_files()
        
        except Exception as e:
            error_msg = str(e)
            print(f"\n❌ Job {self.job_id} failed: {error_msg}", flush=True)
            self.cleanup_temp_files()
            self.update_job_status("failed", error_message=error_msg)
            raise
    
    def cancel(self):
        """Request cancellation of the running job."""
        self.should_cancel = True
        if self.process:
            self.process.terminate()


def execute_job(job_id: int):
    """Execute a job by ID (blocking)."""
    executor = JobExecutor(job_id)
    executor.run()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m app.job_executor <job_id>")
        sys.exit(1)
    
    job_id = int(sys.argv[1])
    execute_job(job_id)
