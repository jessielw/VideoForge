# Your first job

Use a short source and a separate output folder for the first run. Confirm that **Settings** finds
MKVToolNix, your encoder, and the source-filter plugin.

## 1. Add the source

Open **New jobs**, add an MKV, MP4, or M2TS / TS file, and choose the template to start from.
You can also add external subtitles, chapters, or an existing video encode to reuse.
Add the job, review the import summary, and choose **Open queue** to open its editor. Partial imports
retain the input draft and explain which existing jobs were kept or files were unmatched.

## 2. Index and inspect video

Use **Index** on the Queue toolbar. Once indexing finishes, open the job's **Video** tab.
Check several frames, set the crop, and enable resizing or filters if needed. Auto crop detects
borders; inspect the result before encoding.

If preview is unavailable, check the job's log and the
[preview troubleshooting steps](../reference/troubleshooting.md#preview-wont-open).

## 3. Choose encoding and tracks

On **Encoder**, select your installed encoder and a rate-control mode. For an initial test,
leave advanced options alone. On **Audio** and **Subtitles**, exclude unwanted tracks and check
the retained tracks' order, language, titles, and default or forced flags.

The **manual** profile copies tracks by default. An audio encode needs its corresponding tool;
copying audio does not need a separate audio encoder.

## 4. Set the output and run

On **Output**, choose the output folder and MKV or MP4. Inspect any planning issues before starting.
MKV accepts more track formats; an MP4 job can require different track selections.
Use **Run selected** for the test. For a batch, tick each job once it's set up (that queues and locks
it), then **Start queue** runs the queued jobs.

If the reuse dialog appears, choose which completed video or audio encodes to keep. A fresh job
has no completed encodes to reuse.

## 5. Check the result

Wait for **done**, open the finished file, and check picture, audio, subtitles, and chapters.
An **invalid** result means the candidate failed an output check; inspect the issues and the retained
unpublished file. The previously finished output stays intact.
A **failed** result means a step did not complete; inspect the last failed step in **Log**.

Once the test works, save the settings as a [template](../usage/templates.md) for future jobs.
