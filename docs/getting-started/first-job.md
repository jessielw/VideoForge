# Your first job

Use a short source and a separate output folder for the first run. Confirm that **Settings** finds MKVToolNix, your encoder, and the source-filter plugin.

## 1. Add the source

Open **New jobs**, add an MKV, MP4, or M2TS / TS file, and choose the template to start from. You can also add external subtitles, chapters, or an existing video encode to reuse. The bar at the bottom says what adding will do (how many jobs, the template, whether they are indexed and cropped, and where they are saved) and chooses **Index** and **Auto-crop** for this batch. Add the jobs, then choose **Open queue** in that bar to open the first one's editor, or **Add more** to start the next batch. Each input's label counts its paths; remove one with its ×, or empty the input with the clear button beside **Browse…**, and **Clear all** in the bottom bar empties every input. A long list scrolls inside its box. To see more of **Matched files**, pull up the grip on its top edge; a double-click sets it back. Partial imports keep the form and list which existing jobs were kept or files were unmatched. In a browser, paste paths anywhere in the app and they land on New jobs (Explorer: Ctrl+Shift+C, then Ctrl+V), or use **Browse…** ([below](#browsing-for-files)); see [Tray and console](windows.md#tray-and-console) for how the app runs.

![The New jobs page with three matched episodes](../assets/screenshots/new-jobs.png#only-light) ![The New jobs page with three matched episodes](../assets/screenshots/new-jobs-dark.png#only-dark)

### Browsing for files

**Browse…** lists the folders and files the server can see. Every **Browse…** in the app uses the same browser.

- **Tick several files:** click a file's row to tick it. Press on a row and drag over others to tick them all (starting on a ticked row unticks them instead). Shift+click ticks or unticks every row from the last one you clicked.
- **Tick every file:** Ctrl+A (Cmd+A) or the box above the list ticks every file in the folder, and again unticks them. Folders are left as they are.
- **Filter:** type in **Filter this folder** to show only names with every word in them, such as `s01 mkv`. Ctrl+A and ranges take only the rows it shows; files you ticked before stay ticked. Esc clears it.
- **Sort:** click **Name**, **Modified** or **Size** above the list. A new column starts newest or biggest first, and clicking it again flips it. Folders stay above files; sorting by size keeps them by name. Names sort with numbers in order (E2 before E10), and this browser remembers the sort.
- **Keyboard:** ↑ and ↓ move between rows (↓ from the filter goes to the first row), Home and End go to the first and last, and Shift+↑ or ↓ ticks the rows on the way. Space ticks the row (Shift+Space ticks a range). Enter opens a folder, or on a file adds what's ticked (that file, when nothing is). Backspace or Alt+↑ goes up a folder. Press ? outside a text box for the full list.
- **Refresh:** the refresh button (or F5) lists the folder again after files change outside VideoForge, keeping the filter.

## 2. Index and inspect video

Use **Index** on the Queue toolbar. Once indexing finishes, open the job's **Video** tab. Check several frames, set the crop, and enable resizing or filters if needed. Auto crop detects borders; inspect the result before encoding.

If preview is unavailable, check the job's log and the [preview troubleshooting steps](../reference/troubleshooting.md#preview-wont-open).

## 3. Choose encoding and tracks

On **Encoder**, select your installed encoder and a rate-control mode. For an initial test, leave advanced options alone. On **Audio** and **Subtitles**, exclude unwanted tracks and check the retained tracks' order, language, titles, and default or forced flags.

The **manual** rule set copies tracks by default. An audio encode needs its corresponding tool; copying audio does not need a separate audio encoder.

## 4. Set the output and run

On **Output**, choose the output folder and MKV or MP4. Inspect any planning issues before starting. MKV accepts more track formats; an MP4 job can require different track selections. Use **Run selected** for the test. For a batch, tick each job once it's set up (that queues and locks it), then **Start queue** runs the queued jobs.

If the reuse dialog appears, choose which completed video or audio encodes to keep. A fresh job has no completed encodes to reuse.

## 5. Check the result

Wait for **done**, open the finished file, and check picture, audio, subtitles, and chapters. An **invalid** result means the candidate failed an output check; inspect the issues and the retained unpublished file. The previously finished output stays intact. A **failed** result means a step did not complete; inspect the last failed step in **Log**.

Once the test works, save the settings as a [template](../usage/templates.md) for future jobs.
