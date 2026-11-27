# Queue and batch indexing

The queue stores jobs and their settings in SQLite. One worker processes jobs in order; each job can run audio encodes alongside its video encode. A separate indexing lane prepares sources for preview and later encoding.

## Add and edit a batch

1. On **New jobs**, add a folder of episodes or select individual sources.
2. Choose a template and add the jobs. Adding doesn't queue them; step 5 does.
3. Open a job to check video processing, encoder settings, tracks, and output.
4. Select several jobs to apply an edit or template to all of them, or to set their original language ([Tracks](tracks.md#reuse-choices-across-a-season)).
5. Tick each job that's set up to queue it, or select several and use **Queue**.
6. Use **Start queue** to run the queued jobs, or **Run selected** to queue and run a selection at once.

Each job gets its own settings. Changing one job does not silently change the others. Import previews link to existing jobs. They keep those jobs' settings unless you explicitly choose **Replace and reset its edits**; busy jobs cannot be replaced. Partial imports retain the input draft and show added, kept and unmatched counts with details. Drafts survive navigation and refresh in the same browser tab.

## Duplicate a job

To make a second output from the same source with a few settings changed, select the job and use **Duplicate** (the copy icon on the Queue toolbar). The copy appears right after the original with the same settings and a label of its own (`v2`, `v3`, and so on, or `dubbed-2` for a job labeled `dubbed`), so it writes its own file. Change what you need in its tabs; the label and output name are on the **Output** tab. Duplicating several selected jobs copies each one.

Each job keeps its files in its own folder in the source's work folder, named by its label, so set the label before the first run. The copy's run reuses what the two jobs share: the source index, and any video or audio encode whose settings did not change, linked into its folder. The log says `made by the job in dubbed/, reused` for those. Jobs on one source share the index, so one is never indexed while another runs; the second waits and its log says so.

Adding the same source again keeps the existing job instead of making another; use Duplicate.

## Groups

A group shows a batch of jobs together under one header, such as a season. Adding two or more jobs at once on **New jobs** puts them in a group when **Group them** is ticked (it is by default). The group is named after the jobs: `Show S01` from episode names like `Show.S01E01`, else their folder (`Show Season 1` for a season folder), else what their names start with. Change the name there before adding, or untick **Group them**. To group jobs already in the queue, select them and use **Group** (the folder-plus icon on the toolbar); this takes them out of any group they were in.

A group's jobs always sit together in the queue, so the queue runs them one after another. Its header:

- **Collapse/expand** (the arrow) hides or shows its jobs. Collapsing is remembered in this browser. A collapsed group counts as one row on a page, and the arrow keys skip it; a Shift range or Ctrl/Cmd+A still takes all of its jobs.
- **The name** selects every job in it that the search and filter show, for the batch panel. The header counts the jobs (while a filter is on, how many match) and, when there are any, how many are done and how many failed. While one of its jobs runs, a bar along its bottom edge shows the whole group's progress. A collapsed group whose jobs are all selected shows as selected. Under the name, a second line shows what every job in the group shares, such as the resolution, encoder and track counts, and the group's rows show only what differs, usually the length.
- **The box** queues every job in it that can be queued, or, when all are queued, unqueues the ones not running yet.
- **⋯** has **Select its jobs**, **Move the selected jobs here** (to the end of the group), **Take the selected jobs out** (to just after it), **Rename…** and **Ungroup**. Ungroup removes the group; its jobs stay in the queue, where they are. The two Move items are the keyboard's way into and out of a group.

To move jobs, drag the grip (⋮⋮) at the right of a row. The grip of a selected job moves every selected job, and the rows being moved are dimmed. A line shows where they will go: a line indented to the jobs' names puts them in that group, and a full-width line puts them outside any group. Where a drop would change nothing, no line shows. Below a group's last job, the upper part of the gap is still inside the group and the lower part is outside it. On a collapsed header, the middle adds them at the end of the group, and the top or bottom puts them before or after it. Drag a header's grip to move the whole group; it lands before or after another group, never inside one. Esc cancels a drag. Dragging on a row itself still selects the rows you drag across.

The **Move up** and **Move down** buttons keep a job inside its group (drag it to take it out). With a whole group selected, they move the group as one past the next job or group. Removing a group's jobs and undoing it puts them back in the group. A duplicate goes in its job's group. Groups belong to the queue only: they aren't saved in job files, so jobs added from job files start ungrouped.

## Find and select jobs

Search matches job names, labels, source paths and each row's format, ignoring case: its encoder (`x265`), resolution (`3840`) and HDR tags (`HDR10`, `DV`). Every word must match somewhere in them. To give one kind of source its own encoder preset, search for it, use **Select matching jobs**, and set the preset once in the batch panel. Combine it with a status filter; status counts reflect the current search. The filter lists only the statuses that have jobs, and the one you picked. The list shows 100 matching jobs per page, in queue order. **Previous** and **Next** change pages without changing the selection or the run order.

**Select matching jobs** selects every match across pages. Ctrl/Cmd+A does the same when a job row has focus; it keeps its usual text-selection behavior in Search. Use arrows or Home/End to move between matching jobs, including across pages. Shift extends a selection, Ctrl/Cmd-click toggles a row, and dragging selects a range of matching rows. Tab leaves the row group after one stop instead of visiting every job. Press **?** (outside a text field), or **Shortcuts** in the menu, for every keyboard shortcut in the app.

Selections survive filters and live status changes. The count identifies jobs hidden by filters; **Clear selection** clears all selected jobs. **Run selected**, Index with a selection, and the other selected-job actions include selections on other pages and hidden by filters. **Start queue** runs every queued job, and Index without a selection uses all jobs. Move up/down changes positions in the full queue, including across filtered-out neighbors.

Between 1130 and 1439 CSS pixels, opening one job collapses the menu to icons and keeps the list beside the editor, with each job's name and status. Below 1130 CSS pixels, opening one job collapses the list to a rail of numbered chips, each with a small mark for its status. **Show the queue list** opens search and filters over the editor; Escape closes it and restores focus to the opener. Below 1024 CSS pixels, the menu stays collapsed to icons even with no job open. Below 640 CSS pixels, the list fills the available width. Short windows allow scrolling to reach queue controls.

## Queue jobs

A job runs only once it's queued. Queue it when its settings are final: tick its box in the queue list, in the column under **Queued**, or **Queue** at the top of its editor (they're the same switch), or select several jobs and use **Queue (N)** on the toolbar. A queued job is locked: its settings are read-only and its preview doesn't change, so what the queue will encode is what you see. Its row shows a lock before **Queued**. Untick it (or **Unqueue (N)**) to edit it again; the queue leaves it out until it's queued again.

A job queued while the queue runs is picked up in its turn, in queue order. Queueing a completed, failed or canceled job runs it again; unticking it before it runs keeps its last result. A job can't be queued while it's being probed, indexed or crop-detected, or while it's blocked.

## Start a run

**Start queue** runs the queued jobs; with none queued it's disabled. **Run selected** queues the selected jobs and starts, including completed jobs and failed or canceled runs to rerun or retry. Start and Index wait for pending editor saves. Failed saves offer **Retry saves** or **Discard unsaved changes** before work can start. Batch crop reports updated, skipped and failed jobs; imported encodes and busy jobs are skipped without stopping later eligible jobs. For episodes with different track orders, prefer template rules over track positions.

## Concurrent jobs

In **Settings → Queue & indexing**, enable **Run multiple full jobs at once** to use more than one slot. These settings apply to every profile on the installation. The starting limits are two full jobs, two x264 jobs, and one job of each other type. x265 starts with **Run alone** selected.

Each job holds its slot through validation and cleanup. The next queued row shows why it is waiting. For two x264 jobs and one x265 job to run together, set three total slots and clear **Run alone** for x265. Lowering a cap lets active jobs finish. Audio parallelism is configured per job.

Variants with separate job folders can run together. Matching encodes share a finished file. Cancelling a producer lets a waiting variant try the step again. Give custom scripts and raw tool arguments distinct paths for extra files they write.

## Batch indexing

Use **Index** on the Queue toolbar to index selected jobs, or all jobs if none are selected. Indexing creates the source index and working script without starting an encode. A job's preview opens only after its source is indexed; opening an editor never starts a full-source read by itself.

By default a new job is indexed as soon as it is probed (**Settings → Index new jobs**), and its crop is detected after the index (**Auto-crop new jobs**, which indexes the job even with the first option off). Turn them off to index only when you ask. A template with a fixed crop keeps its crop, and a crop you set by hand always wins.

For a source MediaInfo reports as interlaced or with pulldown flags, the lane then runs a [field scan](fields.md#field-scan). The job shows **Scanning fields**: its preview opens and it can be edited, and it can be queued once the scan is done. A template with **Field: Scan per job** puts such a job in the lane even with **Index new jobs** off.

Indexing can run while another job encodes. By default, a source on the same physical disk that the encode is reading waits while that job extracts, encodes audio, indexes, or muxes, and sources on other disks go first. Once the job is only encoding video, which reads the source slowly, the waiting sources are indexed beside it. **Settings → Wait while an encode reads the same disk** controls the wait, and **Index anyway while it only encodes video** turns off the video-only exception. The sidebar shows waiting jobs as _to index after the encode_, apart from the ones being indexed.

BestSource's first index decodes the whole video and can take substantially longer than FFMS2. Check the job log before assuming an index is stuck.

## Pause, stop, and cancel

Use **Cancel job** on a running job’s row to cancel that job. **Stop after active jobs** leaves the remaining jobs queued while active runs finish. **Cancel active jobs and stop** cancels every active full job and leaves pending jobs queued.

**Pause**, **Resume**, and **Priority** apply to all running tools, including the index/sample lane. **Stop indexing** controls that lane separately. By default one sample or CRF search can run alongside full jobs, including an exclusive encode. Select **Count samples and CRF searches toward job limits** to apply the total, encoder limits and exclusivity to samples too.

Untick a queued job, or use **Unqueue** on selected queued jobs, to unlock their settings without removing the jobs or files. This does not cancel a running job.

## Pause after pass 1

A 2-pass encode can be stopped between its passes. **Pause after pass 1** on the job’s row (while the job runs, or click it again to take it back) lets pass 1 finish, then ends the run as **Paused**. Nothing is canceled and the finished steps stay recorded, so you can close VideoForge. Run the job again, even after a restart, and it reuses pass 1 and goes on with pass 2. Audio encodes still running beside the video when the job pauses are stopped and made again on the next run. A job that is not a 2-pass encode has no pass 1 to stop after.

## Job files

Every job's whole setup (source, tracks, video and encoder settings, mux and output options) is saved as `videoforge-job.json` in the job's folder in the source's `_tmp` folder when it runs. **Save job files** in **More actions** (**⋯** on the Queue toolbar) writes it for the selected jobs at any time. **Add jobs from job files…**, also in **More actions**, takes the file, a job's folder, or a source's `_tmp` folder (every job in it), pasted or picked with **Browse…**, and adds each job exactly as it was saved: no template or profile default is applied. A job whose source already has a job with that label is left out. The work folder is where it was, so the run reuses the steps it already finished.

## Reuse completed work

Before rerunning a job, **Start queue** and **Run selected** show the available completed video and audio encodes. Choose which to reuse and which to create again. Reuse depends on the saved step fingerprint and the finished output files; changed inputs or settings can invalidate it.

Intermediate files and `finished-steps.json` live in the job's folder in the source's work folder ([layout](../configuration/storage.md#per-source-work-folders)). Keep that folder to retain reuse. Files another job on the source made the same way are offered too, marked with that job's folder. A process interrupted halfway through an encode restarts that encode rather than continuing inside its bitstream.

## Read the result

| Status | Meaning | Next step |
| --- | --- | --- |
| Done | Output was muxed and passed its output checks | Inspect playback |
| Invalid | Candidate failed an output check; existing finished output was kept | Inspect the **Issues** tab and the unpublished file |
| Failed | A tool or pipeline step failed | Read the last failed step in Log |
| Skipped | The job was skipped by planning or its existing-output policy | Review the **Issues** tab and the Output tab |
| Canceled | The run was interrupted | Rerun and review reuse choices |

A job with errors or warnings shows how many in its header and its queue row, such as "1 error · 2 warnings". Its **Issues** tab, after **Log**, lists each one with its code, and shows only while there are any. An issue with one place to fix it links there, such as **Go to the Encoder tab** or **Go to Settings › Tools**. An error blocks the job (**Blocked**) or says why a run failed; a warning lets it run (**Ready with warnings**; its queue row says **Warning**, or **Warnings** for more than one).

A done (or invalid) job's header says what its last run made: the output's size, that as a share of the source, its overall bitrate, how long the run took and how many steps it reused. It's taken as the run ends, so it stays after an action moves the file or the work folder is deleted.

Use the job's **Log** tab for one job, or the **Log** page for all jobs. For persistent paths and cleanup, see [Storage and backups](../configuration/storage.md).

Opening the Log tab during a run restores its history and live steps. Reconnecting refreshes job details and log snapshots. Initial connection failures retry automatically; **Retry now** retries immediately, including the required catalogs.
